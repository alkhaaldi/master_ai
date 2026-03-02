"""
life_expenses.py - Smart Expense Tracker for Master AI
Track expenses in Kuwaiti Dinar with Arabic NLP
"""
import sqlite3
import json
import re
import logging
from datetime import datetime, date, timedelta
from typing import Optional

logger = logging.getLogger("life_expenses")

DB_PATH = "/home/pi/master_ai/data/audit.db"

CATEGORIES = {
    "أكل": ["غدا", "عشا", "فطور", "مطعم", "كافيه", "قهوة", "شاي", "جمعية", "سوبرماركت", "خضار", "لحم"],
    "بنزين": ["بنزين", "وقود", "محطة"],
    "فواتير": ["كهرباء", "ماء", "انترنت", "تلفون", "هاتف", "موبايل"],
    "سيارة": ["سيارة", "تصليح", "غسيل", "كفر", "زيت"],
    "صحة": ["دكتور", "مطعم", "صيدلية", "دواء", "عيادة"],
    "أخرى": [],
}


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _detect_category(description: str) -> str:
    desc_lower = description.lower()
    for cat, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw in desc_lower:
                return cat
    return "أخرى"


def add_expense(amount, description="", category=None):
    if not category:
        category = _detect_category(description)
    db = _db()
    db.execute("INSERT INTO life_data (domain, category, data, amount, ref_date) VALUES ('expenses', ?, ?, ?, ?)",
        (category, json.dumps({"description": description, "category": category}, ensure_ascii=False), amount, date.today().isoformat()))
    db.commit()
    return f"✅ {amount:.1f} د.ك — {category}" + (f"\n{description}" if description else "")


def get_expenses(period="today"):
    db = _db()
    now = date.today()
    if period == "today": start = now.isoformat(); label = "اليوم"
    elif period == "week": start = (now - timedelta(days=now.weekday())).isoformat(); label = "هالأسبوع"
    elif period == "month": start = now.replace(day=1).isoformat(); label = "هالشهر"
    else: start = now.isoformat(); label = period
    rows = db.execute("SELECT category, SUM(amount) as total, COUNT(*) as cnt FROM life_data WHERE domain='expenses' AND ref_date >= ? GROUP BY category ORDER BY total DESC", (start,)).fetchall()
    if not rows: return f"ما فيه مصاريف {label}"
    grand = sum(r["total"] for r in rows)
    msg = f"💳 مصاريف {label}: {grand:.1f} د.ك\n\n"
    for r in rows: msg += f"• {r['category']}: {r['total']:.1f} د.ك ({r['cnt']})\n"
    return msg


def get_category_expenses(category, period="month"):
    db = _db()
    start = date.today().replace(day=1).isoformat()
    rows = db.execute("SELECT amount, data, ref_date FROM life_data WHERE domain='expenses' AND category=? AND ref_date >= ? ORDER BY ref_date DESC", (category, start)).fetchall()
    if not rows: return f"مافي مصاريف {category}"
    total = sum(r["amount"] for r in rows)
    msg = f"💳 {category}: {total:.1f} د.ك\n"
    for r in rows:
        d = json.loads(r["data"]).get("description","")
        msg += f"• {r['ref_date']}: {r['amount']:.1f}" + (f" {d}" if d else "") + "\n"
    return msg


def parse_expense_command(text):
    text = text.strip()
    m = re.search(r'(?:صرفت|دفعت)\s+([\d.]+)\s*(?:دينار|د\.ك)$)?\s*(.*)', text)
    if m: return {"action": "add", "amount": float(m.group(1)), "description": m.group(2).strip()}
    if "مصاريف اليوم" in text: return {"action": "query", "period": "today"}
    if "مصاريف الشهر" in text or "هالشهر" in text: return {"action": "query", "period": "month"}
    if "مصاريف" in text: return {"action": "query", "period": "today"}
    return {"action": "unknown"}


def handle_expense_command(text):
    cmd = parse_expense_command(text)
    a = cmd.get("action")
    if a == "add": return add_expense(cmd["amount"], cmd.get("description",""))
    if a == "query": return get_expenses(cmd.get("period","today"))
    if a == "category_query": return get_category_expenses(cmd["category"])
    return ""
