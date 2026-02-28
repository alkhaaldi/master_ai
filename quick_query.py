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
