# Layer 1: Degraded Mode — Bridge Health → Trading Engines
# Status: READY FOR EXECUTION
# Executor: Claude Code
# Date: 2026-04-02
# Depends on: service_health.py (DONE)

---

## Overview

Wire `service_health` into `bridge_client.py`, `dashboard_api.py`, and `stock_radar.py` so that:
1. Bridge reports its status to service_health on every request
2. Dashboard endpoints return `degraded` + `degraded_reason` when Bridge is down
3. Radar loop skips cycles with longer sleep when Bridge is down
4. Frontend shows yellow banners (claude.ai does this part)

---

## File 1: bridge_client.py — Report to service_health

### What to change:
Add optional `health_hub` parameter to `BridgeClient.__init__()`, and call `mark_up` / `mark_down` on every successful/failed request.

### Exact changes:

**1a.** In `__init__`, add `health_hub` parameter:

```python
# FIND:
    def __init__(self, base_url: str = BRIDGE_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._cache: dict[str, dict] = {}  # key -> {data, ts}
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._online = False
        self._last_success = None
        self._client: Optional[httpx.AsyncClient] = None

# REPLACE WITH:
    def __init__(self, base_url: str = BRIDGE_BASE_URL, health_hub=None):
        self.base_url = base_url.rstrip("/")
        self._cache: dict[str, dict] = {}  # key -> {data, ts}
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._online = False
        self._last_success = None
        self._client: Optional[httpx.AsyncClient] = None
        self._health_hub = health_hub
```

**1b.** In `_request`, after the success path (after `self._last_success = time.time()`), add health report:

```python
# FIND (in _request, success block):
            self._failure_count = 0
            self._online = True
            self._last_success = time.time()
            return data

# REPLACE WITH:
            self._failure_count = 0
            self._online = True
            self._last_success = time.time()
            if self._health_hub:
                self._health_hub.mark_up("bridge", details={"cached_symbols": len(self._cache)})
            return data
```

**1c.** In `_request`, in the failure block where `self._online = False`, add:

```python
# FIND (in _request, failure block):
            if self._failure_count == MAX_FAILURES:
                self._online = False
                logger.warning("Bridge offline after %d failures: %s", MAX_FAILURES, e)

# REPLACE WITH:
            if self._failure_count == MAX_FAILURES:
                self._online = False
                logger.warning("Bridge offline after %d failures: %s", MAX_FAILURES, e)
                if self._health_hub:
                    self._health_hub.mark_down("bridge", reason=f"offline after {MAX_FAILURES} failures: {e}")
```

**1d.** In `_is_circuit_open`, when cooldown expires and failures reset, also mark up:

```python
# FIND:
            # Cooldown expired, allow retry
            self._failure_count = 0

# REPLACE WITH:
            # Cooldown expired, allow retry
            self._failure_count = 0
            if self._health_hub:
                self._health_hub.mark_up("bridge", details={"circuit_reset": True})
```

---

## File 2: server.py — Wire health_hub into BridgeClient

### What to change:
When BridgeClient is instantiated in server.py, pass the health_hub.

### Find the BridgeClient instantiation:
Search for something like `BridgeClient()` or `bridge_client = BridgeClient` in server.py.
Add `health_hub=health_hub` to the constructor call.

Example:
```python
# BEFORE:
bridge = BridgeClient()

# AFTER:
bridge = BridgeClient(health_hub=health_hub)
```

NOTE: If the health_hub is created later, you may need to use a setter:
```python
bridge._health_hub = health_hub  # set after health_hub is created
```

Search server.py for `ServiceHealthHub` and `BridgeClient` to find the right place.

---

## File 3: dashboard_api.py — Degraded mode for Bridge-dependent endpoints

### What to change:
Add a helper function that checks Bridge health and returns degraded info.
Use it in endpoints that depend on Bridge data.

### 3a. Add helper at top of file (after imports):

```python
# ADD after the existing imports:

def _check_bridge_health():
    """Check if Bridge is available via service_health. Returns (is_up, degraded_info)."""
    try:
        from service_health import get_health_hub
        hub = get_health_hub()
        if hub and not hub.is_up("bridge"):
            svc = hub._services.get("bridge")
            return False, {
                "degraded": True,
                "degraded_reason": f"Bridge offline: {svc.reason if svc else 'unknown'}",
                "data_source": "cache",
            }
    except Exception:
        pass
    return True, {}
```

### 3b. Add `get_health_hub` singleton accessor to service_health.py:

**IMPORTANT**: First check if `get_health_hub()` already exists in service_health.py.
If NOT, add this at the bottom of service_health.py:

```python
# Singleton accessor
_health_hub_instance: ServiceHealthHub = None

def get_health_hub() -> ServiceHealthHub:
    return _health_hub_instance

def set_health_hub(hub: ServiceHealthHub):
    global _health_hub_instance
    _health_hub_instance = hub
```

Then in server.py where `ServiceHealthHub()` is created, also call:
```python
from service_health import set_health_hub
set_health_hub(health_hub)
```

### 3c. Modify `/dashboard` endpoint:

In `ha_dashboard()`, find where `data["degraded_mode"] = "normal"` is set.
Replace with:

```python
# FIND:
    data["degraded_mode"] = "normal"

# REPLACE WITH:
    bridge_up, bridge_degraded = _check_bridge_health()
    if not bridge_up:
        data["degraded_mode"] = "bridge_offline"
        data["degraded_info"] = bridge_degraded
    else:
        data["degraded_mode"] = "normal"
```

### 3d. Modify `/dashboard/radar` endpoint:

At the very beginning of `ha_dashboard_radar()`, add degraded check:

```python
# FIND (beginning of ha_dashboard_radar):
    """Dedicated radar data for HA radar sensor -- lightweight, read-only from DB."""
    import sqlite3
    from datetime import date as _d
    data = {}

# REPLACE WITH:
    """Dedicated radar data for HA radar sensor -- lightweight, read-only from DB."""
    import sqlite3
    from datetime import date as _d
    data = {}
    bridge_up, bridge_degraded = _check_bridge_health()
    if bridge_degraded:
        data.update(bridge_degraded)
```

### 3e. Modify `/dashboard/portfolio` endpoint:

At the beginning of `ha_dashboard_portfolio()`, add:

```python
# FIND (beginning of ha_dashboard_portfolio):
    """Portfolio data for HA dashboard — open positions, closed trades, stats."""
    data = {}

# REPLACE WITH:
    """Portfolio data for HA dashboard — open positions, closed trades, stats."""
    data = {}
    bridge_up, bridge_degraded = _check_bridge_health()
    if bridge_degraded:
        data.update(bridge_degraded)
```

---

## File 4: stock_radar.py — Skip cycles when Bridge is down

### What to change:
In `radar_loop()`, check Bridge health before the watchlist scan.

```python
# FIND (in radar_loop, after market hours check, before watchlist):
            watchlist = get_watchlist()

# ADD BEFORE THAT LINE:
            # Service health: skip cycle if Bridge is down
            try:
                from service_health import get_health_hub
                _hub = get_health_hub()
                if _hub and not _hub.is_up("bridge"):
                    logger.warning("Bridge down (service_health), skipping radar cycle — waiting 300s")
                    await asyncio.sleep(300)
                    continue
            except Exception:
                pass

            watchlist = get_watchlist()
```

---

## Validation Steps

After all changes:

```bash
cd /home/pi/master_ai
python3 _tools/quick_check.py
python3 _tools/smoke_test.py

# Test degraded mode:
# 1. Stop Bridge on PC (close the terminal)
# 2. Wait for circuit breaker to trip (15 failures)
# 3. curl http://localhost:9000/dashboard | jq '.degraded_mode'
#    Expected: "bridge_offline"
# 4. curl http://localhost:9000/dashboard/radar | jq '.degraded'
#    Expected: true
# 5. Check logs: journalctl -u master-ai -n 50 --no-pager | grep "Bridge down"
#    Expected: "Bridge down (service_health), skipping radar cycle"

# Restart:
bash _tools/restart_master_ai.sh
```

---

## Summary of Changes

| File | Change | Lines |
|------|--------|-------|
| bridge_client.py | Add health_hub reporting on connect/disconnect | ~10 |
| service_health.py | Add get_health_hub/set_health_hub singleton | ~8 |
| server.py | Wire health_hub into BridgeClient + call set_health_hub | ~3 |
| dashboard_api.py | Add _check_bridge_health() helper | ~12 |
| dashboard_api.py | /dashboard degraded_mode from health check | ~5 |
| dashboard_api.py | /dashboard/radar degraded flag | ~3 |
| dashboard_api.py | /dashboard/portfolio degraded flag | ~3 |
| stock_radar.py | radar_loop skip when Bridge down | ~7 |

**Total: ~51 lines added/changed across 4 files**
**All changes are minimal and backward-compatible**
**No existing endpoints break — degraded fields are ADDITIVE**
