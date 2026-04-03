# CLAUDE_CONTEXT.md — Master AI v9.0.0
# Last Updated: 2026-04-03 (FINAL — 21/21 patterns complete)
# مصدر الحقيقة الأول: GET /system/context

## Quick Reference
- **Version:** v9.0.0 | **Schema:** 3.4.0
- **Port:** 9000 | **Tunnel:** https://ai.salem-home.com
- **Git:** main | **~650 commits**
- **DB:** data/life.db | **~48 tables**
- **Autonomy:** Level 3 | Policy: auto ≤30, approval ≤60, block ≥61
- **Feature Flags:** 15 (10 infrastructure + 5 trading, DB-backed)
- **New Modules (Apr 2-3):** 15 new files from Claude Code Source Analysis

## Architecture
RPi5 + FastAPI (server.py) + systemd service.
Bridge API on Windows PC (192.168.111.158:8059) — TradingView WebSocket data.
Dashboard: 9 HTML iframe pages in HA via Cloudflare tunnel.
**HTML live path:** `share/master_ai/www/trading/` (served by FastAPI).
`config/www/trading/` was DELETED — do NOT recreate.

---

## Claude Code Source Analysis — 21/21 Patterns COMPLETE (Apr 2-3, 2026)

Extracted 21 architectural patterns from Claude Code leaked source (~10K lines, 16 files).
ALL 21 implemented. 15 new Python modules + 3 skills + dashboard updates.
Full analysis: `_tools/CLAUDE_CODE_SOURCE_ANALYSIS_P1_P2.md` (1584 lines).

### Tier 1 — Safety Nets (7 patterns)
| # | Pattern | File(s) | Commit |
|---|---------|---------|--------|
| 1+2 | Memory Staleness + Human-Readable Age | brain_core.py | 9b16934 |
| 3 | Circuit Breaker | circuit_breaker.py, news_engine.py | 837d04c |
| 4 | Progress After N Seconds | server.py | ca72129 |
| 5 | 3-Layer Validation | tool_registry.py | 6d03d28 |
| 6 | Comprehensive Cleanup (finally blocks) | server.py, stock_radar.py | 8037fed |
| 7 | Cursor-Based Processing | processing_cursor.py | e696655 |

### Tier 2 — Intelligence (7 patterns)
| # | Pattern | File(s) | Commit |
|---|---------|---------|--------|
| 8 | Task State Machine | task_manager.py | 82fc48b |
| 9 | Lightweight Memory Index | brain_core.py | d738bb4 |
| 10 | LLM-Ranked Memory Recall | memory_recall.py | 40ade39 |
| 11 | MasterAITool Class | master_ai_tool.py | f90a916 |
| 12 | Coalesced Executor | coalesced_executor.py | 6109002 |
| 13 | Cron Routing + Orphan Cleanup | server.py | 37a3214 |
| 14 | Session Summary | session_memory.py | e3fa111 |

### Tier 3 — Architecture (7 patterns)
| # | Pattern | File(s) | Commit |
|---|---------|---------|--------|
| 19 | 3-Level Memory Scoping | brain_core.py + DB migration | 748e984 |
| 21 | Memory Prefetch | memory_prefetch.py | 9e49d9d |
| 16 | Background Memory Extraction | auto_memory_extractor.py | f256979 |
| 18 | Coordinator-Worker Parallelism | parallel_coordinator.py | 856a998 |
| 15 | Multi-Layer Context Management | context_manager.py | 900230b |
| 17 | State Machine Query Loop | intent_state_machine.py | 87493b4 |
| 20 | Skill/Plugin System | skill_loader.py + skills/ | 49124ec |

### All 15 New Modules (import and use — don't reinvent):
| Module | Purpose | Key Usage |
|--------|---------|-----------|
| circuit_breaker.py | Stop retrying after N failures | `CircuitBreaker(max_failures=3)` |
| processing_cursor.py | Incremental processing tracking | `ProcessingCursor("engine_name")` |
| tool_registry.py | 3-layer validation for commands | validate → permission → execute |
| task_manager.py | Background ops lifecycle tracking | `TaskManager.instance().create_task()` |
| memory_recall.py | Haiku selects relevant observations | `await find_relevant_memories(query)` |
| master_ai_tool.py | Tool definitions with autonomy flags | `MasterAITool(requires_bridge=True)` |
| coalesced_executor.py | Prevent overlapping operations | `await executor.run(func)` |
| session_memory.py | Conversation-level summaries | `SessionTracker().add_message()` |
| memory_prefetch.py | Parallel Brain lookup | `MemoryPrefetcher(query)` |
| auto_memory_extractor.py | Auto-extract observations | `extractor.record_message()` |
| parallel_coordinator.py | Concurrent analysis tasks | `coord.add_worker(); await coord.run()` |
| context_manager.py | 4-layer context compaction | `await manage_context(messages)` |
| intent_state_machine.py | State machine for intent routing | `IntentContext(message_id, text)` |
| skill_loader.py | Load .md skill templates | `SkillLoader("skills/").get("name")` |

### Skills Directory (skills/):
- technical_analysis.md — Full KSE TA (RSI/MACD/EMA/Volume/ADX)
- morning_briefing.md — Daily briefing by shift type
- stock_comparison.md — Multi-stock side-by-side comparison

### Key brain_core.py Additions:
- `get_observation_manifest()` — lightweight headers for LLM ranking
- `format_observation_manifest()` — one-liner per observation
- `get_full_observations(ids)` — load full text for selected IDs
- `format_staleness_warning(timestamp)` — "⚠️ N days ago"
- `scope` column on brain_observations: global/stock/device

### DB Changes:
- brain_observations: `scope` column + index
- session_summaries: new table
- intent_audit: state machine logs

### Dashboard Updates:
**system.html** (11 sections):
- System Gauges (CPU/RAM/Temp/Disk)
- صحة الخدمات (7 services + circuit breaker status)
- المهام الجارية (live tasks from /api/tasks)
- التعلم التلقائي (/api/memory-extraction/stats)
- تحليل الأوامر (/api/intent-analytics)
- العقل (/api/brain/stats with scope breakdown)
- السياق (/api/context-health with 4-layer dots)
- الاستجابة (/api/latency-stats with breakdown bar)
- KAIROS status
- Feature Flags (15 toggles)
- تفاصيل (RAM/Disk/Load/Uptime)

**home.html**: Health Pulse Bar (Bridge/Radar/News/Tasks)

### API Endpoints Added:
- GET /api/tasks — live task tracking
- GET /api/memory-extraction/stats — auto-learning stats
- GET /api/intent-analytics — command analytics
- GET /api/brain/stats — observation stats by scope
- GET /api/context-health — context layer status
- GET /api/latency-stats — response latency breakdown
- GET /api/skills — list available skill templates

---

## Claude Code Patterns — Infrastructure (6 Phases, Apr 2)
- **Phase 1:** Feature Flags v2 (feature_flags.py, 15 flags, DB-backed, API-toggleable)
- **Phase 2:** Service Health Hub (service_health.py, 7 services)
- **Phase 3:** KAIROS Background Agent (kairos.py, 5min checks, TG alerts)
- **Phase 4:** Telegram Queue (offline buffer, auto-flush)
- **Phase 5:** Chat Context Compaction (context_compactor.py, 4-stage pipeline)
- **Phase 6:** Hooks + Tool Registry (hooks.py 13 events, tool_registry.py 12 tools)

### Trading Integration Layers 1-4:
- Layer 1: Degraded mode (Bridge → dashboard degraded banners)
- Layer 2: Signal hooks (after_signal, before_trade_alert, after_daily_refresh)
- Layer 3: Trading tools (bridge_status, open_trades, trade_stats)
- Layer 4: Trading flags (radar_enabled, momentum_alerts, golden_engine, etc.)

### Feature Flags (15):
circuit_breakers, timeouts, smart_router_v2, entity_health, kairos, telegram_queue, chat_compaction, hooks, tool_registry, speed_templates(OFF), radar_enabled, momentum_alerts, golden_engine, position_monitor, daily_refresh

---

## TradingView Bridge API
- **Location:** C:\Users\MS1\tradingview-bridge | Port 8059
- **Auth:** JWT via Chrome CDP (port 9222), TokenWatchdog auto-renews
- **Startup:** `start_bridge.bat`
- **Endpoints:** /analysis, /quote, /multi-analysis, /health, /token-status
- **Indicators:** rsi_14, macd, ema_9, ema_21, ema_50, ema_200, atr_14, bb, obv, vol_ratio, adx, stoch

## Core Files (top by size)
| File | Size | Role |
|------|------|------|
| server.py | ~462K | Main FastAPI + all endpoints |
| dashboard_api.py | ~101K | Dashboard data endpoints |
| chat_v7.py | ~61K | LLM + Tool Use |
| stock_radar.py | ~60K | 128 KSE stock monitoring |
| tg_intent_router.py | ~50K | Telegram intent routing |
| quick_query.py | ~50K | Speed engine handlers |
| brain_core.py | ~34K | Brain observations + manifest + staleness |

## Trading Brain
- 66,937 signals, 22.1% hit rate, bayesian_regime_aware
- Best: Volume (1.15, 65%) | Worst: RSI (0.75, 25%)
- Stock Personality: 128 profiles, 6,400 patterns

## Dashboard (9 active + 10 archived)
**Core:** home, radar, analysis, positions, journal, news, system
**Utility:** home-control, email
**Archived:** scalper, decisions, personality, brain, signals, assistant, calendar, reviews, strategies, fractal_report

## News Engine
- Boursa RSS (5m) + Gemini Search (30m), 7 sub-categories, priority 1-5

## Telegram Commands
/report /فرص /تقييم /موجة /brain /أخبار /تحليل /kairos /chatgpt

## Shift Schedule
AABBCCDD rotation, epoch 2024-01-04. Unit 114 Hydrocracker, KNPC.

## AI Consultants
- ChatGPT: GPT-5.4, ask_chatgpt.py --ha (HA + Network)
- Gemini: 2.5 Flash/Pro, ask_gemini.py --ha/--pro/--news (NOT trading)

## Credentials
~/.ha_token, ~/.master_ai_key, ~/.openai_key (PC), ~/.gemini_key (PC)
Bridge: 192.168.111.158:8059 | RPi SSH: pi@192.168.109.123

## DC read_file Bug (Known Issue — DC v0.2.38)
Desktop Commander read_file fails with EPERM on some UNC path files.
Node.js fs.realpathSync works fine — it's a DC-specific bug.
**Workaround:**
- READ: `ssh -T pi@192.168.109.123 cat /path/file > C:\Users\MS1\Temp\file` then DC read_file from Temp
- WRITE: `scp C:\Users\MS1\Temp\file pi@192.168.109.123:/path/file`
- DC write_file on UNC works for NON-HTML files
- After writing: `ssh chown pi:pi` on written files

## Plans on Disk
- `_tools/CLAUDE_CODE_SOURCE_ANALYSIS_PLAN.md` — final status (21/21)
- `_tools/CLAUDE_CODE_SOURCE_ANALYSIS_P1_P2.md` — full analysis (1584 lines)
- `_tools/TIER2_STRUCTURED_IMPROVEMENTS_PLAN.md` — Tier 2 details
- `_tools/TIER3_ARCHITECTURE_PLAN.md` — Tier 3 details
- `_tools/DASHBOARD_UPDATES_PLAN.md` — dashboard plan
- `_tools/DASHBOARD_TIER3_ENHANCEMENTS.md` — Tier 3 dashboard enhancements
- `_tools/PATTERN20_SKILL_SYSTEM.md` — skill/plugin system

## Live Status (Updated 2026-04-03)
- 21/21 Claude Code patterns implemented (ALL tiers complete)
- 15 new Python modules + 3 skill templates + 7 API endpoints
- Dashboard system.html: 11 sections (5 new for Tier 3)
- KAIROS running, Circuit Breakers active, Auto Memory Extraction active
- Context Manager: 4-layer compaction ready
- Session Memory: tracking conversation summaries
- Task Manager: /api/tasks endpoint live
- Skill System: 3 skills loaded from skills/ directory


## Round 2 — 3 New Modules (Apr 3, 2026)
Source: Claude Code services/autoDream, tips, toolUseSummary analysis.
Full analysis: _tools/CLAUDE_CODE_SOURCE_ANALYSIS_ROUND2.md

### dream_consolidator.py (190 lines)
- Nightly Brain cleanup at 3 AM KWT
- Gate chain: min count > exact duplicates > stale archives
- Archives before deleting, keeps 2+ per category
- TG: /dream (status), /dream run (manual)
- API: GET /dream/status, POST /dream/run

### tips_engine.py (140 lines)
- 11 context-aware Arabic tips, max 1 per session
- Selection: relevant > cooldown > least-recently-shown
- Context-aware: bridge offline warning, message count
- API: GET /tips

### tool_summary.py (80 lines)
- Gemini Flash summary for long responses (>500 chars)
- Prepends summary before long TG response

### Round 2 Fixes Applied:
- TG 400 Bad Request: tg_send() catches HTTP 400, strips HTML, retries plain text
- news_engine: 6 missing functions added, /api/news returns 50 items
- /api/analyze endpoint: added routing to stock_analyzer

### Audit: 67/68 = 99% (full_audit.py)
- Module Imports 14/14, Integration Wiring 14/14, API Endpoints 13/14
- Database Tables 12/12, Skills 2/2, Dashboard HTML 12/12
