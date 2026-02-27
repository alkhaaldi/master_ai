"""Follow-up Action Resolver v2 for Telegram Session Intelligence."""
import httpx, logging

logger = logging.getLogger("tg_resolver")

SERVICE_MAP = {
    "on":  {"light": "turn_on", "switch": "turn_on", "fan": "turn_on", "climate": "turn_on", "cover": "open_cover", "media_player": "turn_on"},
    "off": {"light": "turn_off", "switch": "turn_off", "fan": "turn_off", "climate": "turn_off", "cover": "close_cover", "media_player": "turn_off"},
    "increase": {"climate": "set_temperature"},
    "decrease": {"climate": "set_temperature"},
    "set_temp": {"climate": "set_temperature"},
}
ACTION_ICONS = {"on": "\U0001f7e2", "off": "\u26ab", "increase": "\U0001f525", "decrease": "\u2744\ufe0f", "set_temp": "\U0001f321\ufe0f"}


async def _call_ha(ha_url, ha_token, eid, action, temp=None):
    """Call a single HA service. Returns (success, friendly_name, detail)."""
    domain = eid.split(".")[0]
    svc = SERVICE_MAP.get(action, {}).get(domain)
    if not svc:
        return False, eid, f"unsupported: {action} on {domain}"
    headers = {"Authorization": f"Bearer {ha_token}", "Content-Type": "application/json"}
    data = {"entity_id": eid}
    
    if action == "set_temp":
        if temp is not None:
            data["temperature"] = temp
        else:
            return False, eid, "no temp specified"
    elif action in ("increase", "decrease"):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{ha_url}/api/states/{eid}", headers=headers)
                ct = r.json().get("attributes", {}).get("temperature", 23)
                data["temperature"] = ct + (1 if action == "increase" else -1)
        except Exception:
            data["temperature"] = 23
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{ha_url}/api/services/{domain}/{svc}", headers=headers, json=data)
        # Try HA API for friendly_name, fallback to entity_id parsing
            # Get friendly_name while client is open
            fname = eid.split(".")[-1].replace("_", " ").title()
            try:
                sr = await client.get(f"{ha_url}/api/states/{eid}", headers={"Authorization": f"Bearer {ha_token}"})
                if sr.status_code == 200:
                    fname = sr.json().get("attributes", {}).get("friendly_name", fname)
            except Exception:
                pass
        detail = f"{data.get('temperature', '')}\u00b0" if "temperature" in data else ""
        return True, fname, detail
    except Exception as e:
        logger.error(f"HA call failed: {e}")
        return False, eid, str(e)


async def resolve_followup_action(followup: dict, ha_url: str, ha_token: str) -> str:
    """Execute follow-up action. Handles single, multi-entity, and temperature targets."""
    eid = followup.get("target_entity")
    action = followup.get("action")
    entities = followup.get("all_entities") or followup.get("last_entities") or []
    temp = followup.get("temp")
    
    if not action and not eid and not entities:
        return "\u2753 \u0645\u0627 \u0639\u0631\u0641\u062a \u0634\u0646\u0648 \u062a\u0642\u0635\u062f \u2014 \u062c\u0631\u0628 /find"
    
    if not action:
        return "\u2753 \u0634\u0646\u0648 \u062a\u0628\u064a\u0646\u064a \u0623\u0633\u0648\u064a\u061f (\u0634\u063a\u0644\u0647/\u0637\u0641\u064a\u0647/\u0627\u0636\u0628\u0637 \u0639\u0644\u0649 22)"
    
    # set_temp without number
    if action == "set_temp" and temp is None:
        return "\U0001f321\ufe0f \u0643\u0645 \u062a\u0628\u064a \u0627\u0644\u062d\u0631\u0627\u0631\u0629\u061f (\u0645\u062b\u0627\u0644: \u0627\u0636\u0628\u0637 \u0627\u0644\u0623\u0648\u0644 \u0639\u0644\u0649 22)"
    
    # Single target specified
    if eid:
        ok, fname, detail = await _call_ha(ha_url, ha_token, eid, action, temp)
        icon = ACTION_ICONS.get(action, "\u2705")
        ar = {
            "on": "\u0634\u063a\u0651\u0644\u062a", "off": "\u0637\u0641\u0651\u064a\u062a",
            "increase": "\u0631\u0641\u0639\u062a \u062d\u0631\u0627\u0631\u0629",
            "decrease": "\u0646\u0632\u0651\u0644\u062a \u062d\u0631\u0627\u0631\u0629",
            "set_temp": "\u0636\u0628\u0637\u062a"
        }.get(action, action)
        if ok:
            return f"{icon} {ar} *{fname}* {detail}".strip()
        return f"\u274c {fname} \u2014 {detail}"
    
    # No specific target but have entities -> apply to ALL
    if entities:
        results = []
        for e in entities:
            ok, fname, detail = await _call_ha(ha_url, ha_token, e, action, temp)
            results.append((ok, fname, detail))
        
        success = [(fname, detail) for ok, fname, detail in results if ok]
        failed = [(fname, detail) for ok, fname, detail in results if not ok]
        icon = ACTION_ICONS.get(action, "\u2705")
        ar = {
            "on": "\u0634\u063a\u0651\u0644\u062a", "off": "\u0637\u0641\u0651\u064a\u062a",
            "set_temp": "\u0636\u0628\u0637\u062a"
        }.get(action, action)
        
        lines = [f"{icon} {ar} *{len(success)}* \u0623\u062c\u0647\u0632\u0629:"]
        for fname, detail in success:
            lines.append(f"  \u2705 {fname} {detail}".strip())
        if failed:
            for fname, detail in failed:
                lines.append(f"  \u274c {fname}")
        return "\n".join(lines)
    
    return "\u2753 \u0645\u0627 \u0639\u0631\u0641\u062a \u0634\u0646\u0648 \u062a\u0642\u0635\u062f"
