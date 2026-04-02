"""
Session Memory for Master AI (Tier2 #14).

Captures conversation-level summaries after meaningful exchanges.
Stores in audit.db (table: session_summaries).
Used for: conversation continuity, weekly insights, audit trail.
"""

import os
import re
import time
import sqlite3
import logging
from typing import Optional

logger = logging.getLogger("session_memory")

_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "audit.db")

# Minimum messages for a "meaningful" conversation worth summarizing
MIN_MESSAGES_FOR_SUMMARY = 4

# Gap threshold: >30 minutes between messages = new session
SESSION_GAP_SECONDS = 1800


def _ensure_table():
    """Create session_summaries table if needed."""
    try:
        conn = sqlite3.connect(_DB_PATH, timeout=5)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                user_id TEXT,
                summary TEXT NOT NULL,
                topics TEXT,
                decisions TEXT,
                actions TEXT,
                message_count INTEGER,
                started_at REAL,
                ended_at REAL,
                created_at REAL DEFAULT (strftime('%s', 'now'))
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Failed to create session_summaries table: %s", e)


def extract_topics(text: str) -> list:
    """Simple keyword-based topic extraction (no LLM needed)."""
    topics = set()
    stock_pattern = r'\b(CLEANING|SENERGY|INOVEST|THURAYA|HUMANSOFT|QURAIN|KFH|NBK|ZAIN|VIVA|AGILITY)\b'
    found = re.findall(stock_pattern, text, re.IGNORECASE)
    for s in found:
        topics.add(s.upper())

    domain_keywords = {
        "trading": ["سهم", "شراء", "بيع", "إشارة", "signal", "buy", "sell", "stock", "radar"],
        "HA": ["automation", "أتمتة", "مكيف", "نور", "light", "AC", "adhan", "scene"],
        "network": ["WiFi", "AP", "شبكة", "bridge", "بريدج"],
        "system": ["restart", "deploy", "error", "خطأ", "update", "status"],
        "calendar": ["موعد", "اجتماع", "meeting", "calendar"],
        "expenses": ["مصروف", "فلوس", "expense", "شراء"],
    }
    text_lower = text.lower()
    for domain, keywords in domain_keywords.items():
        if any(kw.lower() in text_lower for kw in keywords):
            topics.add(domain)

    return list(topics)[:5]


def store_session_summary(
    session_id: str,
    summary: str,
    topics: str = "",
    decisions: str = "",
    actions: str = "",
    message_count: int = 0,
    started_at: float = None,
    ended_at: float = None,
    user_id: str = None,
) -> None:
    """Store summary in audit.db."""
    try:
        conn = sqlite3.connect(_DB_PATH, timeout=5)
        conn.execute(
            """INSERT INTO session_summaries
            (session_id, user_id, summary, topics, decisions, actions,
             message_count, started_at, ended_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, user_id, summary, topics, decisions, actions,
             message_count, started_at, ended_at),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Failed to store session summary: %s", e)


class SessionTracker:
    """Tracks conversation sessions. After meaningful exchanges + quiet period,
    triggers summary extraction."""

    def __init__(self):
        self.current_session_id: Optional[str] = None
        self.messages: list = []
        self.session_start: Optional[float] = None
        _ensure_table()

    def add_message(self, role: str, content: str) -> None:
        """Track a message in the current session."""
        now = time.time()

        if (self.current_session_id is None or
                (self.messages and now - self.messages[-1]["timestamp"] > SESSION_GAP_SECONDS)):
            if self.should_summarize():
                self._trigger_summary()
            self.current_session_id = f"session_{int(now)}"
            self.messages = []
            self.session_start = now

        self.messages.append({
            "role": role,
            "content": content[:500],
            "timestamp": now,
        })

    def should_summarize(self) -> bool:
        return len(self.messages) >= MIN_MESSAGES_FOR_SUMMARY

    def _trigger_summary(self) -> None:
        if not self.messages:
            return
        try:
            conv_text = "\n".join([
                f"{'User' if m['role'] == 'user' else 'AI'}: {m['content']}"
                for m in self.messages[-20:]
            ])
            topics = extract_topics(conv_text)
            summary_text = (
                f"Session with {len(self.messages)} messages. "
                f"Topics: {', '.join(topics) if topics else 'general'}."
            )
            store_session_summary(
                session_id=self.current_session_id,
                summary=summary_text,
                topics=",".join(topics),
                message_count=len(self.messages),
                started_at=self.session_start,
                ended_at=self.messages[-1]["timestamp"],
            )
            logger.info(
                "[session_memory] Summarized %s: %d msgs, topics=%s",
                self.current_session_id, len(self.messages), topics
            )
        except Exception as e:
            logger.warning("[session_memory] Summary failed: %s", e)

    def flush(self) -> None:
        """Force summarize current session (e.g., on shutdown)."""
        if self.should_summarize():
            self._trigger_summary()
