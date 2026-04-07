# Update CLAUDE_CONTEXT.md — All Layers Verified
# Status: READY FOR EXECUTION
# Executor: Claude Code
# Date: 2026-04-02
# Verified via live API: tools=12, flags=15, hooks=13, degraded=working

---

## Change 1: Feature Flags count (Quick Reference)
FIND:
```
- **Feature Flags:** 10 (DB-backed, API-toggleable, no restart needed)
```
REPLACE:
```
- **Feature Flags:** 15 (10 infrastructure + 5 trading, DB-backed, API-toggleable)
```

---

## Change 2: Tool Registry count (Quick Reference, after "Plugins:")
FIND wherever it says tools count is 4:
```
- Tool Registry: 4 tools in 3 categories
```
REPLACE:
```
- Tool Registry: 12 tools in 4 categories (home, system, trading, news)
```

---

## Change 3: Dashboard page count (Architecture line)
FIND:
```
Dashboard: 14 HTML iframe pages in HA via Cloudflare tunnel.
```
REPLACE:
```
Dashboard: 9 HTML iframe pages in HA via Cloudflare tunnel (7 core + 2 utility).
```

---

## Change 4: Phase 6 detail — update tool/hook counts
FIND:
```
- **Hooks:** 10 event types (service_down, service_up, alert_sent, flag_toggled, etc.)
```
REPLACE:
```
- **Hooks:** 13 event types (10 infrastructure + 3 trading: after_signal, before_trade_alert, after_daily_refresh)
```

FIND:
```
- **Tool Registry:** 4 tools registered across 3 categories (home, system, trading)
```
REPLACE:
```
- **Tool Registry:** 12 tools registered across 4 categories (home, system, trading, news)
```

---

## Change 5: Feature Flags Reference table — add 5 trading rows
FIND the table row:
```
| speed_templates | OFF (env) | Speed engine templates (env override) |
```
ADD AFTER that row:
```
| radar_enabled | ON | Stock radar 128-stock monitoring |
| momentum_alerts | ON | Strong-moving stock alerts |
| golden_engine | ON | Golden opportunities matching |
| position_monitor | ON | Position auto-monitoring |
| daily_refresh | ON | Daily snapshot auto-refresh |
```

---

## Change 6: Add Trading Integration section
ADD AFTER the "### Phase 6: Hooks + Tool Registry" section (after its last line about commits):

```
### Trading Engines Integration (Layers 1-4, 2026-04-02)
Connected the trading pipeline to the 6 infrastructure modules.

**Layer 1: Degraded Mode (commit 182bd75)**
- bridge_client.py reports to service_health on every request (mark_up/mark_down)
- dashboard_api.py returns `degraded: true` + `degraded_reason` when Bridge is down
- stock_radar.py radar_loop skips cycles (300s sleep) when Bridge is down
- Frontend degraded banners on home.html, radar.html, positions.html

**Layer 2: Signal Hooks (commit f8980a3)**
- stock_radar fires `after_signal` after every new EMA cross signal
- stock_radar fires `before_trade_alert` before Telegram alerts — handlers can return `{skip: true}` to block
- stock_radar fires `after_daily_refresh` after daily snapshot completes
- Default handler: `_hook_check_market_hours` blocks alerts outside KSE hours

**Layer 3: Trading Tools (commit 8bc3e6c)**
- 3 trading tools: bridge_status, open_trades, trade_stats
- 2 news tools: news_feed, news_counts
- Total registry: 12 tools in 4 categories, health-aware execution

**Layer 4: Trading Feature Flags (commit f8980a3)**
- 5 new flags: radar_enabled, momentum_alerts, golden_engine, position_monitor, daily_refresh
- radar_loop checks `radar_enabled` before each cycle (no restart needed to disable)
- radar_loop checks `daily_refresh` before daily snapshot refresh
- Total: 15 feature flags (10 infra + 5 trading)
```

---

## Change 7: Dashboard Pages section — full rewrite
FIND the entire section starting with `## Dashboard Pages` through its end (before the next `##` section).
REPLACE the whole section with:

```
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
```

---

## Change 8: Live Status section — update counts
FIND:
```
- Hooks: 10 event types registered
- Tool Registry: 4 tools in 3 categories
```
REPLACE:
```
- Hooks: 13 event types, 4 handlers (service_down, service_up, flag_toggled, before_trade_alert)
- Tool Registry: 12 tools in 4 categories (home, system, trading, news)
- Feature Flags: 15 (10 infra + 5 trading), all enabled except speed_templates
- Trading Integration: Layers 1-4 complete (degraded + hooks + tools + flags)
```

---

## Validation
```bash
cd /home/pi/master_ai

# Check all changes applied:
grep "15" CLAUDE_CONTEXT.md | grep -i flag
grep "12 tools" CLAUDE_CONTEXT.md
grep "13 event" CLAUDE_CONTEXT.md
grep "9 HTML" CLAUDE_CONTEXT.md
grep "after_signal" CLAUDE_CONTEXT.md
grep "radar_enabled" CLAUDE_CONTEXT.md
grep "reviews.html" CLAUDE_CONTEXT.md
grep "Layer 1" CLAUDE_CONTEXT.md

# Restart to reload context:
bash _tools/restart_master_ai.sh

# Verify via API:
curl -s https://ai.salem-home.com/dev/context | grep -c "12 tools"
```

---

## Summary — 8 changes, all verified

| # | What | Before | After |
|---|------|--------|-------|
| 1 | Feature Flags count | 10 | 15 |
| 2 | Tool Registry count | 4 in 3 cats | 12 in 4 cats |
| 3 | Dashboard page count | 14 | 9 |
| 4 | Hook events + tools detail | 10 events, 4 tools | 13 events, 12 tools |
| 5 | Flags reference table | 10 rows | 15 rows (+5 trading) |
| 6 | NEW: Trading Integration section | — | Layers 1-4 documented |
| 7 | Dashboard Pages section | outdated | 7 core + 2 utility + 10 archived |
| 8 | Live Status | old counts | current verified counts |
