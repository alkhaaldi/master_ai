import sqlite3
conn = sqlite3.connect('/home/pi/master_ai/data/life.db')
conn.row_factory = sqlite3.Row

# 1. Total events
total = conn.execute("SELECT COUNT(*) FROM stock_radar_events").fetchone()[0]
bull = conn.execute("SELECT COUNT(*) FROM stock_radar_events WHERE signal_type='bullish_cross'").fetchone()[0]
bear = conn.execute("SELECT COUNT(*) FROM stock_radar_events WHERE signal_type='bearish_cross'").fetchone()[0]
print(f"DB TOTAL: {total} | Bull: {bull} | Bear: {bear}")

# 2. All timeframes
tfs = conn.execute("SELECT DISTINCT timeframe FROM stock_radar_events").fetchall()
print(f"Timeframes: {[r[0] for r in tfs]}")

# 3. Last 5 events
rows = conn.execute("SELECT symbol, signal_type, price, ema_fast, ema_slow, rsi, candle_time, created_at FROM stock_radar_events ORDER BY created_at DESC LIMIT 5").fetchall()
print("\n--- Last 5 events ---")
for r in rows:
    print(f"  {r['symbol']} | {r['signal_type']} | price={r['price']} | EMA9={r['ema_fast']} EMA21={r['ema_slow']} | RSI={r['rsi']} | candle={r['candle_time']} | at={r['created_at']}")

# 4. Check EMA values make sense (fast should be close to slow at cross point)
print("\n--- EMA Cross Validation ---")
rows2 = conn.execute("SELECT symbol, signal_type, price, ema_fast, ema_slow FROM stock_radar_events ORDER BY created_at DESC LIMIT 10").fetchall()
for r in rows2:
    f = r['ema_fast'] or 0
    s = r['ema_slow'] or 0
    gap = abs(f - s) / s * 100 if s else 0
    ok = "OK" if gap < 3 else "WARN"
    cross_ok = "OK" if (r['signal_type'] == 'bullish_cross' and f > s) or (r['signal_type'] == 'bearish_cross' and f < s) else "WRONG"
    print(f"  {r['symbol']} | {r['signal_type']} | EMA9={f:.3f} EMA21={s:.3f} | gap={gap:.2f}% [{ok}] | direction={cross_ok}")

# 5. Stock radar state (for proximity)
states = conn.execute("SELECT COUNT(*) FROM stock_radar_state WHERE timeframe='30m' AND prev_ema_fast > 0").fetchone()[0]
print(f"\nRadar state entries (30m with EMA): {states}")

# 6. Verify candle_time is 30m aligned
print("\n--- Candle Time Check ---")
times = conn.execute("SELECT DISTINCT candle_time FROM stock_radar_events ORDER BY candle_time DESC LIMIT 10").fetchall()
for t in times:
    ct = t[0]
    minute = int(ct.split(':')[1]) if ':' in ct else -1
    aligned = minute in [0, 30]
    print(f"  {ct} | 30m aligned: {aligned}")

conn.close()
print("\n=== VALIDATION COMPLETE ===")
