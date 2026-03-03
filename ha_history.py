"""
ha_history.py — Entity History & Log Analysis
يجيب تاريخ أي جهاز من HA History API ويحلله.

Usage:
    from ha_history import get_entity_history, analyze_entity, format_history_report

    # جيب تاريخ مكيف غرفة النوم آخر 24 ساعة
    history = await get_entity_history("climate.my_room_ac", hours=24)

    # حلل التاريخ — منو شغل/طفى، أنماط، مشاكل
    analysis = await analyze_entity("climate.my_room_ac", hours=24)

    # تقرير مفصل جاهز للتلقرام
    report = await format_history_report("climate.my_room_ac", hours=24)
"""
import os, logging, httpx
from datetime import datetime, timedelta, timezone
from collections import defaultdict

logger = logging.getLogger("ha_history")

HA_URL = os.environ.get("HA_URL", "http://localhost:8123")
HA_TOKEN = os.environ.get("HA_TOKEN", "")

_KW_TZ = timezone(timedelta(hours=3))

# ── helpers ──────────────────────────────────────────────

def _headers():
    return {"Authorization": f"Bearer {HA_TOKEN}"}

def _to_kw(iso_str):
    """Convert ISO timestamp to Kuwait time string HH:MM"""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(_KW_TZ).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_str[:16] if iso_str else "?"

def _to_kw_short(iso_str):
    """HH:MM only"""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(_KW_TZ).strftime("%H:%M")
    except Exception:
        return iso_str[:16] if iso_str else "?"


def _duration_str(seconds):
    """Human readable duration in Arabic"""
    if seconds < 60:
        return f"{int(seconds)} ثانية"
    if seconds < 3600:
        m = int(seconds // 60)
        return f"{m} دقيقة" if m != 1 else "دقيقة"
    h = seconds / 3600
    if h < 24:
        return f"{h:.1f} ساعة"
    d = h / 24
    return f"{d:.1f} يوم"


def _state_ar(state, domain=""):
    """Translate state to Arabic"""
    MAP = {
        "on": "شغال", "off": "مطفي",
        "open": "مفتوح", "closed": "مغلق", "opening": "يفتح", "closing": "يسكر",
        "cool": "تبريد", "heat": "تدفئة", "fan_only": "مروحة", "dry": "تجفيف", "auto": "تلقائي",
        "unavailable": "غير متاح", "unknown": "غير معروف",
        "idle": "خامل", "heating": "يسخن", "cooling": "يبرد",
        "playing": "يشغل", "paused": "موقف", "standby": "استعداد",
    }
    return MAP.get(state, state)


# ── core: fetch history ─────────────────────────────────

async def get_entity_history(entity_id: str, hours: int = 24,
                              start_time: str = None, end_time: str = None) -> list:
    """
    Fetch state history from HA.
    
    Args:
        entity_id: e.g. "climate.my_room_ac"
        hours: lookback hours (default 24), ignored if start_time given
        start_time: ISO format "2026-03-01T00:00:00"
        end_time: ISO format (default=now)
    
    Returns:
        List of dicts: [{state, last_changed, attributes}, ...]
    """
    now = datetime.now(timezone.utc)
    
    if start_time:
        start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.replace(tzinfo=_KW_TZ).astimezone(timezone.utc)
    else:
        start = now - timedelta(hours=hours)
    
    if end_time:
        end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        if end.tzinfo is None:
            end = end.replace(tzinfo=_KW_TZ).astimezone(timezone.utc)
    else:
        end = now

    url = f"{HA_URL}/api/history/period/{start.isoformat()}"
    params = {
        "filter_entity_id": entity_id,
        "end_time": end.isoformat(),
        "significant_changes_only": "true",
    }
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=_headers(), params=params)
            r.raise_for_status()
            data = r.json()
            if data and len(data) > 0 and len(data[0]) > 0:
                return data[0]
            return []
    except Exception as e:
        logger.error(f"History fetch error: {e}")
        return []


# ── analysis ────────────────────────────────────────────

async def analyze_entity(entity_id: str, hours: int = 24,
                          start_time: str = None, end_time: str = None) -> dict:
    """
    Analyze entity history and return structured insights.
    
    Returns dict with:
        - entity_id, friendly_name, domain
        - period: {start, end, hours}
        - total_changes: int
        - state_summary: {state: {count, total_seconds, pct}}
        - transitions: [{time, from, to, attrs}]  (every change)
        - on_off_events: [{on_time, off_time, duration}]  (for lights/switches/fans)
        - temp_changes: [{time, temp, current_temp}]  (for climate)
        - anomalies: [str]  (detected issues)
    """
    history = await get_entity_history(entity_id, hours, start_time, end_time)
    if not history:
        return {"entity_id": entity_id, "error": "لا توجد بيانات للفترة المطلوبة"}

    domain = entity_id.split(".")[0]
    friendly = history[0].get("attributes", {}).get("friendly_name", entity_id)
    
    # ── Build transitions ──
    transitions = []
    for i, entry in enumerate(history):
        t = {
            "time": entry.get("last_changed", ""),
            "time_kw": _to_kw(entry.get("last_changed", "")),
            "state": entry.get("state", ""),
            "state_ar": _state_ar(entry.get("state", ""), domain),
        }
        if i > 0:
            t["from"] = history[i-1].get("state", "")
            t["from_ar"] = _state_ar(history[i-1].get("state", ""), domain)
        
        attrs = entry.get("attributes", {})
        if domain == "climate":
            t["temp_set"] = attrs.get("temperature")
            t["temp_current"] = attrs.get("current_temperature")
            t["hvac_mode"] = attrs.get("hvac_mode", "")
            t["hvac_action"] = attrs.get("hvac_action", "")
        elif domain == "cover":
            t["position"] = attrs.get("current_position")
        elif domain == "media_player":
            t["source"] = attrs.get("source", "")
            t["media_title"] = attrs.get("media_title", "")
            
        transitions.append(t)
    
    # ── State duration summary ──
    state_durations = defaultdict(float)
    for i in range(len(history) - 1):
        s = history[i]["state"]
        try:
            t1 = datetime.fromisoformat(history[i]["last_changed"].replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(history[i+1]["last_changed"].replace("Z", "+00:00"))
            dur = (t2 - t1).total_seconds()
            state_durations[s] += dur
        except Exception:
            pass
    
    # Last state till now
    if history:
        try:
            last_t = datetime.fromisoformat(history[-1]["last_changed"].replace("Z", "+00:00"))
            dur = (datetime.now(timezone.utc) - last_t).total_seconds()
            state_durations[history[-1]["state"]] += dur
        except Exception:
            pass
    
    total_secs = sum(state_durations.values()) or 1
    state_summary = {}
    for s, secs in sorted(state_durations.items(), key=lambda x: -x[1]):
        state_summary[s] = {
            "label": _state_ar(s, domain),
            "duration": _duration_str(secs),
            "seconds": round(secs),
            "pct": round(secs / total_secs * 100, 1),
        }
    
    # ── ON/OFF events for lights/switches/fans ──
    on_off_events = []
    if domain in ("light", "switch", "fan"):
        on_time = None
        for entry in history:
            s = entry["state"]
            t = entry["last_changed"]
            if s == "on" and on_time is None:
                on_time = t
            elif s != "on" and on_time is not None:
                try:
                    t1 = datetime.fromisoformat(on_time.replace("Z", "+00:00"))
                    t2 = datetime.fromisoformat(t.replace("Z", "+00:00"))
                    dur = (t2 - t1).total_seconds()
                    on_off_events.append({
                        "on": _to_kw(on_time),
                        "off": _to_kw(t),
                        "duration": _duration_str(dur),
                        "seconds": round(dur),
                    })
                except Exception:
                    pass
                on_time = None
        if on_time:
            on_off_events.append({"on": _to_kw(on_time), "off": "لسا شغال", "duration": "—"})
    
    # ── Climate temp changes ──
    temp_changes = []
    if domain == "climate":
        prev_temp = None
        for entry in history:
            a = entry.get("attributes", {})
            temp = a.get("temperature")
            if temp and temp != prev_temp:
                temp_changes.append({
                    "time": _to_kw(entry["last_changed"]),
                    "temp_set": temp,
                    "temp_current": a.get("current_temperature"),
                    "state": entry["state"],
                })
                prev_temp = temp
    
    # ── Anomalies ──
    anomalies = []
    unavail_count = sum(1 for t in transitions if t["state"] in ("unavailable", "unknown"))
    if unavail_count > 5:
        anomalies.append(f"الجهاز صار unavailable {unavail_count} مرة — ممكن مشكلة شبكة")
    
    # Rapid toggling (light on/off more than 10 times in period)
    if domain in ("light", "switch", "fan"):
        toggles = sum(1 for t in transitions if t["state"] in ("on", "off"))
        if toggles > 20:
            anomalies.append(f"تبديل متكرر ({toggles} مرة) — ممكن أتمتة خربانة")
    
    # Climate: target changed too many times
    if domain == "climate" and len(temp_changes) > 10:
        anomalies.append(f"الحرارة تغيرت {len(temp_changes)} مرة — ممكن تعارض أتمتات")
    
    # Long unavailable periods
    if "unavailable" in state_durations:
        pct = state_durations["unavailable"] / total_secs * 100
        if pct > 20:
            anomalies.append(f"الجهاز كان غير متاح {pct:.0f}% من الوقت")

    return {
        "entity_id": entity_id,
        "friendly_name": friendly,
        "domain": domain,
        "period": {
            "start": _to_kw(history[0]["last_changed"]) if history else "",
            "end": _to_kw(history[-1]["last_changed"]) if history else "",
            "hours": hours,
        },
        "total_changes": len(transitions),
        "state_summary": state_summary,
        "transitions": transitions,
        "on_off_events": on_off_events,
        "temp_changes": temp_changes,
        "anomalies": anomalies,
    }


# ── formatted report ────────────────────────────────────

async def format_history_report(entity_id: str, hours: int = 24,
                                 start_time: str = None, end_time: str = None,
                                 detail_level: str = "normal") -> str:
    """
    Generate a Telegram-ready Arabic report.
    
    detail_level:
        "brief" — summary only
        "normal" — summary + key events
        "full" — everything including all transitions
    """
    data = await analyze_entity(entity_id, hours, start_time, end_time)
    
    if "error" in data:
        return f"\u274c {data['error']}"
    
    lines = []
    domain = data["domain"]
    name = data["friendly_name"]
    period = data["period"]
    
    lines.append(f"\U0001f4cb تقرير: {name}")
    lines.append(f"\u23f0 الفترة: {period['start']} → {period['end']}")
    lines.append(f"\U0001f504 عدد التغييرات: {data['total_changes']}")
    lines.append("")
    
    # State summary
    lines.append("\U0001f4ca ملخص الحالات:")
    for state, info in data["state_summary"].items():
        bar = "\u2588" * max(1, int(info["pct"] / 5))
        lines.append(f"  {info['label']}: {info['duration']} ({info['pct']}%) {bar}")
    lines.append("")
    
    # Domain-specific
    if domain in ("light", "switch", "fan") and data["on_off_events"]:
        lines.append("\U0001f4a1 أوقات التشغيل:")
        events = data["on_off_events"]
        show = events if detail_level == "full" else events[:10]
        for e in show:
            lines.append(f"  \u25b6 {e['on']} → {e['off']} ({e['duration']})")
        if len(events) > 10 and detail_level != "full":
            lines.append(f"  ... و {len(events)-10} مرة أخرى")
        lines.append("")
    
    if domain == "climate" and data["temp_changes"]:
        lines.append("\U0001f321 تغييرات الحرارة:")
        changes = data["temp_changes"]
        show = changes if detail_level == "full" else changes[:10]
        for c in show:
            curr = f" (فعلي: {c['temp_current']}°)" if c.get("temp_current") else ""
            lines.append(f"  {c['time']} → {c['temp_set']}°{curr}")
        if len(changes) > 10 and detail_level != "full":
            lines.append(f"  ... و {len(changes)-10} تغيير آخر")
        lines.append("")
    
    if detail_level in ("normal", "full"):
        lines.append("\U0001f5d3 آخر الأحداث:")
        trans = data["transitions"]
        show = trans[-15:] if detail_level == "normal" else trans
        for t in show:
            extra = ""
            if domain == "climate":
                if t.get("temp_set"):
                    extra = f" | {t['temp_set']}°"
                if t.get("temp_current"):
                    extra += f" (فعلي: {t['temp_current']}°)"
            fr = f"{t.get('from_ar','')} → " if t.get("from_ar") else ""
            lines.append(f"  {_to_kw_short(t['time'])} {fr}{t['state_ar']}{extra}")
        lines.append("")
    
    # Anomalies
    if data["anomalies"]:
        lines.append("\u26a0\ufe0f مشاكل مكتشفة:")
        for a in data["anomalies"]:
            lines.append(f"  \u2022 {a}")
        lines.append("")
    
    return "\n".join(lines)
