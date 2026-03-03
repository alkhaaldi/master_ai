"""Entity Map Health Validator - Step 3A
Compares entity_map.json with live HA state.
Reports: dead entities, missing entities, name mismatches, English names.
"""
import json, re, logging, httpx, os
from pathlib import Path

logger = logging.getLogger("entity_health")

ENTITY_MAP_PATH = Path(__file__).parent / "entity_map.json"

# English words that should be Arabic in entity names
_ENG_WORDS = {
    "chandler": "ثريا", "chandelier": "ثريا", "spot": "سبوت", "strip": "ستريب",
    "backlight": "إضاءة خلفية", "mirror": "مرآة", "vent": "شفاط", "exhaust": "شفاط",
    "shutter": "شتر", "curtain": "ستارة", "storage": "مخزن", "switch": "",
    "small light": "نور صغير", "fan": "", "purifier": "منقي هواء",
    "light": "", "ac": "مكيف", "tv": "تلفزيون",
    "living room": "المعيشة", "kitchen": "المطبخ", "office": "المكتب",
    "master": "الماستر", "mama room": "غرفة ماما", "mama": "ماما",
    "men room": "الديوانية", "reception": "الاستقبال", "ground": "الأرضي",
    "room 3": "غرفة 3", "room 5": "غرفة 5", "bathroom": "حمام",
    "hallway": "ممر", "stair": "درج", "door": "باب",
}

# Domains we track
_TRACKED_DOMAINS = {"light", "switch", "climate", "cover", "fan", "scene", "media_player"}


def load_entity_map() -> dict:
    try:
        return json.loads(ENTITY_MAP_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to load entity_map: {e}")
        return {}


def _get_map_entities(emap: dict) -> dict:
    """Return {entity_id: (room, name)} from entity_map."""
    result = {}
    for room, ents in emap.items():
        for e in ents:
            if "=" in e:
                eid, name = e.split("=", 1)
                result[eid] = (room, name)
    return result


def _find_english_words(name: str) -> list:
    """Find English words in entity name that should be Arabic."""
    nl = name.lower()
    found = []
    for eng in sorted(_ENG_WORDS.keys(), key=len, reverse=True):
        if eng in nl:
            found.append(eng)
    return found


async def validate_entity_map(ha_url: str, ha_token: str) -> dict:
    """Run full validation. Returns health report."""
    emap = load_entity_map()
    map_entities = _get_map_entities(emap)

    report = {
        "total_rooms": len(emap),
        "total_map_entities": len(map_entities),
        "dead_entities": [],      # in map but not in HA
        "missing_entities": [],   # in HA but not in map (tracked domains)
        "english_names": [],      # names with English words
        "name_mismatches": [],    # map name != HA friendly_name
        "ha_reachable": False,
        "ha_entity_count": 0,
    }

    # Fetch live HA states
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{ha_url}/api/states",
                headers={"Authorization": f"Bearer {ha_token}"}
            )
            r.raise_for_status()
            ha_states = {s["entity_id"]: s for s in r.json()}
            report["ha_reachable"] = True
            report["ha_entity_count"] = len(ha_states)
    except Exception as e:
        logger.error(f"HA unreachable: {e}")
        report["error"] = str(e)
        return report

    # 1) Dead entities (in map, not in HA)
    for eid, (room, name) in map_entities.items():
        if eid not in ha_states:
            report["dead_entities"].append({"entity_id": eid, "room": room, "name": name})

    # 2) Missing entities (in HA, not in map, tracked domains)
    for eid, state in ha_states.items():
        domain = eid.split(".")[0]
        if domain in _TRACKED_DOMAINS and eid not in map_entities:
            fn = state["attributes"].get("friendly_name", "")
            report["missing_entities"].append({"entity_id": eid, "name": fn})

    # 3) English names
    for eid, (room, name) in map_entities.items():
        eng = _find_english_words(name)
        if eng:
            report["english_names"].append({"entity_id": eid, "room": room, "name": name, "english_words": eng})

    # 4) Name mismatches (map name != HA friendly_name)
    for eid, (room, name) in map_entities.items():
        if eid in ha_states:
            ha_name = ha_states[eid]["attributes"].get("friendly_name", "")
            if name != ha_name and ha_name:
                report["name_mismatches"].append({
                    "entity_id": eid, "map_name": name, "ha_name": ha_name, "room": room
                })

    # Summary
    report["summary"] = {
        "dead": len(report["dead_entities"]),
        "missing": len(report["missing_entities"]),
        "english": len(report["english_names"]),
        "mismatched": len(report["name_mismatches"]),
        "healthy": len(report["dead_entities"]) == 0 and len(report["english_names"]) == 0,
    }

    return report


def arabize_entity_map(emap: dict) -> tuple:
    """Auto-translate English words in entity names to Arabic.
    Returns (updated_map, changes_list).
    Does NOT save - caller decides.
    """
    changes = []
    new_map = {}

    for room, ents in emap.items():
        new_ents = []
        for e in ents:
            if "=" not in e:
                new_ents.append(e)
                continue
            eid, name = e.split("=", 1)
            new_name = name
            eng_words = _find_english_words(name)
            if eng_words:
                # Replace English words with Arabic equivalents
                for eng in sorted(eng_words, key=len, reverse=True):
                    ar = _ENG_WORDS.get(eng, "")
                    if ar:
                        # Case-insensitive replace
                        pattern = re.compile(re.escape(eng), re.IGNORECASE)
                        new_name = pattern.sub(ar, new_name).strip()
                # Clean up extra spaces
                new_name = re.sub(r"\s+", " ", new_name).strip()
                if new_name != name:
                    changes.append({"entity_id": eid, "old": name, "new": new_name, "room": room})
            new_ents.append(f"{eid}={new_name}")
        new_map[room] = new_ents

    return new_map, changes
