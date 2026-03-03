# CLAUDE_CONTEXT.md — Master AI v5.5.1
> Auto-generated context for Claude sessions

## Quick Reference
- **Version:** v5.5.1 (code v5.5.1)
- **Port:** 9000 | **Tunnel:** ai.salem-home.com
- **Git:** main | **Lines:** server.py ~5,760 | quick_query.py ~330 | tg_report.py ~86
- **Modules:** 16/16 | **Plugins:** 9 | **Schedulers:** 12

## Architecture
Single-file FastAPI (server.py) + helper modules on RPi5.
SmartRouter v2.2 -> quick_query (12 patterns, zero-LLM) -> intent_router -> LLM chat.
LLM: Anthropic Claude Sonnet 4 (streaming to TG with live edit).

## Key Features (this session)
- **LLM Streaming:** Response streams to TG with edit-in-place + typing indicator
- **LLM Cache:** 30min TTL, max 50 entries, exact-match MD5
- **Smart Follow-up:** Contextual buttons after device actions (off->all off, temp->all ACs)
- **Arabic Normalizer:** Tashkeel-only removal + hamza/taa normalization for quick_query
- **Response Time Tracking:** Per-message timing, slow warnings >5s
- **/report:** Daily report (shift+weather+devices+stats+savings%)
- **/find <q>:** Entity search by name
- **/alloff:** Kill everything with confirmation
- **/weather:** Kuwait weather from Open-Meteo
- **/covers:** Cover status with open/close all buttons
- **/ping:** Health check (uptime, HA, avg response)
- **/home:** 2-page menu (10+10 buttons)
- **/help:** Categorized command reference

## Quick Query Patterns (12, zero-LLM)
home status, AC count, lights count, shift, room status (10 rooms),
locks, media, weather, covers, active devices

## Telegram Commands (18)
/home /lights /temp /rooms /scenes /locks /media /covers /weather
/shift /week /stocks /find /alloff /report /ping /help /status

## Background Schedulers (12)
shift_alert, entity_health, morning_report, nightly_summary,
weather_alert, ha_monitor, stock_alert, news, reminders,
expense_reset, discovery_sync, summary_scheduler

## Files
- server.py (~5,760) - main server
- quick_query.py (~330) - zero-LLM patterns
- tg_report.py (~86) - daily report generator
- tg_intent_router.py (~1,390) - device command routing
- smart_router.py (~94) - message classification
- life_work.py - shift calculator (EPOCH: 2024-01-04)
- entity_map.json - 25 rooms, 566 entities
