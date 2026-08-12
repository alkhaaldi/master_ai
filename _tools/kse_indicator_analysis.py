"""
KSE indicator backtest — find which indicator best predicts rises and falls,
and the exact trigger value.

Tests across 7 KSE daily CSVs:
  EQUIPMENT, ALOLA, KPROJ, CLEANING, GFH, KFH, NRE
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

LOOKAHEAD = 5         # days ahead to measure direction
MIN_MOVE_PCT = 1.0    # ignore tiny moves (<1%) as noise


def load(symbol):
    df = pd.read_csv(DL / FILES[symbol])
    # de-dupe Plot columns
    df = df.loc[:, ~df.columns.duplicated()]
    df = df.sort_values("time").reset_index(drop=True)
    df["future_close"] = df["close"].shift(-LOOKAHEAD)
    df["future_ret_pct"] = (df["future_close"] - df["close"]) / df["close"] * 100
    df["future_up"] = df["future_ret_pct"] >= MIN_MOVE_PCT
    df["future_dn"] = df["future_ret_pct"] <= -MIN_MOVE_PCT
    df["symbol"] = symbol
    return df


def all_data():
    frames = [load(s) for s in FILES]
    return pd.concat(frames, ignore_index=True)


# ---------- Test 1: RSI thresholds ----------
def test_rsi(df, low=10, high=90, step=1):
    """For each oversold level X: when RSI<=X, what % of time price rose >=1% in 5d?
       For each overbought level Y: when RSI>=Y, what % of time price fell >=1% in 5d?"""
    results = []
    valid = df.dropna(subset=["RSI", "future_ret_pct"])
    for x in range(low, 51, step):
        mask = valid["RSI"] <= x
        n = mask.sum()
        if n < 20:
            continue
        hit_up = valid.loc[mask, "future_up"].mean() * 100
        avg_ret = valid.loc[mask, "future_ret_pct"].mean()
        results.append({"indicator": "RSI", "direction": "BUY (oversold)",
                        "threshold": f"<= {x}", "trigger_value": x,
                        "samples": int(n), "hit_rate_pct": round(hit_up, 1),
                        "avg_5d_return_pct": round(avg_ret, 2)})
    for y in range(50, high + 1, step):
        mask = valid["RSI"] >= y
        n = mask.sum()
        if n < 20:
            continue
        hit_dn = valid.loc[mask, "future_dn"].mean() * 100
        avg_ret = valid.loc[mask, "future_ret_pct"].mean()
        results.append({"indicator": "RSI", "direction": "SELL (overbought)",
                        "threshold": f">= {y}", "trigger_value": y,
                        "samples": int(n), "hit_rate_pct": round(hit_dn, 1),
                        "avg_5d_return_pct": round(avg_ret, 2)})
    return pd.DataFrame(results)


# ---------- Test 2: Stochastic %K thresholds ----------
def test_stoch(df, low=5, high=95, step=5):
    results = []
    valid = df.dropna(subset=["%K", "future_ret_pct"])
    for x in range(low, 51, step):
        mask = valid["%K"] <= x
        n = mask.sum()
        if n < 20:
            continue
        hit_up = valid.loc[mask, "future_up"].mean() * 100
        avg_ret = valid.loc[mask, "future_ret_pct"].mean()
        results.append({"indicator": "Stoch %K", "direction": "BUY (oversold)",
                        "threshold": f"<= {x}", "trigger_value": x,
                        "samples": int(n), "hit_rate_pct": round(hit_up, 1),
                        "avg_5d_return_pct": round(avg_ret, 2)})
    for y in range(50, high + 1, step):
        mask = valid["%K"] >= y
        n = mask.sum()
        if n < 20:
            continue
        hit_dn = valid.loc[mask, "future_dn"].mean() * 100
        avg_ret = valid.loc[mask, "future_ret_pct"].mean()
        results.append({"indicator": "Stoch %K", "direction": "SELL (overbought)",
                        "threshold": f">= {y}", "trigger_value": y,
                        "samples": int(n), "hit_rate_pct": round(hit_dn, 1),
                        "avg_5d_return_pct": round(avg_ret, 2)})
    return pd.DataFrame(results)


# ---------- Test 3: MACD histogram cross zero ----------
def test_macd_cross(df):
    results = []
    valid = df.dropna(subset=["Histogram", "future_ret_pct"]).copy()
    valid["prev_hist"] = valid["Histogram"].shift(1)
    valid["cross_up"]   = (valid["prev_hist"] < 0) & (valid["Histogram"] > 0)
    valid["cross_down"] = (valid["prev_hist"] > 0) & (valid["Histogram"] < 0)
    for direction, col, target in [
        ("BUY (hist cross > 0)",   "cross_up",   "future_up"),
        ("SELL (hist cross < 0)",  "cross_down", "future_dn"),
    ]:
        mask = valid[col]
        n = mask.sum()
        if n < 20:
            continue
        hit = valid.loc[mask, target].mean() * 100
        avg = valid.loc[mask, "future_ret_pct"].mean()
        results.append({"indicator": "MACD Histogram cross 0",
                        "direction": direction, "threshold": "cross",
                        "trigger_value": 0,
                        "samples": int(n), "hit_rate_pct": round(hit, 1),
                        "avg_5d_return_pct": round(avg, 2)})
    return pd.DataFrame(results)


# ---------- Test 4: Long-exit / Short-exit raw signal columns ----------
def test_long_short_exit(df):
    """Long exit / Short exit appear to be Supertrend-like bands.
       Test: when close crosses above Short-exit -> bullish; below Long-exit -> bearish."""
    results = []
    valid = df.dropna(subset=["Long exit", "Short exit", "future_ret_pct"]).copy()
    valid["above_short_exit"] = valid["close"] > valid["Short exit"]
    valid["below_long_exit"]  = valid["close"] < valid["Long exit"]
    valid["prev_above_se"] = valid["above_short_exit"].shift(1)
    valid["prev_below_le"] = valid["below_long_exit"].shift(1)
    valid["buy_cross"]  = valid["above_short_exit"] & (~valid["prev_above_se"].astype(bool))
    valid["sell_cross"] = valid["below_long_exit"]  & (~valid["prev_below_le"].astype(bool))
    for label, col, target in [
        ("BUY (close crosses above Short-exit)",  "buy_cross",  "future_up"),
        ("SELL (close crosses below Long-exit)",  "sell_cross", "future_dn"),
    ]:
        mask = valid[col]
        n = mask.sum()
        if n < 5:
            continue
        hit = valid.loc[mask, target].mean() * 100
        avg = valid.loc[mask, "future_ret_pct"].mean()
        results.append({"indicator": "Long/Short Exit (Supertrend)",
                        "direction": label, "threshold": "cross",
                        "trigger_value": "—",
                        "samples": int(n), "hit_rate_pct": round(hit, 1),
                        "avg_5d_return_pct": round(avg, 2)})
    return pd.DataFrame(results)


# ---------- Test 5: Regular Bullish / Bearish divergences ----------
def test_divergence(df):
    results = []
    valid = df.dropna(subset=["future_ret_pct"]).copy()
    for col, dir_label, target in [
        ("Regular Bullish", "BUY (Bullish divergence)", "future_up"),
        ("Regular Bearish", "SELL (Bearish divergence)", "future_dn"),
    ]:
        if col not in valid.columns:
            continue
        mask = pd.to_numeric(valid[col], errors="coerce").fillna(0) > 0
        n = mask.sum()
        if n < 5:
            continue
        hit = valid.loc[mask, target].mean() * 100
        avg = valid.loc[mask, "future_ret_pct"].mean()
        results.append({"indicator": "RSI Divergence",
                        "direction": dir_label, "threshold": "signal",
                        "trigger_value": "—",
                        "samples": int(n), "hit_rate_pct": round(hit, 1),
                        "avg_5d_return_pct": round(avg, 2)})
    return pd.DataFrame(results)


# ---------- Test 6: Trendline crosses ----------
def test_trendline(df):
    results = []
    valid = df.dropna(subset=["future_ret_pct"]).copy()
    for col, dir_label, target in [
        ("Crossed upper trendline", "SELL (cross upper TL)", "future_dn"),
        ("Crossed lower trendline", "BUY (cross lower TL)", "future_up"),
    ]:
        if col not in valid.columns:
            continue
        mask = pd.to_numeric(valid[col], errors="coerce").fillna(0) > 0
        n = mask.sum()
        if n < 5:
            continue
        hit = valid.loc[mask, target].mean() * 100
        avg = valid.loc[mask, "future_ret_pct"].mean()
        results.append({"indicator": "Trendline cross",
                        "direction": dir_label, "threshold": "signal",
                        "trigger_value": "—",
                        "samples": int(n), "hit_rate_pct": round(hit, 1),
                        "avg_5d_return_pct": round(avg, 2)})
    return pd.DataFrame(results)


# ---------- baseline ----------
def baseline(df):
    valid = df.dropna(subset=["future_ret_pct"])
    p_up = valid["future_up"].mean() * 100
    p_dn = valid["future_dn"].mean() * 100
    return round(p_up, 1), round(p_dn, 1), len(valid)


def main():
    df = all_data()
    bup, bdn, total = baseline(df)
    print(f"=== Dataset: {total} bars across {len(FILES)} stocks ===")
    print(f"Baseline P(up>=1% in {LOOKAHEAD}d) = {bup}%   P(down>=1%) = {bdn}%\n")

    all_results = pd.concat([
        test_rsi(df),
        test_stoch(df),
        test_macd_cross(df),
        test_long_short_exit(df),
        test_divergence(df),
        test_trendline(df),
    ], ignore_index=True)

    all_results.to_csv(r"S:\_tools\kse_indicator_results.csv", index=False)

    # --- top BUY signals (best at predicting rises) ---
    buys = all_results[all_results["direction"].str.startswith("BUY")]
    buys = buys[buys["samples"] >= 30].sort_values("hit_rate_pct", ascending=False)
    print(">>> TOP BUY signals (predicting >=1% rise in 5 days):")
    print(buys.head(10).to_string(index=False))

    sells = all_results[all_results["direction"].str.startswith("SELL")]
    sells = sells[sells["samples"] >= 30].sort_values("hit_rate_pct", ascending=False)
    print("\n>>> TOP SELL signals (predicting >=1% fall in 5 days):")
    print(sells.head(10).to_string(index=False))

    # --- composite: weight hit_rate by samples and edge over baseline ---
    all_results["edge_pct"] = all_results.apply(
        lambda r: r["hit_rate_pct"] - (bup if r["direction"].startswith("BUY") else bdn),
        axis=1
    )
    sig = all_results[all_results["samples"] >= 30].copy()
    sig = sig.sort_values("edge_pct", ascending=False)
    print("\n>>> Best EDGE over baseline (samples>=30):")
    print(sig.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
