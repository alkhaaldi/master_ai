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
EPOCH = date(2024, 1, 1)  # corrected: 2024-01-01 aligns A-shift to actual schedule

def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_shift(target_date=None):
    if target_date is None: target_date = date.today()
    days_since = (target_date - EPOCH).days
    idx = days_since % 8
    shift = SHIFT_PATTERN[idx]
    return {"date": target_date.isoformat(), "shift": shift, "emoji": SHIFT_EMOJI[shift], "times": SHIFT_TIMES[shift], "day_name": _arabic_day(target_date), "_target": target_date}

def _arabic_day(d):
    return ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"][d.weekday()]

def get_shift_display(target_date=None):
    s = get_shift(target_date)
    # Determine 1st or 2nd day of shift pair
    days_since = (s["_target"] - EPOCH).days
    pair_pos = days_since % 2  # 0=first, 1=second
    order = "أول" if pair_pos == 0 else "ثاني"
    if s["shift"] == "إجازة":
        order_label = ""
    else:
        order_label = f" ({order} {s['shift']})"
    return f"{s['emoji']} {s['day_name']} {s['date']}{order_label}\n🏭 شفت {s['shift']} ({s['times']})"

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
    """Parse Arabic work commands with date extraction."""
    import re
    text = text.strip()
    MONTHS = {"يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4, "مايو": 5, "يونيو": 6,
             "يوليو": 7, "اغسطس": 8, "سبتمبر": 9, "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12}

    # Check for "first/second" questions
    if any(w in text for w in ["اول", "أول", "ثاني", "ثانى"]):
        return {"action": "shift", "date": date.today()}  # will show 1st/2nd in display

    if any(w in text for w in ["شفتي", "شفت", "دوام", "دوامي"]):
        # Tomorrow/yesterday
        if "باكر" in text or "بكرة" in text or "بكره" in text:
            return {"action": "shift", "date": date.today() + timedelta(days=1)}
        if "أمس" in text or "امس" in text:
            return {"action": "shift", "date": date.today() - timedelta(days=1)}

        # Date: "9 مارس" or "تاريخ 9 مارس" or "9/3"
        m = re.search(r"(\d{1,2})\s*[/\-]\s*(\d{1,2})", text)
        if m:
            day, month = int(m.group(1)), int(m.group(2))
            year = date.today().year
            try:
                return {"action": "shift", "date": date(year, month, day)}
            except ValueError:
                pass

        for month_name, month_num in MONTHS.items():
            if month_name in text:
                dm = re.search(r"(\d{1,2})", text)
                if dm:
                    day = int(dm.group(1))
                    year = date.today().year
                    try:
                        return {"action": "shift", "date": date(year, month_num, day)}
                    except ValueError:
                        pass

        # Day names
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
    if "اوفرتايم" in text or "overtime" in text:
        m = re.search(r"(\d+)", text)
        if m: return {"action": "ot", "hours": float(m.group(1))}
        return {"action": "ot_summary"}
    if "اجازة" in text or "اجازتي" in text:
        if "رصيد" in text or "باقي" in text: return {"action": "leave_balance"}
        return {"action": "leave", "type": "annual"}
    return {"action": "shift", "date": date.today()}


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
