#!/usr/bin/env python3
"""Run daily refresh and check results."""
import json, sys
sys.path.insert(0, "/home/pi/master_ai")
from stock_radar import refresh_daily_snapshot
r = refresh_daily_snapshot()
print(json.dumps(r, default=str))

# Now check what changed
import sqlite3
c = sqlite3.connect("/home/pi/master_ai/data/life.db")
c.row_factory = sqlite3.Row
rows = c.execute("SELECT symbol, macd_cross, daily_ema_cross, score, verdict, bb_squeeze FROM stock_radar_daily WHERE macd_cross != 'none' OR daily_ema_cross != 'none' OR score > 0 LIMIT 10").fetchall()
print(f"\n=== Symbols with crosses/scores: {len(rows)} ===")
for r in rows:
    print(json.dumps(dict(r)))
c.close()
