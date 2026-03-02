"""SmartRouter v2 — classify messages into chat/action/unknown.
Enhanced: life domain keywords, greeting detection, better coverage.
"""
import re

# ── Action keywords (device commands) ──
ACTION_KEYWORDS = [
    # Arabic
    "شغل", "طفي", "ولع", "اطفي", "فتح", "سكر", "افتح", "اسكر",
    "حط", "خل", "زيد", "نقص", "ارفع", "وطي", "غير", "بدل",
    "شغله", "طفيه", "ولعه", "فتحه", "سكره",
    "درجة", "حرارة", "مكيف", "تكييف",
    "مشهد", "سين", "scene",
    # English
    "turn on", "turn off", "switch", "set", "open", "close",
    "lock", "unlock", "play", "stop", "pause", "volume",
]

# ── Chat keywords (questions, info, greetings) ──
CHAT_KEYWORDS = [
    # Questions
    "ليش", "ليه", "شنو", "شنهو", "اشرح", "معنى", "كيف", "شلون",
    "متى", "وين", "منو", "شقد", "هل", "ايش",
    "عطني", "فسر", "وضح", "عرف", "ترجم", "قارن",
    "اقترح", "نصيحة", "رأيك", "تنصح", "شرايك", "وش تقول",
    "طيب ليش",
    # English
    "what", "why", "how", "explain", "when", "where", "who",
    "tell me", "describe", "compare", "recommend", "opinion",
    # Greetings
    "هلا", "السلام", "صباح", "مساء", "كيف حالك", "شخبارك",
    "hi", "hello", "good morning", "hey",
    # System
    "حالة النظام", "status", "version", "كم", "عدد",
    # Life domains (answered locally, no LLM needed for routing)
    "محفظ", "اسهم", "سهم", "أسهم", "بورصة", "تداول",
    "شفت", "دوام", "وردية", "اجازة", "اوفرتايم",
    "مصروف", "مصاريف", "صرفت", "حساب",
    "صحت", "صحة", "وزن", "ضغط", "نوم",
    "حالة البيت", "كم مكيف", "اضواء",
]

# ── Room keywords ──
ROOM_KEYWORDS = [
    "صالة", "معيشة", "مطبخ", "ديوانية", "غرفة", "حمام",
    "ماستر", "ملابس", "ممر", "استقبال", "ضيوف", "خادمة",
    "درج", "بلكونة", "مكتب", "سفرة", "خارج", "outdoor",
    "room", "kitchen", "living", "bedroom", "bathroom",
]

# ── Greeting patterns (ultra-fast, no LLM) ──
_GREETING_RE = re.compile(
    r'^(هلا|السلام عليكم|صباح الخير|مساء الخير|مساء النور|'
    r'كيف حالك|شخبارك|شلونك|hi|hello|hey|good morning|'
    r'مرحبا|اهلين|يا هلا|شحالك)$',
    re.IGNORECASE
)


def classify_message(text: str) -> str:
    """
    Classify a message into: 'greeting', 'chat', 'action', or 'unknown'.
    'greeting' = simple greeting → template response (no LLM)
    'chat' = info/question → direct LLM (lighter prompt)
    'action' = device command → iterative_engine
    'unknown' = ambiguous → iterative_engine (safe default)
    """
    t = text.strip().lower()

    # Ultra-short → unknown (followup handled elsewhere)
    if len(t) < 2:
        return "unknown"

    # Pure greetings → no LLM needed at all
    if _GREETING_RE.match(t.strip()):
        return "greeting"

    # Action keywords (high priority)
    for kw in ACTION_KEYWORDS:
        if kw in t:
            return "action"

    # Room + verb pattern
    has_room = any(r in t for r in ROOM_KEYWORDS)
    has_verb = any(v in t for v in ["نور", "ضوء", "لايت", "light"])
    if has_room and has_verb:
        return "action"

    # Chat/question keywords
    for kw in CHAT_KEYWORDS:
        if kw in t:
            return "chat"

    # Question mark → chat
    if "?" in t or "\u061f" in t:
        return "chat"

    # Fallback
    return "unknown"
