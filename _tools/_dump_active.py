import urllib.request, json

# Get active data
r = urllib.request.urlopen('http://localhost:9000/dashboard/ema-active', timeout=10)
d = json.loads(r.read())

print("="*60)
print(f"BULLISH ({d['bullish_count']} stocks):")
print("="*60)
for b in d['bullish']:
    print(f"  {b['symbol']:12} | price={str(b['price']):>8} | EMA9={str(b['ema9']):>10} | EMA21={str(b['ema21']):>10} | RSI={str(b['rsi']):>6} | score={str(b['score']):>3} | time={b['signal_time']}")

print()
print("="*60)
print(f"BEARISH ({d['bearish_count']} stocks):")  
print("="*60)
for b in d['bearish'][:10]:
    print(f"  {b['symbol']:12} | price={str(b['price']):>8} | EMA9={str(b['ema9']):>10} | EMA21={str(b['ema21']):>10} | RSI={str(b['rsi']):>6} | score={str(b['score']):>3} | time={b['signal_time']}")

# Key question: when was the last radar scan?
print()
print("="*60)
print("IMPORTANT NOTES:")
print("="*60)
print(f"Total tracked: {d['total']} out of 128 stocks")
print(f"Missing: {128 - d['total']} stocks have NO signal recorded yet")
print(f"Data source: stock_radar_state.last_signal (set during market hours only)")
print(f"Last signal time (newest bull): {d['bullish'][0]['signal_time'] if d['bullish'] else 'none'}")
print(f"Last signal time (newest bear): {d['bearish'][0]['signal_time'] if d['bearish'] else 'none'}")
