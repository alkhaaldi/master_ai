# Master AI — Claude Context (auto-generated)
## System
- Version: v5.4.0 (code v5.4.6)
- server.py: ~5301 lines
- Port: 9000
- Git: 5cbdedf (main)
- Modules: 16/16 all active
- Plugins: 9

## Brain Modules
brain_core, brain_learning, brain_personality, brain_proactive, brain_observability, brain_multiuser, brain_analytics

## Key Files
- server.py (~5301) — main FastAPI server
- brain_core.py (~590) — LLM prompt builder, room aliases, entity map
- smart_router.py (~105) — SmartRouter v2.1 (greeting/chat/action/unknown)
- tg_intent_router.py — device command NLU
- tg_morning_report.py — daily morning report
- tasks_db.py — user tasks (user_tasks table in audit.db)
- entity_map.json — 25 rooms, 566 entities

## Features (this session)
- SmartRouter v2.1: greeting templates (0 API), life domain keywords, short Arabic=chat
- RotatingFileHandler: 2MB max x 3 backups
- Stats persistence: router_stats.json, save every 30min + atexit
- /summary: daily dashboard (msgs, LLM savings, HA status, errors)
- /diag enhanced: CPU/RAM/Temp + uptime + modules + log size
- /help updated: includes /stats + /summary
- user_tasks table (fixed collision with TaskManager tasks table)

## TG Commands
/status /stats /summary /diag /morning /help /lights /temp /rooms /scenes
/remind /reminders /news /stocks /price /tasks /shift /schedule /expense /expenses /health /brain
/errors /log /crash /clearlog /backup /restart /approvals /cam /find

## Schedulers
telegram_polling, morning_report(5:30AM), entity_health(6h), tg_alerts(5min), reminders, stock_alerts, news, backup, stats_save(30min)

## Message Flow
1. /commands → direct handler
2. Intent router → device NLU (شغل/طفي/مكيف)
3. Session followup → context-aware actions
4. Life router → stocks/expenses/work/health
5. SmartRouter → greeting(template) / chat(brain LLM) / action(planner) / unknown(LLM)
