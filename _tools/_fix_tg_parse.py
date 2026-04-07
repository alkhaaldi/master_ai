"""Fix TG 400 Bad Request by adding plain-text fallback to tg_send."""
import sys, py_compile

FILE = "/home/pi/master_ai/server.py"
with open(FILE) as f:
    content = f.read()

# Replace the inner send loop in tg_send with fallback logic
old_loop = """    for part in tg_split_message(text):
        try:
            payload = {"chat_id": chat_id, "text": part}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            resp = await _tg_client.post(f"{TG_BASE}/sendMessage", json=payload)
            if resp.status_code != 200:
                _cb_tg.record_failure()
                logger.error(f"TG send fail: {resp.text[:200]}")
                if kairos_agent and hasattr(kairos_agent, 'tg_queue') and ff.is_enabled("telegram_queue"):
                    kairos_agent.tg_queue.enqueue(int(chat_id), text, parse_mode or "")
                return False
            _cb_tg.record_success()
        except Exception as e:
            _cb_tg.record_failure()
            logger.error(f"TG send error: {e}")
            if kairos_agent and hasattr(kairos_agent, 'tg_queue') and ff.is_enabled("telegram_queue"):
                kairos_agent.tg_queue.enqueue(int(chat_id), text, parse_mode or "")
            return False
    return True"""

new_loop = """    for part in tg_split_message(text):
        try:
            payload = {"chat_id": chat_id, "text": part}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            resp = await _tg_client.post(f"{TG_BASE}/sendMessage", json=payload)
            if resp.status_code == 400 and parse_mode:
                # Fallback: strip HTML/Markdown and retry as plain text
                import re as _re
                plain = _re.sub(r'<[^>]+>', '', part)
                plain = plain.replace('*', '').replace('_', '').replace('`', '')
                _fb_payload = {"chat_id": chat_id, "text": plain}
                _fb_resp = await _tg_client.post(f"{TG_BASE}/sendMessage", json=_fb_payload)
                if _fb_resp.status_code == 200:
                    _cb_tg.record_success()
                    logger.info("TG send fallback to plain text (parse_mode=%s failed)", parse_mode)
                    continue
                _cb_tg.record_failure()
                logger.error(f"TG send fail (even plain): {_fb_resp.text[:200]}")
                return False
            elif resp.status_code != 200:
                _cb_tg.record_failure()
                logger.error(f"TG send fail: {resp.text[:200]}")
                if kairos_agent and hasattr(kairos_agent, 'tg_queue') and ff.is_enabled("telegram_queue"):
                    kairos_agent.tg_queue.enqueue(int(chat_id), text, parse_mode or "")
                return False
            _cb_tg.record_success()
        except Exception as e:
            _cb_tg.record_failure()
            logger.error(f"TG send error: {e}")
            if kairos_agent and hasattr(kairos_agent, 'tg_queue') and ff.is_enabled("telegram_queue"):
                kairos_agent.tg_queue.enqueue(int(chat_id), text, parse_mode or "")
            return False
    return True"""

if old_loop not in content:
    print("Could not find tg_send loop")
    sys.exit(1)

content = content.replace(old_loop, new_loop, 1)

with open(FILE, "w") as f:
    f.write(content)

try:
    py_compile.compile(FILE, doraise=True)
    print("tg_send fallback PATCHED — syntax OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
    sys.exit(1)
