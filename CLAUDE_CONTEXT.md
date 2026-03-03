# Master AI — Claude Context
# Updated: 2026-03-03T03:25 (Night+morning session — 28 commits)
# Git: ce7206a (main)

## System
- Version: v5.4.0 (code v5.4.7)
- server.py: ~5,500 lines
- Port: 9000 | RPi5 | FastAPI + systemd
- Modules: 16/16 all active
- Plugins: 9 (ha_get_state, ha_call_service, ssh_run, respond_text, http_request, memory_store, win_diagnostics, win_powershell, win_winget_install)
- DB: audit.db (WAL mode, 11 tables)
- Autonomy: Level 3 (low only)
- Active .py files: 35 (5 deprecated in _deprecated/)

## Key Files
| File | Lines | Purpose |
|------|-------|---------|
| server.py | ~5500 | Main server, TG polling, all commands |
| brain_core.py | ~590 | LLM prompt builder, room aliases, entity map |
| smart_router.py | ~105 | SmartRouter v2.2 classifier |
| quick_query.py | ~250 | Fast answers WITHOUT LLM (v2.2) |
| tg_intent_router.py | ~1390 | Device command NLU |
| brain.py | ~160 | Facade for brain_* modules |
| entity_map.json | - | 25 rooms, 566 entities |

## Quick Query v2.2 Patterns (12 patterns, zero LLM)
1. "وضع البيت" → lights/AC/covers summary
2. "كم مكيف" → AC list with temps
3. "كم ضوء" → lights count
4. "شفتي/دوامي" → shift + times (today/tomorrow)
5. "وضع الديوانية/..." → room status (10 rooms)
6. "أقفال/باب" → lock status
7. "سماعات/ميديا" → media players
8. "طقس/جو/حرارة" → weather from Open-Meteo
9. "ستائر/شتر" → covers status
10. "كم جهاز شغال" → active devices by domain

## TG /home Menu (2 pages)
Page 1 - Smart Home: أضواء|مكيفات|ستائر|مشاهد|أقفال|سماعات|كاميرات|طقس|طفي كل شي
Page 2 - Tools: شفت|أسبوع|أسهم|ملخص|نظام|عقل|مهام|مساعدة

## Interactive Commands (with inline buttons)
/lights → list + "all off" button
/covers → list + "open all" / "close all" buttons
/scenes → scene buttons (2 pages)
/rooms → floor groups + room buttons + device toggle
/home → 2-page main menu
/help → categorized + shortcuts

## Background Loops (12 schedulers)
| Loop | Interval | Purpose |
|------|----------|---------|
| telegram_polling | continuous | TG message polling |
| morning_report | daily 5:30 AM | Morning briefing |
| nightly_summary | daily 11 PM | Auto summary + stats reset |
| shift_alert_loop | 15 min | Pre-shift + tomorrow alerts |
| weather_alert_loop | 3 hours | Extreme temp/wind/storm alerts |
| entity_health_check | 6 hours | Dead/new entity detection |
| tg_alert_loop | 5 min | HA monitoring |
| stats_save_loop | 30 min | Stats persistence |
| reminder_loop | continuous | User reminders |
| stock_alert_loop | - | Stock alerts |
| news_scheduler | - | Scheduled news |
| backup_loop | - | Auto backup |

## Infrastructure
- LLM Cache: exact-match, 30min TTL, max 50 entries
- RotatingFileHandler: 2MB max x 3 backups
- Stats Persistence: router_stats.json
- Entity Health: notified_entities.json (no spam)
- Smart Greetings: time-of-day + shift info
- TG Bot Menu: 16 commands registered

## Deprecated (_deprecated/)
brain_backup.py, telegram_bot.py, ha_discovery.py, ruijie_integration.py, tg_ask_router.py

## Deployment
- Git deploy: commit → push → systemctl restart
- Tunnel: https://ai.salem-home.com
- /dev/context → CLAUDE_CONTEXT.md (no auth)
- /system/context → full state (API key)
- API Key: ~/.master_ai_key | HA Token: ~/.ha_token
