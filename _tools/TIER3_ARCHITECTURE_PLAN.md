# Tier 3 Implementation Plan — Architecture Evolution
# Date: 2026-04-03
# For: Claude Code (RPi) execution
# Pre-requisite: Tier 1 (7/7 DONE) + Tier 2 (7/7 DONE)
# Reference: _tools/CLAUDE_CODE_SOURCE_ANALYSIS_P1_P2.md

---

## Overview: 7 Patterns, ordered by impact

Tier 1 = safety nets. Tier 2 = intelligence. Tier 3 = ARCHITECTURE.
These are bigger changes. Each pattern may take multiple commits.

### Implementation Order (by impact/effort):
1. #19 — 3-Level Memory Scoping (LOW effort, foundation for others)
2. #21 — Memory Prefetch (MEDIUM effort, immediate latency win)
3. #16 — Background Memory Extraction (HIGH impact, medium effort)
4. #18 — Coordinator-Worker Parallelism (MEDIUM effort, speed win)
5. #15 — Multi-Layer Context Management (HIGH effort, HIGH impact)
6. #17 — State Machine Query Loop (HIGH effort, maintainability)
7. #20 — Skill/Plugin System (HIGH effort, future extensibility)

---

## Pattern #19: 3-Level Memory Scoping

### What
Add a `scope` field to Brain observations to distinguish:
- `global` — applies everywhere (trading rules, risk limits, user preferences)
- `stock` — per-stock patterns and personality
- `device` — per-device quirks, HA entity behaviors

### Changes: `brain_core.py` + DB migration

### DB Migration (run first):
```sql
-- Add scope column with default 'global'
ALTER TABLE brain_observations ADD COLUMN scope TEXT DEFAULT 'global';

-- Backfill: observations about known stocks → 'stock'
UPDATE brain_observations SET scope = 'stock'
WHERE entity_domain = 'trading'
  AND entity_id IN (SELECT DISTINCT ticker FROM stock_radar_daily);

-- Backfill: observations about HA entities → 'device'
UPDATE brain_observations SET scope = 'device'
WHERE entity_domain IN ('climate', 'light', 'cover', 'fan', 'media_player');

-- Index for fast scope-based queries
CREATE INDEX IF NOT EXISTS idx_brain_obs_scope ON brain_observations(scope);
```

### Code Changes in brain_core.py:
```python
# Update get_observation_manifest() to accept scope filter
def get_observation_manifest(
    entity_domain: str = None,
    scope: str = None,       # NEW: 'global', 'stock', 'device'
    max_items: int = 200,
) -> list[dict]:
    # Add WHERE scope = ? if provided
    ...

# Update any observation-writing functions to include scope
def add_observation(entity_id, domain, observation, scope='global'):
    # Auto-detect scope if not provided:
    # - entity_domain in trading → scope='stock'
    # - entity_domain in climate/light/etc → scope='device'
    # - else → scope='global'
    ...
```

### Integration with memory_recall.py:
```python
# find_relevant_memories() can now filter by scope:
# For trading queries → scope='stock' + scope='global'
# For HA queries → scope='device' + scope='global'
# For general queries → all scopes
```

### Test:
```python
# After migration:
# SELECT scope, COUNT(*) FROM brain_observations GROUP BY scope;
# Expected: global=N, stock=M, device=K
```

### Commit: `feat: add 3-level memory scoping to Brain observations (#19 Tier3)`

---

## Pattern #21: Memory Prefetch (Speculative Loading)

### What
Start Brain observation lookup BEFORE intent parsing completes.
While the LLM or intent router is processing, memories are being retrieved
in the background. When the handler needs memories, they're already ready.

### Changes: `server.py` or `tg_intent_router.py`

### Implementation:
```python
import asyncio

class MemoryPrefetcher:
    """
    Start memory retrieval as soon as a message arrives.
    Don't wait for intent routing to complete.
    
    Usage:
        prefetch = MemoryPrefetcher(user_message)
        # ... do intent routing, validation, etc ...
        memories = await prefetch.get_result()  # usually already done
    """
    
    def __init__(self, query: str, scope: str = None):
        self._task = asyncio.create_task(
            self._fetch(query, scope)
        )
        self._result = None
    
    async def _fetch(self, query: str, scope: str):
        try:
            from memory_recall import find_relevant_memories
            return await find_relevant_memories(
                query=query,
                entity_domain=scope,
                max_selected=5,
            )
        except Exception:
            return []
    
    async def get_result(self, timeout: float = 5.0) -> list:
        """Get prefetched results. If not ready, wait up to timeout."""
        if self._result is not None:
            return self._result
        try:
            self._result = await asyncio.wait_for(
                self._task, timeout=timeout
            )
        except asyncio.TimeoutError:
            self._result = []
        return self._result
    
    @property
    def is_ready(self) -> bool:
        return self._task.done()
```

### Integration in message handler:
```python
async def handle_telegram_message(message):
    # START prefetch immediately (before intent routing)
    prefetch = MemoryPrefetcher(message.text)
    
    # Do intent routing (takes 100-500ms)
    intent = await route_intent(message.text)
    
    # By now, prefetch is likely done (Haiku takes ~200ms)
    memories = await prefetch.get_result()
    
    # Handler uses pre-fetched memories
    response = await handle_intent(intent, message, memories=memories)
```

### Commit: `feat: add memory prefetch for parallel loading (#21 Tier3)`

---

## Pattern #16: Background Memory Extraction (THE BIG ONE)

### What
After each meaningful Telegram conversation, automatically extract
durable observations and save them to Brain — WITHOUT blocking the response.

This is the pattern that makes Master AI "learn" from conversations.

Based on Claude Code's extractMemories.ts (615 lines):
- Runs at END of each conversation turn
- Uses a forked/background task (not the main response path)
- Cursor-based: only processes NEW messages since last extraction
- Coalesced: if extraction running, stash and run trailing
- Scoped permissions: can only READ data and WRITE to observations

### New File: `auto_memory_extractor.py`

```python
"""
Automatic Memory Extraction for Master AI.

After each meaningful conversation exchange, runs a background task
that analyzes what happened and extracts durable observations.

Based on Claude Code's extractMemories.ts pattern.
Uses: session_memory.py (Tier 2 #14), memory_recall.py (Tier 2 #10),
      processing_cursor.py (Tier 1 #7), coalesced_executor.py (Tier 2 #12)
"""

import asyncio
import logging
import time
from typing import Optional
from processing_cursor import ProcessingCursor
from coalesced_executor import CoalescedExecutor

logger = logging.getLogger(__name__)

# Only extract if conversation has this many user messages since last extraction
MIN_MESSAGES_FOR_EXTRACTION = 3

# System prompt for the extraction LLM call
EXTRACTION_PROMPT = """You are analyzing a conversation between a user and an AI assistant.
Extract any DURABLE observations worth remembering for future conversations.

Focus on:
- Decisions the user made (bought/sold stock, changed HA setting, etc.)
- Preferences expressed (likes/dislikes, preferred approaches)
- Facts learned about the user's situation (new position, schedule change, etc.)
- Problems encountered and their solutions
- Patterns noticed (e.g., "user always checks CLEANING first")

Do NOT extract:
- Temporary states ("Bridge is offline right now")
- Generic information (stock prices, weather)
- Anything already in the existing observations

Return a JSON array of observations:
[
  {"entity_id": "CLEANING", "domain": "trading", "scope": "stock",
   "observation": "المستخدم قرر عدم شراء CLEANING بسبب نزول حاد 2026-04-03"},
  {"entity_id": "bedroom_ac", "domain": "climate", "scope": "device",
   "observation": "المستخدم يفضل 21 درجة بالليل مو 23"}
]

Return ONLY valid JSON. If nothing worth extracting, return [].
"""


class AutoMemoryExtractor:
    """
    Background memory extraction from Telegram conversations.
    
    Usage (in server.py message handler):
        extractor = AutoMemoryExtractor()
        
        # After each message exchange:
        extractor.record_message("user", user_text)
        extractor.record_message("assistant", response_text)
        
        # Extraction runs automatically in background
    """
    
    def __init__(self):
        self._cursor = ProcessingCursor("auto_memory_extraction")
        self._executor = CoalescedExecutor("memory_extraction")
        self._messages: list[dict] = []
        self._message_count_since_last = 0
        self._in_progress = False
    
    def record_message(self, role: str, content: str):
        """Record a message and maybe trigger extraction."""
        self._messages.append({
            "role": role,
            "content": content[:1000],  # truncate for memory
            "timestamp": time.time(),
        })
        
        if role == "user":
            self._message_count_since_last += 1
        
        # Check if we should extract
        if (role == "assistant" and 
            self._message_count_since_last >= MIN_MESSAGES_FOR_EXTRACTION):
            # Fire-and-forget background extraction
            asyncio.create_task(self._maybe_extract())
    
    async def _maybe_extract(self):
        """Run extraction if conditions are met. Coalesced."""
        await self._executor.run(self._do_extraction)
    
    async def _do_extraction(self):
        """The actual extraction logic."""
        if not self._messages:
            return
        
        try:
            # Get messages since last extraction
            messages_to_process = self._messages[-20:]  # last 20 max
            
            # Build conversation text
            conv_text = "\n".join([
                f"{'User' if m['role']=='user' else 'AI'}: {m['content']}"
                for m in messages_to_process
            ])
            
            # Get existing observations to avoid duplicates
            from brain_core import get_observation_manifest, format_observation_manifest
            existing = format_observation_manifest(
                get_observation_manifest(max_items=50)
            )
            
            # Ask LLM to extract observations
            import anthropic
            import json
            
            client = anthropic.AsyncAnthropic()
            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=EXTRACTION_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Existing observations (avoid duplicates):\n{existing}\n\n---\n\nConversation to analyze:\n{conv_text}",
                }],
            )
            
            text = response.content[0].text.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            observations = json.loads(text)
            
            if not observations or not isinstance(observations, list):
                logger.debug("[auto_mem] No observations extracted")
                return
            
            # Save to Brain
            from brain_core import get_db_connection
            conn = get_db_connection()
            saved = 0
            for obs in observations:
                if not isinstance(obs, dict):
                    continue
                entity_id = obs.get("entity_id", "general")
                domain = obs.get("domain", "general")
                scope = obs.get("scope", "global")
                text = obs.get("observation", "")
                if not text:
                    continue
                
                conn.execute(
                    """INSERT INTO brain_observations 
                    (entity_id, entity_domain, observation, scope, timestamp)
                    VALUES (?, ?, ?, ?, datetime('now'))""",
                    (entity_id, domain, text, scope),
                )
                saved += 1
            
            conn.commit()
            logger.info(f"[auto_mem] Extracted {saved} observations from {len(messages_to_process)} messages")
            
            # Reset counter
            self._message_count_since_last = 0
            
        except Exception as e:
            logger.warning(f"[auto_mem] Extraction failed: {e}")
```

### Integration in server.py:
```python
# At module level:
from auto_memory_extractor import AutoMemoryExtractor
_extractor = AutoMemoryExtractor()

# In the Telegram message handler:
async def handle_message(update, context):
    user_text = update.message.text
    _extractor.record_message("user", user_text)
    
    # ... existing processing ...
    response = await process_message(user_text)
    
    _extractor.record_message("assistant", response)
    # Extraction happens automatically in background
    
    await update.message.reply_text(response)
```

### Dependencies:
- Tier 1 #7: processing_cursor.py ✅
- Tier 2 #12: coalesced_executor.py ✅
- Tier 2 #10: memory_recall.py (for existing obs check) ✅
- Pattern #19: scope field in brain_observations ← DO #19 FIRST
- Anthropic API key (check .env for ANTHROPIC_API_KEY)

### Commit: `feat: add automatic memory extraction from conversations (#16 Tier3)`

---

## Pattern #18: Coordinator-Worker Parallelism

### What
Formalize asyncio.gather pattern for multi-stock/multi-entity analysis.
Instead of sequential processing, run independent analyses in parallel.

### New File: `parallel_coordinator.py`

```python
"""
Parallel Coordinator for Master AI.
Runs independent analysis tasks concurrently with structured result collection.

Based on Claude Code's coordinatorMode.ts pattern.
"""

import asyncio
import logging
import time
from typing import Any, Callable, Awaitable, Optional
from dataclasses import dataclass, field
from task_manager import TaskManager, TaskType

logger = logging.getLogger(__name__)


@dataclass
class WorkerResult:
    name: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    duration_ms: int = 0


class ParallelCoordinator:
    """
    Run multiple independent tasks in parallel and collect results.
    
    Usage:
        coord = ParallelCoordinator("analyze_stocks")
        coord.add_worker("CLEANING", analyze_stock, ticker="CLEANING")
        coord.add_worker("SENERGY", analyze_stock, ticker="SENERGY")
        coord.add_worker("INOVEST", analyze_stock, ticker="INOVEST")
        results = await coord.run(max_concurrent=5, timeout=30)
        # results = [WorkerResult(name="CLEANING", ...), ...]
    """
    
    def __init__(self, name: str):
        self.name = name
        self._workers: list[tuple[str, Callable, dict]] = []
    
    def add_worker(self, name: str, func: Callable[..., Awaitable], **kwargs):
        self._workers.append((name, func, kwargs))
    
    async def run(
        self,
        max_concurrent: int = 10,
        timeout: float = 60.0,
        on_progress: Optional[Callable[[str, int, int], None]] = None,
    ) -> list[WorkerResult]:
        """
        Run all workers with concurrency limit.
        on_progress(worker_name, completed, total) called after each worker.
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        results: list[WorkerResult] = []
        completed = 0
        total = len(self._workers)
        
        async def run_one(name: str, func: Callable, kwargs: dict):
            nonlocal completed
            async with semaphore:
                start = time.time()
                try:
                    result = await asyncio.wait_for(
                        func(**kwargs), timeout=timeout
                    )
                    wr = WorkerResult(
                        name=name, success=True, result=result,
                        duration_ms=int((time.time()-start)*1000)
                    )
                except asyncio.TimeoutError:
                    wr = WorkerResult(
                        name=name, success=False, error="timeout",
                        duration_ms=int((time.time()-start)*1000)
                    )
                except Exception as e:
                    wr = WorkerResult(
                        name=name, success=False, error=str(e),
                        duration_ms=int((time.time()-start)*1000)
                    )
                results.append(wr)
                completed += 1
                if on_progress:
                    on_progress(name, completed, total)
                return wr
        
        tasks = [
            run_one(name, func, kwargs)
            for name, func, kwargs in self._workers
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        return results
    
    def summarize(self, results: list[WorkerResult]) -> str:
        """Quick text summary of results."""
        ok = sum(1 for r in results if r.success)
        fail = sum(1 for r in results if not r.success)
        total_ms = sum(r.duration_ms for r in results)
        lines = [f"✅ {ok} succeeded, ❌ {fail} failed ({total_ms}ms total)"]
        for r in results:
            if not r.success:
                lines.append(f"  ❌ {r.name}: {r.error}")
        return "\n".join(lines)
```

### Usage in stock_radar.py:
```python
# BEFORE (sequential):
results = []
for stock in stocks:
    r = await analyze_stock(stock)
    results.append(r)

# AFTER (parallel):
coord = ParallelCoordinator("radar_refresh")
for stock in stocks:
    coord.add_worker(stock, analyze_stock, ticker=stock)
results = await coord.run(
    max_concurrent=5,  # 5 concurrent Bridge API calls
    timeout=30,
    on_progress=lambda name, done, total: 
        tm.update_progress(task_id, f"{done}/{total} stocks")
)
```

### Commit: `feat: add ParallelCoordinator for concurrent analysis (#18 Tier3)`

---

## Pattern #15: Multi-Layer Context Management

### What
The most complex pattern. Add context compaction to chat_v7.py so
conversations can run longer without losing important context.

4 layers (cheapest first):
1. TRIM — remove old/irrelevant messages (free)
2. COMPRESS — summarize tool outputs (cheap)
3. SUMMARIZE — full conversation summary (expensive, LLM call)
4. EMERGENCY — hard truncate if still over limit

### Changes: `chat_v7.py` + new `context_manager.py`

### New File: `context_manager.py`

```python
"""
Multi-Layer Context Management for Master AI chat.

Manages conversation context to prevent token overflow.
4 layers, cheapest first — expensive layers only run if needed.

Based on Claude Code's query.ts 4-layer compaction.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Token estimates (rough: 1 token ≈ 4 chars for English, 2 chars for Arabic)
MAX_CONTEXT_TOKENS = 180000  # Claude's limit minus safety margin
TRIM_THRESHOLD = 120000      # Start trimming at 67%
COMPRESS_THRESHOLD = 150000  # Compress tool outputs at 83%
SUMMARIZE_THRESHOLD = 170000 # Full summary at 94%


def estimate_tokens(messages: list[dict]) -> int:
    """Rough token estimate for a message list."""
    total_chars = sum(len(m.get("content", "")) for m in messages)
    return total_chars // 3  # rough average for mixed Arabic/English


def layer1_trim(messages: list[dict], keep_last: int = 10) -> list[dict]:
    """
    Layer 1: TRIM — Remove old messages, keep recent ones.
    FREE (no LLM call).
    
    Keeps: system message + last N messages.
    Removes: everything in between.
    """
    if len(messages) <= keep_last + 1:
        return messages
    
    system_msgs = [m for m in messages[:2] if m.get("role") == "system"]
    recent = messages[-keep_last:]
    
    trimmed = system_msgs + [{
        "role": "system",
        "content": f"[السياق السابق: {len(messages) - len(system_msgs) - keep_last} رسالة تم اختصارها]"
    }] + recent
    
    logger.info(f"[context] Layer 1 TRIM: {len(messages)} → {len(trimmed)} messages")
    return trimmed


def layer2_compress(messages: list[dict], max_tool_chars: int = 500) -> list[dict]:
    """
    Layer 2: COMPRESS — Truncate long tool outputs.
    FREE (no LLM call, just string truncation).
    
    Tool results (API responses, DB queries, etc.) get truncated to max_tool_chars.
    """
    compressed = []
    for m in messages:
        content = m.get("content", "")
        # Detect tool outputs (usually very long, structured data)
        if len(content) > max_tool_chars and m.get("role") == "assistant":
            # Check if it looks like structured data (JSON, tables, etc.)
            if any(indicator in content[:200] for indicator in 
                   ['{', '[', '|', 'RSI', 'MACD', 'EMA', '📊', '📈']):
                compressed_content = content[:max_tool_chars] + f"\n... [{len(content) - max_tool_chars} chars truncated]"
                compressed.append({**m, "content": compressed_content})
                continue
        compressed.append(m)
    
    logger.info(f"[context] Layer 2 COMPRESS: applied to {len(messages)} messages")
    return compressed


async def layer3_summarize(messages: list[dict]) -> list[dict]:
    """
    Layer 3: SUMMARIZE — LLM summarizes the conversation.
    EXPENSIVE (Haiku API call).
    
    Summarizes old messages into a single system message.
    Keeps the last 5 messages intact.
    """
    if len(messages) <= 6:
        return messages
    
    # Messages to summarize (everything except last 5)
    to_summarize = messages[:-5]
    to_keep = messages[-5:]
    
    summary_text = "\n".join([
        f"{m.get('role', 'unknown')}: {m.get('content', '')[:200]}"
        for m in to_summarize
    ])
    
    try:
        import anthropic
        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system="Summarize this conversation in Arabic. Focus on: decisions made, topics discussed, current state. Be concise (max 200 words).",
            messages=[{"role": "user", "content": summary_text}],
        )
        summary = response.content[0].text
    except Exception as e:
        logger.warning(f"[context] Layer 3 summarize failed: {e}")
        summary = f"ملخص المحادثة: {len(to_summarize)} رسالة سابقة"
    
    result = [{
        "role": "system",
        "content": f"ملخص المحادثة السابقة:\n{summary}"
    }] + to_keep
    
    logger.info(f"[context] Layer 3 SUMMARIZE: {len(messages)} → {len(result)} messages")
    return result


def layer4_emergency(messages: list[dict], max_messages: int = 5) -> list[dict]:
    """
    Layer 4: EMERGENCY — Hard truncate. Last resort.
    """
    if len(messages) <= max_messages:
        return messages
    result = [{
        "role": "system", 
        "content": "⚠️ تم اختصار المحادثة بسبب طول السياق"
    }] + messages[-max_messages:]
    logger.warning(f"[context] Layer 4 EMERGENCY: {len(messages)} → {len(result)}")
    return result


async def manage_context(messages: list[dict]) -> list[dict]:
    """
    Main entry point. Apply layers as needed (cheapest first).
    Returns optimized message list.
    """
    tokens = estimate_tokens(messages)
    
    if tokens < TRIM_THRESHOLD:
        return messages  # No action needed
    
    # Layer 1: TRIM
    messages = layer1_trim(messages)
    tokens = estimate_tokens(messages)
    if tokens < COMPRESS_THRESHOLD:
        return messages
    
    # Layer 2: COMPRESS
    messages = layer2_compress(messages)
    tokens = estimate_tokens(messages)
    if tokens < SUMMARIZE_THRESHOLD:
        return messages
    
    # Layer 3: SUMMARIZE
    messages = await layer3_summarize(messages)
    tokens = estimate_tokens(messages)
    if tokens < MAX_CONTEXT_TOKENS:
        return messages
    
    # Layer 4: EMERGENCY
    return layer4_emergency(messages)
```

### Integration in chat_v7.py:
```python
# Before sending to Anthropic API:
from context_manager import manage_context

async def chat(messages, ...):
    # Apply context management
    messages = await manage_context(messages)
    
    # Send to API as usual
    response = await client.messages.create(
        model=model,
        messages=messages,
        ...
    )
```

### Commit: `feat: add multi-layer context management for chat (#15 Tier3)`

---

## Pattern #17: State Machine Query Loop

### What
Refactor tg_intent_router.py from a big if/elif chain into an
explicit state machine with typed transitions and audit logging.

### Changes: `tg_intent_router.py` + new `intent_state_machine.py`

### New File: `intent_state_machine.py`

```python
"""
State Machine for Intent Routing.

Replaces if/elif chains with explicit state transitions.
Each transition is logged for debugging.

States: RECEIVED → CLASSIFIED → VALIDATED → EXECUTING → RESPONDED / FAILED
"""

import logging
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Any

logger = logging.getLogger(__name__)


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
    metadata: dict = field(default_factory=dict)


@dataclass
class IntentContext:
    """Tracks the full lifecycle of a user message."""
    message_id: str
    raw_text: str
    state: IntentState = IntentState.RECEIVED
    intent: Optional[str] = None
    handler: Optional[str] = None
    transitions: list = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    result: Optional[Any] = None
    error: Optional[str] = None
    
    def transition(self, new_state: IntentState, reason: str, **metadata):
        """Record a state transition."""
        t = IntentTransition(
            from_state=self.state,
            to_state=new_state,
            reason=reason,
            metadata=metadata,
        )
        self.transitions.append(t)
        self.state = new_state
        logger.debug(
            f"[intent] {self.message_id}: {t.from_state.value} → {t.to_state.value} ({reason})"
        )
    
    @property
    def duration_ms(self) -> int:
        return int((time.time() - self.started_at) * 1000)
    
    def to_audit_dict(self) -> dict:
        """For logging to audit.db."""
        return {
            "message_id": self.message_id,
            "raw_text": self.raw_text[:200],
            "intent": self.intent,
            "handler": self.handler,
            "state": self.state.value,
            "duration_ms": self.duration_ms,
            "transitions": [
                f"{t.from_state.value}→{t.to_state.value}({t.reason})"
                for t in self.transitions
            ],
            "error": self.error,
        }
```

### Refactored flow in tg_intent_router.py:
```python
async def route_message(message):
    ctx = IntentContext(
        message_id=str(message.message_id),
        raw_text=message.text,
    )
    
    try:
        # Step 1: Classify intent
        intent = classify_intent(message.text)
        ctx.intent = intent
        ctx.transition(IntentState.CLASSIFIED, f"intent={intent}")
        
        # Step 2: Validate (from Tier 1 tool_registry)
        tool = TOOLS.get(intent)
        if tool:
            can_run, reason = tool.can_execute(get_context())
            if not can_run:
                ctx.transition(IntentState.FAILED, reason)
                return reason
        ctx.transition(IntentState.VALIDATED, "pre-flight passed")
        
        # Step 3: Execute
        ctx.handler = f"handle_{intent}"
        ctx.transition(IntentState.EXECUTING, f"handler={ctx.handler}")
        
        result = await execute_intent(intent, message)
        
        ctx.result = str(result)[:200]
        ctx.transition(IntentState.RESPONDED, f"{ctx.duration_ms}ms")
        return result
        
    except Exception as e:
        ctx.error = str(e)
        ctx.transition(IntentState.FAILED, f"error: {e}")
        raise
    finally:
        # Log to audit
        log_intent_audit(ctx.to_audit_dict())
```

### Commit: `feat: add state machine for intent routing (#17 Tier3)`

---

## Pattern #20: Skill/Plugin System

### What
Allow reusable analysis templates defined as .md files with metadata.
Each "skill" is a prompt template + configuration.

### Directory: `skills/`

### Skill Format:
```markdown
---
name: technical_analysis
description: Full technical analysis for a stock
requires_bridge: true
requires_llm: true
timeout: 90
input: ticker
output: telegram_card
---

Analyze {ticker} using:
1. RSI (14) — overbought/oversold status
2. MACD (12/26/9) — signal line crossover
3. EMA 9/21 — trend direction
4. Volume — above/below average
5. Support/Resistance — nearest levels

Format as Arabic Telegram card with emoji indicators.
```

### Skill Loader:
```python
import yaml
import os

def load_skills(skills_dir="skills/"):
    skills = {}
    for f in os.listdir(skills_dir):
        if not f.endswith('.md'):
            continue
        with open(os.path.join(skills_dir, f)) as fh:
            content = fh.read()
        # Parse frontmatter
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1])
                template = parts[2].strip()
                skills[meta['name']] = {
                    'meta': meta,
                    'template': template,
                }
    return skills

def execute_skill(skill_name, **kwargs):
    skill = SKILLS.get(skill_name)
    if not skill:
        return None
    prompt = skill['template']
    for key, val in kwargs.items():
        prompt = prompt.replace(f'{{{key}}}', str(val))
    return prompt
```

### This is LOW priority — current hardcoded commands work fine.
### Commit: `feat: add skill/plugin system for reusable templates (#20 Tier3)`

---

## Execution Order for Claude Code

```
1. Read this entire plan
2. For each pattern (in order: #19 → #21 → #16 → #18 → #15 → #17 → #20):
   a. Read the pattern description carefully
   b. Check current state of target files (especially brain_core.py, server.py)
   c. Check for API key availability: grep -r "ANTHROPIC" .env
   d. Implement the changes
   e. Run quick_check.py
   f. Run smoke_test.py
   g. git add + git commit with specified message
   h. Continue to next pattern
3. After all: restart_master_ai.sh
4. Report: which patterns succeeded, any issues
```

## Critical Notes for Claude Code:

- #19 MUST come before #16 (scope field needed for extraction)
- #16 needs Anthropic API key — check .env first. If not available, implement
  with a simple keyword-extraction fallback (no LLM) and add TODO for LLM version
- #15 (context management) is the riskiest — test thoroughly before committing
  Make sure existing chat flow still works with context_manager as a no-op
  when messages are under TRIM_THRESHOLD
- #17 is a refactor — do NOT break existing command routing. Add state machine
  alongside existing code, don't replace it yet. Wrap existing handlers.
- #20 is optional — skip if time is tight. Current commands work fine.
- Use existing modules from Tier 1+2: circuit_breaker.py, processing_cursor.py,
  coalesced_executor.py, task_manager.py, memory_recall.py
- All new files: add module docstring + logging
- If a pattern fails, commit what works and note the issue
