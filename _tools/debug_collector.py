#!/usr/bin/env python3
"""Debug: test bridge connection from RPi for kse_data_collector"""
import sys, os
sys.path.insert(0, '/home/pi/master_ai')

from kse_data_collector import _fetch_bridge_bars, BRIDGE_URL, _get_watchlist_symbols
print(f"BRIDGE_URL = {BRIDGE_URL}")

symbols = _get_watchlist_symbols()[:3]
print(f"Testing with {symbols}")

result = _fetch_bridge_bars(symbols)
print(f"Result: {len(result)} symbols")
for sym, data in result.items():
    print(f"  {sym}: close={data.get('close')}, vol={data.get('volume')}")

if not result:
    # Manual test
    import requests
    url = f"{BRIDGE_URL}/multi-analysis"
    params = {"symbols": ",".join(symbols), "exchange": "KSE", "interval": "1D", "bars": 5}
    print(f"\nManual test: GET {url}")
    print(f"Params: {params}")
    try:
        r = requests.get(url, params=params, timeout=30)
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Results count: {len(data.get('results', []))}")
        for item in data.get('results', []):
            print(f"  Symbol: {item.get('symbol')}")
            print(f"  Has quote: {'quote' in item}")
            print(f"  Has ohlcv: {'ohlcv' in item}")
            q = item.get('quote', {})
            print(f"  quote.open: {q.get('open')}")
    except Exception as e:
        print(f"Error: {e}")
