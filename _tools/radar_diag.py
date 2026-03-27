import sqlite3, os, sys
from datetime import datetime, timedelta
os.chdir("/var/lib/homeassistant/share/master_ai")

print("=== RADAR DIAGNOSTICS ===")
print(f"Time now (UTC): {datetime.utcnow()}")
print(f"Time now (KWT): {datetime.utcnow() + timedelta(hours=3)}")

# 1. Market open check
try:
    from tv_data import _is_market_open
    print(f"\nMarket open: {_is_market_open()}")
except Exception as e:
    print(f"\nMarket check ERROR: {e}")

# 2. Radar config
try:
    from stock_radar import _get_config
    cfg = _get_config()
    print(f"\nRadar enabled: {cfg.get('enabled')}")
    print(f"Poll seconds: {cfg.get('poll_seconds')}")
    print(f"Cooldown min: {cfg.get('cooldown_minutes')}")
except Exception as e:
    print(f"\nConfig ERROR: {e}")

# 3. Events count
c = sqlite3.connect("data/life.db")
r = c.execute("SELECT COUNT(*) FROM stock_radar_events").fetchone()
print(f"\nEvents total: {r[0]}")

# 4. Last state update
rows = c.execute("SELECT symbol, last_signal, updated_at FROM stock_radar_state ORDER BY updated_at DESC LIMIT 5").fetchall()
print(f"\nLast 5 state updates:")
for r in rows:
    print(f"  {r[0]} {r[1]} @ {r[2]}")

# 5. Try fetching one stock to test tvDatafeed
print("\n=== LIVE DATA TEST ===")
try:
    from tv_data import _get_tv, resolve_symbol
    from tvDatafeed import Interval
    tv = _get_tv()
    df = tv.get_hist("KFH", "KSE", Interval.in_30_minute, n_bars=5)
    if df is not None and not df.empty:
        print(f"KFH data OK: {len(df)} bars, last={df.index[-1]}")
        print(f"  close={df.iloc[-1]['close']} vol={df.iloc[-1]['volume']}")
    else:
        print("KFH data: EMPTY/None - tvDatafeed not returning data!")
except Exception as e:
    print(f"KFH data ERROR: {e}")

# 6. Check server.log for radar errors
print("\n=== RECENT RADAR LOGS ===")
try:
    with open("server.log", "r") as f:
        lines = f.readlines()
    radar_lines = [l.strip() for l in lines if "radar" in l.lower()][-10:]
    if radar_lines:
        for l in radar_lines:
            print(l[:200])
    else:
        print("No radar mentions in server.log")
except Exception as e:
    print(f"Log read error: {e}")

c.close()
print("\n=== DONE ===")
