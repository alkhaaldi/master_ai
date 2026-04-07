"""Fix: move _check_bridge_health before the @router.get decorator."""
import os, shutil

with open("dashboard_api.py", "r") as f:
    content = f.read()

# Remove the misplaced helper (between decorator and function)
old = '''@router.get("/dashboard")

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


async def ha_dashboard():'''

new = '''def _check_bridge_health():
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


@router.get("/dashboard")
async def ha_dashboard():'''

content = content.replace(old, new, 1)
print("Fixed: moved _check_bridge_health before @router.get")

with open("/tmp/_fix_da.py", "w") as f:
    f.write(content)
os.remove("dashboard_api.py")
shutil.move("/tmp/_fix_da.py", "dashboard_api.py")
print("Done.")
