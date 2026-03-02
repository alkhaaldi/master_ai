"""SmartRouter v2.1 — classify messages into greeting/chat/action/unknown.
Learns from unknown patterns to reduce LLM costs.
"""
import re

# ── Action keywords (device commands) ──
ACTION_KEYWORDS = [
    # Arabic device control
    "شغل", "طفي", "ولع", "اطفي", "فتح", "سكر", "افتح", "اسكر",
    "حط", "خل", "زيد", "نقص", "ارفع", "وطي", "غير", "بدل",
    "شغله", "طفيه", "ولعه", "فتحه", "سكره",
    "درجة", "حرارة", "مكيف", "تكييف",
    "مشهد", "سين", "scene",
    # English
    "turn on", "turn off", "switch", "set", "open", "close",
    "lock", "unlock", "play", "stop", "pause", "volume",
]

# ── Chat keywords (questions, info, conversation) ──
CHAT_KEYWORDS = [
    # Questions
    "ليش", "ليه", "شنو", "شنهو", "اشرح", "معنى", "كيف", "شلون",
    "متى", "وين", "منو", "شقد", "هل", "ايش",
    "عطني", "فسر", "وضح", "عرف", "ترجم", "قارن",
    "اقترح", "نصيحة", "رأيك", "تنصح", "شرايك", "وش تقول",
    "طيب ليش",
    # English
    "what", "why", "how", "explain", "when", "where", "who",
    "tell me", "describe", "compare", "suggest", "recommend",
    # Stocks
    "محفظ", "اسهم", "سهم", "أسهم", "بورصة", "تداول",
    # Work
    "شفت", "دوام", "وردية", "اجازة", "اوفرتايم",
    # Expenses
    "مصروف", "مصاريف", "صرفت", "حساب",
    # Health
    "صحت", "صحة", "وزن", "ضغط", "نوم",
    # Home status
    "حالة البيت", "كم مكيف",
    # Conversational context (shift talk, preparation, etc)
    "اتجهز", "استعد", "رايح", "طالع",
    "أول", "ثاني", "ليل", "صباح", "عصر",
    "الساعة", "يبدأ", "ينتهي", "يخلص",
    "من", "الى", "بالليل", "بالصبح",
]

# ── Greeting patterns ──
GREETING_RE = re.compile(
    r"^\s*("
    r"هلا|السلام عليكم|صباح الخير|مساء الخير|"
    r"كيف حالك|شلونك|اهلا|مرحبا|"
    r"hi|hello|hey|good morning|good evening"
    r")\s*[!\?\.\u061f]*\s*$",
    re.IGNORECASE
)

GREETING_TEMPLATES = [
    "هلا بو خليفة! شلونك؟ 👋",
    "السلام عليكم! شنو تبي؟ 😊",
    "هلا وغلا! شلون الحال؟ 🌟",
    "أهلاً! شلونك اليوم؟",
    "مرحبا بو خليفة 👋 شلونك؟",
]


def classify(text: str) -> str:
    """Classify message: greeting, chat, action, or unknown."""
    t = text.strip().lower()

    # 1) Greeting check
    if GREETING_RE.match(t):
        return "greeting"

    # 2) Action keywords (device commands)
    for kw in ACTION_KEYWORDS:
        if kw in t:
            return "action"

    # 3) Chat keywords (questions, life domains, conversation)
    for kw in CHAT_KEYWORDS:
        if kw in t:
            return "chat"

    # 4) Short messages (< 5 words) are likely conversational
    words = t.split()
    if len(words) <= 4 and any(c > "\u0600" for c in t):
        return "chat"

    return "unknown"


# Backward-compatible alias
classify_message = classify
