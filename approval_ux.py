"""
approval_ux.py - Smart Approval UX for Master AI
Phase 3B: Clear, contextual approval messages with action/target/reason/scope
"""
import logging
from datetime import datetime

log = logging.getLogger("approval_ux")

# Arabic service names
_SERVICE_AR = {
    "turn_on": "شغل",
    "turn_off": "طفي",
    "toggle": "غير",
    "open_cover": "افتح",
    "close_cover": "سكر",
    "stop_cover": "وقف",
    "set_temperature": "غير حرارة",
    "lock": "سكر القفل",
    "unlock": "افتح القفل",
    "set_hvac_mode": "غير وضع المكيف",
}

_DOMAIN_AR = {
    "light": "نور",
    "climate": "مكيف",
    "cover": "ستارة",
    "fan": "شفاط/منقي",
    "lock": "قفل",
    "scene": "مشهد",
    "media_player": "سماعة",
    "switch": "سويتش",
}

_RISK_EMOJI = {"low": "✅", "medium": "⚠️", "high": "🛑"}


def format_approval_message(tool_name, args, score_info, reason="", entity_count=1):
    """Generate a smart Arabic approval message.
    
    Returns dict with: message, action_summary, reversible, risk_level
    """
    if tool_name == "ha_call_service":
        return _format_ha_approval(args, score_info, reason, entity_count)
    elif tool_name == "ssh_run":
        return _format_ssh_approval(args, score_info, reason)
    else:
        return _format_generic_approval(tool_name, args, score_info, reason)


def _format_ha_approval(args, score_info, reason, entity_count):
    domain = args.get("domain", "")
    service = args.get("service", "")
    sd = args.get("service_data", {})
    entity_id = sd.get("entity_id", "")
    
    # Action in Arabic
    action_ar = _SERVICE_AR.get(service, service)
    domain_ar = _DOMAIN_AR.get(domain, domain)
    
    # Entity name (extract readable part)
    entity_name = entity_id.split(".")[-1].replace("_", " ") if entity_id else ""
    
    # Scope
    if entity_count > 1:
        scope = f"{entity_count} {domain_ar}"
    else:
        scope = entity_name or domain_ar
    
    # Risk
    risk = score_info.get("level", "medium")
    emoji = _RISK_EMOJI.get(risk, "⚠️")
    
    # Reversible?
    reversible_services = {"turn_on", "turn_off", "toggle", "open_cover", "close_cover", "set_temperature"}
    is_reversible = service in reversible_services
    rev_text = "↩️ ينعكس" if is_reversible else "⚠️ ما ينعكس"
    
    # Temperature detail
    temp_detail = ""
    if service == "set_temperature" and "temperature" in sd:
        temp_detail = f" → {sd['temperature']}°"
    
    # Build message
    notes = ", ".join(score_info.get("notes", []))
    reason_line = f"\nلأن: {reason}" if reason else ""
    notes_line = f"\nملاحظات: {notes}" if notes else ""
    
    msg = f"""{emoji} {action_ar} {scope}{temp_detail}
{rev_text}{reason_line}{notes_line}

موافق؟"""
    
    return {
        "message": msg.strip(),
        "action_summary": f"{action_ar} {scope}{temp_detail}",
        "reversible": is_reversible,
        "risk_level": risk,
        "domain": domain,
        "service": service,
    }


def _format_ssh_approval(args, score_info, reason):
    cmd = args.get("command", args.get("cmd", ""))
    short_cmd = cmd[:60] + "..." if len(cmd) > 60 else cmd
    risk = score_info.get("level", "high")
    emoji = _RISK_EMOJI.get(risk, "🛑")
    
    msg = f"""{emoji} تنفيذ أمر:
{short_cmd}
⚠️ ما ينعكس

موافق؟"""
    
    return {
        "message": msg.strip(),
        "action_summary": f"SSH: {short_cmd}",
        "reversible": False,
        "risk_level": risk,
    }


def _format_generic_approval(tool_name, args, score_info, reason):
    risk = score_info.get("level", "medium")
    emoji = _RISK_EMOJI.get(risk, "⚠️")
    
    msg = f"""{emoji} {tool_name}
{reason or ''}

موافق؟"""
    
    return {
        "message": msg.strip(),
        "action_summary": tool_name,
        "reversible": False,
        "risk_level": risk,
    }


def format_approval_inline_buttons(approval_id):
    """Return TG inline keyboard buttons for approve/reject."""
    return [
        [
            {"text": "✅ نعم", "callback_data": f"approve:{approval_id}"},
            {"text": "❌ لا", "callback_data": f"reject:{approval_id}"},
        ]
    ]
