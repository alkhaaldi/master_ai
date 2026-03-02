"""
Master AI Brain Core v1.1
Knowledge, aliases, entity resolution, system prompt, user message
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

_DOMAIN_ICONS = {
    "light": "💡", "climate": "🌡", "cover": "🪟",
    "fan": "🌀", "scene": "🎬", "media_player": "🔊",
    "switch": "🔌", "button": "⏺", "sensor": "📊"
}


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
    """Build compact one-line summary with key entity IDs for climate/cover."""
    types = {}
    key_ids = []  # climate + cover entity IDs shown explicitly
    for entry in entities:
        eid = str(entry).split("=")[0].strip() if "=" in str(entry) else str(entry).strip()
        domain = eid.split(".")[0] if "." in eid else "?"
        types[domain] = types.get(domain, 0) + 1
        if domain in ("climate", "cover"):
            key_ids.append(eid)
    parts = []
    for domain, count in types.items():
        if domain in ("switch", "button", "sensor", "binary_sensor", "number", "select"):
            continue
        icon = _DOMAIN_ICONS.get(domain, "•")
        parts.append(f"{icon}x{count}")
    line = f"{room_name}: {' '.join(parts)}"
    if key_ids:
        line += " [" + ",".join(key_ids) + "]"
    return line



def build_room_index():
    """Build compact room index for system prompt (ALL rooms, no truncation)."""
    lines = []
    for room_name, entities in _entity_map.items():
        if "المشاهد" in room_name or "Scenes" in room_name:
            lines.append(f"المشاهد: {len(entities)} scene")
            continue
        lines.append(_build_compact_room_line(room_name, entities))
    return "\n".join(lines)


# Room name aliases: maps common Arabic names to entity_map keys
_ROOM_ALIASES = {
    "غرفة النوم": "الماستر",
    "غرفة نوم": "الماستر",
    "النوم": "الماستر",
    "bedroom": "master",
    "غرفتي": "الماستر",
    "الصالة": "المعيشة",
    "صالة": "المعيشة",
    "living": "living",
    "الحوش": "الخارجي",
    "برا": "الخارجي",
    "outside": "outdoor",
    "الأكل": "الطعام",
    "dining": "الطعام",
    "غرفة أمي": "ماما",
    "أم سالم": "ماما",
    "الشغالة": "الخادمة",
    "maid": "الخادمة",
}

def _get_room_entities_for_query(text):
    """Find specific room entity IDs that match the user query (targeted details)."""
    details = []
    text_lower = text.lower()
    expanded = text_lower
    for alias, canonical in _ROOM_ALIASES.items():
        if alias in text_lower:
            expanded = expanded + " " + canonical.lower()
    for room_name, entities in _entity_map.items():
        room_parts = re.split(r'[/|]', room_name)
        matched = False
        for part in room_parts:
            part_clean = part.strip().lower()
            if len(part_clean) > 1:
                # Match: full part in expanded, or any significant word from part in expanded
                if part_clean in expanded:
                    matched = True
                else:
                    # Skip generic words that match too broadly
                    _GENERIC = {"غرفة", "حمام", "صالة", "ممر", "باب", "نافذة", "room", "hall"}
                    words = [w for w in part_clean.split() if len(w) > 2 and w not in _GENERIC]
                    if words and any(w in expanded for w in words):
                        matched = True
            if matched:
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OWNER LIFE CONTEXT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_SHIFT_EPOCH = datetime(2024, 1, 4)
_SHIFT_PATTERN = ["A", "A", "B", "B", "C", "C", "D", "D"]

def get_owner_context() -> str:
    """Build real-time life context for the system prompt.
    
    This is the KEY to making Opus a true personal assistant.
    Instead of hardcoding behaviors, we give Opus the CONTEXT
    and let it figure out the right behavior itself.
    
    Shift pattern AABBCCDD (epoch 2024-01-04):
      A = morning shift (7:00-15:00)
      B = afternoon shift (15:00-23:00)  
      C = night shift (23:00-07:00)
      D = day off
    """
    now = datetime.now()
    hour = now.hour
    day_name = ["الاثنين", "الثلاثاء", "الاربعاء", "الخميس", "الجمعة", "السبت", "الاحد"][now.weekday()]
    days_since = (now - _SHIFT_EPOCH).days
    shift = _SHIFT_PATTERN[days_since % len(_SHIFT_PATTERN)]
    
    # Tomorrow's shift
    tmrw_shift = _SHIFT_PATTERN[(days_since + 1) % len(_SHIFT_PATTERN)]
    shift_names = {"A": "صباحي", "B": "عصري", "C": "ليلي", "D": "إجازة"}
    
    # Location + status based on shift and hour
    if shift == "A":
        if 7 <= hour < 15:
            location = "بالدوام"
            status = "مشغول"
        elif hour < 7:
            location = "بالبيت"
            status = "يستعد للدوام"
        else:
            location = "بالبيت"
            status = "راجع من الدوام"
    elif shift == "B":
        if 15 <= hour < 23:
            location = "بالدوام"
            status = "مشغول"
        elif hour < 15:
            location = "بالبيت"
            status = "فاضي الصبح"
        else:
            location = "بالبيت"
            status = "راجع متأخر"
    elif shift == "C":
        if 23 <= hour or hour < 7:
            location = "بالدوام"
            status = "مشغول"
        elif 7 <= hour < 14:
            location = "بالبيت"
            status = "نايم (راجع من الليل)"
        else:
            location = "بالبيت"
            status = "يستعد للدوام"
    else:  # D = off
        location = "بالبيت"
        status = "إجازة"
    
    return (
        f"الوقت: {day_name} {now.strftime('%H:%M')} | "
        f"الشفت: {shift_names[shift]} | "
        f"باكر: {shift_names[tmrw_shift]} | "
        f"{location} | {status}"
    )


def build_system_prompt():
    """Build system prompt: context-rich, behavior-minimal.
    
    Philosophy: Don't program behaviors. Give Opus the full context
    of bu-khalifa's life and let it figure out the right action.
    Opus is a personal life assistant, not a home automation bot.
    """
    home = _knowledge.get("home", {})
    room_index = build_room_index()
    owner_ctx = get_owner_context()

    owner = home.get("owner", "بو خليفة")

    prompt = f"""{owner_ctx}

أنت المساعد الشخصي لـ{owner} — Unit Controller, Shift A, KNPC MAB. عربي كويتي.
دورك مو بس بيت ذكي — أنت تنفّذ كل شي: منزل/تداول/مواعيد/تخطيط/مشتريات/ايميلات.
استخدم سياق الشفت والوقت عشان تفهم وينه ومزاجه بدون ما يشرحلك.

Tools: ha_get_state, ha_call_service, ssh_run, respond_text, http_request, memory_store, win_diagnostics, win_powershell, win_winget_install
الستائر inverted: open=مسكرة, closed=مفتوحة. entity_id: exact ID أو pattern مثل "climate.*" أو "sensor.*temp*" أو "*" للكل. استخدم exact IDs من Room Index أولاً.

{room_index}

JSON: {{"mode":"single_step|multi_step","thought":"","next_step":{{"type":"","args":{{}}}},"task_state":"running|waiting|complete","response":""}}
"""
    return prompt



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MEMORY INTEGRATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_AUDIT_DB = os.path.join(os.path.dirname(__file__), "data", "audit.db")

def get_relevant_memories(query: str, limit: int = 5) -> str:
    """Retrieve relevant memories. Uses keyword + category matching."""
    try:
        conn = sqlite3.connect(_AUDIT_DB, timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, category, type, content, confidence "
            "FROM memory WHERE active=1 ORDER BY confidence DESC LIMIT 50"
        ).fetchall()
        conn.close()
        if not rows:
            return ""
        CAT_MAP = {
            "أسهم": "trading", "سهم": "trading", "تداول": "trading",
            "بورصة": "trading", "cleaning": "trading", "senergy": "trading",
            "محفظة": "trading", "بيت": "ha", "مكيف": "ha", "أنوار": "ha",
            "ستائر": "ha", "سماعة": "ha", "شغل": "personal",
            "دوام": "personal", "شفت": "personal", "knpc": "personal", "عمل": "personal", "باجر": "personal", "عايلة": "personal",
        }
        ql = query.lower()
        qw = set(ql.split())
        target_cats = set()
        for kw, cat in CAT_MAP.items():
            if kw in ql:
                target_cats.add(cat)
        scored = []
        for r in rows:
            cl = r["content"].lower()
            sc = sum(2 for w in qw if len(w) > 1 and w in cl)
            if r["category"] in target_cats:
                sc += 5
            if r["confidence"] >= 0.9 and r["category"] in ("personal", "preference"):
                sc += 1
            if sc > 0:
                scored.append((sc, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:limit]
        if not top:
            return ""
        # Track hits on retrieved memories
        try:
            conn2 = sqlite3.connect(_AUDIT_DB, timeout=3)
            for _, r in top:
                conn2.execute(
                    "UPDATE memory SET hit_count=COALESCE(hit_count,0)+1, "
                    "hits=COALESCE(hits,0)+1, last_used=datetime('now') WHERE id=?",
                    (r["id"],)
                )
            conn2.commit()
            conn2.close()
        except Exception:
            pass

        lines = []
        for _, r in top:
            lines.append("[" + r["category"] + "/" + r["type"] + "] " + r["content"])
        return chr(10).join(lines)
    except Exception as e:
        return "(memory error: " + str(e) + ")"


def save_conversation(role: str, content: str, channel: str = "telegram"):
    """Save a conversation message to DB for history."""
    try:
        conn = sqlite3.connect(_AUDIT_DB, timeout=5)
        conn.execute(
            "INSERT INTO conversations (channel, role, content, timestamp) VALUES (?, ?, ?, datetime('now'))",
            (channel, role, content[:2000])
        )
        conn.commit()
        conn.close()
    except:
        pass


def auto_learn(query: str, response: str, actions: list = None):
    """Extract and save learnings from a completed interaction.
    
    Simple rule-based extraction (no LLM needed):
    - If user corrects something -> save as pattern
    - If user teaches an alias -> save as alias  
    - Track frequently asked domains
    """
    query_lower = query.lower()
    
    try:
        conn = sqlite3.connect(_AUDIT_DB, timeout=5)
        
        # Track: save every interaction summary for pattern analysis
        conn.execute(
            "INSERT INTO conversations (channel, role, content, timestamp) VALUES (?, ?, ?, datetime('now'))",
            ("auto_learn", "system", 
             json.dumps({"q": query[:200], "r": response[:200], "actions": len(actions or [])}, ensure_ascii=False),
            )
        )
        conn.commit()
        conn.close()
    except:
        pass


def build_user_message(goal, context=None, previous_results=None):
    """Build enriched user message with aliases, targeted entity details, and context."""

    parts = [f"User request: {goal}"]

    # Memory context — let Opus learn from past interactions
    mem_ctx = get_relevant_memories(goal)
    if mem_ctx:
        parts.append("═══ Memory context ═══\n" + mem_ctx)

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
    try:
        from brain_learning import _get_relevant_patterns
        patterns = _get_relevant_patterns(goal)
    except Exception:
        patterns = []
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
