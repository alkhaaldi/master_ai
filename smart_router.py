"""SmartRouter v2.2 — classify messages into greeting/chat/action/unknown.
Persistent learning from unknown patterns. Zero LLM cost for greetings.
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
    # Work/shift
    "شفت", "شفتي", "دوام", "وردية", "اجازة", "إجازة",
    "اوفرتايم", "اتجهز", "استعد",
    "أول", "ثاني", "ليل",
    "من كم", "الى كم", "الى",
    # Stocks  
    "محفظ", "اسهم", "سهم", "أسهم", "بورصة", "تداول",
    "محفظتي", "وش اسهم",
    # Expenses
    "مصروف", "مصاريف", "صرفت", "حساب",
    # Health
    "صحت", "صحة", "وزن", "ضغط", "نوم",
    # Home status
    "حالة البيت", "كم مكيف", "اضواء", "وضع البيت",
    # Conversational
    "تمام", "اوكي", "اوكيه", "خلاص", "شكرا", "مشكور",
    "اي", "ايي", "لا", "اكيد", "تقرير",
    "وضع", "حالة", "معلومات",
    # English
    "what", "why", "how", "explain", "when", "where", "who",
    "tell me", "help", "info", "about", "thanks", "ok", "yes", "no",
    "status", "report", "suggest", "recommend",
]

# ── Greeting patterns ──
GREETING_RE = re.compile(
    r"^\s*("
    r"هلا|اهلين|السلام عليكم|سلام|مرحبا?"
    r"|صباح الخير|مساء الخير|مسا الخير"
    r"|hi|hello|hey|yo|good morning|good evening"
    r")\b",
    re.IGNORECASE,
)


def classify(text: str) -> str:
    t = text.strip().lower()
    if not t or t.startswith("/"):
        return "unknown"

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

    # 4) Short Arabic messages (< 6 words) are likely conversational
    words = t.split()
    if len(words) <= 5 and any(c > "\u0600" for c in t):
        return "chat"

    # 5) Short English messages
    if len(words) <= 4:
        return "chat"

    return "unknown"


# Backward-compatible alias
classify_message = classify
