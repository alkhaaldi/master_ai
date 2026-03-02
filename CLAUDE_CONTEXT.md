# Master AI — Claude Development Context
> Auto-updated: 2026-03-03. Read this at start of every new conversation.
> Served via: GET /dev/context

## System
- Version: v5.4.0 (code v5.4.6+life+router), Port 9000, Tunnel: https://ai.salem-home.com
- Git: main, commit b3c0307. Truth: GET /system/context (X-API-Key)
- DB: audit.db, 11 tables, WAL. Memory: 24 active. Autonomy: L3
- LLM: Claude Sonnet 4 (primary), GPT-4o-mini (fallback)

## Files
- server.py(~5145) - endpoints, plugins, iterative_engine, TG bot, life+smart routers
- smart_router.py(99) - classify: greeting/chat/action/unknown
- tg_morning_report.py(198) - daily report 5:30AM (shift+weather+HA+stocks)
- tg_intent_router.py - device+room command matching
- tg_session.py + tg_session_resolver.py - followup context
- tg_alerts/reminders/news/tasks/stocks/home/ops.py - TG modules
- life_router/stocks/expenses/health/work.py - life domain modules
- brain_core/personality/learning/analytics/observability/proactive.py
- entity_map.json(25 rooms, 566 entities)

## TG Message Flow
1. /commands (39 incl /morning /help /stats /remind /stocks /shift)
2. Intent Router (device+room: shghl nwr almishh)
3. Session Followup (context-aware)
4. Life Router (stocks/expenses/health/work - no LLM)
5. SmartRouter (greeting=template 0 API / chat=Sonnet / action=iterative / unknown=iterative)
6. Iterative Engine (Sonnet LLM with 9 plugins)

## Modules (16/16 active)
intent_router, life_router, smart_router, brain, morning_report,
alerts, reminders, news, discovery, session, home, ops,
stocks, expenses, health, work

## Monitoring
- GET /tg/stats - router stats + module health JSON
- GET /health - system status
