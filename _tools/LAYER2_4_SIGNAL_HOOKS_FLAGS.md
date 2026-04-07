# Layer 2 + Layer 4: Signal Hooks + Trading Feature Flags
# Status: READY FOR EXECUTION
# Executor: Claude Code
# Date: 2026-04-02
# Depends on: Layer 1 (DONE — commit 182bd75), Phase 6 hooks+tools (DONE — commit c34876b)
# Verified: hooks.py has 10 events, feature_flags.py has 10 flags, stock_radar.py unmodified

---

## Overview

Layer 2: Fire trading hooks from stock_radar.py so other systems can react to signals.
Layer 4: Add 5 trading feature flags and wire radar_enabled + daily_refresh into stock_radar.py.

All changes are in 3 files: hooks.py, feature_flags.py, stock_radar.py
Plus 1 handler registration in server.py.

---

## FILE 1: hooks.py — Add 3 trading events to EVENTS list

### FIND (line ~22):
```python
    EVENTS = [
        "service_down",      # service went down (name, reason)
        "service_up",        # service recovered (name)
        "alert_sent",        # KAIROS sent an alert (msg)
        "tg_message_in",     # Telegram message received (chat_id, text)
        "tg_message_out",    # Telegram message sent (chat_id, text)
        "flag_toggled",      # Feature flag changed (name, enabled)
        "llm_call_start",    # LLM call starting (model, prompt_len)
        "llm_call_end",      # LLM call finished (model, duration, tokens)
        "tool_executed",     # Tool was called (name, args, result_len)
        "daily_summary",     # Daily summary generated
    ]
```

### REPLACE WITH:
```python
    EVENTS = [
        "service_down",      # service went down (name, reason)
        "service_up",        # service recovered (name)
        "alert_sent",        # KAIROS sent an alert (msg)
        "tg_message_in",     # Telegram message received (chat_id, text)
        "tg_message_out",    # Telegram message sent (chat_id, text)
        "flag_toggled",      # Feature flag changed (name, enabled)
        "llm_call_start",    # LLM call starting (model, prompt_len)
        "llm_call_end",      # LLM call finished (model, duration, tokens)
        "tool_executed",     # Tool was called (name, args, result_len)
        "daily_summary",     # Daily summary generated
        # Trading events (Layer 2)
        "after_signal",      # Radar detected a new signal (symbol, signal_type, price, score)
        "before_trade_alert",# Before sending trade alert to TG (symbol, action, confidence)
        "after_daily_refresh",# Daily snapshot refreshed (ok_count, err_count)
    ]
```

---

## FILE 2: feature_flags.py — Add 5 trading flags to _SEED_FLAGS

### FIND (line ~13):
```python
_SEED_FLAGS = [
    ("circuit_breakers", 1, "Circuit breakers for external calls"),
    ("timeouts", 1, "Request timeouts"),
    ("speed_templates", 1, "Speed engine templates"),
    ("smart_router_v2", 1, "Smart intent router v2"),
    ("entity_health", 1, "Entity health monitoring"),
    ("kairos", 0, "Background health agent (Phase 3)"),
    ("telegram_queue", 0, "Offline message buffer (Phase 4)"),
    ("chat_compaction", 0, "Chat context compression (Phase 5)"),
    ("hooks", 0, "Event hook system (Phase 6)"),
    ("tool_registry", 0, "Central tool catalog (Phase 6)"),
]
```

### REPLACE WITH:
```python
_SEED_FLAGS = [
    ("circuit_breakers", 1, "Circuit breakers for external calls"),
    ("timeouts", 1, "Request timeouts"),
    ("speed_templates", 1, "Speed engine templates"),
    ("smart_router_v2", 1, "Smart intent router v2"),
    ("entity_health", 1, "Entity health monitoring"),
    ("kairos", 0, "Background health agent (Phase 3)"),
    ("telegram_queue", 0, "Offline message buffer (Phase 4)"),
    ("chat_compaction", 0, "Chat context compression (Phase 5)"),
    ("hooks", 0, "Event hook system (Phase 6)"),
    ("tool_registry", 0, "Central tool catalog (Phase 6)"),
    # Trading feature flags (Layer 4)
    ("radar_enabled", 1, "Stock radar 128-stock monitoring"),
    ("momentum_alerts", 1, "Strong-moving stock alerts"),
    ("golden_engine", 1, "Golden opportunities matching"),
    ("position_monitor", 1, "Position auto-monitoring"),
    ("daily_refresh", 1, "Daily snapshot auto-refresh"),
]
```

NOTE: _SEED_FLAGS uses INSERT OR IGNORE — existing 10 flags untouched.
The 5 new flags seed as enabled (1) on next restart.

---

## FILE 3: stock_radar.py — 5 changes in radar_loop + refresh_daily_snapshot

### Change 3A: Check radar_enabled feature flag at top of while loop

FIND in radar_loop() (inside `while True:`, before config check):
```python
            cfg = _get_config()
            if not cfg.get("enabled", True):
                await asyncio.sleep(300)
                continue
```

REPLACE WITH:
```python
            # Feature flag check (DB-backed, no restart needed)
            try:
                from feature_flags import FeatureFlags
                _ff = FeatureFlags("data/life.db")
                if not _ff.is_enabled("radar_enabled"):
                    logger.info("Radar disabled by feature flag")
                    await asyncio.sleep(300)
                    continue
            except Exception:
                pass
            cfg = _get_config()
            if not cfg.get("enabled", True):
                await asyncio.sleep(300)
                continue
```

### Change 3B: Check daily_refresh flag before daily snapshot refresh

FIND in radar_loop():
```python
            if not _daily_snapshot_is_fresh():
                try:
                    logger.info("Refreshing daily snapshot (stale or missing)...")
```

REPLACE WITH:
```python
            _do_daily = True
            try:
                from feature_flags import FeatureFlags
                _ff2 = FeatureFlags("data/life.db")
                _do_daily = _ff2.is_enabled("daily_refresh")
            except Exception:
                pass
            if _do_daily and not _daily_snapshot_is_fresh():
                try:
                    logger.info("Refreshing daily snapshot (stale or missing)...")
```

### Change 3C: Fire after_signal hook after _record_signal

FIND in radar_loop():
```python
                        _record_signal(sym, signal, result["candle_time"],
                                       result["price"], result["ema_fast"], result["ema_slow"],
                                       enriched=result)
                        msg = _format_alert(sym, signal, result["price"],
```

REPLACE WITH:
```python
                        _record_signal(sym, signal, result["candle_time"],
                                       result["price"], result["ema_fast"], result["ema_slow"],
                                       enriched=result)
                        # Fire after_signal hook (non-blocking)
                        try:
                            from service_health import get_health_hub
                            _hub = get_health_hub()
                            if _hub:
                                _hk = getattr(_hub, '_hooks', None)
                                if _hk:
                                    _hk.fire_sync("after_signal",
                                        symbol=sym, signal_type=signal,
                                        price=result["price"],
                                        score=result.get("score", 0),
                                        timeframe="30m")
                        except Exception:
                            pass
                        msg = _format_alert(sym, signal, result["price"],
```

### Change 3D: Fire before_trade_alert hook before send_fn (can block alert)

FIND in radar_loop():
```python
                        try:
                            _sig_meta = {
                                "symbol": sym, "signal": signal,
                                "price": result["price"],
                                "score": result.get("score", 0),
                                "score_class": result.get("score_class", ""),
                                "rsi": result.get("rsi"),
                                "vol_ratio": result.get("vol_ratio", 0),
                                "source": "radar",
                            }
                            await send_fn(msg, _sig_meta)
                            logger.info(f"Radar alert sent: {sym} {signal}")
```

REPLACE WITH:
```python
                        try:
                            _sig_meta = {
                                "symbol": sym, "signal": signal,
                                "price": result["price"],
                                "score": result.get("score", 0),
                                "score_class": result.get("score_class", ""),
                                "rsi": result.get("rsi"),
                                "vol_ratio": result.get("vol_ratio", 0),
                                "source": "radar",
                            }
                            # before_trade_alert hook — can block the alert
                            _skip_alert = False
                            try:
                                from service_health import get_health_hub
                                _hub2 = get_health_hub()
                                if _hub2:
                                    _hk2 = getattr(_hub2, '_hooks', None)
                                    if _hk2:
                                        _hr = await _hk2.fire("before_trade_alert",
                                            symbol=sym, action=signal,
                                            confidence=result.get("score", 0))
                                        for _r in (_hr or []):
                                            if isinstance(_r, dict) and _r.get("skip"):
                                                _skip_alert = True
                                                logger.info("Hook blocked alert for %s: %s", sym, _r.get("reason", ""))
                                                break
                            except Exception:
                                pass
                            if _skip_alert:
                                continue
                            await send_fn(msg, _sig_meta)
                            logger.info(f"Radar alert sent: {sym} {signal}")
```

### Change 3E: Fire after_daily_refresh hook at end of refresh_daily_snapshot()

FIND at the end of refresh_daily_snapshot():
```python
        return {"ok": ok_count, "errors": err_count}
    finally:
        _daily_refresh_lock = False
```

REPLACE WITH:
```python
        # Fire after_daily_refresh hook
        try:
            from service_health import get_health_hub
            _hub = get_health_hub()
            if _hub:
                _hk = getattr(_hub, '_hooks', None)
                if _hk:
                    _hk.fire_sync("after_daily_refresh",
                        ok_count=ok_count, err_count=err_count)
        except Exception:
            pass
        return {"ok": ok_count, "errors": err_count}
    finally:
        _daily_refresh_lock = False
```

---

## FILE 4: server.py — Register market hours hook handler

FIND where hooks handlers are registered (search for `hooks.on(` — there should
be existing handler registrations from Phase 6). ADD nearby:

```python
# Trading hook: block alerts outside market hours
async def _hook_check_market_hours(**kwargs):
    """Block trade alerts outside KSE market hours."""
    try:
        from tv_data import _is_market_open
        if not _is_market_open():
            return {"skip": True, "reason": "Market closed"}
    except Exception:
        pass
    return {}

hooks.on("before_trade_alert", _hook_check_market_hours)
```

NOTE: `hooks` is the global HookRegistry instance. Verify the variable name
by searching server.py for `HookRegistry(` or existing `.on(` calls.

---

## Validation

```bash
cd /home/pi/master_ai

# 1. Syntax
python3 _tools/quick_check.py

# 2. Verify hooks events count
python3 -c "from hooks import HookRegistry; print('Events:', len(HookRegistry.EVENTS))"
# Expected: 13

# 3. Verify flags seed count
python3 -c "from feature_flags import _SEED_FLAGS; print('Flags:', len(_SEED_FLAGS))"
# Expected: 15

# 4. Smoke test
python3 _tools/smoke_test.py

# 5. Restart
bash _tools/restart_master_ai.sh

# 6. Verify flags in DB
sqlite3 data/life.db "SELECT name, enabled FROM feature_flags WHERE name IN ('radar_enabled','daily_refresh','momentum_alerts','golden_engine','position_monitor')"
# Expected: 5 rows, all enabled=1

# 7. Verify hooks API
curl -s http://localhost:9000/api/hooks/stats | python3 -c "
import sys,json; d=json.load(sys.stdin)
print('Events:', len(d['known_events']))
print('Has after_signal:', 'after_signal' in d['known_events'])
print('Handlers:', d['registered_handlers'])
"
# Expected: Events: 13, Has after_signal: True, Handlers includes before_trade_alert

# 8. Verify flags API
curl -s http://localhost:9000/api/flags | python3 -c "
import sys,json; d=json.load(sys.stdin)
print('Total:', len(d['flags']))
for f in d['flags']:
    if f['name'] in ('radar_enabled','daily_refresh'):
        print(f['name'], '=', f['enabled'])
"
# Expected: Total: 15, radar_enabled=True, daily_refresh=True
```

---

## Summary

| File | Change | Lines added |
|------|--------|-------------|
| hooks.py | 3 trading events in EVENTS list | +3 |
| feature_flags.py | 5 trading flags in _SEED_FLAGS | +5 |
| stock_radar.py | radar_enabled flag check | +7 |
| stock_radar.py | daily_refresh flag check | +5 |
| stock_radar.py | after_signal hook fire | +9 |
| stock_radar.py | before_trade_alert hook (can block) | +15 |
| stock_radar.py | after_daily_refresh hook | +8 |
| server.py | _hook_check_market_hours handler | +8 |

**Total: ~60 lines across 4 files**
**All additive, backward-compatible**
**Hooks gated by ff.is_enabled("hooks") — already ON**
