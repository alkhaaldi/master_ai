"""
expenses_engine.py — Expense Tracker for Master AI v8 Phase 4
Single-file: DB schema, parse, CRUD, summaries, TG formatting, quick handlers.
Tables in life.db: expense_entries
Currency: KWD (Kuwaiti Dinar)
"""
import os
import re
import sqlite3
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger("expenses")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")

# ═══════════════════════════════════════════════════
# CATEGORIES (hardcoded, simple)
# ═══════════════════════════════════════════════════

CATEGORIES = {
    "restaurant": {"ar": "مطعم", "emoji": "🍽", "keywords": ["مطعم", "غدا", "عشا", "فطور", "أكل", "طعام", "ماكدونالدز", "برغر", "بيتزا", "شاورما", "سوشي"]},
    "coffee": {"ar": "قهوة", "emoji": "☕", "keywords": ["قهوة", "كافيه", "ستاربكس", "كوستا", "شاي", "كابتشينو"]},
    "groceries": {"ar": "جمعية", "emoji": "🛒", "keywords": ["جمعية", "سوبرماركت", "خضار", "لحم", "سمك", "بقالة"]},
    "fuel": {"ar": "بنزين", "emoji": "⛽", "keywords": ["بنزين", "وقود", "محطة", "ديزل"]},
    "pharmacy": {"ar": "صيدلية", "emoji": "💊", "keywords": ["صيدلية", "دوا", "دواء", "علاج"]},
    "shopping": {"ar": "تسوق", "emoji": "🛍", "keywords": ["تسوق", "ملابس", "أغراض", "شراء", "مول"]},
    "kids": {"ar": "أطفال", "emoji": "👶", "keywords": ["أطفال", "حفاظات", "حليب", "العاب", "مدرسة"]},
    "bills": {"ar": "فواتير", "emoji": "📄", "keywords": ["فاتورة", "كهرباء", "ماء", "انترنت", "تلفون", "هاتف", "موبايل"]},
    "transport": {"ar": "مواصلات", "emoji": "🚗", "keywords": ["تاكسي", "كريم", "أوبر", "سيارة", "تصليح", "غسيل"]},
    "misc": {"ar": "متفرقات", "emoji": "📦", "keywords": []},
}

# ═══════════════════════════════════════════════════
# DB SCHEMA
# ═══════════════════════════════════════════════════

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS expense_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'KWD',
    category TEXT NOT NULL,
    note TEXT,
    spent_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'telegram',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_expense_spent_at ON expense_entries(spent_at);
CREATE INDEX IF NOT EXISTS idx_expense_category ON expense_entries(category);
"""


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_schema():
    with _conn() as c:
        c.executescript(_SCHEMA_SQL)
    logger.info("expenses schema initialized")


# ═══════════════════════════════════════════════════
# CATEGORY DETECTION
# ═══════════════════════════════════════════════════

def _normalize(text):
    t = text.strip().lower()
    t = t.replace("\u0629", "\u0647")  # taa marbuta
    t = t.replace("\u0623", "\u0627").replace("\u0625", "\u0627").replace("\u0622", "\u0627")
    return t


def guess_category(text):
    """Guess category from Arabic text."""
    t = _normalize(text)
    for key, info in CATEGORIES.items():
        for kw in info["keywords"]:
            if _normalize(kw) in t:
                return key
    return "misc"


# ═══════════════════════════════════════════════════
# PARSE EXPENSE FROM TEXT
# ═══════════════════════════════════════════════════

def parse_expense(text):
    """Parse 'سجل 12.5 مطعم' or '12.5 قهوة' or 'صرف 3.250 بنزين'.
    Returns (amount, category, note) or None."""
    t = text.strip()
    # Remove common prefixes
    for prefix in ["سجل", "صرف", "أضف", "حط", "expense", "add"]:
        if t.startswith(prefix):
            t = t[len(prefix):].strip()

    # Try to find amount (number with optional decimals)
    m = re.search(r'(\d+(?:\.\d+)?)', t)
    if not m:
        return None
    amount = float(m.group(1))
    if amount <= 0:
        return None

    # Rest is the description
    rest = t[:m.start()] + t[m.end():]
    rest = rest.strip()

    category = guess_category(rest) if rest else "misc"
    note = rest if rest else None

    return (amount, category, note)


# ═══════════════════════════════════════════════════
# CRUD
# ═══════════════════════════════════════════════════

def add_expense(amount, category="misc", note=None, spent_at=None, currency="KWD"):
    """Add expense entry."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not spent_at:
        spent_at = now
    with _conn() as c:
        c.execute("""INSERT INTO expense_entries
            (amount, currency, category, note, spent_at, source, created_at)
            VALUES (?, ?, ?, ?, ?, 'telegram', ?)""",
            (amount, currency, category, note, spent_at, now))
        eid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    cat_info = CATEGORIES.get(category, {"ar": category, "emoji": "📦"})
    return {"ok": True, "expense_id": eid, "amount": amount, "category": category,
            "category_ar": cat_info["ar"], "currency": currency}


def list_expenses(limit=10, days=None, category=None):
    """List recent expenses."""
    sql = "SELECT * FROM expense_entries WHERE 1=1"
    params = []
    if days:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        sql += " AND spent_at >= ?"
        params.append(cutoff)
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY spent_at DESC LIMIT ?"
    params.append(limit)
    with _conn() as c:
        rows = c.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def delete_expense(expense_id):
    """Delete expense by ID."""
    with _conn() as c:
        c.execute("DELETE FROM expense_entries WHERE id=?", (expense_id,))
        return c.total_changes > 0


def get_summary(period="today"):
    """Get expense summary for period: today/week/month."""
    today = date.today()
    if period == "today":
        start = today.isoformat()
    elif period == "week":
        start = (today - timedelta(days=today.weekday())).isoformat()
    elif period == "month":
        start = today.replace(day=1).isoformat()
    else:
        start = today.isoformat()

    with _conn() as c:
        # Total
        row = c.execute("SELECT COALESCE(SUM(amount),0) as total, COUNT(*) as cnt FROM expense_entries WHERE spent_at >= ?", (start,)).fetchone()
        total = row["total"]
        count = row["cnt"]
        # By category
        cats = c.execute("""SELECT category, SUM(amount) as cat_total, COUNT(*) as cat_cnt
            FROM expense_entries WHERE spent_at >= ?
            GROUP BY category ORDER BY cat_total DESC""", (start,)).fetchall()

    top_cats = []
    for cat in cats:
        info = CATEGORIES.get(cat["category"], {"ar": cat["category"], "emoji": "📦"})
        top_cats.append({
            "category": cat["category"],
            "category_ar": info["ar"],
            "emoji": info["emoji"],
            "total": cat["cat_total"],
            "count": cat["cat_cnt"],
        })

    period_names = {"today": "اليوم", "week": "هالأسبوع", "month": "هالشهر"}
    return {
        "period": period,
        "period_ar": period_names.get(period, period),
        "total": total,
        "count": count,
        "currency": "KWD",
        "top_categories": top_cats,
    }


# ═══════════════════════════════════════════════════
# TG FORMATTING
# ═══════════════════════════════════════════════════

def format_summary_tg(summary):
    """Format expense summary for Telegram."""
    if summary["count"] == 0:
        return f"💰 لا توجد مصاريف {summary['period_ar']}"
    lines = [f"💰 *مصاريف {summary['period_ar']}:*"]
    lines.append(f"  💵 الإجمالي: *{summary['total']:.3f}* د.ك ({summary['count']} عملية)")
    if summary["top_categories"]:
        lines.append("")
        for cat in summary["top_categories"][:5]:
            lines.append(f"  {cat['emoji']} {cat['category_ar']}: {cat['total']:.3f} د.ك")
    return "\n".join(lines)


def format_recent_tg(expenses):
    """Format recent expenses for Telegram."""
    if not expenses:
        return "💰 لا توجد مصاريف"
    lines = [f"💰 *آخر المصاريف:*\n"]
    for e in expenses:
        info = CATEGORIES.get(e["category"], {"ar": e["category"], "emoji": "📦"})
        dt = e["spent_at"][:10]
        note = f" — {e['note']}" if e.get("note") else ""
        lines.append(f"  {info['emoji']} {e['amount']:.3f} د.ك {info['ar']}{note} ({dt})")
    return "\n".join(lines)


def format_add_confirmation(result):
    """Format add confirmation for Telegram."""
    if not result.get("ok"):
        return f"❌ {result.get('error', 'خطأ')}"
    info = CATEGORIES.get(result["category"], {"ar": result["category"], "emoji": "📦"})
    return f"✅ تم تسجيل {result['amount']:.3f} د.ك — {info['emoji']} {info['ar']}"


# ═══════════════════════════════════════════════════
# MORNING REPORT
# ═══════════════════════════════════════════════════

def get_morning_expense_text():
    """Short expense line for morning report."""
    yesterday = get_summary("today")  # Actually yesterday would be better
    # Get yesterday's total
    yday = (date.today() - timedelta(days=1)).isoformat()
    with _conn() as c:
        row = c.execute("SELECT COALESCE(SUM(amount),0) as total FROM expense_entries WHERE spent_at >= ? AND spent_at < ?",
                       (yday, date.today().isoformat())).fetchone()
    yday_total = row["total"]
    if yday_total > 0:
        return f"💰 صرف أمس: {yday_total:.3f} د.ك"
    return ""


# ═══════════════════════════════════════════════════
# QUICK QUERY HANDLERS
# ═══════════════════════════════════════════════════

def handle_spent_today():
    return format_summary_tg(get_summary("today"))

def handle_spent_week():
    return format_summary_tg(get_summary("week"))

def handle_spent_month():
    return format_summary_tg(get_summary("month"))

def handle_recent_expenses():
    return format_recent_tg(list_expenses(10))
