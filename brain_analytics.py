"""
Brain Analytics & Advanced Learning — Phase 6
Feedback collection, knowledge sync, performance analytics.
"""
import json, sqlite3, logging, asyncio
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger("brain.analytics")

DB_PATH = Path(__file__).parent / "data" / "audit.db"
KNOWLEDGE_PATH = Path(__file__).parent / "knowledge.json"
POLICY_PATH = Path(__file__).parent / "policy.json"

# ═══════════════════════════════════════
# DB setup
# ═══════════════════════════════════════

def _ensure_analytics_tables():
    """Create feedback and analytics tables."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                user_id TEXT DEFAULT 'bu_khalifa',
                goal TEXT,
                rating INTEGER,
                comment TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS request_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'bu_khalifa',
                goal TEXT,
                actions_count INTEGER,
                success INTEGER,
                response_time_ms INTEGER,
                used_quick_template INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reqlog_created ON request_log(created_at)")
        conn.commit()
        conn.close()
        logger.info("Analytics tables ready")
    except Exception as e:
        logger.error(f"Analytics table error: {e}")

# ═══════════════════════════════════════
# Feedback collection
# ═══════════════════════════════════════

def record_feedback(session_id: str, rating: int, comment: str = "", user_id: str = "bu_khalifa", goal: str = ""):
    """Record user feedback (1-5 or thumbs up/down as 1/5)."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO feedback (session_id, user_id, goal, rating, comment) VALUES (?,?,?,?,?)",
            (session_id, user_id, goal[:200], rating, comment[:500])
        )
        conn.commit()
        conn.close()
        logger.info(f"Feedback recorded: session={session_id} rating={rating}")
        return True
    except Exception as e:
        logger.error(f"Feedback error: {e}")
        return False

# ═══════════════════════════════════════
# Request logging
# ═══════════════════════════════════════

def log_request(user_id: str, goal: str, actions_count: int, success: bool, response_time_ms: int, used_template: bool = False):
    """Log a request for analytics."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO request_log (user_id, goal, actions_count, success, response_time_ms, used_quick_template) VALUES (?,?,?,?,?,?)",
            (user_id, goal[:200], actions_count, 1 if success else 0, response_time_ms, 1 if used_template else 0)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Request log error: {e}")

# ═══════════════════════════════════════
# Analytics dashboard
# ═══════════════════════════════════════

def get_analytics(days: int = 7) -> dict:
    """Get performance analytics for the last N days."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    analytics = {
        "period_days": days,
        "requests": {},
        "feedback": {},
        "performance": {},
    }
    
    try:
        conn = sqlite3.connect(str(DB_PATH))
        
        # Request stats
        row = conn.execute(
            "SELECT COUNT(*), SUM(success), AVG(response_time_ms), SUM(used_quick_template) FROM request_log WHERE created_at > ?",
            (cutoff,)
        ).fetchone()
        
        total = row[0] or 0
        success = row[1] or 0
        analytics["requests"] = {
            "total": total,
            "success": success,
            "success_rate": round(success / total * 100, 1) if total > 0 else 0,
            "avg_response_ms": round(row[2] or 0),
            "quick_template_used": row[3] or 0,
            "template_rate": round((row[3] or 0) / total * 100, 1) if total > 0 else 0,
        }
        
        # Feedback stats
        fb = conn.execute(
            "SELECT COUNT(*), AVG(rating), MIN(rating), MAX(rating) FROM feedback WHERE created_at > ?",
            (cutoff,)
        ).fetchone()
        
        analytics["feedback"] = {
            "total": fb[0] or 0,
            "avg_rating": round(fb[1] or 0, 1),
            "min_rating": fb[2],
            "max_rating": fb[3],
        }
        
        # Top commands
        cmds = conn.execute(
            "SELECT goal, COUNT(*) as cnt, AVG(success) as sr FROM request_log WHERE created_at > ? GROUP BY goal ORDER BY cnt DESC LIMIT 10",
            (cutoff,)
        ).fetchall()
        analytics["top_commands"] = [
            {"goal": r[0], "count": r[1], "success_rate": round(r[2] * 100, 1)}
            for r in cmds
        ]
        
        # Hourly distribution
        hours = conn.execute(
            "SELECT CAST(strftime('%H', created_at) AS INTEGER) as hr, COUNT(*) FROM request_log WHERE created_at > ? GROUP BY hr ORDER BY hr",
            (cutoff,)
        ).fetchall()
        analytics["hourly_distribution"] = {r[0]: r[1] for r in hours}
        
        # Per-user stats
        users = conn.execute(
            "SELECT user_id, COUNT(*), AVG(success) FROM request_log WHERE created_at > ? GROUP BY user_id",
            (cutoff,)
        ).fetchall()
        analytics["per_user"] = {
            r[0]: {"requests": r[1], "success_rate": round(r[2] * 100, 1)}
            for r in users
        }
        
        conn.close()
    except Exception as e:
        logger.error(f"Analytics error: {e}")
        analytics["error"] = str(e)
    
    return analytics

# ═══════════════════════════════════════
# Knowledge auto-sync
# ═══════════════════════════════════════

async def knowledge_sync_loop(ha_token: str = None, ha_url: str = None):
    """Periodic sync: compare knowledge.json with HA entities every 6 hours."""
    while True:
        await asyncio.sleep(6 * 3600)  # 6 hours
        try:
            if not ha_token or not ha_url:
                continue
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{ha_url}/api/states",
                    headers={"Authorization": f"Bearer {ha_token}"}
                ) as resp:
                    if resp.status == 200:
                        states = await resp.json()
                        _check_knowledge_drift(states)
        except Exception as e:
            logger.error(f"Knowledge sync error: {e}")

def _check_knowledge_drift(ha_states: list):
    """Check if knowledge.json is out of sync with HA."""
    try:
        with open(KNOWLEDGE_PATH, "r") as f:
            knowledge = json.load(f)
        
        # Get all entity_ids from aliases
        known_entities = set()
        for aliases_key, entities in knowledge.get("device_aliases", {}).items():
            known_entities.update(entities)
        
        # Get all HA entity_ids
        ha_entities = {s["entity_id"] for s in ha_states}
        
        # Find new entities not in knowledge (only important domains)
        important_domains = {"light", "climate", "cover", "media_player", "lock", "fan", "switch"}
        new_entities = []
        for eid in ha_entities - known_entities:
            domain = eid.split(".")[0]
            if domain in important_domains:
                new_entities.append(eid)
        
        # Find dead entities in knowledge but not in HA
        dead_entities = known_entities - ha_entities
        
        if new_entities or dead_entities:
            logger.warning(f"Knowledge drift: {len(new_entities)} new entities, {len(dead_entities)} dead entities")
            # Store drift info in memory for later review
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute(
                "INSERT OR REPLACE INTO memory (category, content, context, source, confidence) VALUES (?,?,?,?,?)",
                ("knowledge_drift", 
                 f"new:{len(new_entities)} dead:{len(dead_entities)}", 
                 json.dumps({"new": new_entities[:20], "dead": list(dead_entities)[:20]}),
                 "auto_sync", 0.5)
            )
            conn.commit()
            conn.close()
        else:
            logger.info("Knowledge sync: no drift detected")
    except Exception as e:
        logger.error(f"Knowledge drift check error: {e}")

# Initialize
_ensure_analytics_tables()
