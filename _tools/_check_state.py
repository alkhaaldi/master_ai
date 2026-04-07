import sqlite3
conn = sqlite3.connect('/home/pi/master_ai/data/life.db')
conn.row_factory = sqlite3.Row

# Check radar state
rows = conn.execute("""
    SELECT symbol, prev_ema_fast, prev_ema_slow, last_signal, last_signal_candle_time, updated_at 
    FROM stock_radar_state 
    WHERE timeframe='30m' 
    ORDER BY updated_at DESC 
    LIMIT 20
""").fetchall()

print(f"Total radar_state 30m rows: {len(rows)}")
print()
for r in rows:
    f = r['prev_ema_fast'] or 0
    s = r['prev_ema_slow'] or 0
    pos = "EMA9 > EMA21" if f > s else "EMA9 < EMA21" if f < s else "equal"
    print(f"  {r['symbol']:12} | EMA9={f:>10.3f} | EMA21={s:>10.3f} | {pos:14} | last_sig={r['last_signal'] or 'none':15} | {r['updated_at']}")

# Also check: how many have EMA data at all?
all_rows = conn.execute("SELECT COUNT(*) FROM stock_radar_state WHERE timeframe='30m'").fetchone()[0]
with_ema = conn.execute("SELECT COUNT(*) FROM stock_radar_state WHERE timeframe='30m' AND prev_ema_fast > 0").fetchone()[0]
with_sig = conn.execute("SELECT COUNT(*) FROM stock_radar_state WHERE timeframe='30m' AND last_signal IS NOT NULL AND last_signal != ''").fetchone()[0]
print(f"\nTotal 30m states: {all_rows}")
print(f"With EMA data: {with_ema}")
print(f"With last_signal: {with_sig}")

# Check what columns exist
cols = conn.execute("PRAGMA table_info(stock_radar_state)").fetchall()
print(f"\nColumns: {[c['name'] for c in cols]}")

conn.close()
