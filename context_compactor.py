"""
Context Compactor — compresses long conversation histories for Telegram chats.
RPi-friendly: extractive summary (no LLM call), DB-cached.

Usage:
    compactor = ContextCompactor("data/life.db")
    messages = compactor.compact(messages, last_message="user's latest text")
"""
import re
import hashlib
import sqlite3
import logging
from datetime import datetime, timezone

logger = logging.getLogger("context_compactor")


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful words (3+ chars, no stopwords)."""
    _STOP = {
        "the", "and", "for", "that", "this", "with", "from", "have", "has",
        "not", "but", "are", "was", "were", "been", "being", "will", "can",
        "does", "did", "its", "his", "her", "our", "your", "all", "any",
        "each", "every", "both", "few", "more", "most", "some", "such",
        "than", "too", "very", "just", "about", "into", "over", "also",
        "هل", "في", "من", "على", "إلى", "عن", "مع", "هذا", "هذه",
        "التي", "الذي", "التى", "كل", "بعد", "قبل", "بين", "حتى",
        "لكن", "أو", "ثم", "لا", "ما", "هو", "هي", "نحن", "هم",
        "شو", "شنو", "ليش", "كيف", "وين", "متى", "يعني", "بس",
    }
    words = set(re.findall(r'[\w\u0600-\u06FF]{3,}', text.lower()))
    return words - _STOP


def _relevance_score(summary_text: str, query_keywords: set[str]) -> float:
    """Score summary by keyword overlap with the latest message."""
    if not query_keywords:
        return 0.0
    summary_kw = _extract_keywords(summary_text)
    if not summary_kw:
        return 0.0
    overlap = summary_kw & query_keywords
    return len(overlap) / len(query_keywords)


def _chunk_hash(messages: list) -> str:
    """Deterministic hash for a chunk of messages."""
    raw = "|".join(f"{m.get('role','')}:{m.get('text', m.get('content',''))[:100]}" for m in messages)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _extractive_summary(messages: list) -> str:
    """Summarize a chunk of messages extractively (no LLM).
    Takes first sentence of each message, joining with context markers."""
    parts = []
    for m in messages:
        role = m.get("role", "user")
        text = m.get("text", m.get("content", ""))
        if not text:
            continue
        # Take first meaningful sentence (up to 80 chars)
        first = text.strip().split("\n")[0][:120]
        # If too long, take first clause
        if len(first) > 80:
            for sep in [".", "،", ",", "؟", "?", "!"]:
                idx = first.find(sep, 20)
                if idx > 0:
                    first = first[:idx+1]
                    break
        icon = "👤" if role == "user" else "🤖"
        parts.append(f"{icon} {first}")
    return " → ".join(parts) if parts else ""


class ContextCompactor:
    """Compresses conversation history using extractive summarization + caching."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self._db_path, timeout=5)

    def _init_db(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS context_cache (
                conversation_id TEXT NOT NULL,
                chunk_hash TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (conversation_id, chunk_hash)
            )""")
            c.commit()

    def compact(self, messages: list, last_message: str = "",
                keep_recent: int = 6, chunk_size: int = 5,
                max_summaries: int = 3, conversation_id: str = "default") -> list:
        """
        Compact a message list.

        Returns a list mixing summary entries + recent messages, always ≤ max_summaries + keep_recent.
        Each item is a dict with role/text (or role/content).

        Stages:
          1. Split: recent (last keep_recent) vs older
          2. Chunk older into groups of chunk_size
          3. Summarize each chunk (extractive, cached)
          4. Rank summaries by relevance to last_message
          5. Return top max_summaries + recent messages
        """
        if len(messages) <= keep_recent + 2:
            return messages  # no compaction needed

        recent = messages[-keep_recent:]
        older = messages[:-keep_recent]

        if not older:
            return messages

        # Chunk older messages
        chunks = []
        for i in range(0, len(older), chunk_size):
            chunks.append(older[i:i+chunk_size])

        # Summarize each chunk (with cache)
        summaries = []
        for chunk in chunks:
            ch = _chunk_hash(chunk)
            cached = self._get_cached(conversation_id, ch)
            if cached:
                summaries.append(cached)
            else:
                summary = _extractive_summary(chunk)
                if summary:
                    self._cache_summary(conversation_id, ch, summary)
                    summaries.append(summary)

        if not summaries:
            return recent

        # Rank by relevance to last message
        query_text = last_message or ""
        if not query_text and recent:
            last = recent[-1] if isinstance(recent[-1], dict) else {}
            query_text = last.get("text", last.get("content", ""))
        query_kw = _extract_keywords(query_text)

        scored = [(s, _relevance_score(s, query_kw)) for s in summaries]
        scored.sort(key=lambda x: x[1], reverse=True)
        top = [s[0] for s in scored[:max_summaries]]

        # Build compacted list: summaries as system context + recent messages
        result = []
        if top:
            ctx = "\n".join(f"[ملخص سابق] {s}" for s in top)
            result.append({"role": "system", "text": ctx, "content": ctx, "_compacted": True})
        result.extend(recent)
        return result

    def _get_cached(self, conv_id: str, chunk_hash: str) -> str | None:
        try:
            with self._conn() as c:
                row = c.execute(
                    "SELECT summary FROM context_cache WHERE conversation_id=? AND chunk_hash=?",
                    (conv_id, chunk_hash),
                ).fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def _cache_summary(self, conv_id: str, chunk_hash: str, summary: str):
        try:
            with self._conn() as c:
                c.execute(
                    """INSERT OR REPLACE INTO context_cache (conversation_id, chunk_hash, summary)
                       VALUES (?, ?, ?)""",
                    (conv_id, chunk_hash, summary),
                )
                c.commit()
        except Exception as e:
            logger.debug("Cache write error: %s", e)

    def cleanup(self, days: int = 7):
        """Remove old cache entries."""
        try:
            with self._conn() as c:
                c.execute(
                    "DELETE FROM context_cache WHERE created_at < datetime('now', ?)",
                    (f"-{days} days",),
                )
                c.commit()
        except Exception:
            pass
