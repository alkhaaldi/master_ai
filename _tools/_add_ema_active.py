import sqlite3, os, sys
from datetime import datetime, timedelta

BASE_DIR = '/home/pi/master_ai'

# Read the file
with open(os.path.join(BASE_DIR, 'server.py'), 'r') as f:
    content = f.read()

# The new endpoint code
new_endpoint = '''

@app.get("/dashboard/ema-active")
async def dashboard_ema_active():
    """Current EMA 9/21 status for all tracked stocks — who is bullish NOW."""
    import sqlite3
    from datetime import datetime

    conn = sqlite3.connect(os.path.join(BASE_DIR, "data", "life.db"))
    conn.row_factory = sqlite3.Row

    # Get latest signal per symbol from state table
    states = conn.execute("""
        SELECT symbol, last_signal, last_signal_candle_time, updated_at,
               prev_ema_fast, prev_ema_slow
        FROM stock_radar_state
        WHERE timeframe = '30m' AND last_signal IS NOT NULL AND last_signal != ''
    """).fetchall()

    # Get latest event details per symbol for enrichment
    events = conn.execute("""
        SELECT e.symbol, e.signal_type, e.price, e.ema_fast, e.ema_slow,
               e.rsi, e.volume, e.score, e.score_class, e.verdict,
               e.support, e.resistance, e.vol_ratio, e.candle_time, e.created_at
        FROM stock_radar_events e
        INNER JOIN (
            SELECT symbol, MAX(created_at) as max_time
            FROM stock_radar_events
            GROUP BY symbol
        ) latest ON e.symbol = latest.symbol AND e.created_at = latest.max_time
    """).fetchall()
    conn.close()

    from tv_data import KSE_STOCKS

    # Build event lookup
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

    # Sort by signal time descending
    bullish.sort(key=lambda x: x.get("signal_time") or "", reverse=True)
    bearish.sort(key=lambda x: x.get("signal_time") or "", reverse=True)

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
if anchor in content:
    content = content.replace(anchor, new_endpoint + anchor, 1)
    # Also add to OPEN_PATHS
    content = content.replace(
        '"/dashboard/ema-proximity"',
        '"/dashboard/ema-proximity", "/dashboard/ema-active"'
    )
    with open(os.path.join(BASE_DIR, 'server.py'), 'w') as f:
        f.write(content)
    print("OK: ema-active endpoint added + OPEN_PATHS updated")
else:
    print("ERROR: anchor not found")
