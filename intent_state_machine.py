"""
State Machine for Intent Routing (Tier3 #17).

Replaces if/elif chains with explicit state transitions.
Each transition is logged for debugging.

States: RECEIVED -> CLASSIFIED -> VALIDATED -> EXECUTING -> RESPONDED / FAILED

Usage:
    ctx = IntentContext(message_id="123", raw_text="شغل المكيف")
    ctx.transition(IntentState.CLASSIFIED, "intent=action")
    ctx.transition(IntentState.VALIDATED, "pre-flight passed")
    ctx.transition(IntentState.EXECUTING, "handler=_handle_action")
    # ... execute ...
    ctx.transition(IntentState.RESPONDED, "200ms")
    log_intent_audit(ctx.to_audit_dict())
"""

import logging
import time
import sqlite3
import os
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Any

logger = logging.getLogger("intent_sm")

_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "audit.db")


class IntentState(Enum):
    RECEIVED = "received"
    CLASSIFIED = "classified"
    VALIDATED = "validated"
    EXECUTING = "executing"
    RESPONDED = "responded"
    FAILED = "failed"


@dataclass
class IntentTransition:
    from_state: IntentState
    to_state: IntentState
    reason: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class IntentContext:
    """Tracks the full lifecycle of a user message through intent routing."""
    message_id: str
    raw_text: str
    state: IntentState = IntentState.RECEIVED
    intent: Optional[str] = None
    handler: Optional[str] = None
    transitions: list = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    result: Optional[Any] = None
    error: Optional[str] = None

    def transition(self, new_state: IntentState, reason: str):
        """Record a state transition."""
        t = IntentTransition(
            from_state=self.state,
            to_state=new_state,
            reason=reason,
        )
        self.transitions.append(t)
        self.state = new_state
        logger.debug(
            "[intent] %s: %s -> %s (%s)",
            self.message_id[:8], t.from_state.value, t.to_state.value, reason
        )

    @property
    def duration_ms(self) -> int:
        return int((time.time() - self.started_at) * 1000)

    @property
    def is_terminal(self) -> bool:
        return self.state in (IntentState.RESPONDED, IntentState.FAILED)

    def to_audit_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "raw_text": self.raw_text[:200],
            "intent": self.intent,
            "handler": self.handler,
            "state": self.state.value,
            "duration_ms": self.duration_ms,
            "transitions": " -> ".join(
                f"{t.to_state.value}({t.reason})" for t in self.transitions
            ),
            "error": self.error,
        }

    def to_status_line(self) -> str:
        icons = {
            IntentState.RECEIVED: "📨",
            IntentState.CLASSIFIED: "🏷",
            IntentState.VALIDATED: "✓",
            IntentState.EXECUTING: "⚡",
            IntentState.RESPONDED: "✅",
            IntentState.FAILED: "❌",
        }
        icon = icons.get(self.state, "?")
        line = f"{icon} [{self.duration_ms}ms] {self.intent or '?'}"
        if self.error:
            line += f" — {self.error[:60]}"
        return line


def _ensure_table():
    """Create intent_audit table if needed."""
    try:
        conn = sqlite3.connect(_DB_PATH, timeout=3)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS intent_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT,
                raw_text TEXT,
                intent TEXT,
                handler TEXT,
                final_state TEXT,
                duration_ms INTEGER,
                transitions TEXT,
                error TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        conn.commit()
        conn.close()
    except Exception:
        pass


_table_ensured = False


def log_intent_audit(audit: dict):
    """Log an intent lifecycle to audit.db."""
    global _table_ensured
    if not _table_ensured:
        _ensure_table()
        _table_ensured = True
    try:
        conn = sqlite3.connect(_DB_PATH, timeout=3)
        conn.execute(
            "INSERT INTO intent_audit "
            "(message_id, raw_text, intent, handler, final_state, duration_ms, transitions, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                audit.get("message_id"),
                audit.get("raw_text"),
                audit.get("intent"),
                audit.get("handler"),
                audit.get("state"),
                audit.get("duration_ms"),
                audit.get("transitions"),
                audit.get("error"),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug("[intent_audit] log failed: %s", e)
