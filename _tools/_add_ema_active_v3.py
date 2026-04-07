import ast, os

BASE = '/home/pi/master_ai'
server_path = os.path.join(BASE, 'server.py')

with open(server_path, 'r') as f:
    original = f.read()

# Verify original syntax
try:
    ast.parse(original)
    print("Step 1: Current syntax OK")
except SyntaxError as e:
    print(f"ABORT: syntax error line {e.lineno}: {e.msg}")
    exit(1)

# Check if ema-active already exists
if 'ema-active' in original:
    print("ema-active already exists, skipping")
    exit(0)

# The endpoint code - using regular strings, no f-strings, no escaping issues
endpoint = '''

@app.get("/dashboard/ema-active")
async def dashboard_ema_active():
    """Current EMA 9/21 status for all tracked stocks."""
    import sqlite3 as _sq3

    db_path = os.path.join(BASE_DIR, "data", "life.db")
    conn = _sq3.connect(db_path)
    conn.row_factory = _sq3.Row

    states = conn.execute(
        "SELECT symbol, last_signal, last_signal_candle_time, updated_at,"
        " prev_ema_fast, prev_ema_slow"
        " FROM stock_radar_state"
        " WHERE timeframe='30m' AND last_signal IS NOT NULL AND last_signal != ''"
    ).fetchall()

    events = conn.execute(
        "SELECT e.symbol, e.signal_type, e.price, e.ema_fast, e.ema_slow,"
        " e.rsi, e.volume, e.score, e.score_class, e.verdict,"
        " e.support, e.resistance, e.vol_ratio, e.candle_time, e.created_at"
        " FROM stock_radar_events e"
        " INNER JOIN ("
        "   SELECT symbol, MAX(created_at) as max_time"
        "   FROM stock_radar_events GROUP BY symbol"
        " ) latest ON e.symbol = latest.symbol AND e.created_at = latest.max_time"
    ).fetchall()
    conn.close()

    from tv_data import KSE_STOCKS
    event_map = {}
    for ev in events:
        event_map[ev["symbol"]] = dict(ev)

    bullish = []
    bearish = []
    for st in states:
        sym = st["symbol"]
        sig = st["last_signal"]
        ev = event_map.get(sym, {})
        entry = {
            "symbol": sym,
            "name_ar": KSE_STOCKS.get(sym, sym),
            "status": "bullish" if "bullish" in sig else "bearish",
            "last_signal": sig,
            "signal_time": st["last_signal_candle_time"] or st["updated_at"],
            "price": ev.get("price"),
            "ema9": ev.get("ema_fast"),
            "ema21": ev.get("ema_slow"),
            "rsi": ev.get("rsi"),
            "volume": ev.get("volume"),
            "score": ev.get("score"),
            "score_class": ev.get("score_class"),
            "verdict": ev.get("verdict"),
            "support": ev.get("support"),
            "resistance": ev.get("resistance"),
            "vol_ratio": ev.get("vol_ratio"),
            "updated_at": st["updated_at"],
        }
        if "bullish" in sig:
            bullish.append(entry)
        else:
            bearish.append(entry)

    bullish.sort(key=lambda x: x.get("signal_time") or "", reverse=True)
    bearish.sort(key=lambda x: x.get("signal_time") or "", reverse=True)

    from datetime import datetime
    return {
        "bullish_count": len(bullish),
        "bearish_count": len(bearish),
        "total": len(bullish) + len(bearish),
        "bullish": bullish,
        "bearish": bearish,
        "timestamp": datetime.utcnow().isoformat(),
    }
'''

# Insert before @app.get("/health")
anchor = '\n@app.get("/health")'
if anchor not in original:
    print("ABORT: anchor not found")
    exit(1)

modified = original.replace(anchor, endpoint + anchor, 1)

# Add to OPEN_PATHS
old_paths = '"/dashboard/ema-proximity"'
new_paths = '"/dashboard/ema-proximity", "/dashboard/ema-active"'
if old_paths in modified and '"/dashboard/ema-active"' not in modified.split('OPEN_PATHS')[0] + modified.split('OPEN_PATHS')[1].split('}')[0]:
    modified = modified.replace(old_paths, new_paths, 1)
    print("Step 2: Added to OPEN_PATHS")

# Verify modified syntax
try:
    ast.parse(modified)
    print("Step 3: Modified syntax OK")
except SyntaxError as e:
    print(f"ABORT: modified syntax error line {e.lineno}: {e.msg}")
    print(f"Text: {e.text}")
    exit(1)

with open(server_path, 'w') as f:
    f.write(modified)

print(f"Step 4: Saved ({len(modified)} bytes)")
print("SUCCESS")
