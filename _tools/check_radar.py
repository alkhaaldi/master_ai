import sqlite3, os
os.chdir("/var/lib/homeassistant/share/master_ai")
c = sqlite3.connect("data/audit.db")

# Radar events
r = c.execute("SELECT COUNT(*) FROM radar_events").fetchone()
print(f"radar_events total: {r[0]}")

r = c.execute("SELECT MAX(created_at) FROM radar_events").fetchone()
print(f"last event: {r[0]}")

r = c.execute("SELECT created_at, symbol, signal_type FROM radar_events ORDER BY created_at DESC LIMIT 5").fetchall()
print("recent events:")
for row in r:
    print(f"  {row[0]} {row[1]} {row[2]}")

# Radar config
r = c.execute("SELECT key, value FROM radar_config WHERE key IN ('enabled','interval_sec','last_scan')").fetchall()
print("\nradar config:")
for row in r:
    print(f"  {row[0]} = {row[1]}")

# Daily snapshot
r = c.execute("SELECT COUNT(*) FROM stock_radar_daily").fetchone()
print(f"\ndaily snapshot rows: {r[0]}")

r = c.execute("SELECT MAX(updated_at) FROM stock_radar_daily").fetchone()
print(f"daily last update: {r[0]}")

c.close()
