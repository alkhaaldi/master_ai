"""Patch server.py to add ServiceHealthHub integration.
Strategy: Active sync only — the endpoint reads CB state on each request.
No passive marks needed (avoids fragile string replacement in varied indentation contexts).
"""
import sys, os, shutil

with open("server.py", "r") as f:
    content = f.read()

changes = 0

# 1. Add import after feature_flags import
old_import = "from feature_flags import FeatureFlags"
new_import = "from feature_flags import FeatureFlags\nfrom service_health import ServiceHealthHub"
if "from service_health import" not in content:
    content = content.replace(old_import, new_import, 1)
    print("1. Added service_health import")
    changes += 1
else:
    print("1. Import already exists")

# 2. Add health_hub init after FEATURE_ENTITY_HEALTH
old_entity = 'FEATURE_ENTITY_HEALTH = ff.is_enabled("entity_health")'
new_entity = old_entity + "\nhealth_hub = ServiceHealthHub(_db_path)"
if "health_hub = ServiceHealthHub" not in content:
    content = content.replace(old_entity, new_entity, 1)
    print("2. Added health_hub init")
    changes += 1
else:
    print("2. health_hub init already exists")

# 3. Add /api/service-health endpoint after /api/flags toggle endpoint
endpoint_code = '''
# ── Service Health Hub API ────────────────────────────────
@app.get("/api/service-health")
async def get_service_health():
    """Central health status — reads from existing circuit breakers + timestamps."""
    bridge_st = None
    try:
        from bridge_client import BridgeClient, BRIDGE_BASE_URL
        client = BridgeClient(BRIDGE_BASE_URL)
        bridge_st = client.get_status()
    except Exception:
        pass
    last_b, last_g = None, None
    try:
        from news_engine import last_boursa_refresh, last_gemini_refresh
        last_b, last_g = last_boursa_refresh, last_gemini_refresh
    except Exception:
        pass
    return health_hub.check_all(
        cb_ha=_cb_ha, cb_llm=_cb_llm, cb_tg=_cb_tg,
        bridge_status=bridge_st,
        last_boursa=last_b, last_gemini=last_g,
    )

'''

if "/api/service-health" not in content:
    ret_line = 'return {"name": name, "enabled": new_val}'
    ret_idx = content.find(ret_line)
    if ret_idx == -1:
        print("3. ERROR: toggle return not found")
        sys.exit(1)
    eol = content.find('\n', ret_idx)
    content = content[:eol+1] + endpoint_code + content[eol+1:]
    print("3. Added /api/service-health endpoint")
    changes += 1
else:
    print("3. Endpoint already exists")

if changes == 0:
    print("\nNo changes needed.")
    sys.exit(0)

with open("/tmp/server_patched.py", "w") as f:
    f.write(content)

os.remove("server.py")
shutil.move("/tmp/server_patched.py", "server.py")
print(f"\nDone ({changes} changes). Run: python -m py_compile server.py")
