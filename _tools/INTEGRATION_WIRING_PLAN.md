# Integration Plan — Wire All 15 Modules Into Live System
# Date: 2026-04-03
# Priority: CRITICAL — modules exist but are not connected
# For: Claude Code execution

---

## Problem
15 new modules were created but only 3 are actually imported/used.
The rest sit as unused files. This plan wires them into the live system.

## Rules
- DO NOT rewrite existing functions — ADD calls to new modules alongside existing code
- Each integration = 1 commit
- Test after each: quick_check.py + curl health check
- If integration breaks something, revert that commit and move on

---

## Integration 1: stock_radar.py ← parallel_coordinator + coalesced_executor + processing_cursor

### What to change:
In `stock_radar.py`, find the main refresh loop where stocks are analyzed sequentially.

### Add imports at top:
```python
from parallel_coordinator import ParallelCoordinator
from coalesced_executor import CoalescedExecutor
from processing_cursor import ProcessingCursor
```

### Wire parallel_coordinator into bulk stock analysis:
Find where stocks are analyzed in a loop (e.g., `for stock in stocks: await analyze(stock)`).
Wrap with ParallelCoordinator:
```python
# BEFORE (sequential):
# for stock in stocks:
#     result = await analyze_single_stock(stock)
#     results.append(result)

# AFTER (parallel):
coord = ParallelCoordinator("radar_refresh")
for stock in stocks:
    coord.add_worker(stock, analyze_single_stock, ticker=stock)
results = await coord.run(max_concurrent=5, timeout=30)
# Extract successful results
successful = [r.result for r in results if r.success and r.result]
```

If the existing code already uses asyncio.gather, just wrap it:
```python
# If already using gather, add coordinator as a logging/progress layer:
coord = ParallelCoordinator("radar_refresh")
# ... use coord.summarize(results) for logging
```

### Wire coalesced_executor to prevent overlapping refreshes:
```python
_radar_executor = CoalescedExecutor("radar_refresh")

async def refresh_all_stocks():
    return await _radar_executor.run(_do_refresh_all_stocks)

async def _do_refresh_all_stocks():
    # ... existing refresh logic ...
```

### Wire processing_cursor for incremental processing:
```python
_radar_cursor = ProcessingCursor("radar_signals")

async def process_new_signals():
    cursor = _radar_cursor.get_position()
    # Only process signals newer than cursor
    new_signals = get_signals_after(cursor)
    for sig in new_signals:
        process_signal(sig)
    _radar_cursor.advance(new_signals[-1].id if new_signals else cursor)
```

### Commit: `integration: wire parallel_coordinator + coalesced_executor + cursor into stock_radar`

---

## Integration 2: bridge_client.py ← circuit_breaker

### What to change:
bridge_client.py likely already has some retry logic. Replace/enhance with CircuitBreaker.

### Add import:
```python
from circuit_breaker import CircuitBreaker
```

### Wire circuit breaker:
```python
_bridge_cb = CircuitBreaker("bridge_api", max_failures=3, cooldown_seconds=300)

async def call_bridge_api(endpoint, **kwargs):
    if not _bridge_cb.can_execute():
        return {"error": "circuit_open", "cooldown": _bridge_cb.remaining_cooldown()}

    try:
        result = await _actual_bridge_call(endpoint, **kwargs)
        _bridge_cb.record_success()
        return result
    except Exception as e:
        _bridge_cb.record_failure()
        raise
```

### Commit: `integration: wire circuit_breaker into bridge_client`

---

## Integration 3: tg_intent_router.py ← intent_state_machine + master_ai_tool + memory_prefetch

### What to change:
This is the Telegram message handler. Add state tracking, tool validation, and memory prefetch.

### Add imports:
```python
from intent_state_machine import IntentContext, IntentState
from master_ai_tool import TOOL_DEFS
from memory_prefetch import MemoryPrefetcher
```

### Wire intent_state_machine:
Find the main message handler function. Wrap the routing logic:
```python
async def handle_message(message_text, user_id, ...):
    ctx = IntentContext(
        message_id=str(int(time.time()*1000)),
        raw_text=message_text,
    )

    try:
        # Start memory prefetch immediately (before routing)
        prefetch = MemoryPrefetcher(message_text)

        # Classify intent (existing logic)
        intent = classify_intent(message_text)  # or however routing works
        ctx.intent = intent
        ctx.transition(IntentState.CLASSIFIED, f"intent={intent}")

        # Pre-flight check with master_ai_tool
        tool_def = TOOL_DEFS.get(intent)
        if tool_def:
            can_run, reason = tool_def.can_execute({"bridge_online": is_bridge_online()})
            if not can_run:
                ctx.transition(IntentState.FAILED, reason)
                return reason
        ctx.transition(IntentState.VALIDATED, "ok")

        # Get prefetched memories (usually ready by now)
        memories = await prefetch.get_result(timeout=3.0)

        # Execute (existing logic)
        ctx.transition(IntentState.EXECUTING, f"handler")
        result = await execute_intent(intent, message_text, memories=memories)

        ctx.transition(IntentState.RESPONDED, f"{ctx.duration_ms}ms")
        return result
    except Exception as e:
        ctx.error = str(e)
        ctx.transition(IntentState.FAILED, str(e))
        raise
    finally:
        # Log to audit (fire-and-forget)
        try:
            log_intent_audit(ctx.to_audit_dict())
        except:
            pass
```

NOTE: The existing tg_intent_router.py may have a very different structure.
Adapt the above to fit. The key integrations are:
1. Create IntentContext at start of each message
2. Call tool_def.can_execute() before running
3. Start MemoryPrefetcher early, await later
4. Log ctx.to_audit_dict() at the end

### Commit: `integration: wire intent_state_machine + master_ai_tool + memory_prefetch into tg_intent_router`

---

## Integration 4: chat_v7.py ← context_manager + memory_recall

### What to change:
chat_v7.py handles LLM conversations. Add context management and memory recall.

### Add imports:
```python
from context_manager import manage_context
from memory_recall import find_relevant_memories
```

### Wire context_manager:
Find where messages are sent to the Anthropic API. Add context management before:
```python
# BEFORE sending to API:
# response = await client.messages.create(messages=messages, ...)

# AFTER:
managed_messages = await manage_context(messages)
response = await client.messages.create(messages=managed_messages, ...)
```

### Wire memory_recall:
When building the system prompt or context for a conversation:
```python
# Get relevant memories for the user's query
relevant_memories = await find_relevant_memories(
    query=user_message,
    max_selected=5,
)
if relevant_memories:
    memory_context = "\n".join([
        f"- {m['entity_id']}: {m['observation']}" +
        (f" {m.get('staleness_warning','')}" if m.get('staleness_warning') else "")
        for m in relevant_memories
    ])
    # Inject into system prompt or as a system message
    messages.insert(0, {"role": "system", "content": f"Relevant observations:\n{memory_context}"})
```

### Commit: `integration: wire context_manager + memory_recall into chat_v7`

---

## Integration 5: server.py TG handler ← auto_memory_extractor + session_memory

### What to change:
Find where Telegram messages are received and responses sent in server.py.

### Add imports:
```python
from auto_memory_extractor import AutoMemoryExtractor
from session_memory import SessionTracker
```

### Wire at module level:
```python
_memory_extractor = AutoMemoryExtractor()
_session_tracker = SessionTracker()
```

### Wire in the Telegram message handler:
Find the function that handles incoming Telegram messages.
```python
async def handle_telegram_message(update, context):
    user_text = update.message.text

    # Track session + auto-learning
    _session_tracker.add_message("user", user_text)
    _memory_extractor.record_message("user", user_text)

    # ... existing processing to get response ...
    response = await process_message(user_text, ...)

    # Track response
    _session_tracker.add_message("assistant", response)
    _memory_extractor.record_message("assistant", response)

    # Send response (existing)
    await update.message.reply_text(response)
```

### Commit: `integration: wire auto_memory_extractor + session_memory into server.py TG handler`

---

## Integration 6: news_engine.py ← processing_cursor (already has circuit_breaker)

### Add import:
```python
from processing_cursor import ProcessingCursor
```

### Wire cursor for RSS processing:
```python
_boursa_cursor = ProcessingCursor("news_boursa")

async def refresh_boursa():
    cursor = _boursa_cursor.get_position()
    # Only process articles newer than cursor
    new_articles = fetch_rss_after(cursor)
    for article in new_articles:
        process_article(article)
    if new_articles:
        _boursa_cursor.advance(new_articles[-1].id)
```

### Commit: `integration: wire processing_cursor into news_engine`

---

## Integration 7: dashboard_api.py ← task_manager for all operations

### What to change:
Wrap long-running dashboard operations with TaskManager tracking.

### Find operations like refresh-boursa, refresh-gemini, etc:
```python
from task_manager import TaskManager, TaskType

@app.post("/api/news/refresh-boursa")
async def refresh_boursa_endpoint():
    tm = TaskManager.instance()
    task = tm.create_task(TaskType.NEWS_FETCH, {"source": "boursa"})
    tm.start_task(task.task_id)
    try:
        result = await refresh_boursa()
        tm.complete_task(task.task_id, result=f"{len(result)} articles")
        return {"ok": True, "count": len(result)}
    except Exception as e:
        tm.fail_task(task.task_id, error=str(e))
        return {"ok": False, "error": str(e)}
```

### Commit: `integration: wire task_manager into dashboard_api endpoints`

---

## Execution Order
```
1. Read this entire plan
2. For each integration (#1 through #7):
   a. Read the target file to understand its current structure
   b. Find the exact insertion points
   c. Add imports + wiring code
   d. Run quick_check.py (import test)
   e. curl http://localhost:9000/health (sanity)
   f. git commit with specified message
   g. If it breaks: git revert HEAD and move to next
3. After all: restart_master_ai.sh
4. Report: which integrations succeeded, which needed revert
```

## Critical Notes
- DO NOT rewrite existing functions — add new module calls ALONGSIDE existing code
- If existing code already does something similar (e.g., bridge already has retry), ADD the new module as a wrapper, don't replace
- Some integrations may need adaptation based on actual code structure
- memory_recall needs Anthropic API key — check if it's available: grep ANTHROPIC .env
- If a module import fails, check if all dependencies exist
- processing_cursor.py needs a storage backend — check if it uses file/DB/memory
