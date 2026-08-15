# -*- coding: utf-8 -*-
"""
Dream Consolidator — nightly memory cleanup for Master AI.
Inspired by Claude Code's autoDream system.

Runs daily at 3 AM KWT:
1. Find exact duplicate memories → merge (keep newest)
2. Archive stale memories (>90 days, low usage) → memory_archive table
3. Compact session_log flood → keep last 30, archive rest
4. Log consolidation report

Gate chain: cheapest checks first, archive before delete.
"""

import logging
import sqlite3
import time
from datetime import datetime, timedelta

logger = logging.getLogger("dream_consolidator")

TASKS_DB = "/home/pi/master_ai/data/audit.db"

# Config
MAX_MEMORY_AGE_DAYS = 90
MIN_MEMORIES_BEFORE_CLEANUP = 50
MAX_SESSION_LOGS = 30  # keep only last 30 session_log entries


def _get_db():
    conn = sqlite3.connect(TASKS_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_archive_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_archive (
            id INTEGER,
            category TEXT,
            content TEXT,
            context TEXT,
            source TEXT,
            confidence REAL,
            hit_count INTEGER,
            last_used TEXT,
            created_at TEXT,
            user_id TEXT,
            use_count INTEGER,
            type TEXT,
            tags TEXT,
            updated_at TEXT,
            hits INTEGER,
            scope TEXT,
            archived_at TEXT DEFAULT CURRENT_TIMESTAMP,
            archive_reason TEXT DEFAULT 'dream_consolidation'
        )
    """)


async def run_dream_consolidation():
    """Main entry point — called by scheduler at 3 AM KWT."""
    logger.info("[dream] Starting nightly consolidation...")
    report = {
        "started": datetime.now().isoformat(),
        "merged": 0,
        "archived": 0,
        "session_compacted": 0,
        "kept": 0,
    }

    conn = _get_db()
    try:
        # Gate 1: Check if cleanup needed
        total = conn.execute("SELECT COUNT(*) FROM memory WHERE active=1").fetchone()[0]
        if total < MIN_MEMORIES_BEFORE_CLEANUP:
            logger.info(f"[dream] Only {total} memories, skipping cleanup")
            report["skipped"] = True
            report["total_before"] = total
            return report
        report["total_before"] = total

        _ensure_archive_table(conn)

        # Gate 2: Merge exact duplicates (same category + content)
        dupes = conn.execute("""
            SELECT category, content, COUNT(*) as cnt, GROUP_CONCAT(id) as ids
            FROM memory WHERE active=1
            GROUP BY category, content
            HAVING cnt > 1
        """).fetchall()
        for row in dupes:
            ids = [int(x) for x in row["ids"].split(",")]
            keep_id = max(ids)
            delete_ids = [x for x in ids if x != keep_id]
            # Archive duplicates before removing
            for did in delete_ids:
                conn.execute("""
                    INSERT INTO memory_archive
                    (id, category, content, context, source, confidence, hit_count,
                     last_used, created_at, user_id, use_count, type, tags,
                     updated_at, hits, scope, archive_reason)
                    SELECT id, category, content, context, source, confidence, hit_count,
                           last_used, created_at, user_id, use_count, type, tags,
                           updated_at, hits, scope, 'duplicate'
                    FROM memory WHERE id=?
                """, (did,))
            placeholders = ",".join("?" * len(delete_ids))
            conn.execute(f"DELETE FROM memory WHERE id IN ({placeholders})", delete_ids)
            # Boost the kept entry's confidence
            conn.execute(
                "UPDATE memory SET confidence=MIN(1.0, confidence+0.1), "
                "updated_at=? WHERE id=?",
                (datetime.now().isoformat(), keep_id),
            )
            report["merged"] += len(delete_ids)
            logger.debug(f"[dream] Merged {len(delete_ids)} dupes in {row['category']}")

        # Gate 3: Archive old low-usage memories (>90 days, use_count<2)
        # UTC: memory.created_at is written utcnow isoformat+Z; a local
        # cutoff archived memories 3h before their 90 days were up
        cutoff = (datetime.utcnow() - timedelta(days=MAX_MEMORY_AGE_DAYS)).isoformat()
        old_rows = conn.execute("""
            SELECT id, category FROM memory
            WHERE active=1 AND created_at < ? AND use_count < 2
              AND category != 'session_log'
            ORDER BY created_at ASC
        """, (cutoff,)).fetchall()
        archived_ids = []
        for row in old_rows:
            # Keep at least 2 per category
            remaining = conn.execute(
                "SELECT COUNT(*) FROM memory WHERE category=? AND active=1",
                (row["category"],),
            ).fetchone()[0]
            if remaining > 2:
                archived_ids.append(row["id"])
        if archived_ids:
            for aid in archived_ids:
                conn.execute("""
                    INSERT INTO memory_archive
                    (id, category, content, context, source, confidence, hit_count,
                     last_used, created_at, user_id, use_count, type, tags,
                     updated_at, hits, scope, archive_reason)
                    SELECT id, category, content, context, source, confidence, hit_count,
                           last_used, created_at, user_id, use_count, type, tags,
                           updated_at, hits, scope, 'stale'
                    FROM memory WHERE id=?
                """, (aid,))
            placeholders = ",".join("?" * len(archived_ids))
            conn.execute(f"DELETE FROM memory WHERE id IN ({placeholders})", archived_ids)
            report["archived"] = len(archived_ids)

        # Gate 4: Compact session_log flood — keep only last MAX_SESSION_LOGS
        session_count = conn.execute(
            "SELECT COUNT(*) FROM memory WHERE active=1 AND category='session_log'"
        ).fetchone()[0]
        if session_count > MAX_SESSION_LOGS:
            excess = conn.execute("""
                SELECT id FROM memory
                WHERE active=1 AND category='session_log'
                ORDER BY created_at ASC
                LIMIT ?
            """, (session_count - MAX_SESSION_LOGS,)).fetchall()
            excess_ids = [r["id"] for r in excess]
            for eid in excess_ids:
                conn.execute("""
                    INSERT INTO memory_archive
                    (id, category, content, context, source, confidence, hit_count,
                     last_used, created_at, user_id, use_count, type, tags,
                     updated_at, hits, scope, archive_reason)
                    SELECT id, category, content, context, source, confidence, hit_count,
                           last_used, created_at, user_id, use_count, type, tags,
                           updated_at, hits, scope, 'session_compact'
                    FROM memory WHERE id=?
                """, (eid,))
            placeholders = ",".join("?" * len(excess_ids))
            conn.execute(f"DELETE FROM memory WHERE id IN ({placeholders})", excess_ids)
            report["session_compacted"] = len(excess_ids)

        conn.commit()

        # Final count
        remaining = conn.execute("SELECT COUNT(*) FROM memory WHERE active=1").fetchone()[0]
        report["kept"] = remaining
        report["finished"] = datetime.now().isoformat()

        logger.info(
            f"[dream] Done: merged={report['merged']}, archived={report['archived']}, "
            f"session_compacted={report['session_compacted']}, kept={report['kept']}"
        )

    except Exception as e:
        logger.error(f"[dream] Consolidation failed: {e}", exc_info=True)
        report["error"] = str(e)
    finally:
        conn.close()

    return report


async def get_dream_status():
    """Get current memory health stats for TG /dream command."""
    conn = _get_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM memory WHERE active=1").fetchone()[0]
        by_category = dict(conn.execute(
            "SELECT category, COUNT(*) FROM memory WHERE active=1 GROUP BY category ORDER BY COUNT(*) DESC"
        ).fetchall())

        now = datetime.utcnow()  # memory.created_at is UTC (isoformat+Z)
        fresh = conn.execute(
            "SELECT COUNT(*) FROM memory WHERE active=1 AND created_at > ?",
            ((now - timedelta(days=1)).isoformat(),),
        ).fetchone()[0]
        recent = conn.execute(
            "SELECT COUNT(*) FROM memory WHERE active=1 AND created_at > ? AND created_at <= ?",
            ((now - timedelta(days=7)).isoformat(), (now - timedelta(days=1)).isoformat()),
        ).fetchone()[0]

        # Duplicates
        dupes = conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT category, content FROM memory WHERE active=1
                GROUP BY category, content HAVING COUNT(*) > 1
            )
        """).fetchone()[0]

        # Archive stats
        archived = 0
        try:
            archived = conn.execute("SELECT COUNT(*) FROM memory_archive").fetchone()[0]
        except Exception:
            pass

        return {
            "total": total,
            "by_category": by_category,
            "fresh_24h": fresh,
            "recent_7d": recent,
            "old": total - fresh - recent,
            "duplicates": dupes,
            "archived_total": archived,
        }
    finally:
        conn.close()


def format_dream_status(status: dict) -> str:
    """Format dream status for Telegram."""
    lines = [
        "🧠 حالة الذاكرة (Dream):",
        f"",
        f"📊 إجمالي: {status['total']} ذاكرة نشطة",
        f"  🟢 جديد (24h): {status['fresh_24h']}",
        f"  🔵 أسبوع: {status['recent_7d']}",
        f"  ⚪ قديم: {status['old']}",
    ]
    if status["duplicates"] > 0:
        lines.append(f"  ⚠️ مكررات: {status['duplicates']}")
    if status["archived_total"] > 0:
        lines.append(f"  🗄 أرشيف: {status['archived_total']}")

    lines.append("")
    lines.append("📂 التصنيفات:")
    for cat, cnt in status.get("by_category", {}).items():
        lines.append(f"  • {cat}: {cnt}")

    return "\n".join(lines)
