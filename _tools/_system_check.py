import urllib.request, json

checks = {
    "Master AI Health": "http://localhost:9000/health",
    "Radar (30m signals)": "http://localhost:9000/dashboard/signals-30m",
    "Radar (1D)": "http://localhost:9000/dashboard/radar",
    "Brain": "http://localhost:9000/dashboard/brain",
    "Portfolio": "http://localhost:9000/dashboard/portfolio",
    "Decisions": "http://localhost:9000/api/decisions-now",
}

bridge_checks = {
    "Bridge Quote NBK": "http://192.168.111.158:8059/quote?symbol=NBK",
    "Bridge Quote CLEANING": "http://192.168.111.158:8059/quote?symbol=CLEANING",
    "Bridge Quote EQUIPMENT": "http://192.168.111.158:8059/quote?symbol=EQUIPMENT",
}

print("=" * 60)
print("  SYSTEM STATUS CHECK — Live Market")
print("=" * 60)

for name, url in checks.items():
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode())
        if name == "Master AI Health":
            print(f"\n  {name}: OK")
            print(f"    Version: {data.get('version')} | Schema: {data.get('schema_version')}")
            print(f"    Uptime: {data.get('uptime_seconds',0)//3600}h | Plugins: {data.get('plugins')}")
            print(f"    Autonomy: L{data.get('autonomy',{}).get('level')}")
        elif "signals" in name.lower() or "radar" in name.lower():
            sigs = data.get("signals", data.get("stocks", []))
            if isinstance(sigs, list):
                print(f"\n  {name}: OK — {len(sigs)} stocks")
            elif isinstance(data, dict):
                print(f"\n  {name}: OK — keys: {list(data.keys())[:5]}")
        elif name == "Brain":
            print(f"\n  {name}: OK")
            w = data.get("weights", {})
            if w:
                top = sorted(w.items(), key=lambda x: x[1], reverse=True)[:3]
                print(f"    Top weights: {', '.join(f'{k}={v:.2f}' for k,v in top)}")
        elif name == "Portfolio":
            pos = data.get("positions", data.get("open_positions", []))
            if isinstance(pos, list):
                print(f"\n  {name}: OK — {len(pos)} open positions")
            else:
                print(f"\n  {name}: OK")
        elif name == "Decisions":
            ops = data.get("opportunities", data.get("decisions", []))
            if isinstance(ops, list):
                print(f"\n  {name}: OK — {len(ops)} opportunities")
            else:
                print(f"\n  {name}: OK — keys: {list(data.keys())[:5]}")
    except Exception as e:
        print(f"\n  {name}: FAIL — {e}")

print(f"\n{'─'*60}")
print(f"  BRIDGE API (PC)")
print(f"{'─'*60}")

for name, url in bridge_checks.items():
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode())
        sym = data.get("symbol","")
        price = data.get("price",0)
        chg = data.get("change_percent",0)
        vol = data.get("volume",0)
        print(f"  {sym}: {price:.0f} ({chg:+.2f}%) vol={vol:,.0f}")
    except Exception as e:
        print(f"  {name}: FAIL — {e}")

print(f"\n{'='*60}")
print("  DONE")
print(f"{'='*60}")
