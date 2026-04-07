import urllib.request, json

endpoints = [
    ("signals-30m", "http://localhost:9000/dashboard/signals-30m"),
    ("portfolio", "http://localhost:9000/dashboard/portfolio"),
    ("brain", "http://localhost:9000/dashboard/brain"),
]

for name, url in endpoints:
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read().decode())
        if name == "signals-30m":
            sigs = data.get("signals", [])
            print(f"  {name}: {len(sigs)} signals")
            if len(sigs) == 0:
                print(f"    keys: {list(data.keys())}")
                for k, v in data.items():
                    if isinstance(v, str):
                        print(f"    {k}: {v}")
        elif name == "portfolio":
            pos = data.get("open_positions", [])
            print(f"  {name}: {len(pos)} positions")
            if pos:
                for p in pos[:2]:
                    print(f"    {p['symbol']}: price={p.get('current_price')} source={p.get('quote_source')} support={p.get('support')} resistance={p.get('resistance')}")
        elif name == "brain":
            w = data.get("weights", {})
            print(f"  {name}: OK, weights={len(w)}")
    except Exception as e:
        print(f"  {name}: FAIL ({e})")
