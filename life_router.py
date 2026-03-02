"""
life_router.py - Smart Life Domain Router v2
Detects which life domain a message belongs to and routes accordingly.

Changes v2:
- Raised threshold from 1 to 2 (reduce false positives)
- Added logging for routing decisions
- Added SMART_HOME_OVERRIDE to avoid conflicts
"""
import re
import logging

logger = logging.getLogger("life_router")

STOCK_WORDS = [
    # === Added: common Arabic stock queries ===
    "اسهمي", "أسهمي", "محفظتي", "المحفظة", "سهمي", "أسهم", "كلينينج", "سنرجي", "انوفست", "سعر", "شراء",
    "شريت", "اشتريت", "بعت", "سهم", "أسهم", "اسهم", "محفظة", "بورصة",
    "ستوب", "target", "stop loss",
    "CLEANING", "SENERGY", "INOVEST", "ZAIN", "KFH", "NBK",
    "كلينج", "سنرجي", "زين", "بيتك", "الوطني",
    "تداول", "watchlist", "صفقات", "راقب السهم",
    "شارت", "chart", "pine", "استراتيجية",
]

EXPENSE_WORDS = [
    "صرفت", "دفعت", "مصاريف", "مصروف", "حسابي",
    "دينار", "د.ك", "kd", "فلوس", "ميزانية", "مصاريفي", "المصاريف", "كم صرفت",
    "فاتورة", "اشتراك",
]

WORK_WORDS = [
    "اوفرتايم", "overtime", "اجازة", "اجازتي", "صباحي", "عصري", "ليلي", "جدولي",
    "شفتي", "شفت", "دوام", "دوامي", "جدول",
    "OT", "أوفرتايم", "اوتي", "overtime",
    "إجازة", "اجازة", "leave", "مرضية", "sick",
    "Unit 114", "الشفت", "شفتات",
    "هيدروكراكر", "hydrocracker",
]

HEALTH_WORDS = [
    "وزني", "الوزن", "وزن",
    "مشيت", "جريت", "جيم", "gym", "تمرين", "رياضة",
    "نمت", "نوم", "نايم",
    "صحتي", "صحة", "دكتور", "موعد طبي",
    "كالوري", "سعرات",
]

# Words that SHOULD NOT trigger life_router (smart home priority)
SMART_HOME_OVERRIDE = {
    "نور", "مكيف", "ستارة", "شفاط", "منقي", "سماعة",
    "سبوت", "ستريب", "مشهد", "scene", "entity",
    "طفي", "شغل", "افتح", "سكر", "حرارة",
}


def detect_life_domain(text: str) -> str:
    # Exclude HA device commands to prevent false routing
    HA_WORDS = ["شغل", "طفي", "اضاءة", "نور", "مكيف", "ستارة", "حرارة", "كهربا", "مكيفات", "شفاط", "turn on", "turn off", "light", "ac", "cover"]
    if any(w in text for w in HA_WORDS):
        return None
    """Detect which life domain a message belongs to.

    Returns domain name or None if not a life domain message.
    """
    text_lower = text.lower().strip()
    words_set = set(re.split(r"\s+", text_lower))

    # If message contains smart home keywords, skip life routing
    if words_set & SMART_HOME_OVERRIDE:
        return None

    # Phrase shortcuts
    WORK_PHRASES = ["اول ليل", "ثاني ليل", "اول صباح", "ثاني صباح", "اول عصر", "ثاني عصر", "اول و لا ثاني", "أول ولا ثاني"]
    if any(p in text for p in WORK_PHRASES):
        return "work"

    def _score(keywords):
        score = 0
        for kw in keywords:
            kw_l = kw.lower()
            if " " in kw_l:
                if kw_l in text_lower:
                    score += 2
            elif kw_l.isupper() or kw_l.isascii():
                if kw_l in text_lower:
                    score += 1
            else:
                if kw_l in words_set:
                    score += 1
        return score

    scores = {
        "stocks": _score(STOCK_WORDS),
        "expenses": _score(EXPENSE_WORDS),
        "work": _score(WORK_WORDS),
        "health": _score(HEALTH_WORDS),
    }
    best = max(scores, key=scores.get)

    # Domain-specific thresholds (stocks=1, others=2)
    _thresholds = {"stocks": 1, "expenses": 1, "work": 1, "health": 1}
    if scores[best] >= _thresholds.get(best, 2):
        logger.info(f"ROUTE life: '{text_lower[:40]}' -> {best} (score={scores[best]})")
        return best

    # Score 1: only for high-confidence tickers
    if scores[best] == 1:
        tickers = {"cleaning", "senergy", "inovest", "zain", "kfh", "nbk"}
        for t in tickers:
            if t in text_lower:
                logger.info(f"ROUTE life: '{text_lower[:40]}' -> stocks (ticker: {t})")
                return "stocks"

    logger.info(f"ROUTE life: '{text_lower[:40]}' -> None (scores: {scores})")
    return None
