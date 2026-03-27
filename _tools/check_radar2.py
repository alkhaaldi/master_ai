import sqlite3, os, glob
os.chdir("/var/lib/homeassistant/share/master_ai")

# Check all DBs for radar tables
for db_path in glob.glob("data/*.db") + glob.glob("*.db"):
    try:
        c = sqlite3.connect(db_path)
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        radar_tables = [t for t in tables if 'radar' in t.lower() or 'signal' in t.lower() or 'stock' in t.lower()]
        if radar_tables:
            print(f"{db_path}: {radar_tables}")
            for t in radar_tables:
                cnt = c.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
                last = c.execute(f"SELECT MAX(created_at) FROM [{t}]").fetchone()[0] if cnt > 0 else None
                print(f"  {t}: {cnt} rows, last: {last}")
                if cnt > 0:
                    cols = [d[0] for d in c.execute(f"SELECT * FROM [{t}] LIMIT 1").description]
                    print(f"  cols: {cols}")
                    rows = c.execute(f"SELECT * FROM [{t}] ORDER BY created_at DESC LIMIT 3").fetchall()
                    for r in rows:
                        print(f"  {r}")
        c.close()
    except Exception as e:
        print(f"{db_path}: err {e}")
