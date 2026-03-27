"""
structured_memory.py — Master AI Structured Memory System
═══════════════════════════════════════════════════════════
Replaces the flat memory_db.py with typed, searchable, decaying memory.

Types:
  - fact: Persistent truths (name, family, job, preferences)
  - event: Time-bound occurrences (meetings, purchases, trips)
  - correction: User corrections ("مو هذا — هذاك")
  (lesson merged into preference) (auto-saved when tools fail)
  - preference: How the user wants things done

Features:
  - Confidence decay (unused memories fade)
  - Dedup on insert (same category+key = update)
  - Semantic search by tags + content
  - get_context_for_llm() — feeds system prompt
  - Migration from old memory table

DB: data/structured_memory.db (separate from audit.db)
"""

import sqlite3
import json
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger("structured_memory")

# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

BASE_DIR = Path("/home/pi/master_ai")
DB_PATH = BASE_DIR / "data" / "structured_memory.db"

# Confidence decay: memories lose 0.02 per day if not accessed
DECAY_RATE = 0.02
MIN_CONFIDENCE = 0.1  # Below this = soft-deleted (active=0)

# Context limits for LLM prompt
MAX_FACTS_IN_CONTEXT = 30
MAX_EVENTS_IN_CONTEXT = 10
MAX_CORRECTIONS_IN_CONTEXT = 10
MAX_LESSONS_IN_CONTEXT = 5
MAX_PREFERENCES_IN_CONTEXT = 10


# ═══════════════════════════════════════════════════════════════════════════════
#  INIT
# ═══════════════════════════════════════════════════════════════════════════════

def _get_db() -> sqlite3.Connection:
    """Get a connection with WAL mode."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            type        TEXT NOT NULL CHECK(type IN ('fact','event','correction','preference')),
            category    TEXT NOT NULL DEFAULT 'general',
            key         TEXT NOT NULL DEFAULT '',
            content     TEXT NOT NULL,
            content_ar  TEXT DEFAULT '',
            tags        TEXT DEFAULT '',
            confidence  REAL NOT NULL DEFAULT 0.8,
            source      TEXT NOT NULL DEFAULT 'user',
            expires_at  TEXT DEFAULT NULL,
            use_count   INTEGER DEFAULT 0,
            last_used   TEXT DEFAULT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
            active      INTEGER DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_mem_type ON memories(type, active);
        CREATE INDEX IF NOT EXISTS idx_mem_category ON memories(category, active);
        CREATE INDEX IF NOT EXISTS idx_mem_key ON memories(type, category, key);
        CREATE INDEX IF NOT EXISTS idx_mem_tags ON memories(tags);

        -- Migration tracking
        CREATE TABLE IF NOT EXISTS migration_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source      TEXT NOT NULL,
            records     INTEGER DEFAULT 0,
            done_at     TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()
    log.info(f"✅ Structured Memory DB ready at {DB_PATH}")


# ═══════════════════════════════════════════════════════════════════════════════
#  CORE CRUD
# ═══════════════════════════════════════════════════════════════════════════════

def save_fact(content: str, category: str = "general", key: str = "",
              tags: str = "", confidence: float = 0.9, source: str = "user",
              content_ar: str = "") -> dict:
    """Save or update a fact. If same category+key exists, update it."""
    return _upsert("fact", category, key, content, content_ar, tags, confidence, source)


def save_event(content: str, category: str = "general", key: str = "",
               tags: str = "", confidence: float = 0.85, source: str = "user",
               content_ar: str = "", expires_at: str = None) -> dict:
    """Save a time-bound event."""
    return _upsert("event", category, key, content, content_ar, tags, confidence, source, expires_at)


def save_correction(content: str, category: str = "general", key: str = "",
                    tags: str = "", source: str = "user",
                    content_ar: str = "") -> dict:
    """Save a user correction (highest priority in context)."""
    return _upsert("correction", category, key, content, content_ar, tags, 0.95, source)


def save_lesson(content: str, category: str = "general", key: str = "",
                tags: str = "", source: str = "auto",
                content_ar: str = "") -> dict:
    """Save a lesson learned from an error."""
    return _upsert("preference", category, key, content, content_ar, tags, 0.8, source)


def save_preference(content: str, category: str = "general", key: str = "",
                    tags: str = "", source: str = "user",
                    content_ar: str = "") -> dict:
    """Save a user preference."""
    return _upsert("preference", category, key, content, content_ar, tags, 0.9, source)


def _upsert(type_: str, category: str, key: str, content: str,
            content_ar: str, tags: str, confidence: float, source: str,
            expires_at: str = None) -> dict:
    """Insert or update (dedup by type+category+key if key is non-empty)."""
    conn = _get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if key:
        # Check for existing
        row = conn.execute(
            "SELECT id, content, confidence FROM memories WHERE type=? AND category=? AND key=? AND active=1",
            (type_, category, key)
        ).fetchone()
        if row:
            # Update existing
            new_conf = min(1.0, max(confidence, row["confidence"]))
            conn.execute(
                """UPDATE memories SET content=?, content_ar=?, tags=?, confidence=?,
                   source=?, expires_at=?, updated_at=?, use_count=use_count+1, last_used=?
                   WHERE id=?""",
                (content, content_ar, tags, new_conf, source, expires_at, now, now, row["id"])
            )
            conn.commit()
            conn.close()
            log.info(f"📝 Updated {type_}/{category}/{key}: {content[:60]}")
            return {"action": "updated", "id": row["id"], "type": type_, "key": key}

    # Insert new
    cursor = conn.execute(
        """INSERT INTO memories (type, category, key, content, content_ar, tags,
           confidence, source, expires_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (type_, category, key, content, content_ar, tags, confidence, source,
         expires_at, now, now)
    )
    conn.commit()
    mid = cursor.lastrowid
    conn.close()
    log.info(f"💾 Saved {type_}/{category}/{key or mid}: {content[:60]}")
    return {"action": "created", "id": mid, "type": type_, "key": key}


# ═══════════════════════════════════════════════════════════════════════════════
#  QUERY
# ═══════════════════════════════════════════════════════════════════════════════

def get_memories(type_: str = None, category: str = None, 
                 min_confidence: float = 0.2, limit: int = 50,
                 search: str = None) -> list[dict]:
    """Retrieve memories with optional filters."""
    conn = _get_db()
    conditions = ["active = 1", "confidence >= ?"]
    params: list = [min_confidence]

    if type_:
        conditions.append("type = ?")
        params.append(type_)
    if category:
        conditions.append("category = ?")
        params.append(category)
    if search:
        conditions.append("(content LIKE ? OR content_ar LIKE ? OR tags LIKE ? OR key LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like, like])

    sql = f"""SELECT * FROM memories WHERE {' AND '.join(conditions)}
              ORDER BY confidence DESC, updated_at DESC LIMIT ?"""
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_by_id(memory_id: int) -> Optional[dict]:
    """Get a single memory by ID."""
    conn = _get_db()
    row = conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def touch(memory_id: int):
    """Mark a memory as used (resets decay)."""
    conn = _get_db()
    conn.execute(
        "UPDATE memories SET use_count=use_count+1, last_used=datetime('now'), updated_at=datetime('now') WHERE id=?",
        (memory_id,)
    )
    conn.commit()
    conn.close()


def delete_memory(memory_id: int) -> bool:
    """Soft-delete a memory."""
    conn = _get_db()
    conn.execute("UPDATE memories SET active=0, updated_at=datetime('now') WHERE id=?", (memory_id,))
    conn.commit()
    conn.close()
    return True


def hard_delete(memory_id: int) -> bool:
    """Permanently delete a memory."""
    conn = _get_db()
    conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
    conn.commit()
    conn.close()
    return True


# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIDENCE DECAY
# ═══════════════════════════════════════════════════════════════════════════════

def apply_decay():
    """Run daily: reduce confidence of unused memories, deactivate dead ones."""
    conn = _get_db()

    # Decay memories not used in the last 24 hours
    cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    
    # Don't decay high-confidence facts from 'seed' or 'user' source
    conn.execute(
        """UPDATE memories SET confidence = MAX(?, confidence - ?)
           WHERE active = 1 
           AND (last_used IS NULL OR last_used < ?)
           AND NOT (type = 'fact' AND source IN ('seed', 'user') AND confidence >= 0.85)""",
        (MIN_CONFIDENCE, DECAY_RATE, cutoff)
    )

    # Deactivate memories below threshold (except corrections — never auto-delete)
    conn.execute(
        """UPDATE memories SET active = 0
           WHERE active = 1 AND confidence < ? AND type != 'correction'""",
        (MIN_CONFIDENCE,)
    )

    # Expire time-bound events
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE memories SET active = 0 WHERE active = 1 AND expires_at IS NOT NULL AND expires_at < ?",
        (now,)
    )

    affected = conn.execute("SELECT changes()").fetchone()[0]
    conn.commit()
    conn.close()
    if affected > 0:
        log.info(f"🔄 Decay: {affected} memories updated/deactivated")
    return affected


# ═══════════════════════════════════════════════════════════════════════════════
#  CONTEXT FOR LLM
# ═══════════════════════════════════════════════════════════════════════════════

def get_context_for_llm(query: str = "") -> str:
    """Build a compact memory context string for the LLM system prompt.
    
    Priority order:
    1. Corrections (highest — user said "مو هذا")
    2. Preferences (how user wants things)
    3. Facts (who/what/where)
    4. Recent events
    5. Lessons (learned from errors)
    
    If query is provided, boost memories whose content/tags match.
    """
    conn = _get_db()
    sections = []

    # 1. Corrections — ALWAYS included
    corrections = conn.execute(
        """SELECT content FROM memories 
           WHERE type='correction' AND active=1 
           ORDER BY updated_at DESC LIMIT ?""",
        (MAX_CORRECTIONS_IN_CONTEXT,)
    ).fetchall()
    if corrections:
        lines = [f"- {r['content']}" for r in corrections]
        sections.append("⚠️ تصحيحات مهمة:\n" + "\n".join(lines))

    # 2. Preferences
    preferences = conn.execute(
        """SELECT content FROM memories 
           WHERE type='preference' AND active=1 AND confidence >= 0.5
           ORDER BY confidence DESC, updated_at DESC LIMIT ?""",
        (MAX_PREFERENCES_IN_CONTEXT,)
    ).fetchall()
    if preferences:
        lines = [f"- {r['content']}" for r in preferences]
        sections.append("تفضيلات المستخدم:\n" + "\n".join(lines))

    # 3. Facts — split by category for readability
    facts = conn.execute(
        """SELECT category, key, content FROM memories 
           WHERE type='fact' AND active=1 AND confidence >= 0.4
           ORDER BY confidence DESC, updated_at DESC LIMIT ?""",
        (MAX_FACTS_IN_CONTEXT,)
    ).fetchall()
    if facts:
        by_cat = {}
        for r in facts:
            cat = r["category"] or "general"
            by_cat.setdefault(cat, []).append(r["content"])
        parts = []
        for cat, items in by_cat.items():
            cat_label = {
                "personal": "👤 شخصي",
                "family": "👨‍👩‍👦 العائلة",
                "work": "🏭 العمل",
                "ha": "🏠 البيت الذكي",
                "trading": "📈 التداول",
                "network": "🌐 الشبكة",
                "general": "📋 عام",
            }.get(cat, f"📂 {cat}")
            parts.append(f"{cat_label}: " + " | ".join(items))
        sections.append("حقائق:\n" + "\n".join(parts))

    # 4. Recent events (last 30 days)
    events = conn.execute(
        """SELECT content, created_at FROM memories 
           WHERE type='event' AND active=1 AND confidence >= 0.4
           AND created_at >= datetime('now', '-30 days')
           ORDER BY created_at DESC LIMIT ?""",
        (MAX_EVENTS_IN_CONTEXT,)
    ).fetchall()
    if events:
        lines = [f"- {r['content']}" for r in events]
        sections.append("أحداث أخيرة:\n" + "\n".join(lines))

    # 5. Lessons
    lessons = conn.execute(
        """SELECT content FROM memories 
           WHERE type='preference' AND category IN ('pattern','tool_error','insight','error_pattern') AND active=1 AND confidence >= 0.5
           ORDER BY confidence DESC, updated_at DESC LIMIT ?""",
        (MAX_LESSONS_IN_CONTEXT,)
    ).fetchall()
    if lessons:
        lines = [f"- {r['content']}" for r in lessons]
        sections.append("دروس مستفادة:\n" + "\n".join(lines))

    conn.close()

    # Query-based boosting: reorder sections if query matches
    if query:
        query_lower = query.lower()
        # Simple keyword boost — move matching sections up
        boosted = []
        rest = []
        for s in sections:
            if any(kw in s.lower() for kw in query_lower.split()):
                boosted.append(s)
            else:
                rest.append(s)
        sections = boosted + rest

    if not sections:
        return ""

    return "═══ ذاكرة المستخدم ═══\n" + "\n\n".join(sections)


def get_stats() -> dict:
    """Memory statistics."""
    conn = _get_db()
    stats = {}
    
    total = conn.execute("SELECT COUNT(*) as c FROM memories WHERE active=1").fetchone()
    stats["total_active"] = total["c"]
    
    by_type = conn.execute(
        "SELECT type, COUNT(*) as c FROM memories WHERE active=1 GROUP BY type"
    ).fetchall()
    stats["by_type"] = {r["type"]: r["c"] for r in by_type}
    
    by_cat = conn.execute(
        "SELECT category, COUNT(*) as c FROM memories WHERE active=1 GROUP BY category ORDER BY c DESC"
    ).fetchall()
    stats["by_category"] = {r["category"]: r["c"] for r in by_cat}
    
    avg_conf = conn.execute(
        "SELECT AVG(confidence) as avg_c FROM memories WHERE active=1"
    ).fetchone()
    stats["avg_confidence"] = round(avg_conf["avg_c"] or 0, 3)
    
    inactive = conn.execute("SELECT COUNT(*) as c FROM memories WHERE active=0").fetchone()
    stats["total_inactive"] = inactive["c"]
    
    conn.close()
    return stats


# ═══════════════════════════════════════════════════════════════════════════════
#  MIGRATION FROM OLD MEMORY
# ═══════════════════════════════════════════════════════════════════════════════

def migrate_from_old_db(old_db_path: str = None) -> dict:
    """Migrate memories from the old memory table in audit.db.
    
    Old schema: memory(id, category, type, content, context, confidence,
                       source, tags, last_used, use_count, created_at, updated_at, active)
    """
    if old_db_path is None:
        old_db_path = str(BASE_DIR / "data" / "audit.db")
    
    if not Path(old_db_path).exists():
        return {"error": "Old DB not found", "path": old_db_path}
    
    old_conn = sqlite3.connect(old_db_path)
    old_conn.row_factory = sqlite3.Row
    
    # Check if old memory table exists
    table_check = old_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='memory'"
    ).fetchone()
    if not table_check:
        old_conn.close()
        return {"error": "No 'memory' table in old DB"}
    
    rows = old_conn.execute("SELECT * FROM memory WHERE active=1").fetchall()
    old_conn.close()
    
    migrated = 0
    skipped = 0
    for r in rows:
        old_type = r["type"] if "type" in r.keys() else "fact"
        # Map old types to new types
        type_map = {
            "fact": "fact",
            "pattern": "preference",
            "preference": "preference",
            "event": "event",
            "relation": "fact",
            "insight": "preference",
        }
        new_type = type_map.get(old_type, "fact")
        
        try:
            _upsert(
                type_=new_type,
                category=r["category"] if "category" in r.keys() else "general",
                key="",  # Old DB didn't have keys
                content=r["content"],
                content_ar="",
                tags=r["tags"] if "tags" in r.keys() else "",
                confidence=r["confidence"] if "confidence" in r.keys() else 0.7,
                source="migrated",
            )
            migrated += 1
        except Exception as e:
            log.warning(f"Migration skip: {e}")
            skipped += 1
    
    # Log migration
    conn = _get_db()
    conn.execute(
        "INSERT INTO migration_log (source, records) VALUES (?, ?)",
        (old_db_path, migrated)
    )
    conn.commit()
    conn.close()
    
    result = {"migrated": migrated, "skipped": skipped, "source": old_db_path}
    log.info(f"📦 Migration: {result}")
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  SEED INITIAL FACTS
# ═══════════════════════════════════════════════════════════════════════════════

def seed_initial():
    """Seed essential facts about بو خليفة. Safe to run multiple times (upsert)."""
    seeds = [
        # Personal
        ("fact", "personal", "name", "اسمه سالم (بو خليفة)", "identity,name"),
        ("fact", "personal", "name_full", "سالم الخالدي — Unit Controller Shift A, Unit 114 Hydrocracker, KNPC MAB Area 8", "identity,work"),
        ("fact", "family", "wife", "زوجته Oana (رومانية)", "family,wife"),
        ("fact", "family", "son", "عنده ولد اسمه عبود (خليفة)", "family,son"),
        ("fact", "family", "mother", "أمه ناهد (أم سالم) — تسكن بالبيت، عندها داشبورد mama-room", "family,mother"),
        
        # Work
        ("fact", "work", "shift", "شفتات: AABBCCDD (صباحي/عصري/ليلي/إجازة)، Epoch=2024-01-04", "work,shift"),
        ("fact", "work", "email", "إيميل العمل: SKK022@knpc.com / sk.khaledi@knpc.com", "work,email"),
        ("fact", "work", "colleagues", "زملاء 114: A=سالم, B=خالد العنزي+يوسف الجلاهمة, C=جابر العازمي+طلال الفضلي, D=فواز العتيبي+عيسى المطوع", "work,colleagues"),
        
        # Home
        ("fact", "ha", "system", "Home Assistant على RPi5 @ 192.168.109.123:8123 مع Nabu Casa", "ha,system"),
        ("fact", "ha", "entities", "~210 entity, 8 tabs, 17 scene, 28 غرفة بـ entity_map.json", "ha,dashboard"),
        ("fact", "ha", "speakers", "4 سماعات Bluesound عبر Music Assistant فقط — native entities معطلة", "ha,audio"),
        ("fact", "ha", "cameras", "6 Dahua عبر NVR + 4 Tapo C120 — go2rtc 9 كاميرات", "ha,cameras"),
        ("fact", "ha", "covers", "الستائر تستخدم _inverted templates فقط", "ha,covers"),
        ("fact", "ha", "ac_guard", "حارس حرارة: حد أقصى 23° على 7 مكيفات، 5 دقائق delay", "ha,climate"),
        
        # Network
        ("fact", "network", "topology", "BE800(108.1) → ES226GC-P → 9 RAP → RPi(109.123)", "network,topology"),
        ("fact", "network", "nvr", "NVR @ 192.168.108.44 (admin/Loverazan12)", "network,nvr"),
        
        # Trading
        ("fact", "trading", "platform", "يتداول ببورصة الكويت — TradingIQ Premium $49/شهر", "trading,platform"),
        ("fact", "trading", "positions", "CLEANING @153 (تجميع مؤسسي)، SENERGY @111 (هدف 140-180)", "trading,stocks"),
        ("fact", "trading", "strategies", "CLEANING V3 (SSA+VWAP+Trail=117%), SENERGY V5 (HH+HL+RSI=104%), INOVEST V5 (HMA-Kahlman+Trail)", "trading,strategies"),
        
        # Preferences
        ("preference", "general", "language", "يفضل الكويتي — لما يخلط عربي مع إنجليزي، الإنجليزي بسطر منفصل", "language,format"),
        ("preference", "general", "code", "يبي كود بس بدون HTML — البسيط أفضل من المعقد", "code,preference"),
        ("preference", "general", "execution", "يفضل التنفيذ المباشر بدون شرح طويل أو إعادة سؤال", "execution,preference"),
        ("preference", "ha", "fan_names", "شفاطات (vent) ≠ منقيات هواء (purifier) ≠ معطرات (freshener) — لا تقول مراوح!", "ha,naming"),
        ("preference", "ha", "ac_temp", "حرارة المكيف لا تتجاوز 23 درجة", "ha,climate"),
    ]
    
    count = 0
    for type_, cat, key, content, tags in seeds:
        if type_ == "fact":
            save_fact(content, cat, key, tags, 0.95, "seed")
        elif type_ == "preference":
            save_preference(content, cat, key, tags, "seed")
        count += 1
    
    log.info(f"🌱 Seeded {count} initial memories")
    return {"seeded": count}


# ═══════════════════════════════════════════════════════════════════════════════
#  CHAT TOOLS — for chat_v7.py
# ═══════════════════════════════════════════════════════════════════════════════

# Tool definitions for Anthropic tool_use
MEMORY_TOOLS = [
    {
        "name": "memory_save_fact",
        "description": "Save a new fact about user/home/work when user shares important info",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The fact in Arabic"},
                "category": {"type": "string", "description": "personal|family|work|ha|trading|network|general", "default": "general"},
                "key": {"type": "string", "description": "Unique key for upsert", "default": ""},
                "tags": {"type": "string", "description": "Comma-separated keywords", "default": ""},
            },
            "required": ["content"]
        }
    },
    {
        "name": "memory_save_event",
        "description": "Save a temporary event (meeting, purchase, travel). Events auto-expire.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Event description in Arabic"},
                "category": {"type": "string", "description": "personal|family|work|ha|trading|network|general", "default": "general"},
                "tags": {"type": "string", "description": "Comma-separated keywords", "default": ""},
                "expires_at": {"type": "string", "description": "Expiry YYYY-MM-DD (optional)", "default": ""},
            },
            "required": ["content"]
        }
    },
    {
        "name": "memory_save_correction",
        "description": "Save user correction (highest priority). Use when user says 'no' or 'wrong'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Correction in Arabic"},
                "category": {"type": "string", "description": "Category", "default": "general"},
                "key": {"type": "string", "description": "Unique key", "default": ""},
                "tags": {"type": "string", "description": "Keywords", "default": ""},
            },
            "required": ["content"]
        }
    },
    {
        "name": "structured_memory_search",
        "description": "Search structured memory for facts, events, corrections",
        "input_schema": {
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "Search query"},
                "category": {"type": "string", "description": "Filter by category", "default": ""},
                "type": {"type": "string", "description": "Filter: fact|event|correction|preference", "default": ""},
            },
            "required": ["search"]
        }
    },
]


def execute_memory_tool(tool_name: str, params: dict) -> dict:
    """Execute a memory tool call from chat_v7. Returns result dict."""
    try:
        if tool_name == "memory_save_fact":
            return save_fact(
                content=params["content"],
                category=params.get("category", "general"),
                key=params.get("key", ""),
                tags=params.get("tags", ""),
            )
        elif tool_name == "memory_save_event":
            return save_event(
                content=params["content"],
                category=params.get("category", "general"),
                key=params.get("key", ""),
                tags=params.get("tags", ""),
                expires_at=params.get("expires_at") or None,
            )
        elif tool_name == "memory_save_correction":
            return save_correction(
                content=params["content"],
                category=params.get("category", "general"),
                key=params.get("key", ""),
                tags=params.get("tags", ""),
            )
        elif tool_name in ("memory_search", "structured_memory_search"):
            results = get_memories(
                type_=params.get("type") or None,
                search=params["search"],
                limit=10,
            )
            return {"results": results, "count": len(results)}
        else:
            return {"error": f"Unknown memory tool: {tool_name}"}
    except Exception as e:
        log.error(f"Memory tool error: {tool_name} — {e}")
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
#  MODULE INIT
# ═══════════════════════════════════════════════════════════════════════════════

# Auto-init on import
try:
    init_db()
except Exception as e:
    log.error(f"❌ Structured Memory init failed: {e}")
