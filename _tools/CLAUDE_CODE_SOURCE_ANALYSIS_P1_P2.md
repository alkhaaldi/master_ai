# Claude Code Source Analysis — P1 Memory + P2 Query Engine
# Date: 2026-04-02
# Analyst: claude.ai
# Purpose: Extract patterns applicable to Master AI

---

## P1: Memory System — Full Analysis

### File 1: `findRelevantMemories.ts` — LLM-Powered Memory Recall

**How it works:**
1. Scans all `.md` memory files (via `scanMemoryFiles`)
2. Filters out already-surfaced paths (`alreadySurfaced` set)
3. Sends memory manifest + user query to **Sonnet** (side-query)
4. Sonnet selects up to **5 most relevant** memories
5. Returns `{path, mtimeMs}` — path + modification time

**Key Design Decisions:**
- Uses a **separate LLM call** (sideQuery to Sonnet) for relevance ranking
- System prompt is carefully crafted: "Be selective and discerning"
- Recent tools filter: if Claude Code is already using a tool, don't surface reference docs for it — BUT DO surface warnings/gotchas
- Budget: max 5 memories per query (prevents context bloat)
- `alreadySurfaced` prevents re-picking same memories across turns
- JSON schema output for structured parsing
- Graceful failure: returns `[]` on any error

**🎯 Master AI Implementation Notes:**

```
Pattern: LLM-Ranked Memory Recall
Where: brain_core.py or new memory_recall.py
How: 
  - Brain already stores observations in audit.db
  - Add a "recall" function: given a user query/intent, 
    use a cheap LLM (Haiku) to rank which stored memories are relevant
  - Max 5 memories per query (same budget as Claude Code)
  - Use JSON schema output for reliable parsing
  - Filter: exclude memories already in current context
Effort: Medium (need sideQuery equivalent in Python)
Impact: HIGH — currently Brain loads everything or nothing
```

```
Pattern: "Already Surfaced" Dedup
Where: chat_v7.py or tg_intent_router.py
How:
  - Track which memories/context were already injected this conversation
  - Don't re-inject same context on follow-up messages
  - Simple Set[str] of memory IDs passed between turns
Effort: Low
Impact: Medium — reduces context bloat in multi-turn conversations
```

```
Pattern: Recent Tools Filter  
Where: quick_query.py tool selection
How:
  - If user just used a tool, don't show its help/docs again
  - BUT still show warnings/gotchas for active tools
  - Example: if user just ran /تقييم, don't re-explain what it does
    but DO warn about data staleness if applicable
Effort: Low
Impact: Low-Medium — UX improvement
```

---

### File 2: `memoryScan.ts` — Memory Directory Scanner

**How it works:**
1. Reads all `.md` files from memory dir (excluding MEMORY.md index)
2. For each file: reads first **30 lines** (frontmatter only, not full content)
3. Extracts: filename, filePath, mtimeMs, description, type
4. Sorts by **newest first** (most recent memories prioritized)
5. Caps at **200 files** max
6. Uses `Promise.allSettled` — individual file failures don't crash the scan

**Key Design Decisions:**
- **Frontmatter-only reads**: Only reads 30 lines, not the full file
- **Single-pass design**: reads then sorts (avoids double stat calls)
- **Graceful degradation**: `allSettled` means broken files are silently skipped
- **Manifest format**: `- [type] filename (ISO date): description` — one line per memory

**🎯 Master AI Implementation Notes:**

```
Pattern: Lightweight Memory Index (Header-Only Scan)
Where: brain_core.py → new function scan_memory_headers()
How:
  - Brain observations in DB already have: entity_id, observation, timestamp
  - Build a "manifest" view: one-liner per observation with type + timestamp + summary
  - This manifest is what gets sent to LLM for ranking (not full observation text)
  - Only load full observation text AFTER LLM selects relevant ones
  - Similar to MEMORY.md index pattern but from DB instead of files
Effort: Low (SQL query with GROUP_CONCAT or similar)
Impact: HIGH — enables the LLM-ranked recall without context explosion
```

```
Pattern: 200-Item Cap + Newest-First Sort
Where: Any memory/observation retrieval
How:
  - Never load more than 200 items for ranking
  - Always sort newest-first (recency bias is intentional)
  - If >200 items exist, old ones naturally fall off
  - Master AI Brain has ~182 entities — fits well within this cap
Effort: Trivial (SQL LIMIT + ORDER BY)
Impact: Performance safety net
```

```
Pattern: Promise.allSettled for Resilient Batch Operations
Where: Any batch operation in server.py (e.g., bulk Bridge API calls)
How:
  - Python equivalent: asyncio.gather(*tasks, return_exceptions=True)
  - Don't let one failed stock quote crash the entire radar refresh
  - Already partially used in stock_radar.py but inconsistently
  - Standardize: all batch operations use gather with return_exceptions=True
Effort: Low (pattern exists, needs consistency)
Impact: Medium — reliability improvement
```

---

### File 3: `memoryAge.ts` — Staleness Detection

**How it works:**
1. `memoryAgeDays(mtimeMs)` — calculates days since last modification
2. `memoryAge(mtimeMs)` — human-readable: "today", "yesterday", "47 days ago"
3. `memoryFreshnessText(mtimeMs)` — staleness WARNING for memories >1 day old
4. `memoryFreshnessNote(mtimeMs)` — same but wrapped in `<system-reminder>` tags

**The Critical Insight — Memory Drift Caveat:**
For memories older than 1 day, Claude Code injects this warning:
> "This memory is N days old. Memories are point-in-time observations, not live state — 
> claims about code behavior or file:line citations may be outdated. 
> Verify against current code before asserting as fact."

This was motivated by **real user reports**: stale code-state memories being asserted 
as fact by the LLM. The citation (file:line) actually made stale claims SOUND MORE 
authoritative, not less.

**Key Design Decisions:**
- Fresh memories (≤1 day) = NO warning (avoid noise)
- Old memories (>1 day) = ALWAYS warned
- Human-readable age ("47 days ago") instead of ISO timestamps
  - Reason: "Models are poor at date arithmetic"
- Warning is per-memory, not global — each stale memory gets its own caveat

**🎯 Master AI Implementation Notes:**

```
Pattern: Memory Staleness Caveat
Where: brain_core.py observations, signal_review.py patterns, daily context
How:
  - When Brain returns observations, tag each with age
  - If observation >1 day old, prepend: "⚠️ N days old — verify before acting"
  - ESPECIALLY important for:
    * Stock patterns: market conditions change daily
    * HA entity states: "light was on" ≠ "light is on"  
    * Trading signals: a signal from 3 days ago is NOT current
  - Daily context already has `daily_context_stale` flag — extend this pattern
  - For Telegram bot responses: if using cached data, always show age
Effort: Low
Impact: HIGH — prevents the exact problem Claude Code users reported:
  stale data being presented as current fact
```

```
Pattern: Human-Readable Age vs ISO Timestamps
Where: All user-facing timestamps (Telegram, dashboard, etc.)
How:
  - Instead of "2026-03-30T14:22:00Z" → "3 days ago"
  - LLMs and humans both parse "3 days ago" faster than ISO dates
  - Already partially done in some dashboards but not consistently
  - Add utility function: def memory_age(timestamp) -> str
Effort: Trivial
Impact: UX improvement across all surfaces
```

---

## P2: Query Engine — Full Analysis

### File 4: `QueryEngine.ts` — Session State + Query Lifecycle

**Architecture Overview:**
- **One QueryEngine per conversation** — owns the full session state
- Each `submitMessage()` = one user turn within the conversation
- State persists across turns: messages, file cache, usage, etc.

**Key Components:**
1. **mutableMessages[]** — the conversation history (grows across turns)
2. **readFileState** — cache of file contents already read (avoids re-reading)
3. **totalUsage** — cumulative token usage tracking
4. **discoveredSkillNames** — skills found this turn (cleared per turn)
5. **loadedNestedMemoryPaths** — memory files already loaded (persists across turns)
6. **permissionDenials[]** — tracks all denied tool permissions

**Query Flow:**
```
1. processUserInput() — parse user input, detect slash commands
2. Build system prompt (default + custom + memory mechanics + append)
3. Record transcript BEFORE API call (crash-safe resume)
4. Enter query() loop:
   a. Build context: system prompt + user context + system context
   b. Auto-compact if needed (summarize old messages)
   c. Call model with streaming
   d. Execute tools (streaming or sequential)
   e. Collect attachments (memories, file changes, queued commands)
   f. Loop back if tool results need follow-up
5. Yield final result with usage stats
```

**Key Design Decisions:**

1. **Pre-query transcript recording:**
   - Saves user message BEFORE calling API
   - If process is killed mid-request, conversation is still resumable
   - "The await is ~4ms on SSD, ~30ms under disk contention"

2. **Budget tracking (3 kinds):**
   - `maxTurns` — hard limit on conversation depth
   - `maxBudgetUsd` — dollar cost cap
   - `taskBudget` — API-level task budget (total + remaining)
   - Each checked after every tool execution

3. **Model fallback:**
   - If primary model fails (rate limit, etc.), falls back to specified model
   - Strips thinking signatures before retry (model-bound format)
   - Yields system message: "Switched to X due to high demand for Y"

4. **Structured output retry:**
   - If JSON schema validation fails, retries up to 5 times
   - Tracks retry count across the query

5. **Session persistence:**
   - Every assistant message → fire-and-forget transcript write
   - Compact boundaries → await transcript write (must be durable)
   - "Eager flush" mode for cowork/desktop environments

**🎯 Master AI Implementation Notes:**

```
Pattern: Pre-Execution State Persistence
Where: server.py request handling, Telegram command processing
How:
  - Before executing ANY long operation (Bridge API call, bulk analysis):
    1. Log the intent to audit.db (what we're about to do)
    2. Execute the operation
    3. Log the result
  - If server crashes mid-operation, we know what was in-flight
  - Currently Master AI has some logging but not systematic "pre-logging"
  - Add to: signal engine runs, radar refreshes, priority calculations
Effort: Medium
Impact: Medium — crash recovery improvement
```

```
Pattern: Multi-Layered Budget System
Where: server.py autonomy system (already has L0-L3 + policy scores)
How:
  - Claude Code tracks: turns, cost, task budget
  - Master AI should track per-command:
    * Turn count (how many LLM calls for this task)
    * Token usage (cumulative input + output)
    * Wall-clock time
    * API calls to Bridge
  - Use these for the autonomy scoring: expensive operations = higher score
  - Already have policy: auto ≤ 30, approval ≤ 60, block ≥ 61
  - Add: if cumulative cost > threshold, auto-escalate to next level
Effort: Medium
Impact: Medium — better autonomy control
```

```
Pattern: Model Fallback Chain
Where: chat_v7.py or any LLM-calling code
How:
  - Primary model fails → try fallback
  - Claude Code: Sonnet → specified fallback
  - Master AI equivalent: if Haiku fails (rate limit), 
    queue for retry instead of failing silently
  - For critical paths (morning report, signal alerts):
    retry with backoff before giving up
  - Already partially done but not formalized
Effort: Low
Impact: Medium — reliability
```

---

### File 5: `query.ts` — The Core Query Loop (1729 lines)

**Architecture Overview:**
This is the beating heart of Claude Code. It's a state machine implemented as 
an infinite `while(true)` loop with explicit `continue`/`return` transitions.

**Loop Structure:**
```
while (true) {
  1. SETUP: Build context, inject user context
  2. SNIP: Remove old/irrelevant messages (HISTORY_SNIP feature)
  3. MICROCOMPACT: Compress tool results (lightweight, cached)
  4. CONTEXT_COLLAPSE: Project collapsed view of old turns
  5. AUTOCOMPACT: Full summarization if context too large
  6. BLOCKING CHECK: Reject if still over limit after compaction
  7. STREAM API CALL: Send to model, receive streaming response
  8. HANDLE RESPONSE: Process assistant messages + tool calls
  9. TOOL EXECUTION: Run tools (streaming or sequential)
  10. ATTACHMENTS: Inject memories, file changes, queued commands
  11. BUDGET CHECK: turns, cost, task budget
  12. CONTINUE or RETURN based on state transitions
}
```

**Key Innovation — 4-Layer Context Compaction:**

| Layer | Name | Purpose | Cost |
|-------|------|---------|------|
| 1 | Snip | Remove marked old segments | Free (no LLM) |
| 2 | Microcompact | Compress tool results | Free (cached) |
| 3 | Context Collapse | Staged collapse of old turns | Cheap |
| 4 | Autocompact | Full conversation summary | Expensive (LLM) |

Each layer runs in order. If cheaper layers free enough space, expensive ones are skipped.

**Recovery Mechanisms:**
- **Prompt too long (413)**: Try collapse drain → reactive compact → surface error
- **Max output tokens**: Escalate to 64k → multi-turn recovery (up to 3 retries)
- **Model fallback**: Switch model on rate limit
- **Image size error**: Specific error handling
- **Media recovery**: Strip oversized images and retry

**Streaming Tool Execution:**
- Tools can execute IN PARALLEL with model streaming
- `StreamingToolExecutor` starts tools as soon as their blocks arrive
- Results are collected after streaming completes
- Fallback: sequential execution if streaming disabled

**Memory Prefetch:**
- Memory relevance check starts at turn BEGIN (before API call)
- Runs in parallel with model streaming
- Consumed after tool execution (when results are ready)
- Uses `using` (dispose pattern) for cleanup on any exit path

**🎯 Master AI Implementation Notes:**

```
Pattern: Multi-Layer Context Management
Where: chat_v7.py context building
How:
  Current Master AI approach: load everything → hope it fits
  Better approach (from Claude Code):
  
  Layer 1 — Snip (free): 
    Mark old conversation parts as "snippable"
    Remove them before sending to LLM
    Master AI: trim old Telegram messages after N turns
    
  Layer 2 — Compress (cheap):
    Summarize tool outputs (API responses, DB query results)
    Keep summary, discard raw data
    Master AI: compress old Bridge API responses in chat history
    
  Layer 3 — Summarize (expensive):
    Full conversation summary when context gets too large
    Master AI: use Haiku to summarize old conversation context
    Only trigger when total tokens > threshold
    
  This is the SINGLE MOST VALUABLE pattern for Master AI.
  Currently chat_v7.py has no context management — conversations
  just grow until they hit limits or get reset.
Effort: HIGH (but highest impact)
Impact: CRITICAL — enables longer, more coherent conversations
```

```
Pattern: State Machine Query Loop (Explicit Transitions)
Where: Potential refactor of chat_v7.py or tg_intent_router.py
How:
  Claude Code's query loop uses explicit state transitions:
  - State object carries all mutable data between iterations
  - Each `continue` site describes WHY it's continuing:
    * next_turn, reactive_compact_retry, max_output_tokens_recovery,
    * collapse_drain_retry, stop_hook_blocking, token_budget_continuation
  - This makes debugging MUCH easier — you can see the exact path
  
  Master AI equivalent:
  - Currently intent routing is a big if/elif chain
  - Refactor to: State object + transition reasons
  - Each handler returns a Transition (Continue/Terminal)
  - Log transitions to audit.db for debugging
  
  This is a FUTURE refactor, not urgent.
Effort: HIGH
Impact: Medium (maintainability, debuggability)
```

```
Pattern: Streaming Tool Execution (Parallel)
Where: stock_radar.py, golden_engine.py batch operations
How:
  Claude Code starts executing tools WHILE the model is still streaming.
  Master AI equivalent:
  - When processing multiple stocks, start Bridge API calls in parallel
  - Don't wait for stock #1 to finish before starting stock #2
  - Already partially done with asyncio.gather but not consistently
  - Formalize: use asyncio.TaskGroup (Python 3.11+) for structured concurrency
  - Key: RPi is on Python 3.11, so TaskGroup is available
Effort: Medium
Impact: Medium — speed improvement for batch operations
```

```
Pattern: Memory Prefetch (Speculative Loading)
Where: chat_v7.py conversation handler
How:
  Claude Code starts memory search BEFORE the main LLM call.
  While the model thinks, memories are being retrieved in background.
  
  Master AI equivalent:
  - When a Telegram message arrives:
    1. Immediately start: Brain observation lookup (in background)
    2. Immediately start: recent signal check (in background)  
    3. Parse intent + route to handler
    4. Handler awaits the prefetched results (usually already done)
  - This hides the latency of DB queries behind intent parsing
  - Current flow: parse → then query DB → then respond (sequential)
Effort: Medium
Impact: Medium — latency reduction for complex queries
```

```
Pattern: Graceful Error Recovery Cascade
Where: Any error-prone operation in server.py
How:
  Claude Code's error cascade:
  1. First: try cheapest fix (collapse drain)
  2. Then: try moderate fix (reactive compact)  
  3. Then: try expensive fix (full recompact)
  4. Finally: surface error to user
  
  Master AI equivalent for Bridge API failures:
  1. First: retry with backoff (maybe transient)
  2. Then: use cached data with staleness warning
  3. Then: degrade gracefully (show what we have)
  4. Finally: tell user Bridge is offline
  
  Already partially done via degraded_mode, but the CASCADE 
  pattern (try cheap first) should be formalized.
Effort: Low (pattern exists, needs ordering)
Impact: Medium — reliability
```

---

## Summary: Top 5 Patterns by Impact/Effort Ratio

| # | Pattern | Impact | Effort | Priority |
|---|---------|--------|--------|----------|
| 1 | Memory Staleness Caveat | HIGH | Low | 🔴 P1 |
| 2 | LLM-Ranked Memory Recall | HIGH | Medium | 🔴 P1 |
| 3 | Lightweight Memory Index (Header-Only) | HIGH | Low | 🔴 P1 |
| 4 | Multi-Layer Context Management | CRITICAL | High | 🔴 P1 (long-term) |
| 5 | Memory Prefetch (Speculative Loading) | Medium | Medium | 🟡 P2 |

### Recommended Implementation Order:
1. **Memory Staleness Caveat** — trivial to add, immediately prevents stale data issues
2. **Human-Readable Age** — utility function, use everywhere
3. **Lightweight Memory Index** — SQL query, enables #4
4. **LLM-Ranked Memory Recall** — the killer feature, needs #3 first
5. **Multi-Layer Context Management** — long-term architectural improvement

---

## Next Steps
- [ ] P3: Task/Agent System analysis (Task.ts, tasks.ts, coordinator/)
- [ ] P4: Tool Architecture (Tool.ts, tools.ts, BashTool/, AgentTool/)
- [ ] P5: Hook/Plugin System
- [ ] P6: Other (voice, skills, state, migrations)


---

## P3: Task/Agent System — Full Analysis

### File 6: `tasks/types.ts` — Task State Model

**Task Types (7 concrete):**
1. `LocalShellTask` — shell commands running in background
2. `LocalAgentTask` — local sub-agents
3. `RemoteAgentTask` — remote agents
4. `InProcessTeammateTask` — in-process teammates (share terminal)
5. `LocalWorkflowTask` — multi-step workflows
6. `MonitorMcpTask` — MCP server monitoring
7. `DreamTask` — "dreaming" mode (background processing)

**Status Model:** `running | pending | completed | failed | killed`

**Background Task Logic:**
- A task is "background" if: (status=running OR pending) AND isBackgrounded=true
- Foreground tasks (isBackgrounded=false) are NOT shown in background indicator

**🎯 Master AI Implementation Notes:**

```
Pattern: Typed Task State Machine  
Where: New task_manager.py or extend server.py
How:
  Master AI currently has ad-hoc async operations (radar refresh, 
  Bridge polling, daily snapshot, news fetching, etc.)
  
  Formalize into typed tasks:
  - RadarRefreshTask (status: running/completed/failed, started_at, stocks_done/total)
  - BridgePollingTask (status: running/degraded/offline)
  - DailySnapshotTask (status: running/completed, progress)
  - NewsEngineTask (status: running/completed, last_fetch)
  - SignalAlertTask (status: queued/sent/failed)
  
  Each task has:
  - id, type, status, created_at, updated_at
  - progress (optional: 45/128 stocks done)
  - result or error
  
  Benefits:
  - /status Telegram command shows all running tasks
  - Dashboard "System" page shows task states
  - Crash recovery: know what was running when server died
  - Audit: task history in audit.db
  
Effort: Medium
Impact: HIGH — visibility into what Master AI is doing right now
```

---

### File 7: `coordinator/coordinatorMode.ts` — Multi-Agent Orchestration

**Architecture:**
Coordinator mode turns Claude Code into a **task orchestrator** that:
1. Receives user request
2. Spawns **workers** (sub-agents) for research/implementation/verification
3. Workers run in parallel (async)
4. Coordinator synthesizes results and communicates with user

**Key Design Decisions:**

1. **Coordinator never executes** — it ONLY delegates and synthesizes
2. **Workers are async and independent** — each gets its own AbortController
3. **Workers can't see coordinator's conversation** — prompts must be self-contained
4. **Results arrive as `<task-notification>` XML** — structured format
5. **Workers have limited tools** — scoped per task
6. **Scratchpad directory** — shared filesystem for cross-worker knowledge
7. **Session mode persistence** — coordinator/normal mode survives resume

**Workflow Phases:**
| Phase | Actor | Purpose |
|-------|-------|---------|
| Research | Workers (parallel) | Investigate, find files, understand |
| Synthesis | Coordinator | Read findings, craft specs |
| Implementation | Workers | Make changes, commit |
| Verification | Workers | Test, typecheck, prove it works |

**Critical Rule: "Never delegate understanding"**
- BAD: "Based on your findings, fix the auth bug"
- GOOD: "Fix the null pointer in src/auth/validate.ts:42. The user field..."
- Coordinator must SYNTHESIZE research into specific implementation specs

**🎯 Master AI Implementation Notes:**

```
Pattern: Coordinator-Worker Architecture for Complex Tasks
Where: Potential future evolution of Master AI
How:
  Current Master AI: single-threaded, sequential command processing
  
  Coordinator pattern would enable:
  - User: "حلل سهم CLEANING و SENERGY و INOVEST"
  - Master AI (coordinator):
    → Worker 1: analyze CLEANING (Bridge API + patterns)
    → Worker 2: analyze SENERGY (Bridge API + patterns)  
    → Worker 3: analyze INOVEST (Bridge API + patterns)
    → All run in parallel
    → Coordinator synthesizes: "CLEANING أقوى إشارة شراء..."
  
  Currently this happens sequentially (one stock at a time).
  
  Implementation:
  - Not full sub-agent LLM calls (too expensive)
  - Instead: parallel asyncio tasks with structured results
  - Each "worker" = a coroutine that calls Bridge + Brain + patterns
  - "Coordinator" = the main handler that merges results
  
  Already partially done with asyncio.gather in stock_radar.py,
  but not formalized as a pattern.
  
Effort: Low (asyncio.gather is the mechanism, just formalize it)
Impact: Medium — speed improvement for multi-stock analysis
```

```
Pattern: Scratchpad / Shared Working Directory
Where: _tools/ directory already serves this role partially
How:
  Claude Code has a "scratchpad" where workers share intermediate results
  without permission prompts.
  
  Master AI equivalent:
  - data/scratch/ directory for temporary cross-component data
  - Example: radar writes analysis → alert engine reads it
  - Currently they share via DB, which is fine
  - But for non-DB artifacts (charts, reports, temp files):
    use a dedicated scratch space
  - Clean up: cron job or startup cleanup for files >24h old
  
Effort: Trivial
Impact: Low — organizational improvement
```

---

### File 8: `tools/AgentTool/runAgent.ts` — Sub-Agent Execution

**Architecture:**
This is how Claude Code spawns and manages sub-agents (973 lines).

**Key Flow:**
1. Create agentId (unique per agent)
2. Resolve model (agent-specific or parent's model)
3. Build initial messages (context fork + prompt + skills + hook context)
4. Initialize agent-specific MCP servers
5. Create isolated ToolUseContext (own abort controller, own file cache)
6. Run query() loop inside the agent
7. Record transcript to sidechain (separate from main conversation)
8. Cleanup on exit (MCP, hooks, file cache, shell tasks, Perfetto, etc.)

**Key Design Decisions:**

1. **Context Isolation:**
   - Each agent gets its OWN readFileState cache (cloned from parent)
   - Async agents get own AbortController (independent lifecycle)
   - Async agents: setAppState is no-op (fully isolated from parent)
   - Sync agents share parent's setAppState and AbortController

2. **Sidechain Transcripts:**
   - Each agent records its conversation to a SEPARATE transcript
   - Uses `lastRecordedUuid` as parent chain for incremental writes
   - Initial messages recorded BEFORE query loop (crash-safe)

3. **Memory Scoping (3 levels):**
   - `user` scope: ~/.claude/agent-memory/ (global, cross-project)
   - `project` scope: .claude/agent-memory/ (shared via git)
   - `local` scope: .claude/agent-memory-local/ (machine-specific)

4. **Cleanup Discipline (finally block):**
   - MCP servers → session hooks → prompt cache tracking
   - File state cache → initial messages → Perfetto → transcript subdir
   - Agent todos → background shell tasks → MCP monitor tasks
   - 11 separate cleanup operations!

5. **Incomplete Tool Call Filtering:**
   - When forking context to a sub-agent, filter out assistant messages
     with tool_use blocks that don't have matching tool_result blocks
   - Prevents API errors from orphaned tool calls

6. **Skill Preloading:**
   - Agent can declare required skills in frontmatter
   - Skills are loaded BEFORE the agent starts (added to initialMessages)
   - Resolution: exact match → plugin prefix → suffix match

**🎯 Master AI Implementation Notes:**

```
Pattern: Comprehensive Cleanup in finally Block
Where: server.py long-running operations
How:
  Claude Code's agent cleanup has 11 items in finally{}.
  Master AI needs similar discipline for:
  
  - Bridge polling: on exit, mark as offline in health endpoint
  - Radar refresh: on exit, release any locks, log completion
  - News engine: on exit, flush pending news items
  - Signal alerts: on exit, mark unsent alerts as failed
  
  Currently: if radar refresh crashes mid-way, there's no cleanup.
  Some resources may stay in inconsistent state.
  
  Pattern: wrap every long operation in try/finally with explicit cleanup.
  Log cleanup failures but don't raise them (same as Claude Code).
  
Effort: Low (add finally blocks to existing operations)
Impact: Medium — reliability improvement
```

```
Pattern: Sidechain Logging for Background Operations
Where: audit.db or new sidechains table
How:
  Claude Code records each sub-agent's conversation SEPARATELY.
  
  Master AI equivalent:
  - Each background operation (radar, news, signals) gets its own
    "sidechain" log in audit.db
  - operation_id, parent_operation_id (for nesting)
  - Each log entry: operation_id, step, input, output, timestamp
  - Enables: "show me what the radar was doing when it crashed"
  
  Currently: operations log to general audit trail mixed together.
  Hard to follow one operation's lifecycle.
  
Effort: Medium (new table + logging calls)
Impact: Medium — debuggability
```

```
Pattern: 3-Level Memory Scoping (User / Project / Local)
Where: Brain observations system
How:
  Claude Code separates memories into:
  - User: applies across all projects
  - Project: shared with team
  - Local: machine-specific, not shared
  
  Master AI equivalent:
  - Trading observations: "user" scope (apply to all stocks)
  - Stock-specific patterns: "project" scope (shared knowledge)
  - Device states: "local" scope (this RPi only)
  
  Brain already has entity_domain but could benefit from
  an explicit scope field:
  - scope='global': trading rules, risk limits
  - scope='stock': per-stock patterns, personality
  - scope='device': per-device quirks, HA entity behaviors
  
Effort: Low (add scope column)
Impact: Medium — better observation organization
```

---

## P3 Summary: Top Patterns

| # | Pattern | Impact | Effort | Priority |
|---|---------|--------|--------|----------|
| 1 | Typed Task State Machine | HIGH | Medium | 🔴 P1 |
| 2 | Comprehensive Cleanup (finally) | Medium | Low | 🔴 P1 |
| 3 | Coordinator-Worker Parallelism | Medium | Low | 🟡 P2 |
| 4 | Sidechain Logging per Operation | Medium | Medium | 🟡 P2 |
| 5 | 3-Level Memory Scoping | Medium | Low | 🟡 P2 |
| 6 | Incomplete Context Filtering | Low | Low | 🟢 P3 |

---

## Overall Priority Matrix (P1 + P2 + P3 combined)

### 🔴 Do First (High Impact, Reasonable Effort)
1. **Memory Staleness Caveat** — trivial, prevents stale data bugs
2. **Human-Readable Age** — utility function, improves all surfaces
3. **Typed Task State Machine** — formalize background operations
4. **Lightweight Memory Index** — enables LLM-ranked recall

### 🟡 Do Next (High Impact, More Effort)
5. **LLM-Ranked Memory Recall** — Haiku selects relevant observations
6. **Comprehensive Cleanup (finally)** — wrap all long operations
7. **Memory Prefetch (Speculative Loading)** — hide DB latency

### 🔵 Long-Term (Highest Impact, Highest Effort)
8. **Multi-Layer Context Management** — 4-layer compaction for chat_v7.py
9. **State Machine Query Loop** — refactor intent routing

---

## Next Steps
- [ ] P4: Tool Architecture (Tool.ts, BashTool/, SkillTool/)
- [ ] P5: Hook/Plugin System
- [ ] P6: Other (voice, skills, state, migrations)


---

## P4: Tool Architecture — Full Analysis

### File 9: `Tool.ts` — Base Tool Interface (792 lines)

**Architecture Overview:**
This defines the COMPLETE interface that every tool in Claude Code must implement.
It's 792 lines of pure type definitions — the most comprehensive tool contract I've seen.

**Core Tool Interface Methods:**

| Method | Purpose | Required? |
|--------|---------|-----------|
| `call()` | Execute the tool | ✅ Yes |
| `inputSchema` | Zod schema for input validation | ✅ Yes |
| `prompt()` | System prompt text describing the tool | ✅ Yes |
| `checkPermissions()` | Tool-specific permission logic | Default: allow |
| `validateInput()` | Pre-execution validation | Optional |
| `description()` | Human-readable description | ✅ Yes |
| `isEnabled()` | Whether tool is currently available | Default: true |
| `isReadOnly()` | Whether tool only reads (no writes) | Default: false |
| `isDestructive()` | Whether tool is irreversible | Default: false |
| `isConcurrencySafe()` | Whether tool can run in parallel | Default: false |
| `isSearchOrReadCommand()` | UI collapse classification | Optional |
| `isOpenWorld()` | Whether tool makes external calls | Optional |
| `requiresUserInteraction()` | Whether tool needs user input | Optional |
| `toAutoClassifierInput()` | Security classifier representation | Default: '' |
| `maxResultSizeChars` | Max output before disk persistence | ✅ Yes |

**Key Design Decisions:**

1. **`buildTool()` Factory with Safe Defaults:**
   - Every tool goes through `buildTool()` which fills in defaults
   - Defaults are FAIL-CLOSED: `isConcurrencySafe=false`, `isReadOnly=false`
   - "Tools not explicitly marked safe are assumed unsafe"

2. **3-Layer Permission Model:**
   - `validateInput()` → Is the input structurally valid?
   - `checkPermissions()` → Tool-specific permission logic
   - External permission system → General permission rules (allow/deny/ask)

3. **Tool Classification Flags:**
   - `isReadOnly` — read-only tools can run with fewer permissions
   - `isDestructive` — destructive tools get extra warnings
   - `isConcurrencySafe` — safe tools can run in parallel
   - `isSearchOrReadCommand` — UI display optimization
   - `shouldDefer` — deferred tools loaded on demand (ToolSearch)

4. **Result Size Management:**
   - `maxResultSizeChars` — if result exceeds this, persisted to disk
   - Tool gets a preview instead of full content
   - Prevents context explosion from large tool outputs
   - `Infinity` for tools that self-bound (e.g., FileRead)

5. **ToolUseContext — The God Object (50+ fields):**
   - Carries ALL state a tool might need
   - Messages, options, abort controller, file cache, app state
   - Agent context, memory triggers, skill tracking
   - Permission context, query tracking, attribution state

**🎯 Master AI Implementation Notes:**

```
Pattern: Typed Tool Interface with Safe Defaults (buildTool)
Where: Master AI tool/command registration system
How:
  Currently Master AI has 12+ Telegram commands (/فرص, /تقييم, /report, etc.)
  registered as ad-hoc functions in tg_intent_router.py.
  
  Formalize with a Tool interface:
  
  class MasterAITool:
      name: str
      description: str
      is_read_only: bool = False       # default unsafe
      is_destructive: bool = False
      requires_bridge: bool = False     # needs Bridge API
      max_result_chars: int = 4000      # Telegram message limit
      autonomy_cost: int = 10           # for autonomy scoring
      
      def validate_input(self, args) -> ValidationResult
      def check_permission(self, context) -> PermissionResult  
      def execute(self, args, context) -> ToolResult
  
  Benefits:
  - Every command declared with its properties upfront
  - Autonomy system can auto-score based on tool flags
  - Commands that need Bridge fail gracefully when offline
  - Result size capping prevents Telegram message overflow
  - New commands get safe defaults automatically
  
Effort: Medium (refactor existing commands into class-based)
Impact: HIGH — foundation for extensible tool system
```

```
Pattern: 3-Layer Validation (Input → Permission → Execute)
Where: tg_intent_router.py command processing
How:
  Currently: receive command → try to execute → handle errors after the fact
  
  Better (from Claude Code):
  1. validateInput() — Is the argument valid? (e.g., is stock ticker real?)
  2. checkPermission() — Can this user/context run this now? (e.g., Bridge online?)
  3. execute() — Do the actual work
  
  Each layer can reject with a clear error message.
  Currently errors surface as generic "حدث خطأ" — this would give
  specific errors like "سهم غير موجود" or "البريدج مو متصل"
  
Effort: Low (add validation before existing execution)
Impact: Medium — better error messages, clearer flow
```

```
Pattern: Result Size Management (maxResultSizeChars)
Where: Any tool that returns data to Telegram or dashboard
How:
  Claude Code persists large results to disk and returns a preview.
  
  Master AI equivalent:
  - If analysis result > 4000 chars (Telegram limit): truncate + add "..."
  - For dashboard: if data > threshold, paginate or summarize
  - For /فرص with many opportunities: show top 5 + "والباقي NN فرصة"
  - Already partially done but not standardized
  
  Add to each tool definition: max_result_chars
  Tool base class handles truncation automatically
  
Effort: Low
Impact: Medium — consistent output handling
```

```
Pattern: Tool Classification Flags for Autonomy
Where: Autonomy system (server.py policy scoring)
How:
  Claude Code classifies tools: read-only, destructive, concurrency-safe, etc.
  
  Master AI equivalent for autonomy scoring:
  - is_read_only=True: /status, /report → auto-execute always (cost=5)
  - is_read_only=False, is_destructive=False: /فرص, /تقييم → auto if ≤30 (cost=15)
  - is_destructive=True: /sell, /alert → require approval (cost=50)
  - requires_bridge=True: all trading tools → fail gracefully if offline
  
  Currently autonomy cost is ad-hoc. Tool flags make it systematic.
  
Effort: Low (add flags, compute cost from flags)
Impact: Medium — better autonomy decisions
```

---

### File 10: `BashTool.tsx` — Shell Execution (1144 lines)

**Key Patterns:**

1. **Command Classification:**
   - Search commands: grep, find, rg, ag, ack, locate
   - Read commands: cat, head, tail, wc, stat, jq, awk
   - List commands: ls, tree, du
   - Silent commands: mv, cp, rm, mkdir (expect no stdout)
   - Semantic-neutral: echo, printf, true, false (don't change classification)
   
   Pipeline classification: ALL parts must be read/search for whole to be classified.

2. **Progress Display:**
   - Show progress after 2 seconds (PROGRESS_THRESHOLD_MS = 2000)
   - In assistant mode, auto-background blocking operations after 15 seconds

3. **Security:**
   - `parseForSecurity()` — AST-level security analysis of shell commands
   - Permission matching with wildcard patterns
   - Sandbox support for untrusted execution

4. **Output Management:**
   - `EndTruncatingAccumulator` — keeps beginning + end, truncates middle
   - Large outputs persisted to disk (same maxResultSizeChars pattern)
   - Image output detection and resizing

**🎯 Master AI Implementation Notes:**

```
Pattern: Command Classification for UX
Where: Telegram command responses / dashboard display
How:
  BashTool classifies commands to optimize UI display.
  
  Master AI equivalent:
  - Read commands (/status, /weather, /shift): show result inline, collapse if long
  - Action commands (/alert, /sell): show confirmation + result
  - Analysis commands (/فرص, /موجة): show progress indicator, then full result
  - Background commands (radar refresh): show "جاري التحديث..." then notify on complete
  
  Currently all commands display the same way. Classification enables
  different UX per command type.
  
Effort: Low (classification already exists via tool flags)
Impact: Medium — UX improvement
```

```
Pattern: Progress After N Seconds
Where: Long-running operations (radar refresh, bulk analysis)
How:
  BashTool shows progress after 2 seconds of execution.
  
  Master AI equivalent:
  - For Telegram: if operation takes > 2 seconds, send "⏳ جاري التحليل..."
  - Update with progress: "⏳ تحليل 45/128 سهم..."
  - Final result replaces or follows progress message
  - For dashboard: loading spinner with progress percentage
  
  Currently: user waits with no feedback until completion.
  
Effort: Low
Impact: HIGH — UX improvement for long operations
```

---

### File 11: `SkillTool.ts` — Skill/Plugin System (1108 lines)

**Architecture Overview:**
Skills are reusable prompts/workflows that Claude Code can invoke.
Two execution modes:
- **Inline**: skill prompt injected into current conversation
- **Forked**: skill runs in a separate sub-agent context

**Key Patterns:**

1. **Skill Discovery & Resolution:**
   - Local skills: from .claude/ directory
   - MCP skills: from connected MCP servers  
   - Remote skills: canonical skills from cloud (experimental)
   - Resolution: exact match → plugin prefix → suffix match

2. **Skill Execution Modes:**
   - `context: 'inline'` → skill prompt added to current messages
   - `context: 'fork'` → skill runs in isolated sub-agent via runAgent()
   
3. **Permission Management:**
   - Safe properties allowlist → auto-allow
   - Deny rules checked first → block
   - Allow rules checked second → allow
   - Default → ask user

4. **Context Modification:**
   - Skills can modify tool permissions (allowedTools)
   - Skills can override model (e.g., use opus for complex analysis)
   - Skills can override effort level
   - All via `contextModifier` callback

5. **Telemetry:**
   - Every invocation tracked: command name, source, execution context
   - was_discovered flag: was skill found via ToolSearch?
   - Plugin tracking: marketplace, repository, version

**🎯 Master AI Implementation Notes:**

```
Pattern: Skill/Plugin System for Master AI
Where: New skills/ directory or _tools/ expansion  
How:
  Claude Code's Skill system maps to Master AI's potential plugin architecture:
  
  Skill = a reusable analysis or action template:
  - "تحليل_فني": runs RSI + MACD + EMA analysis on a stock
  - "تقييم_يومي": daily evaluation combining multiple indicators
  - "فحص_صحة": system health check (Bridge + HA + Network)
  
  Each skill is a .md file with:
  ---
  name: تحليل_فني
  requires_bridge: true
  max_stocks: 10
  output_format: telegram_card
  ---
  [Prompt/template for the analysis]
  
  Benefits:
  - Reusable patterns instead of hardcoded commands
  - Users could add custom skills (future)
  - Skills can be versioned and A/B tested
  
  This is a FUTURE architecture, not immediate need.
  Current system works fine with hardcoded commands.
  
Effort: HIGH
Impact: Medium (long-term extensibility)
```

```
Pattern: Context Modification (Tools + Model Override per Skill)
Where: Command execution in tg_intent_router.py
How:
  Claude Code skills can temporarily change:
  - Which tools are available
  - Which model to use  
  - Effort level
  
  Master AI equivalent:
  - Some commands need Bridge (trading) → temporarily require_bridge
  - Some commands need heavy analysis → use more expensive LLM
  - Some commands are quick lookups → use cheapest LLM
  
  Currently: same LLM/resources for all commands.
  Context modification per command = right-size resources.
  
Effort: Medium
Impact: Medium — cost optimization
```

---

## P4 Summary: Top Patterns

| # | Pattern | Impact | Effort | Priority |
|---|---------|--------|--------|----------|
| 1 | Typed Tool Interface (buildTool) | HIGH | Medium | 🔴 P1 |
| 2 | 3-Layer Validation | Medium | Low | 🔴 P1 |
| 3 | Progress After N Seconds | HIGH | Low | 🔴 P1 |
| 4 | Tool Classification for Autonomy | Medium | Low | 🟡 P2 |
| 5 | Result Size Management | Medium | Low | 🟡 P2 |
| 6 | Skill/Plugin System | Medium | High | 🟢 P3 (future) |

---

## MASTER PRIORITY LIST (P1 through P4 combined)

### 🔴 Tier 1: Do Now (High Impact, Low-Medium Effort)
| # | Pattern | Source | Effort |
|---|---------|--------|--------|
| 1 | Memory Staleness Caveat | P1-memoryAge | Low |
| 2 | Human-Readable Age utility | P1-memoryAge | Trivial |
| 3 | Progress After N Seconds (Telegram) | P4-BashTool | Low |
| 4 | 3-Layer Validation (Input→Permission→Execute) | P4-Tool.ts | Low |
| 5 | Comprehensive Cleanup (finally blocks) | P3-runAgent | Low |

### 🟡 Tier 2: Do Next (High Impact, Medium Effort)
| # | Pattern | Source | Effort |
|---|---------|--------|--------|
| 6 | Typed Task State Machine | P3-types | Medium |
| 7 | Lightweight Memory Index (header scan) | P1-memoryScan | Low |
| 8 | LLM-Ranked Memory Recall | P1-findRelevant | Medium |
| 9 | Typed Tool Interface (MasterAITool class) | P4-Tool.ts | Medium |
| 10 | Tool Classification Flags for Autonomy | P4-Tool.ts | Low |

### 🔵 Tier 3: Long-Term (Highest Impact, Highest Effort)
| # | Pattern | Source | Effort |
|---|---------|--------|--------|
| 11 | Multi-Layer Context Management | P2-query.ts | High |
| 12 | State Machine Query Loop | P2-query.ts | High |
| 13 | Coordinator-Worker Parallelism | P3-coordinator | Medium |
| 14 | Skill/Plugin System | P4-SkillTool | High |
| 15 | Memory Prefetch (Speculative Loading) | P2-QueryEngine | Medium |

---

## Next Steps
- [ ] P5: Hook/Plugin System (hooks/, plugins/, services/)
- [ ] P6: Other (voice, skills, state, migrations)


---

## P5: Hook/Plugin/Services System — Full Analysis

### Hooks Directory (80+ files)
The hooks directory contains React hooks for the REPL UI. Most are UI-specific
(useVimInput, useClipboardImageHint, etc.) but several contain patterns valuable 
for Master AI:

### File 12: `useScheduledTasks.ts` — Cron Scheduler

**Architecture:**
- Uses `createCronScheduler()` for periodic task execution
- Fires scheduled prompts as 'later' priority queue items
- Routes cron fires by agentId (teammate-specific or lead agent)
- Orphaned crons (teammate gone) → auto-cleanup
- Runtime killswitch: isKairosCronEnabled() checked every tick
- Jitter config to spread load

**Key Design:**
- Cron tasks can target specific agents (agentId routing)
- When target agent is gone: remove orphaned cron, don't keep firing
- All scheduled fires go through message queue (not direct execution)
- isMeta: true → hidden from transcript UI

**🎯 Master AI Implementation Notes:**

```
Pattern: Cron Scheduler with Agent Routing and Orphan Cleanup
Where: server.py scheduled tasks (morning report, nightly digest, etc.)
How:
  Master AI already has scheduled tasks (5:30 AM morning report, 11PM digest).
  Improvements from Claude Code:
  
  1. Agent routing: each task has a target_handler
     - morning_report → tg_morning_report handler
     - nightly_digest → brain_core handler
     - daily_snapshot → stock_radar handler
  
  2. Orphan cleanup: if handler crashes/missing, auto-disable the task
     instead of silently failing every interval
  
  3. Queue-based execution: tasks go through a queue, not direct calls
     - Prevents overlapping executions
     - Enables retry logic
     - Audit trail for every fire
  
  4. Runtime killswitch: disable tasks without restart
     - Already partially done with feature flags
     - Formalize: each task has an enabled/disabled flag in config
  
Effort: Low-Medium
Impact: Medium — reliability of scheduled tasks
```

---

### File 13: `extractMemories.ts` — Auto Memory Extraction (615 lines)

**This is one of the most valuable files in the entire codebase.**

**Architecture:**
- Runs at END of each query loop (via stopHooks)
- Uses a FORKED AGENT (shares parent's prompt cache) to extract memories
- Writes to auto-memory directory (~/.claude/projects/<path>/memory/)
- Closure-scoped state: cursor position, overlap guard, pending context

**Key Design Decisions:**

1. **Cursor-Based Processing:**
   - `lastMemoryMessageUuid` tracks what was already processed
   - Each run only looks at NEW messages since cursor
   - If extraction fails, cursor stays put → messages reconsidered next time

2. **Mutual Exclusion with Main Agent:**
   - If main agent already wrote memories → skip extraction
   - "The main agent and the background agent are mutually exclusive per turn"

3. **Overlap Prevention:**
   - `inProgress` flag prevents concurrent extractions
   - New calls during extraction → stashed in `pendingContext`
   - After current extraction: run ONE trailing extraction with latest context
   - Multiple stashed calls coalesced (only latest kept)

4. **Throttling:**
   - `turnsSinceLastExtraction` counter
   - Configurable: extract every N eligible turns (default 1)
   - Trailing runs skip throttle (already committed work)

5. **Scoped Permissions:**
   - Forked agent can ONLY: read files, read-only bash, write to memory dir
   - Cannot: write arbitrary files, run destructive commands
   - Security boundary enforced by custom `canUseTool` function

6. **Telemetry:**
   - Tracks: files written, cache hit rate, duration, turn count
   - Separate events for: skip (direct write), coalesced, error, extraction

**🎯 Master AI Implementation Notes:**

```
Pattern: Background Memory Extraction (Post-Turn Processing)
Where: New auto_memory_extractor.py or extend brain_core.py
How:
  THE KILLER PATTERN: After each meaningful conversation turn:
  1. Fork a lightweight analysis of what just happened
  2. Extract durable observations → save to Brain
  3. Don't block the main response
  
  Master AI equivalent:
  - After every Telegram conversation (not just commands):
    → Background task: "What did we just discuss that's worth remembering?"
    → Extract: user preferences, trading decisions, HA changes, etc.
    → Save to audit.db brain_observations
  
  - After every trading signal alert:
    → Background task: "How did this signal compare to recent ones?"
    → Extract: pattern confirmation/rejection
    → Update stock_personality accordingly
  
  Implementation:
  - asyncio.create_task(extract_memories(messages)) — fire-and-forget
  - Cursor-based: only process new messages since last extraction
  - Overlap guard: if extraction running, stash and run after
  - Scoped: extraction can only READ data and WRITE to observations
  
Effort: Medium-High
Impact: CRITICAL — Master AI currently doesn't learn from conversations
  Brain has observations but they're manual/explicit.
  Auto-extraction = continuous learning.
```

```
Pattern: Cursor-Based Incremental Processing
Where: Any system that processes a growing stream of events
How:
  extractMemories uses a "cursor" (lastMessageUuid) to only process
  new data since the last run.
  
  Master AI equivalent:
  - Signal engine: cursor = last_processed_signal_id
    → Only analyze signals newer than cursor
  - News engine: cursor = last_processed_article_id
    → Only process new RSS items
  - Audit trail: cursor = last_reviewed_audit_id
    → Weekly insight only reviews new entries
  
  Currently: some engines re-scan everything on each run
  Cursor pattern = O(new) instead of O(all)
  
Effort: Low
Impact: Medium — performance improvement
```

```
Pattern: Coalesced Background Execution
Where: Any rate-limited background operation
How:
  If extraction is running and new request comes in:
  → Don't queue multiple pending runs
  → Keep only the LATEST context (has most messages)
  → Run exactly ONE trailing extraction after current finishes
  
  Master AI equivalent for Bridge polling:
  - If refresh_daily_snapshot() is running and another refresh requested:
    → Don't start a second concurrent refresh
    → After current finishes, run ONE trailing refresh with latest config
  - Prevents: overlapping API calls, duplicate DB writes, race conditions
  
Effort: Low (add inProgress flag + pending stash)
Impact: Medium — prevents race conditions
```

---

### File 14: `autoCompact.ts` — Auto Compaction System

**Key Constants:**
- MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20,000 (reserve for compaction output)
- AUTOCOMPACT_BUFFER_TOKENS = 13,000 (trigger buffer below context limit)
- WARNING_THRESHOLD_BUFFER_TOKENS = 20,000
- MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3 (circuit breaker!)

**Circuit Breaker Pattern:**
- If autocompact fails 3 times consecutively → STOP TRYING
- Without this: 50+ consecutive failures per session, wasting ~250K API calls/day globally
- Counter resets on success

**🎯 Master AI Implementation Notes:**

```
Pattern: Circuit Breaker for Failing Operations
Where: bridge_client.py, stock_radar.py, any external API call
How:
  Claude Code discovered 250K wasted API calls/day from retrying
  hopeless compactions. They added a 3-failure circuit breaker.
  
  Master AI NEEDS this for:
  - Bridge API: if 3 consecutive connection failures → stop trying for N minutes
    → Currently: keeps retrying every 30s even when PC is off
  - TradingView auth: if JWT expired and 3 refresh failures → alert user
    → Currently: silent failures until user checks manually
  - News RSS: if feed unreachable 3 times → skip for 1 hour
  
  Implementation:
  consecutive_failures = 0
  MAX_FAILURES = 3
  
  if consecutive_failures >= MAX_FAILURES:
      log("Circuit breaker open — skipping operation")
      return degraded_result
  
  try:
      result = await operation()
      consecutive_failures = 0  # reset on success
  except:
      consecutive_failures += 1
      
Effort: Low (simple counter per operation)
Impact: HIGH — prevents wasted resources and silent failure loops
```

---

### File 15: `SessionMemory/sessionMemory.ts` — Session Memory

**Architecture:**
- Maintains a markdown file with notes about current conversation
- Runs periodically in background via forked subagent
- Initialization threshold: doesn't start until enough turns
- Update threshold: waits for meaningful changes between updates

**🎯 Master AI Implementation Notes:**

```
Pattern: Session Summary (Conversation-Level Memory)
Where: chat_v7.py or new session_memory.py
How:
  Distinct from Brain observations (entity-level):
  Session memory captures WHAT HAPPENED in a conversation:
  - "User asked about CLEANING, I recommended hold"
  - "Discussed HA automation fix for bedroom AC"
  - "User reported Bridge offline, troubleshooted together"
  
  Uses:
  - Resume context in next conversation
  - Weekly insights can reference specific sessions
  - Audit: what advice was given and when
  
  Implementation:
  - After each conversation (not each message):
    → Summarize key decisions, recommendations, actions
    → Store in audit.db with session_id
  
Effort: Medium
Impact: Medium — conversation continuity
```

---

### File 16: `PluginInstallationManager.ts` — Plugin Management

**Architecture:**
- Background installation of plugins from trusted sources
- Marketplace reconciliation (diff → install/update)
- Status tracking per marketplace: pending → installing → installed/failed
- Auto-refresh after new installs, notification for updates

**🎯 Master AI Implementation Notes:**

```
Pattern: Background Dependency Management
Where: Master AI startup sequence
How:
  Claude Code installs plugins in background without blocking startup.
  
  Master AI equivalent for startup:
  - Background: check pip packages are up to date
  - Background: verify DB schema matches expected version
  - Background: test Bridge API connectivity
  - Background: warm up news engine RSS feeds
  
  All run concurrently during startup, don't block Telegram bot.
  Currently: sequential startup checks that delay bot availability.
  
Effort: Low (asyncio.gather at startup)
Impact: Low-Medium — faster startup
```

---

## P6: Other Interesting Files — Brief Analysis

### State Management (`state/`)

**AppStateStore.ts** — Central state store with:
- Tool permission context (mode, rules, working directories)
- Task tracking (background tasks, shell tasks)
- Plugin state (installed, errors, installation status)
- Speculation state (for speculative execution / autocomplete)
- MCP connection state
- Todo lists per agent
- Attribution tracking (commit attribution)
- File history state

**Key Pattern:** Single source of truth for ALL application state.
Immutable updates (prev → new state). Selectors for efficient reads.

**🎯 For Master AI:** Already has audit.db as central state. 
Could benefit from an in-memory state cache (like AppState) for
frequently-read values: Bridge status, last refresh time, feature flags.

### Compact Service (`services/compact/`)

**8 files** managing context compaction:
- `autoCompact.ts` — threshold-based auto-trigger
- `compact.ts` — actual compaction (LLM summarization)
- `microCompact.ts` — lightweight tool result compression
- `grouping.ts` — group related messages for better summaries
- `postCompactCleanup.ts` — cleanup after compaction
- `prompt.ts` — compaction system prompt
- `sessionMemoryCompact.ts` — session memory during compaction

**Key Insight:** 8 files for ONE feature (compaction). This shows how
complex context management really is when done properly.

---

## P5+P6 Summary: Top Patterns

| # | Pattern | Impact | Effort | Priority |
|---|---------|--------|--------|----------|
| 1 | Background Memory Extraction | CRITICAL | Medium-High | 🔴 P1 |
| 2 | Circuit Breaker for Failing Ops | HIGH | Low | 🔴 P1 |
| 3 | Cursor-Based Incremental Processing | Medium | Low | 🔴 P1 |
| 4 | Coalesced Background Execution | Medium | Low | 🟡 P2 |
| 5 | Cron Scheduler with Routing | Medium | Low-Medium | 🟡 P2 |
| 6 | Session Summary (Conv. Memory) | Medium | Medium | 🟡 P2 |
| 7 | Background Startup Tasks | Low-Medium | Low | 🟢 P3 |



---

## ═══════════════════════════════════════════════════════════
## FINAL MASTER IMPLEMENTATION PLAN — All Priorities (P1-P6)
## ═══════════════════════════════════════════════════════════

### 🔴 TIER 1: Implement Now (High Impact, Low-Medium Effort)

| # | Pattern | Source File | What To Do | Effort |
|---|---------|-------------|------------|--------|
| 1 | **Memory Staleness Caveat** | memoryAge.ts | Add age warning to Brain observations >1 day old. `"⚠️ N days old — verify"` | Low |
| 2 | **Human-Readable Age** | memoryAge.ts | Utility: `memory_age(ts)` → "today"/"3 days ago". Use in Telegram + dashboard | Trivial |
| 3 | **Circuit Breaker** | autoCompact.ts | Add `consecutive_failures` counter to Bridge, RSS, JWT refresh. Stop after 3 fails | Low |
| 4 | **Progress After N Seconds** | BashTool.tsx | Send "⏳ جاري..." after 2s for long Telegram operations. Update with progress | Low |
| 5 | **3-Layer Validation** | Tool.ts | For each command: validateInput → checkPermission → execute (not try/except after) | Low |
| 6 | **Comprehensive Cleanup** | runAgent.ts | Add `finally` blocks to all long operations (radar, news, signal alerts) | Low |
| 7 | **Cursor-Based Processing** | extractMemories.ts | Use cursors in signal/news/audit engines instead of re-scanning all data | Low |

**Claude Code Plan File:** `_tools/TIER1_QUICK_WINS_PLAN.md`

---

### 🟡 TIER 2: Implement Next (High Impact, Medium Effort)

| # | Pattern | Source File | What To Do | Effort |
|---|---------|-------------|------------|--------|
| 8 | **Typed Task State Machine** | tasks/types.ts | Formalize background ops as typed tasks with status tracking | Medium |
| 9 | **Lightweight Memory Index** | memoryScan.ts | SQL query for observation summaries (not full text) for LLM ranking | Low |
| 10 | **LLM-Ranked Memory Recall** | findRelevantMemories.ts | Use Haiku to select relevant Brain observations per user query | Medium |
| 11 | **Typed Tool Interface** | Tool.ts | `MasterAITool` class with flags: read_only, destructive, requires_bridge, cost | Medium |
| 12 | **Coalesced Background Exec** | extractMemories.ts | `inProgress` flag + pending stash for Bridge polling, radar refresh | Low |
| 13 | **Cron with Routing + Orphan Cleanup** | useScheduledTasks.ts | Route cron fires to specific handlers; auto-disable if handler gone | Low-Med |
| 14 | **Session Summary** | sessionMemory.ts | Post-conversation summary to audit.db for continuity across sessions | Medium |

**Claude Code Plan File:** `_tools/TIER2_STRUCTURED_IMPROVEMENTS_PLAN.md`

---

### 🔵 TIER 3: Long-Term Architecture (Highest Impact, Highest Effort)

| # | Pattern | Source File | What To Do | Effort |
|---|---------|-------------|------------|--------|
| 15 | **Multi-Layer Context Management** | query.ts | 4-layer compaction for chat_v7.py: snip → compress → collapse → summarize | High |
| 16 | **Background Memory Extraction** | extractMemories.ts | Auto-extract observations from conversations (continuous learning) | Med-High |
| 17 | **State Machine Query Loop** | query.ts | Refactor intent routing into explicit state transitions with reasons | High |
| 18 | **Coordinator-Worker Parallelism** | coordinatorMode.ts | Formalized asyncio.gather for multi-stock analysis | Medium |
| 19 | **3-Level Memory Scoping** | agentMemory.ts | Scope observations: global/per-stock/per-device | Low |
| 20 | **Skill/Plugin System** | SkillTool.ts | Reusable analysis templates as .md files with metadata | High |
| 21 | **Memory Prefetch** | QueryEngine.ts | Start Brain lookup before intent parsing completes | Medium |

**Claude Code Plan File:** `_tools/TIER3_ARCHITECTURE_EVOLUTION_PLAN.md`

---

### Implementation Notes for Claude Code

**General Rules:**
- Each pattern = one git commit (atomic changes)
- Test after each pattern: `quick_check.py` → `smoke_test.py`
- Don't combine patterns — implement and verify one at a time
- Tier 1 patterns can be implemented independently (no dependencies)
- Tier 2 #9 must come before #10 (index before recall)
- Tier 3 patterns may require multiple PRs

**File Locations:**
- Most changes go in: `server.py`, `brain_core.py`, `tg_intent_router.py`
- New utility file needed: `utils/memory_age.py` (patterns #1, #2)
- New utility file needed: `utils/circuit_breaker.py` (pattern #3)
- Bridge changes: `bridge_client.py` (patterns #3, #12)
- Radar changes: `stock_radar.py` (patterns #6, #7, #12)

---

## Files Analyzed (16 source files, ~10,000 lines)

| File | Lines | Priority | Key Pattern |
|------|-------|----------|-------------|
| findRelevantMemories.ts | 141 | P1 | LLM-ranked memory recall |
| memoryScan.ts | 94 | P1 | Header-only memory index |
| memoryAge.ts | 53 | P1 | Staleness detection |
| QueryEngine.ts | 1,295 | P2 | Session lifecycle management |
| query.ts | 1,729 | P2 | 4-layer context compaction |
| tasks/types.ts | 46 | P3 | Typed task state model |
| coordinatorMode.ts | 369 | P3 | Multi-agent orchestration |
| runAgent.ts | 973 | P3 | Sub-agent execution + cleanup |
| agentMemory.ts | 177 | P3 | 3-level memory scoping |
| Tool.ts | 792 | P4 | Base tool interface |
| BashTool.tsx | 1,144 | P4 | Command classification + progress |
| SkillTool.ts | 1,108 | P4 | Skill/plugin system |
| useScheduledTasks.ts | 139 | P5 | Cron scheduler |
| extractMemories.ts | 615 | P5 | Auto memory extraction |
| autoCompact.ts | 351 | P5 | Circuit breaker + compaction |
| sessionMemory.ts | 495 | P5 | Session-level memory |
| AppStateStore.ts | 569 | P6 | Central state store |
| PluginInstallManager.ts | 184 | P6 | Background dependency mgmt |

**Total: ~10,274 lines analyzed → 21 actionable patterns → 3 tiers**
