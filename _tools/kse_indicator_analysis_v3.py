"""
KSE indicator backtest v3 — rank by DIRECTIONAL EDGE (hit_dn - hit_up for SELL,
hit_up - hit_dn for BUY) and verify per-stock robustness.
"""
import pandas as pd
import numpy as np
from pathlib import Path

DL = Path(r"C:\Users\MS1\Downloads")
FILES = {
    "EQUIPMENT": "KSE_EQUIPMENT, 1D_e0b7d.csv",
    "ALOLA":     "KSE_ALOLA, 1D_ccb9b.csv",
    "KPROJ":     "KSE_KPROJ, 1D_adfa5.csv",
    "CLEANING":  "KSE_CLEANING, 1D_6c535.csv",
    "GFH":       "KSE_GFH, 1D_f8384.csv",
    "KFH":       "KSE_KFH, 1D_e7c5a.csv",
    "NRE":       "KSE_NRE, 1D_1f392.csv",
}

LA = 5      # 5-day forward
MIN = 1.0   # >=1% move


def load_all():
    frames = []
    for sym, fn in FILES.items():
        d = pd.read_csv(DL / fn)
        d = d.loc[:, ~d.columns.duplicated()]
        d = d.sort_values("time").reset_index(drop=True)
        d["fut_close"] = d["close"].shift(-LA)
        d["fut_ret"] = (d["fut_close"] - d["close"]) / d["close"] * 100
        d["fut_up"] = d["fut_ret"] >= MIN
        d["fut_dn"] = d["fut_ret"] <= -MIN
        d["symbol"] = sym
        frames.append(d)
    return pd.concat(frames, ignore_index=True)


def stats(df, mask, label, expected_dir):
    sub = df.loc[mask].dropna(subset=["fut_ret"])
    n = len(sub)
    if n < 30:
        return None
    hu = sub["fut_up"].mean() * 100
    hd = sub["fut_dn"].mean() * 100
    avg = sub["fut_ret"].mean()
    edge = (hd - hu) if expected_dir == "down" else (hu - hd)
    return {
        "signal": label,
        "expected": expected_dir,
        "samples": n,
        "hit_up%": round(hu, 1),
        "hit_dn%": round(hd, 1),
        "avg_5d_ret%": round(avg, 2),
        "directional_edge_pp": round(edge, 1),
    }


def per_stock(df, mask, label):
    """Per-stock breakdown of hit rates."""
    out = []
    for sym in FILES:
        sub = df[(df["symbol"] == sym) & mask].dropna(subset=["fut_ret"])
        n = len(sub)
        if n == 0:
            out.append({"symbol": sym, "n": 0, "hit_up%": None, "hit_dn%": None, "avg_ret%": None})
            continue
        out.append({
            "symbol": sym,
            "n": n,
            "hit_up%": round(sub["fut_up"].mean() * 100, 1),
            "hit_dn%": round(sub["fut_dn"].mean() * 100, 1),
            "avg_ret%": round(sub["fut_ret"].mean(), 2),
        })
    return pd.DataFrame(out)


def main():
    df = load_all()
    valid = df.dropna(subset=["fut_ret"])
    bup = valid["fut_up"].mean() * 100
    bdn = valid["fut_dn"].mean() * 100
    bavg = valid["fut_ret"].mean()
    print(f"=== Combined dataset ===")
    print(f"Bars: {len(valid)}")
    print(f"Baseline {LA}d: up>={MIN}% = {bup:.1f}% | dn>={MIN}% = {bdn:.1f}% | avg ret = {bavg:.2f}%\n")

    rsi = df["RSI"]; rsi_prev = rsi.shift(1)
    k = df["%K"]; d_st = df["%D"]
    k_prev = k.shift(1); d_prev = d_st.shift(1)
    h = df["Histogram"]; h_prev = h.shift(1)
    le = df["Long exit"]; se = df["Short exit"]; cl = df["close"]
    above_se = cl > se; below_le = cl < le

    candidates = []
    # SELL candidates
    for lvl in [70, 75, 80, 85, 90, 92, 93, 94, 95, 96, 97]:
        candidates.append((rsi >= lvl, f"RSI >= {lvl}", "down"))
    for lvl in [60, 65, 70, 75, 80, 85, 90]:
        candidates.append(((rsi_prev > lvl) & (rsi <= lvl),
                           f"RSI crosses DOWN through {lvl}", "down"))
    for lvl in [80, 85, 90, 95]:
        candidates.append((k >= lvl, f"Stoch %K >= {lvl}", "down"))
    candidates.append(((h_prev > 0) & (h < 0), "MACD hist crosses BELOW 0", "down"))
    candidates.append((below_le & ~below_le.shift(1).fillna(False).astype(bool),
                       "Close crosses BELOW Long-exit", "down"))

    # BUY candidates
    for lvl in [10, 15, 20, 25, 30, 35, 40]:
        candidates.append((rsi <= lvl, f"RSI <= {lvl}", "up"))
    for lvl in [20, 25, 30, 35, 40]:
        candidates.append(((rsi_prev < lvl) & (rsi >= lvl),
                           f"RSI crosses UP through {lvl}", "up"))
    for lvl in [5, 10, 15, 20]:
        candidates.append((k <= lvl, f"Stoch %K <= {lvl}", "up"))
    candidates.append(((h_prev < 0) & (h > 0), "MACD hist crosses ABOVE 0", "up"))
    candidates.append((above_se & ~above_se.shift(1).fillna(False).astype(bool),
                       "Close crosses ABOVE Short-exit", "up"))

    rows = []
    for mask, lbl, direction in candidates:
        r = stats(df, mask.fillna(False), lbl, direction)
        if r:
            rows.append(r)

    res = pd.DataFrame(rows)
    res.to_csv(r"S:\_tools\kse_indicator_results_v3.csv", index=False)

    print(">>> Ranked by DIRECTIONAL EDGE (hit_target - hit_opposite):")
    print(res.sort_values("directional_edge_pp", ascending=False).head(20).to_string(index=False))

    # Best overall
    best = res.sort_values("directional_edge_pp", ascending=False).iloc[0]
    print(f"\n=== BEST INDICATOR ===")
    print(best.to_string())

    # Robustness check for best signal
    print(f"\n=== Per-stock breakdown of: {best['signal']} ===")
    # rebuild mask for the best signal
    for mask, lbl, _ in candidates:
        if lbl == best["signal"]:
            ps = per_stock(df, mask.fillna(False), lbl)
            print(ps.to_string(index=False))
            print(f"\nStocks where edge>0 (dn>up): "
                  f"{(ps['hit_dn%'].fillna(0) > ps['hit_up%'].fillna(0)).sum()} / {len(ps)}")
            break


if __name__ == "__main__":
    main()
