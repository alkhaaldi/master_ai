#!/usr/bin/env python3
"""Fetch 1D bars for 3 stocks and save to JSON"""
import os
import json, urllib.request

BRIDGE = os.getenv("BRIDGE_URL", "http://192.168.111.214:8059")
STOCKS = ["EQUIPMENT", "IFA", "CLEANING"]
out = {}

for sym in STOCKS:
    url = f"{BRIDGE}/analysis?symbol={sym}&interval=1D"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read().decode())
        bars = data.get("bars", [])
        out[sym] = {
            "count": len(bars),
            "bars": [{"o":b["open"],"h":b["high"],"l":b["low"],"c":b["close"],"v":b["volume"],"t":b.get("time",0)} for b in bars]
        }
        print(f"{sym}: {len(bars)} daily bars")
    except Exception as e:
        print(f"{sym}: ERROR {e}")

with open("/tmp/daily_bars.json", "w") as f:
    json.dump(out, f)
print(f"Saved to /tmp/daily_bars.json")
