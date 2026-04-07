#!/usr/bin/env python3
"""Quick 5-stock test of Fractal Backtest"""
import json, sys, time, urllib.request
from pathlib import Path

BRIDGE_URL = "http://192.168.111.158:8059"
PIVOT = 10
FEE = 0.125

def fetch(sym):
    try:
        with urllib.request.urlopen(f"{BRIDGE_URL}/analysis?symbol={sym}&interval=30", timeout=15) as r:
            return json.loads(r.read().decode()).get("bars", [])
    except: return None

def pivots(bars, p=10):
    n = len(bars); ph, pl = [], []
    for i in range(p, n-p):
        h = bars[i]["high"]
        if all(bars[j]["high"] < h for j in range(i-p,i)) and all(bars[j]["high"] < h for j in range(i+1,i+p+1)):
            ph.append((i,h))
        lo = bars[i]["low"]
        if all(bars[j]["low"] > lo for j in range(i-p,i)) and all(bars[j]["low"] > lo for j in range(i+1,i+p+1)):
            pl.append((i,lo))
    return ph, pl

def classify(ph, pl):
    s = []
    for i in range(1, len(pl)):
        t = "HL" if pl[i][1] > pl[i-1][1] else "LL"
        s.append({"b": pl[i][0], "t": t, "a": "buy"})
    for i in range(1, len(ph)):
        t = "HH" if ph[i][1] > ph[i-1][1] else "LH"
        s.append({"b": ph[i][0], "t": t, "a": "sell"})
    s.sort(key=lambda x: x["b"])
    return s

def sim(sigs, bars):
    trades, pos = [], None
    for s in sigs:
        if s["a"]=="buy" and pos is None:
            eb = min(s["b"]+PIVOT, len(bars)-1)
            pos = {"ep": bars[eb]["close"], "eb": eb, "et": s["t"]}
        elif s["a"]=="sell" and pos is not None:
            xb = min(s["b"]+PIVOT, len(bars)-1)
            xp = bars[xb]["close"]
            gp = ((xp-pos["ep"])/pos["ep"])*100
            np_ = gp-(FEE*2)
            trades.append({"ep":pos["ep"],"xp":xp,"et":pos["et"],"xt":s["t"],"np":round(np_,3),"bh":xb-pos["eb"]})
            pos = None
    return trades

# Test 5 stocks
test_syms = ["NBK","ZAIN","KFH","CLEANING","HUMANSOFT"]
print(f"Testing {len(test_syms)} stocks...")
for sym in test_syms:
    bars = fetch(sym)
    if not bars:
        print(f"  {sym}: NO DATA"); continue
    ph, pl = pivots(bars, PIVOT)
    sigs = classify(ph, pl)
    trades = sim(sigs, bars)
    if trades:
        w = len([t for t in trades if t["np"]>0])
        tr = sum(t["np"] for t in trades)
        print(f"  {sym}: {len(bars)}b | {len(trades)}t | W:{w} L:{len(trades)-w} | WR:{round(w/len(trades)*100,1)}% | Total:{tr:+.2f}%")
        for t in trades:
            print(f"    {t['et']}@{t['ep']:.3f} -> {t['xt']}@{t['xp']:.3f} = {t['np']:+.3f}% ({t['bh']}bars)")
    else:
        print(f"  {sym}: {len(bars)}b | pivots H:{len(ph)} L:{len(pl)} | sigs:{len(sigs)} | NO TRADES")
