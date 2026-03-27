"""calendar_reporting.py — Telegram-formatted calendar reports for Master AI v8

Renders: /today, /tomorrow, /week, /agenda, morning report section.
Uses: calendar_engine (local cache), life_work (shift info).
"""

import logging
from datetime import datetime, date, timedelta
from collections import defaultdict

logger = logging.getLogger("calendar_reporting")

ARABIC_DAYS = {
    "Saturday": "السبت", "Sunday": "الأحد",
    "Monday": "الاثنين", "Tuesday": "الثلاثاء",
    "Wednesday": "الأربعاء", "Thursday": "الخميس",
    "Friday": "الجمعة"
}


# Shift patterns to filter out (already shown via life_work.py)
_SHIFT_PATTERNS = {
    "1st morning", "2nd morning", "1st afternoon", "2nd afternoon",
    "1st night", "2nd night", "1st off", "2nd off",
    "morning", "afternoon", "night", "off",
}


def _is_shift_event(event):
    """Check if event is a shift calendar entry (should be filtered out)."""
    summary = (event.get("summary") or "").strip().lower()
    return summary in _SHIFT_PATTERNS


def _filter_events(events):
    """Remove shift events from list (they're calculated by life_work.py)."""
    return [e for e in events if not _is_shift_event(e)]


def _get_shift(target_date):
    """Get shift info for a date."""
    try:
        from life_work import get_shift
        return get_shift(target_date)
    except Exception:
        return None


def _format_time(ts_str):
    """Format timestamp to readable time."""
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        h = dt.hour
        m = dt.minute
        period = "صباحاً" if h < 12 else "مساءً"
        h12 = h if h <= 12 else h - 12
        if h12 == 0:
            h12 = 12
        if m:
            return f"{h12}:{m:02d} {period}"
        return f"{h12} {period}"
    except Exception:
        return ts_str


def _format_event_line(event):
    """Format single event as Telegram line."""
    if event.get("is_all_day"):
        return f"  📅 {event.get('summary', 'بدون عنوان')} (طول اليوم)"
    time_str = _format_time(event["start_ts"])
    title = event.get("summary", "بدون عنوان")
    loc = event.get("location")
    line = f"  ⏰ {time_str} — {title}"
    if loc:
        line += f" 📍{loc}"
    return line


def _shift_line(shift_info):
    """Format shift info line."""
    if not shift_info:
        return ""
    emoji = shift_info.get("emoji", "")
    name = shift_info.get("shift", "")
    times = shift_info.get("times", "")
    return f"{emoji} الشفت: {name} ({times})"


def _check_shift_conflict(event, shift_info):
    """Check if event conflicts with shift. Returns conflict text or None."""
    if not shift_info or shift_info.get("shift") == "إجازة":
        return None
    if event.get("is_all_day"):
        return None
    try:
        ev_start = datetime.strptime(event["start_ts"], "%Y-%m-%d %H:%M:%S")
        ev_end = datetime.strptime(event["end_ts"], "%Y-%m-%d %H:%M:%S")
        shift = shift_info["shift"]
        if shift == "صباحي":
            s_start, s_end = 7, 15
        elif shift == "عصري":
            s_start, s_end = 15, 23
        elif shift == "ليلي":
            s_start, s_end = 23, 7
        else:
            return None
        if shift == "ليلي":
            if ev_start.hour >= 23 or ev_start.hour < 7:
                return f"⚠️ تعارض مع شفتك الليلي!"
        else:
            if s_start <= ev_start.hour < s_end:
                return f"⚠️ تعارض مع شفتك ال{shift}!"
    except Exception:
        pass
    return None


def render_today(events, target_date=None):
    """Render today's agenda for Telegram."""
    events = _filter_events(events)
    if target_date is None:
        target_date = date.today()
    day_name = ARABIC_DAYS.get(target_date.strftime("%A"), "")
    shift_info = _get_shift(target_date)
    lines = [f"📆 *{day_name} {target_date.strftime('%Y-%m-%d')}*"]
    if shift_info:
        lines.append(_shift_line(shift_info))
    lines.append("")
    if not events:
        lines.append("✅ ما عندك مواعيد اليوم — يومك فاضي!")
    else:
        lines.append(f"📊 {len(events)} موعد:")
        for ev in events:
            lines.append(_format_event_line(ev))
            conflict = _check_shift_conflict(ev, shift_info)
            if conflict:
                lines.append(f"    {conflict}")
    return "\n".join(lines)


def render_tomorrow(events, target_date=None):
    """Render tomorrow's agenda."""
    events = _filter_events(events)
    if target_date is None:
        target_date = date.today() + timedelta(days=1)
    day_name = ARABIC_DAYS.get(target_date.strftime("%A"), "")
    shift_info = _get_shift(target_date)
    lines = [f"📆 *باجر {day_name} {target_date.strftime('%Y-%m-%d')}*"]
    if shift_info:
        lines.append(_shift_line(shift_info))
    lines.append("")
    if not events:
        lines.append("✅ باجر فاضي — لا مواعيد")
    else:
        lines.append(f"📊 {len(events)} موعد:")
        for ev in events:
            lines.append(_format_event_line(ev))
            conflict = _check_shift_conflict(ev, shift_info)
            if conflict:
                lines.append(f"    {conflict}")
    return "\n".join(lines)


def render_week(events):
    """Render week view grouped by day."""
    today = date.today()
    by_day = defaultdict(list)
    for ev in events:
        try:
            d = datetime.strptime(ev["start_ts"], "%Y-%m-%d %H:%M:%S").date()
            by_day[d].append(ev)
        except Exception:
            pass
    lines = ["🗓️ *مواعيد الأسبوع:*", ""]
    for i in range(7):
        d = today + timedelta(days=i)
        day_name = ARABIC_DAYS.get(d.strftime("%A"), "")
        shift_info = _get_shift(d)
        shift_short = shift_info.get("emoji", "") + shift_info.get("shift", "") if shift_info else ""
        day_events = _filter_events(by_day.get(d, []))
        if day_events:
            lines.append(f"*{day_name} {d.strftime('%m/%d')}* ({shift_short}) — {len(day_events)} موعد:")
            for ev in day_events:
                lines.append(_format_event_line(ev))
        else:
            lines.append(f"{day_name} {d.strftime('%m/%d')} ({shift_short}) — فاضي")
    return "\n".join(lines)


def render_morning_calendar_section(events, target_date=None):
    """Short calendar section for morning report."""
    events = _filter_events(events)
    if target_date is None:
        target_date = date.today()
    if not events:
        return "📅 لا مواعيد اليوم"
    lines = [f"📅 مواعيد اليوم ({len(events)}):"]
    shift_info = _get_shift(target_date)
    for ev in events[:3]:
        lines.append(_format_event_line(ev))
        conflict = _check_shift_conflict(ev, shift_info)
        if conflict:
            lines.append(f"    {conflict}")
    if len(events) > 3:
        lines.append(f"  ... و{len(events)-3} مواعيد أخرى")
    return "\n".join(lines)
