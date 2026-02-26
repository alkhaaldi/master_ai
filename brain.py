"""
Master AI Brain v1.0
Intelligence layer — separate from server.py
Provides: system prompt building, entity resolution, alias matching, learning

Design principles (from ChatGPT review):
- Compact index in system prompt + targeted details in user message
- Aliases as structured array (not regex keys)
- Learning via queue + single worker (not unbounded create_task)
- Static knowledge in JSON, dynamic learning in SQLite
- Graceful fallback: if brain fails, server.py uses built-in planner
"""

import os
import json
import re
import time
import logging
import sqlite3
import asyncio
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("brain")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PATHS & STATE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BASE_DIR = Path(os.getenv("MASTER_AI_DIR", "/home/pi/master_ai"))
KNOWLEDGE_FILE = BASE_DIR / "knowledge.json"
ENTITY_MAP_FILE = BASE_DIR / "entity_map.json"
AUDIT_DB = BASE_DIR / "data" / "audit.db"

_knowledge = {}
_entity_map = {}
_entity_index = {}
_alias_cache = []
_learn_queue = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATA LOADING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _load_json(path):
    try:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {path.name}: {e}")
    return {}


def _build_entity_index(emap):
    """Build domain-based index from entity_map for fast lookup."""
    index = {}
    for room, entities in emap.items():
        for entry in entities:
            if "=" in str(entry):
                eid, name = str(entry).split("=", 1)
            else:
                eid, name = str(entry), ""
            domain = eid.split(".")[0] if "." in eid else "unknown"
            if domain not in index:
                index[domain] = []
            index[domain].append({"id": eid, "name": name, "room": room})
    return index


def _compile_aliases(knowledge):
    """Compile alias patterns from knowledge.json into regex objects."""
    aliases = []
    for alias_def in knowledge.get("device_aliases", []):
        compiled = []
        for pat in alias_def.get("patterns", []):
            try:
                compiled.append(re.compile(re.escape(pat), re.IGNORECASE))
            except Exception:
                pass
        if compiled:
            aliases.append({
                "patterns": compiled,
                "raw_patterns": alias_def.get("patterns", []),
                "entities": alias_def.get("entities", []),
                "note": alias_def.get("note", "")
            })
    return aliases


def reload():
    """Reload all data files. Called at import and can be called on demand."""
    global _knowledge, _entity_map, _entity_index, _alias_cache
    _knowledge = _load_json(KNOWLEDGE_FILE)
    _entity_map = _load_json(ENTITY_MAP_FILE)
    _entity_index = _build_entity_index(_entity_map)
    _alias_cache = _compile_aliases(_knowledge)
    total_entities = sum(len(v) for v in _entity_index.values())
    try:
        _ensure_memory_table()
        _apply_confidence_decay()
    except Exception:
        pass
    logger.info(
        f"Brain loaded: {len(_entity_map)} rooms, "
        f"{total_entities} entities, {len(_alias_cache)} alias groups"
    )


# Load on import
reload()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. ALIAS RESOLUTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def resolve_aliases(text):
    """Find all matching aliases in user text."""
    matches = []
    seen = set()
    for alias_def in _alias_cache:
        for regex in alias_def["patterns"]:
            if regex.search(text):
                key = tuple(alias_def["entities"])
                if key not in seen:
                    seen.add(key)
                    matches.append({
                        "match": regex.pattern.replace("\\", ""),
                        "entities": alias_def["entities"],
                        "note": alias_def["note"]
                    })
                break

    # Check learned aliases from DB
    learned = _get_learned_aliases(text)
    for la in learned:
        key = tuple(la["entities"])
        if key not in seen:
            seen.add(key)
            matches.append(la)

    return matches


def _get_learned_aliases(text):
    """Check SQLite for user-learned aliases."""
    try:
        if not AUDIT_DB.exists():
            return []
        conn = sqlite3.connect(str(AUDIT_DB))
        rows = conn.execute(
            "SELECT content, context FROM memory WHERE category='alias' AND active=1"
        ).fetchall()
        conn.close()
        results = []
        for content, context in rows:
            if content and content.lower() in text.lower():
                try:
                    ctx = json.loads(context) if context else {}
                    results.append({
                        "match": content,
                        "entities": ctx.get("entities", []),
                        "note": f"(learned: {content})"
                    })
                except json.JSONDecodeError:
                    pass
        return results
    except Exception:
        return []



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

def get_brain_stats():
    stats = {"brain_version": "1.1", "knowledge_loaded": bool(_knowledge),
             "aliases_compiled": len(_alias_cache), "entity_index_size": len(_entity_index)}
    try:
        conn = sqlite3.connect(str(AUDIT_DB))
        rows = conn.execute("SELECT category, COUNT(*), AVG(confidence), SUM(hit_count) "
                           "FROM memory WHERE active=1 GROUP BY category").fetchall()
        conn.close()
        stats["memory"] = {r[0]: {"count": r[1], "avg_conf": round(r[2],2), "hits": r[3] or 0} for r in rows}
        stats["total_memories"] = sum(r[1] for r in rows)
    except:
        stats["memory"] = {}; stats["total_memories"] = 0
    return stats


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. ENTITY CONTEXT — COMPACT INDEX
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_DOMAIN_ICONS = {
    "light": "💡", "climate": "🌡", "cover": "🪟",
    "fan": "🌀", "scene": "🎬", "media_player": "🔊",
    "switch": "🔌", "button": "⏺", "sensor": "📊"
}


def _build_compact_room_line(room_name, entities):
    """Build compact one-line summary: 'Room: 💡x5 🌡x1 🪟x2'."""
    types = {}
    for entry in entities:
        eid = str(entry).split("=")[0] if "=" in str(entry) else str(entry)
        domain = eid.split(".")[0] if "." in eid else "?"
        types[domain] = types.get(domain, 0) + 1
    parts = []
    for domain, count in types.items():
        if domain in ("switch", "button", "sensor", "binary_sensor", "number", "select"):
            continue
        icon = _DOMAIN_ICONS.get(domain, "•")
        parts.append(f"{icon}x{count}")
    return f"{room_name}: {' '.join(parts)}"


def build_room_index():
    """Build compact room index for system prompt (ALL rooms, no truncation)."""
    lines = []
    for room_name, entities in _entity_map.items():
        if "المشاهد" in room_name or "Scenes" in room_name:
            lines.append(f"المشاهد: {len(entities)} scene")
            continue
        lines.append(_build_compact_room_line(room_name, entities))
    return "\n".join(lines)


def _get_room_entities_for_query(text):
    """Find specific room entity IDs that match the user query (targeted details)."""
    details = []
    text_lower = text.lower()

    for room_name, entities in _entity_map.items():
        room_parts = re.split(r'[/|]', room_name)
        matched = False
        for part in room_parts:
            part_clean = part.strip().lower()
            if len(part_clean) > 1 and part_clean in text_lower:
                matched = True
                break

        if matched:
            for entry in entities:
                if "=" in str(entry):
                    eid, name = str(entry).split("=", 1)
                    details.append(f"  {eid} = {name}")
                else:
                    details.append(f"  {entry}")

    return details


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. BUILD SYSTEM PROMPT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_system_prompt():
    """Build enhanced system prompt with knowledge, compact index, rules, and device notes."""

    home = _knowledge.get("home", {})
    prefs = _knowledge.get("user_preferences", {})
    device_notes = _knowledge.get("device_notes", {})
    rules = _knowledge.get("rules", [])
    room_descs = _knowledge.get("room_descriptions", {})

    room_index = build_room_index()

    notes_lines = [f"- {d}: {n}" for d, n in device_notes.items()]
    device_notes_text = "\n".join(notes_lines)

    rules_text = "\n".join(f"- {r}" for r in rules)

    room_desc_lines = [f"- {r}: {d}" for r, d in room_descs.items()]
    room_desc_text = "\n".join(room_desc_lines)

    prompt = f"""أنت Master AI v5 — العقل المركزي لبيت {home.get('owner', 'بو خليفة')}.
{home.get('description', '')}
العائلة: {', '.join(home.get('family', []))}

Available action types:
- ha_get_state: {{entity_id}} → get HA entity state (use "*" for all)
- ha_call_service: {{domain, service, service_data}} → call HA service
- ssh_run: {{cmd}} → run shell command on Raspberry Pi
- respond_text: {{text}} → respond to user with text
- win_diagnostics: {{checks[]}} → run Windows diagnostics
- win_powershell: {{script}} → run PowerShell on Windows PC
- win_winget_install: {{package}} → install via winget
- http_request: {{url, method, headers, body}} → HTTP request
- memory_store: {{category, content, type}} → store to long-term memory

═══ بيت بو خليفة — خريطة الغرف (مختصرة) ═══
{room_index}

═══ وصف الغرف ═══
{room_desc_text}

═══ ملاحظات الأجهزة ═══
{device_notes_text}

═══ قواعد صارمة ═══
{rules_text}

═══ Lookup Hint ═══
الخريطة أعلاه مختصرة. لما تحتاج entity_id دقيق:
- شيك الـ entity IDs المرفقة بالرسالة (إذا موجودة)
- أو استخدم ha_get_state مع entity_id="*" + domain filter

You MUST respond ONLY with valid JSON (no markdown, no explanation):
{{
  "mode": "single_step" | "multi_step",
  "thought": "brief reasoning",
  "next_step": {{"type": "action_type", "args": {{...}}}},
  "plan": [list of steps if multi_step],
  "task_state": "running" | "waiting" | "complete",
  "response": "text response to user"
}}

Rules:
- For simple questions/greetings → mode: single_step, next_step: respond_text, task_state: complete
- For device control → mode: single_step or multi_step with ha_call_service actions
- For complex tasks → mode: multi_step with a plan array
- If you need more info → task_state: waiting
- Always include "response" with user-facing message in عربي كويتي
- NEVER invent entity IDs — use ONLY from entity map or aliases
- Language: {prefs.get('language', 'عربي كويتي')} — {prefs.get('tone', 'casual')}
"""
    return prompt


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. BUILD USER MESSAGE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_user_message(goal, context=None, previous_results=None):
    """Build enriched user message with aliases, targeted entity details, and context."""

    parts = [f"User request: {goal}"]

    # Alias resolution
    alias_matches = resolve_aliases(goal)
    if alias_matches:
        alias_lines = []
        for m in alias_matches:
            line = f"  [{m['match']}] → {', '.join(m['entities'])}"
            if m.get("note"):
                line += f"  ⚠️ {m['note']}"
            alias_lines.append(line)
        parts.append("═══ Resolved aliases ═══\n" + "\n".join(alias_lines))

    # Targeted entity details (only for relevant rooms)
    room_details = _get_room_entities_for_query(goal)
    if room_details and len(room_details) <= 60:
        parts.append("═══ Relevant entity IDs ═══\n" + "\n".join(room_details))

    # Device notes for relevant domains
    device_notes = _knowledge.get("device_notes", {})
    relevant_notes = []
    goal_lower = goal.lower()
    domain_keywords = {
        "media_player": ["سماعة", "بلو", "تلفزيون", "tv", "speaker", "bluesound", "alexa", "ساوند"],
        "cover": ["ستائر", "شتر", "shutter", "curtain", "ستاير"],
        "climate": ["مكيف", "حرارة", "AC", "temp", "درجة"],
        "scene": ["مشهد", "وضع", "scene", "mode", "نوم", "ضيوف", "سينما", "طفي", "صباح"],
        "light": ["نور", "لمبة", "ضوء", "سبوت", "ستريب", "ثريا", "light", "أنوار"],
        "fan": ["شفاط", "منقي", "purifier", "vent", "تنقية"]
    }
    for domain, keywords in domain_keywords.items():
        if any(kw in goal_lower for kw in keywords):
            if domain in device_notes:
                relevant_notes.append(f"⚠️ {domain}: {device_notes[domain]}")

    if relevant_notes:
        parts.append("═══ Device notes ═══\n" + "\n".join(relevant_notes))

    # Previous step results (iterative planning)
    if previous_results:
        parts.append("═══ Previous step results ═══")
        for i, pr in enumerate(previous_results[-5:]):
            parts.append(f"Step {i}: {json.dumps(pr, ensure_ascii=False)[:300]}")

    # Extra context
    if context:
        for k in ("extra", "task_context"):
            if k in context:
                parts.append(f"\n{k}: {context[k]}")
        if context.get("validation_error"):
            parts.append(f"\nvalidation_error: {context['validation_error']}")
            parts.append("Your previous response had a validation error. Fix and respond with valid JSON.")

    # Add relevant past patterns
    patterns = _get_relevant_patterns(goal)
    if patterns:
        parts.append("═══ Past patterns ═══")
        for p in patterns:
            acts = ", ".join(p.get("actions", []))
            g = p.get("goal", "?")
            h = p.get("hits", 0)
            parts.append("  [%s] -> %s (x%d)" % (g, acts, h))


    return "\n\n".join(parts)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. LEARNING (queue + single worker)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
    if not actions or all(a.get("type") == "respond_text" for a in actions):
        return

    has_errors = any(
        not r.get("success", True) for r in results if isinstance(r, dict)
    )
    has_successes = any(
        r.get("success", False) for r in results if isinstance(r, dict)
    )

    # Learn successful multi-step patterns
    if has_successes and len(actions) > 1 and LEARN_RULES["save_pattern"]:
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
                if "not found" in error_msg.lower() or "entity" in error_msg.lower():
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
