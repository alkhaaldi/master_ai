"""Quick Query — fast HA status without LLM calls.
Handles: "وضع البيت", "كم مكيف شغال", "اضواء شغالة", etc.
"""
import httpx
import logging
import os
import re

logger = logging.getLogger("quick_query")

HA_URL = os.environ.get("HA_URL", "http://localhost:8123")
HA_TOKEN = os.environ.get("HA_TOKEN", "")

# Pattern -> handler mapping
PATTERNS = [
    (r"\u0648\u0636\u0639 \u0627\u0644\u0628\u064a\u062a|\u062d\u0627\u0644\u0629 \u0627\u0644\u0628\u064a\u062a|\u0634\u0646\u0648 \u0648\u0636\u0639|\u0634\u0644\u0648\u0646 \u0627\u0644\u0628\u064a\u062a", "home_status"),
    (r"\u0643\u0645 \u0645\u0643\u064a\u0641|\u0645\u0643\u064a\u0641\u0627\u062a \u0634\u063a\u0627\u0644|ac \u0634\u063a\u0627\u0644", "ac_count"),
    (r"\u0643\u0645 \u0636\u0648\u0621|\u0627\u0636\u0648\u0627\u0621 \u0634\u063a\u0627\u0644|\u0646\u0648\u0631 \u0634\u063a\u0627\u0644", "lights_count"),
]


async def _ha_states():
    """Fetch all HA states."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{HA_URL}/api/states",
                headers={"Authorization": f"Bearer {HA_TOKEN}"}
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.error(f"HA states error: {e}")
    return []


async def quick_answer(text: str) -> str | None:
    """Try to answer quickly without LLM. Returns None if no match."""
    t = text.strip().lower()
    
    for pattern, handler in PATTERNS:
        if re.search(pattern, t):
            return await globals()[f"_handle_{handler}"]()
    return None


async def _handle_home_status():
    """Quick home status summary."""
    states = await _ha_states()
    if not states:
        return None
    
    lights_on = sum(1 for s in states if s["entity_id"].startswith("light.") and s["state"] == "on")
    lights_total = sum(1 for s in states if s["entity_id"].startswith("light."))
    ac_on = sum(1 for s in states if s["entity_id"].startswith("climate.") and s["state"] != "off")
    ac_total = sum(1 for s in states if s["entity_id"].startswith("climate."))
    covers_open = sum(1 for s in states if s["entity_id"].startswith("cover.") and s["state"] == "open")
    covers_total = sum(1 for s in states if s["entity_id"].startswith("cover."))
    
    # AC temps
    ac_temps = []
    for s in states:
        if s["entity_id"].startswith("climate.") and s["state"] != "off":
            temp = s.get("attributes", {}).get("temperature")
            name = s.get("attributes", {}).get("friendly_name", s["entity_id"])
            if temp:
                ac_temps.append(f"  {name}: {temp}\u00b0")
    
    lines = [
        "\U0001f3e0 \u0648\u0636\u0639 \u0627\u0644\u0628\u064a\u062a:",
        f"\U0001f4a1 \u0623\u0636\u0648\u0627\u0621: {lights_on}/{lights_total} \u0634\u063a\u0627\u0644",
        f"\u2744\ufe0f \u0645\u0643\u064a\u0641\u0627\u062a: {ac_on}/{ac_total} \u0634\u063a\u0627\u0644",
    ]
    if ac_temps:
        lines.extend(ac_temps)
    lines.append(f"\U0001f3ea \u0633\u062a\u0627\u0626\u0631: {covers_open}/{covers_total} \u0645\u0641\u062a\u0648\u062d")
    
    return chr(10).join(lines)


async def _handle_ac_count():
    states = await _ha_states()
    if not states:
        return None
    ac_on = [s for s in states if s["entity_id"].startswith("climate.") and s["state"] != "off"]
    if not ac_on:
        return "\u2744\ufe0f \u0643\u0644 \u0627\u0644\u0645\u0643\u064a\u0641\u0627\u062a \u0645\u0637\u0641\u064a\u0629"
    lines = [f"\u2744\ufe0f {len(ac_on)} \u0645\u0643\u064a\u0641 \u0634\u063a\u0627\u0644:"]
    for s in ac_on:
        name = s.get("attributes", {}).get("friendly_name", "")
        temp = s.get("attributes", {}).get("temperature", "?")
        lines.append(f"  {name}: {temp}\u00b0")
    return chr(10).join(lines)


async def _handle_lights_count():
    states = await _ha_states()
    if not states:
        return None
    on = [s for s in states if s["entity_id"].startswith("light.") and s["state"] == "on"]
    return f"\U0001f4a1 {len(on)} \u0636\u0648\u0621 \u0634\u063a\u0627\u0644"
