# discovery.py — HA Entity Discovery & Sync
# Background task: fetch HA states, build entity index, save to JSON
import json
import logging
import os
import asyncio
from datetime import datetime

logger = logging.getLogger("master_ai.discovery")

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DISCOVERY_FILE = os.path.join(DATA_DIR, "discovered_entities.json")

# ── Room mapping v2: multi-signal, priority-ordered ──
# Priority 1: Exact prefix/substring matches in entity_id
# Priority 2: Arabic transliteration patterns from Tuya
# Priority 3: friendly_name Arabic keywords (fallback)

# Ordered list — first match wins. More specific patterns first.
ROOM_RULES = [
    # ── ديوانية (Tuya transliterates as ldywny/dywny/diwani) ──
    ("ldywny",           "ديوانية"),
    ("dywny",            "ديوانية"),
    ("diwani",           "ديوانية"),
    ("diwaniya",         "ديوانية"),
    ("diwaniy",          "ديوانية"),
    ("majlis",           "ديوانية"),
    # ── استقبال (Tuya: sl_lstqbl / lstqbl / istiqbal) ──
    ("lstqbl",           "استقبال"),
    ("istiqbal",         "استقبال"),
    ("reception",        "استقبال"),
    # ── ماستر / غرفتي ──
    ("my_room",          "ماستر"),
    ("my_dressing",      "ماستر"),
    ("my_tv",            "ماستر"),
    ("aisha",            "ماستر"),
    ("abajora",          "ماستر"),
    ("master",           "ماستر"),
    # ── غرف نوم بالرقم ──
    ("room_1",           "غرفة 1"),
    ("room1",            "غرفة 1"),
    ("room_2",           "غرفة 2"),
    ("room2",            "غرفة 2"),
    ("room_3",           "غرفة 3"),
    ("room3",            "غرفة 3"),
    ("room_4",           "غرفة 4"),
    ("room4",            "غرفة 4"),
    ("room_5",           "غرفة 5"),
    ("room5",            "غرفة 5"),
    # ── معيشة / صالة ──
    ("living",           "معيشة"),
    ("salon",            "معيشة"),
    # ── سفرة ──
    ("dining",           "سفرة"),
    # ── مطبخ ──
    ("kitchen",          "مطبخ"),
    ("mtbkh",            "مطبخ"),
    # ── حمامات ──
    ("bathroom",         "حمام"),
    ("bath_",            "حمام"),
    ("_bath",            "حمام"),
    ("wc_",              "حمام"),
    ("toilet",           "حمام"),
    ("hmm_",             "حمام"),
    # ── ملابس / دريسنق ──
    ("dressing",         "ملابس"),
    ("closet",           "ملابس"),
    # ── خادمة ──
    ("maid",             "غرفة خادمة"),
    ("men_room",         "غرفة خادمة"),
    # ── مغسلة ──
    ("laundry",          "مغسلة"),
    ("hand_wash",        "مغسلة"),
    ("guest_hand",       "مغسلة"),
    # ── مكتب ──
    ("office",           "مكتب"),
    # ── بلكونة ──
    ("balcony",          "بلكونة"),
    ("balkon",           "بلكونة"),
    # ── ممر / كوريدور ──
    ("corridor",         "ممر"),
    ("hallway",          "ممر"),
    ("hall_",            "ممر"),
    # ── درج ──
    ("stairs",           "درج"),
    ("stair_",           "درج"),
    # ── مدخل ──
    ("entrance",         "مدخل"),
    ("front_door",       "مدخل"),
    # ── أرضي ──
    ("ground",           "أرضي"),
    # ── أول (الدور الأول) ──
    ("first_floor",      "أول"),
    ("first",            "أول"),
    # ── خارجي ──
    ("outdoor",          "خارجي"),
    ("garden",           "خارجي"),
    ("garage",           "خارجي"),
]

# Arabic friendly_name keywords (fallback if entity_id didn't match)
FRIENDLY_NAME_KEYWORDS = [
    ("ديوانية",   "ديوانية"),
    ("ديوانيه",   "ديوانية"),
    ("استقبال",   "استقبال"),
    ("الاستقبال", "استقبال"),
    ("ماستر",     "ماستر"),
    ("غرفة النوم","ماستر"),
    ("غرفتي",     "ماستر"),
    ("صالة",       "معيشة"),
    ("معيشة",     "معيشة"),
    ("سفرة",       "سفرة"),
    ("مطبخ",       "مطبخ"),
    ("حمام",       "حمام"),
    ("ملابس",     "ملابس"),
    ("خادمة",     "غرفة خادمة"),
    ("مغسلة",     "مغسلة"),
    ("مكتب",       "مكتب"),
    ("بلكونة",   "بلكونة"),
    ("بلكوني",   "بلكونة"),
    ("ممر",         "ممر"),
    ("كوريدور", "ممر"),
    ("درج",         "درج"),
    ("مدخل",       "مدخل"),
    ("أرضي",       "أرضي"),
    ("خارجي",     "خارجي"),
]


def guess_room(entity_id: str, friendly_name: str = "") -> str:
    """Guess room from entity_id patterns, then friendly_name Arabic keywords."""
    eid = entity_id.lower()
    # Strip domain prefix for matching (e.g. light.salon_x -> salon_x)
    eid_short = eid.split(".", 1)[-1] if "." in eid else eid

    # Priority 1: entity_id pattern matching
    for pattern, room in ROOM_RULES:
        if pattern in eid_short:
            return room

    # Priority 2: friendly_name Arabic keyword matching
    fn = (friendly_name or "").strip()
    if fn:
        for keyword, room in FRIENDLY_NAME_KEYWORDS:
            if keyword in fn:
                return room

    return "غير مصنف"


def _self_test():
    """Quick self-test for room mapping. Run: python3 -c 'from discovery import _self_test; _self_test()'"""
    cases = [
        ("light.ldywny_spot_1", "", "ديوانية"),
        ("light.ldywny_s_switch_1", "", "ديوانية"),
        ("light.sl_lstqbl_switch_1", "", "استقبال"),
        ("light.my_room_lights_switch_1", "", "ماستر"),
        ("light.aisha_dressing_room_switch_1", "", "ماستر"),
        ("light.room_2_spot_switch_1", "", "غرفة 2"),
        ("light.room_3_spot_switch_1", "", "غرفة 3"),
        ("light.room_4_strip_switch_1", "", "غرفة 4"),
        ("light.room_5_spot_switch_1", "", "غرفة 5"),
        ("light.salon_light_switch_1", "", "معيشة"),
        ("light.dining_room_switch_1", "", "سفرة"),
        ("light.maid_room_switch_1", "", "غرفة خادمة"),
        ("light.balcony_light_switch_1", "", "بلكونة"),
        ("light.hmm_ldywny_s_switch_3", "", "ديوانية"),
        ("light.guest_hand_wash_light_switch_1", "", "مغسلة"),
        ("light.abajora_socket_1", "", "ماستر"),
        ("light.men_room_switch_1", "", "غرفة خادمة"),
        ("switch.unknown_thing", "ديوانية سبوت", "ديوانية"),
        ("sensor.temp_xyz", "", "غير مصنف"),
    ]
    passed = 0
    for eid, fn, expected in cases:
        result = guess_room(eid, fn)
        ok = result == expected
        passed += ok
        status = "PASS" if ok else "FAIL"
        if not ok:
            print(f"  {status}: {eid} -> got '{result}', expected '{expected}'")
    print(f"Self-test: {passed}/{len(cases)} passed")
    return passed == len(cases)


async def sync_entities(ha_url: str, ha_tkn: str) -> dict:
    """Fetch all HA entities and build discovery index."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{ha_url}/api/states",
                headers={"Authorization": f"Bearer {ha_tkn}"}
            )
            resp.raise_for_status()
            states = resp.json()
    except Exception as e:
        logger.error(f"Discovery sync failed: {e}")
        return {"error": str(e), "count": 0}

    now = datetime.utcnow().isoformat()

    # Load existing
    existing = {}
    if os.path.exists(DISCOVERY_FILE):
        try:
            with open(DISCOVERY_FILE) as f:
                existing = {e["entity_id"]: e for e in json.load(f).get("entities", [])}
        except Exception:
            pass

    entities = []
    new_count = 0
    renamed_count = 0
    for state in states:
        eid = state["entity_id"]
        friendly = state.get("attributes", {}).get("friendly_name", eid)
        domain = eid.split(".")[0]

        prev = existing.get(eid)
        if prev:
            entry = prev.copy()
            entry["last_seen"] = now
            entry["friendly_name"] = friendly
            entry["state"] = state.get("state", "unknown")
            # Re-guess room on every sync (picks up improved mapping)
            entry["room_guess"] = guess_room(eid, friendly)
            if prev.get("friendly_name") != friendly:
                entry["renamed_from"] = prev.get("friendly_name")
                renamed_count += 1
        else:
            entry = {
                "entity_id": eid,
                "friendly_name": friendly,
                "domain": domain,
                "room_guess": guess_room(eid, friendly),
                "first_seen": now,
                "last_seen": now,
                "state": state.get("state", "unknown"),
            }
            new_count += 1
        entities.append(entry)

    # Stats by domain
    domain_counts = {}
    for e in entities:
        d = e["domain"]
        domain_counts[d] = domain_counts.get(d, 0) + 1

    result = {
        "last_sync": now,
        "total": len(entities),
        "new": new_count,
        "renamed": renamed_count,
        "domains": domain_counts,
        "entities": entities,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DISCOVERY_FILE, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    logger.info(f"Discovery sync: {len(entities)} entities ({new_count} new, {renamed_count} renamed)")
    return {"total": len(entities), "new": new_count, "renamed": renamed_count, "domains": domain_counts}


def get_discovery_stats() -> dict:
    """Return current discovery stats without re-syncing."""
    if not os.path.exists(DISCOVERY_FILE):
        return {"synced": False, "total": 0}
    try:
        with open(DISCOVERY_FILE) as f:
            data = json.load(f)
        return {
            "synced": True,
            "last_sync": data.get("last_sync"),
            "total": data.get("total", 0),
            "new": data.get("new", 0),
            "renamed": data.get("renamed", 0),
            "domains": data.get("domains", {}),
        }
    except Exception as e:
        return {"synced": False, "error": str(e)}


async def discovery_loop(ha_url: str, ha_tkn: str, interval_hours: int = 6):
    """Background loop: sync every N hours."""
    logger.info(f"Discovery loop started (every {interval_hours}h)")
    # Initial sync after 30 seconds
    await asyncio.sleep(30)
    while True:
        try:
            await sync_entities(ha_url, ha_tkn)
        except Exception as e:
            logger.error(f"Discovery loop error: {e}")
        await asyncio.sleep(interval_hours * 3600)


def get_home_summary() -> str:
    """Build a concise home summary from discovered entities for LLM context."""
    if not os.path.exists(DISCOVERY_FILE):
        return ""
    try:
        with open(DISCOVERY_FILE) as f:
            data = json.load(f)
    except Exception:
        return ""

    domains = data.get("domains", {})
    total = data.get("total", 0)
    last_sync = data.get("last_sync", "unknown")

    # Room summary from entities
    rooms = {}
    for e in data.get("entities", []):
        room = e.get("room_guess", "غير مصنف")
        if room == "غير مصنف":
            continue
        domain = e.get("domain", "")
        if domain not in ("light", "switch", "climate", "cover", "fan", "media_player", "scene"):
            continue
        rooms.setdefault(room, {}).setdefault(domain, []).append(e.get("friendly_name", e["entity_id"]))

    lines = [f"البيت فيه {total} جهاز ({domains.get('light',0)} ضوء، {domains.get('switch',0)} سويتش، {domains.get('climate',0)} مكيف، {domains.get('cover',0)} ستارة، {domains.get('media_player',0)} سماعة/تلفزيون، {domains.get('scene',0)} مشهد)"]
    for room, devs in sorted(rooms.items()):
        counts = []
        for d, ents in devs.items():
            label = {"light":"ضوء","switch":"سويتش","climate":"مكيف","cover":"ستارة","fan":"مروحة","media_player":"ميديا","scene":"مشهد"}.get(d, d)
            counts.append(f"{len(ents)} {label}")
        lines.append(f"  {room}: {', '.join(counts)}")
    return "\n".join(lines)
