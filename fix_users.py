import sqlite3
conn = sqlite3.connect("/home/pi/master_ai/data/tasks.db")
conn.execute("DELETE FROM user_profiles")
from datetime import datetime
now = datetime.utcnow().isoformat() + "Z"
users = [
    ("bu_khalifa", "بو خليفة", "ar", "kuwaiti"),
    ("mama", "ناهد - أم سالم", "ar", "respectful"),
]
for uid, name, lang, tone in users:
    conn.execute("INSERT INTO user_profiles (user_id,name,language,tone,permissions,preferences,last_interaction,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (uid, name, lang, tone, '{}', '{}', now, now))
conn.commit()
print(f"Users reset: {len(users)}")
conn.close()
