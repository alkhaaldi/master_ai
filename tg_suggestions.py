"""Phase A4: Smart Suggestions — contextual inline buttons after actions.

After every action, suggest relevant next steps as inline buttons.
"""
import logging

logger = logging.getLogger("tg_suggest")


def get_suggestions(action: str, context: dict = None) -> list:
    """Return inline button suggestions based on last action.
    
    Args:
        action: what just happened (on/off/set_temp/find/rooms/devices/scene/query)
        context: optional dict with room, domain, entities, etc.
    
    Returns:
        List of button rows [[{text, callback_data},...]]
    """
    context = context or {}
    room = context.get("room", "")
    domain = context.get("domain", "")
    entity_id = context.get("entity_id", "")
    
    suggestions = []
    
    if action in ("on", "off"):
        # After turning something on/off, suggest opposite + room devices
        opposite = "off" if action == "on" else "on"
        opp_text = "طفيه" if action == "on" else "شغله"
        opp_icon = "⚫" if action == "on" else "🟢"
        suggestions.append([
            {"text": f"{opp_icon} {opp_text}", "callback_data": f"suggest:followup:{opposite}"},
        ])
        if room:
            suggestions.append([
                {"text": f"📋 أجهزة {room[:15]}", "callback_data": f"suggest:devices:{room[:30]}"},
            ])
    
    elif action == "set_temp":
        # After setting temp, suggest common temps
        suggestions.append([
            {"text": "❄️ 20°", "callback_data": "suggest:temp:20"},
            {"text": "❄️ 22°", "callback_data": "suggest:temp:22"},
            {"text": "❄️ 24°", "callback_data": "suggest:temp:24"},
        ])
    
    elif action == "find":
        # After search, suggest common follow-ups
        suggestions.append([
            {"text": "🟢 شغل الكل", "callback_data": "suggest:followup:on"},
            {"text": "⚫ طفي الكل", "callback_data": "suggest:followup:off"},
        ])
    
    elif action == "rooms":
        # After showing rooms, suggest popular rooms
        suggestions.append([
            {"text": "🏠 المعيشة", "callback_data": "suggest:devices:المعيشة"},
            {"text": "🏠 الديوانية", "callback_data": "suggest:devices:الديوانية"},
        ])
        suggestions.append([
            {"text": "🏠 ماستر", "callback_data": "suggest:devices:ماستر"},
            {"text": "🔍 بحث", "callback_data": "suggest:prompt:بحث"},
        ])
    
    elif action == "devices":
        # After showing room devices, suggest scene + control
        suggestions.append([
            {"text": "🎬 المشاهد", "callback_data": "suggest:scenes"},
            {"text": "🔍 بحث جهاز", "callback_data": "suggest:prompt:بحث"},
        ])
    
    elif action == "scene":
        # After activating scene, suggest other popular scenes
        suggestions.append([
            {"text": "🌙 مشهد نوم", "callback_data": "suggest:scene:نوم"},
            {"text": "☀️ مشهد صباح", "callback_data": "suggest:scene:صباح"},
            {"text": "🚪 مشهد مغادرة", "callback_data": "suggest:scene:مغادرة"},
        ])
    
    elif action == "query":
        # After status check, suggest actions
        if domain == "climate":
            suggestions.append([
                {"text": "❄️ اضبط 22°", "callback_data": "suggest:temp:22"},
                {"text": "❄️ اضبط 24°", "callback_data": "suggest:temp:24"},
            ])
        else:
            suggestions.append([
                {"text": "🟢 شغل", "callback_data": "suggest:followup:on"},
                {"text": "⚫ طفي", "callback_data": "suggest:followup:off"},
            ])
    
    return suggestions
