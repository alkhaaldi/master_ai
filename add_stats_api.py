path = "/home/pi/master_ai/server.py"
with open(path) as f:
    content = f.read()

# Add stats endpoint before SHIFT SCHEDULE section
old = """# ============================================================
#  SHIFT SCHEDULE
# ============================================================"""

new = """# ============================================================
#  DAILY STATS
# ============================================================

@app.get("/stats/daily")
async def get_daily_stats(days: int = Query(default=7, ge=1, le=90)):
    import sqlite3
    conn = sqlite3.connect("/home/pi/master_ai/data/tasks.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM daily_stats ORDER BY date DESC LIMIT ?", (days,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        entry = dict(r)
        if entry.get('by_domain'):
            entry['by_domain'] = json.loads(entry['by_domain'])
        result.append(entry)
    return {"days": len(result), "stats": result}

@app.post("/stats/capture")
async def capture_stats_now():
    import subprocess
    r = subprocess.run(["/home/pi/master_ai/venv/bin/python3", "/home/pi/master_ai/daily_stats.py"],
        capture_output=True, text=True, timeout=30)
    return {"success": r.returncode == 0, "output": r.stdout.strip()}

# ============================================================
#  SHIFT SCHEDULE
# ============================================================"""

if old in content and '/stats/daily' not in content:
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    import py_compile
    try:
        py_compile.compile(path, doraise=True)
        print("OK")
    except py_compile.PyCompileError as e:
        print(f"ERR: {e}")
else:
    if '/stats/daily' in content:
        print("ALREADY_EXISTS")
    else:
        print("NOT_FOUND")
