"""
family_assistant.py — Family Assistant for Master AI
Tracks family members, important dates, and provides family-related queries.

Members: Salem, Oana (wife), عبود/Abdullah (son, 4 Feb 2026), عائشة/Aisha (daughter), ناهد (mother)
"""
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger("family")

FAMILY = {
    "salem": {"name": "سالم", "name_en": "Salem", "role": "أب"},
    "oana": {"name": "أوانا", "name_en": "Oana", "role": "زوجة", "aliases": ["زوجتي","أم عبود","الحرمة"]},
    "abdallah": {"name": "عبدالله", "nick": "عبود", "role": "ابن", "birthday": date(2026, 2, 4), "aliases": ["عبود","عبودي","الولد","ولدي"]},
    "aisha": {"name": "عائشة", "nick": "عيوشة", "role": "بنت", "aliases": ["عيوشة","البنت","بنتي"]},
    "nahed": {"name": "ناهد", "role": "أم", "room": "غرفة ماما", "aliases": ["أمي","الوالدة","أم سالم"]},
}


def get_age(birthday, ref_date=None):
    """Calculate age from birthday."""
    ref = ref_date or date.today()
    delta = ref - birthday
    months = delta.days // 30
    days = delta.days % 30
    years = months // 12
    months = months % 12
    if years > 0:
        return f"{years} سنة و {months} شهر و {days} يوم"
    elif months > 0:
        return f"{months} شهر و {days} يوم"
    else:
        return f"{days} يوم"


def get_next_birthday(birthday):
    """Get next birthday date."""
    today = date.today()
    this_year = birthday.replace(year=today.year)
    if this_year < today:
        this_year = birthday.replace(year=today.year + 1)
    days_until = (this_year - today).days
    return this_year, days_until


def get_family_info(query=None):
    """Get family info. If query mentions a member, return their details."""
    q = (query or "").lower()
    
    # Find specific member
    for mid, m in FAMILY.items():
        names_to_check = [m["name"].lower(), m.get("nick","").lower(), m.get("name_en","").lower()]
        names_to_check.extend([a.lower() for a in m.get("aliases",[])])
        
        if any(n and n in q for n in names_to_check):
            lines = [f"U0001f464 {m['name']} ({m['role']})"]
            
            if "birthday" in m:
                age = get_age(m["birthday"])
                lines.append(f"  U0001f382 عمره: {age}")
                next_bd, days = get_next_birthday(m["birthday"])
                lines.append(f"  U0001f389 عيد ميلاده الجاي: {next_bd} (باقي {days} يوم)")
            
            if "room" in m:
                lines.append(f"  U0001f3e0 غرفة: {m['room']}")
            
            return chr(10).join(lines)
    
    # Full family overview
    lines = ["U0001f46a العائلة:"]
    for mid, m in FAMILY.items():
        extra = ""
        if "birthday" in m:
            age = get_age(m["birthday"])
            extra = f" — {age}"
        if "room" in m:
            extra += f" — {m['room']}"
        lines.append(f"  • {m['name']} ({m['role']}){extra}")
    
    # Upcoming birthdays
    upcoming = []
    for mid, m in FAMILY.items():
        if "birthday" in m:
            _, days = get_next_birthday(m["birthday"])
            if days <= 30:
                upcoming.append((m["name"], days))
    
    if upcoming:
        lines.append("")
        lines.append("U0001f389 قريباً:")
        for name, days in upcoming:
            lines.append(f"  • عيد ميلاد {name} بعد {days} يوم")
    
    return chr(10).join(lines)
