#!/usr/bin/env python3
"""Quick test: check Bridge /analysis response format"""
import urllib.request, json, sys
url = "http://192.168.111.158:8059/analysis?symbol=NBK&interval=30"
try:
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    print(f"Keys: {list(data.keys())}")
    bars = data.get("bars", [])
    print(f"Bars count: {len(bars)}")
    if bars:
        print(f"Bar[0] keys: {list(bars[0].keys())}")
        print(f"Bar[0]: {bars[0]}")
        print(f"Bar[-1]: {bars[-1]}")
except Exception as e:
    print(f"Error: {e}")
