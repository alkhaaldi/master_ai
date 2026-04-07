import ast, os, sys

BASE = '/home/pi/master_ai'
server_path = os.path.join(BASE, 'server.py')

# Read current server.py
with open(server_path, 'r') as f:
    original = f.read()

# Verify original is valid first
try:
    ast.parse(original)
    print("Current server.py: SYNTAX OK")
except SyntaxError as e:
    print(f"ABORT: Current server.py has syntax error: {e}")
    sys.exit(1)

# The endpoint to add
ENDPOINT_CODE = '''
@app.get("/dashboard/ema-active")
async def dashboard_ema_active():
    """Current EMA 9/21 status for all tracked stocks."""
    import sqlite3 as _sq
    from datetime import datetime as _dt

    db_path = os.path.join(BASE_DIR, "data", "life.db")
    conn = _sq.connect(db_path)
    conn.row_factory = _sq.Row

    states = conn.execute(
        "SELECT symbol, last_signal, last_signal_candle_time, updated_at, "
        "prev_ema_fast, prev_ema_slow "
        "FROM stock_radar_state "
        "WHERE timeframe=\'30m\' AND last_signal IS NOT NULL AND last_signal != \'\'"
    ).fetchall()

    events = conn.execute(
        "SELECT e.symbol, e.signal_type, e.price, e.ema_fast, e.ema_slow, "
        "e.rsi, e.volume, e.score, e.score_class, e.verdict, "
        "e.support, e.resistance, e.vol_ratio, e.candle_time, e.created_at "
        "FROM stock_radar_events e "
        "INNER JOIN ("
        "  SELECT symbol, MAX(created_at) as max_time "
        "  FROM stock_radar_events GROUP BY symbol"
        ") latest ON e.symbol = latest.symbol AND e.created_at = latest.max_time"
    ).fetchall()
    conn.close()

    from tv_data import KSE_STOCKS
    event_map = {ev["symbol"]: dict(ev) for ev in events}

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
            "ema9": ev.get("ema_fast") or (st["prev_ema_fast"] if st["prev_ema_fast"] else None),
            "ema21": ev.get("ema_slow") or (st["prev_ema_slow"] if st["prev_ema_slow"] else None),
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

    return {
        "bullish_count": len(bullish),
        "bearish_count": len(bearish),
        "total": len(bullish) + len(bearish),
        "bullish": bullish,
        "bearish": bearish,
        "timestamp": _dt.utcnow().isoformat(),
    }
'''

# Find insertion point: before @app.get("/health")
anchor = '\n@app.get("/health")'
if anchor not in original:
    print("ABORT: anchor not found")
    sys.exit(1)

modified = original.replace(anchor, ENDPOINT_CODE + anchor, 1)

# Update OPEN_PATHS
modified = modified.replace(
    '"/dashboard/ema-proximity"',
    '"/dashboard/ema-proximity", "/dashboard/ema-active"'
)

# SYNTAX CHECK before saving
try:
    ast.parse(modified)
    print("Modified server.py: SYNTAX OK")
except SyntaxError as e:
    print(f"ABORT: Modified server.py has syntax error at line {e.lineno}: {e}")
    sys.exit(1)

# Save
with open(server_path, 'w') as f:
    f.write(modified)

print(f"SUCCESS: ema-active endpoint added. File size: {len(modified)} bytes")
