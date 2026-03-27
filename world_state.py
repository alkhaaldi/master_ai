"""
world_state.py — Home Assistant World State Snapshot Cache
Refreshes every 30s in background. Tools read from cache instead of hitting HA every time.
Version: 1.1

Usage:
    from world_state import start_world_state, get_snapshot_text, get_snapshot_data

    # In server.py lifespan:
    await start_world_state()

    # In chat_v7.py system prompt:
    snapshot = get_snapshot_text()
"""
import asyncio
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger("world_state")

HA_URL = os.getenv("HA_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")

# Cache
_snapshot: dict = {}
_snapshot_text: str = ""
_last_refresh: float = 0
_refresh_interval: int = 30  # seconds
_task = None

# Domains we care about
TRACKED_DOMAINS = {"light", "climate", "cover", "fan", "media_player"}
SKIP_PATTERNS = {"backlight", "update.", "sensor.", "binary_sensor.",
                 "automation.", "script.", "input_", "switch."}

# Arabic domain labels
DOMAIN_AR = {
    "light": "الأنوار",
    "climate": "المكيفات",
    "cover": "الستائر",
    "fan": "المراوح والمنقيات",
    "media_player": "السماعات والشاشات",
}

# Room name mappings (entity_id prefix → Arabic name)
# Falls back to entity_map.json if available
_room_map: dict = {}
_name_map: dict = {}


def _load_room_map():
    """Load room + name mappings from entity_map.json."""
    global _room_map, _name_map
    try:
        emap_path = os.path.join(os.path.dirname(__file__), "entity_map.json")
        if os.path.exists(emap_path):
            with open(emap_path, "r", encoding="utf-8") as f:
                emap = json.load(f)
            # Reverse: entity_id → room_name
            for room_name, entities in emap.items():
                # Strip /English suffix from room name
                ar_room = room_name.split('/')[0].strip()
                for entry in entities:
                    # Format: 'entity_id=friendly_name' or just 'entity_id'
                    if '=' in entry:
                        eid, fname = entry.split('=', 1)
                        eid = eid.strip()
                        _name_map[eid] = fname.strip()
                    else:
                        eid = entry.strip()
                    _room_map[eid] = ar_room
            logger.info(f"Room map: {len(_room_map)} entities → {len(emap)} rooms, {len(_name_map)} arabic names")
    except Exception as e:
        logger.warning(f"Room map load failed: {e}")


def _should_track(entity_id: str) -> bool:
    """Filter to meaningful device entities only."""
    domain = entity_id.split(".")[0]
    if domain not in TRACKED_DOMAINS:
        return False
    for skip in SKIP_PATTERNS:
        if skip in entity_id:
            return False
    return True


def _get_room(entity_id: str) -> str:
    """Get Arabic room name for entity."""
    if entity_id in _room_map:
        return _room_map[entity_id]
    # Fallback: extract from friendly_name or entity_id
    return ""


def _get_name(entity_id: str, ha_friendly: str) -> str:
    """Get best Arabic name: entity_map first, then HA friendly_name."""
    return _name_map.get(entity_id, ha_friendly)


def _format_entity(entity: dict) -> str:
    """Format a single entity state compactly."""
    eid = entity["entity_id"]
    attrs = entity.get("attributes", {})
    ha_name = attrs.get("friendly_name", eid.split(".")[-1])
    name = _get_name(eid, ha_name)
    state = entity["state"]
    domain = eid.split(".")[0]

    if state == "unavailable":
        return ""
    if state == "unknown" and domain != "climate":
        return ""

    parts = [name]

    if domain == "climate":
        temp = attrs.get("current_temperature", "?")
        target = attrs.get("temperature", "?")
        if state == "unknown":
            if temp and temp != "?":
                parts.append(f"غير معروف {temp}°")
            else:
                parts.append("غير معروف")
        else:
            mode = attrs.get("hvac_action", state)
            mode_ar = {"cooling": "تبريد", "heating": "تسخين", "idle": "واقف",
                       "off": "مطفي", "fan_only": "مروحة"}.get(mode, mode)
            parts.append(f"{mode_ar} {temp}°→{target}°")
    elif domain == "light":
        if state == "on":
            br = attrs.get("brightness")
            if br:
                parts.append(f"شغال {round(br/255*100)}%")
            else:
                parts.append("شغال")
        else:
            parts.append("مطفي")
    elif domain == "cover":
        pos = attrs.get("current_position")
        # _inverted covers: open=مفتوح (pos high), closed=مسكّر (pos=0)
        if state == "open":
            parts.append("مفتوح" + (f" {int(pos)}%" if pos is not None else ""))
        elif state == "closed":
            parts.append("مسكّر")
        else:
            parts.append(state)
    elif domain == "fan":
        parts.append("شغال" if state == "on" else "مطفي")
    elif domain == "media_player":
        if state == "playing":
            title = attrs.get("media_title", "")
            parts.append(f"يشغل {title}" if title else "يشغل")
        elif state == "idle":
            parts.append("واقف")
        elif state == "off":
            parts.append("مطفي")
        else:
            parts.append(state)
    else:
        parts.append(state)

    return ": ".join(parts)


def _build_snapshot(states: list) -> tuple:
    """Build snapshot dict and text from HA states."""
    by_room = defaultdict(lambda: defaultdict(list))
    counts = {"on": 0, "off": 0, "total": 0}
    ac_summary = []

    for s in states:
        eid = s["entity_id"]
        if not _should_track(eid):
            continue

        counts["total"] += 1
        state = s["state"]
        domain = eid.split(".")[0]

        if state in ("on", "playing", "cooling", "heating", "heat_cool"):
            counts["on"] += 1
        elif state in ("off", "idle"):
            counts["off"] += 1

        room = _get_room(eid) or "أخرى"
        formatted = _format_entity(s)
        if formatted:
            by_room[room][domain].append(formatted)

        # AC detail for summary
        if domain == "climate" and state not in ("unavailable", "unknown"):
            attrs = s.get("attributes", {})
            ha_name = attrs.get("friendly_name", eid.split(".")[-1])
            name = _get_name(eid, ha_name)
            temp = attrs.get("current_temperature", "?")
            target = attrs.get("temperature", "?")
            ac_summary.append(f"{name}: {temp}°→{target}° ({state})")

    # Build text
    lines = []
    now = datetime.now()
    lines.append(f"═══ حالة البيت ({now.strftime('%H:%M')}) ═══")
    lines.append(f"أجهزة شغالة: {counts['on']} | مطفية: {counts['off']} | إجمالي: {counts['total']}")

    if ac_summary:
        lines.append("")
        lines.append("المكيفات:")
        for ac in ac_summary:
            lines.append(f"  {ac}")

    # Rooms with active devices only (to save tokens)
    active_rooms = {}
    for room, domains in by_room.items():
        active = []
        for domain, items in domains.items():
            for item in items:
                if "شغال" in item or "يشغل" in item or "تبريد" in item or "تسخين" in item:
                    active.append(item)
        if active:
            active_rooms[room] = active

    if active_rooms:
        lines.append("")
        lines.append("أجهزة شغالة حسب الغرفة:")
        for room, items in sorted(active_rooms.items()):
            lines.append(f"  {room}: {' | '.join(items)}")

    snapshot_data = {
        "timestamp": now.isoformat(),
        "counts": counts,
        "ac_summary": ac_summary,
        "active_rooms": active_rooms,
        "by_room": {r: {d: items for d, items in doms.items()} for r, doms in by_room.items()},
    }

    return snapshot_data, "\n".join(lines)


async def _refresh():
    """Fetch HA states and update cache."""
    global _snapshot, _snapshot_text, _last_refresh
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{HA_URL}/api/states",
                headers={"Authorization": f"Bearer {HA_TOKEN}"}
            )
            if r.status_code != 200:
                logger.error(f"HA API returned {r.status_code}")
                return
            states = r.json()

        data, text = _build_snapshot(states)
        # Phase 2: Build delta (changes only)
        try:
            from world_state_delta import build_delta
            _delta, _dc = build_delta(states)
            if _dc:
                logger.info(f"World state delta: {_dc} changes")
        except Exception:
            pass
        _snapshot = data
        _snapshot_text = text
        _last_refresh = time.time()
        logger.debug(f"World state refreshed: {data['counts']}")
    except Exception as e:
        logger.error(f"World state refresh failed: {e}")


async def _refresh_loop():
    """Background loop that refreshes world state."""
    _load_room_map()
    # Initial refresh
    await _refresh()
    logger.info("World state initial snapshot taken")

    while True:
        await asyncio.sleep(_refresh_interval)
        try:
            await _refresh()
        except Exception as e:
            logger.error(f"World state loop error: {e}")
            await asyncio.sleep(5)


async def start_world_state():
    """Start the background refresh loop. Call once at startup."""
    global _task
    if _task is not None:
        return
    _task = asyncio.create_task(_refresh_loop())
    logger.info(f"World state started (interval={_refresh_interval}s)")


def get_snapshot_text() -> str:
    """Get current world state as formatted text for system prompt."""
    if not _snapshot_text:
        return ""
    age = time.time() - _last_refresh
    if age > 120:  # stale > 2 min
        return _snapshot_text + f"\n⚠️ آخر تحديث قبل {int(age)}s"
    return _snapshot_text


def get_snapshot_data() -> dict:
    """Get current world state as structured data."""
    return _snapshot.copy() if _snapshot else {}


def get_snapshot_age() -> float:
    """Get seconds since last refresh."""
    return time.time() - _last_refresh if _last_refresh else -1


# --- API endpoint helper ---
def get_status() -> dict:
    """Status dict for /world-state endpoint."""
    return {
        "last_refresh": _last_refresh,
        "age_seconds": round(get_snapshot_age(), 1),
        "counts": _snapshot.get("counts", {}),
        "active_rooms": len(_snapshot.get("active_rooms", {})),
        "text_length": len(_snapshot_text),
        "interval": _refresh_interval,
    }
