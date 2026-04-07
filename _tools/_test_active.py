import urllib.request, json, time

for attempt in range(12):
    time.sleep(5)
    try:
        r = urllib.request.urlopen('http://localhost:9000/health', timeout=5)
        d = json.loads(r.read())
        print(f"Attempt {attempt+1}: HEALTH OK (uptime={d.get('uptime_seconds')}s)")
        break
    except Exception as e:
        print(f"Attempt {attempt+1}: waiting... ({e})")
else:
    print("FAILED: server never came up")
    exit(1)

# Test ema-active
try:
    r = urllib.request.urlopen('http://localhost:9000/dashboard/ema-active', timeout=10)
    d = json.loads(r.read())
    print(f"\nEMA-ACTIVE OK: bull={d['bullish_count']}, bear={d['bearish_count']}, total={d['total']}")
    for b in d['bullish'][:5]:
        print(f"  BULL: {b['symbol']:12} price={b['price']} score={b['score']} verdict={b.get('verdict','?')} time={b['signal_time']}")
    for b in d['bearish'][:5]:
        print(f"  BEAR: {b['symbol']:12} price={b['price']} score={b['score']} time={b['signal_time']}")
except Exception as e:
    print(f"EMA-ACTIVE FAIL: {e}")

# Test ema-crosses
try:
    r = urllib.request.urlopen('http://localhost:9000/dashboard/ema-crosses?hours=240', timeout=10)
    d = json.loads(r.read())
    print(f"\nEMA-CROSSES OK: total={d['total']}, bull={d['bullish_count']}, bear={d['bearish_count']}")
except Exception as e:
    print(f"EMA-CROSSES FAIL: {e}")
