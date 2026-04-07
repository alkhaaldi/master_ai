import sqlite3
c = sqlite3.connect("/home/pi/master_ai/data/life.db")
# Check table structure
cols = c.execute("PRAGMA table_info(stock_radar_daily)").fetchall()
print("Columns:", [col[1] for col in cols])
r = c.execute("SELECT COUNT(*) FROM stock_radar_daily").fetchone()
print(f"Total rows: {r[0]}")
# Find date column
date_cols = [col[1] for col in cols if 'date' in col[1].lower() or 'time' in col[1].lower() or 'updated' in col[1].lower()]
if date_cols:
    for dc in date_cols:
        r2 = c.execute(f"SELECT MAX({dc}) FROM stock_radar_daily").fetchone()
        print(f"Latest {dc}: {r2[0]}")
c.close()
