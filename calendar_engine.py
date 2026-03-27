"""calendar_engine.py — Google Calendar Sync Engine for Master AI v8

Core responsibilities:
- Full sync and incremental sync with Google Calendar API
- Event CRUD operations (create, delete via Google then local cache)
- Background sync loop
- Time range queries from local cache

Uses: calendar_db.py, google_auth_ext.py
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta

from calendar_db import (
    get_db, init_life_db, upsert_event, mark_deleted,
    get_events_range, save_sync_state, load_sync_state,
    clear_sync_state, insert_reminder, cancel_event_reminders,
    get_event_by_google_id, delete_event_local
)

logger = logging.getLogger("calendar_engine")

# Config
SYNC_INTERVAL = 300          # 5 minutes between incremental syncs
SYNC_WINDOW_DAYS_BACK = 7   # Sync events from 7 days ago
SYNC_WINDOW_DAYS_FORWARD = 60  # Sync events up to 60 days ahead
DEFAULT_EVENT_DURATION = 60  # minutes
TIMEZONE = "Asia/Kuwait"

# Default reminder offsets (minutes before event)
DEFAULT_REMINDERS = [60, 15]  # 1 hour and 15 min before
ALLDAY_REMINDER_HOUR = 9     # 9:00 AM for all-day events


def _parse_google_event(g_event: dict, source_key: str = "google_primary") -> dict | None:
    """Convert Google Calendar event to our internal format."""
    eid = g_event.get("id")
    if not eid:
        return None

    status = g_event.get("status", "confirmed")

    # Parse start/end
    start = g_event.get("start", {})
    end = g_event.get("end", {})

    is_all_day = "date" in start
    if is_all_day:
        start_ts = start["date"] + " 00:00:00"
        end_ts = end.get("date", start["date"]) + " 00:00:00"
    else:
        # dateTime format: 2026-03-15T10:00:00+03:00
        start_dt = start.get("dateTime", "")
        end_dt = end.get("dateTime", "")
        # Convert to local naive datetime string
        start_ts = _iso_to_local(start_dt)
        end_ts = _iso_to_local(end_dt)

    if not start_ts:
        return None

    return {
        "source_key": source_key,
        "google_event_id": eid,
        "ical_uid": g_event.get("iCalUID"),
        "status": status,
        "summary": g_event.get("summary"),
        "description": g_event.get("description"),
        "location": g_event.get("location"),
        "start_ts": start_ts,
        "end_ts": end_ts,
        "is_all_day": 1 if is_all_day else 0,
        "timezone": start.get("timeZone", TIMEZONE),
        "html_link": g_event.get("htmlLink"),
        "creator_email": g_event.get("creator", {}).get("email"),
        "organizer_email": g_event.get("organizer", {}).get("email"),
        "raw_json": json.dumps(g_event, ensure_ascii=False),
        "etag": g_event.get("etag"),
        "updated_google_ts": g_event.get("updated"),
        "is_deleted_local": 1 if status == "cancelled" else 0,
    }


def _iso_to_local(iso_str: str) -> str:
    """Convert ISO datetime string to local naive datetime string."""
    if not iso_str:
        return ""
    try:
        from datetime import timezone as tz
        dt = datetime.fromisoformat(iso_str)
        # Convert to Kuwait time (UTC+3)
        if dt.tzinfo:
            kuwait_offset = timedelta(hours=3)
            dt = dt.astimezone(tz(kuwait_offset)).replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        logger.warning(f"Date parse error for {iso_str}: {e}")
        return iso_str[:19].replace("T", " ")


def _get_calendar_service():
    """Get Google Calendar API service."""
    try:
        from google_auth_ext import build_calendar_service
        return build_calendar_service()
    except Exception as e:
        logger.error(f"Cannot build calendar service: {e}")
        return None


# ═══ Sync Operations ═══

async def sync_full(source_key: str = "google_primary") -> dict:
    """Full sync: fetch all events in window and rebuild local cache."""
    service = _get_calendar_service()
    if not service:
        return {"ok": False, "error": "Calendar service unavailable"}

    now = datetime.now()
    time_min = (now - timedelta(days=SYNC_WINDOW_DAYS_BACK)).isoformat() + "+03:00"
    time_max = (now + timedelta(days=SYNC_WINDOW_DAYS_FORWARD)).isoformat() + "+03:00"

    try:
        events = []
        page_token = None
        sync_token = None

        while True:
            result = service.events().list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                maxResults=250,
                pageToken=page_token,
            ).execute()

            for item in result.get("items", []):
                parsed = _parse_google_event(item, source_key)
                if parsed:
                    if parsed["status"] == "cancelled":
                        mark_deleted(source_key, parsed["google_event_id"])
                    else:
                        upsert_event(parsed)
                    events.append(parsed)

            page_token = result.get("nextPageToken")
            if not page_token:
                sync_token = result.get("nextSyncToken")
                break

        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        save_sync_state(
            source_key,
            sync_token=sync_token,
            last_full_sync_at=now_str,
            last_incremental_sync_at=now_str,
            last_status="full_sync_ok",
            last_error=None,
            failure_count=0,
        )

        logger.info(f"Full sync complete: {len(events)} events")
        return {"ok": True, "events_synced": len(events), "sync_token": bool(sync_token)}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Full sync error: {error_msg}")
        state = load_sync_state(source_key)
        fc = (state.get("failure_count", 0) + 1) if state else 1
        save_sync_state(source_key, last_status="full_sync_error",
                        last_error=error_msg, failure_count=fc)
        return {"ok": False, "error": error_msg}


async def sync_incremental(source_key: str = "google_primary") -> dict:
    """Incremental sync using syncToken."""
    state = load_sync_state(source_key)
    if not state or not state.get("sync_token"):
        logger.info("No sync token — falling back to full sync")
        return await sync_full(source_key)

    service = _get_calendar_service()
    if not service:
        return {"ok": False, "error": "Calendar service unavailable"}

    try:
        changes = 0
        page_token = None
        new_sync_token = None

        while True:
            result = service.events().list(
                calendarId="primary",
                syncToken=state["sync_token"],
                pageToken=page_token,
                maxResults=250,
            ).execute()

            for item in result.get("items", []):
                parsed = _parse_google_event(item, source_key)
                if parsed:
                    if parsed["status"] == "cancelled":
                        mark_deleted(source_key, parsed["google_event_id"])
                    else:
                        upsert_event(parsed)
                    changes += 1

            page_token = result.get("nextPageToken")
            if not page_token:
                new_sync_token = result.get("nextSyncToken")
                break

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_sync_state(
            source_key,
            sync_token=new_sync_token or state["sync_token"],
            last_incremental_sync_at=now_str,
            last_status="incremental_ok",
            last_error=None,
            failure_count=0,
        )

        if changes:
            logger.info(f"Incremental sync: {changes} changes")
        return {"ok": True, "changes": changes}

    except Exception as e:
        error_msg = str(e)
        # Google returns 410 GONE when syncToken expires
        if "410" in error_msg or "GONE" in error_msg.upper():
            logger.warning("Sync token expired (410 GONE) — doing full resync")
            clear_sync_state(source_key)
            return await sync_full(source_key)

        logger.error(f"Incremental sync error: {error_msg}")
        fc = (state.get("failure_count", 0) + 1) if state else 1
        save_sync_state(source_key, last_status="incremental_error",
                        last_error=error_msg, failure_count=fc)
        return {"ok": False, "error": error_msg}


async def ensure_fresh_cache(max_age_seconds: int = 120, source_key: str = "google_primary") -> bool:
    """Ensure cache is fresh enough, sync if needed. Returns True if cache is fresh."""
    state = load_sync_state(source_key)
    if not state or not state.get("last_incremental_sync_at"):
        await sync_full(source_key)
        return True

    last_sync = datetime.strptime(state["last_incremental_sync_at"], "%Y-%m-%d %H:%M:%S")
    age = (datetime.now() - last_sync).total_seconds()

    if age > max_age_seconds:
        result = await sync_incremental(source_key)
        return result.get("ok", False)

    return True


# ═══ Query Operations (from local cache) ═══

def get_today_events(source_key: str = "google_primary") -> list:
    """Get today's events from cache."""
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
    end = now.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M:%S")
    return get_events_range(start, end, source_key)


def get_tomorrow_events(source_key: str = "google_primary") -> list:
    """Get tomorrow's events from cache."""
    tomorrow = datetime.now() + timedelta(days=1)
    start = tomorrow.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
    end = tomorrow.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M:%S")
    return get_events_range(start, end, source_key)


def get_week_events(source_key: str = "google_primary") -> list:
    """Get this week's events (today + 6 days) from cache."""
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
    end = (now + timedelta(days=6)).replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M:%S")
    return get_events_range(start, end, source_key)


# ═══ Create / Delete via Google ═══

async def create_event(title: str, start_iso: str, end_iso: str,
                       location: str = None, description: str = None,
                       is_all_day: bool = False, chat_id: str = None,
                       reminder_offsets: list = None) -> dict:
    """Create event on Google Calendar, then cache locally + create reminders."""
    service = _get_calendar_service()
    if not service:
        return {"ok": False, "error": "Calendar service unavailable — check /google/auth"}

    # Build Google event body
    body = {"summary": title}
    if description:
        body["description"] = description
    if location:
        body["location"] = location

    if is_all_day:
        body["start"] = {"date": start_iso[:10]}
        body["end"] = {"date": end_iso[:10]}
    else:
        body["start"] = {"dateTime": start_iso, "timeZone": TIMEZONE}
        body["end"] = {"dateTime": end_iso, "timeZone": TIMEZONE}

    try:
        result = service.events().insert(calendarId="primary", body=body).execute()
        google_id = result["id"]

        # Cache locally
        parsed = _parse_google_event(result)
        if parsed:
            local_id = upsert_event(parsed)

            # Create reminders
            offsets = reminder_offsets or DEFAULT_REMINDERS
            _create_reminders_for_event(local_id, parsed, offsets, chat_id)

        logger.info(f"Event created: {title} ({google_id})")
        return {
            "ok": True,
            "google_event_id": google_id,
            "local_id": local_id if parsed else None,
            "summary": title,
            "start": start_iso,
            "end": end_iso,
            "html_link": result.get("htmlLink"),
        }

    except Exception as e:
        logger.error(f"Create event error: {e}")
        return {"ok": False, "error": str(e)}


async def delete_event(google_event_id: str, source_key: str = "google_primary") -> dict:
    """Delete event from Google Calendar, then update local cache."""
    service = _get_calendar_service()
    if not service:
        return {"ok": False, "error": "Calendar service unavailable"}

    try:
        service.events().delete(calendarId="primary", eventId=google_event_id).execute()
        mark_deleted(source_key, google_event_id)

        # Cancel pending reminders
        ev = get_event_by_google_id(source_key, google_event_id)
        if ev:
            cancel_event_reminders(ev["id"])

        logger.info(f"Event deleted: {google_event_id}")
        return {"ok": True, "google_event_id": google_event_id}

    except Exception as e:
        logger.error(f"Delete event error: {e}")
        return {"ok": False, "error": str(e)}


# ═══ Reminders ═══

def _create_reminders_for_event(local_id: int, event: dict, offsets: list, chat_id: str = None):
    """Create reminder entries for an event."""
    try:
        start_ts = event["start_ts"]
        start_dt = datetime.strptime(start_ts, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()

        if event.get("is_all_day"):
            # All-day event: remind at 9:00 AM on event day
            remind_at = start_dt.replace(hour=ALLDAY_REMINDER_HOUR, minute=0)
            if remind_at > now:
                insert_reminder(local_id, "allday", 0, remind_at.strftime("%Y-%m-%d %H:%M:%S"), chat_id)
        else:
            for offset in offsets:
                remind_at = start_dt - timedelta(minutes=offset)
                # Skip if reminder time is in the past
                if remind_at <= now:
                    continue
                # If event is very soon (<2hrs), only keep 15min reminder
                time_until = (start_dt - now).total_seconds() / 60
                if time_until < 120 and offset > 15:
                    continue
                insert_reminder(local_id, "pre_event", offset,
                                remind_at.strftime("%Y-%m-%d %H:%M:%S"), chat_id)
    except Exception as e:
        logger.error(f"Create reminders error: {e}")


# ═══ Background Sync Loop ═══

async def calendar_sync_loop():
    """Background loop: incremental sync every SYNC_INTERVAL seconds."""
    logger.info("Calendar sync loop started")
    # Wait for system startup
    await asyncio.sleep(30)

    # Initial sync
    init_life_db()
    await sync_full()

    while True:
        try:
            await asyncio.sleep(SYNC_INTERVAL)
            await sync_incremental()
        except Exception as e:
            logger.error(f"Sync loop error: {e}")
            await asyncio.sleep(60)
