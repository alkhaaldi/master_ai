"""Quick Query v2 — fast answers without LLM calls.
Handles: home status, room status, shift queries, AC/lights count.
"""
import httpx
import logging
import os
import re


def _normalize_ar(text):
    """Normalize Arabic text for better matching."""
    t = text.strip().lower()
    # Remove tashkeel only
    _TASHKEEL = set("ًٌٍَُِّْٰٕٖٜٟٓٔٗ٘ٙٚٛٝٞ")
    t = "".join(c for c in t if c not in _TASHKEEL)
    for _o, _n in [(chr(0x623),chr(0x627)),(chr(0x625),chr(0x627)),(chr(0x622),chr(0x627)),(chr(0x626),chr(0x621)),(chr(0x624),chr(0x621))]:
        t = t.replace(_o, _n)
    t = t.replace(chr(0x629), chr(0x647))
    t = t.replace(chr(0x649), chr(0x64a))
    return t

from datetime import datetime, timedelta

logger = logging.getLogger("quick_query")

HA_URL = os.environ.get("HA_URL", "http://localhost:8123")
HA_TOKEN = os.environ.get("HA_TOKEN", "")

# Shift data (same as life_work.py)
_SHIFT_PATTERN = ["صباحي", "صباحي", "عصري", "عصري", "ليلي", "ليلي", "إجازة", "إجازة"]
_SHIFT_EMOJI = {"صباحي": "🌅", "عصري": "🌇", "ليلي": "🌙", "إجازة": "🏖"}
_SHIFT_TIMES = {"صباحي": "7:00 AM - 3:00 PM", "عصري": "3:00 PM - 11:00 PM", "ليلي": "11:00 PM - 7:00 AM", "إجازة": "يوم إجازة"}
_EPOCH = datetime(2024, 1, 4).date()
_DAYS_AR = {0: "الاثنين", 1: "الثلاثاء", 2: "الأربعاء", 3: "الخميس", 4: "الجمعة", 5: "السبت", 6: "الأحد"}
_H_MO = {1: "محرم", 2: "صفر", 3: "ربيع الأول", 4: "ربيع الثاني", 5: "جمادى الأولى", 6: "جمادى الثانية", 7: "رجب", 8: "شعبان", 9: "رمضان", 10: "شوال", 11: "ذو القعدة", 12: "ذو الحجة"}

def _get_shift(d=None):
    if d is None: d = datetime.now().date()
    idx = (d - _EPOCH).days % 8
    s = _SHIFT_PATTERN[idx]
    pos = 1 if idx % 2 == 0 else 2
    return s, _SHIFT_EMOJI[s], _SHIFT_TIMES[s], pos

# Room name mapping for entity filtering
ROOM_MAP = {
    "الديوانية": ["diwaniya", "diwan"],
    "المعيشه": ["living", "living_room"],
    "الصاله": ["living", "living_room"],
    "المطبخ": ["kitchen"],
    "غرفة النوم": ["master", "bedroom", "my_room"],
    "الماستر": ["master", "my_room"],
    "غرفة ماما": ["mama", "mom"],
    "غرفة 3": ["room_3", "room3"],
    "غرفة 5": ["room_5", "room5"],
    "الاستقبال": ["reception", "guest"],
}

# ═══════════════════════════════════════════════════
# MEDIA PLAYER: Speed Engine Support
# ═══════════════════════════════════════════════════

# Excluded junk/virtual/duplicate entities
_MP_EXCLUDED = {
    "media_player.none", "media_player.this_device", "media_player.everywhere",
    "media_player.my_room_alexa", "media_player.living_room_alexa",
    "media_player.googletv6729", "media_player.googletv6729_2",
    "media_player.sony_men_room", "media_player.sony_men_room_2",
}

# Bluesound MA sync group
_MA_LEADER = "media_player.office_1_2"
_MA_FOLLOWERS = {"media_player.office_2_2", "media_player.room_3_2", "media_player.ground_floor"}
_MA_ALL = {_MA_LEADER} | _MA_FOLLOWERS
_PLAYBACK_ACTIONS = {"media_play", "media_pause", "media_stop", "media_play_pause"}

# Alias → entity_id mapping (Arabic + English)
_MEDIA_ALIASES = {
    # TVs
    "تلفزيون المعيشه": "media_player.bravia_kd_85x85j",
    "تلفزيون الصاله": "media_player.bravia_kd_85x85j",
    "تلفزيون الليفنق": "media_player.bravia_kd_85x85j",
    "living room tv": "media_player.bravia_kd_85x85j",
    "bravia": "media_player.bravia_kd_85x85j",
    "تلفزيون الديوانيه": "media_player.bravia_4k_vh2",
    "diwaniya tv": "media_player.bravia_4k_vh2",
    "تلفزيون غرفتي": "media_player.sony_kd_65x80j",
    "تلفزيون الماستر": "media_player.sony_kd_65x80j",
    "my room tv": "media_player.sony_kd_65x80j",
    "سامسونج": "media_player.samsung_bu8000_85_tv",
    "samsung": "media_player.samsung_bu8000_85_tv",
    "samsung tv": "media_player.samsung_bu8000_85_tv",
    "بلاوبنكت": "media_player.blaupunkt_android_tv",
    "blaupunkt": "media_player.blaupunkt_android_tv",
    # Speakers (Bluesound)
    "سبيكر الاول": _MA_LEADER,
    "سماعه الاول": _MA_LEADER,
    "first floor speaker": _MA_LEADER,
    "سماعه القران": _MA_LEADER,
    "quran speaker": _MA_LEADER,
    "سبيكر الاوفس": "media_player.office_2_2",
    "سماعه الاوفس": "media_player.office_2_2",
    "office speaker": "media_player.office_2_2",
    "سبيكر غرفه 3": "media_player.room_3_2",
    "سماعه غرفه 3": "media_player.room_3_2",
    "صوت غرفه 3": "media_player.room_3_2",
    "room 3 speaker": "media_player.room_3_2",
    "سبيكر الارضي": "media_player.ground_floor",
    "سماعه الارضي": "media_player.ground_floor",
    "ground speaker": "media_player.ground_floor",
    "downstairs speaker": "media_player.ground_floor",
}

# Normalized alias lookup (built once)
_MEDIA_ALIASES_NORM = {_normalize_ar(k): v for k, v in _MEDIA_ALIASES.items()}

# Generic fallback keywords → entity (when no specific alias matched)
_MP_GENERIC = {
    "تلفزيون": "media_player.bravia_kd_85x85j",  # default TV = living room
    "التلفزيون": "media_player.bravia_kd_85x85j",
    "tv": "media_player.bravia_kd_85x85j",
    "سبيكر": _MA_LEADER,  # default speaker = leader
    "السبيكر": _MA_LEADER,
    "سماعه": _MA_LEADER,
    "السماعه": _MA_LEADER,
    "speaker": _MA_LEADER,
}
_MP_GENERIC_NORM = {_normalize_ar(k): v for k, v in _MP_GENERIC.items()}


async def _ha_states():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{HA_URL}/api/states", headers={"Authorization": f"Bearer {HA_TOKEN}"})
            if r.status_code == 200: return r.json()
    except Exception as e:
        logger.error(f"HA states: {e}")
    return []


async def quick_answer(text: str):
    """Try to answer quickly without LLM. Returns None if no match."""
    t = _normalize_ar(text)

    # 0-news) News — zero LLM (read latest digest only)
    _news_pats = ["اخر الاخبار", "عطني الاخبار", "ملخص الاخبار", "شنو الاخبار",
                   "اخبار الكويت", "اخبار الاقتصاد", "اخبار التكنولوجيا"]
    for _np in _news_pats:
        if _normalize_ar(_np) in t:
            try:
                from news_engine import handle_news_latest
                cat = None
                if "كويت" in t: cat = "kuwait"
                elif "اقتصاد" in t: cat = "economy"
                elif "تكنولوجيا" in t or "تقنيه" in t: cat = "technology"
                return handle_news_latest(cat)
            except Exception:
                break

    # 0-exp) Expenses — zero LLM
    _exp_today = ["كم صرفت اليوم", "مصاريف اليوم", "صرف اليوم"]
    _exp_week = ["كم صرفت هالاسبوع", "مصاريف الاسبوع", "صرف هالاسبوع"]
    _exp_month = ["كم صرفت هالشهر", "مصاريف الشهر", "صرف هالشهر"]
    _exp_recent = ["اخر مصاريف", "شنو اخر مصاريفي", "اخر 5 مصاريف", "المصاريف الاخيره"]
    for _ep in _exp_today:
        if _normalize_ar(_ep) in t:
            try:
                from expenses_engine import handle_spent_today
                return handle_spent_today()
            except Exception:
                break
    for _ep in _exp_week:
        if _normalize_ar(_ep) in t:
            try:
                from expenses_engine import handle_spent_week
                return handle_spent_week()
            except Exception:
                break
    for _ep in _exp_month:
        if _normalize_ar(_ep) in t:
            try:
                from expenses_engine import handle_spent_month
                return handle_spent_month()
            except Exception:
                break
    for _ep in _exp_recent:
        if _normalize_ar(_ep) in t:
            try:
                from expenses_engine import handle_recent_expenses
                return handle_recent_expenses()
            except Exception:
                break

    # 0-top-vol) Top traded stocks — zero LLM
    _top_pats = ["اعلى تداول", "اكثر تداول", "الاعلى تداول", "اكبر حجم", "top volume", "top traded", "اعلى حجم"]
    for _tp in _top_pats:
        if _normalize_ar(_tp) in t:
            try:
                from tv_data import get_top_volume, format_top_volume_arabic
                _tv = get_top_volume(10)
                return format_top_volume_arabic(_tv)
            except Exception as _te:
                logger.warning(f"Top volume error: {_te}")
                break

    # 0-stock) Stock price — zero LLM
    _stock_pats = ["شكثر", "سعر", "كم سعر", "سعر سهم", "شلون"]
    _stock_names = {
        "كلينينق": "CLEANING", "كلينينج": "CLEANING", "التنظيف": "CLEANING", "cleaning": "CLEANING",
        "سنرجي": "SENERGY", "senergy": "SENERGY",
        "اينوفست": "INOVEST", "inovest": "INOVEST",
        "بيتك": "KFH", "بيت التمويل": "KFH", "kfh": "KFH",
        "الوطني": "NBK", "nbk": "NBK",
        "زين": "ZAIN", "zain": "ZAIN",
        "اوريدو": "OOREDOO", "ooredoo": "OOREDOO",
        "بوبيان": "BOUBYAN", "boubyan": "BOUBYAN",
        "برقان": "BURG", "burg": "BURG",
        "المباني": "MABANEE", "mabanee": "MABANEE",
        "الجزيره": "JAZEERA", "jazeera": "JAZEERA",
        "بورصه": "BOURSA", "boursa": "BOURSA",
        "كامكو": "KAMCO", "kamco": "KAMCO",
        "معدات": "EQUIPMENT", "المعدات": "EQUIPMENT", "equipment": "EQUIPMENT",
        "اكتتاب": "EKTTITAB", "ekttitab": "EKTTITAB",
        "الغانم": "ALG", "غانم": "ALG", "alg": "ALG",
        "الخليج": "GBK", "بنك الخليج": "GBK", "gbk": "GBK",
        "stc": "STC", "اتصالات": "STC",
        "المتكامله": "INTEGRATED", "integrated": "INTEGRATED",
        "اوريدو": "OOREDOO", "ooredoo": "OOREDOO",
        "الاهلي": "ABK", "abk": "ABK",
        "التجاري": "CBK", "cbk": "CBK",
        "وربه": "WARBABANK", "warba": "WARBABANK",
        "الدولي": "KIB", "kib": "KIB",
        "نبك": "NBK",
    }
    for _sp in _stock_pats:
        if _normalize_ar(_sp) in t:
            _found_ticker = None
            for _alias, _tick in _stock_names.items():
                if _normalize_ar(_alias) in t:
                    _found_ticker = _tick
                    break
            if not _found_ticker:
                _words = t.split()
                for _w in _words:
                    _up = _w.upper()
                    if len(_up) >= 2 and _up.isalpha() and _up not in ("شكثر","سعر","كم","سهم","شلون"):
                        _found_ticker = _up
                        break
            if _found_ticker:
                try:
                    from tv_data import get_price
                    from tv_analysis import full_analysis, format_analysis_arabic
                    _pd = get_price(_found_ticker)
                    if "error" not in _pd:
                        _an = full_analysis(_pd)
                        return format_analysis_arabic(_an)
                    else:
                        return f"\u274c ما لقيت بيانات لـ {_found_ticker}"
                except Exception as _se:
                    logger.warning(f"Stock quick query error: {_se}")
                    break

    # 0-rel) Relationships & Occasions — zero LLM
    _occ_patterns = [
        "مناسبات اليوم", "اليوم مناسبه", "اليوم في مناسبه", "عندنا شي اليوم",
        "مناسبات باجر", "باجر مناسبه", "باجر في مناسبه",
        "المناسبات الجايه", "شنو المناسبات", "في مناسبات", "مناسبات قريبه",
        "مناسبات هالشهر", "مناسبات هالاسبوع", "عندنا مناسبات",
    ]
    for _op in _occ_patterns:
        if _normalize_ar(_op) in t:
            try:
                from relationships_engine import handle_occasions_today, handle_occasions_tomorrow, handle_occasions_upcoming
                if any(w in t for w in ["باجر", "بكره"]):
                    return handle_occasions_tomorrow()
                elif any(w in t for w in ["اليوم", "عندنا شي"]):
                    return handle_occasions_today()
                else:
                    return handle_occasions_upcoming()
            except Exception:
                break

    # Birthday lookup: "متى عيد ميلاد X"
    import re as _re2
    _bd_match = _re2.search(r"متى عيد ميلاد\s+(\S+)", t)
    if not _bd_match:
        _bd_match = _re2.search(r"عيد ميلاد\s+(\S+)\s+متى", t)
    if _bd_match:
        try:
            from relationships_engine import handle_birthday_lookup
            return handle_birthday_lookup(_bd_match.group(1))
        except Exception:
            pass

    # 0-cal) Calendar quick queries — zero LLM
    if re.search(r"شنو عندي اليوم|عندي شي اليوم|مواعيد اليوم|جدولي اليوم|اليوم فاضي|today", t):
        try:
            from calendar_engine import get_today_events
            from calendar_reporting import render_today
            from life_work import get_shift
            from task_engine import task_stats, task_list
            parts = []
            si = get_shift()
            parts.append("👷 " + si.get("emoji","") + " " + si.get("shift","") + " " + si.get("times",""))
            cal = render_today(get_today_events())
            if cal: parts.append(cal)
            s = task_stats()
            if s["due_today"] or s["overdue"]:
                tline = "📋 مهام: "
                if s["due_today"]: tline += str(s["due_today"]) + " اليوم  "
                if s["overdue"]:   tline += "⚠️ " + str(s["overdue"]) + " متأخرة"
                parts.append(tline)
                for task in task_list(due_today=True)[:3]:
                    parts.append("  • " + task["title"][:38])
            return chr(10).join(parts)
        except Exception as e:
            return f"calendar error: {e}"

    if re.search(r"شنو عندي باجر|عندي شي باجر|مواعيد باجر|جدولي باجر|باجر فاضي|tomorrow", t):
        try:
            from calendar_engine import get_tomorrow_events
            from calendar_reporting import render_tomorrow
            return render_tomorrow(get_tomorrow_events())
        except Exception as e:
            return f"calendar error: {e}"

    if re.search(r"شنو عندي.*اسبوع|مواعيد.*اسبوع|جدولي.*اسبوع|هالاسبوع|week", t):
        try:
            from calendar_engine import get_week_events
            from calendar_reporting import render_week
            return render_week(get_week_events())
        except Exception as e:
            return f"calendar error: {e}"

    # Task quick patterns (zero-LLM)
    if re.search(r"مهامي|شنو مهامي|وين مهامي|المهام النشطة", t):
        try:
            from task_engine import quick_tasks_active
            return quick_tasks_active()
        except Exception as e:
            return f"tasks error: {e}"

    if re.search(r"مهام اليوم|مهامي اليوم|مستحقة اليوم", t):
        try:
            from task_engine import quick_tasks_today
            return quick_tasks_today()
        except Exception as e:
            return f"tasks error: {e}"

    if re.search(r"مهام متأخرة|مهامي متأخرة|المتأخرة", t):
        try:
            from task_engine import quick_tasks_overdue
            return quick_tasks_overdue()
        except Exception as e:
            return f"tasks error: {e}"

    if re.search(r"فاضي امتى|وقتي الحر|فراغ امتى|free time|هل عندي وقت", t):
        try:
            from life_work import get_shift, get_week_schedule
            from datetime import date
            si = get_shift()
            shift = si.get("shift", "")
            times = si.get("times", "")
            if shift in ("إجازة", "اليوم إجازة"):
                return "🏖️ عندك إجازة اليوم 🎉"
            return ("👷 \u0627\u0644\u064a\u0648\u0645 " + shift + " (" + times + ")\n\u0627\u0644\u0648\u0642\u062a \u0627\u0644\u062d\u0631 \u0628\u0639\u062f \u0627\u0646\u062a\u0647\u0627\u0621 \u0627\u0644\u0648\u0631\u062f\u064a\u0629")
        except Exception as e:
            return f"shift error: {e}"

    # Task done — "خلصت [keyword]" / "انتهيت من [keyword]" / "done [keyword]"
    _done_m = re.search(r"(خلصت|خلصنا|انتهيت من|انجزت|done|finished|completed)[ ]+(.+)", t)
    if _done_m:
        _kw = _done_m.group(2).strip()
        if len(_kw) >= 3:
            try:
                from task_engine import task_search, task_done
                _kw_orig = _kw.replace(chr(0x647), chr(0x629))  # ه->ة for search
                _found = task_search(_kw) or task_search(_kw_orig)
                _active = [x for x in _found if x.get('status') not in ('done','cancelled')]
                if _active:
                    _t = _active[0]
                    task_done(_t['id'])
                    return "✅ تمت إنجاز المهمة #" + str(_t['id']) + ": " + _t['title']
            except Exception: pass

    # Quick task add — "اضف مهمة [title]" / "ذكرني [title]"  
    _add_m = re.search(r"(اضف مهمه|اضف مهمة|أضف مهمه|أضف مهمة|ذكرني|add task)[ ]+(.+)", t)
    if _add_m:
        _title = _add_m.group(2).strip()
        # Remove leading preposition ب from ذكرني
        if _add_m.group(1) in ('ذكرني',) and _title.startswith(chr(0x628)):
            _title = _title[1:].strip()
        if len(_title) >= 3:
            try:
                from task_engine import task_create
                from tg_tasks import _parse_priority, _parse_category, _parse_due_date
                _task = task_create(
                    title=_title,
                    priority=_parse_priority(_title),
                    category=_parse_category(_title),
                    due_date=_parse_due_date(_title),
                )
                return "✅ أضفت مهمة #" + str(_task['id']) + ": " + _task['title']
            except Exception: pass

    if re.search(r"أضف مهام من الإيميل|مهام من الإيميل|suggest.*task|task.*email", t):
        try:
            import asyncio, concurrent.futures
            from inbox_engine import format_email_task_suggestions
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(asyncio.run, format_email_task_suggestions()).result(timeout=20)
            return result if result else "✅ ما في إيميلات تحتاج إجراء"
        except Exception as e:
            return f"suggest error: {e}"

    # 0a) Capabilities — zero LLM
    if re.search(r"شنو تقدر تسوي|شنو تعرف تسوي|وش تسوي|قدراتك|ميزاتك", t):
        cap = "اقدر اساعدك بـ:" + chr(10)
        cap += "🏠 التحكم بالبيت الذكي (أنوار، مكيفات، ستائر، أقفال)" + chr(10)
        cap += "📊 حالة الأجهزة والغرف" + chr(10)
        cap += "📅 جدول الشفتات والدوام" + chr(10)
        cap += "🌤️ حالة الطقس" + chr(10)
        cap += "🧠 حفظ واسترجاع معلومات" + chr(10)
        cap += "🔧 أوامر النظام والصيانة" + chr(10)
        cap += "شنو تبي اسويلك؟"
        return cap

    # 0aaae) /family command
    if t.strip() == "/family" or re.search(r"عائله|عائلتي", t):
        try:
            from family_assistant import get_family_info
            return get_family_info(t)
        except Exception as e:
            return f"family error: {e}"

        # 0aaad) /guardian command
    if t.strip() == "/guardian":
        try:
            from system_guardian import get_status
            return get_status()
        except Exception as e:
            return f"guardian error: {e}"

        # 0aaac) /timeline command
    if t.strip() == "/timeline":
        try:
            from world_state_delta import _last_event, _get_db
            conn = _get_db()
            if conn:
                r = _last_event(conn, {"light","climate","cover","media_player","lock","fan"})
                conn.close()
                return r
            return "DB not available"
        except Exception as e:
            return f"timeline error: {e}"

        # 0aaab) /habits command
    if t.strip() == "/habits":
        try:
            from habit_engine import format_habit_report
            return format_habit_report()
        except Exception as e:
            return f"habit error: {e}"

        # 0aaa) /anomaly command — zero LLM
    if t.strip() == "/anomaly":
        try:
            from anomaly_engine import get_anomaly_summary
            alerts = get_anomaly_summary()
            if not alerts:
                return "✅ ما في شي غير طبيعي"
            lines = [f"🚨 {len(alerts)} تنبيه:", ""]
            for a in alerts:
                lines.append(a["message"])
                if a.get("suggestion"):
                    lines.append("  ➡ " + a["suggestion"])
            return chr(10).join(lines)
        except Exception as e:
            return f"anomaly error: {e}"

    # 0aa) /cost command — zero LLM
    if t.strip() == "/cost":
        try:
            from cost_tracker import get_cost_for_kpi
            c = get_cost_for_kpi()
            bar_len = 10
            filled = int(c["month_pct"] / 100 * bar_len)
            bar = chr(9608) * filled + chr(9617) * (bar_len - filled)
            return chr(10).join([
                "💰 Cost Tracker", "",
                f"📅 اليوم: ${c['today_usd']:.4f}",
                f"📆 الشهر: ${c['month_usd']:.2f} / ${c['month_budget_usd']:.0f}",
                f"[{bar}] {c['month_pct']:.1f}%",
                f"📊 متوسط/طلب: ${c['avg_per_request_usd']:.4f}",
            ])
        except:
            return "cost_tracker not loaded"

    # 0b) Greetings — zero LLM
    if re.match(r"^(مرحبا|هلا|السلام عليكم|هاي|سلام|اهلا)$", t):
        import datetime as _dt
        _h = _dt.datetime.now().hour
        _tod = "صباح الخير" if 5 <= _h < 12 else "مساء الخير" if 12 <= _h < 21 else "هلا"
        _s, _emoji, _times, _pos = _get_shift()
        return f"{_tod} سالم! {_emoji} شفتك اليوم {_s}. شنو تبي اسويلك؟"

    # 0c) Thanks — zero LLM
    if re.match(r"^(شكرا|مشكور|يعطيك العافية|ثانكس|thanks)$", t):
        return "العفو! اي خدمة ثانية؟ 😊"

    # 0d) Goodbye — zero LLM
    if re.match(r"^(مع السلامة|باي|يلا باي|bye)$", t):
        return "مع السلامة! 👋"

    # 1) Home status
    if re.search(r"وضع البيت|حالة البيت|شلون البيت", t):
        return await _home_status()

    # 2) AC count
    if re.search(r"كم مكيف|مكيفات شغال", t):
        return await _ac_count()

    # 3) Lights count
    if re.search(r"كم ضوء|اضواء شغال|كم نور", t):
        return await _lights_count()

    # 4) Shift queries (expanded — today/tomorrow/week/any shift mention)
    if re.search(r"شفتي|دوامي|ورديتي|شفت|اجازة|اجازتي", t):
        # Let LLM handle complex date questions (عيد, رمضان, هجري)
        if re.search(r"عيد|رمضان|هجري|ميلادي", t):
            pass  # fall through to LLM
        else:
            return _shift_answer(t)

    # 5) Room status
    for room_ar, room_keys in ROOM_MAP.items():
        _nr = _normalize_ar(room_ar)
        if _nr in t:
            return await _room_status(room_ar, room_keys)


    # 6) Locks status
    if re.search(r"اقفال|قفل|ابواب|باب", t):
        return await _locks_status()

    # 7) Media players — speed engine (actions + status)
    if re.search(r"سماعات|سماعه|سبيكر|ميديا|تلفزيون|tv|موسيقى|يشغل|صوت.*(?:سبيكر|تلفزيون|سماعه|غرفه \d)|(?:طفي|شغل|وقف|كمل|ارفع|خفض|ميوت|mute).*(?:تلفزيون|سبيكر|سماعه|tv|speaker)", t):
        _mp_result = await _handle_media_player(t)
        if _mp_result is not None:
            return _mp_result
        # Fall back to general media status for read-only queries
        return await _media_status()


    # 8) Weather
    if re.search(r"طقس|جو|حراره برا|درجه الحراره|weather|هواء", t):
        return await _weather()


    # 9) Covers/curtains
    if re.search(r"ستائر|ستارة|شتر|كم ستار|covers|curtains", t):
        return await _covers_status()

    # 10) Total active devices
    if re.search(r"كم جهاز|أجهزة شغال|كل شي شغال|active devices", t):
        return await _active_devices_count()

    
    # 11) System info (CPU/RAM/temp) — zero LLM
    if re.search(r"حراره المعالج|cpu|ram|رام|ديسك|disk|uptime|معالج", t):
        try:
            import subprocess as _sp2
            cpu = _sp2.getoutput("top -bn1 | grep Cpu | awk '{print $2}'")
            _mp = _sp2.getoutput("free -m").split(chr(10))[1].split()
            ram_pct = round(int(_mp[2])/int(_mp[1])*100, 1)
            temp = _sp2.getoutput("vcgencmd measure_temp").replace("temp=","").replace("'C","")
            disk = _sp2.getoutput("df -h / | tail -1 | awk '{print $5}'")
            import time as _t2
            _START = 0
            try:
                import os as _os2
                _pid = int(_sp2.getoutput("pgrep -f 'uvicorn.*server:app'"))
                _START = _os2.stat(f"/proc/{_pid}").st_mtime
            except: pass
            _up = int(_t2.time() - _START) if _START else 0
            _uh, _um = divmod(_up // 60, 60)
            return chr(10).join([
                f"🖥 CPU: {cpu}%",
                f"🧠 RAM: {ram_pct}% ({_mp[2]}/{_mp[1]}MB)",
                f"🌡 Temp: {temp}°C",
                f"💾 Disk: {disk}",
                f"⏱ Up: {_uh}h {_um}m",
            ])
        except:
            pass

    # 12) Memory stats — zero LLM
    if re.search(r"كم ذاكره|ذاكره منظمه|memory stats", t):
        try:
            import structured_memory as _smq
            s = _smq.get_stats()
            bt = s.get("by_type", {})
            return chr(10).join([
                f"🧠 الذاكرة المنظمة:",
                f"  مجموع: {s.get('total_active', 0)}",
                f"  حقائق: {bt.get('fact', 0)}",
                f"  أحداث: {bt.get('event', 0)}",
                f"  تصحيحاث: {bt.get('correction', 0)}",
                f"  تفضيلات: {bt.get('preference', 0)}",
                f"  ثقة: {s.get('avg_confidence', 0):.0%}",
            ])
        except:
            pass

    return None


def _shift_answer(t):
    """Smart shift answer with future lookup + Hijri."""
    today = datetime.now().date()
    
    from hijridate import Gregorian as _Gregorian
    def _fmt(d, label=""):
        s, emoji, times, _pos = _get_shift(d)
        dn = _DAYS_AR.get(d.weekday(), "")
        _pn = 'أول' if _pos == 1 else 'ثاني'
        _sn = {'صباحي':'صباحي','عصري':'عصري','ليلي':'ليلي','إجازة':'أوف'}.get(s, s)
        line = f"{emoji} {label}{dn} {d.strftime('%Y-%m-%d')}: {_pn} {_sn}"
        line += f"\n⏰ {times}"
        try:
            h = _Gregorian(d.year, d.month, d.day).to_hijri()
            mn = _H_MO.get(h.month, str(h.month))
            line += f"\n📅 {h.day} {mn} {h.year} هـ"
        except:
            pass
        return line
    
    def _next(target):
        for i in range(1, 16):
            d = today + timedelta(days=i)
            s, _, _, _ = _get_shift(d)
            if s == target:
                return d
        return None
    
    # Hijri date shift lookup (Eid + last Ramadan)
    try:
        from hijridate import Hijri as _Hijri
        _now_h = _Gregorian(today.year, today.month, today.day).to_hijri()
        if ('اخر' in t or 'آخر' in t) and 'رمضان' in t:
            _yr = _now_h.year if _now_h.month <= 9 else _now_h.year + 1
            try: _tgt = _Hijri(_yr, 9, 30).to_gregorian()
            except: _tgt = _Hijri(_yr, 9, 29).to_gregorian()
            return _fmt(_tgt, 'آخر يوم رمضان: ')
        if ('اول' in t or 'أول' in t) and 'عيد' in t:
            _yr = _now_h.year if _now_h.month <= 10 else _now_h.year + 1
            _tgt = _Hijri(_yr, 10, 1).to_gregorian()
            return _fmt(_tgt, 'أول يوم العيد: ')
    except Exception as _hijri_err:
        import logging; logging.getLogger('master_ai').warning(f'Hijri lookup error: {_hijri_err}')
    
    # Smart Hijri date parser: '28 رمضان شنو دوامي' or 'أول شوال'
    _hijri_months = {'محرم':1,'صفر':2,'ربيع الاول':3,'ربيع الثاني':4,'جمادى الاولى':5,'جمادى الثانية':6,'رجب':7,'شعبان':8,'رمضان':9,'شوال':10,'ذو القعدة':11,'ذو الحجة':12,'ذو الحجه':12}
    import re as _re0
    for _hm_name, _hm_num in _hijri_months.items():
        if _hm_name in t:
            _day_match = _re0.search(r'(\d{1,2})', t)
            if _day_match:
                try:
                    from hijridate import Hijri as _H2
                    _now_h2 = _Gregorian(today.year, today.month, today.day).to_hijri()
                    _hday = int(_day_match.group(1))
                    _hyr = _now_h2.year if _now_h2.month <= _hm_num else _now_h2.year + 1
                    _htgt = _H2(_hyr, _hm_num, _hday).to_gregorian()
                    return _fmt(_htgt, f'{_hday} {_hm_name}: ')
                except: pass
            break
    
    import re as _re
    if _re.search(r"صباح|صبح", t) and _re.search(r"جاي|قادم|متى|اول", t):
        d = _next("صباحي")
        if d: return _fmt(d, "أول صباحي جاي: ")
    if _re.search(r"عصر", t) and _re.search(r"جاي|قادم|متى|اول", t):
        d = _next("عصري")
        if d: return _fmt(d, "أول عصري جاي: ")
    if _re.search(r"ليل", t) and _re.search(r"جاي|قادم|متى|اول", t):
        d = _next("ليلي")
        if d: return _fmt(d, "أول ليلي جاي: ")
    if _re.search(r"اجاز|اوف", t):
        d = _next("إجازة")
        if d: return _fmt(d, "أول إجازة: ")
    if "رمضان" in t:
        return _fmt(today, "اليوم ")
    if "باكر" in t or "غدا" in t or "باخر" in t:
        d = today + timedelta(days=1)
        return _fmt(d, "باكر ")
    if "اسبوع" in t or "جدول" in t:
        ls = ["📅 جدول الأسبوع:\n"]
        for i in range(7):
            d = today + timedelta(days=i)
            s, emoji, _times, _pos = _get_shift(d)
            dn = _DAYS_AR.get(d.weekday(), "")
            mk = " ◀" if i == 0 else ""
            try:
                hh = _Gregorian(d.year, d.month, d.day).to_hijri()
                mn = _H_MO.get(hh.month, str(hh.month))
                hd = f" ({hh.day} {mn})"
            except:
                hd = ""
            ls.append(f"{emoji} {dn} {d.day}/{d.month}{hd}: {s}{mk}")
        return "\n".join(ls)
    return _fmt(today, "اليوم ")

async def _home_status():
    states = await _ha_states()
    if not states: return None
    lights_on = sum(1 for s in states if s["entity_id"].startswith("light.") and s["state"] == "on" and "backlight" not in s["entity_id"])
    lights_total = sum(1 for s in states if s["entity_id"].startswith("light."))
    ac_on = [s for s in states if s["entity_id"].startswith("climate.") and s["state"] != "off"]
    covers_open = sum(1 for s in states if s["entity_id"].startswith("cover.") and s["state"] == "open")
    covers_total = sum(1 for s in states if s["entity_id"].startswith("cover."))

    lines = [
        "🏠 وضع البيت:",
        f"💡 أضواء: {lights_on}/{lights_total} شغال",
        f"❄️ مكيفات: {len(ac_on)}/{sum(1 for s in states if s['entity_id'].startswith('climate.'))} شغال",
    ]
    for s in ac_on:
        name = s.get("attributes", {}).get("friendly_name", "")
        temp = s.get("attributes", {}).get("temperature", "?")
        lines.append(f"  {name}: {temp}°")
    lines.append(f"🏪 ستائر: {covers_open}/{covers_total} مفتوح")
    return chr(10).join(lines)


async def _ac_count():
    states = await _ha_states()
    if not states: return None
    ac_on = [s for s in states if s["entity_id"].startswith("climate.") and s["state"] != "off"]
    if not ac_on: return "❄️ كل المكيفات مطفية"
    lines = [f"❄️ {len(ac_on)} مكيف شغال:"]
    for s in ac_on:
        name = s.get("attributes", {}).get("friendly_name", "")
        temp = s.get("attributes", {}).get("temperature", "?")
        lines.append(f"  {name}: {temp}°")
    return chr(10).join(lines)


async def _lights_count():
    states = await _ha_states()
    if not states: return None
    on = sum(1 for s in states if s["entity_id"].startswith("light.") and s["state"] == "on" and "backlight" not in s["entity_id"])
    return f"💡 {on} ضوء شغال"


async def _room_status(room_ar, room_keys):
    """Status for a specific room."""
    states = await _ha_states()
    if not states: return None

    # Filter entities by room keys in entity_id or friendly_name
    room_entities = []
    for s in states:
        eid = s["entity_id"].lower()
        fname = s.get("attributes", {}).get("friendly_name", "").lower()
        if any(k in eid or k in fname for k in room_keys):
            room_entities.append(s)

    if not room_entities:
        return f"❓ ما لقيت أجهزة لـ{room_ar}"

    lights = [s for s in room_entities if s["entity_id"].startswith("light.") and "backlight" not in s["entity_id"]]
    acs = [s for s in room_entities if s["entity_id"].startswith("climate.")]
    covers = [s for s in room_entities if s["entity_id"].startswith("cover.")]

    lines = [f"🏠 {room_ar}:"]

    if lights:
        on = sum(1 for s in lights if s["state"] == "on")
        lines.append(f"💡 أضواء: {on}/{len(lights)} شغال")

    if acs:
        for s in acs:
            state = s["state"]
            temp = s.get("attributes", {}).get("temperature", "?")
            curr = s.get("attributes", {}).get("current_temperature", "?")
            if state == "off":
                lines.append(f"❄️ مكيف: مطفي")
            elif state in ("unknown", "unavailable"):
                lines.append(f"❄️ مكيف: ⚠️ {temp}° (حالي: {curr}°) — حالة غير معروفة")
            else:
                lines.append(f"❄️ مكيف: {state} {temp}° (حالي: {curr}°)")

    if covers:
        for s in covers:
            name = s.get("attributes", {}).get("friendly_name", "")
            state_ar = "مفتوح" if s["state"] == "open" else "مغلق"
            lines.append(f"🏪 {name}: {state_ar}")

    return chr(10).join(lines)


async def _locks_status():
    states = await _ha_states()
    if not states: return None
    locks = [s for s in states if s["entity_id"].startswith("lock.")]
    if not locks: return "🔐 ما فيه أقفال"
    locked = sum(1 for s in locks if s["state"] == "locked")
    lines = [f"🔐 الأقفال: {locked}/{len(locks)} مقفل"]
    for s in locks:
        name = s.get("attributes", {}).get("friendly_name", s["entity_id"])
        icon = "🔒" if s["state"] == "locked" else "🔓"
        state_ar = "مقفل" if s["state"] == "locked" else "مفتوح"
        lines.append(f"  {icon} {name}: {state_ar}")
    return chr(10).join(lines)


async def _media_status():
    states = await _ha_states()
    if not states: return None
    media = [s for s in states if s["entity_id"].startswith("media_player.") and s["state"] not in ("unavailable", "unknown") and s["entity_id"] not in _MP_EXCLUDED]
    playing = [s for s in media if s["state"] == "playing"]
    if not playing:
        return "🎵 ما فيه شي يشغل حالياً"
    lines = [f"🎵 {len(playing)} جهاز يشغل:"]
    for s in playing:
        name = s.get("attributes", {}).get("friendly_name", "")
        title = s.get("attributes", {}).get("media_title", "")
        artist = s.get("attributes", {}).get("media_artist", "")
        vol = s.get("attributes", {}).get("volume_level")
        vol_pct = f" ({int(vol*100)}%)" if vol else ""
        desc = title or artist or ""
        lines.append(f"  🔊 {name}: {desc}{vol_pct}")
    return chr(10).join(lines)


async def _weather():
    """Quick weather from Open-Meteo."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": 29.3375, "longitude": 47.9775,
                "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m",
                "timezone": "Asia/Kuwait",
                "forecast_days": 1,
                "daily": "temperature_2m_max,temperature_2m_min",
            })
            d = r.json()
            cur = d.get("current", {})
            daily = d.get("daily", {})
            temp = cur.get("temperature_2m", "?")
            code = cur.get("weather_code", 0)
            wind = cur.get("wind_speed_10m", "?")
            humid = cur.get("relative_humidity_2m", "?")
            hi = daily.get("temperature_2m_max", ["?"])[0]
            lo = daily.get("temperature_2m_min", ["?"])[0]
            
            CODES = {0:"☀️",1:"🌤",2:"⛅",3:"☁️",45:"🌫",48:"🌫",51:"🌦",53:"🌦",55:"🌧",61:"🌧",63:"🌧",65:"🌧️",71:"❄️",73:"❄️",75:"❄️",80:"🌦",81:"🌧",82:"⛈",95:"⚡",96:"⚡",99:"⚡"}
            icon = CODES.get(code, "🌡")
            
            return chr(10).join([
                f"{icon} الطقس الكويت:",
                f"🌡 حالياً: {temp}°C",
                f"⬆ أعلى: {hi}° | ⬇ أدنى: {lo}°",
                f"💨 رياح: {wind} km/h",
                f"💧 رطوبة: {humid}%",
            ])
    except Exception as e:
        return f"⚠️ {e}"


async def _covers_status():
    states = await _ha_states()
    if not states: return None
    covers = [s for s in states if s["entity_id"].startswith("cover.") and s["state"] not in ("unavailable", "unknown") and "_curtain" not in s["entity_id"]]
    if not covers: return "🎪 ما فيه ستائر"
    opened = [s for s in covers if s["state"] == "open"]
    closed = [s for s in covers if s["state"] == "closed"]
    lines = [f"🎪 الستائر: {len(opened)} مفتوح / {len(closed)} مغلق"]
    if opened:
        lines.append("")
        lines.append("🟢 المفتوحة:")
        for s in opened:
            name = s.get("attributes", {}).get("friendly_name", s["entity_id"])
            pos = s.get("attributes", {}).get("current_position", "")
            pos_txt = f" ({pos}%)" if pos != "" else ""
            lines.append(f"  • {name}{pos_txt}")
    return chr(10).join(lines)


async def _active_devices_count():
    states = await _ha_states()
    if not states: return None
    _on = {"on", "playing", "open", "heat", "cool", "auto", "heat_cool", "fan_only"}
    active = [s for s in states 
              if s["state"] in _on 
              and s["entity_id"].split(".")[0] in ("light","switch","fan","climate","cover","media_player")
              and "backlight" not in s["entity_id"]]
    by_domain = {}
    for s in active:
        d = s["entity_id"].split(".")[0]
        by_domain.setdefault(d, []).append(s)
    ICONS = {"light":"💡","switch":"🔌","fan":"🌬","climate":"❄️","cover":"🎪","media_player":"🎵"}
    NAMES = {"light":"أضواء","switch":"مفاتيح","fan":"شفاطات/منقيات","climate":"مكيفات","cover":"ستائر","media_player":"سماعات"}
    lines = [f"📱 {len(active)} جهاز شغال:"]
    for d in ["light","climate","cover","media_player","switch","fan"]:
        if d in by_domain:
            lines.append(f"  {ICONS[d]} {NAMES[d]}: {len(by_domain[d])}")
    return chr(10).join(lines)


# ═══════════════════════════════════════════════════
# MEDIA PLAYER: HA Service Calls + Handler
# ═══════════════════════════════════════════════════

async def _ha_call_service(domain, service, entity_id, data=None):
    """Call an HA service."""
    payload = {"entity_id": entity_id}
    if data:
        payload.update(data)
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{HA_URL}/api/services/{domain}/{service}",
                headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
                json=payload,
            )
            return r.status_code == 200
    except Exception as e:
        logger.error(f"HA service call {domain}/{service} error: {e}")
        return False


def _resolve_media_entity(t):
    """Resolve normalized text to a media_player entity_id. Returns entity_id or None."""
    # Try specific aliases first (longest match wins)
    best_alias = None
    best_len = 0
    for alias_norm, eid in _MEDIA_ALIASES_NORM.items():
        if alias_norm in t and len(alias_norm) > best_len:
            best_alias = eid
            best_len = len(alias_norm)
    if best_alias:
        return best_alias
    # Fall back to generic keywords
    for kw_norm, eid in _MP_GENERIC_NORM.items():
        if kw_norm in t:
            return eid
    return None


async def _handle_media_player(t):
    """Handle media_player speed engine queries. Returns response string or None."""
    # Resolve entity
    entity_id = _resolve_media_entity(t)
    if not entity_id:
        return None
    # Skip excluded entities
    if entity_id in _MP_EXCLUDED:
        return None

    attrs_cache = {}

    async def _get_entity_state():
        if attrs_cache:
            return attrs_cache.get("state"), attrs_cache.get("attrs", {})
        states = await _ha_states()
        for s in states:
            if s["entity_id"] == entity_id:
                attrs_cache["state"] = s["state"]
                attrs_cache["attrs"] = s.get("attributes", {})
                return s["state"], s.get("attributes", {})
        return "unavailable", {}

    friendly = None

    async def _get_friendly():
        nonlocal friendly
        if friendly:
            return friendly
        _, attrs = await _get_entity_state()
        friendly = attrs.get("friendly_name", entity_id.split(".")[-1])
        return friendly

    # ── STATUS patterns ──
    _status_pats = [
        r"شنو شغال على|شنو يشتغل على|شنو يعرض",
        r"هل .*(شغال|يشتغل|مشغل)",
        r"حاله (السبيكر|التلفزيون|سبيكر|تلفزيون)",
        r"what.*(playing|on)|is .*(on|playing)|status",
    ]
    if any(re.search(p, t) for p in _status_pats):
        state, attrs = await _get_entity_state()
        fname = await _get_friendly()
        if state in ("unavailable", "unknown"):
            return f"⚠️ {fname}: غير متاح"
        if state == "off":
            return f"📺 {fname}: مطفي"
        if state in ("idle", "standby"):
            return f"📺 {fname}: شغال بس ما يعرض شي"
        # Playing/paused — extract title
        title = attrs.get("media_title") or attrs.get("title") or attrs.get("app_name") or attrs.get("source") or ""
        artist = attrs.get("media_artist", "")
        vol = attrs.get("volume_level")
        vol_txt = f" | 🔊 {int(vol * 100)}%" if vol is not None else ""
        desc = f"{title}" + (f" — {artist}" if artist else "")
        state_ar = "يشغل" if state == "playing" else "متوقف مؤقتاً"
        return f"📺 {fname}: {state_ar}\n🎵 {desc}{vol_txt}"

    # ── POWER patterns ──
    if re.search(r"(طفي|اطفي|طف|اطف|turn off|off)\b", t):
        fname = await _get_friendly()
        ok = await _ha_call_service("media_player", "turn_off", entity_id)
        return f"✅ طفيت {fname}" if ok else f"❌ ما قدرت أطفي {fname}"

    if re.search(r"(شغل|شغلي|turn on|on)\b", t):
        # "شغل قرآن" / "شغل يوتيوب" → fall through to LLM
        if re.search(r"(قران|يوتيوب|نتفلكس|اذان|قناه|اغنيه|موسيقى|youtube|netflix|quran)", t):
            return None
        fname = await _get_friendly()
        ok = await _ha_call_service("media_player", "turn_on", entity_id)
        return f"✅ شغلت {fname}" if ok else f"❌ ما قدرت أشغل {fname}"

    # ── PLAYBACK patterns ──
    _target = entity_id
    # MA follower rerouting for playback
    if entity_id in _MA_FOLLOWERS:
        _target = _MA_LEADER

    if re.search(r"(وقف|وقفي|pause|ايقاف)\b", t):
        fname = await _get_friendly()
        ok = await _ha_call_service("media_player", "media_pause", _target)
        reroute_note = f" (عن طريق {_MA_LEADER.split('.')[-1]})" if _target != entity_id else ""
        return f"⏸ وقفت {fname}{reroute_note}" if ok else f"❌ ما قدرت أوقف {fname}"

    if re.search(r"(كمل|كملي|استمر|resume|play)\b", t):
        # "play quran" etc → LLM
        if re.search(r"(قران|يوتيوب|نتفلكس|اذان|قناه|اغنيه|موسيقى|youtube|netflix|quran)", t):
            return None
        fname = await _get_friendly()
        ok = await _ha_call_service("media_player", "media_play", _target)
        reroute_note = f" (عن طريق {_MA_LEADER.split('.')[-1]})" if _target != entity_id else ""
        return f"▶ كملت {fname}{reroute_note}" if ok else f"❌ ما قدرت أكمل {fname}"

    if re.search(r"(ستوب|stop)\b", t):
        fname = await _get_friendly()
        ok = await _ha_call_service("media_player", "media_stop", _target)
        return f"⏹ وقفت {fname}" if ok else f"❌ ما قدرت أوقف {fname}"

    # ── VOLUME patterns ── (stay on original entity, no reroute)
    # Volume set: "حط صوت ... على 25"
    _vol_match = re.search(r"(?:حط|خلي|سو|set).*(?:صوت|volume|vol).*?(\d{1,3})", t)
    if not _vol_match:
        _vol_match = re.search(r"(?:صوت|volume|vol).*?(\d{1,3})", t)
    if _vol_match:
        vol_val = int(_vol_match.group(1))
        # HA expects 0.0-1.0
        if vol_val > 1:
            vol_val = vol_val / 100.0
        vol_val = max(0.0, min(1.0, vol_val))
        fname = await _get_friendly()
        ok = await _ha_call_service("media_player", "volume_set", entity_id, {"volume_level": vol_val})
        return f"🔊 حطيت صوت {fname} على {int(vol_val * 100)}%" if ok else f"❌ ما قدرت أغير الصوت"

    if re.search(r"(ارفع|زد|رفع).*صوت|volume up", t):
        fname = await _get_friendly()
        ok = await _ha_call_service("media_player", "volume_up", entity_id)
        return f"🔊 رفعت صوت {fname}" if ok else f"❌ ما قدرت أرفع الصوت"

    if re.search(r"(خفض|نزل|وطي).*صوت|volume down", t):
        fname = await _get_friendly()
        ok = await _ha_call_service("media_player", "volume_down", entity_id)
        return f"🔉 خفضت صوت {fname}" if ok else f"❌ ما قدرت أخفض الصوت"

    if re.search(r"(اسكت|ميوت|mute|صامت)\b", t):
        fname = await _get_friendly()
        ok = await _ha_call_service("media_player", "volume_mute", entity_id, {"is_volume_muted": True})
        return f"🔇 سكّت {fname}" if ok else f"❌ ما قدرت أسكت {fname}"

    if re.search(r"(unmute|فك الميوت|فك الصامت|ارجع الصوت)\b", t):
        fname = await _get_friendly()
        ok = await _ha_call_service("media_player", "volume_mute", entity_id, {"is_volume_muted": False})
        return f"🔊 رجعت صوت {fname}" if ok else f"❌ ما قدرت أرجع الصوت"

    return None
