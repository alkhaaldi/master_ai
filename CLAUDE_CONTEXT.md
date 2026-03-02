# Master AI — Claude Context
# Updated: 2026-03-03T02:20 (Night session — 13 commits)
# Git: e7fde76 (main)

## System
- Version: v5.4.0 (code v5.4.6)
- server.py: ~5,330 lines
- Port: 9000 | RPi5 | FastAPI + systemd
- Modules: 16/16 all active
- Plugins: 9 (ha_get_state, ha_call_service, ssh_run, respond_text, http_request, memory_store, win_diagnostics, win_powershell, win_winget_install)
- DB: audit.db (WAL mode, 11 tables including user_tasks, daily_stats, proactive_alerts)
- Autonomy: Level 3 (low only), Policy: auto≤30, approval≤60, block≥61

## Key Files
| File | Lines | Purpose |
|------|-------|---------|
| server.py | ~5330 | Main FastAPI server, TG polling, all commands |
| brain_core.py | ~590 | LLM prompt builder, room aliases, entity map |
| smart_router.py | ~105 | SmartRouter v2.2 — greeting/chat/action/unknown classifier |
| quick_query.py | ~160 | Fast HA/shift answers WITHOUT LLM (v2) |
| tg_intent_router.py | ~1390 | Device command NLU (شغل/طفي/مكيف) |
| tg_session_resolver.py | — | Followup action resolution |
| life_work.py | — | Shift schedule (AABBCCDD, epoch 2024-01-04) |
| life_stocks.py | — | Portfolio tracking |
| life_expenses.py | — | Expense tracking |
| life_health.py | — | Health tracking |
| tg_morning_report.py | — | Daily 5:30 AM morning report |
| tg_alerts.py | — | HA monitoring (offline/cover/AC alerts every 5min) |
| tg_reminders.py | — | Reminder system |
| tg_news.py | — | News fetcher |
| entity_map.json | — | 25 rooms, 566 entities |
| ha_discovery.py | — | Live entity discovery (916 entities) |
| entity_health.py | — | Entity map health validation |
| tasks_db.py | — | User tasks (user_tasks table) |

## Message Flow (TG)
1. /commands → direct handler (zero LLM)
2. Intent router → device NLU: شغل/طفي/مكيف (zero LLM)
3. Session followup → context-aware actions
4. Life router → stocks/expenses/work/health keywords
5. **Quick Query** → "وضع البيت", "شفتي", "كم مكيف", room status (zero LLM)
6. SmartRouter v2.2 → greeting(template) / chat(brain LLM) / action(planner) / unknown(LLM)

## SmartRouter v2.2
- Greeting: regex match → random template with time-of-day + shift info (zero LLM)
- Chat: keyword match (questions + work + stocks + expenses + health + conversational)
- Action: device control keywords
- Unknown: only if nothing matches → goes to LLM
- Short Arabic (≤5 words) → auto-classified as chat
- Keywords added this session: shift/دوام/محفظة/أسهم/اتجهز/أول/ثاني

## Quick Query v2 (NEW — zero LLM)
- "شنو وضع البيت" → lights/AC/covers count from HA
- "كم مكيف شغال" → AC list with temps
- "كم نور شغال" → lights count
- "شنو شفتي/دوامي" → shift + times (today/tomorrow)
- "وضع الديوانية/المطبخ/الماستر..." → room-specific status (lights/AC/covers)
- Room map: 10 rooms mapped to entity_id patterns

## TG Commands
### Core
/status /help /home (inline keyboard)
### Monitoring
/diag (CPU/RAM/Temp/uptime/modules/log) | /stats (router breakdown) | /summary (daily dashboard) | /errors
### Home
/lights /temp /rooms /scenes /cam /find
### Life
/shift /week (=schedule) /morning /stocks /price X /tasks /remind /reminders /expense /expenses /health
### System
/brain /log /crash /clearlog /backup /restart /approvals

## Background Loops (Schedulers)
| Loop | Interval | Purpose |
|------|----------|---------|
| telegram_polling | continuous | TG message polling |
| morning_report | daily 5:30 AM | Morning briefing |
| entity_health_check | 6 hours | Dead/new entity detection (file-backed, no spam) |
| tg_alert_loop | 5 min | HA monitoring (offline/cover/AC) |
| reminder_loop | continuous | User reminders |
| stock_alert_loop | — | Stock price alerts |
| news_scheduler | — | Scheduled news |
| backup_loop | — | Auto backup |
| stats_save_loop | 30 min | Router stats persistence |
| **shift_alert_loop** | 15 min | Pre-shift (1h before) + tomorrow shift change alerts |

## Infrastructure (this session)
- **RotatingFileHandler**: 2MB max × 3 backups (auto-rotate)
- **Stats Persistence**: router_stats.json, save every 30min + atexit + load on startup
- **Entity Health**: notified_entities.json — sends alert ONCE per new entity, file-backed
- **Shift Alerts**: automatic pre-shift reminder + tomorrow shift type notification

## Recent Bug Fixes (this session)
- SmartRouter import: classify_message alias (backward compat)
- BRAIN_LEARN_HOOK: undefined in stock fallback → removed
- Planner UTF-8: corrupted Arabic → fixed with unicode escapes
- /tasks: table collision → renamed to user_tasks
- Path conflict: FastAPI Path() vs pathlib.Path() → _pl alias
- stats_save_loop: missing function definition → added
- Entity health spam: 79 entities every 6h → send once, file-backed

## Deployment
- Git deploy only: commit → push → ssh update.sh
- Tunnel: https://ai.salem-home.com (Cloudflare)
- SSH: POST /ssh/run with X-API-Key
- Deploy: POST /deploy with file_path + content
- API Key: ~/.master_ai_key (read via MCP)
- HA Token: ~/.ha_token (read via MCP)

## Next Steps (potential)
- Proactive alerts improvements (weather-based, energy usage)
- More quick_query patterns (door/window status, energy)
- LLM response caching for repeated questions
- TG inline keyboard for room control
- Daily auto-summary at midnight
