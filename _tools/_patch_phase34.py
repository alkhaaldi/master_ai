"""Patch server.py for Phase 3 (KAIROS) + Phase 4 (Telegram Queue)."""
import sys, os, shutil

with open("server.py", "r") as f:
    content = f.read()

changes = 0

# ═══ Phase 3: KAIROS ═══

# 1. Add import after service_health import
if "from kairos import" not in content:
    content = content.replace(
        "from service_health import ServiceHealthHub",
        "from service_health import ServiceHealthHub\nfrom kairos import KairosAgent",
        1,
    )
    print("1. Added kairos import")
    changes += 1
else:
    print("1. Kairos import already exists")

# 2. Add kairos init after health_hub init
if "kairos_agent = KairosAgent" not in content:
    content = content.replace(
        "health_hub = ServiceHealthHub(_db_path)",
        "health_hub = ServiceHealthHub(_db_path)\nkairos_agent = None  # initialized in lifespan with tg_send",
        1,
    )
    print("2. Added kairos_agent placeholder")
    changes += 1
else:
    print("2. Kairos init already exists")

# 3. Add kairos startup task before yield in lifespan
#    Find the last "yield" preceded by the shutdown log line
yield_marker = '    yield\n    logger.info("Master AI shutting down")'
if yield_marker in content and "kairos_agent.start()" not in content:
    kairos_startup = '''    # Phase 3: KAIROS background agent
    global kairos_agent
    kairos_agent = KairosAgent(
        health_hub=health_hub, ff=ff, tg_send_fn=tg_send, db_path=_db_path,
        cb_ha=_cb_ha, cb_llm=_cb_llm, cb_tg=_cb_tg,
    )
    asyncio.create_task(kairos_agent.start())
    logger.info("KAIROS agent scheduled (gated by feature flag)")
'''
    content = content.replace(yield_marker, kairos_startup + yield_marker, 1)
    print("3. Added KAIROS startup in lifespan")
    changes += 1
else:
    if "kairos_agent.start()" in content:
        print("3. KAIROS startup already exists")
    else:
        print("3. ERROR: yield marker not found")
        sys.exit(1)

# 4. Add /api/kairos/* endpoints after /api/service-health
kairos_endpoints = '''
# ── KAIROS Agent API ──────────────────────────────────────
@app.get("/api/kairos/status")
async def get_kairos_status():
    if kairos_agent is None:
        return {"error": "kairos not initialized"}
    return kairos_agent.get_status()

@app.get("/api/kairos/log")
async def get_kairos_log(limit: int = 50):
    if kairos_agent is None:
        return {"error": "kairos not initialized"}
    return {"log": kairos_agent.get_log(limit)}

'''

if "/api/kairos/status" not in content:
    # Insert after the service-health endpoint's closing
    svc_health_return = "        last_boursa=last_b, last_gemini=last_g,\n    )"
    idx = content.find(svc_health_return)
    if idx == -1:
        print("4. ERROR: service-health return not found")
        sys.exit(1)
    eol = content.find('\n', idx + len(svc_health_return))
    content = content[:eol+1] + kairos_endpoints + content[eol+1:]
    print("4. Added /api/kairos/* endpoints")
    changes += 1
else:
    print("4. Kairos endpoints already exist")

# 5. Add /kairos TG command
if '"/kairos"' not in content:
    # Insert at the beginning of tg_handle_command, after the /start block
    start_marker = '    if cmd == "/report" or cmd == "/morning":'
    if start_marker in content:
        kairos_cmd = '''    if cmd == "/kairos":
        if kairos_agent:
            return kairos_agent.format_tg_status()
        return "🤖 KAIROS: not initialized"

'''
        content = content.replace(start_marker, kairos_cmd + start_marker, 1)
        print("5. Added /kairos TG command")
        changes += 1
    else:
        print("5. ERROR: /report marker not found for /kairos insertion")
else:
    print("5. /kairos TG command already exists")

# ═══ Phase 4: Telegram Queue ═══

# 6. Modify tg_send to queue on failure
if "kairos_agent and kairos_agent.tg_queue" not in content:
    # Replace the two failure return points in tg_send
    old_fail1 = '''                _cb_tg.record_failure()
                logger.error(f"TG send fail: {resp.text[:200]}")
                return False'''
    new_fail1 = '''                _cb_tg.record_failure()
                logger.error(f"TG send fail: {resp.text[:200]}")
                if kairos_agent and hasattr(kairos_agent, 'tg_queue') and ff.is_enabled("telegram_queue"):
                    kairos_agent.tg_queue.enqueue(int(chat_id), text, parse_mode or "Markdown")
                return False'''

    old_fail2 = '''            _cb_tg.record_failure()
            logger.error(f"TG send error: {e}")
            return False'''
    new_fail2 = '''            _cb_tg.record_failure()
            logger.error(f"TG send error: {e}")
            if kairos_agent and hasattr(kairos_agent, 'tg_queue') and ff.is_enabled("telegram_queue"):
                kairos_agent.tg_queue.enqueue(int(chat_id), text, parse_mode or "Markdown")
            return False'''

    # Also queue when CB is open (dropping message)
    old_drop = '''    if not _cb_tg.is_available():
        logger.warning(f"TG circuit open, dropping message to {chat_id}")
        return False'''
    new_drop = '''    if not _cb_tg.is_available():
        logger.warning(f"TG circuit open, dropping message to {chat_id}")
        if kairos_agent and hasattr(kairos_agent, 'tg_queue') and ff.is_enabled("telegram_queue"):
            kairos_agent.tg_queue.enqueue(int(chat_id), text, parse_mode or "Markdown")
        return False'''

    if old_fail1 in content:
        content = content.replace(old_fail1, new_fail1, 1)
    if old_fail2 in content:
        content = content.replace(old_fail2, new_fail2, 1)
    if old_drop in content:
        content = content.replace(old_drop, new_drop, 1)
    print("6. Added TG queue fallback in tg_send")
    changes += 1
else:
    print("6. TG queue fallback already exists")

if changes == 0:
    print("\nNo changes needed.")
    sys.exit(0)

with open("/tmp/server_patched.py", "w") as f:
    f.write(content)

os.remove("server.py")
shutil.move("/tmp/server_patched.py", "server.py")
print(f"\nDone ({changes} changes). Run: python -m py_compile server.py")
