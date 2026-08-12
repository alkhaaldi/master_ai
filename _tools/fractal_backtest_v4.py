#!/usr/bin/env python3
"""
Fractal v3 Backtest V4 — ChatGPT Method
=========================================
Based on ChatGPT's analysis, this version tests properly:

1. Daily (1D) + Pivot=10 across ALL 128 radar stocks (portfolio-level)
2. 30m + Pivot=3,4,5 (smaller periods for intraday)
3. Multiple exit strategies: LH-only, any-pivot-high, ATR trailing stop
4. Compounded equity per stock, then portfolio average
5. No EMA filter initially (raw signal count first)
6. Goal: 100+ trades minimum for statistical validity

Data source: Bridge API (300 bars per request)
Execution: next bar OPEN after pivot confirmation
Cost: 0.125% fee + 0.05% slippage per side

Usage:
    cd /home/pi/master_ai
    python3 _tools/fractal_backtest_v4.py

Output: Console results + www/trading/fractal_report_v4.html
"""
import os
import json, sys, time, urllib.request
from datetime import datetime
from pathlib import Path

BRIDGE_URL = os.getenv("BRIDGE_URL", "http://192.168.111.214:8059")
FEE = 0.125
SLIP = 0.05
COST = (FEE + SLIP) * 2

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parent
REPORT_PATH = PROJECT_DIR / "www" / "trading" / "fractal_report_v4.html"


def get_symbols():
    try:
        sys.path.insert(0, str(PROJECT_DIR))
        from stock_radar import WATCHLIST
        s = list(WATCHLIST) if hasattr(WATCHLIST, '__iter__') else []
        if s: return s
    except: pass
    try:
        import sqlite3
        conn = sqlite3.connect(str(PROJECT_DIR / "data" / "life.db"))
        s = [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM stock_radar_daily ORDER BY symbol")]
        conn.close()
        if s: return s
    except: pass
    return []


def fetch_bars(symbol, interval="1D"):
    url = f"{BRIDGE_URL}/analysis?symbol={symbol}&interval={interval}"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read().decode())
        return data.get("bars", [])
    except:
        return None


def calc_ema(bars, period):
    if len(bars) < period: return [None] * len(bars)
    sma = sum(b["close"] for b in bars[:period]) / period
    ema = [None] * (period - 1) + [sma]
    m = 2 / (period + 1)
    for i in range(period, len(bars)):
        ema.append(bars[i]["close"] * m + ema[-1] * (1 - m))
    return ema


def calc_atr(bars, period=14):
    """Calculate ATR for trailing stop"""
    if len(bars) < period + 1: return [None] * len(bars)
    trs = [None]
    for i in range(1, len(bars)):
        tr = max(bars[i]["high"] - bars[i]["low"],
                 abs(bars[i]["high"] - bars[i-1]["close"]),
                 abs(bars[i]["low"] - bars[i-1]["close"]))
        trs.append(tr)
    atr = [None] * period
    atr_val = sum(t for t in trs[1:period+1]) / period
    atr.append(atr_val)
    for i in range(period + 1, len(bars)):
        atr_val = (atr_val * (period - 1) + trs[i]) / period
        atr.append(atr_val)
    return atr


def detect_pivots(bars, p):
    n = len(bars); ph, pl = [], []
    for i in range(p, n - p):
        h = bars[i]["high"]
        if all(bars[j]["high"] < h for j in range(i-p, i)) and \
           all(bars[j]["high"] < h for j in range(i+1, i+p+1)):
            ph.append((i, h))
        lo = bars[i]["low"]
        if all(bars[j]["low"] > lo for j in range(i-p, i)) and \
           all(bars[j]["low"] > lo for j in range(i+1, i+p+1)):
            pl.append((i, lo))
    return ph, pl


def run_test(bars, pivot_period, exit_mode="lh_only"):
    """
    Run a single backtest configuration.
    
    Entry: HL only (higher low confirmed)
    Exit modes:
      - "lh_only": exit only on confirmed LH
      - "any_high": exit on any confirmed pivot high (HH or LH)
      - "atr_stop": exit on LH or ATR trailing stop (2x ATR below highest close)
    
    Execution: next bar OPEN after confirmation
    """
    ph, pl = detect_pivots(bars, pivot_period)
    atr = calc_atr(bars) if exit_mode == "atr_stop" else []
    
    if len(ph) < 2 or len(pl) < 2:
        return {"trades": [], "equity": 1.0, "hl_count": 0, "ll_count": 0,
                "hh_count": 0, "lh_count": 0, "pivot_highs": len(ph), "pivot_lows": len(pl)}
    
    # Classify
    hl_count = sum(1 for i in range(1, len(pl)) if pl[i][1] > pl[i-1][1])
    ll_count = sum(1 for i in range(1, len(pl)) if pl[i][1] <= pl[i-1][1])
    hh_count = sum(1 for i in range(1, len(ph)) if ph[i][1] > ph[i-1][1])
    lh_count = sum(1 for i in range(1, len(ph)) if ph[i][1] <= ph[i-1][1])

    # Build entry signals: HL only
    buy_sigs = []
    for i in range(1, len(pl)):
        if pl[i][1] > pl[i-1][1]:  # Higher Low
            exec_bar = pl[i][0] + pivot_period + 1
            buy_sigs.append({"bar": exec_bar, "pivot_low": pl[i][1]})
    
    # Build exit signals based on mode
    sell_sigs = []
    for i in range(1, len(ph)):
        is_lh = ph[i][1] < ph[i-1][1]
        is_hh = ph[i][1] > ph[i-1][1]
        exec_bar = ph[i][0] + pivot_period + 1
        if exit_mode == "lh_only" and is_lh:
            sell_sigs.append({"bar": exec_bar, "type": "LH"})
        elif exit_mode in ("any_high", "atr_stop"):
            sell_sigs.append({"bar": exec_bar, "type": "LH" if is_lh else "HH"})
    
    # Merge and execute
    all_sigs = [{"bar": s["bar"], "a": "buy", "stop": s["pivot_low"]} for s in buy_sigs]
    all_sigs += [{"bar": s["bar"], "a": "sell"} for s in sell_sigs]
    all_sigs.sort(key=lambda x: x["bar"])
    
    trades = []
    pos = None
    equity = 1.0
    highest_close = 0
    
    for sig in all_sigs:
        eb = sig["bar"]
        if eb >= len(bars): continue
        
        if sig["a"] == "buy" and pos is None:
            ep = bars[eb]["open"]
            if ep <= 0: continue
            pos = {"ep": ep, "eb": eb, "stop": sig.get("stop", 0)}
            highest_close = ep

        elif sig["a"] == "sell" and pos is not None:
            xp = bars[eb]["open"]
            if xp <= 0: continue
            gp = ((xp - pos["ep"]) / pos["ep"]) * 100
            np_ = gp - COST
            equity *= (1 + np_ / 100)
            trades.append({"np": round(np_, 2), "bh": eb - pos["eb"]})
            pos = None
        
        # ATR trailing stop check (between signals)
        if exit_mode == "atr_stop" and pos is not None:
            for bi in range(pos["eb"] + 1, min(eb, len(bars))):
                if bars[bi]["close"] > highest_close:
                    highest_close = bars[bi]["close"]
                if bi < len(atr) and atr[bi] is not None:
                    trail_stop = highest_close - 2 * atr[bi]
                    if bars[bi]["low"] <= trail_stop:
                        xp = trail_stop
                        gp = ((xp - pos["ep"]) / pos["ep"]) * 100
                        np_ = gp - COST
                        equity *= (1 + np_ / 100)
                        trades.append({"np": round(np_, 2), "bh": bi - pos["eb"]})
                        pos = None
                        break
    
    return {"trades": trades, "equity": round(equity, 4),
            "hl_count": hl_count, "ll_count": ll_count,
            "hh_count": hh_count, "lh_count": lh_count,
            "pivot_highs": len(ph), "pivot_lows": len(pl)}


def run_full_test(symbols, interval, pivot_period, exit_mode, label):
    """Run test across all symbols for one configuration"""
    results = []
    total_hl = 0
    total_ll = 0
    
    for i, sym in enumerate(symbols):
        bars = fetch_bars(sym, interval)
        if not bars or len(bars) < pivot_period * 3 + 50:
            continue
        
        r = run_test(bars, pivot_period, exit_mode)
        total_hl += r["hl_count"]
        total_ll += r["ll_count"]
        
        if r["trades"]:
            w = len([t for t in r["trades"] if t["np"] > 0])
            results.append({
                "sym": sym,
                "nt": len(r["trades"]),
                "w": w,
                "wr": round(w / len(r["trades"]) * 100, 1),
                "eq": r["equity"],
                "tr": round((r["equity"] - 1) * 100, 2),
            })
        
        # Progress every 20 stocks
        if (i + 1) % 20 == 0:
            print(f"    [{i+1}/{len(symbols)}] processed...")
        
        time.sleep(0.2)
    
    # Aggregate
    if not results:
        return {"label": label, "stocks": 0, "trades": 0, "wr": 0,
                "avg_eq": 1.0, "portfolio_ret": 0, "profitable": 0,
                "losing": 0, "total_hl": total_hl, "total_ll": total_ll,
                "results": []}
    
    at = sum(r["nt"] for r in results)
    aw = sum(r["w"] for r in results)
    avg_eq = sum(r["eq"] for r in results) / len(results)
    ps = len([r for r in results if r["tr"] > 0])
    ls = len([r for r in results if r["tr"] < 0])
    
    return {
        "label": label,
        "stocks": len(results),
        "trades": at,
        "wr": round(aw / at * 100, 1) if at else 0,
        "avg_eq": round(avg_eq, 4),
        "portfolio_ret": round((avg_eq - 1) * 100, 2),
        "profitable": ps,
        "losing": ls,
        "total_hl": total_hl,
        "total_ll": total_ll,
        "results": sorted(results, key=lambda x: x["tr"], reverse=True),
    }


def print_summary(s):
    print(f"\n  {'-'*60}")
    print(f"  {s['label']}")
    print(f"  {'-'*60}")
    print(f"  Stocks with trades: {s['stocks']} | HL signals: {s['total_hl']} | LL signals: {s['total_ll']}")
    print(f"  Total trades: {s['trades']} | Winners: {sum(r['w'] for r in s['results'])}")
    print(f"  Win Rate: {s['wr']}%")
    print(f"  Avg Equity: {s['avg_eq']:.4f} ({s['portfolio_ret']:+.2f}%)")
    print(f"  Profitable stocks: {s['profitable']} | Losing: {s['losing']}")
    
    if s["results"]:
        print(f"\n  Top 5:")
        for r in s["results"][:5]:
            print(f"    {r['sym']:12s} eq={r['eq']:.3f} ({r['tr']:+.1f}%) | {r['nt']}t WR{r['wr']}%")
        print(f"\n  Bottom 5:")
        for r in s["results"][-5:]:
            print(f"    {r['sym']:12s} eq={r['eq']:.3f} ({r['tr']:+.1f}%) | {r['nt']}t WR{r['wr']}%")


def main():
    t0 = time.time()
    print("=" * 70)
    print("  FRACTAL v3 BACKTEST V4 — ChatGPT Method")
    print("  Comprehensive test: multiple pivots, exits, timeframes")
    print("=" * 70)
    
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
    print(f"  {len(symbols)} stocks")
    
    all_summaries = []
    
    # ═══════════════════════════════════════════════
    # TEST 1: Daily (1D) + Pivot=10 — the strong test
    # ═══════════════════════════════════════════════
    print(f"\n{'='*70}")
    print(f"  TEST 1: Daily (1D) + Pivot=10 — Portfolio Level")
    print(f"{'='*70}")
    
    for exit_mode, exit_label in [("lh_only", "LH exit"), ("any_high", "Any high exit"), ("atr_stop", "ATR trailing stop")]:
        label = f"1D P=10 | {exit_label}"
        print(f"\n  Running: {label}...")
        s = run_full_test(symbols, "1D", 10, exit_mode, label)
        all_summaries.append(s)
        print_summary(s)

    # ═══════════════════════════════════════════════
    # TEST 2: 30m + Pivot=3,4,5 — intraday test
    # ═══════════════════════════════════════════════
    print(f"\n{'='*70}")
    print(f"  TEST 2: 30m + Pivot=3,4,5 — Intraday")
    print(f"{'='*70}")
    
    for pivot in [3, 4, 5]:
        for exit_mode, exit_label in [("lh_only", "LH exit"), ("any_high", "Any high exit")]:
            label = f"30m P={pivot} | {exit_label}"
            print(f"\n  Running: {label}...")
            s = run_full_test(symbols, "30", pivot, exit_mode, label)
            all_summaries.append(s)
            print_summary(s)
    
    # ═══════════════════════════════════════════════
    # FINAL COMPARISON TABLE
    # ═══════════════════════════════════════════════
    elapsed = time.time() - t0
    print(f"\n\n{'='*70}")
    print(f"  FINAL COMPARISON — ALL CONFIGURATIONS")
    print(f"{'='*70}")
    print(f"  {'Config':<30s} {'Stocks':>6s} {'Trades':>7s} {'WR%':>6s} {'Return':>8s} {'Win':>4s} {'Loss':>5s}")
    print(f"  {'-'*30} {'-'*6} {'-'*7} {'-'*6} {'-'*8} {'-'*4} {'-'*5}")
    
    for s in all_summaries:
        ret_str = f"{s['portfolio_ret']:+.1f}%"
        print(f"  {s['label']:<30s} {s['stocks']:>6d} {s['trades']:>7d} {s['wr']:>5.1f}% {ret_str:>8s} {s['profitable']:>4d} {s['losing']:>5d}")
    
    print(f"\n  Total time: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"  Statistical threshold: need 100+ trades for valid conclusions")
    
    # Mark configs with enough trades
    valid = [s for s in all_summaries if s["trades"] >= 100]
    if valid:
        print(f"\n  STATISTICALLY VALID configs (100+ trades):")
        for s in sorted(valid, key=lambda x: x["portfolio_ret"], reverse=True):
            print(f"    {s['label']:<30s} {s['trades']}t WR:{s['wr']}% Return:{s['portfolio_ret']:+.1f}%")
    else:
        print(f"\n  WARNING: No config reached 100 trades. Results are indicative only.")
    
    print(f"\n{'='*70}")
    print(f"  DONE")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
