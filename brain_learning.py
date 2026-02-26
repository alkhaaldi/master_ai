"""
Master AI Brain Learning v1.1
Pattern learning, memory, confidence decay, user corrections
"""
import asyncio
import re
import json
import logging
import sqlite3
import os
from datetime import datetime, timedelta

logger = logging.getLogger("brain.learning")

# Import shared state from core
from brain_core import _knowledge, _alias_cache, AUDIT_DB

_learn_queue = asyncio.Queue(maxsize=100)


def _get_relevant_patterns(goal):
    try:
        if not AUDIT_DB.exists(): return []
        keywords = _extract_keywords(goal)
        if not keywords: return []
        conn = sqlite3.connect(str(AUDIT_DB))
        rows = conn.execute(
            "SELECT content, context, confidence, hit_count FROM memory "
            "WHERE category='pattern' AND active=1 ORDER BY hit_count DESC LIMIT 20"
        ).fetchall()
        conn.close()
        results = []
        for content, ctx_str, conf, hits in rows:
            try:
                ctx = json.loads(ctx_str) if ctx_str else {}
                past_kw = ctx.get("goal_keywords", [])
                if len(set(keywords) & set(past_kw)) >= 1:
                    results.append({"goal": content, "actions": ctx.get("action_types", []),
                                   "confidence": conf, "hits": hits})
            except: pass
        results.sort(key=lambda x: x.get("hits", 0), reverse=True)
        if results:
            try:
                _c2 = sqlite3.connect(str(AUDIT_DB))
                for _rr in results[:3]:
                    _c2.execute("UPDATE memory SET hit_count=hit_count+1, last_used=datetime('now') WHERE content=? AND category='pattern' AND active=1", (_rr["goal"],))
                _c2.commit()
                _c2.close()
            except Exception:
                pass
        return results[:3]
    except: return []


def _detect_user_correction(goal, previous_results):
    markers = ["مو هذا", "لا مو", "غلط", "أقصد", "ما أبي",
               "not this", "wrong", "I meant"]
    for m in markers:
        if m in goal.lower(): return True
    if previous_results:
        last = previous_results[-1] if previous_results else {}
        if isinstance(last, dict) and not last.get("success", True): return True
    return False


def _apply_confidence_decay():
    try:
        conn = sqlite3.connect(str(AUDIT_DB))
        conn.execute("UPDATE memory SET confidence=MAX(confidence-0.05,0.1) "
                     "WHERE category='pattern' AND active=1 AND "
                     "(last_used IS NULL OR last_used < datetime('now','-7 days'))")
        conn.execute("UPDATE memory SET active=0 WHERE confidence<0.15 AND category!='alias'")
        conn.commit(); conn.close()
    except: pass


LEARN_RULES = {
    "save_pattern": True,       # successful multi-step patterns
    "save_entity_fix": True,    # entity corrections after failure
    "save_alias": True,         # user corrections ("مو هذا أقصد...")
    "save_greeting": False,
    "save_apology": False,
}



async def _learn_worker():
    """Single worker processing learning items from queue."""
    global _learn_queue
    while True:
        try:
            item = await _learn_queue.get()
            if item is None:
                break
            await _process_learn_item(item)
            _learn_queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Learn worker error: {e}")



async def _process_learn_item(item):
    """Process a single learning item."""
    goal = item.get("goal", "")
    actions = item.get("actions", [])
    results = item.get("results", [])

    # Skip trivial interactions
    if not actions or all(a.get("type") == "respond_text" for a in actions if isinstance(a, dict)):
        return

    has_errors = any(
        not r.get("success", True) for r in results if isinstance(r, dict)
    )
    has_successes = any(
        r.get("success", False) for r in results if isinstance(r, dict)
    )

    # Learn successful multi-step patterns
    if len(actions) > 1 and LEARN_RULES["save_pattern"]:
        pattern = {
            "goal_keywords": _extract_keywords(goal),
            "action_types": [a.get("type") for a in actions],
            "timestamp": datetime.now().isoformat()
        }
        _store_learning("pattern", goal[:100],
                       json.dumps(pattern, ensure_ascii=False),
                       source="verified_success")

    # Learn from entity errors
    if has_errors and LEARN_RULES["save_entity_fix"]:
        for i, r in enumerate(results):
            if isinstance(r, dict) and not r.get("success", True):
                error_msg = r.get("error", "")
                if error_msg:  # Save all errors as lessons
                    _store_learning("error_pattern", goal[:100],
                                  json.dumps({"error": error_msg[:200]},
                                            ensure_ascii=False),
                                  source="error_log", confidence=0.5)
    
    # Learn alias from successful correction
    if has_successes and LEARN_RULES.get("save_alias", True):
        if _detect_user_correction(goal, []):
            successful_entities = []
            for a in actions:
                eid = a.get("args", {}).get("entity_id", "")
                if eid and eid != "*":
                    successful_entities.extend(eid.split(","))
            if successful_entities:
                for kw in _extract_keywords(goal)[:3]:
                    if len(kw) > 2:
                        _store_learning("alias", kw,
                            json.dumps({"entities": successful_entities[:5]}, ensure_ascii=False),
                            source="user_correction")
                        logger.info(f"Learned alias: {kw} -> {successful_entities[:3]}")



def _extract_keywords(text):
    """Extract meaningful keywords from Arabic/English text."""
    stops = {"من", "في", "على", "عن", "إلى", "مع", "هل", "ما", "كيف", "أين", "متى",
             "و", "أو", "لا", "لم", "لن", "قد", "كل", "بعض", "هذا", "هذه", "ذلك",
             "عطني", "ابغي", "ابي", "بغيت", "أبي", "خلني", "شنو", "وش", "ليش",
             "the", "a", "an", "is", "are", "was", "for", "to", "of", "and", "in"}
    words = re.findall(r'[\w\u0600-\u06FF]+', text.lower())
    return [w for w in words if w not in stops and len(w) > 1][:10]



def _ensure_memory_table():
    """Auto-create memory table if missing."""
    try:
        conn = sqlite3.connect(str(AUDIT_DB))
        conn.execute("""CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL,
            content TEXT NOT NULL, context TEXT DEFAULT '{}',
            source TEXT DEFAULT 'unknown', confidence REAL DEFAULT 1.0,
            hit_count INTEGER DEFAULT 0, last_used TEXT,
            active INTEGER DEFAULT 1, created_at TEXT NOT NULL,
            UNIQUE(category, content))""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_cat ON memory(category, active)")
        conn.commit(); conn.close()
    except Exception: pass

_ensure_memory_table()



def _store_learning(category, content, context_json, source="unknown", confidence=1.0):
    """Store learning item with ON CONFLICT upsert."""
    try:
        conn = sqlite3.connect(str(AUDIT_DB))
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO memory (category,content,context,source,confidence,active,created_at) "
            "VALUES (?,?,?,?,?,1,?) ON CONFLICT(category,content) DO UPDATE SET "
            "hit_count=hit_count+1, confidence=MIN(confidence+0.1,1.0), last_used=?, context=?",
            (category, content, context_json, source, confidence, now, now, context_json))
        conn.commit(); conn.close()
    except Exception as e:
        logger.warning(f"_store_learning error: {e}")





# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. PUBLIC API (called from server.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def learn_from_result(goal, actions, results, response):
    """Enqueue a learning item. Non-blocking, never raises."""
    global _learn_queue
    try:
        if _learn_queue is None:
            _learn_queue = asyncio.Queue(maxsize=100)
            asyncio.create_task(_learn_worker())
            logger.info("Brain learn worker started")
        _learn_queue.put_nowait({
            "goal": goal,
            "actions": actions,
            "results": results,
            "response": response
        })
    except asyncio.QueueFull:
        logger.warning("Learn queue full, dropping item")
    except Exception as e:
        logger.warning(f"learn_from_result error: {e}")


def _learning_stats():
    """Return learning module statistics."""
    import sqlite3
    from pathlib import Path
    DB = Path(__file__).parent / 'data' / 'audit.db'
    stats = {'queue_size': 0}
    try:
        conn = sqlite3.connect(str(DB))
        rows = conn.execute('SELECT category, COUNT(*), AVG(confidence), SUM(hit_count) FROM memory WHERE active=1 GROUP BY category').fetchall()
        conn.close()
        for r in rows:
            stats[r[0]] = {'count': r[1], 'avg_conf': round(r[2], 2), 'hits': r[3] or 0}
        stats['total_memories'] = sum(r[1] for r in rows)
    except Exception as e:
        stats['error'] = str(e)
    return stats
