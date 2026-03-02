"""Step 6: Status Query Speed Templates"""
import httpx, os, logging

logger = logging.getLogger("quick_query")
HA_URL = os.getenv("HA_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")


def _arabize_room(name: str) -> str:
    """Strip bilingual room format and common English words."""
    if not name:
        return name
    if "/" in name:
        for p in name.split("/"):
            import re
            if len(re.findall(r"[a-zA-Z]", p)) < len(p.replace(" ", "") or "x") * 0.5:
                return p.strip()
    return name


async def _get_state(entity_id: str) -> dict:
    """Get single entity state from HA."""
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{HA_URL}/api/states/{entity_id}",
                          headers={"Authorization": f"Bearer {HA_TOKEN}"})
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.warning(f"State fetch failed for {entity_id}: {e}")
    return {}


async def execute_query(plan: dict) -> str:
    """Execute a status query and build Arabic response."""
    eids = plan.get("entity_ids", [plan.get("entity_id", "")])
    domain = plan.get("domain", "")
    room = plan.get("room", "")
    
    states = []
    for eid in eids[:15]:
        s = await _get_state(eid)
        if s:
            states.append(s)
    
    if not states:
        return "\u26a0\ufe0f \u0645\u0627 \u0642\u062f\u0631\u062a \u0623\u062c\u064a\u0628 \u062d\u0627\u0644\u0629 \u0627\u0644\u0623\u062c\u0647\u0632\u0629"
    
    room_ar = _arabize_room(room)
    
    if domain == "climate":
        title = "\U0001f321 \u062d\u0627\u0644\u0629 \u0627\u0644\u0645\u0643\u064a\u0641\u0627\u062a:" if len(states) > 1 else "\U0001f321 \u062d\u0627\u0644\u0629 \u0627\u0644\u0645\u0643\u064a\u0641:"
        lines = [title]
        for s in states:
            attrs = s.get("attributes", {})
            st = s.get("state", "unknown")
            fn = attrs.get("friendly_name", s.get("entity_id", "?"))
            ct = attrs.get("current_temperature", "?")
            target = attrs.get("temperature", "?")
            if st in ("off", "unknown", "unavailable"):
                lines.append(f"  \u274c {fn}: \u0645\u0637\u0641\u064a")
            else:
                lines.append(f"  \u2705 {fn}: {ct}\u00b0 (\u0647\u062f\u0641 {target}\u00b0)")
        return "\n".join(lines)
    
    elif domain in ("light", "switch", "fan"):
        on_names = []
        off_count = 0
        for s in states:
            fn = s.get("attributes", {}).get("friendly_name", "?")
            if s.get("state") == "on":
                on_names.append(fn)
            else:
                off_count += 1
        
        dtype_map = {"light": "\u0623\u0646\u0648\u0627\u0631", "switch": "\u0633\u0648\u064a\u062a\u0634\u0627\u062a", "fan": "\u0645\u0631\u0627\u0648\u062d"}
        dtype = dtype_map.get(domain, "\u0623\u062c\u0647\u0632\u0629")
        hdr = f"\U0001f4a1 {dtype}"
        if room_ar:
            hdr += f" {room_ar}"
        hdr += ":"
        
        if not on_names:
            return f"{hdr}\n  \u0643\u0644\u0647\u0627 \u0645\u0637\u0641\u064a\u0629 \u2705"
        elif off_count == 0:
            return f"{hdr}\n  \u0643\u0644\u0647\u0627 \u0634\u063a\u0627\u0644\u0629 ({len(on_names)}) \U0001f7e2"
        else:
            lines = [hdr]
            lines.append(f"  \U0001f7e2 \u0634\u063a\u0627\u0644 ({len(on_names)}): " + ", ".join(on_names[:5]))
            lines.append(f"  \u26aa \u0645\u0637\u0641\u064a ({off_count})")
            return "\n".join(lines)
    
    else:
        lines = [f"\U0001f50d \u0627\u0644\u062d\u0627\u0644\u0629 ({len(states)}):"]
        for s in states:
            fn = s.get("attributes", {}).get("friendly_name", "?")
            st = s.get("state", "?")
            lines.append(f"  {fn}: {st}")
        return "\n".join(lines)

async def execute_active_devices() -> str:
    """Step 8: Show all currently ON devices grouped by type."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{HA_URL}/api/states",
                          headers={"Authorization": f"Bearer {HA_TOKEN}"})
            if r.status_code != 200:
                return "\u26a0\ufe0f \u0645\u0627 \u0642\u062f\u0631\u062a \u0623\u0648\u0635\u0644 HA"
            states = r.json()
    except Exception as e:
        return f"\u26a0\ufe0f \u062e\u0637\u0623: {e}"
    
    # Filter ON devices from relevant domains
    active = {"light": [], "switch": [], "fan": [], "climate": [], "cover": [], "media_player": []}
    for s in states:
        eid = s.get("entity_id", "")
        domain = eid.split(".")[0]
        if domain not in active:
            continue
        st = s.get("state", "off")
        if domain == "climate" and st not in ("off", "unavailable"):
            fn = s.get("attributes", {}).get("friendly_name", eid)
            ct = s.get("attributes", {}).get("current_temperature", "?")
            active[domain].append(f"{fn} ({ct}\u00b0)")
        elif domain == "cover" and st == "open":
            fn = s.get("attributes", {}).get("friendly_name", eid)
            active[domain].append(fn)
        elif st == "on":
            fn = s.get("attributes", {}).get("friendly_name", eid)
            active[domain].append(fn)
    
    # Build response
    icons = {"light": "\U0001f4a1", "switch": "\U0001f50c", "fan": "\U0001f32c", 
             "climate": "\U0001f321", "cover": "\U0001fa9f", "media_player": "\U0001f4fa"}
    names = {"light": "\u0623\u0646\u0648\u0627\u0631", "switch": "\u0633\u0648\u064a\u062a\u0634\u0627\u062a", 
             "fan": "\u0645\u0631\u0627\u0648\u062d/\u0634\u0641\u0627\u0637\u0627\u062a", 
             "climate": "\u0645\u0643\u064a\u0641\u0627\u062a", "cover": "\u0633\u062a\u0627\u0626\u0631 \u0645\u0641\u062a\u0648\u062d\u0629", 
             "media_player": "\u0645\u064a\u062f\u064a\u0627"}
    
    total = sum(len(v) for v in active.values())
    if total == 0:
        return "\u2705 \u0645\u0627 \u0641\u064a \u0634\u064a \u0634\u063a\u0627\u0644 \u0628\u0627\u0644\u0628\u064a\u062a"
    
    lines = [f"\U0001f3e0 \u0634\u063a\u0627\u0644 \u0628\u0627\u0644\u0628\u064a\u062a ({total}):"]
    for dom in ["light", "climate", "fan", "switch", "cover", "media_player"]:
        items = active[dom]
        if items:
            icon = icons[dom]
            name = names[dom]
            if len(items) <= 3:
                lines.append(f"  {icon} {name}: " + ", ".join(items))
            else:
                lines.append(f"  {icon} {name} ({len(items)}): " + ", ".join(items[:3]) + "...")
    return "\n".join(lines)
