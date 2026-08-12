#!/usr/bin/env python3
"""
Fractal v3 Backtest V3 — Focused Test
======================================
يختبر 3 أسهم محددة: EQUIPMENT, IFA, CLEANING
يقارن 4 استراتيجيات:
  A) V1 الأصلية: كل pivots بدون فلتر
  B) HL فقط (بدون EMA filter)
  C) HL + EMA50 filter
  D) HL + EMA50 + stop loss تحت آخر pivot low

كل الاستراتيجيات:
- Pivot period = 10
- Execution: next bar OPEN after confirmation
- Compounded equity
- Fee 0.125% + slippage 0.05% per side

Usage: cd /home/pi/master_ai && python3 _tools/fractal_backtest_v3.py
"""
import os
import json, sys, time, urllib.request
from datetime import datetime
from pathlib import Path

BRIDGE_URL = os.getenv("BRIDGE_URL", "http://192.168.111.214:8059")
PIVOT = 10
FEE = 0.125
SLIP = 0.05
COST = (FEE + SLIP) * 2  # round trip

# الأسهم المطلوبة
TARGET_STOCKS = ["EQUIPMENT", "IFA", "CLEANING"]

def fetch_bars(symbol):
    url = f"{BRIDGE_URL}/analysis?symbol={symbol}&interval=30"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read().decode()).get("bars", [])
    except: return None


def calc_ema(bars, period):
    if len(bars) < period: return []
    sma = sum(b["close"] for b in bars[:period]) / period
    ema = [None] * (period - 1) + [sma]
    m = 2 / (period + 1)
    for i in range(period, len(bars)):
        ema.append(bars[i]["close"] * m + ema[-1] * (1 - m))
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


def run_strategy_A(bars, ph, pl, ema50):
    """V1: ALL pivots, no filter, next bar open, compounded"""
    sigs = []
    for i in range(1, len(pl)):
        t = "HL" if pl[i][1] > pl[i-1][1] else "LL"
        eb = pl[i][0] + PIVOT + 1
        sigs.append({"bar": eb, "t": t, "a": "buy"})
    for i in range(1, len(ph)):
        t = "HH" if ph[i][1] > ph[i-1][1] else "LH"
        eb = ph[i][0] + PIVOT + 1
        sigs.append({"bar": eb, "t": t, "a": "sell"})
    sigs.sort(key=lambda x: x["bar"])
    return _execute(sigs, bars, "A: All pivots")


def run_strategy_B(bars, ph, pl, ema50):
    """HL only entry, LH only exit, no EMA filter"""
    sigs = []
    for i in range(1, len(pl)):
        if pl[i][1] > pl[i-1][1]:  # HL only
            sigs.append({"bar": pl[i][0]+PIVOT+1, "t": "HL", "a": "buy"})
    for i in range(1, len(ph)):
        if ph[i][1] < ph[i-1][1]:  # LH only
            sigs.append({"bar": ph[i][0]+PIVOT+1, "t": "LH", "a": "sell"})
    sigs.sort(key=lambda x: x["bar"])
    return _execute(sigs, bars, "B: HL/LH only")


def run_strategy_C(bars, ph, pl, ema50):
    """HL + EMA50 filter entry, LH exit"""
    sigs = []
    for i in range(1, len(pl)):
        if pl[i][1] > pl[i-1][1]:  # HL only
            cb = pl[i][0] + PIVOT
            if cb < len(ema50) and ema50[cb] is not None:
                if bars[cb]["close"] > ema50[cb]:  # above EMA50
                    sigs.append({"bar": cb+1, "t": "HL", "a": "buy"})
    for i in range(1, len(ph)):
        if ph[i][1] < ph[i-1][1]:  # LH only
            sigs.append({"bar": ph[i][0]+PIVOT+1, "t": "LH", "a": "sell"})
    sigs.sort(key=lambda x: x["bar"])
    return _execute(sigs, bars, "C: HL+EMA50")


def run_strategy_D(bars, ph, pl, ema50):
    """HL + EMA50 entry, LH exit OR stop loss below last pivot low"""
    buy_sigs = []
    for i in range(1, len(pl)):
        if pl[i][1] > pl[i-1][1]:
            cb = pl[i][0] + PIVOT
            if cb < len(ema50) and ema50[cb] is not None:
                if bars[cb]["close"] > ema50[cb]:
                    stop = pl[i][1]  # stop at pivot low price
                    buy_sigs.append({"bar": cb+1, "t": "HL", "a": "buy", "stop": stop})
    sell_sigs = []
    for i in range(1, len(ph)):
        if ph[i][1] < ph[i-1][1]:
            sell_sigs.append({"bar": ph[i][0]+PIVOT+1, "t": "LH", "a": "sell"})

    # Execute with stop loss check
    trades = []
    pos = None
    equity = 1.0
    all_sigs = buy_sigs + sell_sigs
    all_sigs.sort(key=lambda x: x["bar"])

    for sig in all_sigs:
        eb = sig["bar"]
        if eb >= len(bars): continue
        if sig["a"] == "buy" and pos is None:
            ep = bars[eb]["open"]
            if ep <= 0: continue
            pos = {"ep": ep, "eb": eb, "stop": sig.get("stop", 0)}
        elif sig["a"] == "sell" and pos is not None:
            xp = bars[eb]["open"]
            if xp <= 0: continue
            gp = ((xp - pos["ep"]) / pos["ep"]) * 100
            np_ = gp - COST
            equity *= (1 + np_ / 100)
            trades.append({"ep":pos["ep"],"xp":xp,"np":round(np_,3),"bh":eb-pos["eb"],"exit":"LH"})
            pos = None

    # Check stop losses for open position
    if pos is not None:
        for bi in range(pos["eb"]+1, len(bars)):
            if bars[bi]["low"] <= pos["stop"]:
                xp = pos["stop"]
                gp = ((xp - pos["ep"]) / pos["ep"]) * 100
                np_ = gp - COST
                equity *= (1 + np_ / 100)
                trades.append({"ep":pos["ep"],"xp":xp,"np":round(np_,3),"bh":bi-pos["eb"],"exit":"STOP"})
                pos = None
                break

    return {"name": "D: HL+EMA50+Stop", "trades": trades, "equity": round(equity, 4)}


def _execute(sigs, bars, name):
    """Shared execution logic for strategies A, B, C"""
    trades = []
    pos = None
    equity = 1.0
    for sig in sigs:
        eb = sig["bar"]
        if eb >= len(bars): continue
        if sig["a"] == "buy" and pos is None:
            ep = bars[eb]["open"]
            if ep <= 0: continue
            pos = {"ep": ep, "eb": eb}
        elif sig["a"] == "sell" and pos is not None:
            xp = bars[eb]["open"]
            if xp <= 0: continue
            gp = ((xp - pos["ep"]) / pos["ep"]) * 100
            np_ = gp - COST
            equity *= (1 + np_ / 100)
            trades.append({"ep":pos["ep"],"xp":xp,"np":round(np_,3),"bh":eb-pos["eb"]})
            pos = None
    return {"name": name, "trades": trades, "equity": round(equity, 4)}


def print_result(sym, res):
    trades = res["trades"]
    if not trades:
        print(f"    {res['name']:25s} | 0 trades")
        return
    w = len([t for t in trades if t["np"] > 0])
    l = len(trades) - w
    wr = round(w/len(trades)*100, 1)
    ret = (res["equity"] - 1) * 100
    print(f"    {res['name']:25s} | {len(trades)}t W:{w} L:{l} WR:{wr:5.1f}% | eq={res['equity']:.4f} ({ret:+.2f}%)")
    for t in trades:
        exit_type = t.get("exit", "signal")
        print(f"      entry@{t['ep']:.3f} -> exit@{t['xp']:.3f} = {t['np']:+.3f}% ({t['bh']}bars) [{exit_type}]")


def main():
    print("=" * 70)
    print("  Fractal v3 Backtest V3 — Focused Comparison")
    print(f"  Stocks: {', '.join(TARGET_STOCKS)}")
    print(f"  Pivot={PIVOT} | 30m | Fee={FEE}%+Slip={SLIP}% per side")
    print(f"  4 strategies: A(all) B(HL/LH) C(HL+EMA50) D(HL+EMA50+Stop)")
    print("=" * 70)

    # Bridge check
    print("\n[1] Bridge check...")
    try:
        with urllib.request.urlopen(f"{BRIDGE_URL}/analysis?symbol=NBK&interval=30", timeout=10) as r:
            if r.status == 200: print("  OK")
    except Exception as e:
        print(f"  FAIL: {e}"); sys.exit(1)

    # Test each stock
    print(f"\n[2] Running backtest...")
    for sym in TARGET_STOCKS:
        print(f"\n{'─'*70}")
        print(f"  {sym}")
        print(f"{'─'*70}")

        bars = fetch_bars(sym)
        if not bars:
            print(f"  ERROR: No data from Bridge")
            continue

        print(f"  Bars: {len(bars)} | First: {bars[0]['close']} | Last: {bars[-1]['close']}")

        if len(bars) < PIVOT * 3 + 50:
            print(f"  ERROR: Not enough bars ({len(bars)})")
            continue

        ph, pl = detect_pivots(bars, PIVOT)
        ema50 = calc_ema(bars, 50)

        print(f"  Pivots: {len(ph)} highs, {len(pl)} lows")
        print(f"  EMA50 available from bar {next((i for i,v in enumerate(ema50) if v is not None), 'N/A')}")

        if len(ph) < 2 or len(pl) < 2:
            print(f"  ERROR: Not enough pivots")
            continue

        # Classify all pivots for info
        hl = sum(1 for i in range(1,len(pl)) if pl[i][1] > pl[i-1][1])
        ll = sum(1 for i in range(1,len(pl)) if pl[i][1] <= pl[i-1][1])
        hh = sum(1 for i in range(1,len(ph)) if ph[i][1] > ph[i-1][1])
        lh = sum(1 for i in range(1,len(ph)) if ph[i][1] <= ph[i-1][1])
        print(f"  Classification: HL={hl} LL={ll} HH={hh} LH={lh}")

        # Run all 4 strategies
        print(f"\n  Results:")
        rA = run_strategy_A(bars, ph, pl, ema50)
        print_result(sym, rA)
        rB = run_strategy_B(bars, ph, pl, ema50)
        print_result(sym, rB)
        rC = run_strategy_C(bars, ph, pl, ema50)
        print_result(sym, rC)
        rD = run_strategy_D(bars, ph, pl, ema50)
        print_result(sym, rD)

    print(f"\n{'='*70}")
    print(f"  DONE")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
