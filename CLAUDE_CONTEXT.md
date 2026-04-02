# CLAUDE_CONTEXT.md — Master AI v9.0.0
# Last Updated: 2026-04-03
# مصدر الحقيقة الأول: GET /system/context

## Quick Reference
- **Version:** v9.0.0 | **Schema:** 3.4.0
- **Port:** 9000 | **Tunnel:** https://ai.salem-home.com
- **Git:** main | **~650 commits**
- **DB:** data/life.db | **~48 tables** (session_summaries added)
- **Autonomy:** Level 3 | Policy: auto ≤30, approval ≤60, block ≥61
- **Feature Flags:** 15 (10 infrastructure + 5 trading, DB-backed)
- **New Modules (Apr 2-3):** 14 new files from Claude Code Source Analysis

## Architecture
RPi5 + FastAPI (server.py) + systemd service.
Bridge API on Windows PC (192.168.111.158:8059) — TradingView WebSocket data.
Dashboard: 9 HTML iframe pages in HA via Cloudflare tunnel.
**HTML live path:** `share/master_ai/www/trading/` (served by FastAPI). `config/www/trading/` was DELETED.

---

## Claude Code Source Analysis — 20 Patterns (Apr 2-3, 2026)

Extracted 21 architectural patterns from Claude Code leaked source (~10K lines, 16 files).
20 implemented across 3 tiers. 14 new Python modules + dashboard updates.
Full analysis: `_tools/CLAUDE_CODE_SOURCE_ANALYSIS_P1_P2.md` (1584 lines).
Plans: `_tools/TIER2_STRUCTURED_IMPROVEMENTS_PLAN.md`, `_tools/TIER3_ARCHITECTURE_PLAN.md`

### New Modules Created (14 files):
| Module | Purpose |
|--------|---------|
| circuit_breaker.py | Stop retrying after N failures (reusable) |
| processing_cursor.py | Incremental processing with cursor tracking |
| tool_registry.py | 3-layer validation (validate→permission→execute) |
| task_manager.py | TaskManager singleton for background ops tracking |
| memory_recall.py | Haiku-powered observation selection from manifest |
| master_ai_tool.py | Tool definitions with autonomy flags + pre-flight |
| coalesced_executor.py | Prevents overlapping background operations |
| session_memory.py | Conversation-level summaries after exchanges |
| memory_prefetch.py | Parallel Brain lookup before intent routing |
| auto_memory_extractor.py | Auto-extract observations from conversations |
| parallel_coordinator.py | Run independent analyses concurrently |
| context_manager.py | 4-layer context compaction (trim→compress→summarize→emergency) |
| intent_state_machine.py | State machine for intent routing with audit |

### Modified Existing Files:
- brain_core.py: staleness warnings, memory manifest, observation scope
- server.py: progress indicators, cleanup blocks, cron routing
- stock_radar.py: finally blocks, coalesced execution
- news_engine.py: per-source circuit breakers
- dashboard_api.py: /api/tasks endpoint
- system.html: Live Tasks Panel + Circuit Breaker status
- home.html: Health Pulse Bar (Bridge/Radar/News/Tasks)

### Key Patterns Explained:
1. **Circuit Breaker** — stops retrying failing operations after 3 failures, cooldown period, auto-reset on success
2. **Memory Staleness** — observations >1 day old get warning: "⚠️ N days ago — verify before acting"
3. **Task Manager** — PENDING→RUNNING→COMPLETED/FAILED lifecycle, /api/tasks endpoint
4. **LLM-Ranked Recall** — Haiku selects top 5 relevant Brain observations per query
5. **Background Memory Extraction** — auto-extracts observations from conversations (fire-and-forget)
6. **Context Manager** — 4-layer compaction prevents token overflow in long conversations
7. **3-Level Memory Scoping** — observations tagged: global/stock/device
8. **Coalesced Executor** — if operation running, stash new request, run trailing after

### DB Changes:
- brain_observations: added `scope` column (global/stock/device) + index
- session_summaries: new table for conversation tracking
- intent_audit: state machine audit trail

---

## Claude Code Patterns — Infrastructure (Added 2026-04-02)
6 phases, 7 files, 5 DB tables, ~15 endpoints. All feature-flagged.

### Phase 1-6 Summary:
- **Phase 1:** Feature Flags v2 (feature_flags.py, 15 flags, DB-backed)
- **Phase 2:** Service Health Hub (service_health.py, 7 services)
- **Phase 3:** KAIROS Background Agent (kairos.py, 5min checks, Telegram alerts)
- **Phase 4:** Telegram Queue (offline buffer, auto-flush on recovery)
- **Phase 5:** Chat Context Compaction (context_compactor.py, 4-stage pipeline)
- **Phase 6:** Hooks + Tool Registry (hooks.py 13 events, tool_registry.py 12 tools)

### Trading Integration Layers 1-4:
- **Layer 1:** Degraded mode — Bridge status → dashboard degraded banners
- **Layer 2:** Signal hooks — after_signal, before_trade_alert, after_daily_refresh
- **Layer 3:** Trading tools — bridge_status, open_trades, trade_stats, news tools
- **Layer 4:** Trading flags — radar_enabled, momentum_alerts, golden_engine, etc.

### Feature Flags (15):
circuit_breakers, timeouts, smart_router_v2, entity_health, kairos, telegram_queue, chat_compaction, hooks, tool_registry, speed_templates(OFF), radar_enabled, momentum_alerts, golden_engine, position_monitor, daily_refresh

---

## TradingView Bridge API
- **Location:** C:\Users\MS1\tradingview-bridge | Port 8059
- **Auth:** JWT via Chrome CDP (port 9222), TokenWatchdog auto-renews
- **Startup:** `start_bridge.bat` (Chrome debug + Bridge + watchdog)
- **Key Endpoints:** /analysis, /quote, /multi-analysis, /health, /token-status
- **Indicators:** rsi_14, macd, ema_9, ema_21, ema_50, ema_200, atr_14, bb, obv, vol_ratio, adx, stoch

## Core Files
| File | Role |
|------|------|
| server.py (~462K) | Main FastAPI + all endpoints |
| dashboard_api.py (~101K) | Dashboard data |
| chat_v7.py (~61K) | Direct LLM + Tool Use |
| stock_radar.py (~60K) | 128 KSE stock monitoring |
| tg_intent_router.py (~50K) | Telegram intent routing |
| quick_query.py (~50K) | Speed engine handlers |
| priority_engine.py (~50K) | Cross-domain ranking |
| brain_core.py (~34K) | Brain observations + manifest + staleness |
| golden_engine.py (~41K) | Golden opportunities matching |
| signal_review.py (~27K) | Daily signal review |
| bridge_client.py (~18K) | Bridge API client |
| news_engine.py (~18K) | Boursa RSS + Gemini news |
| journal_engine.py | Trade journal + P&L |
| position_engine.py | Position monitoring + alerts |
| stock_personality_engine.py | Per-stock profiles (128 profiles, 6400 patterns) |

## Trading Brain
- 66,937 signals, 63,620 evaluated, 22.1% hit rate
- Learning mode: bayesian_regime_aware
- Best indicator: Volume (1.15 weight, 65% hit)
- Worst: RSI (0.75, 25%)

## Dashboard (9 active + 10 archived)
**Core:** home, radar, analysis, positions, journal, news, system
**Utility:** home-control, email
**Archived:** scalper, decisions, personality, brain, signals, assistant, calendar, reviews, strategies, fractal_report

### Dashboard Updates (Apr 3):
- system.html: Live Tasks Panel (/api/tasks), Circuit Breaker status in service health, bug fix (is_available→status)
- home.html: Health Pulse Bar (Bridge 🟢/🔴 | Radar ✅/⚠️ | News | Tasks)

## News Engine
- Boursa RSS (5m) + Gemini Search (30m)
- 7 Boursa sub-categories, priority 1-5
- Priority 5 → Telegram notification

## Telegram Commands
/report /فرص /تقييم /موجة /brain /أخبار /تحليل /kairos /chatgpt

## Shift Schedule
AABBCCDD rotation, epoch 2024-01-04. Unit 114 Hydrocracker, KNPC.

## AI Consultants
| Tool | Model | Script | Best For |
|------|-------|--------|----------|
| ChatGPT | GPT-5.4 | ask_chatgpt.py --ha | HA + Network + Architecture |
| Gemini | 2.5 Flash/Pro | ask_gemini.py --ha/--pro/--news | Research, code, news (NOT trading) |

## Key Credentials
~/.ha_token, ~/.master_ai_key, ~/.openai_key (PC), ~/.gemini_key (PC)
Bridge: 192.168.111.158:8059 | RPi SSH: pi@192.168.109.123

## DC read_file Bug (Known Issue)
Desktop Commander v0.2.38 has a bug: `read_file` fails with EPERM on some UNC path files.
**Workaround:** `ssh -T pi@192.168.109.123 cat /path/to/file > C:\Users\MS1\Temp\file` then read from Temp.
`DC:write_file` works on UNC paths. After writing: `ssh chown -R pi:pi` on the files.

## Live Status (Updated 2026-04-03)
- 20/21 Claude Code patterns implemented (Tier1+2+3)
- 14 new Python modules + dashboard updates
- KAIROS running, 15 feature flags, 7 services monitored
- Trading: Layers 1-4 complete
- Circuit Breakers: active on Bridge, News RSS, LLM calls
- Auto Memory Extraction: active (learns from conversations)
- Context Manager: 4-layer compaction active
- Task Manager: /api/tasks endpoint live
- Session Memory: tracking conversation summaries
