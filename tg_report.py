"""Daily report generator."""
import time
import datetime

async def generate_daily_report(router_stats, response_times, modules):
    parts = []
    now = datetime.datetime.now()
    parts.append(f"\U0001f4ca \u062a\u0642\u0631\u064a\u0631 \u064a\u0648\u0645\u064a - {now.strftime('%Y-%m-%d %H:%M')}")
    parts.append("")
    
    # Shift
    try:
        from life_work import get_shift
        s = get_shift(now.date())
        parts.append(f"\U0001f477 \u0627\u0644\u0634\u0641\u062a: {s['emoji']} {s['shift']} ({s['times']})")
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
    
    # Stats
    t = router_stats.get("total", 0)
    qq = router_stats.get("quick_query", 0)
    cache = router_stats.get("cache_hit", 0)
    chat = router_stats.get("chat", 0)
    avg = round(sum(response_times) / len(response_times), 1) if response_times else 0
    parts.append("")
    parts.append(f"\U0001f4e8 \u0631\u0633\u0627\u0626\u0644: {t} | QQ: {qq} | Cache: {cache} | LLM: {chat}")
    parts.append(f"\u26a1 \u0645\u062a\u0648\u0633\u0637 \u0627\u0644\u0631\u062f: {avg}s")
    
    # Expenses
    try:
        from life_expenses import get_expenses
        exp = get_expenses("today")
        if exp and exp.get("total", 0) > 0:
            parts.append(f"\U0001f4b0 \u0645\u0635\u0627\u0631\u064a\u0641: {exp['total']} KD")
    except Exception:
        pass
    
    return chr(10).join(parts)
