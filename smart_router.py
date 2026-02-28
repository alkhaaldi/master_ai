# smart_router.py — Classify TG messages: chat vs action vs followup
# Minimal, rule-based, no LLM needed
import re

# Question/info keywords (Kuwaiti + MSA + English)
CHAT_KEYWORDS = [
    # Arabic question words
    "ليش", "ليه", "شنو", "شنهو", "اشرح", "معنى", "كيف", "شلون",
    "متى", "وين", "منو", "شقد", "كم", "هل", "ايش", "عطني",
    "فسر", "وضح", "عرف", "ترجم", "قارن", "اقترح", "نصيحة",
    "رأيك", "تنصح", "شرايك", "وش تقول", "طيب ليش",
    # English
    "what", "why", "how", "explain", "when", "where", "who",
    "tell me", "describe", "compare", "recommend", "opinion",
    # Greetings & small talk
    "هلا", "السلام", "صباح", "مساء", "كيف حالك", "شخبارك",
    "hi", "hello", "good morning", "hey",
    # System info questions
    "حالة النظام", "status", "version", "كم", "عدد",
]

# Action/command keywords (device control)
ACTION_KEYWORDS = [
    # Arabic commands
    "شغل", "طفي", "ولع", "اطفي", "فتح", "سكر", "افتح", "اسكر",
    "حط", "خل", "زيد", "نقص", "ارفع", "وطي", "غير", "بدل",
    "شغله", "طفيه", "ولعه", "فتحه", "سكره",
    # Temperature
    "درجة", "حرارة", "مكيف", "تكييف",
    # Scenes
    "مشهد", "سين", "scene",
    # English
    "turn on", "turn off", "switch", "set", "open", "close",
    "lock", "unlock", "play", "stop", "pause", "volume",
]

# Room names that hint at device control
ROOM_KEYWORDS = [
    "صالة", "معيشة", "مطبخ", "ديوانية", "غرفة", "حمام", "ماستر",
    "ملابس", "ممر", "استقبال", "أرضي", "أول", "درج", "مغسلة",
    "office", "room", "kitchen", "living", "bedroom",
]

def classify_message(text: str) -> str:
    """
    Classify a message into: 'chat', 'action', or 'unknown'.
    'chat' = info/question/greeting → direct LLM, skip iterative_engine
    'action' = device command → iterative_engine
    'unknown' = ambiguous → iterative_engine (safe default)
    """
    t = text.strip().lower()

    # Very short follow-up patterns handled elsewhere
    if len(t) < 4:
        return "unknown"

    # Check for action keywords first (higher priority)
    for kw in ACTION_KEYWORDS:
        if kw in t:
            return "action"

    # Check for room + verb patterns (e.g. "نور المعيشة")
    has_room = any(r in t for r in ROOM_KEYWORDS)
    has_action_verb = any(v in t for v in ["نور", "ضوء", "لايت", "light", "أضاء"])
    if has_room and has_action_verb:
        return "action"

    # Check for chat/question keywords
    for kw in CHAT_KEYWORDS:
        if kw in t:
            return "chat"

    # Question mark = likely chat
    if "?" in t or "؟" in t:
        return "chat"

    # Default: unknown → use iterative_engine
    return "unknown"
