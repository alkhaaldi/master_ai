"""
ha_discovery.py — Live HA Entity Discovery & Cache
Pulls all entities from HA API, groups by room/domain, caches with TTL.
Used by brain_core to provide live Room Index to Opus.
"""
import asyncio, httpx, logging, time, os, json, re
from collections import defaultdict

logger = logging.getLogger("ha_discovery")

HA_URL = os.getenv("HA_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")
CACHE_TTL = 300  # 5 minutes

# ═══ Cache ═══
_cache = {
    "entities": [],      # raw list from HA
    "by_domain": {},     # domain -> [entity_id, ...]
    "by_room": {},       # room_name -> {domain: [entity_ids]}
    "friendly_map": {},  # entity_id -> friendly_name
    "ts": 0,
}

# ═══ Room Detection ═══
# Map HA area/friendly_name patterns to room names
_ROOM_PATTERNS = {
    "الماستر|master|my_room|my room|my_bathroom|my_sweet": "غرفة الماستر",
    "المعيشة|living|معيشة|thermostat_13": "المعيشة",
    "المطبخ|kitchen|مطبخ|lmtbkh": "المطبخ",
    "الاستقبال|reception|استقبال|guest_room|guest_bathroom|guest_hand": "الاستقبال",
    "الديوانية|diwaniya|ديوانية|ldywny|men_room|men_door|men_window": "الديوانية",
    "غرفة 1|room_1|room1|sar1": "غرفة 1",
    "غرفة 2|room_2|room2|sar2": "غرفة 2",
    "غرفة 3|room_3|room3|sar3|grf_3": "غرفة 3",
    "ماما|mama|أم سالم|nahid": "غرفة ماما",
    "الخادمة|maid|خادمة|aisha|عائشة": "غرفة الخادمة",
    "الخارجي|outdoor|outside|خارج|garden": "الخارجي",
    "الغسيل|laundry|غسيل|laundry_room": "غرفة الغسيل",
    "الأرضي|ground_floor|ground|أرضي|الدور الأرضي": "الدور الأرضي",
    "الأول|first_floor|الدور الأول|1st_floor": "الدور الأول",
    "الممر|hallway|corridor|ممر": "الممر",
    "الدرج|stairs|stair|درج": "الدرج",
    "الحمام|bathroom|حمام": "حمام عام",
}

_DOMAIN_ICONS = {
    "light": "💡", "switch": "🔌", "climate": "🌀",
    "cover": "🪟", "sensor": "🌡", "media_player": "🔊",
    "fan": "💨", "lock": "🔒", "camera": "📷",
    "scene": "🎬", "automation": "⚙️", "binary_sensor": "📡",
}

_SKIP_DOMAINS = {"person", "zone", "weather", "update", "number", "input_boolean",
                 "input_number", "input_text", "input_select", "input_datetime",
                 "persistent_notification", "device_tracker", "sun", "group",
                 "script", "timer", "counter", "button", "select", "text", "tts"}


def _detect_room(entity_id: str, friendly_name: str, area: str = "") -> str:
    """Detect room from entity_id, friendly_name, or area."""
    text = f"{entity_id} {friendly_name} {area}".lower()
    for pattern_str, room in _ROOM_PATTERNS.items():
        patterns = pattern_str.split("|")
        for p in patterns:
            if p.lower() in text:
                return room
    return "أخرى"


async def refresh_cache(force: bool = False) -> dict:
    """Fetch all entities from HA and rebuild cache."""
    global _cache
    if not force and _cache["ts"] and (time.time() - _cache["ts"]) < CACHE_TTL:
        return {"status": "cached", "age": round(time.time() - _cache["ts"])}
    
    if not HA_TOKEN:
        # Try reading from env file
        token_file = os.path.expanduser("~/.ha_token")
        if os.path.exists(token_file):
            with open(token_file) as f:
                token = f.read().strip()
        else:
            return {"status": "error", "msg": "No HA token"}
    else:
        token = HA_TOKEN

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            headers = {"Authorization": f"Bearer {token}"}
            r = await client.get(f"{HA_URL}/api/states", headers=headers)
            if r.status_code != 200:
                return {"status": "error", "code": r.status_code}
            
            all_states = r.json()
        
        by_domain = defaultdict(list)
        by_room = defaultdict(lambda: defaultdict(list))
        friendly_map = {}
        
        for s in all_states:
            eid = s.get("entity_id", "")
            domain = eid.split(".")[0] if "." in eid else ""
            if domain in _SKIP_DOMAINS:
                continue
            
            fname = s.get("attributes", {}).get("friendly_name", eid)
            area = s.get("attributes", {}).get("area_id", "")
            room = _detect_room(eid, fname, area)
            
            by_domain[domain].append(eid)
            by_room[room][domain].append(eid)
            friendly_map[eid] = fname
        
        _cache = {
            "entities": all_states,
            "by_domain": dict(by_domain),
            "by_room": {r: dict(d) for r, d in by_room.items()},
            "friendly_map": friendly_map,
            "ts": time.time(),
            "total": len(all_states),
            "mapped": len(friendly_map),
        }
        
        logger.info(f"HA Discovery: {len(all_states)} entities, {len(by_room)} rooms, {len(friendly_map)} mapped")
        return {"status": "ok", "total": len(all_states), "rooms": len(by_room), "mapped": len(friendly_map)}
    
    except Exception as e:
        logger.error(f"HA Discovery error: {e}")
        return {"status": "error", "msg": str(e)}


def get_cache() -> dict:
    """Get current cache."""
    return _cache


def get_room_index_live() -> str:
    """Build compact room index from live cache for system prompt injection."""
    if not _cache["by_room"]:
        return ""
    
    lines = []
    for room, domains in sorted(_cache["by_room"].items()):
        parts = []
        climate_ids = []
        cover_ids = []
        for domain, eids in sorted(domains.items()):
            icon = _DOMAIN_ICONS.get(domain, "")
            parts.append(f"{icon}x{len(eids)}")
            if domain == "climate":
                climate_ids.extend(eids)
            elif domain == "cover":
                cover_ids.extend(eids)
        
        line = f"  {room}: {' '.join(parts)}"
        # Append key entity IDs inline
        key_ids = climate_ids + cover_ids
        if key_ids:
            line += f" [{','.join(key_ids)}]"
        lines.append(line)
    
    header = chr(9552)*3 + " Live Room Index " + chr(9552)*3
    return header + chr(10) + chr(10).join(lines)


def get_entities_for_room(room_query: str) -> list:
    """Get entity IDs for a room query."""
    room_query_lower = room_query.lower()
    for room, domains in _cache["by_room"].items():
        if room_query_lower in room.lower():
            return [eid for eids in domains.values() for eid in eids]
    return []


def get_friendly_name(entity_id: str) -> str:
    """Get friendly name for entity."""
    return _cache["friendly_map"].get(entity_id, entity_id)


# ═══ Stats ═══
def get_stats() -> dict:
    return {
        "cached": bool(_cache["ts"]),
        "age": round(time.time() - _cache["ts"]) if _cache["ts"] else None,
        "total": _cache.get("total", 0),
        "mapped": _cache.get("mapped", 0),
        "rooms": len(_cache.get("by_room", {})),
        "domains": list(_cache.get("by_domain", {}).keys()),
    }
