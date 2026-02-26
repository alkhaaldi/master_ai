"""
Master AI Brain Personality v1.0
Quick response templates + response personality prompt
"""
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger("brain.personality")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POLICY_FILE = os.path.join(BASE_DIR, "policy.json")

# Load policy
def _load_policy():
    try:
        with open(POLICY_FILE) as f:
            return json.load(f)
    except Exception:
        return {"quick_response": {"enabled": False}, "personality": {"dialect": "kuwaiti", "verbosity": "minimal", "emoji": True}}

_policy = _load_policy()

def reload_policy():
    global _policy
    _policy = _load_policy()
    logger.info("Policy reloaded")

# ═══════════════════════════════════════
# Quick Response Templates
# ═══════════════════════════════════════

TEMPLATES_AR = {
    "turn_on":  "\u0634\u063a\u0644\u062a {devices} \u2713",
    "turn_off": "\u0637\u0641\u064a\u062a {devices} \u2713",
    "toggle":   "\u063a\u064a\u0631\u062a {devices} \u2713",
    "set_temperature": "\u062d\u0637\u064a\u062a {device} \u0639\u0644\u0649 {value}\u00b0",
    "cover_open":  "\u0641\u062a\u062d\u062a {devices}",
    "cover_close": "\u0633\u0643\u0631\u062a {devices}",
    "scene_activate": "\u0634\u063a\u0644\u062a \u0633\u064a\u0646 {scene} \u2713",
    "lock":   "\u0642\u0641\u0644\u062a {devices} \u2713",
    "unlock": "\u0641\u062a\u062d\u062a \u0642\u0641\u0644 {devices} \u2713",
}

def _extract_device_names(actions, results):
    """Extract friendly device names from action results."""
    names = []
    for a in actions:
        params = a.get("params", {})
        eid = params.get("entity_id", "")
        # Try to get friendly name from result
        name = eid.split(".")[-1].replace("_", " ") if eid else ""
        if name:
            names.append(name)
    return ", ".join(names) if names else "\u0627\u0644\u062c\u0647\u0627\u0632"

def _classify_action(action):
    """Classify action type from plugin + params. Returns template key or None."""
    plugin = action.get("plugin", "")
    params = action.get("params", {})
    
    if plugin != "ha_call_service":
        return None
    
    service = params.get("service", "")
    domain = params.get("domain", "")
    
    if not service:
        return None
    
    # Map service to template
    if service in ("turn_on",):
        return "turn_on"
    elif service in ("turn_off",):
        return "turn_off"
    elif service in ("toggle",):
        return "toggle"
    elif service == "set_temperature" or (domain == "climate" and "temperature" in str(params)):
        return "set_temperature"
    elif service in ("open_cover",):
        return "cover_open"
    elif service in ("close_cover",):
        return "cover_close"
    elif service in ("turn_on",) and domain == "scene":
        return "scene_activate"
    elif service in ("lock",):
        return "lock"
    elif service in ("unlock",):
        return "unlock"
    
    return None

def get_quick_response(actions, results):
    """
    Check if we can respond with a template (no LLM needed).
    Returns response string or None (None = needs LLM).
    """
    if not _policy.get("quick_response", {}).get("enabled", False):
        return None
    
    max_actions = _policy.get("quick_response", {}).get("max_actions_for_template", 2)
    
    if not actions or len(actions) > max_actions:
        return None
    
    # Check all actions succeeded
    if results:
        for r in results:
            if isinstance(r, dict) and r.get("error"):
                return None
    
    # Classify all actions
    action_types = []
    for a in actions:
        atype = _classify_action(a)
        if atype is None:
            return None  # Unknown action = needs LLM
        action_types.append(atype)
    
    # All same type?
    if len(set(action_types)) == 1:
        atype = action_types[0]
        template = TEMPLATES_AR.get(atype)
        if template:
            devices = _extract_device_names(actions, results)
            
            # Special handling for temperature
            if atype == "set_temperature":
                temp = actions[0].get("params", {}).get("temperature", "")
                return template.format(device=devices, value=temp)
            elif atype == "scene_activate":
                scene = actions[0].get("params", {}).get("entity_id", "").split(".")[-1].replace("_", " ")
                return template.format(scene=scene)
            else:
                return template.format(devices=devices)
    
    return None  # Mixed actions = needs LLM


# ═══════════════════════════════════════
# Response Personality Prompt
# ═══════════════════════════════════════

def build_response_prompt():
    """
    System prompt for the response/summary phase.
    Used instead of generic 'summarize results' prompt.
    """
    hour = datetime.now().hour
    
    if 5 <= hour < 12:
        greeting_hint = "\u0625\u0630\u0627 \u0623\u0648\u0644 \u0631\u062f: \u0635\u0628\u0627\u062d \u0627\u0644\u062e\u064a\u0631"
    elif 12 <= hour < 17:
        greeting_hint = ""
    elif 17 <= hour < 21:
        greeting_hint = "\u0625\u0630\u0627 \u0623\u0648\u0644 \u0631\u062f: \u0645\u0633\u0627\u0621 \u0627\u0644\u062e\u064a\u0631"
    else:
        greeting_hint = "\u0648\u0642\u062a \u0645\u062a\u0623\u062e\u0631 \u2014 \u062e\u0641\u0641 \u0627\u0644\u0643\u0644\u0627\u0645"
    
    prompt = """\u0623\u0646\u062a \u0645\u0627\u0633\u062a\u0631 \u2014 \u0645\u0633\u0627\u0639\u062f \u0628\u064a\u062a \u0630\u0643\u064a \u0643\u0648\u064a\u062a\u064a.

\u0642\u0648\u0627\u0639\u062f \u0627\u0644\u0631\u062f:
- \u0643\u0648\u064a\u062a\u064a \u0639\u0627\u0645\u064a \u0645\u062e\u062a\u0635\u0631
- \u0644\u0627 \u062a\u0643\u0631\u0631 \u0627\u0644\u0644\u064a \u0627\u0644\u0645\u0633\u062a\u062e\u062f\u0645 \u064a\u0639\u0631\u0641\u0647
- \u0628\u062f\u0627\u0644 "\u062a\u0645 \u0628\u0646\u062c\u0627\u062d" \u0642\u0648\u0644 "\u062a\u0645 \u2713" \u0623\u0648 "\u0623\u0648\u0643\u064a"
- \u0644\u0648 \u0633\u0623\u0644\u0643 \u0639\u0646 \u0628\u064a\u0627\u0646\u0627\u062a\u060c \u0631\u062a\u0628\u0647\u0627 \u0628\u0634\u0643\u0644 \u0645\u0642\u0631\u0648\u0621
- \u0644\u0648 \u0641\u064a\u0647 \u0645\u0634\u0643\u0644\u0629\u060c \u0642\u0648\u0644\u0647\u0627 \u0645\u0628\u0627\u0634\u0631\u0629
- emoji \u0645\u0642\u0628\u0648\u0644 \u0628\u0633 \u0644\u0627 \u062a\u0643\u062b\u0631"""
    
    if greeting_hint:
        prompt += f"\n- {greeting_hint}"
    
    return prompt

def get_policy():
    """Return current policy for external use."""
    return _policy.copy()
