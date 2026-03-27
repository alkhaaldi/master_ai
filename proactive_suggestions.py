"""proactive_suggestions.py — Smart Proactive Suggestions for Master AI v7

Background task that monitors HA state and sends helpful suggestions:
- Lights on too long during daytime
- Door unlocked at night
- Baby room temperature unusual
- AC forgotten in empty room
- Many lights on at unusual hour

Rules (from ChatGPT plan):
- signals واضحة فقط
- confidence عالي
- rate-limited (max 3/day, 6h cooldown per type)
- opt-in (can be disabled)
"""
import httpx, logging, os, asyncio
from datetime import datetime

logger = logging.getLogger("proactive")

HA_URL = os.environ.get("HA_URL", "http://localhost:8123")
HA_TOKEN = os.environ.get("HA_TOKEN", "")

# Rate limiting
_daily_suggestions = []
MAX_DAILY = 3
_suggestion_cooldown = {}
COOLDOWN_HOURS = 6


# Custom cooldown hours per type
COOLDOWN_OVERRIDE = {
    "tasks_overdue": 22,   # once per day
    "inbox_critical": 6,   # every 6h
}

def _in_cooldown(stype):
    last = _suggestion_cooldown.get(stype)
    if not last:
        return False
    hours = COOLDOWN_OVERRIDE.get(stype, COOLDOWN_HOURS)
    return (datetime.now() - last).total_seconds() < hours * 3600


def _can_suggest():
    today = str(datetime.now().date())
    return len([s for s in _daily_suggestions if s.get("date") == today]) < MAX_DAILY


def _record(stype, msg):
    _daily_suggestions.append({"type": stype, "message": msg, "date": str(datetime.now().date())})
    _suggestion_cooldown[stype] = datetime.now()


async def _get_states():
    if not HA_TOKEN:
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{HA_URL}/api/states", headers={"Authorization": f"Bearer {HA_TOKEN}"})
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.error(f"HA states: {e}")
    return []


async def check_suggestions():
    if not _can_suggest():
        return []
    states = await _get_states()
    if not states:
        return []

    results = []
    now = datetime.now()
    hour = now.hour

    # 1. Outdoor lights on during daytime
    if not _in_cooldown("lights_long_on"):
        found = []
        for s in states:
            eid = s["entity_id"]
            if not eid.startswith("light.") or s["state"] != "on":
                continue
            fname = s.get("attributes", {}).get("friendly_name", "").lower()
            if any(w in eid or w in fname for w in ["parking", "outdoor", "balcon", "exterior"]):
                lc = s.get("last_changed", "")
                if lc:
                    try:
                        t = datetime.fromisoformat(lc.replace("Z", "+00:00")).replace(tzinfo=None)
                        hrs = (now - t).total_seconds() / 3600
                        if hrs > 3 and 6 <= hour <= 18:
                            found.append((fname, round(hrs, 1)))
                    except:
                        pass
        if found:
            names = ", ".join(f"{n} ({h}h)" for n, h in found[:3])
            msg = f"💡 {names} شغالة من فترة طويلة بالنهار — تبي أطفيهم؟"
            results.append(msg)
            _record("lights_long_on", msg)

    # 2. Door unlocked at night
    if not _in_cooldown("door_unlocked") and (hour >= 23 or hour < 6):
        unlocked = []
        for s in states:
            if s["entity_id"].startswith("lock.") and s["state"] == "unlocked":
                unlocked.append(s.get("attributes", {}).get("friendly_name", s["entity_id"]))
        if unlocked:
            msg = f"🔓 تنبيه ليلي: {', '.join(unlocked[:3])} غير مقفل — تبي أقفلهم؟"
            results.append(msg)
            _record("door_unlocked", msg)

    # 3. Baby/master room temperature
    if not _in_cooldown("room_temp"):
        for s in states:
            if not s["entity_id"].startswith("climate.") or "my_room" not in s["entity_id"]:
                continue
            curr = s.get("attributes", {}).get("current_temperature")
            if curr and isinstance(curr, (int, float)):
                if curr > 26:
                    msg = f"🌡️ غرفة الماستر {curr}° — حارة. تبي أنزل المكيف؟"
                    results.append(msg)
                    _record("room_temp", msg)
                elif curr < 18:
                    msg = f"🌡️ غرفة الماستر {curr}° — بردانة. تبي أرفع المكيف؟"
                    results.append(msg)
                    _record("room_temp", msg)

    # 4. AC struggling (on 3+ hours but current temp still far from target = possible fault)
    if not _in_cooldown("ac_struggling"):
        found = []
        for s in states:
            if not s["entity_id"].startswith("climate.") or s["state"] == "off":
                continue
            attrs = s.get("attributes", {})
            target = attrs.get("temperature")
            current = attrs.get("current_temperature")
            if target is None or current is None:
                continue
            target_f = float(target)
            current_f = float(current)
            # Only alert if current temp is 3+ degrees above target (not cooling properly)
            if current_f - target_f < 3:
                continue
            lc = s.get("last_changed", "")
            if lc:
                try:
                    t = datetime.fromisoformat(lc.replace("Z", "+00:00")).replace(tzinfo=None)
                    hrs = (now - t).total_seconds() / 3600
                    if hrs > 3:
                        fname = attrs.get("friendly_name", "")
                        found.append((fname, target_f, current_f, round(hrs, 1)))
                except:
                    pass
        if found:
            names = ", ".join(f"{n} (هدف {t}° / حالي {c}° / {h}h)" for n, t, c, h in found[:3])
            msg = f"⚠️ مكيفات ما تبرد: {names} — ممكن خربانة؟"
            results.append(msg)
            _record("ac_struggling", msg)

    # 5. Many lights on at unusual hour (1-5 AM)
    if not _in_cooldown("lights_night") and 1 <= hour <= 5:
        on_count = sum(1 for s in states if s["entity_id"].startswith("light.") and s["state"] == "on" and "backlight" not in s["entity_id"])
        if on_count > 5:
            msg = f"🏠 {on_count} نور شغال الساعة {hour} الصبح — تبي أطفي الكل؟"
            results.append(msg)
            _record("lights_night", msg)


    # 6. v8: Overdue high-priority tasks reminder (once per day, 10AM-11AM window)
    if not _in_cooldown("tasks_overdue") and 10 <= hour <= 11:
        try:
            from task_engine import task_list
            overdue = task_list(due_overdue=True, priority="high")
            if overdue:
                titles = ", ".join(t["title"][:25] for t in overdue[:3])
                msg = "⚠️ عندك " + str(len(overdue)) + " مهمة عالية متأخرة: " + titles
                results.append(msg)
                _record("tasks_overdue", msg)
        except Exception: pass

    # 7. v8: Critical inbox alert (once per 6h, any hour)
    if not _in_cooldown("inbox_critical"):
        try:
            import asyncio as _aio
            import concurrent.futures as _cf
            from inbox_engine import fetch_unified_inbox, P_CRITICAL
            with _cf.ThreadPoolExecutor() as pool:
                data = pool.submit(_aio.run, fetch_unified_inbox(hours=6, limit=10)).result(timeout=15)
            critical = [m for m in data.get("messages",[]) if m.get("_priority",0) >= P_CRITICAL and m.get("unread")]
            if critical:
                subj = critical[0].get("subject","")[:40]
                msg = "🚨 إيميل عاجل: " + subj
                results.append(msg)
                _record("inbox_critical", msg)
        except Exception: pass

    return results


async def proactive_loop(send_fn):
    logger.info("Proactive suggestions loop started")
    await asyncio.sleep(120)
    while True:
        try:
            msgs = await check_suggestions()
            for msg in msgs:
                try:
                    await send_fn(msg)
                    logger.info(f"Proactive sent: {msg[:50]}")
                except Exception as e:
                    logger.error(f"Send error: {e}")
            await asyncio.sleep(900)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Proactive loop error: {e}")
            await asyncio.sleep(300)


def get_suggestion_stats():
    today = str(datetime.now().date())
    return {
        "total": len(_daily_suggestions),
        "today": len([s for s in _daily_suggestions if s.get("date") == today]),
        "max_daily": MAX_DAILY,
        "cooldowns": {k: v.isoformat() for k, v in _suggestion_cooldown.items()},
    }
