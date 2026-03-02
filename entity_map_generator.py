#!/usr/bin/env python3
"""
entity_map_generator.py v2 — Smart Entity Map Generator

MERGE strategy: pulls entities from HA areas, but NEVER removes entries
from the existing entity_map.json. Only ADDS new entities/rooms found in HA.

This ensures manually-added entries (inverted covers, input_booleans,
scenes, aliases) are always preserved.

Usage:
    python3 entity_map_generator.py              # Preview changes (dry-run)
    python3 entity_map_generator.py --apply       # Apply merge to entity_map.json
    python3 entity_map_generator.py --cron        # Silent cron mode (merge only if new entities)
    python3 entity_map_generator.py --full        # Full regenerate (REPLACES file, use with caution)
    python3 entity_map_generator.py --audit       # Show missing areas / unassigned entities

Cron example (daily 4:00 AM):
    0 4 * * * cd /home/pi/master_ai && venv/bin/python3 entity_map_generator.py --cron >> /tmp/emap_cron.log 2>&1
"""
import argparse
import json
import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from collections import OrderedDict

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

# ─── Configuration ─────────────────────────────────────────
BASE_DIR = Path("/home/pi/master_ai")
ENTITY_MAP_PATH = BASE_DIR / "entity_map.json"
HA_URL = os.getenv("HA_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")

if not HA_TOKEN:
    token_file = Path.home() / ".ha_token"
    if token_file.exists():
        HA_TOKEN = token_file.read_text().strip()

# Domains to include
INCLUDED_DOMAINS = {
    "light", "switch", "climate", "cover", "fan",
    "media_player", "scene", "input_boolean",
}

# Patterns to exclude from entity IDs
EXCLUDE_PATTERNS = [
    "backlight", "_energy", "_power", "_voltage", "_current",
    "_signal", "_rssi", "_uptime", "_update", "_firmware",
    "filter_cartridge_reset", "_ionizer",
]

# Domains to always exclude
EXCLUDE_DOMAINS = {
    "button", "number", "select", "text", "update", "sensor",
    "binary_sensor", "automation", "script", "person", "zone",
    "sun", "weather", "calendar", "device_tracker", "tts", "stt",
    "conversation", "input_number", "input_text", "input_select",
    "input_datetime", "timer", "counter", "group", "camera",
}

# ══════════════════════════════════════════════════════════════
# HA Area Name → entity_map Room Key
#
# This is the SINGLE SOURCE OF TRUTH for room name mapping.
# When HA has area "غرفة النوم الرئيسية", we map it to
# "غرفة الماستر/Master" to match the router's ROOM_KEYWORDS.
#
# Sub-areas (bathrooms, closets) are MERGED into their parent
# room so the router can control "طفي كل شي بالماستر" and
# it includes the bathroom + closet entities too.
# ══════════════════════════════════════════════════════════════
AREA_TO_ROOM = {
    # --- Diwaniya (merge bathroom into parent) ---
    "الديوانية":                    "الديوانية/Diwaniya",
    "حمام الديوانية":              "الديوانية/Diwaniya",

    # --- Kitchen ---
    "المطبخ":                      "المطبخ/Kitchen",

    # --- Reception ---
    "صالة الاستقبال":              "صالة الاستقبال/Reception",

    # --- Living ---
    "صالة المعيشة":                "صالة المعيشة/Living",

    # --- Master suite ---
    "غرفة النوم الرئيسية":         "غرفة الماستر/Master",
    "حمام غرفة النوم الرئيسية":    "حمام الماستر",
    "غرفة ملابس الرئيسية":         "ملابس الماستر",

    # --- Mama ---
    "غرفة أمي":                    "غرفة ماما/Mama",

    # --- Guest (merge bathroom + closet) ---
    "حمام الضيوف":                 "غرفة الضيوف/Guest",
    "غرفة ملابس الضيوف":           "غرفة الضيوف/Guest",

    # --- Numbered rooms (merge sub-areas) ---
    "غرفة 2":                      "غرفة 2",
    "حمام غرفة 2":                 "غرفة 2",
    "غرفة ملابس 2":                "غرفة 2",
    "غرفة 3":                      "غرفة 3",
    "حمام غرفة 3":                 "غرفة 3",
    "غرفة ملابس 3":                "غرفة 3",
    "غرفة 4":                      "غرفة 4",
    "حمام غرفة 4":                 "غرفة 4",
    "غرفة ملابس 4":                "غرفة 4",
    "غرفة 5":                      "غرفة 5",
    "حمام غرفة 5":                 "غرفة 5",
    "غرفة ملابس 5":                "غرفة 5",

    # --- Service rooms ---
    "غرفة الغسيل":                 "غرفة الغسيل/Laundry",
    "غرفة الخادمة":                "غرفة الخادمة/Maid",
    "غرفة الطعام":                 "غرفة الطعام/Dining",

    # --- Office (merge bathroom + dresser) ---
    "My Office":                    "المكتب/Office",
    "المكتب":                      "المكتب/Office",
    "Office bathroom":              "المكتب/Office",
    "Office Dresser":               "المكتب/Office",

    # --- Salon ---
    "MY SWEET":                     "صالتي/Salon",

    # --- Corridors / Stairs ---
    "صالة الدور الأول":             "ممر الدور الأول",
    "درج الدور الأول":              "الدرج/Stairs",

    # --- Exterior (merge multiple areas) ---
    "باب المدخل الجانبي":           "الأرضي/Ground",
    "مدخل المؤجرين":               "الأرضي/Ground",
    "مخرج غرفة الغسيل":            "الأرضي/Ground",
    "مخرج المطبخ":                 "الأرضي/Ground",
    "parking":                      "الخارجي/Outdoor",
    "ظهر البيت":                   "الخارجي/Outdoor",
}

# Preferred room ordering (for consistent JSON output)
ROOM_ORDER = [
    "الديوانية/Diwaniya", "المطبخ/Kitchen", "صالة الاستقبال/Reception",
    "صالة المعيشة/Living", "غرفة الماستر/Master", "حمام الماستر",
    "ملابس الماستر", "غرفة ماما/Mama", "غرفة الضيوف/Guest",
    "غرفة عيشة/Aisha", "غرفة 2", "غرفة 3", "غرفة 4", "غرفة 5",
    "المكتب/Office", "صالتي/Salon", "غرفة الطعام/Dining",
    "غرفة الغسيل/Laundry", "غرفة الخادمة/Maid",
    "البلكونة/Balcony", "ممر الدور الأول", "الدرج/Stairs",
    "الأرضي/Ground", "الخارجي/Outdoor", "المشاهد/Scenes",
]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


# ─── HA API ────────────────────────────────────────────────

def ha_get(endpoint: str):
    """GET from HA REST API."""
    headers = {"Authorization": f"Bearer {HA_TOKEN}"}
    r = httpx.get(f"{HA_URL}{endpoint}", headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()


def ha_ws_get(msg_type: str) -> list:
    """Query HA WebSocket API for registry data."""
    try:
        import websocket
    except ImportError:
        logger.error("websocket-client not installed: pip install websocket-client")
        return []

    url = HA_URL.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"
    result = []
    done = __import__("threading").Event()

    def on_message(ws, message):
        nonlocal result
        data = json.loads(message)
        if data.get("type") == "auth_required":
            ws.send(json.dumps({"type": "auth", "access_token": HA_TOKEN}))
        elif data.get("type") == "auth_ok":
            ws.send(json.dumps({"id": 1, "type": msg_type}))
        elif data.get("type") == "result" and data.get("id") == 1:
            result = data.get("result", [])
            done.set()
            ws.close()

    def on_error(ws, error):
        logger.error(f"WS error: {error}")
        done.set()

    wsapp = websocket.WebSocketApp(url, on_message=on_message, on_error=on_error)
    t = __import__("threading").Thread(target=wsapp.run_forever, kwargs={"ping_timeout": 5})
    t.daemon = True
    t.start()
    done.wait(timeout=15)
    return result


# ─── Helpers ───────────────────────────────────────────────

def should_include(entity_id: str) -> bool:
    """Check if entity belongs in entity_map."""
    domain = entity_id.split(".")[0]
    if domain in EXCLUDE_DOMAINS:
        return False
    if domain not in INCLUDED_DOMAINS:
        return False
    for pat in EXCLUDE_PATTERNS:
        if pat in entity_id.lower():
            return False
    return True


def load_existing() -> dict:
    """Load current entity_map.json."""
    if ENTITY_MAP_PATH.exists():
        try:
            return json.loads(ENTITY_MAP_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to load existing map: {e}")
    return {}


def sort_room_map(room_map: dict) -> OrderedDict:
    """Sort rooms in preferred order, unknowns at end."""
    order_idx = {name: i for i, name in enumerate(ROOM_ORDER)}
    sorted_keys = sorted(room_map.keys(), key=lambda k: order_idx.get(k, 999))
    result = OrderedDict()
    for k in sorted_keys:
        result[k] = sorted(set(room_map[k]), key=lambda x: x.split("=")[0])
    return result


# ─── Core Logic ────────────────────────────────────────────

def fetch_ha_entities() -> dict:
    """Pull entities from HA, grouped by mapped room name.
    Returns: {room_key: [entity_entries]}
    """
    # 1. States
    states = ha_get("/api/states")
    logger.info(f"Total states: {len(states)}")

    # 2. Areas
    areas_raw = ha_ws_get("config/area_registry/list")
    areas = {a["area_id"]: a["name"] for a in areas_raw}
    logger.info(f"Areas: {len(areas)} — {list(areas.values())}")

    # 3. Entity → area mapping (via entity registry + device registry)
    ent_reg = ha_ws_get("config/entity_registry/list")
    dev_reg = ha_ws_get("config/device_registry/list")
    dev_area = {d["id"]: d.get("area_id") for d in dev_reg if d.get("area_id")}

    ent_area = {}
    for e in ent_reg:
        aid = e.get("area_id")
        if not aid and e.get("device_id"):
            aid = dev_area.get(e["device_id"])
        if aid:
            ent_area[e["entity_id"]] = aid

    logger.info(f"Entity-area mappings: {len(ent_area)}")

    # 4. Build room_map
    room_map = {}
    scenes = []
    unassigned = []

    for state in states:
        eid = state["entity_id"]
        if not should_include(eid):
            continue

        friendly = state.get("attributes", {}).get("friendly_name", eid.split(".")[-1])
        entry = f"{eid}={friendly}"

        if eid.startswith("scene."):
            scenes.append(entry)
            continue

        area_id = ent_area.get(eid)
        if area_id and area_id in areas:
            area_name = areas[area_id]
            room_key = AREA_TO_ROOM.get(area_name, area_name)
        else:
            unassigned.append(entry)
            continue

        room_map.setdefault(room_key, []).append(entry)

    if scenes:
        room_map["المشاهد/Scenes"] = scenes

    if unassigned:
        logger.warning(f"Unassigned (no HA area): {len(unassigned)}")
        for u in unassigned[:10]:
            logger.warning(f"  {u}")

    return room_map


def merge_maps(existing: dict, from_ha: dict) -> tuple[dict, dict]:
    """Merge HA data INTO existing map (never removes).

    Returns: (merged_map, stats)
    """
    merged = {}
    stats = {"new_rooms": [], "new_entities": 0, "existing_rooms": 0, "total_rooms": 0}

    # Start with all existing rooms and entries
    for room, entries in existing.items():
        merged[room] = list(entries)

    # Add new from HA
    for room, ha_entries in from_ha.items():
        if room not in merged:
            merged[room] = []
            stats["new_rooms"].append(room)

        # Existing entity IDs in this room
        existing_eids = {e.split("=")[0] for e in merged[room]}

        for entry in ha_entries:
            eid = entry.split("=")[0]
            if eid not in existing_eids:
                merged[room].append(entry)
                stats["new_entities"] += 1

    stats["existing_rooms"] = len(existing)
    stats["total_rooms"] = len(merged)
    return merged, stats


def full_generate(from_ha: dict) -> dict:
    """Full replacement mode — use HA data only."""
    return from_ha


def audit_report(existing: dict, from_ha: dict):
    """Show what's different between existing and HA data."""
    print("\n" + "=" * 60)
    print("AUDIT REPORT")
    print("=" * 60)

    # Rooms in existing but not generated from HA
    ha_rooms = set(from_ha.keys())
    ex_rooms = set(existing.keys())
    only_manual = ex_rooms - ha_rooms
    only_ha = ha_rooms - ex_rooms
    common = ex_rooms & ha_rooms

    print(f"\nExisting rooms: {len(ex_rooms)}")
    print(f"HA-generated rooms: {len(ha_rooms)}")

    if only_manual:
        print(f"\n📌 Rooms ONLY in manual map ({len(only_manual)}):")
        for r in sorted(only_manual):
            count = len(existing.get(r, []))
            print(f"  {r} ({count} entities)")

    if only_ha:
        print(f"\n🆕 Rooms ONLY in HA ({len(only_ha)}):")
        for r in sorted(only_ha):
            count = len(from_ha.get(r, []))
            print(f"  {r} ({count} entities)")

    # Entity-level diff for common rooms
    total_new = 0
    total_removed = 0
    for room in sorted(common):
        ex_eids = {e.split("=")[0] for e in existing.get(room, [])}
        ha_eids = {e.split("=")[0] for e in from_ha.get(room, [])}
        new = ha_eids - ex_eids
        removed = ex_eids - ha_eids
        if new or removed:
            print(f"\n🔄 {room}:")
            for eid in sorted(new):
                entry = next((e for e in from_ha[room] if e.startswith(eid)), eid)
                print(f"  + {entry}")
                total_new += 1
            for eid in sorted(removed):
                print(f"  - {eid} (manual only)")
                total_removed += 1

    print(f"\n{'='*60}")
    print(f"Summary: +{total_new} new entities, {total_removed} manual-only entities")
    print(f"{'='*60}\n")


# ─── CLI ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Entity Map Generator v2 (merge mode)")
    parser.add_argument("--apply", action="store_true", help="Merge HA entities into entity_map.json")
    parser.add_argument("--cron", action="store_true", help="Silent cron mode (only writes if new)")
    parser.add_argument("--full", action="store_true", help="Full regenerate (REPLACES, use with caution)")
    parser.add_argument("--audit", action="store_true", help="Show detailed diff report")
    args = parser.parse_args()

    if args.cron:
        logging.getLogger().setLevel(logging.WARNING)

    if not HA_TOKEN:
        logger.error("No HA token! Set HA_TOKEN env or create ~/.ha_token")
        sys.exit(1)

    # Fetch from HA
    logger.info("Fetching HA data...")
    from_ha = fetch_ha_entities()

    if not from_ha:
        logger.error("HA returned empty data! Aborting.")
        sys.exit(1)

    ha_total = sum(len(v) for v in from_ha.values())
    logger.info(f"HA: {len(from_ha)} rooms, {ha_total} entities")

    # Load existing
    existing = load_existing()
    ex_total = sum(len(v) for v in existing.values())

    # Audit mode
    if args.audit:
        audit_report(existing, from_ha)
        return

    # Full regenerate mode
    if args.full:
        result = sort_room_map(full_generate(from_ha))
        result_total = sum(len(v) for v in result.values())
        print(f"\n⚠️  FULL REGENERATE: {len(result)} rooms, {result_total} entities")
        print(f"    (existing had {len(existing)} rooms, {ex_total} entities)")
        if not args.apply:
            print("    Use --full --apply to write.")
            return
    else:
        # Default: MERGE mode
        merged, stats = merge_maps(existing, from_ha)
        result = sort_room_map(merged)
        result_total = sum(len(v) for v in result.values())

    if not args.cron:
        print(f"\n{'='*50}")
        print(f"Entity Map Generator v2")
        print(f"{'='*50}")
        print(f"Existing: {len(existing)} rooms, {ex_total} entities")
        print(f"From HA:  {len(from_ha)} rooms, {ha_total} entities")
        print(f"Result:   {len(result)} rooms, {result_total} entities")
        if not args.full:
            print(f"New rooms: {stats['new_rooms'] or 'none'}")
            print(f"New entities: {stats['new_entities']}")
        print(f"{'='*50}\n")

    # Write
    if args.apply or args.cron:
        if args.cron and not args.full:
            if stats["new_entities"] == 0 and not stats["new_rooms"]:
                return  # Nothing new

        # Backup
        if ENTITY_MAP_PATH.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = ENTITY_MAP_PATH.with_suffix(f".json.bak.{ts}")
            import shutil
            shutil.copy2(ENTITY_MAP_PATH, backup)
            logger.info(f"Backup: {backup}")

        # Write
        ENTITY_MAP_PATH.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        new_count = stats["new_entities"] if not args.full else result_total
        print(f"✅ entity_map.json updated ({len(result)} rooms, {result_total} entities, +{new_count} new)")
    elif not args.audit:
        # Preview first 2000 chars
        preview = json.dumps(result, ensure_ascii=False, indent=2)
        print(preview[:2000])
        if len(preview) > 2000:
            print(f"\n... ({len(preview)} chars total). Use --apply to write.")


if __name__ == "__main__":
    main()
