"""
Habit Tracker — learns daily patterns and suggests automations.
Phase 1: Log events + detect patterns + suggest automations.
"""
import sqlite3
import os
import json
import logging
from datetime import datetime, timedelta
from collections import Counter, defaultdict

logger = logging.getLogger("habit_tracker")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "habits.db")


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT DEFAULT (datetime('now','localtime')),
        entity_id TEXT,
        action TEXT,
        source TEXT DEFAULT 'user',
        day_of_week INTEGER,
        hour INTEGER,
        shift TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS patterns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id TEXT,
        action TEXT,
        hour INTEGER,
        day_of_week INTEGER,
        shift TEXT,
        occurrences INTEGER DEFAULT 0,
        last_seen TEXT,
        suggested INTEGER DEFAULT 0,
        dismissed INTEGER DEFAULT 0,
        UNIQUE(entity_id, action, hour, shift)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT DEFAULT (datetime('now','localtime')),
        pattern_id INTEGER,
        message TEXT,
        status TEXT DEFAULT 'pending',
        FOREIGN KEY (pattern_id) REFERENCES patterns(id)
    )""")
    conn.commit()
    return conn


def log_event(entity_id: str, action: str, source: str = "user", shift: str = ""):
    """Log a device event for pattern learning."""
    now = datetime.now()
    try:
        conn = _db()
        conn.execute(
            "INSERT INTO events (entity_id, action, source, day_of_week, hour, shift) VALUES (?,?,?,?,?,?)",
            (entity_id, action, source, now.weekday(), now.hour, shift)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"log_event: {e}")


def analyze_patterns(min_occurrences: int = 5):
    """Analyze events to find recurring patterns."""
    try:
        conn = _db()
        # Group by entity+action+hour+shift, count occurrences
        rows = conn.execute("""
            SELECT entity_id, action, hour, shift, COUNT(*) as cnt,
                   MAX(ts) as last_seen
            FROM events
            WHERE ts > datetime('now', '-30 days', 'localtime')
            GROUP BY entity_id, action, hour, shift
            HAVING cnt >= ?
            ORDER BY cnt DESC
        """, (min_occurrences,)).fetchall()

        new_patterns = 0
        for r in rows:
            conn.execute("""
                INSERT INTO patterns (entity_id, action, hour, shift, occurrences, last_seen)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(entity_id, action, hour, shift) DO UPDATE SET
                    occurrences = ?, last_seen = ?
            """, (r["entity_id"], r["action"], r["hour"], r["shift"],
                  r["cnt"], r["last_seen"], r["cnt"], r["last_seen"]))
            new_patterns += 1

        conn.commit()
        conn.close()
        return new_patterns
    except Exception as e:
        logger.error(f"analyze_patterns: {e}")
        return 0


def get_suggestions(limit: int = 5):
    """Get unsuggested patterns that could become automations."""
    try:
        conn = _db()
        rows = conn.execute("""
            SELECT p.id, p.entity_id, p.action, p.hour, p.shift,
                   p.occurrences, p.last_seen
            FROM patterns p
            WHERE p.suggested = 0 AND p.dismissed = 0
                  AND p.occurrences >= 7
            ORDER BY p.occurrences DESC
            LIMIT ?
        """, (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_suggestions: {e}")
        return []


def mark_suggested(pattern_id: int):
    """Mark a pattern as suggested."""
    try:
        conn = _db()
        conn.execute("UPDATE patterns SET suggested = 1 WHERE id = ?", (pattern_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"mark_suggested: {e}")


def dismiss_suggestion(pattern_id: int):
    """Dismiss a suggestion."""
    try:
        conn = _db()
        conn.execute("UPDATE patterns SET dismissed = 1 WHERE id = ?", (pattern_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"dismiss_suggestion: {e}")


def get_stats():
    """Get habit tracking stats."""
    try:
        conn = _db()
        total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        today_events = conn.execute(
            "SELECT COUNT(*) FROM events WHERE date(ts) = date('now','localtime')"
        ).fetchone()[0]
        patterns = conn.execute(
            "SELECT COUNT(*) FROM patterns WHERE occurrences >= 5"
        ).fetchone()[0]
        conn.close()
        return {"total_events": total_events, "today": today_events, "patterns": patterns}
    except Exception as e:
        logger.error(f"get_stats: {e}")
        return {"total_events": 0, "today": 0, "patterns": 0}


def format_suggestion(s: dict) -> str:
    """Format a pattern as a human-readable Arabic suggestion."""
    action_ar = {"turn_on": "\u062a\u0634\u063a\u0644", "turn_off": "\u062a\u0637\u0641\u064a",
                 "set_temperature": "\u062a\u0636\u0628\u0637", "open_cover": "\u062a\u0641\u062a\u062d",
                 "close_cover": "\u062a\u0633\u0643\u0631", "activate": "\u062a\u0641\u0639\u0644"}
    act = action_ar.get(s["action"], s["action"])
    h = s["hour"]
    period = "\u0635\u0628\u0627\u062d\u0627\u064b" if 5 <= h < 12 else "\u0638\u0647\u0631\u0627\u064b" if 12 <= h < 17 else "\u0645\u0633\u0627\u0621\u064b" if 17 <= h < 22 else "\u0644\u064a\u0644\u0627\u064b"
    time_str = f"{h:02d}:00"
    name = s["entity_id"].split(".")[-1].replace("_", " ")
    return f"\U0001f4a1 \u0644\u0627\u062d\u0638\u062a \u0625\u0646\u0643 \u062f\u0627\u064a\u0645 {act} {name} \u0627\u0644\u0633\u0627\u0639\u0629 {time_str} {period} ({s['occurrences']} \u0645\u0631\u0629)\n\u062a\u0628\u064a\u0646\u064a \u0623\u0633\u0648\u064a\u0647\u0627 \u0623\u0648\u062a\u0648\u0645\u0627\u062a\u064a\u0643\u061f"
