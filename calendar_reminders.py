"""calendar_reminders.py — Reminder loop for Master AI v8 Calendar

Background task that checks for due reminders every 60 seconds
and sends them via Telegram.
"""

import asyncio
import logging
from datetime import datetime

from calendar_db import get_due_reminders, mark_reminder_sent

logger = logging.getLogger("calendar_reminders")

CHECK_INTERVAL = 60  # seconds
QUIET_HOURS_START = 0   # 12:30 AM
QUIET_HOURS_END = 6     # 6:00 AM


def _format_reminder(r):
    """Format reminder message for Telegram."""
    summary = r.get("summary", "بدون عنوان")
    start_ts = r.get("start_ts", "")
    location = r.get("location")
    offset = r.get("offset_minutes", 0)
    rtype = r.get("reminder_type", "pre_event")

    try:
        start_dt = datetime.strptime(start_ts, "%Y-%m-%d %H:%M:%S")
        h = start_dt.hour
        m = start_dt.minute
        period = "صباحاً" if h < 12 else "مساءً"
        h12 = h if h <= 12 else h - 12
        if h12 == 0:
            h12 = 12
        time_str = f"{h12}:{m:02d} {period}" if m else f"{h12} {period}"
    except Exception:
        time_str = start_ts

    if rtype == "allday":
        msg = f"📅 تذكير: {summary} (اليوم)"
    elif offset <= 15:
        msg = f"⏰ بعد شوي! {summary} الساعة {time_str}"
    else:
        mins = offset
        if mins >= 60:
            hrs = mins // 60
            msg = f"⏰ تذكير: {summary} بعد {hrs} ساعة ({time_str})"
        else:
            msg = f"⏰ تذكير: {summary} بعد {mins} دقيقة ({time_str})"

    if location:
        msg += f"\n📍 {location}"

    return msg


def _in_quiet_hours():
    """Check if we're in quiet hours (no reminders)."""
    h = datetime.now().hour
    return QUIET_HOURS_START <= h < QUIET_HOURS_END


async def run_reminder_loop(send_fn):
    """Background loop: check and send due reminders every 60 seconds.
    
    Args:
        send_fn: async function(text) that sends a Telegram message
    """
    logger.info("Calendar reminder loop started")
    await asyncio.sleep(60)  # Wait for system startup

    while True:
        try:
            if _in_quiet_hours():
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            due = get_due_reminders()
            for r in due:
                # Skip if event was cancelled
                if r.get("event_status") == "cancelled":
                    mark_reminder_sent(r["id"])
                    continue

                msg = _format_reminder(r)
                try:
                    await send_fn(msg)
                    mark_reminder_sent(r["id"])
                    logger.info(f"Reminder sent: {r.get('summary', '?')}")
                except Exception as e:
                    logger.error(f"Reminder send error: {e}")

        except Exception as e:
            logger.error(f"Reminder loop error: {e}")

        await asyncio.sleep(CHECK_INTERVAL)
