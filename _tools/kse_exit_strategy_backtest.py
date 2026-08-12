"""
Compare exit strategies for the BUY signal:
   BUY = close crosses ABOVE Short exit while in downtrend (prior 10d ret <= -5%)

Strategies tested:
  A. Hold-until-Long-exit-cross   (default Chandelier behavior)
  B. Fixed TP only                (test TP at 2,3,4,5,6,8,10%)
  C. Fixed TP + Long-exit SL      (combo: whichever hits first)
  D. Trailing Long-exit           (exit when close < Long exit, no TP)
  E. Time exit after N bars       (test 3,5,7,10)
  F. ATR-based TP+SL              (TP=entry+k*ATR, SL=entry-m*ATR)
  G. Smart exit: Long exit OR price drop > X% from peak
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

TREND_LB  = 10
TREND_PCT = 5.0
MAX_HOLD  = 30  # max bars to hold before forced exit


def load_all():
    frames = []
    for sym, fn in FILES.items():
        d = pd.read_csv(DL / fn)
        d = d.loc[:, ~d.columns.duplicated()].sort_values("time").reset_index(drop=True)
        d["prior_ret"] = (d["close"] / d["close"].shift(TREND_LB) - 1) * 100
        d["in_downtrend"] = d["prior_ret"] <= -TREND_PCT
        d["symbol"] = sym
        # ATR for ATR-based strategy
        tr = pd.concat([d["high"] - d["low"],
                        (d["high"] - d["close"].shift()).abs(),
                        (d["low"]  - d["close"].shift()).abs()], axis=1).max(axis=1)
        d["atr"] = tr.rolling(14).mean()
        frames.append(d)
    return pd.concat(frames, ignore_index=True), {sym: f for sym, f in zip(FILES, frames)}


def buy_signal_bars(df):
    """Bars where close crosses ABOVE Short exit AND in downtrend"""
    above = df["close"] > df["Short exit"]
    cross_up = above & ~above.shift(1).fillna(False).astype(bool)
    return df.index[cross_up & df["in_downtrend"]].tolist()


def simulate_trade(df_sym, entry_idx, strategy, **params):
    """
    Walk forward from entry_idx and apply exit strategy.
    Returns (exit_idx, exit_price, return_pct, bars_held, exit_reason)
    """
    entry_price = df_sym.at[entry_idx, "close"]
    atr_at_entry = df_sym.at[entry_idx, "atr"]
    peak = entry_price

    for i in range(1, MAX_HOLD + 1):
        idx = entry_idx + i
        if idx >= len(df_sym):
            break
        row = df_sym.loc[idx]
        high = row["high"]; low = row["low"]; close = row["close"]
        long_exit = row["Long exit"]
        peak = max(peak, high)

        if strategy == "A":  # Hold until close crosses below Long exit
            if close < long_exit:
                return idx, close, (close / entry_price - 1) * 100, i, "long_exit_cross"

        elif strategy == "B":  # Fixed TP only
            tp = entry_price * (1 + params["tp_pct"] / 100)
            if high >= tp:
                return idx, tp, params["tp_pct"], i, "tp_hit"

        elif strategy == "C":  # Fixed TP + Long-exit SL
            tp = entry_price * (1 + params["tp_pct"] / 100)
            if high >= tp:
                return idx, tp, params["tp_pct"], i, "tp_hit"
            if close < long_exit:
                return idx, close, (close / entry_price - 1) * 100, i, "long_exit_cross"

        elif strategy == "D":  # Pure Long-exit trail (same as A)
            if close < long_exit:
                return idx, close, (close / entry_price - 1) * 100, i, "long_exit_cross"

        elif strategy == "E":  # Time exit after N bars
            if i >= params["bars"]:
                return idx, close, (close / entry_price - 1) * 100, i, "time"

        elif strategy == "F":  # ATR TP + ATR SL
            tp = entry_price + params["k"] * atr_at_entry
            sl = entry_price - params["m"] * atr_at_entry
            if low <= sl:
                return idx, sl, (sl / entry_price - 1) * 100, i, "atr_sl"
            if high >= tp:
                return idx, tp, (tp / entry_price - 1) * 100, i, "atr_tp"

        elif strategy == "G":  # Smart: Long-exit OR drop X% from peak
            drop = (close - peak) / peak * 100
            if close < long_exit:
                return idx, close, (close / entry_price - 1) * 100, i, "long_exit_cross"
            if drop <= -params["drop_pct"]:
                return idx, close, (close / entry_price - 1) * 100, i, "peak_drop"

        elif strategy == "H":  # TP at X% AND trailing Long-exit (whichever first)
                                # but also a peak-drop guard
            tp = entry_price * (1 + params["tp_pct"] / 100)
            if high >= tp:
                return idx, tp, params["tp_pct"], i, "tp_hit"
            if close < long_exit:
                return idx, close, (close / entry_price - 1) * 100, i, "long_exit_cross"
            drop = (close - peak) / peak * 100
            if drop <= -params["drop_pct"]:
                return idx, close, (close / entry_price - 1) * 100, i, "peak_drop"

    # forced exit at MAX_HOLD
    idx = min(entry_idx + MAX_HOLD, len(df_sym) - 1)
    close = df_sym.at[idx, "close"]
    return idx, close, (close / entry_price - 1) * 100, idx - entry_idx, "max_hold"


def evaluate_strategy(per_sym, strategy, **params):
    """Run strategy across all symbols, return summary stats."""
    trades = []
    for sym, df_sym in per_sym.items():
        entries = buy_signal_bars(df_sym)
        for e in entries:
            res = simulate_trade(df_sym, e, strategy, **params)
            if res is None:
                continue
            exit_idx, exit_price, ret, bars, reason = res
            trades.append({
                "symbol": sym, "entry_idx": e, "exit_idx": exit_idx,
                "return_pct": ret, "bars_held": bars, "exit_reason": reason,
            })
    if not trades:
        return None
    tdf = pd.DataFrame(trades)
    n = len(tdf)
    wins = tdf[tdf["return_pct"] > 0]
    losses = tdf[tdf["return_pct"] <= 0]
    win_rate = len(wins) / n * 100
    avg_ret = tdf["return_pct"].mean()
    avg_win = wins["return_pct"].mean() if len(wins) else 0
    avg_loss = losses["return_pct"].mean() if len(losses) else 0
    profit_factor = (wins["return_pct"].sum() / abs(losses["return_pct"].sum())) if len(losses) and losses["return_pct"].sum() != 0 else float("inf")
    # Total return assuming compounding 1% of capital per trade equivalent (simple)
    total = tdf["return_pct"].sum()
    expectancy = avg_ret  # avg return per trade
    avg_bars = tdf["bars_held"].mean()
    return {
        "trades": n,
        "win_rate%": round(win_rate, 1),
        "avg_return%": round(avg_ret, 2),
        "avg_win%": round(avg_win, 2),
        "avg_loss%": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "total_return%": round(total, 1),
        "expectancy%": round(expectancy, 2),
        "avg_bars_held": round(avg_bars, 1),
    }, tdf


def main():
    df_all, per_sym = load_all()
    print(f"Loaded {len(df_all)} bars across {len(FILES)} stocks")
    n_signals = sum(len(buy_signal_bars(per_sym[s])) for s in per_sym)
    print(f"Total BUY signals (Chandelier cross-up in downtrend): {n_signals}\n")

    configs = [
        ("A - Hold till Long-exit cross", "A", {}),
        ("B - Fixed TP 2%",  "B", {"tp_pct": 2}),
        ("B - Fixed TP 3%",  "B", {"tp_pct": 3}),
        ("B - Fixed TP 4%",  "B", {"tp_pct": 4}),
        ("B - Fixed TP 5%",  "B", {"tp_pct": 5}),
        ("B - Fixed TP 7%",  "B", {"tp_pct": 7}),
        ("B - Fixed TP 10%", "B", {"tp_pct": 10}),
        ("C - TP 3% + LE-SL", "C", {"tp_pct": 3}),
        ("C - TP 4% + LE-SL", "C", {"tp_pct": 4}),
        ("C - TP 5% + LE-SL", "C", {"tp_pct": 5}),
        ("C - TP 7% + LE-SL", "C", {"tp_pct": 7}),
        ("C - TP 10% + LE-SL","C", {"tp_pct": 10}),
        ("E - Time 3 bars",  "E", {"bars": 3}),
        ("E - Time 5 bars",  "E", {"bars": 5}),
        ("E - Time 7 bars",  "E", {"bars": 7}),
        ("E - Time 10 bars", "E", {"bars": 10}),
        ("F - ATR TP=3,SL=2", "F", {"k": 3, "m": 2}),
        ("F - ATR TP=2,SL=1", "F", {"k": 2, "m": 1}),
        ("F - ATR TP=4,SL=2", "F", {"k": 4, "m": 2}),
        ("G - LE OR drop 2% from peak", "G", {"drop_pct": 2}),
        ("G - LE OR drop 3% from peak", "G", {"drop_pct": 3}),
        ("G - LE OR drop 4% from peak", "G", {"drop_pct": 4}),
        ("G - LE OR drop 5% from peak", "G", {"drop_pct": 5}),
        ("H - TP 5% + LE + drop 3%",  "H", {"tp_pct": 5, "drop_pct": 3}),
        ("H - TP 7% + LE + drop 3%",  "H", {"tp_pct": 7, "drop_pct": 3}),
        ("H - TP 10% + LE + drop 3%", "H", {"tp_pct": 10, "drop_pct": 3}),
        ("H - TP 7% + LE + drop 2%",  "H", {"tp_pct": 7, "drop_pct": 2}),
        ("H - TP 5% + LE + drop 2%",  "H", {"tp_pct": 5, "drop_pct": 2}),
    ]

    rows = []
    for name, strat, params in configs:
        stats, _ = evaluate_strategy(per_sym, strat, **params)
        if stats:
            rows.append({"strategy": name, **stats})

    res = pd.DataFrame(rows)
    res.to_csv(r"S:\_tools\exit_strategy_results.csv", index=False)

    print("=" * 110)
    print(">>> Ranked by AVG RETURN per trade (expectancy):")
    print(res.sort_values("avg_return%", ascending=False).to_string(index=False))

    print("\n" + "=" * 110)
    print(">>> Ranked by WIN RATE:")
    print(res.sort_values("win_rate%", ascending=False).to_string(index=False))

    print("\n" + "=" * 110)
    print(">>> Ranked by PROFIT FACTOR (best risk/reward):")
    print(res.sort_values("profit_factor", ascending=False).to_string(index=False))

    print("\n" + "=" * 110)
    print(">>> Ranked by TOTAL RETURN (cumulative across all signals):")
    print(res.sort_values("total_return%", ascending=False).to_string(index=False))


if __name__ == "__main__":
    main()
