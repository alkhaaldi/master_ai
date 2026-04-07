import urllib.request, json

# Get live signal data for ALDEERA
r = urllib.request.urlopen("http://localhost:9000/dashboard/radar", timeout=15)
d = json.loads(r.read().decode())

# Check structure
ctx = d.get("radar_daily_context", [])
print(f"Type: {type(ctx).__name__}")
if isinstance(ctx, list):
    for item in ctx:
        if isinstance(item, dict) and item.get("symbol") == "ALDEERA":
            print("=== ALDEERA ===")
            for k, v in sorted(item.items()):
                print(f"  {k}: {v}")
            break
    else:
        print("ALDEERA not in daily context")
        if ctx:
            print(f"First item keys: {list(ctx[0].keys()) if isinstance(ctx[0], dict) else ctx[0]}")
elif isinstance(ctx, dict):
    a = ctx.get("ALDEERA", {})
    print("=== ALDEERA ===")
    for k, v in sorted(a.items()):
        print(f"  {k}: {v}")

# Also check 30m signals
try:
    r2 = urllib.request.urlopen("http://localhost:9000/dashboard/signals-30m", timeout=15)
    d2 = json.loads(r2.read().decode())
    sigs = d2.get("signals", [])
    for s in sigs:
        if isinstance(s, dict) and s.get("symbol") == "ALDEERA":
            print("\n=== ALDEERA 30m live ===")
            for k, v in sorted(s.items()):
                print(f"  {k}: {v}")
            break
except Exception as e:
    print(f"30m signals: {e}")
