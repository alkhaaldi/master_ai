# Tier 2 Implementation Plan — Structured Improvements
# Date: 2026-04-02
# For: Claude Code (RPi) execution
# Pre-requisite: Tier 1 COMPLETE (commits 9b16934 through e696655)
# Reference: _tools/CLAUDE_CODE_SOURCE_ANALYSIS_P1_P2.md (full analysis)

---

## Overview: 7 Patterns, implement in order

Tier 1 gave us safety nets (circuit breakers, staleness warnings, cleanup).
Tier 2 gives us INTELLIGENCE (smart memory recall, task visibility, tool structure).

Dependencies:
- #8 (Task State Machine) — independent, do first
- #9 (Memory Index) — independent, do second  
- #10 (LLM-Ranked Recall) — DEPENDS ON #9
- #11 (Tool Interface) — builds on Tier 1 #5 (tool_registry.py)
- #12 (Coalesced Execution) — builds on Tier 1 #3 (circuit_breaker.py)
- #13 (Cron Routing) — independent
- #14 (Session Summary) — independent

---

## Pattern #8: Typed Task State Machine

### What
Formalize all background operations as typed tasks with status tracking.
Currently: ad-hoc async operations with no visibility into what's running.
After: every background op is a tracked task with status, progress, timing.

### New File: `task_manager.py`

```python
"""
Task State Machine for Master AI background operations.

Each background operation (radar refresh, Bridge polling, news fetch, etc.)
is registered as a typed task with lifecycle tracking.

Task States: PENDING → RUNNING → COMPLETED / FAILED / CANCELLED
"""

import asyncio
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable, Awaitable
import logging

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(Enum):
    RADAR_REFRESH = "radar_refresh"
    BRIDGE_POLL = "bridge_poll"
    DAILY_SNAPSHOT = "daily_snapshot"
    NEWS_FETCH = "news_fetch"
    SIGNAL_ALERT = "signal_alert"
    PATTERN_LEARNING = "pattern_learning"
    NIGHTLY_DIGEST = "nightly_digest"
    WEEKLY_INSIGHT = "weekly_insight"
    MORNING_REPORT = "morning_report"


@dataclass
class TaskState:
    task_id: str
    task_type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    progress: Optional[str] = None  # e.g., "45/128 stocks"
    result: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> Optional[int]:
        if self.started_at is None:
            return None
        end = self.completed_at or time.time()
        return int((end - self.started_at) * 1000)

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        )

    def to_status_line(self) -> str:
        """One-line status for Telegram /status command."""
        icons = {
            TaskStatus.PENDING: "⏳",
            TaskStatus.RUNNING: "🟢",
            TaskStatus.COMPLETED: "✅",
            TaskStatus.FAILED: "🔴",
            TaskStatus.CANCELLED: "⚪",
        }
        icon = icons.get(self.status, "❓")
        line = f"{icon} {self.task_type.value}: {self.status.value}"
        if self.progress:
            line += f" ({self.progress})"
        if self.duration_ms is not None and self.is_terminal:
            line += f" [{self.duration_ms}ms]"
        if self.error:
            line += f" — {self.error[:80]}"
        return line


class TaskManager:
    """
    Singleton task manager. Tracks all background operations.
    
    Usage:
        tm = TaskManager.instance()
        task = tm.create_task(TaskType.RADAR_REFRESH)
        tm.start_task(task.task_id)
        tm.update_progress(task.task_id, "45/128 stocks")
        tm.complete_task(task.task_id, result="128 stocks analyzed")
        # or
        tm.fail_task(task.task_id, error="Bridge offline")
    """

    _instance = None

    @classmethod
    def instance(cls) -> "TaskManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._tasks: Dict[str, TaskState] = {}
        self._counter = 0
        self._max_history = 50  # keep last 50 completed tasks

    def create_task(
        self, task_type: TaskType, metadata: Optional[Dict] = None
    ) -> TaskState:
        self._counter += 1
        task_id = f"{task_type.value}_{self._counter}_{int(time.time())}"
        task = TaskState(
            task_id=task_id,
            task_type=task_type,
            metadata=metadata or {},
        )
        self._tasks[task_id] = task
        self._cleanup_old_tasks()
        return task

    def start_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task and not task.is_terminal:
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()

    def update_progress(self, task_id: str, progress: str) -> None:
        task = self._tasks.get(task_id)
        if task and task.status == TaskStatus.RUNNING:
            task.progress = progress

    def complete_task(
        self, task_id: str, result: Optional[str] = None
    ) -> None:
        task = self._tasks.get(task_id)
        if task and not task.is_terminal:
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            task.result = result

    def fail_task(self, task_id: str, error: str) -> None:
        task = self._tasks.get(task_id)
        if task and not task.is_terminal:
            task.status = TaskStatus.FAILED
            task.completed_at = time.time()
            task.error = error

    def cancel_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task and not task.is_terminal:
            task.status = TaskStatus.CANCELLED
            task.completed_at = time.time()

    def get_running_tasks(self) -> list:
        return [
            t for t in self._tasks.values()
            if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
        ]

    def get_status_summary(self) -> str:
        """Full status for /status command or dashboard."""
        running = self.get_running_tasks()
        if not running:
            return "No active tasks"
        return "\n".join(t.to_status_line() for t in running)

    def get_recent_tasks(self, n: int = 10) -> list:
        """Last N tasks (any status) for audit/dashboard."""
        all_tasks = sorted(
            self._tasks.values(),
            key=lambda t: t.created_at,
            reverse=True,
        )
        return all_tasks[:n]

    def _cleanup_old_tasks(self) -> None:
        """Remove old completed tasks to prevent memory growth."""
        terminal = [
            t for t in self._tasks.values() if t.is_terminal
        ]
        if len(terminal) > self._max_history:
            terminal.sort(key=lambda t: t.completed_at or 0)
            for t in terminal[: len(terminal) - self._max_history]:
                del self._tasks[t.task_id]
```

### Integration Points (modify existing files)

In `server.py` — wrap existing background operations:
```python
# BEFORE (current):
async def refresh_radar():
    results = await stock_radar.refresh_all()
    return results

# AFTER:
async def refresh_radar():
    tm = TaskManager.instance()
    task = tm.create_task(TaskType.RADAR_REFRESH)
    tm.start_task(task.task_id)
    try:
        results = await stock_radar.refresh_all(
            on_progress=lambda p: tm.update_progress(task.task_id, p)
        )
        tm.complete_task(task.task_id, result=f"{len(results)} stocks")
        return results
    except Exception as e:
        tm.fail_task(task.task_id, error=str(e))
        raise
```

In `stock_radar.py` — add progress callback:
```python
# Add on_progress parameter to refresh_all()
async def refresh_all(on_progress=None):
    for i, stock in enumerate(stocks):
        if on_progress:
            on_progress(f"{i+1}/{len(stocks)} stocks")
        # ... existing logic
```

Add `/status` endpoint or Telegram command:
```python
# In dashboard_api.py or server.py
@app.get("/api/tasks")
async def get_tasks():
    tm = TaskManager.instance()
    return {
        "running": [vars(t) for t in tm.get_running_tasks()],
        "recent": [vars(t) for t in tm.get_recent_tasks(10)],
    }
```

### Test
```bash
quick_check.py  # import test
# Then trigger a radar refresh and check /api/tasks shows it
```

### Commit message
`feat: add TaskManager for background operation tracking (#8 Tier2)`

---

## Pattern #9: Lightweight Memory Index (Brain Header Scan)

### What
Build a fast "manifest" of Brain observations — one-liner per observation
with type + timestamp + summary. This is what gets sent to LLM for ranking
in Pattern #10 (NOT the full observation text).

### Changes to: `brain_core.py`

Add these functions:

```python
def get_observation_manifest(
    entity_domain: str = None,
    max_items: int = 200,
) -> list[dict]:
    """
    Return lightweight observation headers for LLM ranking.
    Each item: {id, entity_id, domain, summary (first 100 chars), age_str, timestamp}
    Sorted newest-first, capped at max_items.
    
    This is the "table of contents" — NOT the full observation text.
    Full text is loaded only AFTER LLM selects relevant items.
    """
    conn = get_db_connection()
    query = """
        SELECT id, entity_id, entity_domain, 
               SUBSTR(observation, 1, 100) as summary,
               timestamp
        FROM brain_observations
        {where_clause}
        ORDER BY timestamp DESC
        LIMIT ?
    """
    where_clause = ""
    params = []
    if entity_domain:
        where_clause = "WHERE entity_domain = ?"
        params.append(entity_domain)
    params.append(max_items)
    
    rows = conn.execute(
        query.format(where_clause=where_clause), params
    ).fetchall()
    
    result = []
    for row in rows:
        result.append({
            "id": row["id"],
            "entity_id": row["entity_id"],
            "domain": row["entity_domain"],
            "summary": row["summary"],
            "age_str": memory_age(row["timestamp"]),  # from Tier 1
            "timestamp": row["timestamp"],
        })
    return result


def format_observation_manifest(observations: list[dict]) -> str:
    """
    Format observations as a text manifest for LLM ranking.
    One line per observation: [domain] entity (age): summary...
    
    Example:
    - [trading] CLEANING (3 days ago): نمط صعودي مع RSI فوق 60
    - [trading] SENERGY (today): إشارة شراء من golden engine
    - [climate] bedroom_ac (5 days ago): الحرارة تتجاوز 23 بالليل
    """
    lines = []
    for obs in observations:
        line = f"- [{obs['domain']}] {obs['entity_id']} ({obs['age_str']}): {obs['summary']}"
        lines.append(line)
    return "\n".join(lines)


def get_full_observations(observation_ids: list[int]) -> list[dict]:
    """
    Load full observation text for selected IDs only.
    Called AFTER LLM selects relevant items from the manifest.
    """
    if not observation_ids:
        return []
    conn = get_db_connection()
    placeholders = ",".join("?" * len(observation_ids))
    rows = conn.execute(
        f"SELECT * FROM brain_observations WHERE id IN ({placeholders})",
        observation_ids,
    ).fetchall()
    return [dict(r) for r in rows]
```

### Test
```python
# In Python REPL on RPi:
from brain_core import get_observation_manifest, format_observation_manifest
manifest = get_observation_manifest(max_items=10)
print(format_observation_manifest(manifest))
# Should show 10 one-liners like:
# - [trading] CLEANING (3 days ago): نمط صعودي مع RSI فوق 60
```

### Commit message
`feat: add lightweight observation manifest for LLM ranking (#9 Tier2)`

---

## Pattern #10: LLM-Ranked Memory Recall

### What
Use Haiku to select the most relevant Brain observations for a given query.
Instead of returning ALL observations or NONE, return the TOP 5 most relevant.

### DEPENDS ON: Pattern #9 (manifest functions)

### New File: `memory_recall.py`

```python
"""
LLM-Ranked Memory Recall for Master AI.

Given a user query/intent, uses Haiku to select the most relevant
Brain observations from the manifest (Pattern #9).

Based on Claude Code's findRelevantMemories.ts pattern:
- Scan manifest (lightweight headers only)
- Ask LLM to select top 5 most relevant
- Load full text only for selected items
- Tag stale items with warnings (Tier 1 staleness)
"""

import json
import logging
import anthropic  # or use existing LLM client
from brain_core import (
    get_observation_manifest,
    format_observation_manifest,
    get_full_observations,
    format_staleness_warning,  # from Tier 1
)

logger = logging.getLogger(__name__)

SELECT_MEMORIES_PROMPT = """You are selecting observations that will be useful for answering a user's query.
You will be given the query and a list of available observations with their summaries.

Return a JSON object with a "selected_ids" array containing the IDs of observations 
that will clearly be useful (up to 5). Only include observations you are certain 
will be helpful based on their summary and domain.

- If unsure, do not include it. Be selective.
- If nothing is clearly relevant, return an empty list.
- Prefer recent observations over old ones when relevance is similar.

Return ONLY valid JSON: {"selected_ids": [1, 5, 23]}
"""


async def find_relevant_memories(
    query: str,
    entity_domain: str = None,
    max_candidates: int = 200,
    max_selected: int = 5,
    already_surfaced: set = None,
) -> list[dict]:
    """
    Find the most relevant Brain observations for a query.
    
    Args:
        query: User's question or intent
        entity_domain: Optional filter (e.g., "trading", "climate")
        max_candidates: Max observations to consider
        max_selected: Max observations to return (default 5)
        already_surfaced: Set of observation IDs already shown (dedup)
    
    Returns:
        List of full observation dicts, each tagged with staleness warning
    """
    already_surfaced = already_surfaced or set()
    
    # Step 1: Get lightweight manifest
    manifest = get_observation_manifest(
        entity_domain=entity_domain,
        max_items=max_candidates,
    )
    
    # Filter already-surfaced
    manifest = [m for m in manifest if m["id"] not in already_surfaced]
    
    if not manifest:
        return []
    
    # Step 2: Format manifest for LLM
    manifest_text = format_observation_manifest(manifest)
    valid_ids = {m["id"] for m in manifest}
    
    # Step 3: Ask Haiku to select relevant observations
    try:
        # Use whatever LLM client Master AI has (anthropic SDK, etc.)
        # This should be the CHEAPEST model available (Haiku)
        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=SELECT_MEMORIES_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Query: {query}\n\nAvailable observations:\n{manifest_text}",
            }],
        )
        
        # Parse response
        text = response.content[0].text.strip()
        # Clean potential markdown fences
        text = text.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(text)
        selected_ids = parsed.get("selected_ids", [])
        
        # Validate: only keep IDs that exist in manifest
        selected_ids = [id for id in selected_ids if id in valid_ids]
        selected_ids = selected_ids[:max_selected]
        
    except Exception as e:
        logger.warning(f"[memory_recall] LLM selection failed: {e}")
        # Fallback: return most recent observations
        selected_ids = [m["id"] for m in manifest[:max_selected]]
    
    if not selected_ids:
        return []
    
    # Step 4: Load full observations for selected IDs only
    full_observations = get_full_observations(selected_ids)
    
    # Step 5: Tag with staleness warnings (from Tier 1)
    for obs in full_observations:
        obs["staleness_warning"] = format_staleness_warning(obs["timestamp"])
    
    return full_observations
```

### Integration: Use in chat_v7.py or tg_intent_router.py

```python
# When handling a user query that might benefit from memory:
async def handle_query_with_memory(query: str, context: dict):
    # Get relevant memories (non-blocking, fast)
    memories = await find_relevant_memories(
        query=query,
        already_surfaced=context.get("surfaced_ids", set()),
    )
    
    if memories:
        memory_context = "\n\n".join([
            f"📝 {m['entity_id']} ({m.get('staleness_warning', '')}): {m['observation']}"
            for m in memories
        ])
        # Prepend to LLM context
        enhanced_query = f"Relevant observations:\n{memory_context}\n\nUser query: {query}"
    else:
        enhanced_query = query
    
    # Continue with normal processing...
```

### Test
```python
# Test the manifest
manifest = get_observation_manifest(max_items=5)
print(format_observation_manifest(manifest))

# Test the recall
memories = await find_relevant_memories("شلون CLEANING اليوم؟")
for m in memories:
    print(f"[{m['entity_id']}] {m['observation'][:100]}")
    print(f"  {m['staleness_warning']}")
```

### Note on API Key
memory_recall.py needs access to Anthropic API. Options:
1. Use existing API key from .env (if Master AI already calls Claude)
2. Use the HA-based LLM integration
3. Hardcode to use server.py's existing LLM client

Check what's available: `grep -r "anthropic\|claude\|haiku" server.py chat_v7.py`

### Commit message
`feat: add LLM-ranked memory recall using Haiku (#10 Tier2)`

---

## Pattern #11: Typed Tool Interface (MasterAITool class)

### What
Extend the tool_registry.py from Tier 1 (#5) with a proper Tool base class.
Each command gets declared properties that the system uses for autonomy scoring,
error handling, and resource management.

### Changes to: `tool_registry.py`

```python
"""
Extend tool_registry.py with MasterAITool base class.
Builds on Tier 1's 3-layer validation pattern.
"""

from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable, Any
from enum import Enum


class ToolCategory(Enum):
    QUERY = "query"          # Read-only lookups
    ANALYSIS = "analysis"    # Compute-intensive analysis
    ACTION = "action"        # Modifies state
    SYSTEM = "system"        # System management


@dataclass
class MasterAITool:
    """Base tool definition with properties for autonomy and resource management."""
    
    name: str                           # e.g., "فرص", "تقييم", "report"
    description: str                    # Human-readable description
    category: ToolCategory = ToolCategory.QUERY
    
    # Flags (fail-closed defaults, same as Claude Code)
    is_read_only: bool = False          # True = no state changes
    is_destructive: bool = False        # True = irreversible action
    requires_bridge: bool = False       # True = needs Bridge API online
    requires_llm: bool = False          # True = needs LLM API call
    
    # Resource limits
    max_result_chars: int = 4000        # Telegram message limit
    timeout_seconds: int = 60           # Max execution time
    
    # Autonomy scoring
    autonomy_cost: int = 10             # Base cost for policy scoring
    
    # Handler (set during registration)
    handler: Optional[Callable] = None
    
    @property
    def computed_autonomy_cost(self) -> int:
        """Auto-compute cost from flags if not explicitly set."""
        cost = self.autonomy_cost
        if self.is_destructive:
            cost = max(cost, 50)
        if self.requires_llm:
            cost += 10
        if not self.is_read_only:
            cost += 5
        return cost
    
    def can_execute(self, context: dict) -> tuple[bool, str]:
        """Pre-flight check: can this tool run right now?"""
        if self.requires_bridge and not context.get("bridge_online", False):
            return False, "البريدج مو متصل"
        if self.requires_llm and not context.get("llm_available", True):
            return False, "خدمة الذكاء الاصطناعي غير متاحة"
        return True, ""


# Tool registry with typed tools
TOOLS: dict[str, MasterAITool] = {}


def register_tool(tool: MasterAITool) -> Callable:
    """Decorator-compatible tool registration."""
    def decorator(func):
        tool.handler = func
        TOOLS[tool.name] = tool
        return func
    return decorator


# Example registrations:
# (These go in the respective handler files or in a central registry)

TOOL_DEFS = {
    "فرص": MasterAITool(
        name="فرص", description="Golden opportunities scanner",
        category=ToolCategory.ANALYSIS,
        is_read_only=True, requires_bridge=True,
        autonomy_cost=15, timeout_seconds=120,
    ),
    "تقييم": MasterAITool(
        name="تقييم", description="Signal review/evaluation",
        category=ToolCategory.ANALYSIS,
        is_read_only=True, requires_bridge=True,
        autonomy_cost=15,
    ),
    "report": MasterAITool(
        name="report", description="Morning/status report",
        category=ToolCategory.QUERY,
        is_read_only=True, requires_bridge=False,
        autonomy_cost=5,
    ),
    "status": MasterAITool(
        name="status", description="System status check",
        category=ToolCategory.QUERY,
        is_read_only=True, autonomy_cost=3,
    ),
    "موجة": MasterAITool(
        name="موجة", description="Elliott Wave analysis",
        category=ToolCategory.ANALYSIS,
        is_read_only=True, requires_bridge=True, requires_llm=True,
        autonomy_cost=25, timeout_seconds=90,
    ),
}
```

### Integration
Update tg_intent_router.py to check `tool.can_execute(context)` before running,
and use `tool.max_result_chars` for response truncation.

### Commit message
`feat: add MasterAITool class with autonomy flags (#11 Tier2)`

---

## Pattern #12: Coalesced Background Execution

### What
When a background operation (Bridge poll, radar refresh) is already running
and a new request comes in: don't start a second one. Stash the request,
run ONE trailing execution after the current one finishes.

### Changes to: `server.py` (or specific engine files)

```python
"""
Coalesced execution wrapper. Prevents overlapping background operations.
Builds on circuit_breaker.py from Tier 1.
"""

import asyncio
from typing import Optional, Callable, Awaitable, Any


class CoalescedExecutor:
    """
    Ensures only one instance of an operation runs at a time.
    Additional requests during execution are coalesced — only the
    latest is kept and runs as a trailing execution.
    
    Usage:
        executor = CoalescedExecutor("radar_refresh")
        await executor.run(refresh_all_stocks, on_progress=callback)
    """
    
    def __init__(self, name: str):
        self.name = name
        self._in_progress = False
        self._pending_args: Optional[dict] = None
        self._pending_future: Optional[asyncio.Future] = None
    
    async def run(self, func: Callable[..., Awaitable], **kwargs) -> Any:
        """
        Run func if not already running.
        If already running, stash kwargs for a trailing run.
        """
        if self._in_progress:
            # Stash for trailing run (latest wins)
            self._pending_args = kwargs
            if self._pending_future is None:
                self._pending_future = asyncio.get_event_loop().create_future()
            return await self._pending_future
        
        self._in_progress = True
        try:
            result = await func(**kwargs)
            return result
        finally:
            self._in_progress = False
            # Check for trailing run
            if self._pending_args is not None:
                trailing_args = self._pending_args
                trailing_future = self._pending_future
                self._pending_args = None
                self._pending_future = None
                try:
                    trailing_result = await self.run(func, **trailing_args)
                    if trailing_future and not trailing_future.done():
                        trailing_future.set_result(trailing_result)
                except Exception as e:
                    if trailing_future and not trailing_future.done():
                        trailing_future.set_exception(e)


# Create executors for each major operation
radar_executor = CoalescedExecutor("radar_refresh")
daily_snapshot_executor = CoalescedExecutor("daily_snapshot")
news_executor = CoalescedExecutor("news_fetch")
```

### Usage in existing code:
```python
# BEFORE:
await refresh_daily_snapshot()

# AFTER:
await daily_snapshot_executor.run(refresh_daily_snapshot)
# If called again while running, second call waits for trailing run
```

### Commit message
`feat: add CoalescedExecutor to prevent overlapping operations (#12 Tier2)`

---

## Pattern #13: Cron Scheduler with Routing + Orphan Cleanup

### What
Improve scheduled tasks: each task targets a specific handler,
and if the handler is gone/crashed, auto-disable the task.

### Changes to: `server.py` scheduled task management

```python
"""
Add to existing scheduled task logic in server.py.
Route each cron fire to its specific handler.
Auto-disable orphaned tasks.
"""

# In the scheduler section of server.py:

SCHEDULED_HANDLERS = {
    "morning_report": handle_morning_report,      # existing
    "nightly_digest": handle_nightly_digest,       # existing
    "weekly_insight": handle_weekly_insight,        # existing
    "daily_snapshot": handle_daily_snapshot,        # existing
    "news_refresh": handle_news_refresh,            # existing
}

async def fire_scheduled_task(task_name: str, **kwargs):
    """
    Route a scheduled task fire to its handler.
    If handler missing or fails 3 times consecutively, disable task.
    """
    handler = SCHEDULED_HANDLERS.get(task_name)
    if handler is None:
        logger.warning(f"Orphaned scheduled task: {task_name} — disabling")
        disable_scheduled_task(task_name)
        return
    
    # Use circuit breaker from Tier 1
    breaker = get_or_create_breaker(f"cron_{task_name}", max_failures=3)
    if not breaker.can_execute():
        logger.warning(f"Cron {task_name} circuit open — skipping")
        return
    
    try:
        await handler(**kwargs)
        breaker.record_success()
    except Exception as e:
        breaker.record_failure()
        logger.error(f"Cron {task_name} failed: {e}")
        if breaker.failure_count >= 3:
            logger.warning(f"Cron {task_name} failed 3x — disabling")
            # Don't permanently disable — just skip until manual re-enable
```

### Commit message
`feat: add cron handler routing with orphan cleanup (#13 Tier2)`

---

## Pattern #14: Session Summary (Conversation-Level Memory)

### What
After each meaningful Telegram conversation, summarize what happened
and store it. Distinct from Brain observations (entity-level) — this
captures the CONVERSATION itself.

### New File: `session_memory.py`

```python
"""
Session Memory for Master AI.
Captures conversation-level summaries after meaningful exchanges.

Stores in audit.db (new table: session_summaries).
Used for: conversation continuity, weekly insights, audit trail.
"""

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Minimum messages for a "meaningful" conversation worth summarizing
MIN_MESSAGES_FOR_SUMMARY = 4

# Schema for new table (run via db_sanity.py or migration)
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS session_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id TEXT,
    summary TEXT NOT NULL,
    topics TEXT,          -- comma-separated: "trading,CLEANING,HA"
    decisions TEXT,       -- key decisions made
    actions TEXT,         -- actions taken or recommended
    message_count INTEGER,
    started_at REAL,
    ended_at REAL,
    created_at REAL DEFAULT (strftime('%s', 'now'))
);
"""


class SessionTracker:
    """
    Tracks the current conversation session.
    After MIN_MESSAGES_FOR_SUMMARY messages and a quiet period,
    triggers summary extraction.
    """
    
    def __init__(self):
        self.current_session_id: Optional[str] = None
        self.messages: list[dict] = []  # {role, content, timestamp}
        self.session_start: Optional[float] = None
    
    def add_message(self, role: str, content: str) -> None:
        """Track a message in the current session."""
        now = time.time()
        
        # Start new session if: no current session, or gap > 30 minutes
        if (self.current_session_id is None or 
            (self.messages and now - self.messages[-1]["timestamp"] > 1800)):
            # Summarize previous session if meaningful
            if self.should_summarize():
                self._trigger_summary()
            # Start new session
            self.current_session_id = f"session_{int(now)}"
            self.messages = []
            self.session_start = now
        
        self.messages.append({
            "role": role,
            "content": content[:500],  # truncate for memory
            "timestamp": now,
        })
    
    def should_summarize(self) -> bool:
        """Is the current session worth summarizing?"""
        return len(self.messages) >= MIN_MESSAGES_FOR_SUMMARY
    
    def _trigger_summary(self) -> None:
        """Extract and store session summary."""
        if not self.messages:
            return
        
        try:
            # Build conversation text for summarization
            conv_text = "\n".join([
                f"{'User' if m['role'] == 'user' else 'AI'}: {m['content']}"
                for m in self.messages[-20:]  # last 20 messages max
            ])
            
            # Simple keyword extraction (no LLM needed for basic version)
            topics = extract_topics(conv_text)
            
            summary_text = (
                f"Session with {len(self.messages)} messages. "
                f"Topics: {', '.join(topics) if topics else 'general'}."
            )
            
            # Store in DB
            store_session_summary(
                session_id=self.current_session_id,
                summary=summary_text,
                topics=",".join(topics),
                message_count=len(self.messages),
                started_at=self.session_start,
                ended_at=self.messages[-1]["timestamp"],
            )
            
            logger.info(
                f"[session_memory] Summarized session {self.current_session_id}: "
                f"{len(self.messages)} msgs, topics={topics}"
            )
        except Exception as e:
            logger.warning(f"[session_memory] Summary failed: {e}")


def extract_topics(text: str) -> list[str]:
    """Simple keyword-based topic extraction (no LLM)."""
    topics = set()
    
    # Trading stocks (look for known tickers)
    import re
    # Common KSE stock patterns
    stock_pattern = r'\b(CLEANING|SENERGY|INOVEST|THURAYA|HUMANSOFT)\b'
    found_stocks = re.findall(stock_pattern, text, re.IGNORECASE)
    for s in found_stocks:
        topics.add(s.upper())
    
    # Domain keywords
    domain_keywords = {
        "trading": ["سهم", "شراء", "بيع", "إشارة", "signal", "buy", "sell", "stock"],
        "HA": ["automation", "أتمتة", "مكيف", "نور", "light", "AC", "adhan"],
        "network": ["WiFi", "AP", "شبكة", "bridge", "بريدج"],
        "system": ["restart", "deploy", "error", "خطأ", "update"],
    }
    text_lower = text.lower()
    for domain, keywords in domain_keywords.items():
        if any(kw.lower() in text_lower for kw in keywords):
            topics.add(domain)
    
    return list(topics)[:5]  # max 5 topics


def store_session_summary(
    session_id: str,
    summary: str,
    topics: str = "",
    decisions: str = "",
    actions: str = "",
    message_count: int = 0,
    started_at: float = None,
    ended_at: float = None,
) -> None:
    """Store summary in audit.db."""
    from brain_core import get_db_connection  # reuse existing DB connection
    conn = get_db_connection()
    conn.execute(
        """INSERT INTO session_summaries 
        (session_id, summary, topics, decisions, actions, 
         message_count, started_at, ended_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, summary, topics, decisions, actions,
         message_count, started_at, ended_at),
    )
    conn.commit()
```

### Integration
In server.py where Telegram messages are received:
```python
session_tracker = SessionTracker()

# In message handler:
session_tracker.add_message("user", user_message)
# ... process and respond ...
session_tracker.add_message("assistant", response)
```

### DB Migration
Run this SQL (or add to db_sanity.py):
```sql
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
);
```

### Commit message
`feat: add session memory for conversation tracking (#14 Tier2)`

---

## Execution Order for Claude Code

```
1. Read this entire plan
2. For each pattern (#8 through #14):
   a. Read the pattern description
   b. Check current state of target files
   c. Implement the changes
   d. Run quick_check.py
   e. Run smoke_test.py (if available)
   f. git add + git commit with specified message
   g. Continue to next pattern
3. After all 7: restart_master_ai.sh
4. Report: which patterns succeeded, any issues
```

## Order: #8 → #9 → #10 → #11 → #12 → #13 → #14

Critical: #9 MUST come before #10 (index before recall).
All others are independent but this order makes sense for building on each other.

## Important Notes for Claude Code

- DO NOT modify existing function signatures — ADD new functions
- All new files: add proper module docstring + logging
- Use existing DB connections (get_db_connection from brain_core.py)
- Use existing LLM client if available (check server.py for Anthropic SDK usage)
- If Anthropic SDK not installed: skip #10's LLM call, implement fallback only
- circuit_breaker.py from Tier 1 is available — import and reuse
- processing_cursor.py from Tier 1 is available — import and reuse
- tool_registry.py from Tier 1 is available — extend it for #11
- Test each pattern before moving to next
- If a pattern fails, commit what works and note the issue — don't block others
