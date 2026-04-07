"""Integration 7: Wire task_manager into server.py API endpoints."""
import sys, py_compile

FILE = "/home/pi/master_ai/server.py"
with open(FILE) as f:
    content = f.read()

# Replace news refresh endpoints with task-tracked versions
old_boursa = """@app.post("/api/news/refresh-boursa")
async def api_news_refresh_boursa():
    if not NEWS_ENGINE_OK:
        return {"ok": False, "error": "news_engine not loaded"}
    result = await asyncio.to_thread(news_refresh_boursa)
    return result"""

new_boursa = """@app.post("/api/news/refresh-boursa")
async def api_news_refresh_boursa():
    if not NEWS_ENGINE_OK:
        return {"ok": False, "error": "news_engine not loaded"}
    # Task tracking (Integration 7)
    try:
        from task_manager import TaskManager, TaskType
        _tm = TaskManager.instance()
        _task = _tm.create_task(TaskType.NEWS_FETCH, {"source": "boursa"})
        _tm.start_task(_task.task_id)
    except Exception:
        _tm, _task = None, None
    try:
        result = await asyncio.to_thread(news_refresh_boursa)
        if _tm and _task:
            _tm.complete_task(_task.task_id, result=str(result.get("count", 0)) + " items")
        return result
    except Exception as e:
        if _tm and _task:
            _tm.fail_task(_task.task_id, error=str(e)[:100])
        return {"ok": False, "error": str(e)}"""

if old_boursa in content:
    content = content.replace(old_boursa, new_boursa, 1)
    print("Wired TaskManager into refresh-boursa")
else:
    print("WARN: Could not find refresh-boursa endpoint")

old_gemini = """@app.post("/api/news/refresh-gemini")
async def api_news_refresh_gemini():
    if not NEWS_ENGINE_OK:
        return {"ok": False, "error": "news_engine not loaded"}
    result = await asyncio.to_thread(news_refresh_gemini)
    return result"""

new_gemini = """@app.post("/api/news/refresh-gemini")
async def api_news_refresh_gemini():
    if not NEWS_ENGINE_OK:
        return {"ok": False, "error": "news_engine not loaded"}
    try:
        from task_manager import TaskManager, TaskType
        _tm = TaskManager.instance()
        _task = _tm.create_task(TaskType.NEWS_FETCH, {"source": "gemini"})
        _tm.start_task(_task.task_id)
    except Exception:
        _tm, _task = None, None
    try:
        result = await asyncio.to_thread(news_refresh_gemini)
        if _tm and _task:
            _tm.complete_task(_task.task_id, result=str(result.get("count", 0)) + " items")
        return result
    except Exception as e:
        if _tm and _task:
            _tm.fail_task(_task.task_id, error=str(e)[:100])
        return {"ok": False, "error": str(e)}"""

if old_gemini in content:
    content = content.replace(old_gemini, new_gemini, 1)
    print("Wired TaskManager into refresh-gemini")
else:
    print("WARN: Could not find refresh-gemini endpoint")

with open(FILE, "w") as f:
    f.write(content)

try:
    py_compile.compile(FILE, doraise=True)
    print("Integration 7 DONE — syntax OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
    sys.exit(1)
