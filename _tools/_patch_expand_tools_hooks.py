"""Expand tool registry to 10+ tools and wire hook handlers for logging."""
import os, shutil

with open("server.py", "r") as f:
    content = f.read()

changes = 0

# 1. Replace the tool registration block with expanded version
old_reg = '''    # Phase 6: Register tools in catalog
    tool_reg.register("ha_get_state", _exec_ha_get_state, category="home",
                      description="Get Home Assistant entity state", requires=["home_assistant"])
    tool_reg.register("ha_call_service", _exec_ha_call_service, category="home",
                      description="Call Home Assistant service", requires=["home_assistant"])
    tool_reg.register("ssh_run", _exec_ssh_run, category="system",
                      description="Run shell command on RPi")
    try:
        from bridge_client import BridgeClient, BRIDGE_BASE_URL
        tool_reg.register("bridge_status", lambda: BridgeClient(BRIDGE_BASE_URL).get_status(),
                          category="trading", description="TradingView Bridge status", requires=["bridge"])
    except Exception:
        pass
    try:
        from stock_radar import get_radar_snapshot
        tool_reg.register("radar_snapshot", get_radar_snapshot, category="trading",
                          description="Stock radar daily snapshot")
    except Exception:
        pass
    logger.info(f"Tool registry: {len(tool_reg.list_tools())} tools registered")'''

new_reg = '''    # Phase 6: Register tools in catalog
    # -- Home --
    tool_reg.register("ha_get_state", _exec_ha_get_state, category="home",
                      description="Get Home Assistant entity state", requires=["home_assistant"])
    tool_reg.register("ha_call_service", _exec_ha_call_service, category="home",
                      description="Call Home Assistant service", requires=["home_assistant"])
    # -- System --
    tool_reg.register("ssh_run", _exec_ssh_run, category="system",
                      description="Run shell command on RPi")
    tool_reg.register("service_health", lambda: health_hub.get_summary(), category="system",
                      description="Get all service health statuses")
    tool_reg.register("feature_flags", lambda: ff.get_all(), category="system",
                      description="List all feature flags")
    tool_reg.register("kairos_status", lambda: kairos_agent.get_status() if kairos_agent else {}, category="system",
                      description="KAIROS agent status")
    # -- Trading --
    try:
        from bridge_client import BridgeClient, BRIDGE_BASE_URL
        tool_reg.register("bridge_status", lambda: BridgeClient(BRIDGE_BASE_URL).get_status(),
                          category="trading", description="TradingView Bridge status", requires=["bridge"])
    except Exception:
        pass
    try:
        from stock_radar import get_radar_snapshot, get_watchlist
        tool_reg.register("radar_snapshot", get_radar_snapshot, category="trading",
                          description="Stock radar daily snapshot")
        tool_reg.register("radar_watchlist", get_watchlist, category="trading",
                          description="Current radar watchlist")
    except Exception:
        pass
    # -- News --
    if NEWS_ENGINE_OK:
        tool_reg.register("news_feed", lambda: news_get_news(limit=20), category="news",
                          description="Latest 20 news items")
        tool_reg.register("news_counts", news_get_counts, category="news",
                          description="News item counts by category")
    # -- Journal --
    if JOURNAL_OK:
        try:
            from journal_engine import get_open_trades, get_trade_stats
            tool_reg.register("open_trades", get_open_trades, category="trading",
                              description="Current open trading positions")
            tool_reg.register("trade_stats", get_trade_stats, category="trading",
                              description="Trading statistics summary")
        except Exception:
            pass
    # -- Memory --
    if MEMORY_AVAILABLE:
        tool_reg.register("memory_stats", lambda: _get_memory_stats() if callable(_get_memory_stats) else {},
                          category="system", description="Memory DB statistics")
    logger.info(f"Tool registry: {len(tool_reg.list_tools())} tools registered")

    # Phase 6: Wire hook handlers for logging
    async def _hook_log_service_down(name="", reason="", **kw):
        logger.info(f"HOOK service_down: {name} - {reason}")
    async def _hook_log_service_up(name="", **kw):
        logger.info(f"HOOK service_up: {name}")
    async def _hook_log_flag_toggle(name="", enabled=False, **kw):
        logger.info(f"HOOK flag_toggled: {name}={enabled}")
    hook_registry.on("service_down", _hook_log_service_down)
    hook_registry.on("service_up", _hook_log_service_up)
    hook_registry.on("flag_toggled", _hook_log_flag_toggle)
    logger.info(f"Hooks: {hook_registry.get_stats()['total_handlers']} handlers registered")'''

if "news_feed" not in content:
    content = content.replace(old_reg, new_reg, 1)
    print("1. Expanded tool registry + wired hook handlers")
    changes += 1
else:
    print("1. Already expanded")

if changes == 0:
    print("No changes needed.")
    import sys; sys.exit(0)

with open("/tmp/server_patched.py", "w") as f:
    f.write(content)
os.remove("server.py")
shutil.move("/tmp/server_patched.py", "server.py")
print(f"Done ({changes} changes).")
