# Master AI — Claude Development Context
> Auto-updated: 2026-03-02. Read this at start of every new conversation.
> Served via: GET /dev/context

## System
- Version: v5.4.0 (code v5.4.6), Port 9000, Tunnel: https://ai.salem-home.com
- Git: main, 37 ahead. Truth: GET /system/context (X-API-Key)
- DB: audit.db, 11 tables, WAL. Memory: 24 active. Autonomy: L3

## Files
- server.py(~4870) — endpoints, plugins, iterative_engine, TG bot
- brain_core.py(~590) — prompt builder, room aliases, entity map
- brain_personality.py — quick_response, response prompt
- brain_learning.py — auto-learn LLM extraction
- brain_analytics/observability/proactive.py
- tg_intent_router.py, tg_session_resolver.py(active), quick_query.py
- entity_map.json(25 rooms, 566 entities, cron 4AM)

## 9 Plugins
ha_get_state, ha_call_service, ssh_run, respond_text, http_request, memory_store, win_diagnostics, win_powershell, win_winget_install

## Features Built
1. Wildcard matching — fnmatch + comma-separated patterns
2. Room aliases — _ROOM_ALIASES + word-level matching
3. Room index inline IDs — climate/cover in Opus prompt
4. Conversation context — short_term deque(20), last 3 in context
5. Response synthesis — LLM fallback when empty response
6. _action leak fix — _reserved set in ha_call_service
7. Auto-learning — BRAIN_LEARN_HOOK after /ask
8. Speed Engine — quick_classify/execute
9. Safe serialization — /system/context

## Rules
1. Read /system/context BEFORE modifying server.py
2. docker kill BEFORE lovelace edits
3. Check HA API for entity IDs
4. Git deploy only
5. API keys from ~/.master_ai_key via MCP
6. Minimal backward-compatible changes
7. py_compile BEFORE restart

## Deploy Pattern
python3 -m py_compile server.py && sudo systemctl restart master-ai
