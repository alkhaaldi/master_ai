"""Add /api/tasks endpoint to server.py (integrates task_manager.py with dashboard)."""
import sys
from datetime import datetime

FILE = "/home/pi/master_ai/server.py"
with open(FILE) as f:
    content = f.read()

# Insert /api/tasks right after the service-health endpoint block
# Find the KAIROS section marker
marker = "# ── KAIROS Agent API ──"
idx = content.find(marker)
if idx < 0:
    print("Could not find KAIROS marker")
    sys.exit(1)

endpoint_code = '''
# ── Task Manager API (Tier2 #8 integration) ──────────────
@app.get("/api/tasks")
async def get_tasks():
    """Expose TaskManager state for dashboard (system.html + home.html)."""
    try:
        from task_manager import TaskManager
        tm = TaskManager.instance()
        running = tm.get_running_tasks()
        recent = tm.get_recent_tasks(10)

        def _fmt(t):
            d = t.to_dict()
            if t.started_at:
                d["started_at"] = datetime.utcfromtimestamp(t.started_at).isoformat() + "Z"
            if t.completed_at:
                d["completed_at"] = datetime.utcfromtimestamp(t.completed_at).isoformat() + "Z"
            return d

        all_recent = tm.get_recent_tasks(100)
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0).timestamp()
        today_tasks = [t for t in all_recent if t.created_at >= today_start]

        return {
            "running": [_fmt(t) for t in running],
            "recent": [_fmt(t) for t in recent if t.is_terminal],
            "stats": {
                "total_today": len(today_tasks),
                "completed_today": sum(1 for t in today_tasks if t.status.value == "completed"),
                "failed_today": sum(1 for t in today_tasks if t.status.value == "failed"),
            },
        }
    except Exception as e:
        return {"running": [], "recent": [], "stats": {}, "error": str(e)}


'''

content = content[:idx] + endpoint_code + content[idx:]

with open(FILE, "w") as f:
    f.write(content)

print("PATCHED OK — added /api/tasks endpoint")
