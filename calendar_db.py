"""calendar_db.py — Database layer for Master AI Calendar (life.db)

v8 Phase 1: Calendar + Reminders
Tables: calendar_sources, calendar_sync_state, calendar_events,
        calendar_reminders, calendar_conflicts, calendar_parse_log
"""

import sqlite3
import logging
import os
import json
from datetime import datetime

logger = logging.getLogger("calendar_db")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")


def get_db():
    """Get connection to life.db with WAL mode."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_life_db():
    """Create all calendar tables if they don't exist."""
    conn = get_db()
    try:
        conn.executescript("""
        -- Calendar sources (Google primary, etc.)
        CREATE TABLE IF NOT EXISTS calendar_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_key TEXT UNIQUE NOT NULL,
            provider TEXT NOT NULL DEFAULT 'google',
            calendar_id TEXT NOT NULL DEFAULT 'primary',
            display_name TEXT,
            is_enabled INTEGER NOT NULL DEFAULT 1,
            timezone TEXT NOT NULL DEFAULT 'Asia/Kuwait',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- Sync state per source
        CREATE TABLE IF NOT EXISTS calendar_sync_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_key TEXT UNIQUE NOT NULL,
            last_full_sync_at TEXT,
            last_incremental_sync_at TEXT,
            next_sync_due_at TEXT,
            sync_token TEXT,
            last_status TEXT,
            last_error TEXT,
            failure_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- Local cache of calendar events
        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_key TEXT NOT NULL DEFAULT 'google_primary',
            google_event_id TEXT NOT NULL,
            ical_uid TEXT,
            status TEXT NOT NULL DEFAULT 'confirmed',
            summary TEXT,
            description TEXT,
            location TEXT,
            start_ts TEXT NOT NULL,
            end_ts TEXT NOT NULL,
            is_all_day INTEGER NOT NULL DEFAULT 0,
            timezone TEXT DEFAULT 'Asia/Kuwait',
            html_link TEXT,
            creator_email TEXT,
            organizer_email TEXT,
            raw_json TEXT,
            etag TEXT,
            updated_google_ts TEXT,
            is_deleted_local INTEGER NOT NULL DEFAULT 0,
            last_synced_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- Internal reminders
        CREATE TABLE IF NOT EXISTS calendar_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            reminder_type TEXT NOT NULL DEFAULT 'pre_event',
            offset_minutes INTEGER NOT NULL DEFAULT 60,
            scheduled_for TEXT NOT NULL,
            sent_at TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            channel TEXT NOT NULL DEFAULT 'telegram',
            chat_id TEXT,
            dedupe_key TEXT UNIQUE,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- Conflict detection results
        CREATE TABLE IF NOT EXISTS calendar_conflicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            conflict_type TEXT NOT NULL,
            severity INTEGER NOT NULL DEFAULT 50,
            conflict_text TEXT NOT NULL,
            resolved INTEGER NOT NULL DEFAULT 0,
            resolved_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- Parser debug log (first 4 weeks)
        CREATE TABLE IF NOT EXISTS calendar_parse_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            input_text TEXT NOT NULL,
            parser_used TEXT NOT NULL DEFAULT 'rule',
            parsed_json TEXT,
            success INTEGER NOT NULL DEFAULT 1,
            error_text TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- Indexes
        CREATE UNIQUE INDEX IF NOT EXISTS idx_cal_events_source_google
            ON calendar_events(source_key, google_event_id);
        CREATE INDEX IF NOT EXISTS idx_cal_events_range
            ON calendar_events(start_ts, end_ts);
        CREATE INDEX IF NOT EXISTS idx_cal_events_status
            ON calendar_events(status);
        CREATE INDEX IF NOT EXISTS idx_cal_reminders_due
            ON calendar_reminders(status, scheduled_for);
        CREATE INDEX IF NOT EXISTS idx_cal_conflicts_event
            ON calendar_conflicts(event_id);
        """)

        # Seed default source
        conn.execute("""
            INSERT OR IGNORE INTO calendar_sources (source_key, provider, calendar_id, display_name)
            VALUES ('google_primary', 'google', 'primary', 'Google Calendar')
        """)
        conn.execute("""
            INSERT OR IGNORE INTO calendar_sync_state (source_key, last_status)
            VALUES ('google_primary', 'not_synced')
        """)
        conn.commit()
        logger.info("life.db initialized with calendar tables")
        return True
    except Exception as e:
        logger.error(f"life.db init error: {e}")
        return False
    finally:
        conn.close()


# ═══ Event Cache Operations ═══

def upsert_event(event_dict: dict) -> int:
    """Insert or update a cached calendar event. Returns row id."""
    conn = get_db()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        existing = conn.execute(
            "SELECT id FROM calendar_events WHERE source_key=? AND google_event_id=?",
            (event_dict.get("source_key", "google_primary"), event_dict["google_event_id"])
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE calendar_events SET
                    status=?, summary=?, description=?, location=?,
                    start_ts=?, end_ts=?, is_all_day=?, timezone=?,
                    html_link=?, creator_email=?, organizer_email=?,
                    raw_json=?, etag=?, updated_google_ts=?,
                    is_deleted_local=?, last_synced_at=?, updated_at=?
                WHERE id=?
            """, (
                event_dict.get("status", "confirmed"),
                event_dict.get("summary"), event_dict.get("description"),
                event_dict.get("location"),
                event_dict["start_ts"], event_dict["end_ts"],
                event_dict.get("is_all_day", 0), event_dict.get("timezone", "Asia/Kuwait"),
                event_dict.get("html_link"), event_dict.get("creator_email"),
                event_dict.get("organizer_email"),
                event_dict.get("raw_json"), event_dict.get("etag"),
                event_dict.get("updated_google_ts"),
                event_dict.get("is_deleted_local", 0), now, now,
                existing["id"]
            ))
            conn.commit()
            return existing["id"]
        else:
            cur = conn.execute("""
                INSERT INTO calendar_events (
                    source_key, google_event_id, ical_uid, status,
                    summary, description, location,
                    start_ts, end_ts, is_all_day, timezone,
                    html_link, creator_email, organizer_email,
                    raw_json, etag, updated_google_ts,
                    is_deleted_local, last_synced_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                event_dict.get("source_key", "google_primary"),
                event_dict["google_event_id"],
                event_dict.get("ical_uid"),
                event_dict.get("status", "confirmed"),
                event_dict.get("summary"), event_dict.get("description"),
                event_dict.get("location"),
                event_dict["start_ts"], event_dict["end_ts"],
                event_dict.get("is_all_day", 0),
                event_dict.get("timezone", "Asia/Kuwait"),
                event_dict.get("html_link"), event_dict.get("creator_email"),
                event_dict.get("organizer_email"),
                event_dict.get("raw_json"), event_dict.get("etag"),
                event_dict.get("updated_google_ts"),
                event_dict.get("is_deleted_local", 0),
                now
            ))
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


def mark_deleted(source_key: str, google_event_id: str):
    """Mark event as deleted locally (cancelled on Google)."""
    conn = get_db()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            UPDATE calendar_events SET status='cancelled', is_deleted_local=1, updated_at=?
            WHERE source_key=? AND google_event_id=?
        """, (now, source_key, google_event_id))
        conn.commit()
    finally:
        conn.close()


def get_events_range(start_ts: str, end_ts: str, source_key: str = "google_primary") -> list:
    """Get cached events in a time range."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT * FROM calendar_events
            WHERE source_key=? AND status != 'cancelled' AND is_deleted_local=0
                AND start_ts < ? AND end_ts > ?
            ORDER BY start_ts ASC
        """, (source_key, end_ts, start_ts)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_event_by_google_id(source_key: str, google_event_id: str) -> dict | None:
    """Get a single event by Google event ID."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM calendar_events WHERE source_key=? AND google_event_id=?",
            (source_key, google_event_id)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_event_local(event_id: int):
    """Hard delete from local cache."""
    conn = get_db()
    try:
        conn.execute("DELETE FROM calendar_events WHERE id=?", (event_id,))
        conn.execute("DELETE FROM calendar_reminders WHERE event_id=?", (event_id,))
        conn.execute("DELETE FROM calendar_conflicts WHERE event_id=?", (event_id,))
        conn.commit()
    finally:
        conn.close()


# ═══ Sync State ═══

def save_sync_state(source_key: str, **kwargs):
    """Update sync state fields."""
    conn = get_db()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fields = []
        values = []
        for k, v in kwargs.items():
            if k in ("sync_token", "last_full_sync_at", "last_incremental_sync_at",
                      "next_sync_due_at", "last_status", "last_error", "failure_count"):
                fields.append(f"{k}=?")
                values.append(v)
        fields.append("updated_at=?")
        values.append(now)
        values.append(source_key)
        conn.execute(
            f"UPDATE calendar_sync_state SET {', '.join(fields)} WHERE source_key=?",
            values
        )
        conn.commit()
    finally:
        conn.close()


def load_sync_state(source_key: str = "google_primary") -> dict | None:
    """Load sync state for a source."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM calendar_sync_state WHERE source_key=?", (source_key,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def clear_sync_state(source_key: str = "google_primary"):
    """Clear sync token (forces full resync)."""
    save_sync_state(source_key, sync_token=None, last_status="token_cleared", failure_count=0)


# ═══ Reminders ═══

def insert_reminder(event_id: int, reminder_type: str, offset_minutes: int,
                    scheduled_for: str, chat_id: str = None) -> int | None:
    """Insert a reminder, returns id or None if dedupe hit."""
    conn = get_db()
    try:
        dedupe = f"{event_id}_{reminder_type}_{offset_minutes}"
        cur = conn.execute("""
            INSERT OR IGNORE INTO calendar_reminders
                (event_id, reminder_type, offset_minutes, scheduled_for, chat_id, dedupe_key)
            VALUES (?,?,?,?,?,?)
        """, (event_id, reminder_type, offset_minutes, scheduled_for, chat_id, dedupe))
        conn.commit()
        return cur.lastrowid if cur.lastrowid else None
    finally:
        conn.close()


def get_due_reminders(now_ts: str = None) -> list:
    """Get pending reminders that are due."""
    if not now_ts:
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT r.*, e.summary, e.start_ts, e.end_ts, e.location, e.status as event_status
            FROM calendar_reminders r
            JOIN calendar_events e ON r.event_id = e.id
            WHERE r.status='pending' AND r.scheduled_for <= ?
                AND e.status != 'cancelled' AND e.is_deleted_local=0
            ORDER BY r.scheduled_for ASC
        """, (now_ts,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_reminder_sent(reminder_id: int):
    """Mark a reminder as sent."""
    conn = get_db()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE calendar_reminders SET status='sent', sent_at=?, updated_at=? WHERE id=?",
            (now, now, reminder_id)
        )
        conn.commit()
    finally:
        conn.close()


def cancel_event_reminders(event_id: int):
    """Cancel all pending reminders for an event."""
    conn = get_db()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE calendar_reminders SET status='cancelled', updated_at=? WHERE event_id=? AND status='pending'",
            (now, event_id)
        )
        conn.commit()
    finally:
        conn.close()


# ═══ Conflicts ═══

def insert_conflict(event_id: int, conflict_type: str, severity: int, conflict_text: str) -> int:
    """Record a conflict."""
    conn = get_db()
    try:
        cur = conn.execute("""
            INSERT INTO calendar_conflicts (event_id, conflict_type, severity, conflict_text)
            VALUES (?,?,?,?)
        """, (event_id, conflict_type, severity, conflict_text))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


# ═══ Parse Log ═══

def log_parse(input_text: str, parser_used: str, parsed_json: str = None,
              success: bool = True, error_text: str = None):
    """Log a parse attempt for debugging."""
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO calendar_parse_log (input_text, parser_used, parsed_json, success, error_text)
            VALUES (?,?,?,?,?)
        """, (input_text, parser_used, json.dumps(parsed_json) if parsed_json else None,
              1 if success else 0, error_text))
        conn.commit()
    except Exception:
        pass  # Non-critical
    finally:
        conn.close()


# ═══ Stats ═══

def get_calendar_stats() -> dict:
    """Get calendar statistics."""
    conn = get_db()
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM calendar_events WHERE status != 'cancelled'"
        ).fetchone()[0]
        pending_reminders = conn.execute(
            "SELECT COUNT(*) FROM calendar_reminders WHERE status='pending'"
        ).fetchone()[0]
        sync = load_sync_state()
        return {
            "total_events": total,
            "pending_reminders": pending_reminders,
            "last_sync": sync.get("last_incremental_sync_at") if sync else None,
            "sync_status": sync.get("last_status") if sync else "unknown"
        }
    finally:
        conn.close()
