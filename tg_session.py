"""Telegram Session Manager — Conversation Intelligence Layer."""
import json, sqlite3, time, uuid, logging, os
from datetime import datetime, timedelta

logger = logging.getLogger("tg_session")

AUDIT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "audit.db")
SESSION_TTL_MIN = 45
MAX_CONTEXT = 5

# --- Schema ---
_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS tg_sessions (
    user_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    last_intent TEXT DEFAULT '',
    last_room TEXT DEFAULT '',
    last_entities TEXT DEFAULT '[]',
    last_query TEXT DEFAULT '',
    context_window TEXT DEFAULT '[]',
    updated_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
)
"""

def _ensure_table():
    try:
        conn = sqlite3.connect(AUDIT_DB)
        conn.execute(_CREATE_TABLE)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"tg_sessions table creation failed: {e}")

_ensure_table()


def _now_iso():
    return datetime.now().isoformat()

def _expiry_iso():
    return (datetime.now() + timedelta(minutes=SESSION_TTL_MIN)).isoformat()


def tg_session_get(user_id: str) -> dict:
    try:
        conn = sqlite3.connect(AUDIT_DB)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tg_sessions WHERE user_id = ?", (str(user_id),)).fetchone()
        conn.close()
        if not row:
            return None
        d = dict(row)
        if d.get("expires_at", "") < _now_iso():
            tg_session_reset(user_id)
            return None
        d["last_entities"] = json.loads(d.get("last_entities", "[]"))
        d["context_window"] = json.loads(d.get("context_window", "[]"))
        return d
    except Exception as e:
        logger.error(f"session_get error: {e}")
        return None


def tg_session_upsert(user_id: str, **fields):
    try:
        existing = tg_session_get(user_id)
        now = _now_iso()
        exp = _expiry_iso()
        if not existing:
            sid = str(uuid.uuid4())[:8]
            conn = sqlite3.connect(AUDIT_DB)
            conn.execute(
                "INSERT INTO tg_sessions (user_id, session_id, last_intent, last_room, last_entities, last_query, context_window, updated_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (str(user_id), sid,
                 fields.get("last_intent", ""),
                 fields.get("last_room", ""),
                 json.dumps(fields.get("last_entities", []), ensure_ascii=False),
                 fields.get("last_query", ""),
                 json.dumps(fields.get("context_window", []), ensure_ascii=False),
                 now, exp))
            conn.commit()
            conn.close()
            return sid
        else:
            sets = ["updated_at = ?", "expires_at = ?"]
            vals = [now, exp]
            for k in ("last_intent", "last_room", "last_query"):
                if k in fields:
                    sets.append(f"{k} = ?")
                    vals.append(fields[k])
            for k in ("last_entities", "context_window"):
                if k in fields:
                    sets.append(f"{k} = ?")
                    vals.append(json.dumps(fields[k], ensure_ascii=False))
            vals.append(str(user_id))
            conn = sqlite3.connect(AUDIT_DB)
            conn.execute(f"UPDATE tg_sessions SET {', '.join(sets)} WHERE user_id = ?", vals)
            conn.commit()
            conn.close()
            return existing["session_id"]
    except Exception as e:
        logger.error(f"session_upsert error: {e}")
        return None


def tg_session_append_context(user_id: str, role: str, text: str):
    try:
        sess = tg_session_get(user_id)
        ctx = sess["context_window"] if sess else []
        short = text[:200]
        ctx.append({"role": role, "text": short, "ts": _now_iso()})
        if len(ctx) > MAX_CONTEXT:
            ctx = ctx[-MAX_CONTEXT:]
        tg_session_upsert(user_id, context_window=ctx)
    except Exception as e:
        logger.error(f"session_append error: {e}")


def tg_session_reset(user_id: str):
    try:
        conn = sqlite3.connect(AUDIT_DB)
        conn.execute("DELETE FROM tg_sessions WHERE user_id = ?", (str(user_id),))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"session_reset error: {e}")
        return False


# --- Follow-up Detection v2 ---
import re as _re

FOLLOWUP_PRONOUNS = {
    "هذا", "هذي", "هاذا", "ذا",
    "الأول", "الثاني", "الثالث",
    "اول", "ثاني", "ثالث",
    "نفسه", "نفسها",
}

# Verbs with action mapping
VERB_ACTION_MAP = {
    # on
    "شغل": "on", "شغله": "on", "شغلها": "on", "شغلهم": "on",
    "افتح": "on", "افتحه": "on", "افتحها": "on",
    # off
    "طفي": "off", "طف": "off", "طفيه": "off", "طفيها": "off", "طفيهم": "off",
    "سكر": "off", "سكره": "off", "سكرها": "off",
    "وقف": "off", "وقفه": "off", "وقفها": "off",
    # increase/decrease
    "زيد": "increase", "زيده": "increase", "زيدها": "increase",
    "نقص": "decrease", "نقصه": "decrease", "نقصها": "decrease",
    # temperature set
    "اضبط": "set_temp", "حط": "set_temp", "خله": "set_temp", "خليه": "set_temp",
    "خلها": "set_temp", "خليها": "set_temp", "خلهم": "set_temp", "خليهم": "set_temp",
    # return/reset
    "رجع": "on", "رجعه": "on", "رجعها": "on", "رجعهم": "on",
}

CORRECTION_WORDS = {
    "لا", "مو", "غلط", "أقصد", "اقصد", "غير",
}

def _extract_number(text: str):
    """Extract a number from text (for temperature)."""
    m = _re.search(r"(\d+\.?\d*)", text)
    return float(m.group(1)) if m else None

def _resolve_target_idx(words):
    """Resolve ordinal words to index."""
    if "الأول" in words or "اول" in words:
        return 0
    if "الثاني" in words or "ثاني" in words:
        return 1
    if "الثالث" in words or "ثالث" in words:
        return 2
    return None


def detect_followup(text: str, session: dict) -> dict:
    if not session:
        return {"type": None}
    words = set(text.strip().split())

    # Correction
    if words & CORRECTION_WORDS:
        return {"type": "correction", "last_entities": session.get("last_entities", []), "last_room": session.get("last_room", "")}

    # Check for action verb
    action = None
    for w in words:
        if w in VERB_ACTION_MAP:
            action = VERB_ACTION_MAP[w]
            break

    # Check for pronoun (ordinal or reference)
    has_pronoun = bool(words & FOLLOWUP_PRONOUNS)
    has_verb = action is not None

    if not has_verb and not has_pronoun:
        return {"type": None}

    # Extract temperature number
    temp_value = _extract_number(text)

    # If set_temp without number, check "على XX" pattern
    if action == "set_temp" and temp_value is None:
        return {"type": "followup", "action": "set_temp", "target_entity": None,
                "target_idx": None, "temp": None,
                "last_entities": session.get("last_entities", [])}

    # Resolve target index
    target_idx = _resolve_target_idx(words)
    entities = session.get("last_entities", [])
    target_entity = None
    if target_idx is not None and entities and target_idx < len(entities):
        target_entity = entities[target_idx]
    elif len(entities) == 1:
        target_entity = entities[0]

    return {
        "type": "followup",
        "action": action,
        "target_entity": target_entity,
        "target_idx": target_idx,
        "temp": temp_value,
        "last_entities": entities,
    }
