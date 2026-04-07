import urllib.request, json
r = urllib.request.urlopen('http://localhost:9000/dashboard/ema-live', timeout=30)
d = json.loads(r.read())
print("bridge_online:", d.get("bridge_online"))
print("total_checked:", d.get("total_checked"))
print("bullish:", d.get("bullish_count"))
print("bearish:", d.get("bearish_count"))
print("touching:", d.get("touching_count"))
print("stale:", d.get("stale", False))
print()
print("--- BULLISH ---")
for b in d.get("bullish", []):
    print(f"  {b['symbol']:12} price={b['price']} ema9={b['ema9']} ema21={b['ema21']} gap={b['gap_pct']}%")
print()
print("--- BEARISH ---")
for b in d.get("bearish", [])[:5]:
    print(f"  {b['symbol']:12} price={b['price']} ema9={b['ema9']} ema21={b['ema21']} gap={b['gap_pct']}%")
print(f"  ... and {len(d.get('bearish',[]))-5} more" if len(d.get('bearish',[])) > 5 else "")
