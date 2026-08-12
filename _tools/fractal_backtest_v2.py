#!/usr/bin/env python3
"""
Fractal v3 Backtest V2 — Corrected
===================================
Fixes from ChatGPT analysis:
1. HL only as entry (no LL)
2. LH only as exit (no HH)
3. EMA50 trend filter (buy only above EMA50)
4. Entry at next bar OPEN after confirmation
5. Compounded equity (not summed %)
6. Spread/slippage model

Usage: cd /home/pi/master_ai && python3 _tools/fractal_backtest_v2.py
"""
import os
import json, sys, time, urllib.request
from datetime import datetime
from pathlib import Path

BRIDGE_URL = os.getenv("BRIDGE_URL", "http://192.168.111.214:8059")
PIVOT = 10
BROKER_FEE = 0.125   # % per side
SLIPPAGE = 0.05      # % per side (conservative KSE estimate)
TOTAL_COST = (BROKER_FEE + SLIPPAGE) * 2  # round trip

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parent
REPORT_PATH = PROJECT_DIR / "www" / "trading" / "fractal_report_v2.html"


def get_symbols():
    try:
        sys.path.insert(0, str(PROJECT_DIR))
        from stock_radar import WATCHLIST
        s = list(WATCHLIST) if hasattr(WATCHLIST, '__iter__') else []
        if s: print(f"  {len(s)} symbols from WATCHLIST"); return s
    except Exception as e: print(f"  WATCHLIST err: {e}")
    try:
        import sqlite3
        conn = sqlite3.connect(str(PROJECT_DIR / "data" / "life.db"))
        s = [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM stock_radar_daily ORDER BY symbol")]
        conn.close()
        if s: print(f"  {len(s)} symbols from DB"); return s
    except Exception as e: print(f"  DB err: {e}")
    return []


def fetch_bars(symbol):
    url = f"{BRIDGE_URL}/analysis?symbol={symbol}&interval=30"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read().decode()).get("bars", [])
    except: return None


def calc_ema(bars, period, key="close"):
    """Calculate EMA from bars list"""
    if not bars or len(bars) < period: return []
    ema = []
    # SMA for first value
    sma = sum(b[key] for b in bars[:period]) / period
    ema = [None] * (period - 1) + [sma]
    mult = 2 / (period + 1)
    for i in range(period, len(bars)):
        val = bars[i][key] * mult + ema[-1] * (1 - mult)
        ema.append(val)
    return ema


def detect_pivots(bars, p=10):
    n = len(bars); ph, pl = [], []
    for i in range(p, n - p):
        h = bars[i]["high"]
        if all(bars[j]["high"] < h for j in range(i-p,i)) and \
           all(bars[j]["high"] < h for j in range(i+1,i+p+1)):
            ph.append((i, h))
        lo = bars[i]["low"]
        if all(bars[j]["low"] > lo for j in range(i-p,i)) and \
           all(bars[j]["low"] > lo for j in range(i+1,i+p+1)):
            pl.append((i, lo))
    return ph, pl


def run_strategy(bars, ph, pl, ema50):
    """
    V2 Strategy:
    - Entry: HL only (higher low), close > EMA50
    - Exit: LH only (lower high)
    - Execution: next bar OPEN after confirmation
    - Equity: compounded
    """
    trades = []
    pos = None  # {entry_price, entry_bar, equity_before}
    equity = 1.0  # start with 1.0 = 100%

    # Classify pivot lows
    buy_signals = []
    for i in range(1, len(pl)):
        if pl[i][1] > pl[i-1][1]:  # HL only — higher low
            confirm_bar = pl[i][0] + PIVOT  # confirmation bar
            exec_bar = confirm_bar + 1      # next bar open
            buy_signals.append({"bar": exec_bar, "pivot_price": pl[i][1],
                               "confirm_bar": confirm_bar})

    # Classify pivot highs
    sell_signals = []
    for i in range(1, len(ph)):
        if ph[i][1] < ph[i-1][1]:  # LH only — lower high
            confirm_bar = ph[i][0] + PIVOT
            exec_bar = confirm_bar + 1
            sell_signals.append({"bar": exec_bar, "pivot_price": ph[i][1],
                                "confirm_bar": confirm_bar})

    # Merge and sort all signals by bar
    all_sigs = []
    for s in buy_signals: all_sigs.append({**s, "action": "buy"})
    for s in sell_signals: all_sigs.append({**s, "action": "sell"})
    all_sigs.sort(key=lambda x: x["bar"])

    for sig in all_sigs:
        eb = sig["bar"]
        if eb >= len(bars): continue

        if sig["action"] == "buy" and pos is None:
            # EMA50 filter: close must be above EMA50 at confirmation bar
            cb = sig["confirm_bar"]
            if cb >= len(ema50) or ema50[cb] is None: continue
            if bars[cb]["close"] <= ema50[cb]: continue

            entry_price = bars[eb]["open"]  # next bar OPEN
            if entry_price <= 0: continue
            pos = {"ep": entry_price, "eb": eb, "eq": equity}

        elif sig["action"] == "sell" and pos is not None:
            exit_price = bars[eb]["open"]  # next bar OPEN
            if exit_price <= 0: continue

            gross_pct = ((exit_price - pos["ep"]) / pos["ep"]) * 100
            net_pct = gross_pct - TOTAL_COST
            # Compound equity
            equity = equity * (1 + net_pct / 100)

            trades.append({
                "ep": pos["ep"], "xp": exit_price,
                "eb": pos["eb"], "xb": eb,
                "gp": round(gross_pct, 3),
                "np": round(net_pct, 3),
                "bh": eb - pos["eb"],
                "eq": round(equity, 4)
            })
            pos = None

    return trades, equity


def analyze(sym, trades, final_eq):
    if not trades:
        return {"s": sym, "nt": 0, "w": 0, "l": 0, "wr": 0,
                "tr": 0, "ar": 0, "best": 0, "worst": 0, "abh": 0, "eq": 1.0}
    w = len([t for t in trades if t["np"] > 0])
    tr = (final_eq - 1.0) * 100  # compounded return
    return {"s": sym, "nt": len(trades), "w": w, "l": len(trades)-w,
            "wr": round(w/len(trades)*100, 1),
            "tr": round(tr, 2),
            "ar": round(tr/len(trades), 2),
            "best": round(max(t["np"] for t in trades), 2),
            "worst": round(min(t["np"] for t in trades), 2),
            "abh": round(sum(t["bh"] for t in trades)/len(trades), 1),
            "eq": round(final_eq, 4)}


def main():
    t0 = time.time()
    print("=" * 60)
    print("  Fractal v3 Backtest V2 — CORRECTED")
    print(f"  Entry: HL only | Exit: LH only")
    print(f"  Filter: close > EMA50")
    print(f"  Execution: next bar OPEN")
    print(f"  Cost: {BROKER_FEE}% fee + {SLIPPAGE}% slippage per side")
    print(f"  Equity: compounded")
    print("=" * 60)

    # Bridge check
    print("\n[1] Bridge check...")
    try:
        with urllib.request.urlopen(f"{BRIDGE_URL}/analysis?symbol=NBK&interval=30", timeout=10) as r:
            if r.status == 200: print("  OK")
    except Exception as e:
        print(f"  FAIL: {e}"); sys.exit(1)

    # Symbols
    print("\n[2] Symbols...")
    symbols = get_symbols()
    if not symbols: print("  NONE"); sys.exit(1)

    # Backtest
    print(f"\n[3] Backtest {len(symbols)} stocks...")
    results = []
    v1_results = []  # for comparison
    for i, sym in enumerate(symbols):
        p = f"[{i+1}/{len(symbols)}]"
        bars = fetch_bars(sym)
        if not bars or len(bars) < PIVOT * 3 + 50:  # need enough for EMA50
            c = len(bars) if bars else 0
            print(f"  {p} {sym}: X ({c})")
            results.append(analyze(sym, [], 1.0))
            continue

        ph, pl = detect_pivots(bars, PIVOT)
        ema50 = calc_ema(bars, 50)

        if len(ph) < 2 or len(pl) < 2:
            print(f"  {p} {sym}: no pivots")
            results.append(analyze(sym, [], 1.0))
            continue

        trades, final_eq = run_strategy(bars, ph, pl, ema50)
        r = analyze(sym, trades, final_eq)
        results.append(r)

        ret = f"eq={r['eq']:.3f}" if trades else "-"
        wr = f"WR{r['wr']}%" if trades else ""
        tr = f"{r['tr']:+.1f}%" if trades else ""
        print(f"  {p} {sym}: {len(bars)}b {len(trades)}t {tr} {wr} {ret}")
        time.sleep(0.3)

    # Summary
    elapsed = time.time() - t0
    swt = [r for r in results if r["nt"] > 0]
    at = sum(r["nt"] for r in results)
    aw = sum(r["w"] for r in results)

    # Portfolio equity: average of all stock equities
    if swt:
        avg_eq = sum(r["eq"] for r in swt) / len(swt)
        portfolio_return = (avg_eq - 1.0) * 100
    else:
        avg_eq = 1.0
        portfolio_return = 0

    ps = len([r for r in results if r["tr"] > 0])
    ls = len([r for r in results if r["tr"] < 0 and r["nt"] > 0])

    print(f"\n{'='*60}")
    print(f"  RESULTS V2 — CORRECTED BACKTEST")
    print(f"  Strategy: HL entry + LH exit + EMA50 filter")
    print(f"  Stocks analyzed: {len(swt)}/{len(results)}")
    print(f"  Total trades: {at}")
    print(f"  Winners: {aw} | Losers: {at-aw}")
    print(f"  Win Rate: {round(aw/at*100,1) if at else 0}%")
    print(f"  Avg Equity: {avg_eq:.4f} ({portfolio_return:+.2f}%)")
    print(f"  Profitable stocks: {ps} | Losing: {ls}")
    print(f"  Time: {elapsed:.0f}s")
    print(f"{'='*60}")

    swt.sort(key=lambda x: x["tr"], reverse=True)
    print(f"\n  TOP 5:")
    for r in swt[:5]:
        print(f"    {r['s']:12s} eq={r['eq']:.3f} ({r['tr']:+.1f}%) | {r['nt']}t WR{r['wr']}%")
    print(f"\n  BOTTOM 5:")
    for r in list(reversed(swt))[:5]:
        print(f"    {r['s']:12s} eq={r['eq']:.3f} ({r['tr']:+.1f}%) | {r['nt']}t WR{r['wr']}%")

    # Comparison summary
    print(f"\n  V1 vs V2 COMPARISON:")
    print(f"  V1: ALL pivots, no filter, close price, summed %")
    print(f"  V2: HL only, EMA50 filter, next bar open, compounded")
    print(f"  V1 trades: ~352 | V2 trades: {at}")
    print(f"  V1 win rate: 33.5% | V2 win rate: {round(aw/at*100,1) if at else 0}%")
    print(f"  V1 return: -353% (summed) | V2 return: {portfolio_return:+.2f}% (compounded avg)")

    # No HTML report — just console output for now
    print(f"\n  [No HTML report — results shown here for review]")


if __name__ == "__main__":
    main()
