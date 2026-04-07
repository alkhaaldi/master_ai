import urllib.request, json

# Check radar endpoint structure
with urllib.request.urlopen("http://localhost:9000/dashboard/radar", timeout=10) as r:
    data = json.loads(r.read().decode())
print(f"Radar keys: {list(data.keys())}")
for k, v in data.items():
    if isinstance(v, list):
        print(f"  {k}: {len(v)} items")
    elif isinstance(v, dict):
        print(f"  {k}: dict with {len(v)} keys")
    else:
        print(f"  {k}: {v}")

# Check daily context
dc = data.get("radar_daily_context", data.get("daily_context", []))
if isinstance(dc, list) and dc:
    print(f"\nDaily context sample: {dc[0].get('symbol','?')}")
    print(f"  Keys: {list(dc[0].keys())[:8]}")

# Check if refresh process still running
import subprocess
result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
count = sum(1 for line in result.stdout.split("\n") if "refresh_daily" in line and "grep" not in line)
print(f"\nrefresh_daily processes still running: {count}")
