# CLAUDE_CONTEXT.md — Master AI v9.0.0
> Auto-generated context for Claude sessions. Updated: 2026-03-27

## Quick Reference
- **Version:** v9.0.0
- **Port:** 9000 | **Tunnel:** ai.salem-home.com | **Local:** 192.168.109.123:9000
- **Git:** main | ~610 commits
- **Lines:** server.py ~8135 | priority_engine.py ~1052 | dashboard_api.py ~1646 | signal_engine.py ~291 | journal_engine.py ~433 | trading_brain.py ~666 | chat_v7.py ~795 | stock_radar.py ~1060 | quick_query.py ~646
- **Modules:** 74 .py files
- **life.db tables:** calendar_sources, sqlite_sequence, calendar_sync_state, calendar_events, calendar_reminders, calendar_conflicts, calendar_parse_log, task_categories, tasks, expense_entries, trades, tv_watchlists, tv_alert_events, trade_journal, stock_radar_daily, confluence_signals, confluence_decisions, signal_snapshots, indicator_performance, brain_weekly_reports
- **stock_radar_daily columns:** symbol, exchange, price, trend, rsi, support, resistance, score, score_class, verdict, volume, vol_ratio, change_pct, source_timeframe, updated_at, ema_fast, ema_slow, macd, macd_signal, macd_histogram, macd_cross, daily_ema9, daily_ema21, daily_ema_cross, confluence_score, confluence_direction, avg_volume, volume_spike, macd_above_zero

## Architecture
FastAPI (server.py ~8020 lines) + extracted modules on RPi5.
- **priority_engine.py** (~1052 lines): PE + Assistant Surface (extracted from server.py in v8.4.0)
- **dashboard_api.py** (~1280 lines): FastAPI Router for /dashboard/* endpoints (8 endpoints)
- **stock_radar.py** (~1060 lines): EMA radar + MACD + confluence + daily snapshots
- **journal_engine.py** (~370 lines): Trading journal + P&L calculator + weekly report
- Context injection pattern: modules receive server globals via `init_*_context()` in lifespan startup
LLM-first: All TG/API → chat_v7.py (Anthropic native tool use, 18 tools).
Fast path: quick_query intercepts zero-LLM patterns (~25 patterns).
Models: claude-sonnet-4-6 (primary) + claude-opus-4-6 (self_check fallback).
Schema: 3.4.0 | audit.db: 30 tables | life.db: 9 tables

## chat_v7 Tools (18)
1. ha_get_state — HA states (wildcard/patterns)
2. ha_call_service — Control devices
3. ssh_run — Shell commands (confidence-gated)
4. http_request — Internal API
5. memory_search — Old memory DB
6. memory_save — Old memory DB
7. get_weather — Kuwait weather (Open-Meteo)
8. get_shift — Shift schedule (AABBCCDD)
9. memory_save_fact — Structured fact
10. memory_save_event — Time-bound event
11. memory_save_correction — User correction
12. memory_search (structured) — Structured memory
13. calendar_list_events — Google Calendar (today/tomorrow/week/custom)
14. calendar_create_event — Create calendar event
15. calendar_delete_event — Delete by title_search
16. task_list — List tasks (personal/work, filters)
17. task_create — Create task
18. task_update — Update task (status/priority/due_date)
+ inbox_summary — Unified Gmail+KNPC inbox (hours=24/48/168)

## Deployment
- systemd: master-ai.service (enabled, Restart=always)
- Restart: sudo systemctl restart master-ai.service
- Git deploy: commit → systemd auto-restarts
- IMPORTANT: commit BEFORE any kill/restart

## API Auth
- GET: X-API-Key header
- POST /ssh/run: X-API-Key + Authorization: Bearer
- /health: no auth

## v8 Phases Complete
- Phase 1: Calendar (Google OAuth, life.db, sync, reminders, TG commands)
- Phase 2: Tasks + Inbox (task_engine, tg_tasks, inbox_engine, /inbox, /week_summary, /tasks)
- Phase 3: Life OS (/life, /me, /suggest_tasks, /stats+, /today+, /tomorrow+, proactive alerts)

## TG Commands (v8)
/me — personal daily snapshot (shift+tasks+inbox+cost)
/life — unified dashboard
/today — shift+calendar+tasks today
/tomorrow — shift+calendar+tasks tomorrow
/week_summary — weekly tasks+inbox
/tasks — task management (add/done/cancel/delete/view/search)
/inbox /inbox48 /inbox_week — unified email inbox
/suggest_tasks — email→task suggestions
/stats — system stats + tasks + cost

## Alert System (Fixed)
- tg_alerts.py: offline/online devices, covers opened at night (non-inverted only), AC temp exceeded
- proactive_suggestions.py: outdoor lights long on, door unlocked at night, AC struggling, morning lights
- anomaly_engine.py: via /anomaly command + nightly digest ONLY (not realtime)
- Cover _inverted: open=closed, closed=open — alerts exclude _inverted entities

## Key Files
- server.py (~8135 lines) — main FastAPI
- priority_engine.py (~1052) — PE + Assistant Surface + Change Tracking + Temporal Intelligence
- dashboard_api.py (~1646) — FastAPI Router: /dashboard/*, /api/trade/*, /api/symbols
- signal_engine.py (~291) — Signal matrix + indicator aggregation
- journal_engine.py (~433) — Trading journal + P&L calculator
- trading_brain.py (~666) — Signal learning engine with adaptive weights
- bridge_client.py — TradingView Bridge API client (extended with pro indicators)
- modules/panel.py — Static file serving for /trading/* HTML pages
- chat_v7.py (~795) — LLM handler
- task_engine.py — Tasks CRUD (life.db)
- inbox_engine.py — Unified Gmail+KNPC inbox
- tg_alerts.py — Realtime home alerts
- proactive_suggestions.py — Proactive suggestions
- calendar_engine.py — Google Calendar sync
- quick_query.py (~646) — Zero-LLM fast patterns
- stock_radar.py (~1060) — Stock radar + daily snapshots


## v8 Phase 4: Clean & Stabilize (IN PROGRESS)

### W1 - Dead Code Cleanup (COMPLETE)
- Removed 7 dead .py files (0 references)
- Removed 8 empty .db files (0 bytes)
- Result: 79->72 .py files, 27373->26321 lines, 15->7 .db files


## Dashboard Platform (V12 - 2026-03-21)

### Architecture
8-page YAML dashboard in HA (1745 lines), **fully rebuilt with native HA cards only**.
File: `/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml`

**Card types used (native only):**
- `vertical-stack` — page structure
- `grid` — column distribution (2-col, 3-col, 4-col)
- `markdown` — text content + Jinja templates (with `card_mod` for styling)
- `button` — native HA button for actions and navigation

**Card types BANNED (cause rendering issues):**
- ~~custom:stack-in-card~~ → use `vertical-stack`
- ~~custom:mushroom-template-card~~ → use `markdown` with Jinja
- ~~custom:mushroom-title-card~~ → use `markdown` with `##` heading
- ~~custom:button-card~~ → use native `button`
- ~~custom:layout-card~~ → use `grid`

### Pages

**Home (master-ai)** — Main view, 7 sections (V12):
1. Hero Banner — version/uptime/status
2. Decision Card — top_action from assistant_surface (urgency-colored border)
3. Next Actions — auto-hide when empty
4. Later Today (V12) — shows later_today items from assistant_surface, auto-hide when empty
5. Shift + Status — grid 4: shift, home pulse, market, events
6. Top Stock Teaser — best daily context stock
7. Portfolio Preview (V13) — open positions count + total P&L
8. Command Feedback (V12) — hidden when no command, unicode fixed
9. Navigation (V12) — grid 7 columns: trading, calendar, home, assistant, system, email, news

**Trading (sub-radar)** — Subview (V12+V13):
1. Market Pulse — status + radar + watch count + alerts
2. Quick Actions (V12) — 4 buttons: toggle radar, stocks, top, status
3. Decision Card — top stock detail (price, change, RSI, EMA, trend, action)
4. Top Opportunities — table of remaining stocks
5. 30m Signals — signal flash table
6. Watchlist (V12) — capped to 6 items (was 12)
7. Journal — open positions
8. Signal History (V13) — last 10 radar events from analysis sensor
9. Diagnostics + Command Feedback (V12: unicode fixed)
10. Trading Nav (V13) — buttons to Portfolio, Analysis, Home

**Portfolio (sub-portfolio)** — NEW in V13:
1. Pulse Hero — open count + 30d stats + win rate
2. Open Positions — table with live P&L (entry, current, %, fils)
3. Signal vs Trade — 3 cards: signals 7d, confirmed, skip rate
4. Closed Trades — table with exit reason
5. 30-Day Stats — 4 cards: total, win rate, P&L, this week
6. Quick Actions — radar, analysis, review, home

**Analysis (sub-analysis)** — NEW in V13:
1. Pulse Hero — total signals + bullish/bearish + avg score
2. Radar Accuracy — 4 cards: total, bullish, bearish, avg score
3. Signal History — last 15 radar events table
4. TV Alert Log — TradingView webhook alerts table
5. Signal Stats — per-ticker signal frequency
6. Quick Actions — radar, portfolio, TV sync, home

**Calendar (sub-calendar-tasks)** — V12: shift events filtered, 3 action buttons added, unicode fixed
**Home Control (sub-home)** — V12: duplicate Status Grid removed, Arabic encoding fixed, 3 control buttons added
**Assistant (sub-assistant)** — Memory + Cost + Requests + Git Log
**System (sub-system-health)** — V12: Git Log (last 5 commits) + Tool Usage breakdown added
**Email (sub-email)** — V12: HTML divs replaced with pure markdown, refresh button added, unicode fixed
**News (sub-news)** — V12: Top 3 Decision Card (uses news_items API), empty categories hidden, typo fixed, news button added

### Sensors (configuration.yaml)
- `sensor.master_ai_dashboard` — REST `/dashboard` every 60s, ~35 attributes
- `sensor.master_ai_extended` — REST `/dashboard/extended` every 120s, ~24 attributes (radar fields REMOVED, V12: news_digest.news_items added)
- `sensor.master_ai_radar` — REST `/dashboard/radar` every 120s, DEDICATED sensor:
  - radar_enabled, radar_watch_count, radar_watchlist
  - radar_recent_signals, radar_alerts_today
  - radar_daily_context, daily_context_stale, daily_context_reason
- `sensor.master_ai_portfolio` — REST `/dashboard/portfolio` every 120s (V13):
  - open_positions (with live P&L), closed_trades, stats_30d, stats_7d, signal_vs_trade
- `sensor.master_ai_analysis` — REST `/dashboard/analysis` every 300s (V13):
  - tv_alerts, signal_history, signal_stats, radar_accuracy
- Template sensors: ac_house_avg_temperature, ac_active_units_count, ac_hottest_room, ac_coldest_room

### Sensor Size (after radar split)
- `/dashboard/radar`: ~4.7 KB (dedicated, safe)
- `/dashboard/extended`: ~4.6 KB (was 12.4 KB before split, safe)
- Both well under HA 16KB limit

### Scripts (scripts.yaml)
All buttons use `rest_command.master_ai_tg_cmd` -> POST `/dashboard/cmd`:
- master_ai_radar_toggle -> /radar_toggle
- master_ai_radar_top -> /radar_top
- master_ai_morning -> /morning
- master_ai_backup -> /backup run
- master_ai_radar_status -> /radar_status
- master_ai_stocks -> /stocks
- master_ai_news -> /news_now
- master_ai_alloff -> /alloff

### Encoding Rule (CRITICAL)
**Arabic text in YAML must be written correctly:**
1. Write YAML file on Windows via `Filesystem:write_file` (preserves UTF-8 Arabic correctly)
2. Copy to RPi via Samba: `Copy-Item → \\192.168.109.123\share\master_ai\_tools\patches\`
3. Apply via SSH: `sudo python3 _tools/patches/rebuild_dashboard.py`

**BANNED approaches:**
- Python f-strings with `\uXXXX` unicode escapes → renders as literal `\u0641` in YAML
- `Desktop Commander:write_file` directly to Samba for Arabic → encoding issues
- SSH echo/heredoc for Arabic content → encoding unreliable

### Rebuild Workflow
1. Write new page YAML to `C:\Users\MS1\Temp\radar_patch\` via `Filesystem:write_file`
2. Copy to RPi: `Copy-Item → \\192.168.109.123\share\master_ai\_tools\patches\`
3. Run: `sudo python3 _tools/patches/rebuild_dashboard.py` (replaces home + radar, keeps rest)
4. Validate: YAML check + HA reload + quick_check + git commit

### Dashboard Development Roadmap
**COMPLETED:**
- Radar sensor split (extended 12.4KB → 4.6KB + radar 4.7KB)
- Home page rebuild (native HA cards)
- Trading page: T1 (change_pct + actions) → T2 (Decision Card) → T2.5 (polish) → T3 (ChatGPT layout) → Native rebuild

**ALL 8 PAGES REBUILT + V12 UPGRADE (2026-03-21).**
**V13: Trading Dashboard Expansion (2026-03-21) — 3 trading pages (radar + portfolio + analysis), 10 pages total.**

**V12 Backend:**
- `_parse_news_items(digest)` — parses news text blobs into structured items array (category, emoji, text, source, priority)
- Wired into `/dashboard/extended`: `news_digest.news_items` (backward-compatible, existing fields unchanged)

**NEXT:**
1. **Performance monitoring** — PE adds SQLite reads each cycle
2. **Scoring fine-tune** — after usage period

### Bug Fixes (server.py)
- `home_covers_open`: Fixed double-counting. Commit: 295f3ac
- `ai_insight`: Now driven by Priority Engine (was concatenation). Fallback to old logic on PE error. Commit: a2bc722
- `/dashboard/radar`: New dedicated endpoint. Commit: f256260
- Radar fields removed from `/dashboard/extended`
- V12: Separated `tg_tasks` and `tg_stocks` imports (were in same try block — tg_tasks failure cascaded to tg_stocks)
- V12: Added `TG_STOCKS_OK` guard to `/stocks` handler (prevents crash on unloaded module)
- V12: Fixed `tg_tasks` import: uses `handle_tasks_command` instead of non-existent `cmd_tasks`
- V12: Fixed `tg_stocks` import: removed `tg_alert_loop` (correct name is `stock_alert_loop`, already imported from `tg_alerts`)


## Priority Engine v1 (2026-03-18)

Cross-domain priority ranking inside `/dashboard`. Replaces flat `ai_insight` concatenation with ranked priorities.

### How it works
- `build_priority_engine()` in server.py collects candidates from 5 domains (trading, calendar/tasks, home, email, system)
- Each candidate gets a `priority_score` (0-100) and `severity` (critical/high/medium/low/info)
- Top 3 are selected with diversity rule (max 2 per domain)
- Result returned as `priority_engine` field inside `/dashboard`
- `ai_insight` now shows `summary_line` from top priority (fallback to old logic on error)

### `/dashboard` new field: `priority_engine`
```json
{
  "priority_engine": {
    "generated_at": "ISO",
    "stale": false,
    "empty_state": false,
    "summary_line": "أهم شي الحين: ...",
    "top_priority": { "id", "domain", "type", "title", "reason", "why_now", "severity", "priority_score", "action_label", "action_target", "status", "freshness_minutes", "source", "meta" },
    "priorities": [ /* max 3 items */ ]
  }
}
```

### Domain types
- **trading:** radar_disabled, live_opportunity, daily_candidate
- **calendar:** event_starting_soon, upcoming_event, shift_soon
- **tasks:** high_task_load, overdue_task
- **home:** device_issue, home_alert, lights_high
- **email:** urgent_email, important_unread
- **system:** system_degraded, cpu_high, temperature_warning, integration_problem

### HA Sensor
- `priority_engine` added to `json_attributes` in `configuration.yaml` for `sensor.master_ai_dashboard`

### Dashboard
- Home page section 2 (AI Insight) replaced with Priority Cards showing top priority + more priorities
- Top priority card: severity indicator + title + reason + why_now + action_label
- More priorities: compact list of remaining items

### Functions (all in priority_engine.py, prefixed `_pe_`)
- `_pe_minutes_since`, `_pe_get_extended_snapshot`, `_pe_get_radar_snapshot`
- `_pe_extract_trading`, `_pe_extract_calendar`, `_pe_extract_home`, `_pe_extract_email`, `_pe_extract_system`
- `build_priority_engine`, `_pe_build_empty_state`, `_pe_make_summary`

### Git commits
- `a2bc722` feat: Priority Engine v1 - cross-domain ranked priorities in /dashboard
- `fd7d900` dashboard: Priority Engine home page YAML + pe_functions reference
- `db8ab0e` docs: CLAUDE_CONTEXT.md
- `df7d70f` fix: filter shift-calendar events
- `f85e616` feat: Change Tracking (new/resolved/escalated priorities)

### Change Tracking (v1.1)
- `_pe_last_state` global: stores previous priority IDs, severities, scores
- `_pe_compute_changes()`: diffs current vs previous, returns `changes` dict
- Fields in `priority_engine.changes`: `has_changes`, `new[]`, `resolved[]`, `escalated[]`, `summary`, `since`
- First call after restart: all priorities show as `new` (expected cold start)
- Subsequent calls: only actual differences flagged

### Assistant Surface Layer (A1: Action Reframing)
- `build_assistant_surface(pe_result, dash_data)`: transforms PE into action recommendations
- `_ACTION_TEMPLATES`: 12 templates for all existing priority types
- `_as_reframe_priority()`: converts PE priority to action (verb + why_now + consequence)
- `/dashboard` returns `assistant_surface` alongside `priority_engine` (backward-compatible)
- `configuration.yaml`: `assistant_surface` in dashboard sensor `json_attributes`
- Home page YAML reads from `assistant_surface` instead of `priority_engine`
- Quiet mode: "كل شيء تحت السيطرة" when no urgent items
- Git: `4a99429` feat(A1)

### A2-v1: Temporal Intelligence (2026-03-19)
- `_as_compute_temporal_context()`: detects time_mode (morning/market/day/evening/night), market_open, hours_to_shift
- `_TEMPORAL_WEIGHTS`: domain multipliers by time_mode (e.g. trading 1.8x during market, 0.1x at night)
- `_as_apply_temporal_weight()`: deadline boost, staleness penalty, market boost, shift proximity boost
- Output fields: `time_bucket` (now/soon/later_today/passive), `deadline_minutes`, `delay_cost`, `temporal_weight`
- PE re-sorted by temporal weight before display
- Git: `05e7be1` feat(A2-v1) + `486a4ce` fix(_pe_last_state)

### A2d: Temporal Deepening (2026-03-19)
- Lowered later_today threshold: 40 → 25 (more items survive as later_today)
- Gentler staleness penalty: 5%/hr → 3%/hr, min 0.3 → 0.5
- Force daily_candidate and email to at least later_today (never passive)
- Context-aware delay_cost: trading gets market-specific phrasing, passive gets "يمكن تجاهله اليوم"
- Promote best later_item to top when no now/soon items exist
- Git: `cbe91b4` feat(A2d) + `02aa6a3` fix(A2d promote)

### /dashboard/extended fixes
- `total_requests`: reads from `audit_log` (was non-existent `traces` table)
- `cost_today/total`: now uses real token tracking from `cost_tracker.py` (was duration estimate)
- `tool_usage`: reads `audit_log.route_type` (backfilled 1188 unknown→tg_command)
- Inbox cache: 5-minute TTL prevents Gmail API timeout
- Git: `4b94725` fix + `fb154cd` perf


## v8.3.0 Transformation (2026-03-21)

### Phase 1: Audit & Data Quality
- Fixed `route_type` tracking: all 3 `audit_log()` calls now pass proper route_type (llm_chat, tg_command)
- Backfilled 1188 "unknown" audit entries → `tg_command`
- Verified: expenses table exists, structured memory works (312 memories), all TG commands have live handlers

### Phase 2: Email → Task Pipeline
- `inbox_engine.py`: `auto_create_tasks_from_inbox()` now deduplicates via `source_ref`
- Added `auto_create_logbook_task()`: detects KNPC logbook emails and auto-creates review tasks
- PE email action_label updated: "راجع البريد أو حوّله لمهمة"

### Phase 3: Trade Auto-Logging (superseded by v8.4.0 Trade Confirmation)
- Originally auto-logged trades silently; replaced in v8.4.0 with interactive TG confirmation

### Phase 4: Real Cost Tracking
- `/dashboard/extended` `cost_today/total` now reads from `cost_tracker.py` (real token counts from API responses)
- Replaced duration-based estimation with actual `input_tokens` + `output_tokens` pricing
- `tool_usage` now shows correct distribution after route_type backfill

### Phase 5: Version Bump
- VERSION: 8.0.0 → 8.3.0


## v8.4.0 Server Split + Trade Confirmation (2026-03-21)

### Phase 1: Extract priority_engine.py
- Extracted all `_pe_*` and `_as_*` functions from server.py (~1052 lines)
- `set_inbox_cache_ref()` pattern for decoupled `ha_dashboard_extended` reference
- Wired in lifespan startup: `_pe_set_inbox_cache_ref(ha_dashboard_extended)`
- server.py: 9691 → 8663 lines

### Phase 2: Extract dashboard_api.py
- FastAPI APIRouter with all `/dashboard/*` endpoints (~828 lines)
- Context injection via `init_dashboard_context()` passing VERSION, START_TIME, etc.
- `app.include_router(dashboard_router)` in server.py
- server.py: 8663 → 7843 lines

### Phase 3: SKIPPED (tg_handle_command)
- 1570 lines, 35+ global flags, 40+ helper functions — too risky to extract
- tg_handle_command stays in server.py

### Phase 4: Trade Confirmation via TG Inline Keyboard
- TradingView webhook no longer auto-logs trades silently
- Instead sends TG message with inline buttons: "شريت ✅" / "تجاهلت ❌"
- `trade_confirm:` callback → `open_trade()` or `close_trade()` in journal_engine
- `trade_skip:` callback → log only, no trade recorded
- Also fixed broken `tg_send(message)` call (was missing chat_id) → now uses `get_admin_chat_id()`
- Non-trade signals (info, alert) still sent as plain TG messages

### Phase 5: Version Bump
- VERSION: 8.3.0 → 8.4.0
- server.py: ~9691 → ~7899 lines (19% reduction)
- New modules: priority_engine.py (1052), dashboard_api.py (828)


## v8.5.0 Integrated Trading Platform (2026-03-21)

### Phase 1: Price Normalization
- `_normalize_price_to_fils(price, symbol)` in tv_data.py
- Applied in: tradingview_bridge.py `save_tv_alert()`, webhook handler, dashboard P&L
- Rule: price < 10 → KWD (×1000 to fils), price >= 10 → already fils

### Phase 2: Radar → TG Confirmation Buttons
- When radar detects EMA9/21 cross on any of 128 stocks → sends TG alert WITH inline buttons
- "شريت ✅" / "تجاهلت ❌" — same system as webhook trade confirmation
- `_radar_sender` now receives signal metadata (symbol, price, score, signal_type)
- Only sent for signals that pass smart filter (score >= 70, A-class, bullish, or open trade symbol)

### Phase 3: TV Watchlist Sync
- `/tv_sync` command syncs TV watchlist from radar watchlist (128 stocks)
- `sync_tv_from_radar()` in tradingview_bridge.py
- Auto-deactivates old items, inserts/reactivates from radar

### Phase 4: Journal Live P&L
- `/dashboard/radar` endpoint enriches open trades with current_price, pnl_pct, pnl_fils
- Uses `stock_radar_daily` table (no blocking API calls) for current prices
- Resolves Arabic symbol names via `resolve_symbol()`

### Phase 5: Daily Trading Summary
- Runs at 13:00 KWT (after market close 12:40)
- Includes: today's radar signals count, top signals by score, open trades with live P&L, closed trades stats
- Sun-Thu only (KSE trading days)

### Phase 6: Version Bump
- VERSION: 8.4.0 → 8.5.0


## Trading Platform v2 (2026-03-27)

### HTML Pages (www/trading/)
5 professional HTML pages served from `/www/trading/`, routed via `modules/panel.py`:
- **radar.html** (30KB) — Command Center: ticker strip, signal filters, hero decision card, opportunities table, mini positions
- **signals.html** (39KB) — Signal Matrix: 18-column sortable table, search/filter, collapsible indicator legend
- **positions.html** (46KB) — Position Management: add/close/edit trades, signal health alerts, P&L with fees
- **journal.html** (24KB) — Performance Review: pulse stats, open/closed trades, monthly stats, best/worst, period comparison
- **brain.html** (24KB) — Trading Brain: indicator weights, evaluation history, learning status

Design: Boursa Kuwait institutional dark navy (#070D17) + gold (#C6974B), Tajawal + Noto Kufi Arabic + IBM Plex Mono
All pages: responsive, RTL Arabic, auto-refresh 120s, shared nav bar, Kuwait time clock
HA dashboard: each page displayed via iframe card in corresponding sub-page

### Trade Management API (dashboard_api.py)
```
POST /api/trade/open   — Open new trade (symbol, entry_price, quantity, strategy, stop_loss, take_profit)
POST /api/trade/close  — Close trade (trade_id, exit_price, reason)
POST /api/trade/update  — Update SL/TP (trade_id, stop_loss, take_profit)
GET  /api/symbols      — List all 128 tracked symbols
```

P&L Calculation: 2-layer pricing (bridge cache → stock_radar_daily fallback)
Each position includes: pnl_pct, pnl_kwd, fees_kwd, net_pnl_kwd, quote_source, quote_stale
Broker fee: 0.125% per transaction (0.25% round trip)

Signal Health Alerts on positions:
- confluence < 40 → "بيع — confluence ضعيف" (danger)
- RSI divergence bearish → "مراجعة — divergence سلبي" (warning)
- Price below stop_loss → "بيع فوراً" (danger)
- Bearish MACD + confluence < 50 → "مراجعة — momentum سلبي" (warning)

### Trading Brain (trading_brain.py, 666 lines)
- TRACK: `snapshot_signals()` every 2h during market (Sun-Thu 9-13 KWT)
- EVALUATE: `evaluate_pending_signals()` daily 13:30 KWT
- LEARN: `update_indicator_performance()` after each evaluation
- ADJUST: `adjust_weights()` weekly Sunday
- REPORT: `generate_weekly_report()` Friday 14:00 KWT → Telegram

7 indicators tracked: RSI, MACD, EMA, ADX, VOL, STOCH, OBV
Adaptive weight formula: new_weight = base_weight × (0.5 + rolling_hit_rate_50)
Weight range: 0.3 (terrible) → 2.0 (excellent), minimum 30 signals before adjustment

DB tables: signal_snapshots, indicator_performance, brain_weekly_reports
Endpoint: GET /dashboard/brain | Dashboard: /trading/brain

### Signal Engine (signal_engine.py, 291 lines)
Extended indicator fields in bridge_client.py `_normalize_analysis`:
- atr_14, adx, bb_squeeze, bb_bandwidth, vol_ratio, stoch_k, stoch_d
- signals dict: rsi_divergence, macd_momentum, ema_cross, confluence

Endpoint: GET /dashboard/signals — returns full signal matrix for all tracked stocks
HA sensor: sensor.master_ai_signals (REST /dashboard/signals every 120s)

### OPEN_PATHS (server.py)
```
/trading, /trading/*, /dashboard/signals, /dashboard/portfolio, /dashboard/journal, /dashboard/brain,
/api/trade/open, /api/trade/close, /api/trade/update, /api/symbols
```
All `/api/*` paths open via startswith check.

### HA Dashboard Trading Pages (iframe cards)
```
sub-radar     → iframe https://ai.salem-home.com/trading/radar
sub-signals   → iframe https://ai.salem-home.com/trading/signals
sub-positions → iframe https://ai.salem-home.com/trading/positions
sub-journal   → iframe https://ai.salem-home.com/trading/journal
sub-brain     → iframe https://ai.salem-home.com/trading/brain
```
Home page nav: 9 buttons (added العقل/brain)

### Recent Git Commits (2026-03-27)
```
b6c35d6 feat: add indicator legend to signals page
a547f75 fix: journal best/worst shows single card when only 1 trade exists
6b612b1 fix: P&L calculation + 2-layer price freshness for portfolio/journal
5b7cf16 feat: trade management system — add/close/update trades from dashboard
84443cd fix: open /dashboard/portfolio + /dashboard/journal for trading platform
832a96f feat: trading brain — signal learning engine with adaptive weights
1afbb30 feat: trading platform v2 — 4 professional HTML pages + HA iframe integration
3015145 fix: open /dashboard/signals for trading page + add dashboard button
```

### trades Table Schema (22 columns)
```
id, symbol, name_ar, direction, status, entry_price, entry_date, entry_reason,
entry_signal_id, quantity, exit_price, exit_date, exit_reason, pnl_fils, pnl_pct,
strategy, timeframe, notes, created_at, updated_at, stop_loss, take_profit
```
Current open positions: EQUIPMENT@183, ALOLA@109, ARGAN@97


## Live Status
- Uptime: check /health
- Plugins: 9
- Memory: True
- Brain: True


## TradingView Bridge API (Windows PC)
### Overview
- Local FastAPI service on Windows PC at C:\Users\MS1\tradingview-bridge
- Python 3.13, port 8059
- Connects to TradingView WebSocket (wss://data.tradingview.com/socket.io/websocket) with JWT auth
- Provides live KSE stock data: price, OHLCV, RSI(14), MACD(12,26,9), EMA(9,20,50,200), Support/Resistance
- TradingView highest tier subscription

### Endpoints
- GET http://PC_IP:8059/health - Service health
- GET http://PC_IP:8059/quote?symbol=CLEANING&exchange=KSE - Live quote
- GET http://PC_IP:8059/ohlcv?symbol=CLEANING&exchange=KSE&interval=1D&bars=300 - Historical bars
- GET http://PC_IP:8059/analysis?symbol=CLEANING&exchange=KSE&interval=1D&bars=300 - Full analysis (quote+indicators+S/R)
- GET http://PC_IP:8059/multi-analysis?symbols=CLEANING,NBK,ZAIN&exchange=KSE - Multi-symbol batch
- GET http://PC_IP:8059/search?query=CLEAN&exchange=KSE - Symbol search

### Authentication Flow
1. Chrome started with: --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir=real-profile
2. grab_cookies.py extracts cookies via Chrome CDP (port 9222)
3. get_auth_token.py extracts JWT auth_token from TradingView page source via CDP
4. Cookies saved in tv_cookies.json (sessionid + auth_token JWT)
5. JWT expires periodically - re-run get_auth_token.py when needed

### Key Files
- app/main.py - FastAPI endpoints
- app/tv_ws.py - TradingView WebSocket client (~m~len~m~payload framing)
- app/indicators.py - RSI, MACD, EMA, S/R calculation (pure Python, no pandas)
- app/models.py - Pydantic response models
- app/cache.py - SQLite cache (quote 30s, bars 120s TTL)
- grab_cookies.py - Extract cookies from Chrome via CDP
- get_auth_token.py - Extract JWT auth token from TradingView page

### WS Protocol Notes
- Must read initial session message before sending auth
- create_series requires empty string "" as last parameter
- Heartbeat replies must be properly framed: ~m~{len}~m~{heartbeat_body}
- Auth token is JWT (not sessionid cookie)

### Integration with Master AI
- Master AI can call Bridge API over LAN: http://WINDOWS_PC_IP:8059/analysis?symbol=...
- Bridge provides structured JSON for dashboard, radar, and trading analysis
- No API key required currently (internal LAN only)

### Startup Sequence
1. Kill Chrome: taskkill /F /IM chrome.exe /T
2. Start Chrome with debug: Start-Process chrome.exe "--remote-debugging-port=9222","--remote-allow-origins=*","--user-data-dir=C:\Users\MS1\AppData\Local\Google\Chrome\User Data","https://www.tradingview.com/chart/"
3. Extract cookies: python grab_cookies.py (if needed)
4. Extract auth token: python get_auth_token.py (if JWT expired)
5. Start server: python -m uvicorn app.main:app --host 0.0.0.0 --port 8059
