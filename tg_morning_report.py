"""Daily Morning Report for Telegram — Phase B1."""
import httpx, logging, json, os
from datetime import datetime, timedelta

logger = logging.getLogger("tg_morning")

HA_URL = os.environ.get("HA_URL", "http://localhost:8123")
HA_TOKEN = os.environ.get("HA_TOKEN", "")

# Shift schedule (same as server.py)
SHIFT_PATTERN = ["A", "A", "D", "D", "B", "B", "C", "C"]
SHIFT_NAMES = {"A": "صباحي ☀️", "B": "مسائي 🌅", "C": "ليلي 🌙", "D": "إجازة 😎"}
SHIFT_EPOCH = datetime(2024, 1, 1)


def _get_shift(date=None):
    """Get shift for a given date."""
    target = date or datetime.now()
    days_since = (target - SHIFT_EPOCH).days
    idx = days_since % len(SHIFT_PATTERN)
    shift = SHIFT_PATTERN[idx]
    return shift, SHIFT_NAMES[shift]


def _get_shift_week():
    """Get next 3 days shift."""
    today = datetime.now()
    days = []
    weekdays_ar = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    for i in range(0, 4):
        d = today + timedelta(days=i)
        s, name = _get_shift(d)
        day_name = weekdays_ar[d.weekday()]
        prefix = "📌 اليوم" if i == 0 else f"    {day_name}"
        days.append(f"{prefix}: {name}")
    return "\n".join(days)


async def _get_weather():
    """Get Kuwait weather from wttr.in."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("https://wttr.in/Kuwait?format=%t+%C&lang=ar")
            if r.status_code == 200:
                return r.text.strip()
    except Exception as e:
        logger.error(f"Weather error: {e}")
    return "غير متوفر"


async def _get_ha_summary():
    """Get home status: offline devices, open doors, AC temps."""
    if not HA_TOKEN:
        return "⚠️ HA غير متصل"
    
    headers = {"Authorization": f"Bearer {HA_TOKEN}"}
    summary = []
    
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{HA_URL}/api/states", headers=headers)
            if r.status_code != 200:
                return "⚠️ HA غير متصل"
            
            states = r.json()
            
            # 1. Offline/unavailable devices
            unavailable = []
            for s in states:
                eid = s.get("entity_id", "")
                state = s.get("state", "")
                if state == "unavailable" and any(eid.startswith(d) for d in ["light.", "switch.", "climate.", "cover."]):
                    name = s.get("attributes", {}).get("friendly_name", eid)
                    unavailable.append(name)
            
            if unavailable:
                summary.append(f"⚠️ أجهزة offline ({len(unavailable)}):")
                for name in unavailable[:5]:
                    summary.append(f"  • {name}")
                if len(unavailable) > 5:
                    summary.append(f"  ... و {len(unavailable)-5} أجهزة أخرى")
            else:
                summary.append("✅ كل الأجهزة شغالة")
            
            # 2. AC temperatures
            acs = []
            for s in states:
                eid = s.get("entity_id", "")
                if eid.startswith("climate.") and s.get("state") not in ("unavailable", "off"):
                    name = s.get("attributes", {}).get("friendly_name", eid)
                    temp = s.get("attributes", {}).get("current_temperature")
                    target = s.get("attributes", {}).get("temperature")
                    if temp:
                        acs.append(f"  🌡️ {name}: {temp}° (هدف {target}°)")
            
            if acs:
                summary.append(f"\n❄️ المكيفات الشغالة ({len(acs)}):")
                summary.extend(acs)
            
            # 3. Open covers
            open_covers = []
            for s in states:
                eid = s.get("entity_id", "")
                if eid.startswith("cover.") and s.get("state") == "open":
                    name = s.get("attributes", {}).get("friendly_name", eid)
                    open_covers.append(name)
            
            if open_covers:
                summary.append(f"\n🪟 ستائر مفتوحة ({len(open_covers)}):")
                for name in open_covers:
                    summary.append(f"  • {name}")
            
            # 4. Lights on count
            lights_on = sum(1 for s in states if s["entity_id"].startswith("light.") and s["state"] == "on")
            if lights_on:
                summary.append(f"\n💡 أنوار شغالة: {lights_on}")
    
    except Exception as e:
        logger.error(f"HA summary error: {e}")
        summary.append(f"⚠️ خطأ: {str(e)[:50]}")
    
    return "\n".join(summary) if summary else "✅ البيت تمام"


async def build_morning_report() -> str:
    """Build the complete morning report message."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    weekdays_ar = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    day_name = weekdays_ar[now.weekday()]
    
    # Gather all data
    weather = await _get_weather()
    shift_code, shift_name = _get_shift()
    shift_week = _get_shift_week()
    ha_summary = await _get_ha_summary()
    
    report = f"""☀️ *صباح الخير بو خليفة!*
📅 {day_name} {date_str}

🌤️ *الطقس:* {weather}

👷 *الوردية:*
{shift_week}

🏠 *حالة البيت:*
{ha_summary}"""
    
    return report


async def send_morning_report(bot_token: str, chat_id: str):
    """Send the morning report via Telegram."""
    report = await build_morning_report()
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": report, "parse_mode": "Markdown"}
            )
            if r.status_code == 200:
                logger.info("Morning report sent successfully")
                return True
            else:
                logger.error(f"Morning report send failed: {r.text[:200]}")
    except Exception as e:
        logger.error(f"Morning report error: {e}")
    return False
