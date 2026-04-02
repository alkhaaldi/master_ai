# CLAUDE_CONTEXT.md — Master AI v9.0.0
# Last Updated: 2026-04-02
# مصدر الحقيقة الأول: GET /system/context

## Quick Reference
- **Version:** v9.0.0 | **Schema:** 3.4.0
- **Port:** 9000 | **Tunnel:** https://ai.salem-home.com
- **Git:** main | **~630 commits**
- **DB:** data/life.db | **~45 tables** (5 new from Claude Code Patterns project)
- **Autonomy:** Level 3 | Policy: auto ≤30, approval ≤60, block ≥61
- **Plugins:** 9 | **Schedulers:** 12+
- **Feature Flags:** 10 (DB-backed, API-toggleable, no restart needed)
- **New Files (Apr 2):** feature_flags.py, service_health.py, kairos.py, context_compactor.py, hooks.py, tool_registry.py

## Architecture
RPi5 + FastAPI (server.py) + systemd service.
Bridge API on Windows PC (192.168.111.158:8059) — TradingView WebSocket data.
Dashboard: 9 HTML iframe pages in HA via Cloudflare tunnel (7 core + 2 utility).

## Claude Code Patterns — Infrastructure (Added 2026-04-02)
Inspired by Claude Code source leak analysis. 6 phases, 7 new files, 5 new DB tables, ~15 new endpoints.

### Phase 1: Feature Flags v2 (`feature_flags.py`)
- **10 flags** in `feature_flags` table (life.db), DB-backed, thread-safe, 60s cache
- Env vars (`FEATURE_*`) still override DB values for backward compatibility
- **Endpoints:** GET `/api/flags`, POST `/api/flags/{name}/toggle`
- Toggle any feature without restart
- Commits: `07b68b5`

### Phase 2: Service Health Hub (`service_health.py`)
- Central health monitoring for 7 services: bridge, home_assistant, telegram, llm_anthropic, daily_snapshot, news_boursa, news_gemini
- Reads existing circuit breakers (bridge_client, gemini_scanner, server.py LLM)
- Traffic light status: up/down per service
- **Endpoint:** GET `/api/service-health`
- Commit: `2668bcc`

### Phase 3: KAIROS Background Agent (`kairos.py`)
- Proactive health monitor — checks every 5 minutes
- Auto-detects service failures, sends Telegram alerts (deduped per hour)
- Sends recovery notifications when services come back
- Daily summary at 11PM
- Gated by `ff.is_enabled("kairos")`
- **Tables:** `kairos_alerts`, `kairos_log`
- **Endpoints:** GET `/api/kairos/status`, GET `/api/kairos/log`
- **Telegram:** `/kairos` command
- Commit: `21f3a1c`

### Phase 4: Telegram Queue (in `kairos.py`)
- Offline message buffer — stores messages in DB when Telegram is down
- Flushes queue on recovery (oldest first, max 20 per cycle)
- **Table:** `telegram_queue`
- tg_send fallback patched in 3 locations in server.py
- Gated by `ff.is_enabled("telegram_queue")`
- Commit: `21f3a1c`

### Phase 5: Chat Context Compaction (`context_compactor.py`)
- 4-stage pipeline (collect → compress → rank → inject) for Telegram conversations
- Triggers when messages > 12
- Caches chunk summaries in `context_cache` table
- Fallback: if compaction fails → last 10 messages only
- Gated by `ff.is_enabled("chat_compaction")`
- Commit: `3f88fd8`

### Phase 6: Hooks + Tool Registry (`hooks.py` + `tool_registry.py`)
- **Hooks:** 10 event types (service_down, service_up, alert_sent, flag_toggled, etc.)
- Async handlers, DB-logged in `hook_log` table
- **Tool Registry:** 12 tools registered across 4 categories (home, system, trading, news)
- Service health check before execution
- **Endpoints:** GET `/api/hooks/stats`, GET `/api/hooks/log`, GET `/api/tools`, GET `/api/tools/{name}`
- Gated by `ff.is_enabled("hooks")` and `ff.is_enabled("tool_registry")`
- Commit: `c34876b`

### Trading Engines Integration (Partial — 2026-04-02)
Connecting trading pipeline to the 6 infrastructure modules. Work in progress.

**Layer 1: Degraded Mode (DONE — commit 182bd75)**
- bridge_client.py reports to service_health on every request (mark_up/mark_down)
- dashboard_api.py returns `degraded: true` + `degraded_reason` when Bridge is down
- stock_radar.py skips radar cycles (300s sleep) when Bridge is down
- Frontend degraded banners on home.html, radar.html, positions.html (amber warning)

**Layer 2: Signal Hooks (PENDING)**
- Plan ready: _tools/LAYER2_3_4_HOOKS_TOOLS_FLAGS.md
- Will add: after_signal, before_trade_alert, after_daily_refresh events
- Will add: market hours check handler to block off-hours alerts

**Layer 3: Trading Tools (PARTIAL — commit 8bc3e6c)**
- 3 trading tools registered: bridge_status, open_trades, trade_stats
- Total registry: 12 tools in 4 categories

**Layer 4: Trading Feature Flags (PENDING)**
- Plan ready: _tools/LAYER2_3_4_HOOKS_TOOLS_FLAGS.md
- Will add: radar_enabled, momentum_alerts, golden_engine, position_monitor, daily_refresh

### Feature Flags Reference
| Flag | Default | Description |
|------|---------|-------------|
| circuit_breakers | ON | Circuit breakers for external calls |
| timeouts | ON | Request timeouts |
| smart_router_v2 | ON | Smart intent router v2 |
| entity_health | ON | Entity health monitoring |
| kairos | ON | Background health agent |
| telegram_queue | ON | Offline message buffer |
| chat_compaction | ON | Chat context compression |
| hooks | ON | Event hook system |
| tool_registry | ON | Central tool catalog |
| speed_templates | OFF (env) | Speed engine templates (env override) |

### Dashboard: system.html Updated
- Added: Service Health traffic lights (7 services)
- Added: KAIROS status + action log
- Added: Feature Flags toggle switches (10 flags)
- Auto-refresh: health 30s, KAIROS 60s, flags 60s

### Master Plan Reference
Full plan: `_tools/CLAUDE_CODE_PATTERNS_MASTERPLAN.md`

## TradingView Bridge API — IMPORTANT DETAILS
- **Location:** C:\Users\MS1\tradingview-bridge
- **Python:** .venv313\Scripts\python.exe | uvicorn app.main:app --host 0.0.0.0 --port 8059
- **Auth:** JWT token in tv_cookies.json (list format: [{name, value, domain, ...}])
- **Token renewal:** TokenWatchdog background thread — auto-renews every 5 min check
  - Reads auth_token from Chrome CDP (port 9222) via HTML scan
  - Chrome MUST be open with: --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir=C:\Users\MS1\ChromeDebug
  - Startup script: C:\Users\MS1\tradingview-bridge\start_bridge.bat
- **Endpoints:**
  - GET /health — bridge status
  - GET /token-status — JWT expiry info
  - POST /refresh-token — force token renewal now
  - GET /analysis?symbol=X&interval=30 — indicators including EMA 9/21
  - GET /quote?symbol=X — live price
  - GET /multi-analysis?symbols=A,B,C — bulk (batches of 25, 1s delay)
- **Indicators returned:** rsi_14, macd, ema_9, ema_21, ema_20(=ema_21), ema_50, ema_200, atr_14, bb_*, obv, vol_ratio, adx, stoch_k/d
- **models.py fix (2026-03-31):** Added ema_21 to IndicatorBar + IndicatorsSnapshot

## Core Files
| File | Role |
|------|------|
| server.py | Main FastAPI server + all endpoints |
| dashboard_api.py | Dashboard data endpoints |
| signal_engine.py | Signal generation (30m + 1D) with Brain weights |
| stock_radar.py | 128 KSE stock monitoring every 90s |
| trading_brain.py | Learning engine — Bayesian + regime-aware + decay |
| bridge_client.py | Bridge API client (async, cache, circuit breaker) |
| journal_engine.py | Trade journal + P&L + ATR trailing stop |
| stock_personality_engine.py | Per-stock profiles, patterns, auto-notes |
| golden_engine.py | Golden opportunities — pattern matching + confidence |
| trading_decision_engine.py | Entry timing + trade plan (zone/stop/target/R:R) |
| sr_engine.py | Support/Resistance from swing pivots + clustering |
| brain_backfill.py | Historical backfill (1D + 30m) from Bridge |
| priority_engine.py | Cross-domain priority ranking |
| data_integrity.py | Data quality gate (freshness + S/R + ATR fallback) |
| position_engine.py | Position monitoring + 5 alert types + auto breakeven |
| risk_engine.py | Max 2/sector, max 8 positions, low liquidity downgrade |
| sector_map.py | 130 stocks in 10 sectors |
| kse_data_collector.py | Daily data collector from Bridge (128 stocks, scheduler 1:30PM KWT) |
| feature_flags.py | DB-backed feature flags with API toggle (Phase 1) |
| service_health.py | Central health monitoring for 7 services (Phase 2) |
| kairos.py | Background health agent + Telegram queue (Phase 3+4) |
| context_compactor.py | Chat context compression pipeline (Phase 5) |
| hooks.py | Event hook system with 10 event types (Phase 6) |
| tool_registry.py | Central tool catalog with 12 tools (Phase 6) |


## Trading Brain — Learning System
- **Total signals:** 66,937 (16,147 1D backfill + ~50,790 30m backfill)
- **Evaluated:** 63,620
- **Overall hit rate:** 22.1%
- **Learning mode:** bayesian_regime_aware
- **Indicator weights (learned):**
  - Volume: 1.15 (best — 65% hit rate)
  - ADX: 1.13 (63%)
  - Stochastic: 1.05 (55%)
  - MACD: 0.87 (37%)
  - EMA: 0.85 (35%)
  - RSI: 0.75 (worst — 25%)
- **Thresholds:** brain_learned from 40,966 data points
  - Ready: score ≥ 60, vol > 1.2
  - Setup: score ≥ 40
  - Watch: score ≥ 50
  - Avoid: score < 105
- **Regime stats:** 3 regimes (trending/transition/ranging) × 6 indicators

## Stock Personality Engine
- **128 profiles** with per-stock indicator lifts
- **6,400 patterns** (1-3 atom combinations, min 3 occurrences)
- **128 auto-notes** in Arabic
- **21 pattern atoms:** RSI, MACD, EMA, ADX, Volume, Stoch, BB, S/R proximity, ATR, breakout/breakdown
- **Endpoints:** GET /api/stocks/symbol/{symbol}, GET /api/stocks/profiles
- **Tables:** stock_profiles, symbol_patterns, symbol_notes

## Golden Opportunities Engine
- Matches live data against historical winning patterns
- **Confidence score:** 6 components (match 35% + win_rate 20% + sample 15% + pattern 10% + gain 10% + alignment 10%)
- **Quality filters:** occurrences ≥ 8, win_rate ≥ 55%, match_ratio ≥ 75%
- **Endpoint:** GET /api/decisions-now

## Trading Decision Engine V2
- **Entry Status:** 5 states — enter_now / wait_pullback / watch / missed / avoid
- **Trade Plan:** entry zone (low-high) + stop loss (S/R + ATR) + target 1 & 2 + R/R ratio
- **S/R Engine:** swing pivot detection + level clustering from daily bars
- **Telegram Alerts:** dedup + send on enter_now with confidence ≥ 80
- **Table:** alert_history (dedup_key unique)

## Strategy Mining Engine
- **Signal snapshots:** 66,937 signals, 40,966 clean with outcomes
- **signal_outcomes table:** 40,966 rows with ~7.9 atoms per signal
- **Regime classification:** trending 54%, ranging 28%, transition 18%
- **FP-Growth mining:** 4,227 raw → 1,552 validated → stored in mined_strategies
- **Top pattern:** RSI>70 + MACD decel + high ATR + low vol = 70% win, EV 19.4
- **Endpoints:** GET /dashboard/strategies
- **Tables:** signal_outcomes, mined_strategies

## 4-Phase Trading Infrastructure

### Phase 1: Data Integrity Gate
- **data_integrity.py** — DataIntegrityGate class
- check_freshness, check_sr_quality, get_quality_score (0-100), gate_decision
- Fallback S/R from ATR when support/resistance is NULL

### Phase 2: Position Management Engine
- **position_engine.py** — 5 alert types, auto breakeven, Telegram alerts
- New table: position_alerts
- Endpoints: GET /api/portfolio-status, POST /api/portfolio-monitor

### Phase 3: Risk Gate + Sector Classification
- **sector_map.py** — 130 stocks in 10 sectors
- **risk_engine.py** — Max 2/sector ENTER, max 8 positions, low liquidity downgrade

### Phase 4: Signal Review Engine
- **signal_review.py** — daily review of yesterday's signals
- **reviews.html** — dashboard with Arabic trade reports
- **Scheduler:** 2:00PM KWT daily
- **Telegram commands:** /فرص (current opportunities), /تقييم (yesterday review), /موجة (momentum alerts)
- **Momentum alerts:** strong-moving stocks regardless of pattern win rate

## EMA 9/21 Scalper Dashboard
- **scalper.html** — 128 KSE stocks EMA 9/21 crossover on 30m timeframe
- **Pulse cards** with age badges (fresh/today/recent/old/reversed)
- **Filter tabs** including "صاعدة حالياً" (currently bullish)
- **Auto-refresh** every 90 seconds + sound alerts
- **Linked from home.html** as most important page
- **Backend endpoints:**
  - GET /dashboard/ema-crosses — historical crossover events
  - GET /dashboard/ema-proximity — stocks near crossing
  - GET /dashboard/ema-active — last known signal per stock
  - GET /dashboard/ema-live — real-time EMA9/EMA21 from Bridge (batched, cached 3min)
- **Data source:** bridge_client.py → Bridge API → TradingView WebSocket

## Bridge JWT Token System (FIXED 2026-03-31)
### Problem History
- JWT token expired 2026-03-25
- Chrome HttpOnly cookie prevented JS access
- CDP via --remote-debugging-port=9222 required cmd.exe (not PowerShell)

### Solution Implemented
1. Chrome launched via: `start_bridge.bat` (cmd only, not PowerShell)
   - Path: C:\Progra~1\Google\Chrome\Application\chrome.exe
   - Flags: --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir=C:\Users\MS1\ChromeDebug
2. Token extracted from HTML via CDP Runtime.evaluate (Page.loadEventFired)
3. Saved as LIST format in tv_cookies.json: [{name, value, domain, httpOnly, ...}]
4. **TokenWatchdog** (app/token_watchdog.py) — background thread in Bridge
   - Checks every 5 min, renews 30 min before expiry
   - Uses CDP to grab fresh token from Chrome automatically
   - Endpoints: GET /token-status, POST /refresh-token
5. models.py fix: added ema_21 to IndicatorBar + IndicatorsSnapshot (was missing, Pydantic filtered it out)

### Current Status (2026-03-31 20:47)
- Bridge: running PID 35120, port 8059
- Token: valid, ~4h expiry
- EMA9 + EMA21: both returning correctly
- TokenWatchdog: active, auto-renews when Chrome is open

### Startup Procedure
Run once after PC restart:
`C:\Users\MS1\tradingview-bridge\start_bridge.bat`
This opens Chrome (debug mode) + starts Bridge + TokenWatchdog handles the rest.

## Dashboard Pages (7 core + 2 utility)
All served as iframes in Home Assistant via Cloudflare tunnel.

### Core Trading Pages:
1. home.html — Command center, workflow launcher
2. radar.html — 128-stock surveillance, market-wide monitoring
3. analysis.html — Gemini 2.5 Pro deep technical analysis (click any stock)
4. positions.html — Portfolio monitoring, P&L, active trade management
5. journal.html — Trade journal, performance review
6. news.html — Boursa RSS + Gemini news (economy/world/tech)
7. system.html — System health monitoring

### Utility (accessible but outside main nav):
- home-control.html — Smart home controls
- email.html — Email management

### Archived (files kept on disk, removed from nav):
- scalper.html — EMA 9/21 crossover scalper (128 stocks)
- decisions.html — Scanner decision engine
- personality.html — Stock personality profiles
- brain.html — Trading brain insights
- signals.html — Composite signal matrix (30m + 1D)
- assistant.html — AI assistant surface
- calendar.html — Calendar + tasks + shift schedule
- reviews.html — Signal Review Engine dashboard
- strategies.html — FP-Growth mined strategies
- fractal_report.html — Static backtest report (Fractal v3)

### Workflow: Discover (radar) → Analyze (analysis/news) → Execute (positions) → Review (journal)

## Telegram Commands
- /report — morning report (weather + shift + HA status)
- /فرص — current golden opportunities
- /تقييم — yesterday signal review
- /موجة — momentum alerts (strong-moving stocks)
- /brain — trading brain status
- /أخبار — news (بورصة/اقتصاد/عالمي/تقنية)
- /تحليل SYMBOL — Gemini deep technical analysis

## Shift Schedule
AABBCCDD rotation, epoch 2024-01-04
A=morning, B=afternoon, C=night, D=off
Unit 114 Hydrocracker, MAB Area 8, KNPC

## AI Consultant Tools
| Tool | Model | Script | Role | NOT for |
|------|-------|--------|------|---------|
| ChatGPT | GPT-5.4 + gpt-4o fallback | C:\Users\MS1\Temp\ask_chatgpt.py | HA + Bluesound + Network + Architecture | — |
| Gemini | 2.5 Flash + Pro fallback | C:\Users\MS1\Temp\ask_gemini.py | Research, news, docs, code review | Trading (hallucination risk) |

Both support: `--ha` (live HA states), `--file prompt.md`, `--context "text"` flags.
Gemini extra flags: `--pro` (force 2.5 Pro for complex questions), `--news` (Google Search grounding)
Logs: `~/chatgpt_logs/conversations.md`, `~/gemini_logs/conversations.md`
Telegram: `/chatgpt` (active), `/جيمني` (pending — plan in `_tools/ADD_GEMINI_CONSULTANT.md`)

## News Engine (news_engine.py)
**2 data sources, 5 sections, 7 Boursa sub-categories:**
- **Boursa Kuwait RSS** (every 5m, FREE): 3 feeds parsed → 7 sub-categories
  - نتائج مالية (T=9), توزيعات (T=4,5,20), مجلس إدارة (T=7,8,10-15), جمعيات (T=1-3,19,21,22), إفصاحات جوهرية (T=23-25,34-36), مطلعين (T=6), أخرى
- **Gemini + Google Search** (every 30m): economy, world, tech/AI news
- **Priority scoring 1-5:** Financial results/material info=5(urgent), dividends/board results=4, AGM=3, date changes=2, other=1
- **DB:** `news_items` table in `data/life.db` with dedup by headline hash
- **Endpoints:** GET `/api/news`, POST `/api/news/refresh-boursa`, POST `/api/news/refresh-gemini`
- **Schedulers:** Boursa 5m, Gemini 30m, cleanup daily midnight (7-day retention)
- **Telegram:** Priority 5 items trigger notification
- **Dashboard:** `www/trading/news.html` — 5 main tabs + 7 Boursa sub-tabs, priority-based card styling

## Key Credentials Location
- HA token: ~/.ha_token
- Master AI key: ~/.master_ai_key
- OpenAI key: ~/.openai_key (on PC)
- Gemini key: ~/.gemini_key (on PC, pending RPi)
- Bridge runs on PC 192.168.111.158:8059
- RPi SSH: pi@192.168.109.123
- Master AI tunnel: https://ai.salem-home.com


## Live Status (Updated 2026-04-02)
- Feature Flags: 10 (9 enabled, 1 env override)
- KAIROS: running, checks every 5min
- Service Health: 7 services monitored
- Telegram Queue: active
- Context Compaction: active (triggers at 12+ messages)
- Hooks: 10 event types registered, 3 handlers (service_down, service_up, flag_toggled)
- Tool Registry: 12 tools in 4 categories (home, system, trading, news)
- Trading Integration: Layer 1 complete (degraded mode), Layers 2+4 pending
- Plugins: 9
- Dashboard: system.html updated with health + KAIROS + flags sections
- Errors fixed: Gmail OAuth renewed, TG parse mode switched to plain text
