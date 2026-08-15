#!/usr/bin/env python3
"""corrections_loop.py — Corrections Learning Loop for Master AI v7

This module makes Master AI learn from user corrections:
1. Detects corrections in user messages ("لا أقصد X مو Y")
2. Extracts the correction (wrong → right)
3. Stores with confidence and context
4. Applies corrections to future similar queries
5. Decays corrections that become irrelevant

Integration:
- Import in chat_v7.py
- Call detect_correction() on every user message
- Call apply_corrections() before generating response
- Call get_correction_context() for system prompt injection
"""
import re
import json
import time
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("corrections_loop")

# ── Correction Patterns ──────────────────────────────────────
# Arabic patterns that indicate user is correcting the AI
CORRECTION_PATTERNS = [
    # Direct negation + correction
    (r"لا[,،]?\s*(أقصد|قصدي|المقصود)\s+(.+?)(?:\s+مو\s+|\s+مش\s+|\s+ليس\s+)(.+)", "negation_correction"),
    # "مو X، Y" pattern
    (r"مو\s+(.+?)[,،]\s*(.+)", "mou_correction"),
    # "لا، X" pattern
    (r"^لا[,،]\s+(.+)", "simple_no"),
    # "غلط، الصح هو X"
    (r"غلط[,،]?\s*(الصح|الصحيح|المفروض)\s+(?:هو\s+)?(.+)", "wrong_correction"),
    # "أسمه/اسمه X مو Y"
    (r"(?:اسمه|أسمه|إسمه)\s+(.+?)\s+مو\s+(.+)", "name_correction"),
    # "X مو Y — Z هو الصح"
    (r"(.+?)\s+مو\s+(.+?)(?:[,،—-]\s*(.+?)(?:\s+هو\s+الصح))?$", "x_not_y"),
    # "الصالة = المعيشة" type
    (r"(.+?)\s*[=:]\s*(.+)", "alias_definition"),
    # "عبود = عبدالله" type
    (r"(\S+)\s*يعني\s+(.+)", "alias_yani"),
]

# Contexts that help categorize corrections
CORRECTION_CATEGORIES = {
    "room_alias": ["غرفة", "الصالة", "المعيشة", "الماستر", "المطبخ", "الديوانية", "الاستقبال"],
    "person_name": ["اسم", "أسمه", "عبود", "عبدالله", "ناهد", "أوانا", "فواز", "خالد", "جابر"],
    "device": ["مكيف", "نور", "ستارة", "سماعة", "تلفزيون", "قفل"],
    "shift": ["دوام", "شفت", "إجازة", "صباحي", "عصري", "ليلي"],
    "location": ["وين", "مكان", "عنوان", "بيت"],
}


class CorrectionsLoop:
    def __init__(self, db_path: str = "data/structured_memory.db"):
        self.db_path = db_path
        self._ensure_table()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_table(self):
        """Create corrections table if not exists."""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wrong_value TEXT NOT NULL,
                right_value TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                context TEXT DEFAULT '',
                confidence REAL DEFAULT 1.0,
                times_applied INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                last_applied TEXT,
                source TEXT DEFAULT 'user'
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_corrections_wrong
            ON corrections(wrong_value)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_corrections_category
            ON corrections(category)
        """)
        conn.commit()
        conn.close()

    def detect_correction(self, user_message: str, ai_previous_response: str = "") -> dict | None:
        """Detect if user message contains a correction.

        Returns dict with:
            wrong: what AI said (incorrect)
            right: what user means (correct)
            category: room_alias, person_name, device, etc.
            pattern: which pattern matched
            confidence: initial confidence (0.0 - 1.0)
        """
        msg = user_message.strip()

        # --- False positive filters ---
        # Skip TG forwarded/quoted messages (contain timestamps like [12/03/2026 05:37])
        if re.search(r"\[\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}", msg):
            return None
        # Skip messages that are too long to be corrections (>200 chars)
        if len(msg) > 200:
            return None
        # Skip messages that look like commands or URLs
        if msg.startswith("/") or msg.startswith("http"):
            return None

        for pattern, ptype in CORRECTION_PATTERNS:
            match = re.search(pattern, msg)
            if not match:
                continue

            groups = match.groups()

            if ptype == "negation_correction" and len(groups) >= 3:
                right_val = groups[1].strip()
                wrong_val = groups[2].strip()
            elif ptype == "mou_correction" and len(groups) >= 2:
                wrong_val = groups[0].strip()
                right_val = groups[1].strip()
            elif ptype == "simple_no" and len(groups) >= 1:
                right_val = groups[0].strip()
                # Try to extract wrong from AI's previous response
                wrong_val = self._extract_wrong_from_context(ai_previous_response, right_val)
            elif ptype == "wrong_correction" and len(groups) >= 2:
                right_val = groups[1].strip()
                wrong_val = self._extract_wrong_from_context(ai_previous_response, right_val)
            elif ptype == "x_not_y" and len(groups) >= 2:
                wrong_val = groups[1].strip()
                right_val = groups[2].strip() if len(groups) > 2 and groups[2] else groups[0].strip()
            elif ptype == "name_correction" and len(groups) >= 2:
                right_val = groups[0].strip()
                wrong_val = groups[1].strip()
            elif ptype in ("alias_definition", "alias_yani") and len(groups) >= 2:
                wrong_val = groups[0].strip()  # not really "wrong", more like alias
                right_val = groups[1].strip()
            else:
                continue

            if not wrong_val or not right_val:
                continue
            if wrong_val == right_val:
                continue
            # Filter: min 2 chars for both values
            if len(wrong_val) < 2 or len(right_val) < 2:
                continue
            # Filter: max 100 chars (longer = not a correction)
            if len(wrong_val) > 100 or len(right_val) > 100:
                continue
            # Filter: skip if either contains TG timestamp patterns
            if re.search(r"\d{2}/\d{2}/\d{4}", wrong_val) or re.search(r"\d{2}/\d{2}/\d{4}", right_val):
                continue

            # Categorize
            category = self._categorize(wrong_val, right_val, msg)

            # Confidence based on pattern clarity
            confidence = 0.9 if ptype in ("negation_correction", "name_correction", "wrong_correction") else 0.7

            return {
                "wrong": wrong_val,
                "right": right_val,
                "category": category,
                "pattern": ptype,
                "confidence": confidence,
                "original_message": msg,
            }

        return None

    def _extract_wrong_from_context(self, ai_response: str, right_val: str) -> str | None:
        """Try to figure out what AI said wrong from its previous response."""
        if not ai_response:
            return None
        # Simple heuristic: look for the most specific noun in AI's response
        # that differs from the right value
        # Cannot reliably determine the wrong value — return None to skip saving
        return None

    def _categorize(self, wrong: str, right: str, full_msg: str) -> str:
        """Categorize the correction."""
        combined = f"{wrong} {right} {full_msg}".lower()
        for cat, keywords in CORRECTION_CATEGORIES.items():
            if any(kw in combined for kw in keywords):
                return cat
        return "general"

    def save_correction(self, correction: dict) -> int:
        """Save a detected correction to DB. Returns correction ID."""
        conn = self._get_conn()

        # Check for existing similar correction
        existing = conn.execute(
            "SELECT id, confidence, times_applied FROM corrections WHERE wrong_value = ? AND right_value = ?",
            (correction["wrong"], correction["right"])
        ).fetchone()

        if existing:
            # Boost confidence of existing correction
            new_conf = min(1.0, existing["confidence"] + 0.1)
            conn.execute(
                "UPDATE corrections SET confidence = ? WHERE id = ?",
                (new_conf, existing["id"])
            )
            conn.commit()
            conn.close()
            logger.info(f"Boosted correction #{existing['id']}: {correction['wrong']} → {correction['right']} (conf={new_conf})")
            return existing["id"]

        cursor = conn.execute(
            """INSERT INTO corrections (wrong_value, right_value, category, context, confidence, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (correction["wrong"], correction["right"], correction["category"],
             correction.get("original_message", ""), correction["confidence"], "user")
        )
        conn.commit()
        cid = cursor.lastrowid
        conn.close()
        logger.info(f"Saved correction #{cid}: {correction['wrong']} → {correction['right']} [{correction['category']}]")

        # Also save to structured memory
        self._save_to_structured_memory(correction)

        return cid

    def _save_to_structured_memory(self, correction: dict):
        """Also save correction to structured_memory table for LLM context."""
        try:
            conn = self._get_conn()
            conn.execute(
                """INSERT OR REPLACE INTO memories
                   (type, category, key, value, confidence, source, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
                ("correction", correction["category"],
                 f"{correction['wrong']}_to_{correction['right']}",
                 json.dumps({"wrong": correction["wrong"], "right": correction["right"],
                            "context": correction.get("original_message", "")}, ensure_ascii=False),
                 correction["confidence"], "user_correction")
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to save to structured_memory: {e}")

    def apply_corrections(self, text: str) -> tuple[str, list[dict]]:
        """Apply known corrections to text before processing.

        Returns (corrected_text, list_of_applied_corrections)
        """
        conn = self._get_conn()
        corrections = conn.execute(
            "SELECT * FROM corrections WHERE confidence >= 0.7 ORDER BY confidence DESC"
        ).fetchall()
        conn.close()

        applied = []
        corrected = text

        for c in corrections:
            wrong = c["wrong_value"]
            right = c["right_value"]

            if wrong.lower() in corrected.lower():
                # Apply correction with word boundary to avoid partial-word replacements
                try:
                    corrected = re.sub(r'(?<![\w؀-ۿ])' + re.escape(wrong) + r'(?![\w؀-ۿ])', right, corrected, flags=re.IGNORECASE)
                except re.error:
                    corrected = re.sub(re.escape(wrong), right, corrected, flags=re.IGNORECASE)
                applied.append({
                    "id": c["id"],
                    "wrong": wrong,
                    "right": right,
                    "category": c["category"],
                    "confidence": c["confidence"],
                })

                # Update usage stats
                conn2 = self._get_conn()
                conn2.execute(
                    "UPDATE corrections SET times_applied = times_applied + 1, last_applied = datetime('now') WHERE id = ?",
                    (c["id"],)
                )
                conn2.commit()
                conn2.close()

        return corrected, applied

    def get_correction_context(self, limit: int = 20) -> str:
        """Get corrections context for LLM system prompt injection."""
        conn = self._get_conn()
        corrections = conn.execute(
            """SELECT wrong_value, right_value, category, confidence, times_applied
               FROM corrections
               WHERE confidence >= 0.5
               ORDER BY confidence DESC, times_applied DESC
               LIMIT ?""",
            (limit,)
        ).fetchall()
        conn.close()

        if not corrections:
            return ""

        lines = ["## تصحيحات المستخدم (يجب مراعاتها):"]
        for c in corrections:
            lines.append(f"- ❌ {c['wrong_value']} → ✅ {c['right_value']} [{c['category']}] (ثقة: {c['confidence']:.0%})")

        return "\n".join(lines)

    def decay_corrections(self, days_inactive: int = 30, decay_rate: float = 0.05):
        """Decay confidence of corrections not used recently."""
        conn = self._get_conn()
        # UTC space like the columns (created_at/last_applied are SQLite
        # datetime("now")); the local T cutoff decayed corrections 3h early
        cutoff = (datetime.utcnow() - timedelta(days=days_inactive)).strftime("%Y-%m-%d %H:%M:%S")

        old_corrections = conn.execute(
            """SELECT id, confidence FROM corrections
               WHERE (last_applied IS NULL AND created_at < ?) OR last_applied < ?""",
            (cutoff, cutoff)
        ).fetchall()

        for c in old_corrections:
            new_conf = max(0.1, c["confidence"] - decay_rate)
            conn.execute("UPDATE corrections SET confidence = ? WHERE id = ?", (new_conf, c["id"]))

        conn.commit()
        decayed_count = len(old_corrections)
        conn.close()

        if decayed_count:
            logger.info(f"Decayed {decayed_count} inactive corrections")
        return decayed_count

    def get_stats(self) -> dict:
        """Get corrections statistics."""
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM corrections WHERE confidence >= 0.5").fetchone()[0]
        by_cat = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM corrections GROUP BY category ORDER BY cnt DESC"
        ).fetchall()
        most_applied = conn.execute(
            "SELECT wrong_value, right_value, times_applied FROM corrections ORDER BY times_applied DESC LIMIT 5"
        ).fetchall()
        conn.close()

        return {
            "total": total,
            "active": active,
            "by_category": {r["category"]: r["cnt"] for r in by_cat},
            "most_applied": [
                {"wrong": r["wrong_value"], "right": r["right_value"], "applied": r["times_applied"]}
                for r in most_applied
            ],
        }


# ── Singleton ────────────────────────────────────────────────
_instance = None

def get_corrections_loop(db_path: str = "data/structured_memory.db") -> CorrectionsLoop:
    global _instance
    if _instance is None:
        _instance = CorrectionsLoop(db_path)
    return _instance


# ── Convenience wrapper for chat_v7 integration ─────────────
def process_correction(user_message: str, ai_previous_response: str = "") -> dict | None:
    """Wrapper for chat_v7: detect + save correction in one call."""
    cl = get_corrections_loop()
    correction = cl.detect_correction(user_message, ai_previous_response)
    if correction:
        cl.save_correction(correction)
        return correction
    return None

def apply_corrections_to_text(text: str) -> tuple:
    """Wrapper for chat_v7: apply stored corrections to user text before LLM."""
    cl = get_corrections_loop()
    return cl.apply_corrections(text)

def get_correction_context(limit: int = 20) -> str:
    """Wrapper for brain_core: get corrections for system prompt."""
    cl = get_corrections_loop()
    return cl.get_correction_context(limit)
