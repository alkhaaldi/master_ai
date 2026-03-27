"""
feedback_learner.py — Phase 3: Closed-Loop Learning
Records interaction signals and applies learning over time.

Sources:
  - correction: User said "moo hatha" -> wrong interpretation penalized
  - proactive: Suggestion accepted/ignored/rejected
  - action: Command executed -> was it right?
  - clarification: Asked when should have executed (or vice versa)

Feedback values:
  - accepted: User approved or executed suggestion
  - rejected: User explicitly said no
  - corrected: User provided the right answer
  - ignored: No response within timeout

DB: audit.db table 'interaction_feedback'
"""

import sqlite3
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from pathlib import Path

log = logging.getLogger("feedback_learner")

DB_PATH = Path(__file__).parent / "data" / "audit.db"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS interaction_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    source_type TEXT NOT NULL,
    query_text TEXT,
    decision_taken TEXT,
    user_feedback TEXT NOT NULL,
    correct_answer TEXT,
    entity_id TEXT,
    room TEXT,
    confidence_before REAL,
    confidence_after REAL,
    meta TEXT
);
"""

CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_ifb_source ON interaction_feedback(source_type)",
    "CREATE INDEX IF NOT EXISTS idx_ifb_feedback ON interaction_feedback(user_feedback)",
    "CREATE INDEX IF NOT EXISTS idx_ifb_entity ON interaction_feedback(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_ifb_ts ON interaction_feedback(timestamp)",
]


def _get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_table():
    try:
        conn = _get_db()
        conn.execute(CREATE_TABLE_SQL)
        for idx_sql in CREATE_INDEXES_SQL:
            conn.execute(idx_sql)
        conn.commit()
        conn.close()
        log.info("[FeedbackLearner] Table ensured")
    except Exception as e:
        log.error(f"[FeedbackLearner] Table creation failed: {e}")


def record_feedback(
    source_type: str,
    user_feedback: str,
    query_text: str = "",
    decision_taken: str = "",
    correct_answer: str = "",
    entity_id: str = "",
    room: str = "",
    confidence_before: float = 0.0,
    confidence_after: float = 0.0,
    meta: dict = None,
) -> Optional[int]:
    valid_sources = {"correction", "proactive", "action", "clarification"}
    valid_feedback = {"accepted", "rejected", "corrected", "ignored"}
    if source_type not in valid_sources:
        log.warning(f"[FeedbackLearner] Invalid source_type: {source_type}")
        return None
    if user_feedback not in valid_feedback:
        log.warning(f"[FeedbackLearner] Invalid user_feedback: {user_feedback}")
        return None
    try:
        conn = _get_db()
        cur = conn.execute(
            """INSERT INTO interaction_feedback
               (source_type, query_text, decision_taken, user_feedback,
                correct_answer, entity_id, room, confidence_before,
                confidence_after, meta)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (source_type, query_text, decision_taken, user_feedback,
             correct_answer, entity_id, room, confidence_before,
             confidence_after, json.dumps(meta or {}, ensure_ascii=False)),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        log.info(f"[FeedbackLearner] Recorded: {source_type}/{user_feedback} entity={entity_id} id={row_id}")
        return row_id
    except Exception as e:
        log.error(f"[FeedbackLearner] Record failed: {e}")
        return None


def get_stats(days: int = 30) -> Dict:
    try:
        conn = _get_db()
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        rows = conn.execute(
            "SELECT user_feedback, COUNT(*) as cnt FROM interaction_feedback WHERE timestamp >= ? GROUP BY user_feedback",
            (cutoff,)).fetchall()
        by_feedback = {r["user_feedback"]: r["cnt"] for r in rows}
        rows2 = conn.execute(
            "SELECT source_type, COUNT(*) as cnt FROM interaction_feedback WHERE timestamp >= ? GROUP BY source_type",
            (cutoff,)).fetchall()
        by_source = {r["source_type"]: r["cnt"] for r in rows2}
        rows3 = conn.execute(
            "SELECT entity_id, COUNT(*) as cnt FROM interaction_feedback WHERE timestamp >= ? AND user_feedback = 'corrected' AND entity_id != '' GROUP BY entity_id ORDER BY cnt DESC LIMIT 5",
            (cutoff,)).fetchall()
        top_corrected = [{"entity": r["entity_id"], "count": r["cnt"]} for r in rows3]
        rows4 = conn.execute(
            "SELECT decision_taken, COUNT(*) as cnt FROM interaction_feedback WHERE timestamp >= ? AND source_type = 'proactive' AND user_feedback IN ('rejected', 'ignored') GROUP BY decision_taken ORDER BY cnt DESC LIMIT 5",
            (cutoff,)).fetchall()
        top_rejected_proactive = [{"suggestion": r["decision_taken"], "count": r["cnt"]} for r in rows4]
        total = sum(by_feedback.values())
        accepted = by_feedback.get("accepted", 0)
        acceptance_rate = round(accepted / total * 100, 1) if total > 0 else 0.0
        conn.close()
        return {"period_days": days, "total": total, "by_feedback": by_feedback,
                "by_source": by_source, "acceptance_rate": acceptance_rate,
                "top_corrected_entities": top_corrected,
                "top_rejected_proactive": top_rejected_proactive}
    except Exception as e:
        log.error(f"[FeedbackLearner] Stats failed: {e}")
        return {"error": str(e)}


_confidence_adjustments: Dict[str, float] = {}
_ADJUSTMENT_STEP = 0.05
_MAX_ADJUSTMENT = 0.3


def get_confidence_adjustment(entity_id: str) -> float:
    return _confidence_adjustments.get(entity_id, 0.0)


def apply_learning(days: int = 30):
    global _confidence_adjustments
    try:
        conn = _get_db()
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        rows = conn.execute(
            """SELECT entity_id,
                      SUM(CASE WHEN user_feedback = 'corrected' THEN 1 ELSE 0 END) as corrections,
                      SUM(CASE WHEN user_feedback = 'accepted' THEN 1 ELSE 0 END) as accepts,
                      COUNT(*) as total
               FROM interaction_feedback
               WHERE timestamp >= ? AND entity_id != ''
               GROUP BY entity_id HAVING total >= 3""",
            (cutoff,)).fetchall()
        new_adjustments = {}
        for r in rows:
            entity = r["entity_id"]
            corrections = r["corrections"]
            accepts = r["accepts"]
            total = r["total"]
            if total == 0: continue
            correction_ratio = corrections / total
            accept_ratio = accepts / total
            adjustment = (accept_ratio - correction_ratio) * _ADJUSTMENT_STEP * total
            adjustment = max(-_MAX_ADJUSTMENT, min(_MAX_ADJUSTMENT, adjustment))
            new_adjustments[entity] = round(adjustment, 3)
        _confidence_adjustments = new_adjustments
        conn.close()
        if new_adjustments:
            log.info(f"[FeedbackLearner] Applied learning: {len(new_adjustments)} entity adjustments")
        return new_adjustments
    except Exception as e:
        log.error(f"[FeedbackLearner] apply_learning failed: {e}")
        return {}


def generate_digest(days: int = 7) -> str:
    stats = get_stats(days=days)
    if "error" in stats:
        return f"\u26a0\ufe0f Error: {stats['error']}"
    total = stats["total"]
    if total == 0:
        return "\U0001f4ca No interactions recorded this period"
    lines = []
    lines.append(f"\U0001f4ca Learning Digest ({days} days)")
    lines.append("\u2501" * 18)
    lines.append(f"\U0001f4c8 Total: {total} interactions")
    lines.append(f"\u2705 Acceptance rate: {stats['acceptance_rate']}%")
    by_fb = stats["by_feedback"]
    lines.append("")
    lines.append("\U0001f4cb By result:")
    for fb, cnt in sorted(by_fb.items(), key=lambda x: -x[1]):
        emoji = {"accepted": "\u2705", "rejected": "\u274c", "corrected": "\U0001f504", "ignored": "\u23f8\ufe0f"}.get(fb, "\u2022")
        lines.append(f"  {emoji} {fb}: {cnt}")
    if stats["top_corrected_entities"]:
        lines.append("")
        lines.append("\U0001f6a8 Most corrected entities:")
        for item in stats["top_corrected_entities"]:
            lines.append(f"  \u2022 {item['entity']}: {item['count']}x")
    if stats["top_rejected_proactive"]:
        lines.append("")
        lines.append("\U0001f6ab Rejected suggestions:")
        for item in stats["top_rejected_proactive"]:
            lines.append(f"  \u2022 {item['suggestion'][:50]}: {item['count']}x")
    adjustments = apply_learning(days=days)
    if adjustments:
        lines.append("")
        lines.append("\U0001f9e0 Confidence adjustments:")
        sorted_adj = sorted(adjustments.items(), key=lambda x: x[1])
        for entity, adj in sorted_adj[:5]:
            direction = "\u2b06\ufe0f" if adj > 0 else "\u2b07\ufe0f"
            lines.append(f"  {direction} {entity}: {adj:+.3f}")
    return "\n".join(lines)


def init():
    ensure_table()
    apply_learning(days=30)
    log.info("[FeedbackLearner] Initialized")
