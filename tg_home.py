"""Level 2 Telegram Home commands — rooms, devices, find, scenes (dynamic)."""
import json, os, time, logging, httpx

logger = logging.getLogger("tg_home")

# --- Config ---
HA_URL = os.getenv("HA_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")
BASE = os.path.dirname(os.path.abspath(__file__))

# --- HA States Cache (TTL 45s) ---
_ha_cache = {"states": [], "ts": 0}
CACHE_TTL = 45

async def _get_ha_states():
    now = time.time()
    if _ha_cache["states"] and (now - _ha_cache["ts"]) < CACHE_TTL:
        return _ha_cache["states"]
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{HA_URL}/api/states",
                            headers={"Authorization": f"Bearer {HA_TOKEN}"})
            if r.status_code == 200:
                _ha_cache["states"] = r.json()
                _ha_cache["ts"] = now
    except Exception as e:
        logger.error(f"HA cache refresh: {e}")
    return _ha_cache["states"]

# --- Load entity_map.json ---
def _load_entity_map():
    p = os.path.join(BASE, "entity_map.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

# --- Load knowledge.json aliases ---
def _load_aliases():
    p = os.path.join(BASE, "knowledge.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("device_aliases", [])
    except Exception:
        return []

# --- Parse entity line: "entity_id=friendly_name" ---
def _parse_entity(line):
    if "=" in line:
        eid, name = line.split("=", 1)
        return eid.strip(), name.strip()
    return line.strip(), line.strip()

# --- Entity type category ---
def _category(eid):
    if eid.startswith("light."): return "lights"
    if eid.startswith("climate."): return "climate"
    if eid.startswith("cover."): return "covers"
    if eid.startswith("fan."): return "fans"
    if eid.startswith("media_player."): return "media"
    if eid.startswith("sensor."): return "sensors"
    if eid.startswith("switch."): return "switches"
    if eid.startswith("scene.") or "backlight" in eid.lower() or "Backlight" in name: return "scenes"
    if eid.startswith("air_quality.") or eid.startswith("humidifier."): return "air"
    return "other"

CATEGORY_ICONS = {
    "lights": "\U0001f4a1", "climate": "\u2744\ufe0f", "covers": "\U0001f6aa",
    "fans": "\U0001f32c\ufe0f", "media": "\U0001f3b5", "sensors": "\U0001f4ca",
    "switches": "\u26a1", "scenes": "\U0001f3ac", "air": "\U0001f32b\ufe0f",
    "other": "\u2699\ufe0f"
}

# --- State shorthand ---
def _short_state(eid, states_map):
    s = states_map.get(eid)
    if not s: return "?"
    st = s.get("state", "?")
    if st == "unavailable": return "\u274c"
    if eid.startswith("climate."):
        temp = s.get("attributes", {}).get("current_temperature", "?")
        return f"{temp}\u00b0"
    if st == "on": return "\U0001f7e2"
    if st == "off": return "\u26ab"
    if st in ("open", "opening"): return "\U0001f7e2\u2b06"
    if st in ("closed", "closing"): return "\u26ab\u2b07"
    return st[:8]

def _should_skip(eid, name, seen_bases=None):
    if "backlight" in eid.lower() or "Backlight" in name:
        return True
    if eid.startswith("switch."):
        light_eid = "light." + eid[len("switch."):]
        if seen_bases is not None and light_eid in seen_bases:
            return True
    return False

def _build_seen_set(entity_lines):
    s = set()
    for line in entity_lines:
        eid, _ = _parse_entity(line)
        s.add(eid)
    return s

# ============= COMMANDS =============

async def cmd_rooms():
    emap = _load_entity_map()
    if not emap:
        return "entity_map.json not found"
    lines = []
    for room, entities in emap.items():
        if room == "\u0627\u0644\u0645\u0634\u0627\u0647\u062f/Scenes":
            continue
        count = len([e for e in entities if not _parse_entity(e)[0].startswith("scene.")])
        lines.append(f"\U0001f3e0 {room}  ({count})")
    return "\U0001f3e0 *\u0627\u0644\u063a\u0631\u0641* \n\n" + "\n".join(lines)


async def cmd_devices(room_query):
    emap = _load_entity_map()
    if not emap:
        return "entity_map.json not found"
    # Find matching room (case-insensitive, contains)
    q = room_query.strip().lower()
    match_room = None
    match_entities = None
    for room, entities in emap.items():
        if q in room.lower():
            match_room = room
            match_entities = entities
            break
    if not match_room:
        # Suggest closest 3
        suggestions = [r for r in emap.keys() if r != "\u0627\u0644\u0645\u0634\u0627\u0647\u062f/Scenes"][:3]
        return "\u2753 \u0645\u0627 \u0644\u0642\u064a\u062a \u0627\u0644\u063a\u0631\u0641\u0629. \u062c\u0631\u0628:\n" + "\n".join(f"\u2022 {s}" for s in suggestions)

    states = await _get_ha_states()
    smap = {s["entity_id"]: s for s in states}

    all_eids = _build_seen_set(match_entities)
    cats = {}
    for line in match_entities:
        eid, name = _parse_entity(line)
        if eid.startswith("scene.") or _should_skip(eid, name, all_eids):
            continue
        cat = _category(eid)
        if cat not in cats:
            cats[cat] = []
        st = _short_state(eid, smap)
        cats[cat].append(f"{st} {name}")

    text = f"\U0001f3e0 *{match_room}*\n\n"
    for cat, items in cats.items():
        icon = CATEGORY_ICONS.get(cat, "")
        text += f"{icon} *{cat}* ({len(items)}):\n"
        for item in items:
            text += f"  {item}\n"
        text += "\n"
    return text.strip()


async def cmd_find(keyword):
    if not keyword or len(keyword) < 2:
        return "\u0627\u0643\u062a\u0628 \u0643\u0644\u0645\u0629 \u0628\u062d\u062b (\u062d\u062f \u0623\u062f\u0646\u0649 \u062d\u0631\u0641\u064a\u0646)"
    q = keyword.strip().lower()
    emap = _load_entity_map()
    aliases = _load_aliases()
    states = await _get_ha_states()
    smap = {s["entity_id"]: s for s in states}

    results = []
    seen = set()

    # Search entity_map
    all_map_eids = set()
    for _r, _ents in emap.items():
        for _l in _ents:
            _e, _ = _parse_entity(_l)
            all_map_eids.add(_e)
    for room, entities in emap.items():
        for line in entities:
            eid, name = _parse_entity(line)
            if eid in seen:
                continue
            if _should_skip(eid, name, all_map_eids):
                continue
            if q in eid.lower() or q in name.lower():
                seen.add(eid)
                st = _short_state(eid, smap)
                results.append((eid, name, st, room))

    # Search aliases
    for alias in aliases:
        patterns = alias.get("patterns", [])
        if any(q in p.lower() for p in patterns):
            for eid in alias.get("entities", []):
                if eid in seen:
                    continue
                seen.add(eid)
                fname = smap.get(eid, {}).get("attributes", {}).get("friendly_name", eid)
                st = _short_state(eid, smap)
                results.append((eid, fname, st, ""))

    # Search HA states friendly_name
    for s in states:
        eid = s["entity_id"]
        if eid in seen:
            continue
        fname = s.get("attributes", {}).get("friendly_name", "")
        if q in eid.lower() or q in fname.lower():
            seen.add(eid)
            st = _short_state(eid, smap)
            results.append((eid, fname, st, ""))

    if not results:
        return f"\U0001f50d \u0645\u0627 \u0644\u0642\u064a\u062a \u0634\u064a \u0639\u0646: {keyword}"

    results = results[:10]
    lines = [f"\U0001f50d *\u0646\u062a\u0627\u0626\u062c ({len(results)}):*\n"]
    for eid, name, st, room in results:
        r_tag = f" [{room}]" if room else ""
        lines.append(f"{st} {name}{r_tag}")
    return "\n".join(lines), results  # Return results for inline buttons


def find_buttons(results):
    buttons = []
    for eid, name, st, room in results[:10]:
        cat = _category(eid)
        short = name[:20]
        if cat in ("lights", "switches"):
            buttons.append([
                {"text": f"\U0001f7e2 {short}", "callback_data": f"devctl:on:{eid}"},
                {"text": f"\u26ab {short}", "callback_data": f"devctl:off:{eid}"}
            ])
        elif cat == "covers":
            buttons.append([
                {"text": f"\u2b06 {short}", "callback_data": f"devctl:open:{eid}"},
                {"text": f"\u2b07 {short}", "callback_data": f"devctl:close:{eid}"},
                {"text": f"\u23f9 Stop", "callback_data": f"devctl:stop:{eid}"}
            ])
    return buttons


async def cmd_scenes_dynamic():
    states = await _get_ha_states()
    scenes = [s for s in states if s["entity_id"].startswith("scene.")]
    if not scenes:
        return "\u0645\u0627 \u0641\u064a \u0645\u0634\u0627\u0647\u062f", []
    buttons = []
    for s in scenes[:20]:
        fname = s.get("attributes", {}).get("friendly_name", s["entity_id"])
        buttons.append({"text": fname, "callback_data": f"sc:{s['entity_id']}"})
    return f"\U0001f3ac *\u0627\u0644\u0645\u0634\u0627\u0647\u062f* ({len(scenes)})", buttons


async def handle_devctl(action, entity_id):
    domain = entity_id.split(".")[0]
    svc_map = {
        "on": ("turn_on", domain),
        "off": ("turn_off", domain),
        "open": ("open_cover", "cover"),
        "close": ("close_cover", "cover"),
        "stop": ("stop_cover", "cover"),
    }
    if action not in svc_map:
        return f"Unknown action: {action}"
    svc, dom = svc_map[action]
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{HA_URL}/api/services/{dom}/{svc}",
                headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
                json={"entity_id": entity_id}
            )
            if r.status_code == 200:
                return f"\u2705 {svc} {entity_id}"
            return f"\u274c Error {r.status_code}"
    except Exception as e:
        return f"\u274c {e}"
