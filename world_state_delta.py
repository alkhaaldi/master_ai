"""
world_state_delta.py — World State Delta + House Timeline
Phase 2: Injects only changed entities (last 5 min) instead of full snapshot.
Also provides House Timeline queries (when did X happen?).

Uses: data/home_brain.db (state_changes)
Integrates with: world_state.py (replaces full snapshot injection)
"""
import sqlite3, logging, os, time
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger("world_state_delta")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "home_brain.db")

_prev_snapshot = {}  # {entity_id: state} from last check
_delta_text = ""
_delta_ts = 0

def _get_db():
    if not os.path.exists(DB_PATH): return None
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


# ═══ DELTA: Only changed entities ═══

def build_delta(current_states):
    """Compare current HA states with previous, return only changes.
    Args: current_states = list of HA state dicts
    Returns: (delta_text, changed_count)
    """
    global _prev_snapshot, _delta_text, _delta_ts
    
    changes = []
    new_snap = {}
    
    for s in current_states:
        eid = s["entity_id"]
        domain = eid.split(".")[0]
        if domain not in ("light","climate","cover","fan","media_player","lock"):
            continue
        state = s["state"]
        new_snap[eid] = state
        
        old = _prev_snapshot.get(eid)
        if old is not None and old != state:
            name = s.get("attributes",{}).get("friendly_name", eid.split(".")[-1])
            changes.append(f"  {name}: {old} → {state}")
    
    _prev_snapshot = new_snap
    
    if not changes:
        _delta_text = ""
        _delta_ts = time.time()
        return "", 0
    
    _delta_text = "التغييرات (آخر 30ث):" + chr(10) + chr(10).join(changes)
    _delta_ts = time.time()
    return _delta_text, len(changes)


def get_delta_text():
    """Get recent changes text for system prompt injection."""
    if time.time() - _delta_ts > 60:
        return ""  # stale
    return _delta_text


# ═══ HOUSE TIMELINE ═══

def timeline_query(question):
    """Answer timeline questions like 'when did X happen?'
    Returns: formatted answer string or None
    """
    conn = _get_db()
    if not conn: return None
    
    q = question.lower()
    try:
        # Pattern: "when did [entity/room] turn on/off"
        # Pattern: "what happened at [time]"
        # Pattern: "what changed today/yesterday"
        
        # Last state change for any mentioned entity keyword
        keywords = _extract_keywords(q)
        
        if any(w in q for w in ["آخر","اخر","متى آخر","last"]):
            return _last_event(conn, keywords)
        
        if any(w in q for w in ["اليوم","هاليوم","today"]):
            return _today_events(conn, keywords)
        
        if any(w in q for w in ["أمس","البارحة","yesterday"]):
            return _yesterday_events(conn, keywords)
        
        if any(w in q for w in ["كم مرة","كم مره","how many times"]):
            return _count_events(conn, keywords)
        
        # Default: last 5 events matching keywords
        return _last_event(conn, keywords)
        
    except Exception as e:
        logger.error(f"Timeline query: {e}")
        return None
    finally:
        conn.close()


def _extract_keywords(text):
    """Extract entity-related keywords from Arabic text."""
    kw_map = {
        "باب":("lock","cover"), "أبواب":("lock","cover"),
        "نور":("light",), "أنوار":("light",), "أضواء":("light",), "ضوء":("light",),
        "مكيف":("climate",), "مكيفات":("climate",),
        "ستارة":("cover",), "ستائر":("cover",),
        "سماعة":("media_player",), "سماعات":("media_player",),
        "قفل":("lock",), "أقفال":("lock",),
    }
    domains = set()
    for kw, doms in kw_map.items():
        if kw in text:
            domains.update(doms)
    return domains or {"light","climate","cover","media_player","lock","fan"}


def _last_event(conn, domains):
    """Get last events for domains."""
    dom_list = ",".join(f"'{d}'" for d in domains)
    rows = conn.execute(f"""
        SELECT entity_id, old_state, new_state, ts, domain
        FROM state_changes
        WHERE domain IN ({dom_list})
        ORDER BY ts DESC LIMIT 10
    """).fetchall()
    if not rows:
        return "ما في أحداث"
    lines = ["U0001f4cb آخر الأحداث:"]
    for r in rows:
        name = r["entity_id"].split(".")[-1].replace("_"," ")
        ts = r["ts"][-8:-3]  # HH:MM
        lines.append(f"  {ts} | {name}: {r['old_state']} → {r['new_state']}")
    return chr(10).join(lines)


def _today_events(conn, domains):
    """Events from today."""
    dom_list = ",".join(f"'{d}'" for d in domains)
    rows = conn.execute(f"""
        SELECT domain, new_state, COUNT(*) as c
        FROM state_changes
        WHERE domain IN ({dom_list}) AND date(ts) = date('now','localtime')
        GROUP BY domain, new_state
        ORDER BY c DESC
    """).fetchall()
    if not rows:
        return "ما في أحداث اليوم"
    total = sum(r["c"] for r in rows)
    lines = [f"U0001f4ca أحداث اليوم ({total} تغيير):"]
    for r in rows:
        lines.append(f"  {r['domain']} {r['new_state']}: {r['c']}")
    return chr(10).join(lines)


def _yesterday_events(conn, domains):
    """Events from yesterday."""
    dom_list = ",".join(f"'{d}'" for d in domains)
    rows = conn.execute(f"""
        SELECT domain, new_state, COUNT(*) as c
        FROM state_changes
        WHERE domain IN ({dom_list}) AND date(ts) = date('now','-1 day','localtime')
        GROUP BY domain, new_state
        ORDER BY c DESC
    """).fetchall()
    if not rows:
        return "ما في أحداث أمس"
    total = sum(r["c"] for r in rows)
    lines = [f"U0001f4ca أحداث أمس ({total} تغيير):"]
    for r in rows:
        lines.append(f"  {r['domain']} {r['new_state']}: {r['c']}")
    return chr(10).join(lines)


def _count_events(conn, domains):
    """Count events for domain."""
    dom_list = ",".join(f"'{d}'" for d in domains)
    row = conn.execute(f"""
        SELECT COUNT(*) as c FROM state_changes
        WHERE domain IN ({dom_list}) AND date(ts) = date('now','localtime')
    """).fetchone()
    return f"U0001f522 {row['c']} تغيير اليوم"
