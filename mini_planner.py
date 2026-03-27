"""
mini_planner.py - Simple planner for compound tasks + intent classifier + trace logger
ChatGPT Plan #15 (planner mode) + #7 (intent types) + #19 (tracing)
"""
import json, time, logging, sqlite3
from pathlib import Path
from datetime import datetime

log = logging.getLogger("planner")
DB_PATH = Path("/home/pi/master_ai/data/traces.db")

# ═══ INTENT CLASSIFIER (#7) ═══
# 4 types: retrieval, action, reasoning, open

RETRIEVAL_SIGNALS = ["شنو","كم","وش","حالة","درجة","حرارة","status","state","كيف"]
ACTION_SIGNALS = ["شغل","طفي","افتح","سكر","اضبط","غير","حط","ارفع","نزل","turn","set"]
REASONING_SIGNALS = ["متى","ليش","شلون","كيف اقدر","وين","هل","إذا","لو"]
COMPOUND_SIGNALS = ["و","ثم","بعدين","وبعد","إلا إذا","لو","إذا كان"]

def classify_intent(text):
    """Classify user message into intent type."""
    t = text.strip().lower()
    words = t.split()
    
    # Check compound first
    compound_count = sum(1 for s in COMPOUND_SIGNALS if s in t)
    is_compound = compound_count >= 1 and len(words) >= 8
    
    # Score each type — use word-level matching to avoid substring false positives
    scores = {
        "retrieval": sum(1 for s in RETRIEVAL_SIGNALS if s in words),
        "action": sum(1 for s in ACTION_SIGNALS if s in words),
        "reasoning": sum(1 for s in REASONING_SIGNALS if s in words),
    }
    
    # Precedence: action verbs (imperative) > reasoning questions > retrieval
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        best = "open"
    elif scores["action"] > 0 and scores["action"] >= scores["retrieval"]:
        best = "action"
    elif scores["reasoning"] > 0 and any(s in words for s in ["ليش", "لماذا", "كيف"]):
        best = "reasoning"
    
    return {
        "type": best,
        "compound": is_compound,
        "scores": scores,
        "suggested_model": _model_for_intent(best, is_compound),
    }

def _model_for_intent(intent_type, compound):
    if compound:
        return "opus"
    if intent_type == "retrieval":
        return "sonnet"
    if intent_type == "action":
        return "sonnet"
    if intent_type == "reasoning":
        return "opus"
    return "sonnet"


# ═══ MINI PLANNER (#15) ═══

def decompose_compound(text):
    """Break a compound request into steps."""
    steps = []
    
    # Split by Arabic conjunctions
    parts = text
    for sep in [" ثم ", " وبعدين ", " بعدها "]:  # Removed " و " — too common in normal phrases
        parts = parts.replace(sep, "|||")
    
    raw_steps = [s.strip() for s in parts.split("|||") if s.strip()]
    
    for i, step in enumerate(raw_steps):
        intent = classify_intent(step)
        steps.append({
            "index": i + 1,
            "text": step,
            "intent": intent["type"],
            "model": intent["suggested_model"],
        })
    
    return {
        "original": text,
        "steps": steps,
        "total": len(steps),
        "needs_planning": len(steps) > 1,
    }


# ═══ TRACE LOGGER (#19) ═══

def _init_trace_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.execute("""CREATE TABLE IF NOT EXISTS traces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        msg_id TEXT,
        user_text TEXT,
        intent_type TEXT,
        compound INTEGER DEFAULT 0,
        model TEXT,
        tools_used TEXT,
        tools_count INTEGER DEFAULT 0,
        confidence_avg REAL DEFAULT 0,
        self_check_ok INTEGER DEFAULT 1,
        self_check_issues TEXT DEFAULT '',
        final_status TEXT DEFAULT 'ok',
        response_len INTEGER DEFAULT 0,
        elapsed_ms REAL DEFAULT 0,
        user_id TEXT DEFAULT 'default',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""")
    conn.commit()
    conn.close()

def save_trace(trace):
    """Save a trace record."""
    try:
        _init_trace_db()
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.execute(
            """INSERT INTO traces (msg_id, user_text, intent_type, compound, model,
               tools_used, tools_count, confidence_avg, self_check_ok, self_check_issues,
               final_status, response_len, elapsed_ms, user_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                trace.get("msg_id",""),
                trace.get("user_text","")[:200],
                trace.get("intent_type",""),
                1 if trace.get("compound") else 0,
                trace.get("model",""),
                json.dumps(trace.get("tools_used",[]), ensure_ascii=False),
                trace.get("tools_count",0),
                trace.get("confidence_avg",0),
                1 if trace.get("self_check_ok",True) else 0,
                json.dumps(trace.get("self_check_issues",[]), ensure_ascii=False),
                trace.get("final_status","ok"),
                trace.get("response_len",0),
                trace.get("elapsed_ms",0),
                trace.get("user_id","default"),
            )
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.debug(f"Trace save skip: {e}")

def get_traces(limit=20):
    """Get recent traces."""
    try:
        _init_trace_db()
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM traces ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except:
        return []

def get_trace_stats():
    """Get aggregated trace statistics."""
    try:
        _init_trace_db()
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        total = conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
        by_intent = dict(conn.execute(
            "SELECT intent_type, COUNT(*) FROM traces GROUP BY intent_type"
        ).fetchall())
        avg_ms = conn.execute("SELECT AVG(elapsed_ms) FROM traces").fetchone()[0] or 0
        fail_rate = conn.execute(
            "SELECT COUNT(*) FROM traces WHERE self_check_ok=0"
        ).fetchone()[0]
        by_model = dict(conn.execute(
            "SELECT model, COUNT(*) FROM traces GROUP BY model"
        ).fetchall())
        conn.close()
        return {
            "total": total,
            "by_intent": by_intent,
            "by_model": by_model,
            "avg_ms": round(avg_ms, 1),
            "fail_count": fail_rate,
            "fail_rate": round(fail_rate / max(total,1) * 100, 1),
        }
    except:
        return {"total": 0}

# Init on import
try:
    _init_trace_db()
except:
    pass
