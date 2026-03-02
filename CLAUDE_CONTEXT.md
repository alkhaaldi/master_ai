# Master AI — Claude Context
# Updated: 2026-03-03T02:45 (Night session — 17 commits)
# Git: 85bf91c (main)

## System
- Version: v5.4.0 (code v5.4.6)
- server.py: ~5,400 lines
- Port: 9000 | RPi5 | FastAPI + systemd
- Modules: 16/16 all active
- Plugins: 9 (ha_get_state, ha_call_service, ssh_run, respond_text, http_request, memory_store, win_diagnostics, win_powershell, win_winget_install)
- DB: audit.db (WAL mode, 11 tables)
- Autonomy: Level 3 (low only), Policy: auto≤30, approval≤60, block≥61
- Active .py files: 35 (5 deprecated moved to _deprecated/)

## Key Files
| File | Lines | Purpose |
|------|-------|---------|
| server.py | ~5400 | Main FastAPI server, TG polling, all commands |
| brain_core.py | ~590 | LLM prompt builder, room aliases, entity map |
| smart_router.py | ~105 | SmartRouter v2.2 — greeting/chat/action/unknown |
| quick_query.py | ~200 | Fast HA/shift/locks/media WITHOUT LLM (v2.1) |
| tg_intent_router.py | ~1390 | Device command NLU |
| brain.py | ~160 | Facade: re-exports all brain_* modules |
| life_work.py | — | Shift schedule (AABBCCDD, epoch 2024-01-04) |
| tg_alerts.py | — | HA monitoring (offline/cover/AC every 5min) |
| tg_morning_report.py | — | Daily 5:30 AM morning report |
| entity_map.json | — | 25 rooms, 566 entities |

## Message Flow (TG)
1. /commands → direct handler (zero LLM)
2. Intent router → device NLU (zero LLM)
3. Session followup → context-aware actions
4. Life router → stocks/expenses/work/health
5. **Quick Query v2.1** → home/room/shift/ac/lights/locks/media (zero LLM)
6. SmartRouter v2.2 → greeting(template) / chat(LLM) / action(planner)

## Quick Query v2.1 Patterns (zero LLM)
- "وضع البيت" → lights/AC/covers count
- "كم مكيف/نور" → AC/lights list
- "شفتي/دوامي" → shift + times (today/tomorrow)
- "وضع الديوانية/المطبخ/..." → room-specific status
- "أقفال/باب" → lock status
- "سماعات/موسيقى" → media players status
- Room map: 10 rooms (الديوانية, المعيشة, المطبخ, الماستر, غرفة ماما, غرفة 3, غرفة 5, الاستقبال, الصالة)

## TG Commands
/status /help /home(inline keyboard) /diag /stats /summary /errors
/lights /temp /rooms /scenes /cam /find
/shift /week /morning /stocks /price /tasks /remind /reminders /expense /expenses /health
/brain /log /crash /clearlog /backup /restart /approvals

## Background Loops (11 schedulers)
| Loop | Interval | Purpose |
|------|----------|---------|
| telegram_polling | continuous | TG message polling |
| morning_report | daily 5:30 AM | Morning briefing |
| **nightly_summary** | daily 11 PM | Auto daily summary + stats reset + tomorrow shift |
| shift_alert_loop | 15 min check | Pre-shift (1h before) + tomorrow change alert |
| entity_health_check | 6 hours | Dead/new entity detection (file-backed, no spam) |
| tg_alert_loop | 5 min | HA monitoring (offline/cover/AC) |
| stats_save_loop | 30 min | Router stats persistence |
| reminder_loop | continuous | User reminders |
| stock_alert_loop | — | Stock price alerts |
| news_scheduler | — | Scheduled news |
| backup_loop | — | Auto backup |

## Infrastructure
- RotatingFileHandler: 2MB max × 3 backups
- Stats Persistence: router_stats.json (save 30min + atexit)
- Entity Health: notified_entities.json (send once only)
- Shift Alerts: pre-shift reminder + tomorrow notification
- Nightly Summary: 11 PM auto report + daily counter reset
- Smart Greetings: time-of-day + shift info (zero LLM)

## Deprecated Files (in _deprecated/)
brain_backup.py, telegram_bot.py, ha_discovery.py, ruijie_integration.py, tg_ask_router.py

## Deployment
- Git deploy only: commit → push → ssh update.sh
- Tunnel: https://ai.salem-home.com (Cloudflare)
- /dev/context → CLAUDE_CONTEXT.md (no API key needed)
- /system/context → full system state (needs API key)
- /ssh/run → POST with X-API-Key + {cmd}
- /deploy → POST with file_path + content
- API Key: ~/.master_ai_key | HA Token: ~/.ha_token

## Next Steps
- LLM response caching for repeated questions
- TG inline keyboard for room control
- Proactive weather/energy alerts
- More quick_query patterns (energy usage, sensor data)
