import json, subprocess, sqlite3, os
from datetime import datetime

DB_PATH = "/home/pi/master_ai/data/audit.db"  # consolidated from tasks.db

# Create daily_stats table
conn = sqlite3.connect(DB_PATH)
conn.execute("""CREATE TABLE IF NOT EXISTS daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    total_entities INTEGER,
    online INTEGER,
    offline INTEGER,
    by_domain TEXT,
    captured_at TEXT
)""")
conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_stats(date)")
conn.commit()

# Function to capture stats
def capture():
    r = subprocess.run(['curl','-s','-H','Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI1ZDVlZWRkMzk0MjY0MDk2OTY0YThlNjYyZDU0NTYzYiIsImlhdCI6MTc3MTI1NDI4NywiZXhwIjoyMDg2NjE0Mjg3fQ.Ws_86k8u0abSGfBZMYxKVSxzO8r6kX2yyIXPicjyFd0','http://localhost:8123/api/states'], capture_output=True, text=True)
    entities = json.loads(r.stdout)
    
    total = len(entities)
    online = sum(1 for e in entities if e['state'] not in ['unavailable','unknown'])
    offline = total - online
    
    by_domain = {}
    for e in entities:
        d = e['entity_id'].split('.')[0]
        if d not in by_domain:
            by_domain[d] = {'total':0,'online':0}
        by_domain[d]['total'] += 1
        if e['state'] not in ['unavailable','unknown']:
            by_domain[d]['online'] += 1
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Check if already captured today
    existing = conn.execute("SELECT id FROM daily_stats WHERE date=?", (today,)).fetchone()
    if existing:
        conn.execute("UPDATE daily_stats SET total_entities=?, online=?, offline=?, by_domain=?, captured_at=? WHERE date=?",
            (total, online, offline, json.dumps(by_domain), datetime.now().isoformat(), today))
    else:
        conn.execute("INSERT INTO daily_stats (date, total_entities, online, offline, by_domain, captured_at) VALUES (?,?,?,?,?,?)",
            (today, total, online, offline, json.dumps(by_domain), datetime.now().isoformat()))
    
    conn.commit()
    return total, online, offline, today

total, online, offline, today = capture()
print(f"Captured: {today} | Total:{total} Online:{online} Offline:{offline}")
conn.close()
