"""
Processing Cursor — Tier1 Pattern #7 from Claude Code Source Analysis.

Tracks "last processed" position for any engine, preventing re-scanning.
Uses audit.db for persistence across restarts.

Usage:
    cursor = ProcessingCursor("news_digest")
    last_id = cursor.get()          # Returns last processed ID (int) or 0
    # ... process items with id > last_id ...
    cursor.set(new_last_id)         # Update cursor position

    # With timestamp cursors:
    cursor_ts = ProcessingCursor("radar_signals", cursor_type="timestamp")
    last_ts = cursor_ts.get()       # Returns ISO timestamp string or ""
    cursor_ts.set(new_timestamp)
"""
import os
import sqlite3
import logging

logger = logging.getLogger("cursor")

_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "audit.db")


def _ensure_table():
    """Create processing_cursors table if it doesn't exist."""
    try:
        conn = sqlite3.connect(_DB_PATH, timeout=5)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS processing_cursors (
                engine TEXT PRIMARY KEY,
                cursor_value TEXT NOT NULL DEFAULT '',
                cursor_type TEXT NOT NULL DEFAULT 'id',
                updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Failed to create processing_cursors table: %s", e)


class ProcessingCursor:
    """Track last-processed position for an engine to avoid re-scanning."""

    def __init__(self, engine: str, cursor_type: str = "id"):
        self.engine = engine
        self.cursor_type = cursor_type
        _ensure_table()

    def get(self) -> str:
        """Get current cursor value. Returns '' if not set."""
        try:
            conn = sqlite3.connect(_DB_PATH, timeout=3)
            row = conn.execute(
                "SELECT cursor_value FROM processing_cursors WHERE engine=?",
                (self.engine,)
            ).fetchone()
            conn.close()
            return row[0] if row else ""
        except Exception:
            return ""

    def get_int(self) -> int:
        """Get cursor as integer. Returns 0 if not set."""
        val = self.get()
        try:
            return int(val) if val else 0
        except (ValueError, TypeError):
            return 0

    def set(self, value) -> None:
        """Update cursor position."""
        try:
            conn = sqlite3.connect(_DB_PATH, timeout=5)
            conn.execute("""
                INSERT INTO processing_cursors (engine, cursor_value, cursor_type, updated_at)
                VALUES (?, ?, ?, datetime('now','localtime'))
                ON CONFLICT(engine) DO UPDATE SET
                    cursor_value=excluded.cursor_value,
                    updated_at=excluded.updated_at
            """, (self.engine, str(value), self.cursor_type))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Failed to update cursor for %s: %s", self.engine, e)

    def to_dict(self) -> dict:
        return {
            "engine": self.engine,
            "cursor_type": self.cursor_type,
            "value": self.get(),
        }
