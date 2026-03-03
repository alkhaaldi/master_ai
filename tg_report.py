"""Daily report generator."""
import time
import datetime
import httpx
import os
import logging

logger = logging.getLogger("tg_report")
HA_URL = os.environ.get("HA_URL", "http://localhost:8123")
HA_TOKEN = os.environ.get("HA_TOKEN", "")


async def generate_daily_report(router_stats, response_times, modules):
    parts = []
    now = datetime.datetime.now()
    weekdays = ["\u0627\u0644\u0627\u062b\u0646\u064a\u0646","\u0627\u0644\u062b\u0644\u0627\u062b\u0627\u0621","\u0627\u0644\u0623\u0631\u0628\u0639\u0627\u0621","\u0627\u0644\u062e\u0645\u064a\u0633","\u0627\u0644\u062c\u0645\u0639\u0629","\u0627\u0644\u0633\u0628\u062a","\u0627\u0644\u0623\u062d\u062f"]
    day_name = weekdays[now.weekday()]
    parts.append(f"\U0001f4ca *\u062a\u0642\u0631\u064a\u0631 {day_name} {now.strftime('%m/%d')} - {now.strftime('%H:%M')}*")
    parts.append("")

    # Shift
    try:
        from life_work import get_shift
        s = get_shift(now.date())
        parts.append(f"\U0001f477 {s['emoji']} {s['shift']} ({s['times']})")
    except Exception:
        pass

    # Weather
    try:
        from quick_query import _weather
        w = await _weather()
        if w:
            parts.append("")
            parts.append(w)
    except Exception:
        pass

    # Active devices
    try:
        from quick_query import _active_devices_count
        ad = await _active_devices_count()
        if ad:
            parts.append("")
            parts.append(ad)
    except Exception:
        pass

    # HA status
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{HA_URL}/api/", headers={"Authorization": f"Bearer {HA_TOKEN}"})
            if r.status_code == 200:
                parts.append("")
                parts.append("\U0001f3e0 HA: \u2705 \u0634\u063a\u0627\u0644")
    except Exception:
        parts.append("\U0001f3e0 HA: \u274c \u0645\u0648 \u0645\u062a\u0648\u0641\u0631")

    # Bot stats
    t = router_stats.get("total", 0)
    qq = router_stats.get("quick_query", 0)
    cache = router_stats.get("cache_hit", 0)
    chat = router_stats.get("chat", 0)
    intent = router_stats.get("intent", 0)
    avg = round(sum(response_times) / len(response_times), 1) if response_times else 0
    parts.append("")
    parts.append(f"\U0001f4e8 \u0631\u0633\u0627\u0626\u0644: {t} | \u0623\u0648\u0627\u0645\u0631: {intent} | QQ: {qq}")
    parts.append(f"\u26a1 \u0645\u062a\u0648\u0633\u0637: {avg}s | LLM: {chat} | Cache: {cache}")

    # Savings
    greet = router_stats.get("template", 0)
    saved = greet + intent + qq + cache
    if t > 0:
        pct = round(saved / t * 100)
        parts.append(f"\U0001f4b0 \u0648\u0641\u0631\u0646\u0627: {saved}/{t} ({pct}%) \u0628\u062f\u0648\u0646 LLM")

    # Expenses
    try:
        from life_expenses import get_expenses
        exp = get_expenses("today")
        if exp and exp.get("total", 0) > 0:
            parts.append(f"\U0001f4b5 \u0645\u0635\u0627\u0631\u064a\u0641: {exp['total']} KD")
    except Exception:
        pass

    return chr(10).join(parts)
