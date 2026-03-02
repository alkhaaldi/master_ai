"""Daily Morning Report for Telegram — v2.0"""
import httpx, logging, json, os
from datetime import datetime, timedelta
from pathlib import Path as _Path

logger = logging.getLogger("tg_morning")

HA_URL = os.environ.get("HA_URL", "http://localhost:8123")
HA_TOKEN = os.environ.get("HA_TOKEN", "")

SHIFT_PATTERN = ["A", "A", "B", "B", "C", "C", "D", "D"]
SHIFT_NAMES = {"A": "صباحي ☀️", "B": "عصري 🌅", "C": "ليلي 🌙", "D": "إجازة 😎"}
SHIFT_TIMES = {"A": "7:00-15:00", "B": "15:00-23:00", "C": "23:00-07:00", "D": "إجازة"}
SHIFT_EPOCH = datetime(2024, 1, 4)

_IMPORTANT_DOMAINS = {"climate.", "light.", "cover.", "lock.", "camera.", "fan."}


def _load_entity_names():
    names = {}
    try:
        emap = json.load(open(_Path(__file__).parent / "entity_map.json"))
        for room, entries in emap.items():
            for entry in entries:
                if "=" in entry:
                    eid, name = entry.split("=", 1)
                    names[eid] = name
    except Exception:
        pass
    return names


def _ar_name(entity_id, friendly_name, names_map):
    return names_map.get(entity_id, friendly_name or entity_id)


def _get_shift(date=None):
    target = date or datetime.now()
    days_since = (target - SHIFT_EPOCH).days
    idx = days_since % len(SHIFT_PATTERN)
    shift = SHIFT_PATTERN[idx]
    return shift, SHIFT_NAMES[shift]


def _get_shift_week():
    today = datetime.now()
    days = []
    weekdays_ar = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    for i in range(4):
        d = today + timedelta(days=i)
        s, name = _get_shift(d)
        day_name = weekdays_ar[d.weekday()]
        prefix = "📌 اليوم" if i == 0 else f"    {day_name}"
        time_str = SHIFT_TIMES.get(s, "")
        days.append(f"{prefix}: {name}" + (f" ({time_str})" if s != "D" else ""))
    return "\n".join(days)


async def _get_weather():
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": 29.3117, "longitude": 47.4818,
                "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m",
                "daily": "temperature_2m_max,temperature_2m_min",
                "timezone": "Asia/Kuwait", "forecast_days": 1
            })
            d = r.json()
            cur = d.get("current", {})
            daily = d.get("daily", {})
            temp = cur.get("temperature_2m", "?")
            code = cur.get("weather_code", 0)
            wind = cur.get("wind_speed_10m", "?")
            hum = cur.get("relative_humidity_2m", "?")
            hi = daily.get("temperature_2m_max", ["?"])[0]
            lo = daily.get("temperature_2m_min", ["?"])[0]
            icons = {0: "☀️ صحو", 1: "🌤 غالباً صحو", 2: "⛅ غيوم جزئية", 3: "☁️ غائم", 45: "🌫️ ضباب", 51: "🌧️ رذاذ", 61: "🌧️ مطر", 80: "⛈️ عواصف"}
            desc = icons.get(code, icons.get(code // 10 * 10, f"🌡️ كود {code}"))
            return f"{temp}° — {desc}\n  💨 رياح {wind} كم/س | رطوبة {hum}%\n  ↑{hi}° ↓{lo}°"
    except Exception as e:
        return f"⚠️ {e}"


async def _get_ha_summary():
    if not HA_TOKEN:
        return "⚠️ HA غير متصل"
    names_map = _load_entity_names()
    headers = {"Authorization": f"Bearer {HA_TOKEN}"}
    summary = []
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{HA_URL}/api/states", headers=headers)
            if r.status_code != 200:
                return f"⚠️ HA رجع {r.status_code}"
            states = r.json()

            important_offline = []
            for s in states:
                eid = s.get("entity_id", "")
                if s.get("state") == "unavailable":
                    if any(eid.startswith(d) for d in _IMPORTANT_DOMAINS):
                        fname = s.get("attributes", {}).get("friendly_name", eid)
                        important_offline.append(_ar_name(eid, fname, names_map))
            if important_offline:
                summary.append(f"⚠️ أجهزة مهمة offline ({len(important_offline)}):")
                for name in important_offline[:8]:
                    summary.append(f"  • {name}")
                if len(important_offline) > 8:
                    summary.append(f"  ... و {len(important_offline)-8} أخرى")
            else:
                summary.append("✅ كل الأجهزة المهمة شغالة")

            acs = []
            for s in states:
                eid = s.get("entity_id", "")
                if eid.startswith("climate.") and s.get("state") not in ("unavailable", "off"):
                    fname = s.get("attributes", {}).get("friendly_name", eid)
                    name = _ar_name(eid, fname, names_map)
                    temp = s.get("attributes", {}).get("current_temperature")
                    target_t = s.get("attributes", {}).get("temperature")
                    if temp:
                        acs.append(f"  🌡 {name}: {temp}° (هدف {target_t}°)")
            if acs:
                summary.append(f"\n❄️ المكيفات ({len(acs)}):")
                summary.extend(acs)

            lights_on = sum(1 for s in states if s.get("entity_id", "").startswith("light.") and s.get("state") == "on")
            if lights_on > 0:
                summary.append(f"\n💡 أضواء شغالة: {lights_on}")

            covers_open = sum(1 for s in states if s.get("entity_id", "").startswith("cover.") and s.get("state") == "open")
            if covers_open > 0:
                summary.append(f"🪧 ستائر مفتوحة: {covers_open}")

    except Exception as e:
        summary.append(f"⚠️ خطأ: {e}")
    return "\n".join(summary)


async def _get_stocks_summary():
    try:
        from life_stocks import portfolio_summary
        result = await portfolio_summary()
        if result:
            lines = result.strip().split("\n")
            return "\n".join(lines[:6]) + ("\n..." if len(lines) > 6 else "")
    except Exception:
        pass
    return None


async def build_morning_report() -> str:
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    weekdays_ar = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    day_name = weekdays_ar[now.weekday()]

    shift_code, shift_name = _get_shift()
    hour = now.hour
    if 5 <= hour < 12:
        greeting = "☀️ صباح الخير بو خليفة!"
    elif 12 <= hour < 17:
        greeting = "🌞 مساء النور بو خليفة!"
    elif 17 <= hour < 21:
        greeting = "🌆 مساء الخير بو خليفة!"
    else:
        greeting = "🌙 السلام عليكم بو خليفة!"

    weather = await _get_weather()
    shift_week = _get_shift_week()
    ha_summary = await _get_ha_summary()
    stocks = await _get_stocks_summary()

    report = f"{greeting}\n📅 {day_name} {date_str}\n\n🌤️ الطقس: {weather}\n\n👷 الوردية:\n{shift_week}\n\n🏠 حالة البيت:\n{ha_summary}"

    if stocks:
        report += f"\n\n📈 الأسهم:\n{stocks}"

    return report


async def send_morning_report(bot_token: str, chat_id: str):
    report = await build_morning_report()
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": report}
            )
            if r.status_code == 200:
                logger.info("Morning report sent")
                return True
            else:
                logger.error(f"Morning report send failed: {r.status_code}")
                return False
    except Exception as e:
        logger.error(f"Morning report error: {e}")
        return False
