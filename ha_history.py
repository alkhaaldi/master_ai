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
    """Generate a Telegram-ready Arabic report — smart per domain."""
    data = await analyze_entity(entity_id, hours, start_time, end_time)
    
    if "error" in data:
        return f"\u274c {data['error']}"
    
    lines = []
    domain = data["domain"]
    name = data["friendly_name"]
    period = data["period"]
    
    lines.append(f"\U0001f4cb \u062a\u0642\u0631\u064a\u0631: {name}")
    lines.append(f"\u23f0 \u0627\u0644\u0641\u062a\u0631\u0629: {period['start']} \u2192 {period['end']}")
    lines.append("")
    
    # == Climate: temp changes + smart summary ==
    if domain == "climate":
        tc = data["temp_changes"]
        if tc:
            lines.append(f"\U0001f321 \u062a\u063a\u064a\u064a\u0631\u0627\u062a \u0627\u0644\u062d\u0631\u0627\u0631\u0629 ({len(tc)} \u062a\u063a\u064a\u064a\u0631):")
            show = tc if detail_level == "full" else tc[:15]
            for c in show:
                curr = f" (\u0627\u0644\u063a\u0631\u0641\u0629: {c['temp_current']}\u00b0)" if c.get("temp_current") else ""
                lines.append(f"  {c['time']} \u2192 {c['temp_set']}\u00b0{curr}")
            if len(tc) > 15 and detail_level != "full":
                lines.append(f"  ... \u0648 {len(tc)-15} \u062a\u063a\u064a\u064a\u0631 \u0622\u062e\u0631")
            lines.append("")
            
            temps = [c["temp_set"] for c in tc if c.get("temp_set")]
            if temps:
                lines.append("\U0001f4ca \u0645\u0644\u062e\u0635:")
                lines.append(f"  \u0623\u0642\u0644 \u062d\u0631\u0627\u0631\u0629 \u0645\u0637\u0644\u0648\u0628\u0629: {min(temps)}\u00b0")
                lines.append(f"  \u0623\u0639\u0644\u0649 \u062d\u0631\u0627\u0631\u0629 \u0645\u0637\u0644\u0648\u0628\u0629: {max(temps)}\u00b0")
                lines.append(f"  \u0622\u062e\u0631 \u0625\u0639\u062f\u0627\u062f: {temps[-1]}\u00b0")
                curr_temps = [c["temp_current"] for c in tc if c.get("temp_current")]
                if curr_temps:
                    lines.append(f"  \u062d\u0631\u0627\u0631\u0629 \u0627\u0644\u063a\u0631\u0641\u0629 \u0627\u0644\u062d\u0627\u0644\u064a\u0629: {curr_temps[-1]}\u00b0")
                lines.append("")
            
            if len(temps) > 5:
                lines.append("\U0001f50d \u062a\u062d\u0644\u064a\u0644:")
                from collections import Counter
                hours_count = Counter()
                for c in tc:
                    h = c["time"].split(" ")[1][:2] if " " in c["time"] else "?"
                    hours_count[h] += 1
                busy = [(h, cnt) for h, cnt in hours_count.items() if cnt >= 3]
                if busy:
                    busy.sort(key=lambda x: -x[1])
                    for h, cnt in busy[:3]:
                        lines.append(f"  \u26a0\ufe0f \u0627\u0644\u0633\u0627\u0639\u0629 {h}:00 \u2014 {cnt} \u062a\u063a\u064a\u064a\u0631\u0627\u062a (\u062a\u0639\u062f\u064a\u0644 \u064a\u062f\u0648\u064a \u0623\u0648 \u062a\u0639\u0627\u0631\u0636 \u0623\u062a\u0645\u062a\u0629)")
                lines.append("")
        else:
            lines.append("\u0644\u0627 \u062a\u0648\u062c\u062f \u062a\u063a\u064a\u064a\u0631\u0627\u062a \u0628\u0627\u0644\u062d\u0631\u0627\u0631\u0629 \u062e\u0644\u0627\u0644 \u0647\u0630\u064a \u0627\u0644\u0641\u062a\u0631\u0629")
            lines.append("")
    
    # == Lights/Switches/Fans ==
    elif domain in ("light", "switch", "fan"):
        events = data["on_off_events"]
        summary = data["state_summary"]
        
        if summary:
            on_info = summary.get("on", {})
            off_info = summary.get("off", {})
            if on_info:
                lines.append(f"\U0001f4a1 \u0634\u063a\u0627\u0644: {on_info['duration']} ({on_info['pct']}%)")
            if off_info:
                lines.append(f"\U0001f311 \u0645\u0637\u0641\u064a: {off_info['duration']} ({off_info['pct']}%)")
            lines.append("")
        
        if events:
            lines.append(f"\U0001f50c \u0623\u0648\u0642\u0627\u062a \u0627\u0644\u062a\u0634\u063a\u064a\u0644 ({len(events)} \u0645\u0631\u0629):")
            show = events if detail_level == "full" else events[:15]
            for e in show:
                lines.append(f"  \u25b6 {e['on']} \u2192 {e['off']} ({e['duration']})")
            if len(events) > 15 and detail_level != "full":
                lines.append(f"  ... \u0648 {len(events)-15} \u0645\u0631\u0629 \u0623\u062e\u0631\u0649")
            lines.append("")
        else:
            lines.append("\u0627\u0644\u062c\u0647\u0627\u0632 \u0645\u0627 \u0627\u0634\u062a\u063a\u0644 \u062e\u0644\u0627\u0644 \u0647\u0630\u064a \u0627\u0644\u0641\u062a\u0631\u0629")
            lines.append("")
    
    # == Covers ==
    elif domain == "cover":
        summary = data["state_summary"]
        if summary:
            for state, info in summary.items():
                lines.append(f"  {info['label']}: {info['duration']} ({info['pct']}%)")
            lines.append("")
        trans = data["transitions"]
        if trans:
            lines.append(f"\U0001f5d3 \u0627\u0644\u062d\u0631\u0643\u0627\u062a ({len(trans)} \u062d\u0631\u0643\u0629):")
            show = trans if detail_level == "full" else trans[:15]
            for t in show:
                fr = f"{t.get('from_ar','')} \u2192 " if t.get("from_ar") else ""
                pos = f" ({t['position']}%)" if t.get("position") is not None else ""
                lines.append(f"  {_to_kw_short(t['time'])} {fr}{t['state_ar']}{pos}")
            lines.append("")
    
    # == Media players ==
    elif domain == "media_player":
        summary = data["state_summary"]
        if summary:
            for state, info in summary.items():
                lines.append(f"  {info['label']}: {info['duration']} ({info['pct']}%)")
            lines.append("")
        trans = data["transitions"]
        if trans:
            lines.append("\U0001f3b5 \u0627\u0644\u0646\u0634\u0627\u0637:")
            show = trans[-15:]
            for t in show:
                extra = ""
                if t.get("media_title"):
                    extra = f" | {t['media_title']}"
                elif t.get("source"):
                    extra = f" | {t['source']}"
                lines.append(f"  {_to_kw_short(t['time'])} {t['state_ar']}{extra}")
            lines.append("")
    
    # == Default ==
    else:
        summary = data["state_summary"]
        if summary:
            lines.append("\U0001f4ca \u0645\u0644\u062e\u0635 \u0627\u0644\u062d\u0627\u0644\u0627\u062a:")
            for state, info in summary.items():
                bar = "\u2588" * max(1, int(info["pct"] / 5))
                lines.append(f"  {info['label']}: {info['duration']} ({info['pct']}%) {bar}")
            lines.append("")
        trans = data["transitions"]
        if trans and detail_level in ("normal", "full"):
            lines.append("\U0001f5d3 \u0622\u062e\u0631 \u0627\u0644\u0623\u062d\u062f\u0627\u062b:")
            show = trans[-15:] if detail_level == "normal" else trans
            for t in show:
                fr = f"{t.get('from_ar','')} \u2192 " if t.get("from_ar") else ""
                lines.append(f"  {_to_kw_short(t['time'])} {fr}{t['state_ar']}")
            lines.append("")
    
    # == Anomalies ==
    if data["anomalies"]:
        lines.append("\u26a0\ufe0f \u0645\u0634\u0627\u0643\u0644 \u0645\u0643\u062a\u0634\u0641\u0629:")
        for a in data["anomalies"]:
            lines.append(f"  \u2022 {a}")
        lines.append("")
    
    return "\n".join(lines)
