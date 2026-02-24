
import re

with open("/home/pi/master_ai/server.py", "r") as f:
    content = f.read()

# --- Patch /claude return to include sessions ---
old_ret = '        "knowledge": {"count": len(knowledge_data), "items": knowledge_data}\n    }'
new_ret = """        "knowledge": {"count": len(knowledge_data), "items": knowledge_data},
        "recent_sessions": sessions_data
    }"""

# Also need to add session fetch code before the return
old_knowledge_block = '    # Get knowledge base\n    knowledge_data = []'
new_knowledge_block = """    # Get recent sessions
    sessions_data = []
    try:
        async with aiosqlite.connect(TASKS_DB) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM session_log ORDER BY id DESC LIMIT 5")
            rows = await cursor.fetchall()
            sessions_data = [dict(r) for r in rows]
    except:
        sessions_data = []

    # Get knowledge base
    knowledge_data = []"""

if old_knowledge_block in content:
    content = content.replace(old_knowledge_block, new_knowledge_block)
    print("Added session fetch to /claude")
if old_ret in content:
    content = content.replace(old_ret, new_ret)
    print("Added sessions to /claude return")

# --- Add /sessions endpoints ---
sessions_code = """
# ============================================================
#  SESSION LOG
# ============================================================
from tasks_db import add_session_log, get_session_logs, get_latest_session

class SessionCreate(BaseModel):
    summary: str
    changes_made: str = ""
    decisions: str = ""
    blockers: str = ""
    next_steps: str = ""

@app.post("/sessions")
async def create_session(data: SessionCreate):
    from datetime import datetime as dt2
    session_date = dt2.now().strftime("%Y-%m-%d %H:%M")
    sid = await add_session_log(session_date, data.summary, data.changes_made, data.decisions, data.blockers, data.next_steps)
    return {"id": sid, "status": "logged"}

@app.get("/sessions")
async def list_sessions_log(limit: int = Query(default=10)):
    sessions = await get_session_logs(limit)
    return {"sessions": sessions}

@app.get("/sessions/latest")
async def latest_session():
    s = await get_latest_session()
    return s if s else {"message": "no sessions yet"}

"""

marker = "# ============================================================\n#  KNOWLEDGE BASE\n# ============================================================"
if marker in content:
    content = content.replace(marker, sessions_code + marker)
    print("Added /sessions endpoints")

with open("/home/pi/master_ai/server.py", "w") as f:
    f.write(content)
print("server.py saved")
