import urllib.request, json

checks = {
    "health": "http://localhost:9000/health",
    "signals-30m": "http://localhost:9000/dashboard/signals-30m",
    "radar": "http://localhost:9000/dashboard/radar",
    "portfolio": "http://localhost:9000/dashboard/portfolio",
    "brain": "http://localhost:9000/dashboard/brain",
    "decisions": "http://localhost:9000/api/decisions-now",
    "signals-1d": "http://localhost:9000/dashboard/signals",
}

for name, url in checks.items():
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode())
        if isinstance(data, dict):
            keys = list(data.keys())
            # Check for empty data
            empty = []
            for k in keys:
                v = data[k]
                if isinstance(v, list) and len(v) == 0:
                    empty.append(k)
                elif isinstance(v, dict) and len(v) == 0:
                    empty.append(k)
                elif v is None:
                    empty.append(k)
            
            # Count items in lists
            counts = {}
            for k in keys:
                v = data[k]
                if isinstance(v, list):
                    counts[k] = len(v)
            
            status = "OK" if not empty else f"EMPTY: {empty}"
            print(f"  {name:15s} | {status} | counts: {counts}")
        else:
            print(f"  {name:15s} | OK (type={type(data).__name__})")
    except Exception as e:
        print(f"  {name:15s} | FAIL: {e}")
