# Master AI — Claude Development Context
> Auto-updated: 2026-03-02. Read this at start of every new conversation.
> Served via: GET /dev/context

## System
- Version: v5.4.0 (code v5.4.6+life), Port 9000, Tunnel: https://ai.salem-home.com
- Git: main, commit 9daf542. Truth: GET /system/context (X-API-Key)
- DB: audit.db, 11 tables, WAL. Memory: 24 active. Autonomy: L3

## Files
- server.py(~5018) — endpoints, plugins, iterative_engine, TG bot, life router
- brain_core.py(~590) — prompt builder, room aliases, entity map
- brain_personality.py — quick_response, response prompt
- brain_learning.py — auto-learn LLM extraction
- brain_analytics/observability/proactive.py
- tg_intent_router.py, tg_session_resolver.py(active)
- life_router.py — smart domain detection (stocks/expenses/health/work)
- life_stocks.py(565) — portfolio, trades, watchlist, live prices
- life_expenses.py(95) — expense tracking + categories
- life_health.py(135) — weight, exercise, sleep logging
- life_work.py(136) — shift schedule, OT, leave tracking
- entity_map.json(25 rooms, 566 entities, cron 4AM)

## 9 Plugins
ha_get_state, ha_call_service, ssh_run, respond_text, http_request, memory_store, win_diagnostics, win_powershell, win_winget_install

## TG Message Flow (priority order)
1. /commands -> tg_handle_command
2. route_intent -> direct HA commands (lights/AC/covers)
3. detect_followup -> session continuity
4. **life_router -> stocks/expenses/health/work (bypasses LLM)**
5. SmartRouter -> classify chat vs action
6. chat -> brain_core (Opus LLM)
7. action -> iterative planner (Opus LLM)

## Features Built
1. Wildcard matching — fnmatch + comma-separated patterns
2. Room aliases — brain_core word-level matching
3. Entity ID inline — climate/cover in room index
4. Conversation context — deque(20), last 3 in context
5. Response synthesis — LLM fallback for empty responses
6. Auto learning — LLM extraction after each interaction
7. Life modules — 4 domains routed before LLM (stocks/expenses/health/work)

## Remaining Orphans (safe to ignore)
- tg_ask_router.py — old classify_message, replaced by smart_router.py
- brain_backup.py — old brain.py snapshot, not a module
