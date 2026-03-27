import sqlite3, os
os.chdir("/var/lib/homeassistant/share/master_ai")
c = sqlite3.connect("data/life.db")

# List all radar tables and their columns
for t in ['stock_radar_events', 'stock_radar_daily', 'stock_radar_watchlist', 'stock_radar_state', 'tv_signal_stats']:
    try:
        cols = [d[1] for d in c.execute(f"PRAGMA table_info({t})").fetchall()]
        cnt = c.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        print(f"\n{t}: {cnt} rows")
        print(f"  cols: {cols}")
        if cnt > 0:
            rows = c.execute(f"SELECT * FROM [{t}] ORDER BY rowid DESC LIMIT 3").fetchall()
            for r in rows:
                print(f"  {r}")
    except Exception as e:
        print(f"{t}: err {e}")

c.close()
