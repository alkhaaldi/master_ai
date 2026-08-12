"""
KSE REVERSAL detection — which indicator best catches:
  (a) end of an UPTREND  (rise then sharp fall)
  (b) end of a DOWNTREND (fall then sharp rise)

Method:
  Define "in uptrend"   = close gained >= TREND_PCT in prior TREND_LB bars
  Define "in downtrend" = close lost   >= TREND_PCT in prior TREND_LB bars
  Reversal SUCCESS if next FWD bars produce opposite move >= REV_PCT
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

TREND_LB  = 10   # look back 10 bars for trend
TREND_PCT = 5.0  # >=5% prior move = "in trend"
FWD       = 5    # forward window
REV_PCT   = 2.0  # >=2% opposite move = successful reversal


def load_all():
    frames = []
    for sym, fn in FILES.items():
        d = pd.read_csv(DL / fn)
        d = d.loc[:, ~d.columns.duplicated()]
        d = d.sort_values("time").reset_index(drop=True)
        # prior trend
        d["prior_ret"] = (d["close"] / d["close"].shift(TREND_LB) - 1) * 100
        d["in_uptrend"]   = d["prior_ret"] >=  TREND_PCT
        d["in_downtrend"] = d["prior_ret"] <= -TREND_PCT
        # forward reversal
        d["fwd_high"] = d["high"].rolling(FWD).max().shift(-FWD)
        d["fwd_low"]  = d["low"].rolling(FWD).min().shift(-FWD)
        d["fwd_max_up"]   = (d["fwd_high"] / d["close"] - 1) * 100
        d["fwd_max_down"] = (d["fwd_low"]  / d["close"] - 1) * 100
        d["reversed_down"] = d["fwd_max_down"] <= -REV_PCT
        d["reversed_up"]   = d["fwd_max_up"]   >=  REV_PCT
        d["symbol"] = sym
        frames.append(d)
    return pd.concat(frames, ignore_index=True)


def score(df, mask, label, mode):
    """mode='top' = signal at uptrend top → expect reversal down
       mode='bot' = signal at downtrend bottom → expect reversal up"""
    if mode == "top":
        ctx = df["in_uptrend"]; target = "reversed_down"; ctx_label = "in_uptrend"
    else:
        ctx = df["in_downtrend"]; target = "reversed_up"; ctx_label = "in_downtrend"

    base_mask = ctx & df[target].notna() & df["fwd_max_up"].notna() & df["fwd_max_down"].notna()
    base = df.loc[base_mask, target].mean() * 100

    sig_mask = base_mask & mask.fillna(False)
    n = sig_mask.sum()
    if n < 20:
        return None
    hit = df.loc[sig_mask, target].mean() * 100
    return {
        "signal": label,
        "mode": "END_OF_RISE" if mode == "top" else "END_OF_FALL",
        "context": ctx_label,
        "n": int(n),
        "hit_rate%": round(hit, 1),
        "context_base%": round(base, 1),
        "edge_pp": round(hit - base, 1),
    }


def main():
    df = load_all()
    n_up = df["in_uptrend"].sum()
    n_dn = df["in_downtrend"].sum()
    print(f"Bars: {len(df)} | in_uptrend: {n_up} | in_downtrend: {n_dn}\n")

    valid_top = df["in_uptrend"] & df["reversed_down"].notna()
    valid_bot = df["in_downtrend"] & df["reversed_up"].notna()
    base_top = df.loc[valid_top, "reversed_down"].mean() * 100
    base_bot = df.loc[valid_bot, "reversed_up"].mean() * 100
    print(f"Base: when in uptrend, prob of >={REV_PCT}% drop in next {FWD} bars = {base_top:.1f}%")
    print(f"Base: when in downtrend, prob of >={REV_PCT}% rise in next {FWD} bars = {base_bot:.1f}%\n")

    rsi = df["RSI"]; rsi_prev = rsi.shift(1)
    rsi_ma = df["RSI-based MA"]
    k = df["%K"]; d_st = df["%D"]
    k_prev = k.shift(1); d_prev = d_st.shift(1)
    h = df["Histogram"]; h_prev = h.shift(1)
    m = df["MACD"]; s = df["Signal line"]
    m_prev = m.shift(1); s_prev = s.shift(1)
    le = df["Long exit"]; se = df["Short exit"]; cl = df["close"]
    above_se = cl > se; below_le = cl < le
    bull_div = pd.to_numeric(df["Regular Bullish"], errors="coerce").fillna(0) > 0
    bear_div = pd.to_numeric(df["Regular Bearish"], errors="coerce").fillna(0) > 0
    cr_upper = pd.to_numeric(df["Crossed upper trendline"], errors="coerce").fillna(0) > 0
    cr_lower = pd.to_numeric(df["Crossed lower trendline"], errors="coerce").fillna(0) > 0

    rows = []

    # ---- END_OF_RISE candidates (top reversal signals) ----
    for lvl in [70, 75, 80, 85, 90, 92, 94, 95, 96, 97]:
        rows.append(score(df, rsi >= lvl, f"RSI >= {lvl}", "top"))
    for lvl in [60, 65, 70, 75, 80, 85, 90]:
        rows.append(score(df, (rsi_prev > lvl) & (rsi <= lvl),
                          f"RSI crosses DOWN through {lvl}", "top"))
    rows.append(score(df, (rsi_prev > rsi_ma.shift(1)) & (rsi < rsi_ma),
                      "RSI crosses BELOW its MA", "top"))
    for lvl in [80, 85, 90, 95]:
        rows.append(score(df, k >= lvl, f"Stoch %K >= {lvl}", "top"))
    rows.append(score(df, (k_prev > d_prev) & (k < d_st) & (k > 70),
                      "Stoch %K crosses DOWN %D in overbought (>70)", "top"))
    rows.append(score(df, (k_prev > d_prev) & (k < d_st) & (k > 80),
                      "Stoch %K crosses DOWN %D in overbought (>80)", "top"))
    rows.append(score(df, (h_prev > 0) & (h < 0), "MACD hist crosses BELOW 0", "top"))
    rows.append(score(df, (m_prev > s_prev) & (m < s), "MACD line crosses BELOW Signal", "top"))
    rows.append(score(df, below_le & ~below_le.shift(1).fillna(False).astype(bool),
                      "Close crosses BELOW Long-exit (Supertrend SELL)", "top"))
    rows.append(score(df, bear_div, "Regular Bearish Divergence", "top"))
    rows.append(score(df, cr_upper, "Crossed upper trendline", "top"))

    # ---- END_OF_FALL candidates (bottom reversal signals) ----
    for lvl in [10, 15, 20, 25, 30, 35, 40]:
        rows.append(score(df, rsi <= lvl, f"RSI <= {lvl}", "bot"))
    for lvl in [20, 25, 30, 35, 40]:
        rows.append(score(df, (rsi_prev < lvl) & (rsi >= lvl),
                          f"RSI crosses UP through {lvl}", "bot"))
    rows.append(score(df, (rsi_prev < rsi_ma.shift(1)) & (rsi > rsi_ma),
                      "RSI crosses ABOVE its MA", "bot"))
    for lvl in [5, 10, 15, 20]:
        rows.append(score(df, k <= lvl, f"Stoch %K <= {lvl}", "bot"))
    rows.append(score(df, (k_prev < d_prev) & (k > d_st) & (k < 30),
                      "Stoch %K crosses UP %D in oversold (<30)", "bot"))
    rows.append(score(df, (k_prev < d_prev) & (k > d_st) & (k < 20),
                      "Stoch %K crosses UP %D in oversold (<20)", "bot"))
    rows.append(score(df, (h_prev < 0) & (h > 0), "MACD hist crosses ABOVE 0", "bot"))
    rows.append(score(df, (m_prev < s_prev) & (m > s), "MACD line crosses ABOVE Signal", "bot"))
    rows.append(score(df, above_se & ~above_se.shift(1).fillna(False).astype(bool),
                      "Close crosses ABOVE Short-exit (Supertrend BUY)", "bot"))
    rows.append(score(df, bull_div, "Regular Bullish Divergence", "bot"))
    rows.append(score(df, cr_lower, "Crossed lower trendline", "bot"))

    res = pd.DataFrame([r for r in rows if r])
    res.to_csv(r"S:\_tools\kse_reversal_results.csv", index=False)

    print(">>> END OF UPTREND (signal after >=5% rise, predicts >=2% drop in 5d):")
    tops = res[res["mode"] == "END_OF_RISE"].sort_values("hit_rate%", ascending=False)
    print(tops.to_string(index=False))

    print("\n>>> END OF DOWNTREND (signal after >=5% drop, predicts >=2% rise in 5d):")
    bots = res[res["mode"] == "END_OF_FALL"].sort_values("hit_rate%", ascending=False)
    print(bots.to_string(index=False))

    print("\n=== BEST signals overall (by edge over context baseline) ===")
    print(res.sort_values("edge_pp", ascending=False).head(10).to_string(index=False))


if __name__ == "__main__":
    main()
