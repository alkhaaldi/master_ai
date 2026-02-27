"""Daily Morning Report for Telegram Phase B1."""
import httpx, logging, json, os
from datetime import datetime, timedelta

logger = logging.getLogger("tg_morning")

HA_URL = os.environ.get("HA_URL", "http://localhost:8123")
HA_TOKEN = os.environ.get("HA_TOKEN", "")

SHIFT_PATTERN = ["A", "A", "D", "D", "B", "B", "C", "C"]
SHIFT_NAMES = {"A": "\u0635\u0628\u0627\u062d\u064a \u2600\ufe0f", "B": "\u0645\u0633\u0627\u0626\u064a \ud83c\udf05", "C": "\u0644\u064a\u0644\u064a \ud83c\udf19", "D": "\u0625\u062c\u0627\u0632\u0629 \ud83d\ude0e"}
SHIFT_EPOCH = datetime(2024, 1, 4)


def _get_shift(date=None):
    target = date or datetime.now()
    days_since = (target - SHIFT_EPOCH).days
    idx = days_since % len(SHIFT_PATTERN)
    shift = SHIFT_PATTERN[idx]
    return shift, SHIFT_NAMES[shift]


def _get_shift_week():
    today = datetime.now()
    days = []
    weekdays_ar = ["\u0627\u0644\u0625\u062b\u0646\u064a\u0646", "\u0627\u0644\u062b\u0644\u0627\u062b\u0627\u0621", "\u0627\u0644\u0623\u0631\u0628\u0639\u0627\u0621", "\u0627\u0644\u062e\u0645\u064a\u0633", "\u0627\u0644\u062c\u0645\u0639\u0629", "\u0627\u0644\u0633\u0628\u062a", "\u0627\u0644\u0623\u062d\u062f"]
    for i in range(0, 4):
        d = today + timedelta(days=i)
        s, name = _get_shift(d)
        day_name = weekdays_ar[d.weekday()]
        prefix = "\ud83d\udccc \u0627\u0644\u064a\u0648\u0645" if i == 0 else f"    {day_name}"
        days.append(f"{prefix}: {name}")
    return "\n".join(days)


async def _get_weather():
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            url = "https://api.open-meteo.com/v1/forecast?latitude=29.3759&longitude=47.9774&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&daily=temperature_2m_max,temperature_2m_min&timezone=Asia/Kuwait&forecast_days=1"
            r = await c.get(url)
            if r.status_code == 200:
                data = r.json()
                current = data.get("current", {})
                daily = data.get("daily", {})
                temp = current.get("temperature_2m", "?")
                humidity = current.get("relative_humidity_2m", "?")
                wind = current.get("wind_speed_10m", "?")
                high = daily.get("temperature_2m_max", ["?"])[0]
                low = daily.get("temperature_2m_min", ["?"])[0]
                wcode = current.get("weather_code", 0)
                weather_desc = {0: "\u0635\u062d\u0648 \u2600\ufe0f", 1: "\u063a\u0627\u0644\u0628\u0627\u064b \u0635\u062d\u0648 \ud83c\udf24\ufe0f", 2: "\u063a\u064a\u0648\u0645 \u062c\u0632\u0626\u064a\u0629 \u26c5", 3: "\u063a\u0627\u0626\u0645 \u2601\ufe0f", 45: "\u0636\u0628\u0627\u0628 \ud83c\udf2b\ufe0f", 51: "\u0631\u0630\u0627\u0630 \u062e\u0641\u064a\u0641", 61: "\u0645\u0637\u0631 \u062e\u0641\u064a\u0641 \ud83c\udf27\ufe0f", 63: "\u0645\u0637\u0631 \ud83c\udf27\ufe0f", 65: "\u0645\u0637\u0631 \u063a\u0632\u064a\u0631 \ud83c\udf27\ufe0f", 80: "\u0632\u062e\u0627\u062a \ud83c\udf26\ufe0f", 95: "\u0639\u0648\u0627\u0635\u0641 \u26c8\ufe0f"}
                desc = weather_desc.get(wcode, f"\u0643\u0648\u062f {wcode}")
                return f"{temp}\u00b0 \u2014 {desc}\n  \ud83d\udca8 \u0631\u064a\u0627\u062d {wind} \u0643\u0645/\u0633 | \u0631\u0637\u0648\u0628\u0629 {humidity}%\n  \u2191{high}\u00b0 \u2193{low}\u00b0"
    except Exception as e:
        logger.error(f"Weather error: {e}")
    return "\u063a\u064a\u0631 \u0645\u062a\u0648\u0641\u0631"


async def _get_ha_summary():
    if not HA_TOKEN:
        return "\u26a0\ufe0f HA \u063a\u064a\u0631 \u0645\u062a\u0635\u0644"
    headers = {"Authorization": f"Bearer {HA_TOKEN}"}
    summary = []
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{HA_URL}/api/states", headers=headers)
            if r.status_code != 200:
                return "\u26a0\ufe0f HA \u063a\u064a\u0631 \u0645\u062a\u0635\u0644"
            states = r.json()
            unavailable = []
            for s in states:
                eid = s.get("entity_id", "")
                state = s.get("state", "")
                if state == "unavailable" and any(eid.startswith(d) for d in ["light.", "switch.", "climate.", "cover."]):
                    name = s.get("attributes", {}).get("friendly_name", eid)
                    unavailable.append(name)
            if unavailable:
                summary.append(f"\u26a0\ufe0f \u0623\u062c\u0647\u0632\u0629 offline ({len(unavailable)}):")
                for name in unavailable[:5]:
                    summary.append(f"  \u2022 {name}")
                if len(unavailable) > 5:
                    summary.append(f"  ... \u0648 {len(unavailable)-5} \u0623\u062c\u0647\u0632\u0629 \u0623\u062e\u0631\u0649")
            else:
                summary.append("\u2705 \u0643\u0644 \u0627\u0644\u0623\u062c\u0647\u0632\u0629 \u0634\u063a\u0627\u0644\u0629")
            acs = []
            for s in states:
                eid = s.get("entity_id", "")
                if eid.startswith("climate.") and s.get("state") not in ("unavailable", "off"):
                    name = s.get("attributes", {}).get("friendly_name", eid)
                    temp = s.get("attributes", {}).get("current_temperature")
                    target = s.get("attributes", {}).get("temperature")
                    if temp:
                        acs.append(f"  \ud83c\udf21 {name}: {temp}\u00b0 (\u0647\u062f\u0641 {target}\u00b0)")
            if acs:
                summary.append(f"\n\u2744\ufe0f \u0627\u0644\u0645\u0643\u064a\u0641\u0627\u062a \u0627\u0644\u0634\u063a\u0627\u0644\u0629 ({len(acs)}):")
                summary.extend(acs)
            open_covers = []
            for s in states:
                eid = s.get("entity_id", "")
                if eid.startswith("cover.") and s.get("state") == "open":
                    name = s.get("attributes", {}).get("friendly_name", eid)
                    open_covers.append(name)
            if open_covers:
                summary.append(f"\n\ud83e\ude9f \u0633\u062a\u0627\u0626\u0631 \u0645\u0641\u062a\u0648\u062d\u0629 ({len(open_covers)}):")
                for name in open_covers:
                    summary.append(f"  \u2022 {name}")
            lights_on = sum(1 for s in states if s["entity_id"].startswith("light.") and s["state"] == "on")
            if lights_on:
                summary.append(f"\n\ud83d\udca1 \u0623\u0646\u0648\u0627\u0631 \u0634\u063a\u0627\u0644\u0629: {lights_on}")
    except Exception as e:
        logger.error(f"HA summary error: {e}")
        summary.append(f"\u26a0\ufe0f \u062e\u0637\u0623: {str(e)[:50]}")
    return "\n".join(summary) if summary else "\u2705 \u0627\u0644\u0628\u064a\u062a \u062a\u0645\u0627\u0645"


async def build_morning_report() -> str:
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    weekdays_ar = ["\u0627\u0644\u0625\u062b\u0646\u064a\u0646", "\u0627\u0644\u062b\u0644\u0627\u062b\u0627\u0621", "\u0627\u0644\u0623\u0631\u0628\u0639\u0627\u0621", "\u0627\u0644\u062e\u0645\u064a\u0633", "\u0627\u0644\u062c\u0645\u0639\u0629", "\u0627\u0644\u0633\u0628\u062a", "\u0627\u0644\u0623\u062d\u062f"]
    day_name = weekdays_ar[now.weekday()]
    weather = await _get_weather()
    shift_week = _get_shift_week()
    ha_summary = await _get_ha_summary()
    report = f"\u2600\ufe0f *\u0635\u0628\u0627\u062d \u0627\u0644\u062e\u064a\u0631 \u0628\u0648 \u062e\u0644\u064a\u0641\u0629!*\n\ud83d\udcc5 {day_name} {date_str}\n\n\ud83c\udf24\ufe0f *\u0627\u0644\u0637\u0642\u0633:* {weather}\n\n\ud83d\udc77 *\u0627\u0644\u0648\u0631\u062f\u064a\u0629:*\n{shift_week}\n\n\ud83c\udfe0 *\u062d\u0627\u0644\u0629 \u0627\u0644\u0628\u064a\u062a:*\n{ha_summary}"
    return report


async def send_morning_report(bot_token: str, chat_id: str):
    report = await build_morning_report()
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": report, "parse_mode": "Markdown"}
            )
            if r.status_code == 200:
                logger.info("Morning report sent")
                return True
            else:
                logger.error(f"Morning report failed: {r.text[:200]}")
    except Exception as e:
        logger.error(f"Morning report error: {e}")
    return False
