"""Patch server.py for Phase 6: Hooks + Tool Registry."""
import sys, os, shutil

with open("server.py", "r") as f:
    content = f.read()

changes = 0

# 1. Add imports after kairos import
if "from hooks import" not in content:
    content = content.replace(
        "from kairos import KairosAgent",
        "from kairos import KairosAgent\nfrom hooks import HookRegistry\nfrom tool_registry import ToolRegistry",
        1,
    )
    print("1. Added hooks + tool_registry imports")
    changes += 1
else:
    print("1. Imports already exist")

# 2. Add hooks/registry init after health_hub init
if "hook_registry = HookRegistry" not in content:
    content = content.replace(
        "health_hub = ServiceHealthHub(_db_path)",
        "health_hub = ServiceHealthHub(_db_path)\nhook_registry = HookRegistry(_db_path, ff=ff)\ntool_reg = ToolRegistry(ff=ff, health_hub=health_hub, hooks=hook_registry)",
        1,
    )
    print("2. Added hook_registry + tool_reg init")
    changes += 1
else:
    print("2. Init already exists")

# 3. Wire hooks into health_hub in lifespan (after kairos init)
if "health_hub.set_hooks" not in content:
    content = content.replace(
        '    asyncio.create_task(kairos_agent.start())\n    logger.info("KAIROS agent scheduled (gated by feature flag)")',
        '    asyncio.create_task(kairos_agent.start())\n    logger.info("KAIROS agent scheduled (gated by feature flag)")\n    health_hub.set_hooks(hook_registry)\n    logger.info("Hooks wired into health_hub")',
        1,
    )
    print("3. Wired hooks into health_hub")
    changes += 1
else:
    print("3. health_hub hooks already wired")

# 4. Register existing tools
tool_reg_code = '''
    # Phase 6: Register tools in catalog
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
    logger.info(f"Tool registry: {len(tool_reg.list_tools())} tools registered")
'''

if "tool_reg.register" not in content:
    # Insert after hooks wiring
    marker = '    logger.info("Hooks wired into health_hub")'
    if marker in content:
        content = content.replace(marker, marker + tool_reg_code, 1)
        print("4. Registered tools in catalog")
        changes += 1
    else:
        print("4. ERROR: hooks marker not found")
        sys.exit(1)
else:
    print("4. Tools already registered")

# 5. Add /api/tools endpoints after /api/kairos/log
endpoints = '''
# ── Hooks + Tool Registry API (Phase 6) ──────────────────
@app.get("/api/hooks/stats")
async def get_hooks_stats():
    return hook_registry.get_stats()

@app.get("/api/hooks/log")
async def get_hooks_log(limit: int = 50, event: str = None):
    return {"log": hook_registry.get_log(limit, event)}

@app.get("/api/tools")
async def get_tools(category: str = None, q: str = None):
    if q:
        return {"tools": tool_reg.find(q)}
    return tool_reg.get_stats()

@app.get("/api/tools/{name}")
async def get_tool_detail(name: str):
    tool = tool_reg.get(name)
    if not tool:
        return {"error": f"Tool '{name}' not found"}
    d = tool.to_dict()
    d["available"] = tool_reg.is_available(name)
    return d

'''

if "/api/tools" not in content:
    # Find kairos log endpoint
    marker = 'async def get_kairos_log(limit: int = 50):'
    idx = content.find(marker)
    if idx == -1:
        print("5. ERROR: kairos log endpoint not found")
        sys.exit(1)
    # Find the return of that function
    ret_idx = content.find('return {"log": kairos_agent.get_log(limit)}', idx)
    if ret_idx == -1:
        print("5. ERROR: kairos log return not found")
        sys.exit(1)
    eol = content.find('\n', ret_idx)
    content = content[:eol+1] + endpoints + content[eol+1:]
    print("5. Added /api/hooks/* and /api/tools/* endpoints")
    changes += 1
else:
    print("5. Endpoints already exist")

# 6. Fire hook on flag toggle
if "hook_registry.fire_sync" not in content:
    old_toggle_log = '    logger.info(f"Feature flag \'{name}\' toggled to {new_val}")'
    new_toggle_log = old_toggle_log + '\n    hook_registry.fire_sync("flag_toggled", name=name, enabled=new_val)'
    content = content.replace(old_toggle_log, new_toggle_log, 1)
    print("6. Added hook fire on flag toggle")
    changes += 1
else:
    print("6. Hook fire already exists")

if changes == 0:
    print("\nNo changes needed.")
    sys.exit(0)

with open("/tmp/server_patched.py", "w") as f:
    f.write(content)
os.remove("server.py")
shutil.move("/tmp/server_patched.py", "server.py")
print(f"\nDone ({changes} changes).")
