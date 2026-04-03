# Round 2 Implementation Plan — Dream Consolidator + Tips + Speculation
# Date: 2026-04-03
# Source: _tools/CLAUDE_CODE_SOURCE_ANALYSIS_ROUND2.md
# For: Claude Code execution
# Pre-req: Round 1 complete (21/21 patterns + 7 integrations)

---

## Overview: 3 High-Impact Patterns from Round 2 Analysis

Based on the Round 2 source analysis, implement these 3 patterns in order:

### Pattern R1: Dream Consolidator (from autoDream/)
### Pattern R2: Smart Tips System (from services/tips/)
### Pattern R3: Tool Usage Summary (from toolUseSummary/)

Speculation (pre-execution) is too complex for now — skip it.
PromptSuggestion is UI-dependent — skip for Telegram bot.
AgentSummary is already partially covered by session_memory.py.

---

## Pattern R1: Dream Consolidator

### What
Background job that runs once daily (3 AM KWT). Analyzes brain_observations:
- Merges duplicate/similar observations about the same entity
- Archives observations older than 90 days with no recent relevance
- Generates a "consolidation report" logged to DB

### Why
brain_observations has 178 entries, ALL marked "old". Without cleanup,
this table will grow forever and memory_recall will get slower/noisier.

### New File: `dream_consolidator.py`

```python
"""
Dream Consolidator — nightly Brain observation cleanup.
Inspired by Claude Code's autoDream system.

Runs daily at 3 AM KWT:
1. Find duplicate observations (same entity + similar text)
2. Merge duplicates (keep newest, combine insights)
3. Archive stale observations (>90 days, no recent hits)
4. Log consolidation report

Uses gate chain: cheap checks first, LLM only if needed.
"""

import asyncio
import logging
import sqlite3
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Config
MAX_OBSERVATION_AGE_DAYS = 90
SIMILARITY_THRESHOLD = 0.8  # for duplicate detection
MIN_OBSERVATIONS_BEFORE_CLEANUP = 50

def get_db():
    import os
    return sqlite3.connect(os.path.expanduser("~/master_ai/data/life.db"))

async def run_dream_consolidation():
    """Main entry point — called by scheduler at 3 AM."""
    logger.info("[dream] Starting nightly consolidation...")
    conn = get_db()
    report = {"started": datetime.now().isoformat(), "merged": 0, "archived": 0, "kept": 0}

    try:
        # Gate 1: Check if cleanup needed (cheapest check)
        total = conn.execute("SELECT COUNT(*) FROM brain_observations").fetchone()[0]
        if total < MIN_OBSERVATIONS_BEFORE_CLEANUP:
            logger.info(f"[dream] Only {total} observations, skipping cleanup")
            report["skipped"] = True
            return report

        # Gate 2: Find exact duplicates (same entity_id + same observation text)
        dupes = conn.execute("""
            SELECT entity_id, observation, COUNT(*) as cnt, GROUP_CONCAT(rowid) as ids
            FROM brain_observations
            GROUP BY entity_id, observation
            HAVING cnt > 1
        """).fetchall()
        for entity_id, obs_text, cnt, ids_str in dupes:
            ids = [int(x) for x in ids_str.split(',')]
            # Keep the newest (highest rowid), delete the rest
            keep_id = max(ids)
            delete_ids = [x for x in ids if x != keep_id]
            conn.execute(
                f"DELETE FROM brain_observations WHERE rowid IN ({','.join('?' * len(delete_ids))})",
                delete_ids
            )
            report["merged"] += len(delete_ids)
            logger.debug(f"[dream] Merged {len(delete_ids)} dupes for {entity_id}")

        # Gate 3: Archive old observations (>90 days)
        cutoff = (datetime.now() - timedelta(days=MAX_OBSERVATION_AGE_DAYS)).isoformat()
        old_rows = conn.execute("""
            SELECT rowid, entity_id, observation, timestamp
            FROM brain_observations
            WHERE timestamp < ?
            ORDER BY timestamp ASC
        """, (cutoff,)).fetchall()

        if old_rows:
            # Don't delete all old ones — keep at least 2 per entity
            entity_counts = {}
            to_archive = []
            for rowid, entity_id, obs, ts in old_rows:
                entity_counts[entity_id] = entity_counts.get(entity_id, 0) + 1
                total_for_entity = conn.execute(
                    "SELECT COUNT(*) FROM brain_observations WHERE entity_id = ?",
                    (entity_id,)
                ).fetchone()[0]
                if total_for_entity > 2:
                    to_archive.append(rowid)

            if to_archive:
                # Archive: move to brain_observations_archive (create if needed)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS brain_observations_archive (
                        rowid INTEGER, entity_id TEXT, entity_domain TEXT,
                        observation TEXT, scope TEXT, timestamp TEXT,
                        archived_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                for rid in to_archive:
                    conn.execute("""
                        INSERT INTO brain_observations_archive
                        SELECT rowid, entity_id, entity_domain, observation, scope, timestamp, datetime('now')
                        FROM brain_observations WHERE rowid = ?
                    """, (rid,))
                conn.execute(
                    f"DELETE FROM brain_observations WHERE rowid IN ({','.join('?' * len(to_archive))})",
                    to_archive
                )
                report["archived"] = len(to_archive)

        # Count remaining
        remaining = conn.execute("SELECT COUNT(*) FROM brain_observations").fetchone()[0]
        report["kept"] = remaining
        report["finished"] = datetime.now().isoformat()

        conn.commit()
        logger.info(f"[dream] Consolidation done: merged={report['merged']}, archived={report['archived']}, kept={report['kept']}")

    except Exception as e:
        logger.error(f"[dream] Consolidation failed: {e}")
        report["error"] = str(e)
    finally:
        conn.close()

    return report


# For manual trigger via Telegram: /dream or /تنظيف
async def get_dream_status():
    """Get current Brain health stats."""
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM brain_observations").fetchone()[0]
    by_scope = dict(conn.execute(
        "SELECT scope, COUNT(*) FROM brain_observations GROUP BY scope"
    ).fetchall())

    # Age distribution
    now = datetime.now()
    fresh = conn.execute(
        "SELECT COUNT(*) FROM brain_observations WHERE timestamp > ?",
        ((now - timedelta(days=1)).isoformat(),)
    ).fetchone()[0]
    recent = conn.execute(
        "SELECT COUNT(*) FROM brain_observations WHERE timestamp > ? AND timestamp <= ?",
        ((now - timedelta(days=7)).isoformat(), (now - timedelta(days=1)).isoformat())
    ).fetchone()[0]

    # Check archive
    archived = 0
    try:
        archived = conn.execute("SELECT COUNT(*) FROM brain_observations_archive").fetchone()[0]
    except:
        pass

    conn.close()
    return {
        "total": total, "by_scope": by_scope,
        "fresh_24h": fresh, "recent_7d": recent, "old": total - fresh - recent,
        "archived_total": archived,
    }
```

### Scheduler Integration (in server.py):
```python
# Add to scheduled tasks (alongside KAIROS, news, etc.)
from dream_consolidator import run_dream_consolidation

# Schedule at 3 AM KWT daily
scheduler.add_job(run_dream_consolidation, 'cron', hour=3, minute=0)
```

### API Endpoint (in dashboard_api.py):
```python
@app.get("/api/dream/status")
async def dream_status():
    from dream_consolidator import get_dream_status
    return await get_dream_status()

@app.post("/api/dream/run")
async def dream_run_now():
    from dream_consolidator import run_dream_consolidation
    report = await run_dream_consolidation()
    return report
```

### Telegram Command: /dream or /تنظيف
Shows Brain health + last consolidation report.

### Commit: `feat: add Dream Consolidator for nightly Brain cleanup (R2-P1)`

---

## Pattern R2: Smart Tips System

### What
Context-aware tips shown in Telegram after certain conditions.
Each tip has: content, isRelevant() check, cooldown, priority.
Shown max 1 per session, picked by "least recently shown".

### Why
The user doesn't know about all Master AI features.
Tips like "هل تعلم؟ تقدر تقول /تحليل EQUIPMENT" teach new commands.

### New File: `tips_engine.py`

```python
"""
Smart Tips Engine — context-aware tips for the user.
Inspired by Claude Code's services/tips/ system.

Each tip has:
- content (Arabic text)
- is_relevant(context) — function that checks if tip applies NOW
- cooldown_hours — minimum hours between showing same tip
- category — trading / ha / system / general

Tips are shown max 1 per Telegram session.
Selection: filter relevant → remove recently shown → pick oldest shown.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

@dataclass
class Tip:
    id: str
    content: str
    category: str = "general"
    cooldown_hours: int = 24
    is_relevant: Callable = lambda ctx: True
    last_shown: float = 0

    def can_show(self) -> bool:
        if self.cooldown_hours <= 0:
            return True
        elapsed_h = (time.time() - self.last_shown) / 3600
        return elapsed_h >= self.cooldown_hours


# === TIP DEFINITIONS ===
def _make_tips() -> list:
    tips = []

    # Trading tips
    tips.append(Tip(
        id="tip_analyze",
        content="💡 هل تعلم؟ أرسل /تحليل EQUIPMENT وأحلل لك السهم بالتفصيل مع Gemini",
        category="trading",
        cooldown_hours=72,
    ))
    tips.append(Tip(
        id="tip_review",
        content="💡 أرسل /تقييم عشان أعطيك مراجعة إشارات أمس — شنو نجح وشنو فشل",
        category="trading",
        cooldown_hours=72,
    ))
    tips.append(Tip(
        id="tip_momentum",
        content="💡 /موجة يعطيك الأسهم القوية الحين — بغض النظر عن نسبة النجاح",
        category="trading",
        cooldown_hours=72,
    ))
    tips.append(Tip(
        id="tip_brain",
        content="💡 /brain يوريك شنو تعلمت من السوق — أوزان المؤشرات وأفضل الأنماط",
        category="trading",
        cooldown_hours=72,
    ))
    tips.append(Tip(
        id="tip_news",
        content="💡 /أخبار يجيب لك آخر أخبار البورصة + اقتصاد + تقنية من Gemini",
        category="trading",
        cooldown_hours=48,
    ))

    # System tips
    tips.append(Tip(
        id="tip_kairos",
        content="💡 KAIROS يراقب صحة النظام كل 5 دقائق ويرسل تنبيه لو شي طاح",
        category="system",
        cooldown_hours=168,  # weekly
    ))
    tips.append(Tip(
        id="tip_dream",
        content="💡 كل ليلة الساعة 3 الفجر، نظام Dream ينظف الذاكرة من الملاحظات المكررة والقديمة",
        category="system",
        cooldown_hours=168,
    ))
    tips.append(Tip(
        id="tip_dashboard",
        content="💡 صفحة النظام بالداشبورد تبيّن: تعلم تلقائي، تحليل الأوامر، صحة السياق",
        category="system",
        cooldown_hours=168,
    ))

    # HA tips
    tips.append(Tip(
        id="tip_report",
        content="💡 /report يعطيك تقرير الصباح — الشفت + الطقس + حالة البيت",
        category="ha",
        cooldown_hours=48,
    ))

    # Learning tips (context-dependent)
    tips.append(Tip(
        id="tip_memory",
        content="💡 أنا أتعلم من محادثاتنا — كل ما تقول رأيك عن سهم أو جهاز، أسجله تلقائياً",
        category="general",
        cooldown_hours=72,
        is_relevant=lambda ctx: ctx.get("message_count", 0) >= 5,
    ))
    tips.append(Tip(
        id="tip_bridge_offline",
        content="⚠️ البريدج مو متصل — شغّل start_bridge.bat على الكمبيوتر عشان التحليل والرادار يشتغلون",
        category="system",
        cooldown_hours=4,
        is_relevant=lambda ctx: not ctx.get("bridge_online", True),
    ))

    return tips


class TipsEngine:
    def __init__(self):
        self._tips = _make_tips()
        self._shown_this_session = False

    def get_tip(self, context: dict = None) -> Optional[str]:
        """Get a relevant tip for the current context. Returns None if no tip or already shown."""
        if self._shown_this_session:
            return None

        context = context or {}

        # Filter: relevant + can_show (cooldown)
        candidates = [t for t in self._tips if t.is_relevant(context) and t.can_show()]
        if not candidates:
            return None

        # Pick: least recently shown
        candidates.sort(key=lambda t: t.last_shown)
        tip = candidates[0]

        # Mark as shown
        tip.last_shown = time.time()
        self._shown_this_session = True

        logger.info(f"[tips] Showing tip: {tip.id}")
        return tip.content

    def reset_session(self):
        """Call at start of each new Telegram conversation/session."""
        self._shown_this_session = False

    def get_all_tips(self) -> list:
        """For dashboard/API."""
        return [{"id": t.id, "content": t.content, "category": t.category,
                 "cooldown_h": t.cooldown_hours, "can_show": t.can_show()} for t in self._tips]
```

### Integration in server.py TG handler:
```python
from tips_engine import TipsEngine
_tips = TipsEngine()

# In message handler, AFTER sending the response:
tip = _tips.get_tip(context={
    "bridge_online": is_bridge_online(),
    "message_count": session_message_count,
})
if tip:
    await tg_send(chat_id, f"\n\n{tip}")
```

### API Endpoint:
```python
@app.get("/api/tips")
async def list_tips():
    return {"tips": _tips.get_all_tips()}
```

### Commit: `feat: add Smart Tips engine with 11 context-aware tips (R2-P2)`

---

## Pattern R3: Tool Usage Summary

### What
After each Telegram command that uses tools (analyze, radar refresh, etc.),
generate a 1-line summary using Haiku: "حلل EQUIPMENT — RSI 41, EMA مختلط, انتظار"

### Why
Long tool outputs are noisy. A 1-line summary at the top helps.

### New File: `tool_summary.py`

```python
"""
Tool Usage Summary — generate short labels for tool operations.
Inspired by Claude Code's toolUseSummary system.

Uses Haiku to generate a 3-8 word Arabic summary of what a tool did.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """Generate a very short Arabic summary (5-10 words max) of this tool operation result.
Focus on: what was analyzed, key finding, and verdict.
Examples:
- "حلل EQUIPMENT — RSI 41, انتظار"
- "رادار: 3 إشارات جديدة، CLEANING أقوى"
- "أخبار: 12 خبر جديد، 2 مهم"
Return ONLY the summary text, nothing else."""


async def generate_summary(tool_name: str, tool_output: str) -> Optional[str]:
    """Generate a 1-line summary of a tool operation."""
    if not tool_output or len(tool_output) < 20:
        return None

    try:
        import anthropic
        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            system=SUMMARY_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Tool: {tool_name}\nOutput:\n{tool_output[:1000]}"
            }]
        )
        summary = response.content[0].text.strip()
        logger.debug(f"[summary] {tool_name}: {summary}")
        return summary
    except Exception as e:
        logger.warning(f"[summary] Failed: {e}")
        return None
```

### Integration:
```python
# After tool execution in tg_intent_router or chat_v7:
from tool_summary import generate_summary

# When tool result is long (>500 chars):
if len(tool_result) > 500:
    summary = await generate_summary(tool_name, tool_result)
    if summary:
        final_response = f"📋 {summary}\n\n{tool_result}"
```

### Commit: `feat: add tool usage summary with Haiku labels (R2-P3)`

---

## Execution Order
```
1. Read this entire plan
2. Pattern R1 (Dream Consolidator):
   - Create dream_consolidator.py
   - Add scheduler job in server.py
   - Add /api/dream/status and /api/dream/run endpoints
   - Add /تنظيف Telegram command
   - quick_check.py + smoke_test.py
   - git commit
3. Pattern R2 (Tips Engine):
   - Create tips_engine.py
   - Wire into TG message handler in server.py
   - Add /api/tips endpoint
   - quick_check.py
   - git commit
4. Pattern R3 (Tool Summary):
   - Create tool_summary.py
   - Wire into tg_intent_router.py for long responses
   - quick_check.py
   - git commit
5. restart_master_ai.sh
6. Report results
```

## Critical Notes
- Dream Consolidator: DO NOT delete observations without archiving first
- Tips: max 1 per session, don't spam the user
- Tool Summary: only for long outputs (>500 chars), don't add cost for short responses
- All 3 use Haiku for LLM calls (cheapest model) — check ANTHROPIC_API_KEY
- If any pattern fails, commit what works and note the issue
