import sqlite3, json
c = sqlite3.connect("/home/pi/master_ai/data/life.db")
c.row_factory = sqlite3.Row
rows = c.execute("SELECT symbol, macd_cross, daily_ema_cross, score, verdict, bb_squeeze FROM stock_radar_daily LIMIT 8").fetchall()
for r in rows:
    print(json.dumps(dict(r)))
