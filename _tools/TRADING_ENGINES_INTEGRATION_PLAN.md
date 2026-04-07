# Integration Plan: Connect Trading Engines to New Infrastructure
# Date: 2026-04-02
# Status: Ready for next conversation
# Depends on: All 6 Claude Code Patterns phases (COMPLETE)
# Executor: Claude Code (Python changes) + claude.ai (HTML changes)

---

## Problem Statement

The 6 new infrastructure modules (feature_flags, service_health, kairos, 
context_compactor, hooks, tool_registry) are running but ISOLATED from the 
trading engines. The trading pipeline (stock_radar → signal_engine → 
golden_engine → trading_decision_engine → dashboard_api) has ZERO integration 
with the new infrastructure.

Current state:
- KAIROS monitors Bridge status but trading engines don't check it
- service_health tracks 7 services but dashboard_api doesn't use degraded mode
- hooks system has 10 event types but signal_engine doesn't fire any
- tool_registry has 4 tools but none are trading tools
- feature_flags exist but no trading feature uses them

## What Needs to Change (3 integration layers)

### Layer 1: Service Health → Trading Engines (degraded mode)
**Goal:** When Bridge is down, show clear "stale data" warnings instead of silent failures.

Files to modify:
- `dashboard_api.py` — Before any Bridge call, check service_health
- `stock_radar.py` — Check Bridge health before radar loop iteration
- `bridge_client.py` — Report to service_health on connect/disconnect

Logic:
```
# In dashboard_api.py (every endpoint that uses Bridge):
from service_health import get_health_hub
health = get_health_hub()

if not health.is_up("bridge"):
    return {
        "data": cached_data,  # return last known data
        "degraded": True,
        "degraded_reason": "Bridge offline",
        "data_age_minutes": age_in_minutes
    }
```

```
# In stock_radar.py radar_loop():
if not health.is_up("bridge"):
    logger.warning("Bridge down, skipping radar cycle")
    await asyncio.sleep(300)  # wait 5min instead of 90s
    continue
```

Dashboard HTML changes (claude.ai):
- radar.html: Show yellow banner "بيانات قديمة — البريدج غير متاح" when degraded=true
- positions.html: Show stale badge on prices
- home.html: Show degraded indicator

### Layer 2: Signal Engine → Hooks (event-driven)
**Goal:** Signal generation fires hooks so other systems can react.

Files to modify:
- `signal_engine.py` — Fire hooks after signal generation
- `hooks.py` — Register default handlers

Hook points to add:
```
# In signal_engine.py after generating a signal:
from hooks import get_hook_registry
hooks = get_hook_registry()

# After signal generated:
await hooks.fire("after_signal", {
    "symbol": symbol,
    "signal_type": signal_type,
    "confidence": confidence,
    "timeframe": timeframe,
    "price": price
})

# Before trade alert:
result = await hooks.fire("before_trade_alert", {
    "symbol": symbol,
    "action": "enter_now",
    "confidence": confidence
})
if result.get("skip"):
    logger.info(f"Hook blocked alert for {symbol}")
    return
```

Default handlers to register:
```
# In hooks.py or a new hooks_trading.py:

@hooks.on("after_signal")
async def log_signal_audit(data):
    """Log every signal to hook_log for audit trail."""
    pass  # just logging, already handled by hooks infrastructure

@hooks.on("before_trade_alert")
async def check_market_hours(data):
    """Block alerts outside market hours."""
    from life_work import is_market_open
    if not is_market_open():
        return {"skip": True, "reason": "Market closed"}
    return {}

@hooks.on("before_trade_alert")
async def check_risk_limits(data):
    """Block if at max positions."""
    # Check risk_engine limits
    pass
```

### Layer 3: Tool Registry → Trading Tools
**Goal:** Register trading capabilities as discoverable tools.

Tools to register in `tool_registry.py`:
```
# Trading tools (wrap existing functions):
- get_stock_quote: bridge_client.get_quote(symbol) 
  requires=["bridge"]
  
- get_radar_signals: dashboard_api /dashboard/signals
  requires=["bridge"]
  
- get_golden_opportunities: golden_engine
  requires=["bridge", "daily_snapshot"]
  
- get_portfolio_status: position_engine.get_portfolio()
  requires=[]
  
- get_journal_stats: journal_engine
  requires=[]
  
- get_stock_personality: stock_personality_engine
  requires=[]
  
- get_daily_context: dashboard_api radar_daily_context
  requires=["daily_snapshot"]
```

### Layer 4: Feature Flags for Trading Features
**Goal:** Toggle trading features without restart.

New flags to add:
```sql
INSERT OR IGNORE INTO feature_flags (name, enabled, description) VALUES
  ('radar_enabled', 1, 'Stock radar 128-stock monitoring'),
  ('momentum_alerts', 1, 'Strong-moving stock alerts'),
  ('golden_engine', 1, 'Golden opportunities matching'),
  ('position_monitor', 1, 'Position auto-monitoring'),
  ('daily_refresh', 1, 'Daily snapshot auto-refresh');
```

Usage in stock_radar.py:
```
if not ff.is_enabled("radar_enabled"):
    logger.info("Radar disabled by feature flag")
    return
```

---

## Implementation Order

| Step | What | Who | Effort |
|------|------|-----|--------|
| 1 | Layer 1: dashboard_api degraded mode | Claude Code | 2h |
| 2 | Layer 1: stock_radar Bridge health check | Claude Code | 30min |
| 3 | Layer 1: Dashboard HTML degraded banners | claude.ai | 1h |
| 4 | Layer 2: signal_engine hook points | Claude Code | 1h |
| 5 | Layer 2: Default trading handlers | Claude Code | 1h |
| 6 | Layer 3: Register trading tools | Claude Code | 1h |
| 7 | Layer 4: Trading feature flags | Claude Code | 30min |

## Files Summary

### Modified (Claude Code):
- dashboard_api.py — degraded mode responses
- stock_radar.py — health check + feature flag
- signal_engine.py — hook fire points
- bridge_client.py — health reporting
- hooks.py — trading handlers
- tool_registry.py — trading tools
- feature_flags (DB) — 5 new trading flags

### Modified (claude.ai):
- radar.html — degraded banner
- positions.html — stale price badge
- home.html — degraded indicator

## Validation

After each step:
```bash
quick_check.py
smoke_test.py
# Test degraded: stop Bridge, check radar returns cached + degraded flag
# Test hooks: generate signal, check hook_log
# Test tools: curl /api/tools — should show 10+ tools
# Test flags: toggle radar_enabled, verify radar stops/starts
```

## Success Criteria

1. Bridge down → radar shows "بيانات قديمة" banner (not empty/error)
2. Signal generated → appears in hook_log
3. Alert blocked outside market hours → hook log shows skip
4. /api/tools → lists all trading tools with availability
5. Toggle radar_enabled → radar stops/starts without restart
