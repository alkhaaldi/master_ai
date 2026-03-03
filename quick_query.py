"""Quick Query v2 — fast answers without LLM calls.
Handles: home status, room status, shift queries, AC/lights count.
"""
import httpx
import logging
import os
import re


def _normalize_ar(text):
    """Normalize Arabic text for better matching."""
    import re
    t = _normalize_ar(text).lower()
    # Remove tashkeel
    t = re.sub(r'[ؐ-ًؚ-ٰٟۖ-ۜ۟-ۤۧ-۪ۨ-ۭ]', '', t)
    # Normalize hamza variants
    t = t.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا').replace('ئ', 'ء').replace('ؤ', 'ء')
    # Normalize taa marboota
    t = t.replace('ة', 'ه')
    # Normalize alef maksura
    t = t.replace('ى', 'ي')
    return t

from datetime import datetime, timedelta

logger = logging.getLogger("quick_query")

HA_URL = os.environ.get("HA_URL", "http://localhost:8123")
HA_TOKEN = os.environ.get("HA_TOKEN", "")

# Shift data (same as life_work.py)
_SHIFT_PATTERN = ["صباحي", "صباحي", "عصري", "عصري", "ليلي", "ليلي", "إجازة", "إجازة"]
_SHIFT_EMOJI = {"صباحي": "U0001f305", "عصري": "U0001f307", "ليلي": "U0001f319", "إجازة": "U0001f3d6"}
_SHIFT_TIMES = {"صباحي": "7:00 AM - 3:00 PM", "عصري": "3:00 PM - 11:00 PM", "ليلي": "11:00 PM - 7:00 AM", "إجازة": "يوم إجازة"}
_EPOCH = datetime(2024, 1, 4).date()
_DAYS_AR = {0: "الاثنين", 1: "الثلاثاء", 2: "الأربعاء", 3: "الخميس", 4: "الجمعة", 5: "السبت", 6: "الأحد"}

def _get_shift(d=None):
    if d is None: d = datetime.now().date()
    idx = (d - _EPOCH).days % 8
    s = _SHIFT_PATTERN[idx]
    return s, _SHIFT_EMOJI[s], _SHIFT_TIMES[s]

# Room name mapping for entity filtering
ROOM_MAP = {
    "الديوانية": ["diwaniya", "diwan"],
    "المعيشة": ["living", "living_room"],
    "الصالة": ["living", "living_room"],
    "المطبخ": ["kitchen"],
    "غرفة النوم": ["master", "bedroom"],
    "الماستر": ["master"],
    "غرفة ماما": ["mama", "mom"],
    "غرفة 3": ["room_3", "room3"],
    "غرفة 5": ["room_5", "room5"],
    "الاستقبال": ["reception", "guest"],
}


async def _ha_states():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{HA_URL}/api/states", headers={"Authorization": f"Bearer {HA_TOKEN}"})
            if r.status_code == 200: return r.json()
    except Exception as e:
        logger.error(f"HA states: {e}")
    return []


async def quick_answer(text: str):
    """Try to answer quickly without LLM. Returns None if no match."""
    t = _normalize_ar(text)

    # 1) Home status
    if re.search(r"وضع البيت|حالة البيت|شلون البيت", t):
        return await _home_status()

    # 2) AC count
    if re.search(r"كم مكيف|مكيفات شغال", t):
        return await _ac_count()

    # 3) Lights count
    if re.search(r"كم ضوء|اضواء شغال|كم نور", t):
        return await _lights_count()

    # 4) Shift queries
    if re.search(r"شفتي|دوامي|شنو شفت|شنو دوام", t):
        return _shift_answer(t)

    # 5) Room status
    for room_ar, room_keys in ROOM_MAP.items():
        if room_ar in t:
            return await _room_status(room_ar, room_keys)


    # 6) Locks status
    if re.search(r"أقفال|قفل|أبواب|باب", t):
        return await _locks_status()

    # 7) Media players
    if re.search(r"سماعات|ميديا|تلفزيون|موسيقى|قرآن|يشغل", t):
        return await _media_status()


    # 8) Weather
    if re.search(r"طقس|جو|حرارة برا|درجة الحرارة|weather|هواء", t):
        return await _weather()


    # 9) Covers/curtains
    if re.search(r"ستائر|ستارة|شتر|كم ستار|covers|curtains", t):
        return await _covers_status()

    # 10) Total active devices
    if re.search(r"كم جهاز|أجهزة شغال|كل شي شغال|active devices", t):
        return await _active_devices_count()

    return None


def _shift_answer(t):
    """Answer shift-related questions."""
    today = datetime.now().date()
    
    # "باكر" or "غدا"
    if "باكر" in t or "غدا" in t or "باخر" in t:
        d = today + timedelta(days=1)
        s, emoji, times = _get_shift(d)
        day_name = _DAYS_AR.get(d.weekday(), "")
        return f"{emoji} باكر {day_name}: {s}\n⏰ {times}"

    # "اليوم" or default
    s, emoji, times = _get_shift(today)
    day_name = _DAYS_AR.get(today.weekday(), "")
    return f"{emoji} اليوم {day_name}: {s}\n⏰ {times}"


async def _home_status():
    states = await _ha_states()
    if not states: return None
    lights_on = sum(1 for s in states if s["entity_id"].startswith("light.") and s["state"] == "on")
    lights_total = sum(1 for s in states if s["entity_id"].startswith("light."))
    ac_on = [s for s in states if s["entity_id"].startswith("climate.") and s["state"] != "off"]
    covers_open = sum(1 for s in states if s["entity_id"].startswith("cover.") and s["state"] == "open")
    covers_total = sum(1 for s in states if s["entity_id"].startswith("cover."))

    lines = [
        "U0001f3e0 وضع البيت:",
        f"U0001f4a1 أضواء: {lights_on}/{lights_total} شغال",
        f"❄️ مكيفات: {len(ac_on)}/{sum(1 for s in states if s['entity_id'].startswith('climate.'))} شغال",
    ]
    for s in ac_on:
        name = s.get("attributes", {}).get("friendly_name", "")
        temp = s.get("attributes", {}).get("temperature", "?")
        lines.append(f"  {name}: {temp}°")
    lines.append(f"U0001f3ea ستائر: {covers_open}/{covers_total} مفتوح")
    return chr(10).join(lines)


async def _ac_count():
    states = await _ha_states()
    if not states: return None
    ac_on = [s for s in states if s["entity_id"].startswith("climate.") and s["state"] != "off"]
    if not ac_on: return "❄️ كل المكيفات مطفية"
    lines = [f"❄️ {len(ac_on)} مكيف شغال:"]
    for s in ac_on:
        name = s.get("attributes", {}).get("friendly_name", "")
        temp = s.get("attributes", {}).get("temperature", "?")
        lines.append(f"  {name}: {temp}°")
    return chr(10).join(lines)


async def _lights_count():
    states = await _ha_states()
    if not states: return None
    on = sum(1 for s in states if s["entity_id"].startswith("light.") and s["state"] == "on")
    return f"U0001f4a1 {on} ضوء شغال"


async def _room_status(room_ar, room_keys):
    """Status for a specific room."""
    states = await _ha_states()
    if not states: return None

    # Filter entities by room keys in entity_id or friendly_name
    room_entities = []
    for s in states:
        eid = s["entity_id"].lower()
        fname = s.get("attributes", {}).get("friendly_name", "").lower()
        if any(k in eid or k in fname for k in room_keys):
            room_entities.append(s)

    if not room_entities:
        return f"❓ ما لقيت أجهزة لـ{room_ar}"

    lights = [s for s in room_entities if s["entity_id"].startswith("light.")]
    acs = [s for s in room_entities if s["entity_id"].startswith("climate.")]
    covers = [s for s in room_entities if s["entity_id"].startswith("cover.")]

    lines = [f"U0001f3e0 {room_ar}:"]

    if lights:
        on = sum(1 for s in lights if s["state"] == "on")
        lines.append(f"U0001f4a1 أضواء: {on}/{len(lights)} شغال")

    if acs:
        for s in acs:
            state = s["state"]
            temp = s.get("attributes", {}).get("temperature", "?")
            curr = s.get("attributes", {}).get("current_temperature", "?")
            if state == "off":
                lines.append(f"❄️ مكيف: مطفي")
            else:
                lines.append(f"❄️ مكيف: {temp}° (حالي: {curr}°)")

    if covers:
        for s in covers:
            name = s.get("attributes", {}).get("friendly_name", "")
            state_ar = "مفتوح" if s["state"] == "open" else "مسكر"
            lines.append(f"U0001f3ea {name}: {state_ar}")

    return chr(10).join(lines)


async def _locks_status():
    states = await _ha_states()
    if not states: return None
    locks = [s for s in states if s["entity_id"].startswith("lock.")]
    if not locks: return "🔐 ما فيه أقفال"
    locked = sum(1 for s in locks if s["state"] == "locked")
    lines = [f"🔐 الأقفال: {locked}/{len(locks)} مقفل"]
    for s in locks:
        name = s.get("attributes", {}).get("friendly_name", s["entity_id"])
        icon = "🔒" if s["state"] == "locked" else "🔓"
        state_ar = "مقفل" if s["state"] == "locked" else "مفتوح"
        lines.append(f"  {icon} {name}: {state_ar}")
    return chr(10).join(lines)


async def _media_status():
    states = await _ha_states()
    if not states: return None
    media = [s for s in states if s["entity_id"].startswith("media_player.") and s["state"] not in ("unavailable", "unknown")]
    playing = [s for s in media if s["state"] == "playing"]
    if not playing:
        return "🎵 ما فيه شي يشغل حالياً"
    lines = [f"🎵 {len(playing)} جهاز يشغل:"]
    for s in playing:
        name = s.get("attributes", {}).get("friendly_name", "")
        title = s.get("attributes", {}).get("media_title", "")
        artist = s.get("attributes", {}).get("media_artist", "")
        vol = s.get("attributes", {}).get("volume_level")
        vol_pct = f" ({int(vol*100)}%)" if vol else ""
        desc = title or artist or ""
        lines.append(f"  🔊 {name}: {desc}{vol_pct}")
    return chr(10).join(lines)


async def _weather():
    """Quick weather from Open-Meteo."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": 29.3375, "longitude": 47.9775,
                "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m",
                "timezone": "Asia/Kuwait",
                "forecast_days": 1,
                "daily": "temperature_2m_max,temperature_2m_min",
            })
            d = r.json()
            cur = d.get("current", {})
            daily = d.get("daily", {})
            temp = cur.get("temperature_2m", "?")
            code = cur.get("weather_code", 0)
            wind = cur.get("wind_speed_10m", "?")
            humid = cur.get("relative_humidity_2m", "?")
            hi = daily.get("temperature_2m_max", ["?"])[0]
            lo = daily.get("temperature_2m_min", ["?"])[0]
            
            CODES = {0:"☀️",1:"🌤",2:"⛅",3:"☁️",45:"🌫",48:"🌫",51:"🌦",53:"🌦",55:"🌧",61:"🌧",63:"🌧",65:"🌧️",71:"❄️",73:"❄️",75:"❄️",80:"🌦",81:"🌧",82:"⛈",95:"⚡",96:"⚡",99:"⚡"}
            icon = CODES.get(code, "🌡")
            
            return chr(10).join([
                f"{icon} الطقس الكويت:",
                f"🌡 حالياً: {temp}°C",
                f"⬆ أعلى: {hi}° | ⬇ أدنى: {lo}°",
                f"💨 رياح: {wind} km/h",
                f"💧 رطوبة: {humid}%",
            ])
    except Exception as e:
        return f"⚠️ {e}"


async def _covers_status():
    states = await _ha_states()
    if not states: return None
    covers = [s for s in states if s["entity_id"].startswith("cover.") and s["state"] not in ("unavailable", "unknown")]
    if not covers: return "🎪 ما فيه ستائر"
    opened = [s for s in covers if s["state"] == "open"]
    closed = [s for s in covers if s["state"] == "closed"]
    lines = [f"🎪 الستائر: {len(opened)} مفتوح / {len(closed)} مغلق"]
    if opened:
        lines.append("")
        lines.append("🟢 المفتوحة:")
        for s in opened:
            name = s.get("attributes", {}).get("friendly_name", s["entity_id"])
            pos = s.get("attributes", {}).get("current_position", "")
            pos_txt = f" ({pos}%)" if pos != "" else ""
            lines.append(f"  • {name}{pos_txt}")
    return chr(10).join(lines)


async def _active_devices_count():
    states = await _ha_states()
    if not states: return None
    _on = {"on", "playing", "open", "heat", "cool", "auto", "heat_cool", "fan_only"}
    active = [s for s in states 
              if s["state"] in _on 
              and s["entity_id"].split(".")[0] in ("light","switch","fan","climate","cover","media_player")
              and "backlight" not in s["entity_id"]]
    by_domain = {}
    for s in active:
        d = s["entity_id"].split(".")[0]
        by_domain.setdefault(d, []).append(s)
    ICONS = {"light":"💡","switch":"🔌","fan":"🌬","climate":"❄️","cover":"🎪","media_player":"🎵"}
    NAMES = {"light":"أضواء","switch":"مفاتيح","fan":"مراوح","climate":"مكيفات","cover":"ستائر","media_player":"سماعات"}
    lines = [f"📱 {len(active)} جهاز شغال:"]
    for d in ["light","climate","cover","media_player","switch","fan"]:
        if d in by_domain:
            lines.append(f"  {ICONS[d]} {NAMES[d]}: {len(by_domain[d])}")
    return chr(10).join(lines)
