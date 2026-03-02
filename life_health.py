"""
life_health.py - Health & Fitness Tracker
Zeight, exercise, sleep, medical appointments
"""
import sqlite3
import json
import re
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger("life_health")

DB_PATH = "/home/pi/master_ai/data/audit.db"


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def log_weight(weight: float) -> str:
    db = _db()
    db.execute(
        "INSERT INTO life_data (domain, category, data, amount, ref_date) VALUES (?,?,?,?,?)",
        ("health", "weight", json.dumps({"kg": weight}), weight, date.today().isoformat())
    )
    db.commit()
    prev = db.execute(
        """SELECT amount FROM life_data WHERE domain='health' AND category='weight'
           AND ref_date < ? ORDER BY ref_date DESC LIMIT 1""",
        (date.today().isoformat(),)
    ).fetchone()
    msg = f"⚔️ الوزن: {weight} كج"
    if prev:
        diff = weight - prev["amount"]
        arrow = "⬆️" if diff < 0 else "⬇️" if diff > 0 else "↔️"
        msg += f"\n{arrow} التغيير: {diff:+.1f} كج"
    return msg


def log_exercise(exercise_type: str, value: float = 0, unit: str = "km") -> str:
    db = _db()
    data = {"type": exercise_type, "value": value, "unit": unit}
    db.execute(
        "INSERT INTO life_data (domain, category, data, amount, ref_date) VALUES (?,?,?,?,?)",
        ("health", "exercise", json.dumps(data, ensure_ascii=False), value,
         date.today().isoformat())
    )
    db.commit()
    type_map = {"walk": "مشي", "run": "جري", "gym": "جيم", "swim": "سباحة"}
    t = type_map.get(exercise_type, exercise_type)
    return f"🏋️ {t}" + (f": {value} {unit}" if value else "") + " ✅"


def log_sleep(hours: float) -> str:
    db = _db()
    db.execute(
        "INSERT INTO life_data (domain, category, data, amount, ref_date) VALUES (?,?,?,?,?)",
        ("health", "sleep", json.dumps({"hours": hours}), hours, date.today().isoformat())
    )
    db.commit()
    quality = "😴 ممتاز" if hours >= 7 else "😐 كافي" if hours >= 5 else "😫 قليل"
    return f"🛏 نوم: {hours} ساعة — {quality}"


def health_summary(days: int = 7) -> str:
    db = _db()
    start = (date.today() - timedelta(days=days)).isoformat()
    weights = db.execute(
        """SELECT amount, ref_date FROM life_data
           WHERE domain='health' AND category='weight' AND ref_date >= ?
           ORDER BY ref_date""",
        (start,)
    ).fetchall()
    exercises = db.execute(
        """SELECT COUNT(*) as cnt, SUM(amount) as total FROM life_data
           WHERE domain='health' AND category='exercise' AND ref_date >= ?""",
        (start,)
    ).fetchone()
    sleep = db.execute(
        """SELECT AVG(amount) as avg, COUNT(*) as cnt FROM life_data
           WHERE domain='health' AND category='sleep' AND ref_date >= ?""",
        (start,)
    ).fetchone()
    msg = f"🏥 صحتك آخر {days} أيام\n\n"
    if weights:
        latest = weights[-1]["amount"]
        first = weights[0]["amount"]
        diff = latest - first
        arrow = "⬆️" if diff < 0 else "⬇️" if diff > 0 else "↔️"
        msg += f"⚔️ الوزن: {latest} كج ({arrow} {diff:+.1f})\n"
    else:
        msg += "⚔️ الوزن: لم يسجل\n"
    ex_cnt = exercises["cnt"] or 0
    ex_total = exercises["total"] or 0
    msg += f"🏋️ رياضة: {ex_cnt} مرة ({ex_total:.1f} كم)\n"
    if sleep["cnt"]:
        msg += f"🛏 نوم: متوسط {sleep['avg']:.1f} ساعة ({sleep['cnt']} يوم)\n"
    else:
        msg += "🛏 نوم: لم يسجل\n"
    return msg


def parse_health_command(text: str) -> dict:
    text = text.strip()
    m = re.search(r'(?: وزنى|الوزن|وزن)\s*([\d.]+)', text)
    if m:
        return {"action": "weight", "value": float(m.group(1))}
    m = re.search(r'(?:مشيت|جريت|ركضت)\s*([\d.]+)\s*(?:كيلو|km)?', text)
    if m:
        etype = "run" if "جري" in text or "ركض" in text else "walk"
        return {"action": "exercise", "type": etype, "value": float(m.group(1))}
    if any(w in text for w in ["جيم", "gym", "تمرين", "حديد"]):
        return {"action": "exercise", "type": "gym", "value": 0}
    m = re.search(r'(?:نمت|نوم|نايم)\s*([\d.]+)\s*(?:ساع)?', text)
    if m:
        return {"action": "sleep", "value": float(m.group(1))}
    if any(w in text for w in ["صحتي", "صحة", "ملخص صحي"]):
        return {"action": "summary"}
    return {"action": "unknown"}


def handle_health_command(text: str) -> str:
    cmd = parse_health_command(text)
    action = cmd.get("action")
    if action == "weight":
        return log_weight(cmd["value"])
    elif action == "exercise":
        return log_exercise(cmd.get("type", "walk"), cmd.get("value", 0))
    elif action == "sleep":
        return log_sleep(cmd["value"])
    elif action == "summary":
        return health_summary()
    return ""
