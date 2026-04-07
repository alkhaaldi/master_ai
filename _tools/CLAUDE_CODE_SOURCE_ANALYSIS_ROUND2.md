# Claude Code Source Analysis — Round 2
# Date: 2026-04-03
# Analyst: Claude Code (Opus 4.6)
# Purpose: Extract architectural patterns from 7 new service areas for Master AI

---

## Table of Contents
1. [autoDream — Background Memory Consolidation](#1-autodream)
2. [PromptSuggestion — Predictive Input + Speculation](#2-promptsuggestion)
3. [toolUseSummary — LLM-Powered Action Summaries](#3-toolusesummary)
4. [AgentSummary — Live Sub-Agent Progress](#4-agentsummary)
5. [cronScheduler — Production Cron Engine](#5-cronscheduler)
6. [tips — Context-Aware Tip System](#6-tips)
7. [todo — Structured Task Types](#7-todo)
8. [Cross-Cutting Patterns](#8-cross-cutting-patterns)
9. [Master AI Implementation Roadmap](#9-implementation-roadmap)

---

## 1. autoDream — Background Memory Consolidation

### Files: `autoDream.ts`, `config.ts`, `consolidationPrompt.ts`, `consolidationLock.ts`

### How It Works

autoDream is a **background memory defragmentation system** that runs while the user is idle. It:

1. **Gate checks (cheapest first):**
   - Feature flag check (isAutoDreamEnabled via GrowthBook + user setting override)
   - Time gate: hours since last consolidation >= minHours (default: 24h)
   - Scan throttle: don't re-scan sessions more than once per 10 minutes
   - Session gate: at least N sessions (default: 5) modified since last consolidation
   - Lock gate: no other process already consolidating

2. **Lock mechanism** uses a single file whose **mtime IS the timestamp**:
   - PID written as body for holder identification
   - Stale detection: 60min timeout + dead PID check via `isProcessRunning()`
   - Race-condition handling: write PID → re-read → verify it's still ours
   - Rollback on failure: rewind mtime to pre-acquire value

3. **Runs as forked agent** (`runForkedAgent`) with:
   - Read-only bash restrictions (ls, find, grep, cat, stat, wc, head, tail only)
   - Memory write permissions (Edit/Write to memory dir)
   - skipTranscript: true (doesn't pollute user's conversation)
   - Abort controller for user cancellation

4. **Consolidation prompt** is a 4-phase plan:
   - Phase 1: Orient (ls memory dir, read index, skim existing topics)
   - Phase 2: Gather signal (daily logs, stale memories, targeted transcript grep)
   - Phase 3: Consolidate (merge/update/create memory files)
   - Phase 4: Prune index (keep MEMORY.md under limit)

5. **Progress tracking** via DreamTask state machine:
   - Watches forked agent messages, extracts text + tool counts + file paths
   - Reports "Improved N memories" to user after completion
   - Kill support: user can abort from background tasks dialog

### Key Design Decisions
- **Cheapest gates first**: feature flag → stat → scan → lock (avoids expensive ops)
- **mtime-as-timestamp**: zero-overhead state persistence, no DB needed
- **Scan throttle**: prevents re-scanning sessions every turn when time-gate passes but session-gate doesn't
- **Excludes current session** from count (its mtime is always recent)
- **KAIROS mode bypass**: disk-skill dream uses different path
- **Config from GrowthBook** with defensive per-field validation

### 🎯 Master AI Implementation Notes

```
Pattern: Background Memory Consolidation ("Dream Mode")
Where: New file dream_consolidator.py
How:
  - Run as background thread/process every 24h (or after 5+ TG conversations)
  - Gate order: time_since_last → session_count → lock
  - Lock: simple file with PID, mtime = last consolidation time
  - Use Gemini Flash (cheap) to review recent audit.db entries + memory files
  - Prompt: "Review memories, merge duplicates, update stale facts, prune index"
  - Read-only access to code, write access only to memory dir
  - Track progress, allow cancellation via TG command
Effort: HIGH
Impact: CRITICAL — memories currently grow without bounds, duplicates accumulate
Priority: P1 — this is the biggest quality-of-life improvement possible
```

```
Pattern: Mtime-as-Timestamp Lock
Where: dream_consolidator.py
How:
  - Lock file: ~/.master_ai/memory/.consolidate-lock
  - Body: PID of holder
  - mtime: last successful consolidation timestamp
  - Stale after 60min even if PID alive (PID reuse guard)
  - On failure: rollback mtime to pre-acquire value
  - Zero external dependencies, works on any filesystem
Effort: LOW
Impact: MEDIUM — prevents concurrent consolidation
```

```
Pattern: Cheapest-Gate-First Evaluation
Where: All background tasks (dream, news refresh, signal scan)
How:
  - Order checks: in-memory flag → single stat() → list scan → lock acquire
  - Never do expensive IO if a cheap check already says "skip"
  - Apply to: news_engine refresh, signal_review scan, trading brain refresh
Effort: LOW
Impact: MEDIUM — reduces unnecessary CPU/IO on Pi
```

---

## 2. PromptSuggestion + Speculation — Predictive Execution

### Files: `promptSuggestion.ts`, `speculation.ts`

### How PromptSuggestion Works

Predicts what the user will type next and shows it as a suggestion:

1. **Guard chain** (lots of suppression reasons):
   - Disabled in non-interactive/SDK/swarm-teammate mode
   - Skips first 2 turns (not enough context)
   - Skips if last response was an API error
   - Skips if prompt cache is cold (>10K uncached tokens = expensive fork)
   - Skips if pending permissions/elicitation/plan-mode/rate-limit

2. **Generation**: Forks the entire conversation + a suggestion prompt to the model
   - Prompt: "Predict what the USER would type next (2-12 words, match their style)"
   - **Cache piggyback**: uses identical cache-key params as parent request (critical!)
   - Tools denied via callback (NOT by passing tools:[] which busts cache)
   - skipCacheWrite: true (don't create new cache entries for this side-query)

3. **Filter chain** (15+ filters!):
   - "done", meta-text ("nothing found", "silence"), wrapped in parens/brackets
   - Error messages, prefixed labels ("Suggestion: ...")
   - Too few words (unless allowed single words: yes/no/push/commit/continue/etc)
   - Too many words (>12), too long (>100 chars), multiple sentences
   - Evaluative ("thanks", "looks good"), Claude-voice ("Let me...", "I'll...")

4. **Outcome tracking**: accepted vs ignored, time-to-accept, similarity ratio

### How Speculation Works (The Real Gem)

When a suggestion is shown, speculation **pre-executes it in a sandbox**:

1. **Overlay filesystem**: creates temp dir, copy-on-write for file edits
   - Writes go to overlay path, reads check overlay first then fall back to main
   - Path rewriting via canUseTool callback (not filesystem-level)

2. **Tool permission boundaries**:
   - Read-only tools (Read, Glob, Grep): allowed, path-rewritten if in overlay
   - Write tools (Edit, Write, NotebookEdit): allowed only if user is in acceptEdits/bypass mode
   - Bash: allowed only if read-only (ls, grep, etc.)
   - Everything else: denied → sets boundary → aborts speculation

3. **Boundary tracking**: records where speculation stopped
   - `complete`: ran to natural end
   - `edit`: stopped at file edit needing permission
   - `bash`: stopped at non-read-only bash
   - `denied_tool`: stopped at unsupported tool

4. **Accept flow**:
   - Copy overlay files to real filesystem
   - Inject speculated messages into conversation (filtered: no thinking blocks, no failed tool calls)
   - If complete: no query needed (instant response!)
   - If incomplete: follow-up query continues from where speculation stopped
   - Track time saved per accept + session total

5. **Pipelined suggestions**: while speculation runs, generates the NEXT suggestion for the completed state → chains speculation recursively

### Key Design Decisions
- **Cache-key identity is sacred**: changing ANY param (effort, maxOutputTokens, tools:[]) busts the prompt cache → 45x cache write spike. Only safe overrides: abortController, skipTranscript, skipCacheWrite, canUseTool
- **Copy-on-write overlay**: simple, no FUSE, no filesystem hooks
- **Fail open**: errors in speculation → normal query flow, user never notices
- **Message injection filtering**: strips thinking blocks, failed tool calls, interrupt messages

### 🎯 Master AI Implementation Notes

```
Pattern: Predictive Intent Suggestion
Where: tg_stocks.py (after each response)
How:
  - After responding to user, use Gemini Flash to predict next query
  - Show as inline keyboard button: "Did you mean: [suggestion]?"
  - Filter: skip evaluative, skip Claude-voice, 2-12 words
  - Track acceptance rate in audit.db
  - Use ONLY when conversation has 2+ turns (need context)
Example: User asks "analyze AAPL" → suggest "compare with MSFT" or "check resistance levels"
Effort: MEDIUM
Impact: HIGH — reduces friction, feels magical
```

```
Pattern: Speculative Pre-execution
Where: New speculative_executor.py
How:
  - When user gets a suggestion, pre-compute the response in background
  - For trading: pre-fetch stock data, pre-run analysis, pre-generate charts
  - Store result in Redis/dict cache keyed by suggestion text
  - If user accepts suggestion → serve cached response instantly
  - If user types something else → discard cache
  - Time-box: max 30 seconds of pre-computation
Example: Suggest "check AAPL support levels" → pre-fetch AAPL data + compute S/R
Effort: HIGH
Impact: HIGH — perceived latency drops to near-zero for predicted queries
```

```
Pattern: Suggestion Filter Chain
Where: tg_stocks.py or new suggestion_filter.py
How:
  - Apply 10+ filters in sequence (cheapest first):
    1. Too short (<2 words, unless "yes"/"no")
    2. Too long (>12 words)
    3. Evaluative ("thanks", "looks good")
    4. Bot-voice ("Let me...", "I'll analyze...")
    5. Meta-text ("no suggestion", "nothing found")
    6. Multiple sentences
  - Each filter logs why it suppressed → tune over time
Effort: LOW
Impact: MEDIUM — prevents bad suggestions from eroding trust
```

---

## 3. toolUseSummary — LLM-Powered Action Summaries

### File: `toolUseSummaryGenerator.ts`

### How It Works

Generates human-readable labels for completed tool batches (for SDK mobile UI):

1. **Input**: array of {name, input, output} for completed tools + optional last assistant text
2. **Truncation**: JSON-serialize each tool's input/output, truncate to 300 chars
3. **LLM call**: Haiku with system prompt "write a short summary label, ~30 chars, past tense, git-commit-subject style"
4. **Context injection**: prepends last assistant text (trimmed to 200 chars) as intent hint
5. **Non-critical**: errors are logged but never propagated (graceful degradation)

### Key Design Decisions
- **Haiku for cost**: summaries are UI decoration, don't need Sonnet/Opus
- **300-char truncation**: keeps prompt small, Haiku stays fast
- **Past tense, distinctive noun**: "Fixed NPE in UserService" > "Made changes to code"
- **Intent context**: last assistant message helps disambiguate (e.g., "Ran tests" vs "Ran failing tests")

### 🎯 Master AI Implementation Notes

```
Pattern: LLM-Summarized Action Labels
Where: task_manager.py or audit logging
How:
  - After each tool execution batch, use Gemini Flash to generate 1-line summary
  - Format: past tense verb + distinctive noun, <40 chars
  - Use for: TG status messages, audit.db entries, daily summary
  - Include context: "User asked about AAPL" + "Fetched price data, computed EMA"
  - Non-critical: wrap in try/except, return "Processing..." on failure
  - Cache: if same tool combo seen before, reuse previous summary
Example: tools=[fetch_price(AAPL), compute_ema(21)] → "Computed AAPL 21-EMA"
Effort: LOW
Impact: MEDIUM — better UX for TG progress messages
```

---

## 4. AgentSummary — Live Sub-Agent Progress

### File: `agentSummary.ts`

### How It Works

Periodically summarizes what a sub-agent is doing (for coordinator UI):

1. **Timer-based**: fires every 30 seconds via setInterval
2. **Reads live transcript**: gets current messages from agent's session storage
3. **Forks conversation**: sends summary prompt to the agent's own conversation context
4. **Cache sharing**: uses same CacheSafeParams as parent (critical for cache hits)
5. **Prompt**: "Describe your most recent action in 3-5 words, present tense (-ing), name the file/function"
6. **Anti-repeat**: passes previous summary with "say something NEW"
7. **Non-overlapping**: schedules NEXT timer only after current summary completes

### Key Design Decisions
- **30s interval**: balances freshness vs cost
- **Completion-based scheduling**: `finally { scheduleNext() }` prevents overlap
- **Drops forkContextMessages from closure**: prevents memory leak (rebuilds from transcript each tick)
- **DO NOT set maxOutputTokens**: would bust cache by changing thinking config
- **Tools denied but kept in request**: removing tools changes cache key

### 🎯 Master AI Implementation Notes

```
Pattern: Periodic Background Task Summarization
Where: parallel_coordinator.py or task_manager.py
How:
  - When running long tasks (news refresh, signal scan, brain analysis):
    - Every 30s, generate 3-5 word status label
    - Send as TG "typing..." indicator or edit previous status message
    - Use Gemini Flash with the task's recent actions as context
  - Anti-repeat: pass previous status, ask for something NEW
  - Schedule next AFTER completion (prevent overlap)
  - Stop timer when task completes
Example: "Scanning AAPL signals" → "Computing RSI divergence" → "Writing analysis"
Effort: MEDIUM
Impact: MEDIUM — user knows system is alive during long operations
```

---

## 5. cronScheduler — Production Cron Engine

### File: `cronScheduler.ts`

### How It Works

Full production cron scheduler with file watching, locking, and jitter:

1. **Task storage**: `.claude/scheduled_tasks.json` (file-backed) + session-only tasks (in-memory)
2. **Startup sequence**:
   - Poll `getScheduledTasksEnabled()` until true (lazy init)
   - Acquire per-project scheduler lock (only one Claude session fires tasks)
   - Load tasks from JSON + watch file with chokidar
   - Start 1-second check timer

3. **Check loop** (every 1s):
   - For each task: compute next fire time with jitter, fire if past due
   - Recurring: reschedule from NOW (not from scheduled time) to prevent catch-up storms
   - One-shot: delete after firing
   - Aged-out: recurring tasks auto-expire after 7 days (configurable)

4. **Jitter system**:
   - `jitteredNextCronRunMs()`: adds deterministic jitter to prevent fleet-wide :00 spikes
   - Jitter config from GrowthBook (live-tunable without restart)
   - One-shot tasks get separate jitter calculation

5. **Lock mechanism** (`cronTasksLock.ts`):
   - Per-project lock file with PID + session ID
   - Non-owning sessions probe every 5s to take over if owner dies
   - Lock released on stop()

6. **Missed task detection** (on startup):
   - Finds one-shot tasks whose fire time passed while Claude was offline
   - Wraps them in code fences to prevent prompt injection (!!)
   - Asks user for confirmation before executing

7. **File stability**: chokidar `awaitWriteFinish` with 300ms threshold

### Key Design Decisions
- **1s check interval** with `unref()`: doesn't keep process alive
- **Reschedule from NOW**: prevents rapid catch-up if session was blocked
- **Deterministic jitter**: keyed on task ID, reproducible across restarts
- **Session tasks vs file tasks**: session tasks die with process, no file events needed
- **Anti-injection**: missed task prompts wrapped in code fences with dynamic fence length
- **Lock probe interval**: 5s (coarse, only matters when owner crashed)
- **inFlight set**: prevents double-fire during async remove + chokidar reload

### 🎯 Master AI Implementation Notes

```
Pattern: Robust Cron Scheduler with Jitter
Where: Replace current cron_tasks.py or enhance it
How:
  - File-backed tasks in ~/.master_ai/scheduled_tasks.json
  - 1-second check loop (lightweight: just timestamp comparisons)
  - Jitter: hash(task_id) % jitter_window to spread :00 spikes
  - Reschedule recurring from NOW (not scheduled time) to prevent catch-up
  - Auto-expire recurring tasks after 7 days
  - Lock: only one master_ai process fires tasks (PID-based lock)
  - Missed tasks: on startup, detect and ask user before executing
  - File watching: watchdog or inotify for live task updates
Effort: HIGH
Impact: HIGH — replaces fragile cron system with production-grade one
```

```
Pattern: Anti-Injection for Scheduled Tasks
Where: cron scheduler missed-task handler
How:
  - NEVER execute missed tasks automatically
  - Wrap task prompt in code fences (dynamic length to prevent fence-breaking)
  - Show to user: "This task was missed. Run it now?"
  - Only execute after explicit confirmation
  - Delete from JSON BEFORE showing to user (prevent re-fire on reload)
Effort: LOW
Impact: CRITICAL for security — scheduled tasks are a prompt injection vector
```

```
Pattern: Session-Only vs Persistent Tasks
Where: task_manager.py
How:
  - Two task types:
    1. Persistent: saved to JSON, survive restarts, need lock coordination
    2. Session-only: in-memory dict, die with process, no lock needed
  - Use session-only for: "remind me in 5 minutes", temp polling
  - Use persistent for: daily summary, weekly report, recurring scans
  - Session tasks checked from memory every tick (no file IO)
Effort: MEDIUM
Impact: MEDIUM — cleaner task lifecycle management
```

---

## 6. tips — Context-Aware Tip System

### Files: `tipScheduler.ts`, `tipRegistry.ts`, `tipHistory.ts`

### How It Works

Shows contextual tips during loading spinners:

1. **Tip registry**: 40+ tips, each with:
   - `id`: unique identifier
   - `content`: async function returning formatted string (can use chalk colors, context)
   - `cooldownSessions`: minimum sessions between re-shows
   - `isRelevant`: async predicate checking current context

2. **Selection**: "longest time since shown" strategy
   - Filter tips by relevance (async, parallel `Promise.all`)
   - Filter by cooldown (sessions since last shown >= cooldownSessions)
   - Sort by sessions-since-last-shown descending
   - Pick the one not shown for longest

3. **History**: stored in globalConfig.tipsHistory as `{tipId: lastShownAtSessionNumber}`
   - Uses session count (numStartups) as monotonic clock
   - `getSessionsSinceLastShown()`: Infinity if never shown (always eligible)

4. **Relevance examples**:
   - "Use plan mode": only if haven't used plan mode in 7+ days
   - "Git worktrees": only if single worktree and 50+ startups
   - "Color sessions": only if 2+ concurrent sessions and no color set
   - "Shift+Enter": only if terminal setup completed
   - Plugin tips: only if relevant file types in readFileState cache

5. **Customization**:
   - `spinnerTipsOverride` in settings: custom tip content
   - `excludeDefault`: show only custom tips
   - Internal-only tips for Anthropic employees

### Key Design Decisions
- **Async relevance checks**: run in parallel, some need filesystem/process checks
- **Session-count clock**: simpler than timestamps, monotonically increasing
- **Longest-unseen selection**: ensures variety, no tip dominates
- **Cooldown per tip**: frequent tips (3 sessions) vs rare tips (30 sessions)
- **Context-aware content**: tips can read theme, terminal type, installed tools

### 🎯 Master AI Implementation Notes

```
Pattern: Context-Aware Tip System
Where: New tips_engine.py, wire into TG responses
How:
  - Registry of 20+ tips, each with:
    - id, content_fn, cooldown_interactions, is_relevant_fn
  - Show tips during: long operations, daily briefing footer, idle periods
  - Examples:
    - "Set stop-loss alerts with /alert AAPL < 150" (if no alerts set)
    - "Use /compare AAPL MSFT for side-by-side analysis" (after single stock query)
    - "Golden opportunities scan runs daily at 9am" (if never used scanner)
  - Selection: pick tip not shown for longest time
  - History: store in audit.db {tip_id, last_shown_at, show_count}
  - Cooldown: per-tip, measured in interactions (not time)
  - Relevance: check current context (portfolio, active alerts, recent queries)
Effort: MEDIUM
Impact: MEDIUM — teaches user features organically, increases engagement
```

```
Pattern: Session-Count Monotonic Clock
Where: tips_engine.py, audit.db
How:
  - Track "interaction count" as monotonic counter (simpler than timestamps)
  - getInteractionsSinceLastShown(tip_id) = current_count - last_shown_count
  - Infinity if never shown (always eligible)
  - Survives time changes, DST, etc.
Effort: LOW
Impact: LOW — just a cleaner way to track recency
```

---

## 7. todo — Structured Task Types

### File: `types.ts`

### How It Works

Minimal but well-designed task schema using Zod:

```typescript
TodoItem = {
  content: string     // imperative form: "Run tests"
  status: 'pending' | 'in_progress' | 'completed'
  activeForm: string  // present continuous: "Running tests"
}
TodoList = TodoItem[]
```

### Key Design Decisions
- **Dual-form content**: `content` (imperative) for display, `activeForm` (gerund) for progress indicator
- **Zod validation**: runtime type safety with `.min(1)` constraints
- **Lazy schema**: `lazySchema()` wrapper for circular reference handling
- **Three states only**: no "blocked", "cancelled", "failed" — keep it simple

### 🎯 Master AI Implementation Notes

```
Pattern: Dual-Form Task Descriptions
Where: task_manager.py
How:
  - Each task has two descriptions:
    1. content: "Fetch AAPL price data" (for task list display)
    2. activeForm: "Fetching AAPL price data" (for progress/status messages)
  - Generate activeForm automatically: "Run X" → "Running X", "Check X" → "Checking X"
  - Use activeForm in TG typing indicators and status messages
Effort: LOW
Impact: LOW — small UX polish
```

---

## 8. Cross-Cutting Patterns

### Pattern: Forked Agent Architecture
Used by: autoDream, PromptSuggestion, Speculation, AgentSummary

The `runForkedAgent()` is the backbone of all background processing:
- Forks the current conversation context
- Shares prompt cache via identical cache-key params
- Tool permissions controlled via `canUseTool` callback
- AbortController for cancellation
- skipTranscript: true to avoid polluting user's history
- Returns messages + usage stats

```
Master AI Equivalent: forked_query.py
  - Function: run_side_query(prompt, context, model="flash", tools_allowed=[], timeout=30)
  - Shares conversation context (recent messages)
  - Uses cheap model (Gemini Flash) for side queries
  - Returns structured result
  - Timeout + cancellation support
  - Usage tracking for cost monitoring
```

### Pattern: Cache-Key Discipline
The single most important performance insight from this codebase:
- **Never change API params between parent and fork** — even seemingly harmless changes bust the prompt cache
- PR #18143 tried setting effort:'low' on fork → 45x cache write spike (92.7% → 61% hit rate)
- Only safe overrides: client-side things (abortController, skipTranscript, canUseTool)
- Deny tools via callback, NEVER by passing empty tools array

```
Master AI Equivalent:
  - When making side queries to Gemini, reuse the same system prompt + tool definitions
  - Don't strip tools from side queries — just deny them in the response handler
  - Gemini's context caching has similar cache-key sensitivity
```

### Pattern: Graceful Degradation Everywhere
Every background system follows the same pattern:
- Wrap in try/catch
- Log error but don't propagate
- Return safe default (null, [], false)
- User never sees background failures

```
Master AI: Apply to ALL background tasks:
  - news_engine refresh failures → serve stale data
  - signal scan failures → skip scan, try next cycle
  - dream failures → rollback lock, try next cycle
  - tip failures → show no tip (not crash)
```

### Pattern: Anti-Double-Fire
Used by: cronScheduler, autoDream

Multiple mechanisms prevent the same task from firing twice:
1. **Lock file**: only one process owns the scheduler
2. **inFlight set**: tracks tasks currently being processed
3. **Scan throttle**: don't re-check too frequently
4. **mtime-as-state**: filesystem is the source of truth

---

## 9. Master AI Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
| # | Task | Source Pattern | Effort | Impact |
|---|------|---------------|--------|--------|
| 1 | `forked_query.py` — side-query infrastructure | runForkedAgent | HIGH | CRITICAL |
| 2 | `dream_consolidator.py` — memory defrag | autoDream | HIGH | CRITICAL |
| 3 | Mtime-based lock mechanism | consolidationLock | LOW | MEDIUM |

### Phase 2: Intelligence (Week 3-4)
| # | Task | Source Pattern | Effort | Impact |
|---|------|---------------|--------|--------|
| 4 | Predictive intent suggestions | PromptSuggestion | MEDIUM | HIGH |
| 5 | Suggestion filter chain | shouldFilterSuggestion | LOW | MEDIUM |
| 6 | Speculative pre-computation | Speculation (simplified) | HIGH | HIGH |

### Phase 3: Operations (Week 5-6)
| # | Task | Source Pattern | Effort | Impact |
|---|------|---------------|--------|--------|
| 7 | Production cron scheduler with jitter | cronScheduler | HIGH | HIGH |
| 8 | Anti-injection for scheduled tasks | buildMissedTaskNotification | LOW | CRITICAL |
| 9 | LLM-powered action summaries | toolUseSummary | LOW | MEDIUM |
| 10 | Live task progress labels | AgentSummary | MEDIUM | MEDIUM |

### Phase 4: Polish (Week 7-8)
| # | Task | Source Pattern | Effort | Impact |
|---|------|---------------|--------|--------|
| 11 | Context-aware tip system | tips/* | MEDIUM | MEDIUM |
| 12 | Dual-form task descriptions | todo/types | LOW | LOW |
| 13 | Cheapest-gate-first for all bg tasks | autoDream gate chain | LOW | MEDIUM |

---

## Appendix: File-by-File Summary

| File | Lines | Key Pattern | Complexity |
|------|-------|-------------|------------|
| `autoDream.ts` | ~230 | Background consolidation with gate chain + forked agent | HIGH |
| `config.ts` | ~20 | User setting override → GrowthBook fallback | LOW |
| `consolidationPrompt.ts` | ~60 | 4-phase consolidation prompt builder | LOW |
| `consolidationLock.ts` | ~120 | PID-based lock with mtime-as-timestamp | MEDIUM |
| `promptSuggestion.ts` | ~350 | Predictive suggestions with 15+ filter chain | HIGH |
| `speculation.ts` | ~990 | Copy-on-write speculative execution engine | VERY HIGH |
| `toolUseSummaryGenerator.ts` | ~90 | Haiku-powered action label generator | LOW |
| `agentSummary.ts` | ~140 | Timer-based periodic sub-agent summarization | MEDIUM |
| `cronScheduler.ts` | ~480 | Full production cron with jitter, locking, file watching | VERY HIGH |
| `tipScheduler.ts` | ~50 | Longest-unseen tip selection | LOW |
| `tipRegistry.ts` | ~400 | 40+ context-aware tips with async relevance | MEDIUM |
| `tipHistory.ts` | ~20 | Session-count based tip history | LOW |
| `todo/types.ts` | ~15 | Zod schema for task items | LOW |

**Total: ~2,965 lines analyzed across 13 files + 1 type file**
