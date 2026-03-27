"""
proactive_engine.py - Proactive Suggestions (Phase 2 Week 8)
AI initiates helpful suggestions based on time + HA state + habits.
Rate limited: max 3/hour, cooldown per type.
"""
import logging, time, os, httpx
from datetime import datetime
logger = logging.getLogger("proactive")
_suggestion_log = []
MAX_PER_HOUR = 3
COOLDOWN = 3600
_last_type = {}
HA_URL = os.environ.get("HA_URL", "http://192.168.109.123:8123")
HA_TOKEN = ""
try:
    tp = os.path.expanduser("~/.ha_token")
    if os.path.exists(tp): HA_TOKEN = open(tp).read().strip()
except: pass

def _rate_ok(stype):
    now = time.time()
    global _suggestion_log
    _suggestion_log = [(t,s) for t,s in _suggestion_log if now-t < 3600]
    if len(_suggestion_log) >= MAX_PER_HOUR: return False
    if stype in _last_type and now - _last_type[stype] < COOLDOWN: return False
    return True

def _mark_sent(stype):
    _suggestion_log.append((time.time(), stype))
    _last_type[stype] = time.time()

async def _get_ha_states():
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{HA_URL}/api/states", headers={"Authorization": f"Bearer {HA_TOKEN}"})
            return r.json() if r.status_code == 200 else []
    except: return []

async def suggest_lights_off():
    h = datetime.now().hour
    if h < 23 and h >= 5: return None
    states = await _get_ha_states()
    on = [s for s in states if s["entity_id"].startswith("light.") and s["state"] == "on"]
    if len(on) >= 3 and _rate_ok("lights_off"):
        names = [s.get("attributes",{}).get("friendly_name", s["entity_id"]) for s in on[:4]]
        NL = chr(10)
        msg = f"\U0001f4a1 {len(on)} \u0623\u0646\u0648\u0627\u0631 \u0634\u063a\u0627\u0644\u0629 \u0648\u0627\u0644\u0648\u0642\u062a \u0645\u062a\u0623\u062e\u0631 ({h}:00){NL}{', '.join(names[:3])}"
        return {"type":"lights_off","message":msg,"suggestion":"\u062a\u0628\u064a\u0646\u064a \u0623\u0637\u0641\u064a \u0643\u0644 \u0634\u064a\u061f","action":"scene.tfwy_kl_shy"}
    return None

async def suggest_ac_off():
    h = datetime.now().hour
    if h < 1 or h >= 6: return None
    states = await _get_ha_states()
    on = [s for s in states if s["entity_id"].startswith("climate.") and s["state"] not in ("off","unavailable")]
    if len(on) >= 2 and _rate_ok("ac_night"):
        names = [s.get("attributes",{}).get("friendly_name", s["entity_id"]) for s in on[:4]]
        NL = chr(10)
        msg = f"\u2744\ufe0f {len(on)} \u0645\u0643\u064a\u0641\u0627\u062a \u0634\u063a\u0627\u0644\u0629 \u0627\u0644\u0641\u062c\u0631 ({h}:00){NL}{', '.join(names[:3])}"
        return {"type":"ac_night","message":msg,"suggestion":"\u062a\u0628\u064a\u0646\u064a \u0623\u0637\u0641\u064a \u0627\u0644\u0644\u064a \u0645\u0627 \u062a\u062d\u062a\u0627\u062c\u0647\u061f","action":None}
    return None

async def suggest_covers_close():
    h = datetime.now().hour
    if h < 22 and h >= 6: return None
    states = await _get_ha_states()
    op = [s for s in states if s["entity_id"].startswith("cover.") and s["state"] == "open"]
    if op and _rate_ok("covers_night"):
        names = [s.get("attributes",{}).get("friendly_name", s["entity_id"]) for s in op[:4]]
        NL = chr(10)
        msg = f"\U0001f319 {len(op)} \u0633\u062a\u0627\u0626\u0631 \u0645\u0641\u062a\u0648\u062d\u0629 \u0628\u0627\u0644\u0644\u064a\u0644{NL}{', '.join(names[:3])}"
        return {"type":"covers_night","message":msg,"suggestion":"\u062a\u0628\u064a\u0646\u064a \u0623\u0633\u0643\u0631\u0647\u0645\u061f","action":"scene.skwr_kl_lstyr"}
    return None

async def suggest_morning():
    h = datetime.now().hour
    if h < 6 or h > 8: return None
    if not _rate_ok("morning"): return None
    try:
        from habit_engine import learn_morning_routine
        mr = learn_morning_routine()
        if mr and mr["actions"]:
            return {"type":"morning","message":"\u2600\ufe0f \u0635\u0628\u0627\u062d \u0627\u0644\u062e\u064a\u0631! \u062a\u0628\u064a\u0646\u064a \u0623\u0634\u063a\u0644 \u0631\u0648\u062a\u064a\u0646 \u0627\u0644\u0635\u0628\u0627\u062d\u061f","suggestion":mr["description"],"action":"scene.sbh_lkhyr"}
    except: pass
    return None

async def suggest_leaving():
    h = datetime.now().hour
    if h < 5 or h > 7: return None
    if not _rate_ok("leaving"): return None
    try:
        from life_work import get_shift_display
        shift = get_shift_display()
        if shift and "\u0635\u0628\u0627\u062d" in str(shift):
            states = await _get_ha_states()
            on_c = sum(1 for s in states if s["entity_id"].startswith("light.") and s["state"]=="on")
            if on_c >= 3:
                return {"type":"leaving","message":f"\U0001f3e0 \u0634\u0641\u062a\u0643 \u0635\u0628\u0627\u062d\u064a \u0648\u0639\u0646\u062f\u0643 {on_c} \u0623\u0646\u0648\u0627\u0631 \u0634\u063a\u0627\u0644\u0629","suggestion":"\u062a\u0628\u064a\u0646\u064a \u0623\u0634\u063a\u0644 \u0645\u0634\u0647\u062f \u0645\u063a\u0627\u062f\u0631\u0629\u061f","action":"scene.mgdr_lbyt"}
    except: pass
    return None

async def get_proactive_suggestions():
    suggestions = []
    for fn in [suggest_lights_off, suggest_ac_off, suggest_covers_close, suggest_morning, suggest_leaving]:
        try:
            s = await fn()
            if s: suggestions.append(s)
        except Exception as e:
            logger.debug(f"Proactive {fn.__name__}: {e}")
    return suggestions

async def send_proactive(send_fn, send_inline_fn=None):
    suggestions = await get_proactive_suggestions()
    sent = 0
    for s in suggestions:
        if not _rate_ok(s["type"]): continue
        msg = s["message"]
        if s.get("suggestion"): msg += chr(10) + s["suggestion"]
        if send_inline_fn and s.get("action"):
            buttons = [{"text":"\u2705 \u0646\u0639\u0645","callback_data":f"sc:{s['action']}"},{"text":"\u274c \u0644\u0627","callback_data":"dismiss"}]
            try:
                await send_inline_fn(msg, buttons)
                _mark_sent(s["type"]); sent += 1
            except:
                await send_fn(msg)
                _mark_sent(s["type"]); sent += 1
        else:
            await send_fn(msg)
            _mark_sent(s["type"]); sent += 1
    if sent: logger.info(f"Proactive: sent {sent} suggestions")
    return sent
