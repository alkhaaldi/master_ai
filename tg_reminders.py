"""Phase B4: Telegram Reminders — /remind and /reminders commands.

Set reminders that fire at specific times via Telegram.
Supports: /remind 5m check oven, /remind 14:30 call doctor, /remind 2h meeting
"""
import asyncio, logging, re, json, os
from datetime import datetime, timedelta

logger = logging.getLogger("tg_remind")

# In-memory reminder store (survives until restart)
_reminders = []  # [{id, chat_id, fire_at, message, created}]
_next_id = 1
_sender_fn = None

ARABIC_MONTHS = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل",
    5: "مايو", 6: "يونيو", 7: "يوليو", 8: "أغسطس",
    9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر"
}

def _parse_time(time_str: str) -> datetime | None:
    """Parse time string to datetime.
    Supports: 5m, 2h, 30s, 14:30, 2:00PM
    """
    time_str = time_str.strip().lower()
    now = datetime.now()

    # Relative: 5m, 2h, 30s, 1d
    m = re.match(r"^(\d+)\s*(s|m|h|d|sec|min|hour|day|دقيقة|دقائق|ساعة|ساعات|يوم)$", time_str)
    if m:
        val = int(m.group(1))
        unit = m.group(2)
        if unit in ("s", "sec"):
            return now + timedelta(seconds=val)
        elif unit in ("m", "min", "دقيقة", "دقائق"):
            return now + timedelta(minutes=val)
        elif unit in ("h", "hour", "ساعة", "ساعات"):
            return now + timedelta(hours=val)
        elif unit in ("d", "day", "يوم"):
            return now + timedelta(days=val)

    # Absolute: 14:30 or 2:30PM
    m = re.match(r"^(\d{1,2}):(\d{2})\s*(am|pm)?$", time_str)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        ampm = m.group(3)
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)  # Next day
        return target

    return None


def add_reminder(chat_id: int, time_str: str, message: str) -> str:
    """Add a new reminder. Returns confirmation text."""
    global _next_id
    fire_at = _parse_time(time_str)
    if not fire_at:
        return "\u26a0\ufe0f ما فهمت الوقت. أمثلة: 5m, 2h, 14:30, 3:00PM"

    reminder = {
        "id": _next_id,
        "chat_id": chat_id,
        "fire_at": fire_at,
        "message": message,
        "created": datetime.now(),
    }
    _reminders.append(reminder)
    _next_id += 1

    delta = fire_at - datetime.now()
    if delta.total_seconds() < 3600:
        time_desc = f"{int(delta.total_seconds() / 60)} دقيقة"
    elif delta.total_seconds() < 86400:
        time_desc = f"{delta.total_seconds() / 3600:.1f} ساعة"
    else:
        time_desc = f"{delta.days} يوم"

    fire_str = fire_at.strftime("%H:%M")
    return f"\u23f0 تم! تذكير بعد {time_desc} (الساعة {fire_str}):\n\u2022 {message}"


def list_reminders(chat_id: int) -> str:
    """List active reminders for a chat."""
    active = [r for r in _reminders if r["chat_id"] == chat_id and r["fire_at"] > datetime.now()]
    if not active:
        return "\u2705 ما عندك تذكيرات حالياً"

    lines = ["\u23f0 التذكيرات النشطة:\n"]
    for r in sorted(active, key=lambda x: x["fire_at"]):
        fire_str = r["fire_at"].strftime("%H:%M")
        delta = r["fire_at"] - datetime.now()
        if delta.total_seconds() < 3600:
            remaining = f"{int(delta.total_seconds() / 60)}د"
        else:
            remaining = f"{delta.total_seconds() / 3600:.1f}س"
        lines.append(f"  {r['id']}. [{fire_str}] ({remaining}) — {r['message']}")
    return "\n".join(lines)


def cancel_reminder(reminder_id: int, chat_id: int) -> str:
    """Cancel a reminder by ID."""
    for i, r in enumerate(_reminders):
        if r["id"] == reminder_id and r["chat_id"] == chat_id:
            _reminders.pop(i)
            return f"\u2705 تم إلغاء التذكير #{reminder_id}"
    return "\u26a0\ufe0f تذكير غير موجود"


async def reminder_loop(sender_fn):
    """Background loop that fires reminders."""
    global _sender_fn
    _sender_fn = sender_fn
    logger.info("\u23f0 Reminder loop started")
    while True:
        try:
            now = datetime.now()
            fired = []
            for r in _reminders:
                if r["fire_at"] <= now:
                    try:
                        msg = f"\u23f0 تذكير!\n\n{r['message']}"
                        await sender_fn(r["chat_id"], msg)
                        fired.append(r)
                    except Exception as e:
                        logger.error(f"Reminder send error: {e}")
                        fired.append(r)  # Remove even if failed
            for r in fired:
                _reminders.remove(r)
        except Exception as e:
            logger.error(f"Reminder loop error: {e}")
        await asyncio.sleep(15)  # Check every 15 seconds
