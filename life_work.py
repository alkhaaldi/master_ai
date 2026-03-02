"""
life_work.py - Shift & Work Tracker for KNPC MAB Unit Controller
AABBCCDD pattern, OT tracking, leave balance
"""
import json, re, sqlite3, logging
from datetime import datetime, date, timedelta

logger = logging.getLogger("life_work")
DB_PATH = "/home/pi/master_ai/data/audit.db"

SHIFT_PATTERN = ["صباحي", "صباحي", "عصري", "عصري", "ليلي", "ليلي", "إجازة", "إجازة"]
SHIFT_EMOJI = {"صباحي": "🌅", "عصري": "🌇", "ليلي": "🌙", "إجازة": "🏖"}
SHIFT_TIMES = {"صباحي": "7:00 AM - 3:00 PM", "عصري": "3:00 PM - 11:00 PM", "ليلي": "11:00 PM - 7:00 AM", "إجازة": "يوم إجازة"}
EPOCH = date(2024, 1, 4)

def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_shift(target_date=None):
    if target_date is None: target_date = date.today()
    days_since = (target_date - EPOCH).days
    idx = days_since % 8
    shift = SHIFT_PATTERN[idx]
    return {"date": target_date.isoformat(), "shift": shift, "emoji": SHIFT_EMOJI[shift], "times": SHIFT_TIMES[shift], "day_name": _arabic_day(target_date)}

def _arabic_day(d):
    return ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"][d.weekday()]

def get_shift_display(target_date=None):
    s = get_shift(target_date)
    return f"{s['emoji']} {s['day_name']} {s['date']}\n🏭 شفت {s['shift']} ({s['times']})"

def get_week_schedule(start=None):
    if not start: start = date.today()
    msg = "📅 **جدول الأسبوع**\n\n"
    for i in range(7):
        d = start + timedelta(days=i)
        s = get_shift(d)
        mark = " ← اليوم" if d == date.today() else ""
        msg += f"{s['emoji']} {s['day_name']} {d.day}/{d.month}: {s['shift']}{mark}\n"
    return msg

def get_month_schedule(month=None, year=None):
    now = date.today()
    if not month: month = now.month
    if not year: year = now.year
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) - timedelta(days=1) if month == 12 else date(year, month + 1, 1) - timedelta(days=1)
    counts = {"صباحي": 0, "عصري": 0, "ليلي": 0, "إجازة": 0}
    d = start
    while d <= end:
        counts[get_shift(d)["shift"]] += 1
        d += timedelta(days=1)
    msg = f"📅 **شفتات شهر {month}/{year}**\n\n"
    for shift, count in counts.items():
        msg += f"{SHIFT_EMOJI[shift]} {shift}: {count} يوم\n"
    msg += f"\n🏭 مجموع أيام العمل: {counts['صباحي'] + counts['عصري'] + counts['ليلي']}"
    return msg

def add_ot(hours, notes=""):
    db = _db()
    db.execute("INSERT INTO life_data (domain, category, data, amount, ref_date) VALUES (?,?,?,?,?)",
        ("work", "overtime", json.dumps({"hours": hours, "notes": notes}, ensure_ascii=False), hours, date.today().isoformat()))
    db.commit()
    return f"✅ تم تسجيل {hours} ساعة OT" + (f"\n📝 {notes}" if notes else "")

def get_ot_summary(period="month"):
    db = _db()
    now = date.today()
    start = now.replace(day=1).isoformat() if period == "month" else (now - timedelta(days=365)).isoformat()
    rows = db.execute("SELECT SUM(amount) as total, COUNT(*) as days FROM life_data WHERE domain='work' AND category='overtime' AND ref_date >= ?", (start,)).fetchone()
    total = rows["total"] or 0
    days = rows["days"] or 0
    label = "هالشهر" if period == "month" else "السنة"
    return f"⏰ OT {label}: {total:.1f} ساعة ({days} يوم)"

def add_leave(leave_type="annual", notes=""):
    db = _db()
    db.execute("INSERT INTO life_data (domain, category, data, amount, ref_date) VALUES (?,?,?,?,?)",
        ("work", f"leave_{leave_type}", json.dumps({"type": leave_type, "notes": notes}, ensure_ascii=False), 1, date.today().isoformat()))
    db.commit()
    type_ar = {"annual": "سنوية", "sick": "مرضية", "emergency": "طارئة"}.get(leave_type, leave_type)
    return f"✅ تم تسجيل إجازة {type_ar}" + (f"\n📝 {notes}" if notes else "")

def get_leave_balance():
    db = _db()
    year_start = date.today().replace(month=1, day=1).isoformat()
    rows = db.execute("SELECT category, COUNT(*) as used FROM life_data WHERE domain='work' AND category LIKE 'leave_%' AND ref_date >= ? GROUP BY category", (year_start,)).fetchall()
    annual_used = sick_used = 0
    for r in rows:
        if "annual" in r["category"]: annual_used = r["used"]
        elif "sick" in r["category"]: sick_used = r["used"]
    msg = f"📋 **رصيد الإجازات {date.today().year}**\n\n"
    msg += f"🏖 سنوية: {30 - annual_used} متبقي (استخدمت {annual_used}/30)\n"
    msg += f"🤒 مرضية: {sick_used} مستخدمة"
    return msg

def parse_work_command(text):
    text = text.strip()
    if any(w in text for w in ["شفتي", "شفت", "دوام"]):
        if "باكر" in text or "بكرة" in text:
            return {"action": "shift", "date": date.today() + timedelta(days=1)}
        if "أمس" in text:
            return {"action": "shift", "date": date.today() - timedelta(days=1)}
        day_map = {"الأحد": 6, "الاثنين": 0, "الثلاثاء": 1, "الأربعاء": 2, "الخميس": 3, "الجمعة": 4, "السبت": 5}
        for day_name, weekday in day_map.items():
            if day_name in text:
                today = date.today()
                days_ahead = weekday - today.weekday()
                if days_ahead <= 0: days_ahead += 7
                return {"action": "shift", "date": today + timedelta(days=days_ahead)}
        return {"action": "shift", "date": date.today()}
    if "جدول" in text and ("أسبوع" in text or "الاسبوع" in text): return {"action": "week"}
    if "شفتات" in text and "شهر" in text: return {"action": "month"}
    m = re.search(r'(?:سجل\s+)?(?:OT|اوتي|أوفرتايم|overtime)\s*([\d.]+)', text, re.IGNORECASE)
    if m: return {"action": "ot", "hours": float(m.group(1))}
    if any(w in text for w in ["إجازة", "اجازة", "leave"]):
        if any(w in text for w in ["مرضية", "sick"]): return {"action": "leave", "type": "sick"}
        if any(w in text for w in ["باقي", "رصيد", "كم"]): return {"action": "leave_balance"}
        return {"action": "leave", "type": "annual"}
    if "OT" in text.upper() and any(w in text for w in ["كم", "مجموع"]): return {"action": "ot_summary"}
    return {"action": "unknown"}

def handle_work_command(text):
    cmd = parse_work_command(text)
    a = cmd.get("action")
    if a == "shift": return get_shift_display(cmd.get("date"))
    if a == "week": return get_week_schedule()
    if a == "month": return get_month_schedule()
    if a == "ot": return add_ot(cmd["hours"])
    if a == "ot_summary": return get_ot_summary()
    if a == "leave": return add_leave(cmd.get("type", "annual"))
    if a == "leave_balance": return get_leave_balance()
    return ""
