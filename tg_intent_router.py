"""Phase A3: Telegram Intent Router — fast-path for common smart home commands.

Intercepts natural language BEFORE the AI agent to handle:
1. Direct device control: "شغل نور المعيشة", "طفي مكيف الديوانية"
2. State queries: "كم حرارة المكيف؟", "شنو حالة المعيشة؟"
3. Scene activation: "فعل مشهد النوم", "مشهد مغادرة"
4. Temperature set: "اضبط مكيف المعيشة على 22"

Returns None if no match → falls through to AI agent.
"""
import re, json, os, logging, httpx

logger = logging.getLogger("tg_intent")

HA_URL = os.getenv("HA_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")
BASE = os.path.dirname(os.path.abspath(__file__))

# -- Alias Learning System (Step 9) --
ALIAS_FILE = os.path.join(BASE, "data", "user_aliases.json")

def _load_aliases():
    try:
        if os.path.exists(ALIAS_FILE):
            with open(ALIAS_FILE) as _af:
                return json.load(_af)
    except Exception:
        pass
    return {}

def _save_aliases(aliases):
    try:
        os.makedirs(os.path.dirname(ALIAS_FILE), exist_ok=True)
        with open(ALIAS_FILE, "w") as _af:
            json.dump(aliases, _af, ensure_ascii=False, indent=2)
    except Exception:
        pass

def learn_alias(original_text, entity_id):
    aliases = _load_aliases()
    key = original_text.strip().lower()
    if len(key) < 3 or len(key) > 100:
        return
    aliases[key] = entity_id
    _save_aliases(aliases)
    logger.info(f"Alias learned: {key} -> {entity_id}")

def resolve_alias(text):
    aliases = _load_aliases()
    key = text.strip().lower()
    return aliases.get(key)

def get_alias_stats():
    aliases = _load_aliases()
    return {"total": len(aliases), "aliases": aliases}


# --- Action patterns ---
# Pattern: (verb)(optional_space)(device_keyword)(optional_space)(room_keyword)
ACTION_VERBS = {
    "شغل": "on", "افتح": "on", "فتح": "on", "ولع": "on", "نور": "on",
    "طفي": "off", "سكر": "off", "وقف": "off", "أغلق": "off",
    "زيد": "increase", "نقص": "decrease", "نزل": "decrease",
    "خفف": "dim", "عتم": "dim", "خفّف": "dim", "عتّم": "dim",
    "اضبط": "set_temp", "حط": "set_temp", "خل": "set_temp",
}

# Device keywords → entity domain + name fragment
DEVICE_KEYWORDS = {
    "نور": ("light", ""), "النور": ("light", ""), "الأنوار": ("light", ""),
    "أنوار": ("light", ""), "انوار": ("light", ""), "الانوار": ("light", ""),
    "اضاءة": ("light", ""), "اضاءات": ("light", ""), "إضاءة": ("light", ""), "الاضاءة": ("light", ""), "الإضاءة": ("light", ""), "اضاءه": ("light", ""),
    "سبوت": ("light", "spot"), "ستريب": ("light", "strip"),
    "مكيف": ("climate", ""), "المكيف": ("climate", ""), "المكيفات": ("climate", ""), "مكيفات": ("climate", ""),
    "ستارة": ("cover", ""), "الستارة": ("cover", ""), "ستائر": ("cover", ""),
    "شتر": ("cover", ""), "الشتر": ("cover", ""), "شتارات": ("cover", ""),  "الشتارات": ("cover", ""),
    "شفاط": ("switch", "شفاط"), "الشفاط": ("switch", "شفاط"),
    "منقي": ("fan", "منقي"), "المنقي": ("fan", "منقي"),
    "تلفزيون": ("media_player", "tv"), "التلفزيون": ("media_player", "tv"),
    "سماعة": ("media_player", "bluesound"), "السماعة": ("media_player", "bluesound"),
}

# Room keywords → room name fragments in entity_map
ROOM_KEYWORDS = {
    "معيشة": ["صالة المعيشة", "Living"],
    "المعيشة": ["صالة المعيشة", "Living"],
    "ديوانية": ["الديوانية", "Diwaniya"],
    "الديوانية": ["الديوانية", "Diwaniya"],
    "مطبخ": ["مطبخ", "Kitchen"],
    "المطبخ": ["مطبخ", "Kitchen"],
    "استقبال": ["استقبال", "Reception"],
    "الاستقبال": ["استقبال", "Reception"],
    "غرفتي": ["My room"],
    "غرفة": ["غرفة", "room"],
    "غرفه": ["غرفة", "room"],
    "ماستر": ["ماستر", "Master"],
    "ماما": ["mama", "ناهد"],
    "أمي": ["mama", "ناهد"],
    "أول": ["الدور الأول", "First"],
    "الأول": ["الدور الأول", "First"],
    "أرضي": ["الأرضي", "Ground"],
    "الأرضي": ["الأرضي", "Ground"],
    "ممر": ["ممر", "Men Room"],
    "حمام": ["حمام", "bath"],
    "ملابس": ["ملابس", "closet"],
    "مكتب": ["المكتب", "Office"],
    "المكتب": ["المكتب", "Office"],
}

# Query patterns
QUERY_WORDS = {"كم", "شنو", "وش", "حالة", "شحال", "درجة", "حرارة"}
# Step 6: Query verbs
QUERY_VERBS = {"شيك", "شيكي", "شلون", "كيف", "وريني", "ورني"}
QUERY_PREFIX = {"شنو", "وش", "كم", "هل"}

SCENE_WORDS = {"مشهد", "سين", "scene"}


def _load_entity_map():
    p = os.path.join(BASE, "entity_map.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _find_entities(emap, domain_filter, name_fragment, room_fragments):
    """Find matching entities from entity_map."""
    results = []
    for room, entities in emap.items():
        # Check room match
        room_match = True
        if room_fragments:
            room_match = any(rf.lower() in room.lower() for rf in room_fragments)
        if not room_match:
            continue

        for line in entities:
            if "=" in line:
                eid, name = line.split("=", 1)
            else:
                eid, name = line, line
            eid = eid.strip()
            name = name.strip()

            # Check domain
            if domain_filter and not eid.startswith(domain_filter + "."):
                continue

            # Check name fragment
            if name_fragment and name_fragment.lower() not in name.lower() and name_fragment.lower() not in eid.lower():
                continue

            # Skip backlights and helpers
            if "backlight" in eid.lower() or eid.startswith("input_") or eid.startswith("sensor."):
                continue

            results.append((eid, name, room))
    return results


def _extract_number(text):
    m = re.search(r"(\d+\.?\d*)", text)
    return float(m.group(1)) if m else None


async def _ha_call(entity_id, action, temp=None):
    """Execute HA service call. Returns (success, detail)."""
    domain = entity_id.split(".")[0]
    headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}

    svc_map = {
        "on": {"light": "turn_on", "switch": "turn_on", "fan": "turn_on", "climate": "turn_on", "cover": "open_cover", "media_player": "turn_on"},
        "off": {"light": "turn_off", "switch": "turn_off", "fan": "turn_off", "climate": "turn_off", "cover": "close_cover", "media_player": "turn_off"},
        "set_temp": {"climate": "set_temperature"},
    }
    svc = svc_map.get(action, {}).get(domain)
    if not svc:
        return False, f"unsupported: {action}/{domain}"

    data = {"entity_id": entity_id}
    if action == "set_temp" and temp is not None:
        data["temperature"] = temp
    elif action == "increase":
        # Get current temp and add 1
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(f"{HA_URL}/api/states/{entity_id}", headers=headers)
                ct = r.json().get("attributes", {}).get("temperature", 23)
                data["temperature"] = ct + 1
                svc = "set_temperature"
        except Exception:
            return False, "cant read temp"
    elif action == "decrease":
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(f"{HA_URL}/api/states/{entity_id}", headers=headers)
                ct = r.json().get("attributes", {}).get("temperature", 23)
                data["temperature"] = ct - 1
                svc = "set_temperature"
        except Exception:
            return False, "cant read temp"

    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(f"{HA_URL}/api/services/{domain}/{svc}", headers=headers, json=data)
        detail = f"{data.get('temperature', '')}°" if "temperature" in data else ""
        return True, detail
    except Exception as e:
        return False, str(e)


async def _ha_get_state(entity_id):
    """Get entity state from HA."""
    headers = {"Authorization": f"Bearer {HA_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{HA_URL}/api/states/{entity_id}", headers=headers)
            return r.json()
    except Exception:
        return None


async def route_intent(text: str) -> dict | None:
    """Try to route text to a fast-path handler.
    Returns dict {text, entities, action} or None."""
    # Step 9: Check learned aliases first
    _alias_eid = resolve_alias(text)
    if _alias_eid:
        _awords = text.strip().split()
        _act = None
        for _w in _awords:
            if _w in ACTION_VERBS:
                _act = ACTION_VERBS[_w]
                break
        if _act and _act != "query":
            _alias_r = await _ha_call(_alias_eid, _act)
            if _alias_r:
                logger.info(f"Alias hit: {text} -> {_alias_eid} ({_act})")
                return {"text": _alias_r, "entities": [_alias_eid], "action": _act, "source": "alias"}

    text = text.strip()
    words = text.split()
    if not words:
        return None

    emap = _load_entity_map()
    if not emap:
        return None

    first = words[0]

    # --- 1. Scene activation ---
    if any(sw in text for sw in SCENE_WORDS) or text.startswith("فعل"):
        return await _handle_scene(text, emap)

    # --- 2. State query ---
    if any(qw in text for qw in QUERY_WORDS):
        return await _handle_query(text, words, emap)

    # --- 3. Direct device control ---
    if first in ACTION_VERBS:
        return await _handle_action(text, words, emap)

    return None


async def _handle_scene(text, emap):
    """Activate a scene by name match."""
    # Remove scene trigger words
    clean = text
    for sw in ["فعل", "مشهد", "سين", "scene", "شغل"]:
        clean = clean.replace(sw, "").strip()

    # Find matching scene from HA states
    headers = {"Authorization": f"Bearer {HA_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{HA_URL}/api/states", headers=headers)
            states = r.json()
    except Exception:
        return None

    scenes = [s for s in states if s["entity_id"].startswith("scene.")]
    best = None
    for s in scenes:
        fname = s.get("attributes", {}).get("friendly_name", "")
        if clean.lower() in fname.lower() or clean.lower() in s["entity_id"].lower():
            best = s
            break

    if not best:
        return None

    # Activate scene
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(f"{HA_URL}/api/services/scene/turn_on", headers=headers, json={"entity_id": best["entity_id"]})
        fname = best.get("attributes", {}).get("friendly_name", best["entity_id"])
        return {"text": f"🎬 فعّلت مشهد *{fname}*", "entities": [], "action": "scene"}
    except Exception:
        return None


async def _handle_query(text, words, emap):
    """Handle state/status queries."""
    # Find device and room from text
    domain_filter = None
    name_frag = ""
    room_frags = []

    for w in words:
        if w in DEVICE_KEYWORDS:
            domain_filter, name_frag = DEVICE_KEYWORDS[w]
        if w in ROOM_KEYWORDS:
            room_frags = ROOM_KEYWORDS[w]

    if not domain_filter and not room_frags:
        return None  # Too vague, let AI handle

    entities = _find_entities(emap, domain_filter, name_frag, room_frags)
    if not entities:
        return None

    # Get states
    lines = ["🔍 *الحالة:*\n"]
    for eid, name, room in entities[:8]:
        state = await _ha_get_state(eid)
        if not state:
            continue
        st = state.get("state", "?")
        attrs = state.get("attributes", {})

        if eid.startswith("climate."):
            ct = attrs.get("current_temperature", "?")
            target = attrs.get("temperature", "?")
            lines.append(f"❄️ {name}: {ct}° (هدف {target}°)")
        elif st == "on":
            lines.append(f"🟢 {name}")
        elif st == "off":
            lines.append(f"⚫ {name}")
        elif st in ("open", "opening"):
            lines.append(f"🟢⬆ {name}")
        elif st in ("closed", "closing"):
            lines.append(f"⚫⬇ {name}")
        else:
            lines.append(f"• {name}: {st}")

    return "\n".join(lines) if len(lines) > 1 else None


async def _handle_action(text, words, emap):
    """Handle direct device control commands."""
    first = words[0]
    action = ACTION_VERBS.get(first)
    if not action:
        return None

    rest = words[1:]
    temp = _extract_number(text)

    # Parse device and room from remaining words
    domain_filter = None
    name_frag = ""
    room_frags = []

    for w in rest:
        if w in DEVICE_KEYWORDS:
            domain_filter, name_frag = DEVICE_KEYWORDS[w]
        if w in ROOM_KEYWORDS:
            room_frags = ROOM_KEYWORDS[w]
        # Handle "على" (for temperature)
        if w == "على":
            continue

    if not domain_filter and not room_frags:
        return None  # Can't determine target

    entities = _find_entities(emap, domain_filter, name_frag, room_frags)
    if not entities:
        return None

    # For set_temp without number
    if action == "set_temp" and temp is None:
        return {"text": "🌡️ كم تبي الحرارة؟", "entities": [], "action": "set_temp"}

    # Execute on all matching entities
    results = []
    for eid, name, room in entities:
        ok, detail = await _ha_call(eid, action, temp)
        results.append((ok, name, detail))

    success = [(n, d) for ok, n, d in results if ok]
    failed = [(n, d) for ok, n, d in results if not ok]

    if not success and not failed:
        return None

    icons = {"on": "🟢", "off": "⚫", "set_temp": "🌡️", "set_brightness": "💡", "dim": "💡", "increase": "🔥", "decrease": "❄️"}
    verbs = {"on": "شغّلت", "off": "طفّيت", "set_temp": "ضبطت", "set_brightness": "ضبطت إضاءة", "increase": "رفعت حرارة", "decrease": "نزّلت حرارة"}
    icon = icons.get(action, "✅")
    verb = verbs.get(action, action)

    eids = [eid for eid, _, _ in entities]

    if len(success) == 1:
        name, detail = success[0]
        return {"text": f"{icon} {verb} *{name}* {detail}".strip(), "entities": eids, "action": action}

    lines = [f"{icon} {verb} *{len(success)}* أجهزة:"]
    for name, detail in success:
        lines.append(f"  ✅ {name} {detail}".strip())
    if failed:
        for name, detail in failed:
            lines.append(f"  ❌ {name}")
    return {"text": "\n".join(lines), "entities": eids, "action": action}


# ── Speed Engine: quick_classify (Step 2) ──
# Guarded domains that must NOT use speed templates
_GUARDED_DOMAINS = {"lock", "alarm_control_panel"}

def quick_classify(text: str, session_ctx: dict = None) -> dict | None:
    """Classify text into a plan WITHOUT executing.
    Returns {intent, action, entity_id, entity_name, domain, value, room} or None.
    Only returns a plan if exactly ONE entity matches and intent is clear."""
    # Step 9: Check aliases first
    _alias_eid = resolve_alias(text)
    if _alias_eid:
        _awords = text.strip().split()
        _act = None
        for _w in _awords:
            if _w in ACTION_VERBS:
                _act = ACTION_VERBS[_w]
                break
        if _act and _act not in ("query", "increase", "decrease"):
            _domain = _alias_eid.split(".")[0]
            if _domain in _GUARDED_DOMAINS:
                return None
            return {"intent": _act, "action": _act, "entity_id": _alias_eid,
                    "entity_name": _alias_eid.split(".")[-1].replace("_", " "),
                    "domain": _domain, "value": None, "room": None, "source": "alias"}

    text_s = text.strip()
    words = text_s.split()
    # Step 7: Reject compound commands (شغل X وطفي Y)
    if " و" in text_s:
        _cp = text_s.split(" و")
        if len(_cp) >= 2:
            _nv = sum(1 for _p in _cp if any(_v in _p.split() for _v in list(ACTION_VERBS.keys())[:15]))
            if _nv >= 2:
                return None
    if not words:
        return None

    emap = _load_entity_map()
    if not emap:
        return None

    first = words[0]

    # --- Step 8: Quick chat responses ---
    _QUICK_CHAT = {
        # Greetings
        "مرحبا": "أهلين! شلون أقدر أساعدك؟ 👋",
        "هلا": "هلا والله! أمر 👋",
        "السلام عليكم": "وعليكم السلام! شلون أقدر أخدمك؟",
        "سلام": "وعليكم السلام ✌️",
        "هاي": "هلا! 👋",
        # Gratitude
        "شكرا": "العفو! إذا تحتاج شي ثاني أمر 😊",
        "مشكور": "ولا يهمك! 😊",
        "يعطيك العافية": "الله يعافيك! 💪",
        "تسلم": "الله يسلمك! 🙏",
        # Status
        "شلونك": "الحمدلله تمام! جاهز لأي أمر ⚡",
        "كيفك": "تمام الحمدلله! شلون أساعدك؟ ⚡",
        "شخبارك": "بخير الحمدلله! أمر 😊",
        # Capabilities
        "شنو تقدر تسوي": "أقدر أتحكم بالأنوار والمكيفات والستائر والشفاطات 💡🌡️🪟\nوأشيك الحالة وأفعّل المشاهد 🎬\nجرب: شغل نور المعيشة، وضع النوم، شيك المكيفات",
        "وش تسوي": "أقدر أتحكم بالأنوار والمكيفات والستائر والشفاطات 💡🌡🪟. جرب: شغل نور المعيشة / وضع النوم / شيك المكيفات",
    }
    _chat_norm = __import__("re").sub(r"[ً-ٟ?!؟]", "", text_s).strip()
    if _chat_norm in _QUICK_CHAT:
        return {"intent": "chat", "action": "chat", "entity_id": "", "entity_name": "",
                "domain": "", "value": _QUICK_CHAT[_chat_norm], "room": "", "source": "quick_chat"}

    # --- Step 2: Pronoun followup (طفيه/شغله/أطفيه) ---
    _PRONOUN_SUFFIXED = {
        "طفيه": "off", "أطفيه": "off", "اطفيه": "off",
        "شغله": "on", "أشغله": "on", "اشغله": "on",
        "سكره": "off", "افتحه": "on", "فتحه": "on",
        "طفهم": "off", "شغلهم": "on", "سكرهم": "off", "افتحهم": "on",
    }
    if text_s in _PRONOUN_SUFFIXED and session_ctx:
        _last_ents = session_ctx.get("last_entities") or []
        _pact = _PRONOUN_SUFFIXED[text_s]
        if len(_last_ents) == 1:
            _pe = _last_ents[0]
            _pd = _pe.split(".")[0]
            if _pd not in _GUARDED_DOMAINS:
                return {"intent": _pact, "action": _pact,
                        "entity_id": _pe, "entity_name": _pe.split(".")[-1].replace("_", " "),
                        "domain": _pd, "value": None, "room": None, "source": "followup_pronoun"}
        elif len(_last_ents) > 1 and _pact in ("on", "off"):
            # Step 4: Multi-device pronoun followup
            _safe = [e for e in _last_ents if e.split(".")[0] not in _GUARDED_DOMAINS]
            if _safe:
                _pd = _safe[0].split(".")[0]
                _room = session_ctx.get("last_room", "")
                return {"intent": _pact, "action": _pact,
                        "entity_ids": _safe, "entity_names": [e.split(".")[-1].replace("_"," ") for e in _safe],
                        "entity_id": _safe[0], "entity_name": _safe[0].split(".")[-1].replace("_"," "),
                        "domain": _pd, "value": None, "room": _room,
                        "multi": True, "count": len(_safe), "source": "followup_pronoun_multi"}

        # --- Step 5: Scene activation (direct name match) ---
    # Common shorthand aliases for scenes
    _SCENE_ALIASES = {
        "سكر الستائر": "scene.skwr_kl_lstyr",
        "سكر كل الستائر": "scene.skwr_kl_lstyr",
        "فتح الستائر": "scene.fth_kl_lstyr",
        "افتح الستائر": "scene.fth_kl_lstyr",
        "افتح كل الستائر": "scene.fth_kl_lstyr",
        "طفي الحمامات": "scene.tf_kl_lhmmt",
        "طفي كل الحمامات": "scene.tf_kl_lhmmt",
        "طفي الشفاطات": "scene.glq_kl_lshftt",
        "طفي الملابس": "scene.tf_kl_grf_lmlbs",
        "طفي كل الملابس": "scene.tf_kl_grf_lmlbs",
        "طفي الارضي": "scene.tf_lrdy",
        "اطفاء الارضي": "scene.tf_lrdy",
        "طفي الاول": "scene.tf_grf_lwl",
        "اطفاء الاول": "scene.tf_grf_lwl",
        "تنقية الهواء": "scene.tnqy_hw_shml",
        "تنقية هواء": "scene.tnqy_hw_shml",
    }
    _alias_norm = __import__("re").sub(r"[ً-ٟ]", "", text_s)
    if _alias_norm in _SCENE_ALIASES:
        _sa_eid = _SCENE_ALIASES[_alias_norm]
        # Find name from emap
        for _sar, _saents in emap.items():
            for _sal in _saents:
                if "=" in _sal and _sal.split("=")[0] == _sa_eid:
                    return {"intent": "scene_activate", "action": "scene", "entity_id": _sa_eid,
                            "entity_name": _sal.split("=")[1], "domain": "scene", "value": None,
                            "room": _sar, "source": "classify_scene_alias"}

    # Build scene lookup from entity_map
    _scene_matches = []
    for _sroom, _sents in emap.items():
        for _sline in _sents:
            if "=" not in _sline:
                continue
            _seid, _sname = _sline.split("=", 1)
            if not _seid.startswith("scene."):
                continue
            # Clean scene name: remove emojis and normalize
            import re as _re3
            _clean = _re3.sub(r"[🌀-🧿☀-➿]", "", _sname).strip()
            _clean_low = __import__("re").sub(r"[ً-ٟ]", "", _clean).lower()
            # Check: does text match or closely match scene name?
            _txt_low = text_s.lower()
            # Step 7: Require min 60% overlap to avoid false positives
            _match_ratio = min(len(_txt_low), len(_clean_low)) / max(len(_clean_low), 1)
            if (_txt_low == _clean_low) or (_txt_low in _clean_low and _match_ratio > 0.6) or (_clean_low in _txt_low and _match_ratio > 0.6):
                _scene_matches.append((_seid, _sname, _sroom, len(_clean)))
    # Also check with SCENE_WORDS stripped
    if not _scene_matches:
        _scene_text = text_s
        for _sw in list(SCENE_WORDS) + ["فعّل", "شغل", "فعل"]:
            _scene_text = _scene_text.replace(_sw, "").strip()
        if _scene_text and _scene_text != text_s:
            for _sroom, _sents in emap.items():
                for _sline in _sents:
                    if "=" not in _sline:
                        continue
                    _seid, _sname = _sline.split("=", 1)
                    if not _seid.startswith("scene."):
                        continue
                    import re as _re4
                    _clean = _re4.sub(r"[🌀-🧿☀-➿]", "", _sname).strip().lower()
                    # Step 7: Same ratio check for fallback
                    _fr = min(len(_scene_text), len(_clean)) / max(len(_clean), 1)
                    if (_scene_text.lower() == _clean) or (_scene_text.lower() in _clean and _fr > 0.6) or (_clean in _scene_text.lower() and _fr > 0.6):
                        _scene_matches.append((_seid, _sname, _sroom, len(_clean)))
    if _scene_matches:
        # Pick best: longest name match (most specific)
        _scene_matches.sort(key=lambda x: x[3], reverse=True)
        _best = _scene_matches[0]
        return {"intent": "scene_activate", "action": "scene", "entity_id": _best[0],
                "entity_name": _best[1], "domain": "scene", "value": None,
                "room": _best[2], "source": "classify_scene"}

    # --- Step 8: Global status queries ---
    _GLOBAL_QUERIES = {
        "شنو شغال": "active_devices",
        "شنو شغال بالبيت": "active_devices",
        "وش شغال": "active_devices",
        "وش مفتوح": "active_devices",
        "شنو مفتوح": "active_devices",
    }
    _gq_norm = __import__("re").sub(r"[ً-ٟ?؟]", "", text_s).strip()
    if _gq_norm in _GLOBAL_QUERIES:
        return {"intent": "query", "action": "query",
                "entity_ids": [], "entity_names": [],
                "entity_id": "", "entity_name": "",
                "domain": "all", "value": None, "room": "",
                "query_type": _GLOBAL_QUERIES[_gq_norm], "count": 0,
                "source": "classify_query_global"}

    # --- Step 6: Status query detection ---
    _is_query = False
    _q_domain = None
    _q_room = []
    _q_name_frag = ""
    if first in QUERY_VERBS or first in QUERY_PREFIX or any(qw in text_s for qw in ("حالة", "حرارة", "درجة", "شغال", "شغالة", "مفتوح", "مسكر")):
        _is_query = True
        _rest_q = words[1:] if first in QUERY_VERBS or first in QUERY_PREFIX else words
        _qi = 0
        while _qi < len(_rest_q):
            _qw = _rest_q[_qi]
            if _qw in DEVICE_KEYWORDS:
                _q_domain, _q_name_frag = DEVICE_KEYWORDS[_qw]
            elif _qw in ROOM_KEYWORDS:
                _qcomp = _qw
                if _qi + 1 < len(_rest_q) and _rest_q[_qi + 1].isdigit():
                    _qcomp = _qw + " " + _rest_q[_qi + 1]
                    _qi += 1
                if _qcomp in ROOM_KEYWORDS:
                    _q_room = ROOM_KEYWORDS[_qcomp]
                else:
                    _q_room = [_qcomp]
            _qi += 1
        if _q_domain or _q_room:
            _q_ents = _find_entities(emap, _q_domain or "light", _q_name_frag, _q_room)
            if _q_ents:
                return {"intent": "query", "action": "query",
                        "entity_ids": [e[0] for e in _q_ents[:15]],
                        "entity_names": [e[1] for e in _q_ents[:15]],
                        "entity_id": _q_ents[0][0], "entity_name": _q_ents[0][1],
                        "domain": _q_domain or _q_ents[0][0].split(".")[0],
                        "value": None, "room": _q_ents[0][2],
                        "query_type": "status", "count": len(_q_ents[:15]),
                        "source": "classify_query"}

    # --- Device control ---
    if first not in ACTION_VERBS:
        return None
    action = ACTION_VERBS[first]
    # Step 9: Brightness + temperature increase/decrease
    if action == "dim":
        action = "set_brightness"  # will extract % from rest
    if action in ("increase", "decrease"):
        pass  # Allow through for temperature control

    rest = " ".join(words[1:])

    # Extract temperature
    temp = None
    if action == "set_temp":
        import re as _re
        m = _re.search(r"(\d+)", rest)
        if m:
            temp = int(m.group(1))

    # Find device + room
    domain_filter = None
    name_frag = ""
    room_frags = []
    _rest = words[1:]
    _i = 0
    while _i < len(_rest):
        w = _rest[_i]
        if w in DEVICE_KEYWORDS:
            d, nf = DEVICE_KEYWORDS[w]
            domain_filter = d
            if nf:
                name_frag = nf
        elif w in ROOM_KEYWORDS:
            # Step 4: Combine room word + following number (e.g. "غرفة 3")
            compound = w
            if _i + 1 < len(_rest) and _rest[_i + 1].isdigit():
                compound = w + " " + _rest[_i + 1]
                _i += 1
            if compound in ROOM_KEYWORDS:
                room_frags = ROOM_KEYWORDS[compound]
            else:
                room_frags = [compound]  # use compound as-is for matching
        _i += 1

    if not domain_filter:
        return None

    entities = _find_entities(emap, domain_filter, name_frag, room_frags)
    # Step 2: Smart disambiguation for generic "نور" → prefer chandelier
    if len(entities) > 1 and domain_filter == "light" and not name_frag:
        _chandelier = [e for e in entities if any(kw in e[1].lower() for kw in ("chandl", "ثريا", "switch_1")) and "strip" not in e[1].lower() and "spot" not in e[1].lower() and "backlight" not in e[1].lower() and "mirror" not in e[1].lower()]
        if len(_chandelier) == 1:
            entities = _chandelier
    # Step 2: Default room for climate when no room specified
    if len(entities) > 1 and domain_filter == "climate" and not room_frags:
        _master = [e for e in entities if "master" in e[2].lower() or "ماستر" in e[2]]
        if len(_master) == 1:
            entities = _master
    # Step 9: Brightness control
    _brightness_pct = None
    if action in ("dim", "set_brightness") and domain_filter == "light":
        import re as _reb
        _bm = _reb.search(r"(\d+)", rest)
        _brightness_pct = int(_bm.group(1)) if _bm else 30  # default dim=30%
        action = "set_brightness"
    elif action == "set_temp" and domain_filter == "light":
        # "خل النور 50" -> brightness not temp
        import re as _reb2
        _bm2 = _reb2.search(r"(\d+)", rest)
        if _bm2:
            _brightness_pct = int(_bm2.group(1))
            action = "set_brightness"
    elif action == "increase" and domain_filter == "light":
        _brightness_pct = -1  # signal: increase by 25%
        action = "set_brightness"
    elif action == "decrease" and domain_filter == "light":
        _brightness_pct = -2  # signal: decrease by 25%
        action = "set_brightness"

    if len(entities) == 0:
        return None
    
    # Single entity - original behavior
    if len(entities) == 1:
        eid, name, room = entities[0]
        _domain = eid.split(".")[0]
        if _domain in _GUARDED_DOMAINS:
            return None
        return {"intent": action, "action": action, "entity_id": eid,
                "entity_name": name, "domain": _domain, "value": _brightness_pct if _brightness_pct is not None else temp,
                "room": room, "source": "classify"}

    # Step 4: Multi-device support for simple on/off only
    MAX_MULTI = 20
    if action in ("on", "off", "set_brightness") and len(entities) <= MAX_MULTI and (room_frags or name_frag or action == "set_brightness"):
        # Filter out guarded domains
        safe = [(e, n, r) for e, n, r in entities if e.split(".")[0] not in _GUARDED_DOMAINS]
        if not safe:
            return None
        # Build multi-entity plan
        eids = [e for e, n, r in safe]
        names = [n for e, n, r in safe]
        _domain = eids[0].split(".")[0]
        _room = safe[0][2]
        return {"intent": action, "action": action,
                "entity_ids": eids, "entity_names": names,
                "entity_id": eids[0], "entity_name": names[0],
                "domain": _domain, "value": _brightness_pct if _brightness_pct is not None else temp,
                "room": _room, "multi": True, "count": len(safe),
                "source": "classify_multi"}
    
    return None  # Too many or unsupported action for multi
