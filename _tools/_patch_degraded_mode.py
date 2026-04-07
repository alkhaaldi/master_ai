"""Layer 1: Degraded Mode — Bridge Health → Trading Engines"""
import sys, os, shutil

changes = 0

def patch_file(filename, old, new, label):
    global changes
    with open(filename, "r") as f:
        content = f.read()
    if old not in content:
        print(f"  SKIP {label}: pattern not found in {filename}")
        return content
    content = content.replace(old, new, 1)
    print(f"  OK {label}")
    changes += 1
    return content

def save_file(filename, content):
    with open(f"/tmp/_patch_{os.path.basename(filename)}", "w") as f:
        f.write(content)
    os.remove(filename)
    shutil.move(f"/tmp/_patch_{os.path.basename(filename)}", filename)

# ═══ 1. bridge_client.py ═══
print("=== bridge_client.py ===")
with open("bridge_client.py", "r") as f:
    bc = f.read()

# 1a. Add health_hub to __init__
bc = patch_file.__wrapped__(bc) if False else bc  # dummy
old = """    def __init__(self, base_url: str = BRIDGE_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._cache: dict[str, dict] = {}  # key -> {data, ts}
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._online = False
        self._last_success = None
        self._client: Optional[httpx.AsyncClient] = None"""
new = """    def __init__(self, base_url: str = BRIDGE_BASE_URL, health_hub=None):
        self.base_url = base_url.rstrip("/")
        self._cache: dict[str, dict] = {}  # key -> {data, ts}
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._online = False
        self._last_success = None
        self._client: Optional[httpx.AsyncClient] = None
        self._health_hub = health_hub"""
if "_health_hub" not in bc:
    bc = bc.replace(old, new, 1)
    print("  1a. Added health_hub param")
    changes += 1
else:
    print("  1a. SKIP already exists")

# 1b. Success path
old = """            self._failure_count = 0
            self._online = True
            self._last_success = time.time()
            return data"""
new = """            self._failure_count = 0
            self._online = True
            self._last_success = time.time()
            if self._health_hub:
                self._health_hub.mark_up("bridge", details={"cached_symbols": len(self._cache)})
            return data"""
if 'mark_up("bridge"' not in bc:
    bc = bc.replace(old, new, 1)
    print("  1b. Added mark_up on success")
    changes += 1
else:
    print("  1b. SKIP already exists")

# 1c. Failure path
old = """            if self._failure_count == MAX_FAILURES:
                self._online = False
                logger.warning("Bridge offline after %d failures: %s", MAX_FAILURES, e)"""
new = """            if self._failure_count == MAX_FAILURES:
                self._online = False
                logger.warning("Bridge offline after %d failures: %s", MAX_FAILURES, e)
                if self._health_hub:
                    self._health_hub.mark_down("bridge", reason=f"offline after {MAX_FAILURES} failures: {e}")"""
if 'mark_down("bridge"' not in bc:
    bc = bc.replace(old, new, 1)
    print("  1c. Added mark_down on failure")
    changes += 1
else:
    print("  1c. SKIP already exists")

# 1d. Circuit reset
old = """            # Cooldown expired, allow retry
            self._failure_count = 0"""
new = """            # Cooldown expired, allow retry
            self._failure_count = 0
            if self._health_hub:
                self._health_hub.mark_up("bridge", details={"circuit_reset": True})"""
if "circuit_reset" not in bc:
    bc = bc.replace(old, new, 1)
    print("  1d. Added mark_up on circuit reset")
    changes += 1
else:
    print("  1d. SKIP already exists")

# 1e. Modify get_bridge_client and init_bridge_client to accept health_hub
old_get = (
    'def get_bridge_client() -> BridgeClient:\n'
    '    global _bridge_client\n'
    '    if _bridge_client is None:\n'
    '        _bridge_client = BridgeClient()\n'
    '    return _bridge_client\n'
    '\n'
    '\n'
    'async def init_bridge_client():\n'
    '    """Called during server lifespan startup."""\n'
    '    client = get_bridge_client()'
)
new_get = (
    'def get_bridge_client(health_hub=None) -> BridgeClient:\n'
    '    global _bridge_client\n'
    '    if _bridge_client is None:\n'
    '        _bridge_client = BridgeClient(health_hub=health_hub)\n'
    '    elif health_hub and not _bridge_client._health_hub:\n'
    '        _bridge_client._health_hub = health_hub\n'
    '    return _bridge_client\n'
    '\n'
    '\n'
    'async def init_bridge_client(health_hub=None):\n'
    '    """Called during server lifespan startup."""\n'
    '    client = get_bridge_client(health_hub=health_hub)'
)
if "def get_bridge_client(health_hub" not in bc:
    bc = bc.replace(old_get, new_get, 1)
    print("  1e. Updated get/init_bridge_client to accept health_hub")
    changes += 1
else:
    print("  1e. SKIP already exists")

save_file("bridge_client.py", bc)

# ═══ 2. service_health.py ═══
print("\n=== service_health.py ===")
with open("service_health.py", "r") as f:
    sh = f.read()

if "get_health_hub" not in sh:
    sh += """

# Singleton accessor
_health_hub_instance: ServiceHealthHub = None

def get_health_hub() -> ServiceHealthHub:
    return _health_hub_instance

def set_health_hub(hub: ServiceHealthHub):
    global _health_hub_instance
    _health_hub_instance = hub
"""
    print("  2. Added get/set_health_hub singleton")
    changes += 1
else:
    print("  2. SKIP already exists")

save_file("service_health.py", sh)

# ═══ 3. dashboard_api.py ═══
print("\n=== dashboard_api.py ===")
with open("dashboard_api.py", "r") as f:
    da = f.read()

# 3a. Add helper function after imports
if "_check_bridge_health" not in da:
    # Find end of imports area — insert before first function
    marker = "async def ha_dashboard():"
    idx = da.find(marker)
    if idx == -1:
        print("  3a. ERROR: ha_dashboard not found")
        sys.exit(1)
    helper = '''
def _check_bridge_health():
    """Check if Bridge is available via service_health."""
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


'''
    da = da[:idx] + helper + da[idx:]
    print("  3a. Added _check_bridge_health helper")
    changes += 1
else:
    print("  3a. SKIP already exists")

# 3b. /dashboard degraded_mode
old_deg = '    data["degraded_mode"] = "normal"'
new_deg = '''    bridge_up, bridge_degraded = _check_bridge_health()
    if not bridge_up:
        data["degraded_mode"] = "bridge_offline"
        data["degraded_info"] = bridge_degraded
    else:
        data["degraded_mode"] = "normal"'''
if "bridge_offline" not in da:
    da = da.replace(old_deg, new_deg, 1)
    print("  3b. Dashboard degraded_mode from health check")
    changes += 1
else:
    print("  3b. SKIP already exists")

# 3c. /dashboard/radar
old_radar = '''    """Dedicated radar data for HA radar sensor -- lightweight, read-only from DB."""
    import sqlite3
    from datetime import date as _d
    data = {}'''
new_radar = '''    """Dedicated radar data for HA radar sensor -- lightweight, read-only from DB."""
    import sqlite3
    from datetime import date as _d
    data = {}
    bridge_up, bridge_degraded = _check_bridge_health()
    if bridge_degraded:
        data.update(bridge_degraded)'''
if "bridge_degraded" not in da or old_radar in da:
    da = da.replace(old_radar, new_radar, 1)
    print("  3c. Radar degraded flag")
    changes += 1
else:
    print("  3c. SKIP already exists")

# 3d. /dashboard/portfolio
old_port = '''    """Portfolio data for HA dashboard — open positions, closed trades, stats."""
    data = {}'''
new_port = '''    """Portfolio data for HA dashboard — open positions, closed trades, stats."""
    data = {}
    bridge_up, bridge_degraded = _check_bridge_health()
    if bridge_degraded:
        data.update(bridge_degraded)'''
if old_port in da:
    da = da.replace(old_port, new_port, 1)
    print("  3d. Portfolio degraded flag")
    changes += 1
else:
    print("  3d. SKIP already exists")

save_file("dashboard_api.py", da)

# ═══ 4. stock_radar.py ═══
print("\n=== stock_radar.py ===")
with open("stock_radar.py", "r") as f:
    sr = f.read()

old_wl = """            watchlist = get_watchlist()
            if not watchlist:
                # Fallback to config symbols"""
new_wl = """            # Service health: skip cycle if Bridge is down
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
            if not watchlist:
                # Fallback to config symbols"""
if "skipping radar cycle" not in sr:
    sr = sr.replace(old_wl, new_wl, 1)
    print("  4. Added Bridge health check before watchlist")
    changes += 1
else:
    print("  4. SKIP already exists")

save_file("stock_radar.py", sr)

# ═══ 5. server.py ═══
print("\n=== server.py ===")
with open("server.py", "r") as f:
    sv = f.read()

# 5a. Add set_health_hub call after health_hub creation
if "set_health_hub" not in sv:
    old_hh = "health_hub = ServiceHealthHub(_db_path)"
    new_hh = """health_hub = ServiceHealthHub(_db_path)
from service_health import set_health_hub
set_health_hub(health_hub)"""
    sv = sv.replace(old_hh, new_hh, 1)
    print("  5a. Added set_health_hub call")
    changes += 1
else:
    print("  5a. SKIP already exists")

# 5b. Wire health_hub into BridgeClient init_bridge_client
old_bridge = "from bridge_client import init_bridge_client\n        await init_bridge_client()"
new_bridge = "from bridge_client import init_bridge_client\n        await init_bridge_client(health_hub=health_hub)"
if "init_bridge_client(health_hub" not in sv:
    if old_bridge in sv:
        sv = sv.replace(old_bridge, new_bridge, 1)
        print("  5b. Passed health_hub to init_bridge_client")
        changes += 1
    else:
        print("  5b. WARN: init_bridge_client pattern not found, checking alt")
        # Maybe it's just BridgeClient() direct
        if "BridgeClient(BRIDGE_BASE_URL)" in sv and "health_hub=health_hub" not in sv.split("BridgeClient(BRIDGE_BASE_URL)")[0][-200:]:
            print("  5b. Found direct BridgeClient usage — will need manual wire")
else:
    print("  5b. SKIP already exists")

save_file("server.py", sv)

print(f"\nDone ({changes} changes).")
