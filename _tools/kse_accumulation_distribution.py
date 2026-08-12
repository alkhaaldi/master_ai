"""
Detect accumulation vs distribution for each KSE stock using:
  - OBV trend (last 20 and 50 bars)
  - Price vs OBV divergence
  - Volume on up days vs down days
  - Accumulation/Distribution Line (calculated from OHLCV)
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


def analyze(sym, fn, recent=20):
    d = pd.read_csv(DL / fn)
    d = d.loc[:, ~d.columns.duplicated()].sort_values("time").reset_index(drop=True)

    # Accumulation/Distribution Line (Chaikin)
    mfm = ((d["close"] - d["low"]) - (d["high"] - d["close"])) / (d["high"] - d["low"]).replace(0, np.nan)
    mfv = mfm * d["Volume"]
    d["ADL"] = mfv.fillna(0).cumsum()

    last = d.tail(recent).reset_index(drop=True)
    price_change = (last["close"].iloc[-1] / last["close"].iloc[0] - 1) * 100
    obv_change = (last["OnBalanceVolume"].iloc[-1] - last["OnBalanceVolume"].iloc[0]) / abs(last["OnBalanceVolume"].iloc[0] + 1) * 100
    adl_change = (last["ADL"].iloc[-1] - last["ADL"].iloc[0]) / abs(last["ADL"].iloc[0] + 1) * 100

    # Volume bias: up-day volume vs down-day volume
    last["ret"] = last["close"].pct_change()
    up_vol = last.loc[last["ret"] > 0, "Volume"].sum()
    dn_vol = last.loc[last["ret"] < 0, "Volume"].sum()
    vol_ratio = up_vol / dn_vol if dn_vol else float("inf")

    # OBV slope (last 20 vs prior 20)
    obv_20 = d["OnBalanceVolume"].tail(20).mean()
    obv_50 = d["OnBalanceVolume"].tail(50).head(30).mean()
    obv_trend = "صاعد" if obv_20 > obv_50 else "هابط"

    # Divergence check (last 20 bars)
    price_dir = "صاعد" if price_change > 1 else "هابط" if price_change < -1 else "ثابت"
    obv_dir   = "صاعد" if obv_change > 1 else "هابط" if obv_change < -1 else "ثابت"

    divergence = ""
    if price_dir == "هابط" and obv_dir == "صاعد":
        divergence = "🟢 تباعد إيجابي (التجميع المخفي!)"
    elif price_dir == "صاعد" and obv_dir == "هابط":
        divergence = "🔴 تباعد سلبي (التصريف المخفي!)"
    elif price_dir == "صاعد" and obv_dir == "صاعد":
        divergence = "🟢 تجميع علني"
    elif price_dir == "هابط" and obv_dir == "هابط":
        divergence = "🔴 تصريف علني"
    else:
        divergence = "⚪ محايد"

    # Final verdict
    score = 0
    if obv_change > 1: score += 1
    if adl_change > 1: score += 1
    if vol_ratio > 1.2: score += 1
    if obv_20 > obv_50: score += 1
    if obv_change < -1: score -= 1
    if adl_change < -1: score -= 1
    if vol_ratio < 0.8: score -= 1
    if obv_20 < obv_50: score -= 1

    if   score >= 3: verdict = "🟢🟢 تجميع قوي"
    elif score >= 1: verdict = "🟢 تجميع"
    elif score <= -3: verdict = "🔴🔴 تصريف قوي"
    elif score <= -1: verdict = "🔴 تصريف"
    else: verdict = "⚪ محايد/تذبذب"

    return {
        "السهم": sym,
        "السعر الحالي": round(d["close"].iloc[-1], 2),
        f"تغير السعر {recent}ي": f"{price_change:+.1f}%",
        f"تغير OBV {recent}ي": f"{obv_change:+.1f}%",
        f"تغير A/D {recent}ي": f"{adl_change:+.1f}%",
        "نسبة فوليوم صعود/هبوط": f"{vol_ratio:.2f}",
        "اتجاه OBV (20 vs 50)": obv_trend,
        "التباعد": divergence,
        "الحكم النهائي": verdict,
    }


def main():
    rows = [analyze(sym, fn) for sym, fn in FILES.items()]
    df = pd.DataFrame(rows)
    pd.set_option("display.unicode.east_asian_width", True)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 30)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
