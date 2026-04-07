# Master Plan v2: Claude Code Patterns → Master AI (Post-Audit)
# Date: 2026-04-02
# Status: Planning — Claude Code executes all Python
# Audit: Checked all 84 .py files for existing implementations

---

## Audit Results — What Already Exists

| Pattern | Status | Where | Gap |
|---------|--------|-------|-----|
| Feature Flags | PARTIAL | server.py:633-638 (5 env vars) | Static — needs restart to change |
| Circuit Breaker | EXISTS | bridge_client.py:62, gemini_scanner.py:118, server.py LLM | Per-service, no central view |
| Degraded Mode | EXISTS | degraded_mode.py, priority_engine.py:386 | Works but no proactive alerts |
| Context Compaction | PARTIAL | brain_core.py:381 (entity compact) | Only entities, not chat messages |
| Stale Cache Fallback | EXISTS | bridge_client.py:55 | Bridge only |
| Retry Logic | EXISTS | dropzone_watcher.py:234 | Deploy only |
| KAIROS Agent | MISSING | — | Biggest gap |
| Service Health Central | MISSING | — | Each service handles own errors |
| Hooks System | MISSING | — | No extensible hook points |
| Tool Registry | MISSING | — | No central tool discovery |
| Telegram Queue | MISSING | — | Messages lost if TG down |
| Proactive Alerts | MISSING | — | Logs errors but never alerts |

## Revised Priority (build on what exists, don't rebuild)

| # | Phase | What | Effort | Why |
|---|-------|------|--------|-----|
| 1 | Feature Flags v2 | Upgrade env→DB+API | 1.5h | Enables safe rollout of everything else |
| 2 | Service Health Hub | Unify existing circuit breakers | 2h | Central view, foundation for KAIROS |
| 3 | KAIROS Agent | New proactive monitor | 3h | Biggest gap — system can't self-alert |
| 4 | Telegram Queue | Offline message buffer | 1h | Quick win, prevents lost alerts |
| 5 | Chat Context Compaction | Extend brain_core pattern | 2h | Better Telegram conversations |
| 6 | Hooks + Tool Registry | Extensibility layer | 3h | Nice-to-have, future-proofing |
---

## Phase 1: Feature Flags v2 (Upgrade, Not Rebuild)
**Effort: ~1.5h | Changes: 1 new file + server.py modify**

### What exists now (server.py:633-638):
```python
FEATURE_CIRCUIT_BREAKERS = os.getenv("FEATURE_CIRCUIT_BREAKERS", "1") == "1"
FEATURE_TIMEOUTS = os.getenv("FEATURE_TIMEOUTS", "1") == "1"
FEATURE_SPEED_TEMPLATES = os.getenv("FEATURE_SPEED_TEMPLATES", "1") == "1"
FEATURE_SMART_ROUTER_V2 = os.getenv("FEATURE_SMART_ROUTER_V2", "1") == "1"
FEATURE_ENTITY_HEALTH = os.getenv("FEATURE_ENTITY_HEALTH", "1") == "1"
```
Problem: Need systemd restart to change any flag.

### What to build: `feature_flags.py`
- DB table in life.db (CREATE IF NOT EXISTS)
- In-memory cache with 60s refresh
- Thread-safe access
- Backward compatible: existing FEATURE_* env vars still work as override
- API endpoints for toggle without restart

### Migration strategy:
1. Create feature_flags.py with FeatureFlags class
2. Add table to life.db
3. Seed with existing 5 flags (all enabled)
4. Add to server.py startup: `ff = FeatureFlags("data/life.db")`
5. Keep env vars as override: `env_val or ff.is_enabled(name)`
6. Add endpoints: GET /api/flags, POST /api/flags/{name}/toggle
7. Future phases just call ff.is_enabled("kairos") — no restart needed

### DB Schema:
```sql
CREATE TABLE IF NOT EXISTS feature_flags (
  name TEXT PRIMARY KEY,
  enabled INTEGER DEFAULT 0,
  description TEXT DEFAULT '',
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO feature_flags (name, enabled, description) VALUES
  ('circuit_breakers', 1, 'Circuit breakers for external calls'),
  ('timeouts', 1, 'Request timeouts'),
  ('speed_templates', 1, 'Speed engine templates'),
  ('smart_router_v2', 1, 'Smart intent router v2'),
  ('entity_health', 1, 'Entity health monitoring'),
  ('kairos', 0, 'Background health agent (Phase 3)'),
  ('telegram_queue', 0, 'Offline message buffer (Phase 4)'),
  ('chat_compaction', 0, 'Chat context compression (Phase 5)');
```

### Validation:
```bash
quick_check.py
curl https://ai.salem-home.com/api/flags
curl -X POST https://ai.salem-home.com/api/flags/kairos/toggle
curl https://ai.salem-home.com/api/flags  # verify kairos=1
smoke_test.py
```
---

## Phase 2: Service Health Hub (Unify, Not Rebuild)
**Effort: ~2h | Changes: 1 new file + 3 modified**

### What exists now (scattered):
- bridge_client.py: circuit breaker (_failure_count, _is_circuit_open)
- gemini_scanner.py: CircuitBreaker class (failures, recovery_timeout)
- server.py: LLM circuit breaker (FEATURE_CIRCUIT_BREAKERS)
- degraded_mode.py: system degraded mode
- dashboard_api.py: references degraded_mode

### What to build: `service_health.py`
Purpose: Single source of truth for all service statuses.
Does NOT replace existing circuit breakers — reads FROM them.

```
Class: ServiceHealthHub (singleton)

Services to track:
  bridge: reads bridge_client circuit breaker state + /health ping
  home_assistant: GET /api/ with token
  telegram: bot.get_me()
  news_boursa: last news_items timestamp < 15min
  news_gemini: last gemini news timestamp < 1h
  daily_snapshot: max(updated_at) in stock_radar_daily < 24h
  llm_anthropic: reads server.py circuit breaker state
  llm_openai: reads server.py fallback state

Per service:
  name, is_available, last_checked, consecutive_failures, reason

Methods:
  check_all() -> dict
  get_summary() -> dict (for dashboard)
  is_up(name) -> bool

Integration points:
  - bridge_client.py: on failure → health.mark_down("bridge", reason)
  - bridge_client.py: on success → health.mark_up("bridge")
  - gemini_scanner.py: same pattern
  - server.py llm_call: same pattern
  - news_engine.py: same pattern

Endpoint:
  GET /api/service-health -> full status
  GET /health -> add services_summary field
```

### Dashboard (claude.ai builds):
- Add to system.html: service health grid
- Traffic lights: green (up), yellow (degraded), red (down)
- Last check timestamp + failure reason

### Validation:
```bash
quick_check.py
curl https://ai.salem-home.com/api/service-health
# Should show all services with status
smoke_test.py
```
---

## Phase 3: KAIROS Background Agent (New)
**Effort: ~3h | Changes: 1 new file + server.py + 2 new tables**
**Depends on: Phase 1 (flags) + Phase 2 (health hub)**

### What to build: `kairos.py`
The ONLY completely new component. Named after Claude Code's leaked feature.

```
Class: KairosAgent

Gated: ff.is_enabled("kairos")
Runs: asyncio task, checks every 5 min

Main loop:
  1. health_hub.check_all()
  2. For each DOWN service:
     - If first failure: log + wait
     - If 3+ consecutive: send Telegram alert (deduped)
     - If recovered: send recovery notification
  3. Special checks:
     - daily_snapshot stale > 2h during market (Sun-Thu 9:00-13:30):
       → auto-trigger refresh for top 20 stocks
     - Memory > 80%: gc.collect() + clear caches + alert
     - Disk > 85%: alert
  4. Log all actions to kairos_log table

Alert dedup:
  - Same alert_key → don't re-send within 1 hour
  - Daily summary at 11PM via Telegram

Telegram:
  /kairos → agent status + today's stats
  Alerts format:
    Warning:  "⚠️ Bridge غير متاح منذ 15 دقيقة"
    Recovery: "✅ Bridge رجع يشتغل (توقف 20 دقيقة)"
    Daily:    "📊 KAIROS: 3 مشاكل، 2 حُلت تلقائياً"
```

### New tables in life.db:
```sql
CREATE TABLE IF NOT EXISTS kairos_alerts (
  alert_key TEXT PRIMARY KEY,
  last_sent TEXT,
  count INTEGER DEFAULT 1,
  resolved INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS kairos_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
  action TEXT NOT NULL,
  service TEXT,
  result TEXT,
  detail TEXT
);
```

### Integration in server.py:
```
from kairos import KairosAgent
kairos = KairosAgent(health_hub, ff, tg_send)

@app.on_event("startup"):
  asyncio.create_task(kairos.start())

GET /api/kairos/status
GET /api/kairos/log?limit=50
```

### Validation:
```bash
quick_check.py
curl -X POST https://ai.salem-home.com/api/flags/kairos/toggle  # enable
# Wait 5 min
curl https://ai.salem-home.com/api/kairos/status
curl https://ai.salem-home.com/api/kairos/log
smoke_test.py
```
---

## Phase 4: Telegram Queue (Quick Win)
**Effort: ~1h | Changes: 1 new table + server.py tg_send modify**

### Problem:
When Telegram is down, alerts from KAIROS/signals/news are lost forever.

### Solution: Buffer in DB, flush on recovery.

```sql
CREATE TABLE IF NOT EXISTS telegram_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id INTEGER NOT NULL,
  message TEXT NOT NULL,
  parse_mode TEXT DEFAULT 'Markdown',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  sent INTEGER DEFAULT 0,
  sent_at TEXT
);
```

### Changes to tg_send in server.py:
```
Current: try send → if fail, log and move on
New:     try send → if fail, INSERT into telegram_queue
         On KAIROS health check: if telegram is_up and queue not empty:
           flush queue (oldest first, max 20 per cycle, 1s delay)
           mark sent=1, sent_at=now
         Cleanup: delete sent messages older than 24h
```

### Validation:
```bash
# Simulate: stop Telegram polling, trigger a signal
# Check telegram_queue table has pending messages
# Restart polling, verify messages flush
```

---

## Phase 5: Chat Context Compaction (Extend Existing)
**Effort: ~2h | Changes: 1 new file + chat_v7.py modify**

### What exists (brain_core.py:381+):
- compact_entities() — summarizes HA entities per room
- build_room_index() — compact room listing
- These are for SYSTEM PROMPT compaction, not chat history

### What to build: `context_compactor.py`
For CONVERSATION compaction in Telegram chats.

```
Class: ContextCompactor

Method: compact(messages: list, max_messages=20) -> list

Logic (adapted from Claude Code's 4-stage pipeline):
  Stage 1 - Collect: Take full message history
  Stage 2 - Compress: Messages older than last 6:
            Group in chunks of 5 → summarize each to ~2 sentences
            Use LLM (cheap model) or simple extractive summary
  Stage 3 - Rank: Score summaries by keyword overlap with last message
  Stage 4 - Inject: System prompt + top 3 summaries + last 6 messages

Cache: context_cache table (conversation_id, chunk_hash, summary)
Fallback: If compaction fails → just keep last 10 messages (truncate)
RPi-friendly: Only triggers when messages > 12
```

### Integration in chat_v7.py:
```
if ff.is_enabled("chat_compaction") and len(messages) > 12:
    messages = compactor.compact(messages)
```

---

## Phase 6: Hooks + Tool Registry (Future)
**Effort: ~3h | Low priority — nice-to-have**

### Hooks: `hooks.py`
Event system for before/after key operations.
Build only when we have a concrete use case beyond "it would be nice."

### Tool Registry: `tool_registry.py`
Central catalog of all capabilities as callable tools.
Build when we want tg_intent_router to dynamically discover tools.

**Recommendation: Skip Phase 6 until Phases 1-5 are stable.**

---

## Implementation Workflow

### For each phase:
1. User tells Claude Code: "Read _tools/CLAUDE_CODE_PATTERNS_MASTERPLAN.md, execute Phase N"
2. Claude Code: creates files, migrates DB, modifies server.py
3. Claude Code: quick_check.py → smoke_test.py → git commit → restart
4. claude.ai: builds dashboard HTML additions (system.html)
5. User: verifies via Telegram + dashboard

### Testing protocol:
```bash
python _tools/quick_check.py          # syntax
python -c "from feature_flags import FeatureFlags; print('OK')"  # import
python _tools/smoke_test.py           # endpoints
curl https://ai.salem-home.com/health # live check
git add -A && git commit -m "Phase N: description"
bash _tools/restart_master_ai.sh
```

---

## Files Summary

### New files (4-5):
| File | Phase | Purpose |
|------|-------|---------|
| feature_flags.py | 1 | Dynamic flags with DB + API |
| service_health.py | 2 | Central health monitoring |
| kairos.py | 3 | Background proactive agent |
| context_compactor.py | 5 | Chat history compression |

### Modified files:
| File | Phases | Changes |
|------|--------|---------|
| server.py | 1-4 | Imports + startup + endpoints + tg_send queue |
| bridge_client.py | 2 | Report to health hub on fail/success |
| gemini_scanner.py | 2 | Report to health hub |
| chat_v7.py | 5 | Context compaction integration |

### New tables (4):
| Table | Phase |
|-------|-------|
| feature_flags | 1 |
| kairos_alerts | 3 |
| kairos_log | 3 |
| telegram_queue | 4 |

### Dashboard changes (claude.ai):
| Page | Phase | Addition |
|------|-------|----------|
| system.html | 1 | Feature flag toggles |
| system.html | 2 | Service health traffic lights |
| system.html | 3 | KAIROS status + action log |

---

## Key Principles

1. **Build on what exists** — don't replace circuit breakers, unify them
2. **Feature flags gate everything** — Phase 1 enables safe rollout
3. **Minimal changes** — each phase touches 2-4 files max
4. **Backward compatible** — existing env vars still work
5. **RPi-friendly** — async, lightweight, configurable intervals
6. **Arabic first** — all Telegram messages in Kuwaiti Arabic

## Success Criteria

After Phases 1-5:
- Bridge down → Telegram alert within 5 min (KAIROS)
- Daily snapshot stale → auto-retry during market hours (KAIROS)
- Toggle feature → API call, no restart (Feature Flags v2)
- system.html → shows all services green/yellow/red (Health Hub)
- Long Telegram chat → stays coherent (Context Compaction)
- Telegram down → messages queued, sent on recovery (Queue)

---

## Phase 6: Hooks System + Tool Registry
**Effort: ~3h | Files: 2 new + 2-3 modified**
**Status: Ready to execute**

### Part A: Hooks System — `hooks.py`

Purpose: Event system for before/after key operations.
Gated: ff.is_enabled("hooks") — add this flag to feature_flags table.

```python
class HookRegistry:
    _hooks: dict[str, list[Callable]]  # event_name -> [handler_fn, ...]

    def on(event_name: str) -> decorator
    def trigger(event_name: str, data: dict) -> dict
    # trigger runs all handlers for event, returns merged result
    # if any handler returns {"skip": True}, operation is skipped
```

Hook points to add (minimal first set):
  1. after_signal — in signal_engine.py after signal generated
     Use: extra validation (reject low-confidence, log to audit)
  2. before_trade_alert — in server.py before Telegram alert for enter_now
     Use: check risk_engine limits, check market hours
  3. on_service_down — called by service_health.py when mark_down()
     Use: KAIROS remediation trigger (connects Phase 2→3→4)
  4. on_service_up — called by service_health.py when mark_up()
     Use: flush telegram_queue, log recovery

Implementation:
  - Handlers registered via decorator @hooks.on("event_name")
  - All handlers are async
  - Execution logged to hook_log table
  - If handler raises exception → log and continue (don't break main flow)
  - Timeout per handler: 5 seconds

```sql
CREATE TABLE IF NOT EXISTS hook_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
  hook_name TEXT NOT NULL,
  handler TEXT,
  duration_ms INTEGER,
  result TEXT,
  error TEXT
);
```

Initial handlers to register (in hooks.py itself):
  - after_signal: log signal to hook_log (audit trail)
  - on_service_down: log event
  - on_service_up: log event

### Part B: Tool Registry — `tool_registry.py`

Purpose: Central catalog of all callable capabilities.
Gated: ff.is_enabled("tool_registry") — add this flag.

```python
@dataclass
class Tool:
    name: str           # "get_stock_price"
    description: str    # Arabic description
    category: str       # "trading" | "home" | "system" | "news"
    func: Callable      # the actual async function
    requires: list[str] # service dependencies ["bridge"]

class ToolRegistry:
    _tools: dict[str, Tool]

    def register(name, description, category, requires=[]) -> decorator
    def execute(name, **kwargs) -> result
    # execute checks service_health before running
    def list_tools() -> list[dict]
    def get_tool(name) -> Tool
```

Tools to register (wrap existing functions, don't rewrite them):
  Trading:
    - get_stock_price: bridge_client.get_quote(symbol) → requires=["bridge"]
    - get_signals: dashboard_api signals endpoint → requires=["bridge"]
    - get_opportunities: golden_engine → requires=["bridge","daily_snapshot"]
    - get_portfolio: position_engine → requires=[]
    - get_journal: journal_engine → requires=[]

  Home:
    - ha_control: exec_ha service call → requires=["home_assistant"]
    - ha_status: get HA states → requires=["home_assistant"]

  System:
    - system_health: service_health.get_summary() → requires=[]
    - kairos_status: kairos status → requires=[]
    - get_flags: feature_flags.get_all() → requires=[]

  News:
    - get_news: news_engine → requires=[]

Endpoints:
  GET /api/tools → list all tools with name, description, category, available
  GET /api/tools/{name} → tool detail + whether its dependencies are up

Integration with tg_intent_router.py:
  - Don't change routing logic now
  - Just make tools discoverable via /api/tools
  - Future: router can use tool list for dynamic dispatch

### DB Migration:
```sql
-- hook_log table
CREATE TABLE IF NOT EXISTS hook_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
  hook_name TEXT NOT NULL,
  handler TEXT,
  duration_ms INTEGER,
  result TEXT,
  error TEXT
);

-- New feature flags
INSERT OR IGNORE INTO feature_flags (name, enabled, description) VALUES
  ('hooks', 0, 'Event hooks system (before/after operations)'),
  ('tool_registry', 0, 'Central tool discovery and execution');
```

### Validation:
```bash
quick_check.py
smoke_test.py

# Test hooks:
curl -X POST https://ai.salem-home.com/api/flags/hooks/toggle
# Wait for next signal cycle, check hook_log

# Test tool registry:
curl -X POST https://ai.salem-home.com/api/flags/tool_registry/toggle
curl https://ai.salem-home.com/api/tools
# Should list all registered tools with availability status

git add hooks.py tool_registry.py
git commit -m "Phase 6: Hooks system + Tool Registry"
restart_master_ai.sh
```
