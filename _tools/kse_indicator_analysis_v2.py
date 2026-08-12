"""
KSE indicator backtest v2 — focus on CROSSING events (not just thresholds)
and per-stock breakdown, plus multiple lookaheads.
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

LOOKAHEADS = [3, 5, 10]
MIN_MOVE_PCT = 1.0


def load(symbol):
    df = pd.read_csv(DL / FILES[symbol])
    df = df.loc[:, ~df.columns.duplicated()]
    df = df.sort_values("time").reset_index(drop=True)
    for la in LOOKAHEADS:
        df[f"fut_close_{la}"] = df["close"].shift(-la)
        df[f"fut_ret_{la}"] = (df[f"fut_close_{la}"] - df["close"]) / df["close"] * 100
        df[f"fut_up_{la}"] = df[f"fut_ret_{la}"] >= MIN_MOVE_PCT
        df[f"fut_dn_{la}"] = df[f"fut_ret_{la}"] <= -MIN_MOVE_PCT
    df["symbol"] = symbol
    return df


def all_data():
    return pd.concat([load(s) for s in FILES], ignore_index=True)


def evaluate(df, mask, label, indicator, trigger):
    rows = []
    for la in LOOKAHEADS:
        sub = df.loc[mask].dropna(subset=[f"fut_ret_{la}"])
        n = len(sub)
        if n < 20:
            continue
        hit_up = sub[f"fut_up_{la}"].mean() * 100
        hit_dn = sub[f"fut_dn_{la}"].mean() * 100
        avg = sub[f"fut_ret_{la}"].mean()
        rows.append({
            "indicator": indicator,
            "signal": label,
            "trigger": trigger,
            "lookahead": la,
            "samples": n,
            "hit_up%": round(hit_up, 1),
            "hit_dn%": round(hit_dn, 1),
            "avg_ret%": round(avg, 2),
        })
    return rows


def main():
    df = all_data()
    print(f"=== {len(df)} bars across {len(FILES)} stocks ===\n")

    # baselines
    for la in LOOKAHEADS:
        sub = df.dropna(subset=[f"fut_ret_{la}"])
        print(f"baseline {la}d: up>={MIN_MOVE_PCT}% = {sub[f'fut_up_{la}'].mean()*100:.1f}% | "
              f"down>={MIN_MOVE_PCT}% = {sub[f'fut_dn_{la}'].mean()*100:.1f}% | "
              f"avg ret = {sub[f'fut_ret_{la}'].mean():.2f}%")
    print()

    rows = []

    # --- RSI crossing back UP through key oversold levels (classic BUY) ---
    rsi = df["RSI"]
    rsi_prev = rsi.shift(1)
    for lvl in [20, 25, 30, 35]:
        mask = (rsi_prev < lvl) & (rsi >= lvl)
        rows += evaluate(df, mask, f"RSI crosses UP through {lvl}", "RSI cross up", lvl)

    # --- RSI crossing DOWN through key overbought levels (classic SELL) ---
    for lvl in [65, 70, 75, 80, 85, 90]:
        mask = (rsi_prev > lvl) & (rsi <= lvl)
        rows += evaluate(df, mask, f"RSI crosses DOWN through {lvl}", "RSI cross down", lvl)

    # --- RSI absolute extremes ---
    for lvl in [10, 15, 20, 25, 30]:
        mask = rsi <= lvl
        rows += evaluate(df, mask, f"RSI <= {lvl}", "RSI low", lvl)
    for lvl in [70, 75, 80, 85, 90, 95]:
        mask = rsi >= lvl
        rows += evaluate(df, mask, f"RSI >= {lvl}", "RSI high", lvl)

    # --- Stoch %K cross through %D ---
    k = df["%K"]; d = df["%D"]
    k_prev = k.shift(1); d_prev = d.shift(1)
    mask_bull = (k_prev < d_prev) & (k > d) & (k < 30)
    rows += evaluate(df, mask_bull, "Stoch %K crosses %D in oversold (<30)", "Stoch", 30)
    mask_bear = (k_prev > d_prev) & (k < d) & (k > 70)
    rows += evaluate(df, mask_bear, "Stoch %K crosses %D in overbought (>70)", "Stoch", 70)

    # --- Stoch absolute extremes ---
    for lvl in [10, 15, 20]:
        rows += evaluate(df, k <= lvl, f"Stoch %K <= {lvl}", "Stoch low", lvl)
    for lvl in [80, 85, 90, 95]:
        rows += evaluate(df, k >= lvl, f"Stoch %K >= {lvl}", "Stoch high", lvl)

    # --- MACD histogram zero-cross ---
    h = df["Histogram"]; h_prev = h.shift(1)
    rows += evaluate(df, (h_prev < 0) & (h > 0), "MACD hist crosses ABOVE 0", "MACD", 0)
    rows += evaluate(df, (h_prev > 0) & (h < 0), "MACD hist crosses BELOW 0", "MACD", 0)

    # --- MACD line crosses Signal ---
    m = df["MACD"]; s = df["Signal line"]
    m_prev = m.shift(1); s_prev = s.shift(1)
    rows += evaluate(df, (m_prev < s_prev) & (m > s), "MACD crosses ABOVE Signal", "MACD/Sig", "cross")
    rows += evaluate(df, (m_prev > s_prev) & (m < s), "MACD crosses BELOW Signal", "MACD/Sig", "cross")

    # --- Long/Short exit Supertrend-style crosses ---
    le = df["Long exit"]; se = df["Short exit"]; close = df["close"]
    above_se = close > se; below_le = close < le
    rows += evaluate(df,
        above_se & ~above_se.shift(1).fillna(False).astype(bool),
        "Close crosses ABOVE Short-exit (Supertrend BUY)", "Supertrend", "cross")
    rows += evaluate(df,
        below_le & ~below_le.shift(1).fillna(False).astype(bool),
        "Close crosses BELOW Long-exit (Supertrend SELL)", "Supertrend", "cross")

    # --- Divergences ---
    for col, lbl in [("Regular Bullish", "Regular Bullish divergence"),
                      ("Regular Bearish", "Regular Bearish divergence")]:
        if col in df.columns:
            mask = pd.to_numeric(df[col], errors="coerce").fillna(0) > 0
            rows += evaluate(df, mask, lbl, "Divergence", "signal")

    # --- Trendline crosses ---
    for col, lbl in [("Crossed upper trendline", "Crossed upper trendline"),
                      ("Crossed lower trendline", "Crossed lower trendline")]:
        if col in df.columns:
            mask = pd.to_numeric(df[col], errors="coerce").fillna(0) > 0
            rows += evaluate(df, mask, lbl, "Trendline", "signal")

    res = pd.DataFrame(rows)
    res.to_csv(r"S:\_tools\kse_indicator_results_v2.csv", index=False)

    # Best BUY: filter signals expected to predict UP; use hit_up%
    buy_sigs = res[res["signal"].str.contains("UP|BUY|Bullish|lower TL|<=|low|oversold|ABOVE 0|ABOVE Sig",
                                              case=False, regex=True)]
    print(">>> TOP BUY signals (by hit_up%, samples>=30):")
    print(buy_sigs[buy_sigs["samples"] >= 30]
          .sort_values("hit_up%", ascending=False).head(15).to_string(index=False))

    sell_sigs = res[res["signal"].str.contains("DOWN|SELL|Bearish|upper TL|>=|high|overbought|BELOW 0|BELOW Sig",
                                               case=False, regex=True)]
    print("\n>>> TOP SELL signals (by hit_dn%, samples>=30):")
    print(sell_sigs[sell_sigs["samples"] >= 30]
          .sort_values("hit_dn%", ascending=False).head(15).to_string(index=False))

    # Highest average return BUY signals
    print("\n>>> Highest avg-return BUY-style signals (samples>=20):")
    print(buy_sigs[buy_sigs["samples"] >= 20]
          .sort_values("avg_ret%", ascending=False).head(10).to_string(index=False))

    print("\n>>> Most-negative avg-return SELL-style signals (samples>=20):")
    print(sell_sigs[sell_sigs["samples"] >= 20]
          .sort_values("avg_ret%", ascending=True).head(10).to_string(index=False))


if __name__ == "__main__":
    main()
