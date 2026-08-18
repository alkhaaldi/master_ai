"""
priority_engine.py — Priority Engine + Assistant Surface Layer
Extracted from server.py v8.3.0
"""
import logging
import sqlite3
from datetime import datetime, timedelta

logger = logging.getLogger("priority_engine")

# ── Module-level reference for inbox cache ──
_inbox_cache_ref = None


def set_inbox_cache_ref(fn):
    """Set the module-level reference to the object that holds _inbox_cache."""
    global _inbox_cache_ref
    _inbox_cache_ref = fn


def _pe_minutes_since(time_str):
    """Parse time string, return minutes elapsed. Returns 9999 on failure."""
    if not time_str:
        return 9999
    try:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                t = datetime.strptime(time_str[:26], fmt)
                return max(0, int((datetime.now() - t).total_seconds() / 60))
            except ValueError:
                continue
        return 9999
    except Exception:
        return 9999


def _pe_get_extended_snapshot():
    """Quick DB reads for priority engine — no psutil/git."""
    from datetime import date as _d
    snap = {"tasks_list": [], "events_list": [], "anomalies_today": 0}
    try:
        with sqlite3.connect("data/life.db", timeout=3) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT id, title, priority, category, due_date, status FROM tasks WHERE status='todo' ORDER BY priority, due_date LIMIT 15").fetchall()
            snap["tasks_list"] = [dict(r) for r in rows]
            today_str = str(_d.today())
            tomorrow_str = str(_d.today() + timedelta(days=1))
            rows2 = conn.execute("SELECT summary, start_ts, end_ts, location FROM calendar_events WHERE (start_ts LIKE ? OR start_ts LIKE ?) AND status='confirmed' ORDER BY start_ts LIMIT 10", (today_str+"%", tomorrow_str+"%")).fetchall()
            snap["events_list"] = [dict(r) for r in rows2]
    except Exception as e:
        logger.debug("PE extended snapshot failed: %s", e)
    return snap


def _pe_get_radar_snapshot():
    """Get radar data for priority engine."""
    snap = {"radar_enabled": False, "radar_daily_context": [], "radar_recent_signals": [],
            "daily_context_stale": True, "radar_alerts_today": 0}
    try:
        from stock_radar import get_watchlist, get_recent_events, _get_config, get_daily_snapshot
        from tv_data import _is_market_open, KSE_STOCKS
        from datetime import date as _d
        cfg = _get_config()
        snap["radar_enabled"] = cfg.get("enabled", False)
        events = get_recent_events(10)
        today_str = str(_d.today())
        snap["radar_alerts_today"] = len([e for e in events if e.get("created_at", "")[:10] == today_str])
        enriched = []
        for e in events[:5]:
            sym = e.get("symbol", "")
            enriched.append({
                "symbol": sym, "name_ar": KSE_STOCKS.get(sym, sym),
                "type": e.get("signal_type", ""), "price": e.get("price", 0),
                "time": e.get("created_at", "")[:16], "score": e.get("score", 0),
                "score_class": e.get("score_class", ""), "verdict": e.get("verdict", ""),
                "strength": e.get("strength", ""), "rsi": e.get("rsi"),
            })
        snap["radar_recent_signals"] = enriched
        try:
            daily = get_daily_snapshot(top_n=10, min_score=0)
            snap["radar_daily_context"] = [{
                "symbol": d["symbol"], "name_ar": d.get("name_ar", d["symbol"]),
                "score": d.get("score", 0), "score_class": d.get("score_class", ""),
                "verdict": d.get("verdict", ""), "change_pct": d.get("change_pct", 0),
                "trend": d.get("trend", ""), "data_age_hours": d.get("data_age_hours", 999),
                "is_stale": d.get("is_stale", True),
            } for d in daily]
            snap["daily_context_stale"] = all(d.get("is_stale", True) for d in daily) if daily else True
        except Exception:
            pass
    except Exception:
        pass
    return snap


def _pe_extract_trading(dash, radar):
    """Extract trading priorities."""
    candidates = []
    now = datetime.now()
    ds = now.strftime("%Y%m%d")
    mo = dash.get("market_open", False)
    re_on = dash.get("radar_enabled", False) or radar.get("radar_enabled", False)

    if mo and not re_on:
        candidates.append({
            "id": f"trade_radar_off_{ds}", "domain": "trading", "type": "radar_disabled",
            "title": "الرادار متوقف أثناء السوق",
            "reason": "السوق مفتوح والرادار غير مفعّل",
            "why_now": "لا يمكن رصد الإشارات",
            "severity": "high", "priority_score": 75,
            "action_label": "شغّل الرادار",
            "action_target": "/master-ai/sub-radar", "status": "action_needed",
            "freshness_minutes": 0,
            "source": {"endpoint": "/dashboard", "field": "radar_enabled"},
            "meta": {"market_open": True}
        })

    if mo and re_on:
        for sig in radar.get("radar_recent_signals", [])[:3]:
            sc = sig.get("score", 0)
            if sc >= 70:
                candidates.append({
                    "id": f"trade_live_{sig.get('symbol','x')}_{ds}", "domain": "trading",
                    "type": "live_opportunity",
                    "title": f"فرصة تداول على {sig.get('symbol','')}",
                    "reason": sig.get("verdict", "إشارة قوية"),
                    "why_now": "السوق مفتوح والإشارة حية",
                    "severity": "high", "priority_score": min(92, 70 + sc // 5),
                    "action_label": "افتح التداول",
                    "action_target": "/master-ai/sub-radar", "status": "action_needed",
                    "freshness_minutes": _pe_minutes_since(sig.get("time")),
                    "source": {"endpoint": "/dashboard/radar", "field": "radar_recent_signals"},
                    "meta": {"symbol": sig.get("symbol",""), "score": sc, "strength": sig.get("strength","")}
                })
                break

    if not mo:
        daily = radar.get("radar_daily_context", [])
        best = [d for d in daily if d.get("score_class") == "A" and not d.get("is_stale", True)]
        if not best:
            best = [d for d in daily if d.get("score_class") == "A"]
        if best:
            top = best[0]
            candidates.append({
                "id": f"trade_daily_{top.get('symbol','x')}_{ds}", "domain": "trading",
                "type": "daily_candidate",
                "title": f"مرشح يومي: {top.get('symbol','')}",
                "reason": top.get("verdict", "تقييم عالي"),
                "why_now": "السوق مغلق — وقت المراجعة",
                "severity": "medium", "priority_score": min(70, 50 + top.get("score", 0) // 5),
                "action_label": "راجع التداول",
                "action_target": "/master-ai/sub-radar", "status": "watch",
                "freshness_minutes": round(top.get("data_age_hours", 0) * 60),
                "source": {"endpoint": "/dashboard/radar", "field": "radar_daily_context"},
                "meta": {"symbol": top.get("symbol",""), "score": top.get("score",0), "change_pct": top.get("change_pct",0)}
            })

    return candidates


def _pe_extract_calendar(dash, extended):
    """Extract calendar & task priorities."""
    candidates = []
    now = datetime.now()
    ds = now.strftime("%Y%m%d")

    evt_time_str = dash.get("next_event_time", "")
    evt_name = dash.get("next_event", "")
    # Filter out shift-calendar events (not real appointments)
    _shift_keywords = {'night', 'morning', 'afternoon', 'off', '1st', '2nd', '3rd', '4th'}
    _is_shift_event = evt_name and any(kw in evt_name.lower() for kw in _shift_keywords)
    if evt_time_str and evt_name and not _is_shift_event:
        try:
            evt_time = datetime.strptime(evt_time_str, "%Y-%m-%d %H:%M")
            minutes_until = (evt_time - now).total_seconds() / 60
            if 0 < minutes_until <= 180:
                if minutes_until <= 15:
                    sev, score = "critical", 95
                elif minutes_until <= 60:
                    sev, score = "high", 80
                else:
                    sev, score = "medium", 58
                mu = int(minutes_until)
                candidates.append({
                    "id": f"cal_evt_{ds}_{mu}", "domain": "calendar",
                    "type": "event_starting_soon" if minutes_until <= 60 else "upcoming_event",
                    "title": f"موعد خلال {mu} دقيقة" if minutes_until <= 60 else f"موعد قادم: {evt_name}",
                    "reason": f"الحدث: {evt_name}",
                    "why_now": f"يبدأ خلال {mu} دقيقة",
                    "severity": sev, "priority_score": score,
                    "action_label": "افتح المواعيد",
                    "action_target": "/master-ai/sub-calendar-tasks", "status": "action_needed",
                    "freshness_minutes": 0,
                    "source": {"endpoint": "/dashboard", "field": "next_event_time"},
                    "meta": {"event_name": evt_name, "minutes_until": mu}
                })
        except Exception:
            pass

    th = dash.get("tasks_high", 0)
    if th > 0:
        candidates.append({
            "id": f"task_high_{ds}", "domain": "tasks", "type": "high_task_load",
            "title": f"{th} مهمة عاجلة",
            "reason": "مهام ذات أولوية عالية تنتظر التنفيذ",
            "why_now": "لم تُنجز بعد",
            "severity": "high", "priority_score": 65 + min(10, th * 3),
            "action_label": "راجع المهام",
            "action_target": "/master-ai/sub-calendar-tasks", "status": "action_needed",
            "freshness_minutes": 0,
            "source": {"endpoint": "/dashboard", "field": "tasks_high"},
            "meta": {"count": th}
        })

    for task in extended.get("tasks_list", []):
        due = task.get("due_date", "")
        if due and due < str(now.date()):
            candidates.append({
                "id": f"task_overdue_{task.get('id','x')}", "domain": "tasks", "type": "overdue_task",
                "title": f"مهمة متأخرة: {task.get('title','?')[:30]}",
                "reason": f"كان موعدها {due}",
                "why_now": "تجاوزت الموعد",
                "severity": "high", "priority_score": 70,
                "action_label": "راجع المهمة",
                "action_target": "/master-ai/sub-calendar-tasks", "status": "action_needed",
                "freshness_minutes": 0,
                "source": {"endpoint": "/dashboard/extended", "field": "tasks_list"},
                "meta": {"task_id": task.get("id"), "due_date": due}
            })
            break

    shift = dash.get("shift_today", "")
    if shift:
        shift_name = shift.split()[0] if shift else ""
        shift_starts = {"صباحي": 6, "عصري": 14, "ليلي": 22}
        start_hour = shift_starts.get(shift_name)
        if start_hour is not None:
            shift_start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
            if shift_start < now:
                shift_start += timedelta(days=1)
            hours_until = (shift_start - now).total_seconds() / 3600
            if 0 < hours_until <= 4:
                hu = round(hours_until, 1)
                candidates.append({
                    "id": f"shift_{ds}", "domain": "calendar", "type": "shift_soon",
                    "title": f"شفت {shift_name} خلال {hu} ساعة",
                    "reason": f"الشفت القادم: {shift}",
                    "why_now": "وقت التحضير",
                    "severity": "medium", "priority_score": 55 + int((4 - hours_until) * 5),
                    "action_label": "راجع الشفت",
                    "action_target": "/master-ai/sub-calendar-tasks", "status": "info",
                    "freshness_minutes": 0,
                    "source": {"endpoint": "/dashboard", "field": "shift_today"},
                    "meta": {"shift": shift_name, "hours_until": hu}
                })

    return candidates


def _pe_extract_home(dash, extended):
    """Extract home priorities."""
    candidates = []
    now = datetime.now()
    ds = now.strftime("%Y%m%d")

    if dash.get("home_lights_on", 0) == -1:
        candidates.append({
            "id": f"home_ha_down_{ds}", "domain": "home", "type": "device_issue",
            "title": "اتصال البيت الذكي منقطع",
            "reason": "لا يمكن قراءة حالة الأجهزة",
            "why_now": "الاتصال مفقود حالياً",
            "severity": "high", "priority_score": 75,
            "action_label": "افتح النظام",
            "action_target": "/master-ai/sub-system-health", "status": "action_needed",
            "freshness_minutes": 0,
            "source": {"endpoint": "/dashboard", "field": "home_lights_on"},
            "meta": {}
        })

    anom = extended.get("anomalies_today", 0)
    if anom > 0:
        candidates.append({
            "id": f"home_anomaly_{ds}", "domain": "home", "type": "home_alert",
            "title": f"{anom} حالة غير طبيعية في البيت",
            "reason": "تم رصد شذوذ في حالة الأجهزة",
            "why_now": "حالة مستمرة",
            "severity": "medium", "priority_score": 65,
            "action_label": "افتح البيت",
            "action_target": "/master-ai/sub-home", "status": "watch",
            "freshness_minutes": 0,
            "source": {"endpoint": "/dashboard/extended", "field": "anomalies_today"},
            "meta": {"count": anom}
        })

    hour = now.hour
    lights = dash.get("home_lights_on", 0)
    if lights > 15 and (hour >= 23 or hour < 5):
        candidates.append({
            "id": f"home_lights_{ds}_{hour}", "domain": "home", "type": "lights_high",
            "title": f"{lights} نور مشتغل — وقت متأخر",
            "reason": "عدد كبير من الأنوار مشتغلة",
            "why_now": f"الساعة {hour}:00",
            "severity": "low", "priority_score": 42,
            "action_label": "افتح البيت",
            "action_target": "/master-ai/sub-home", "status": "watch",
            "freshness_minutes": 0,
            "source": {"endpoint": "/dashboard", "field": "home_lights_on"},
            "meta": {"lights_on": lights, "hour": hour}
        })

    return candidates


def _pe_extract_email(extended):
    """Extract email priorities."""
    candidates = []
    ds = datetime.now().strftime("%Y%m%d")

    crit = extended.get("email_critical", 0)
    if crit > 0:
        candidates.append({
            "id": f"email_crit_{ds}", "domain": "email", "type": "urgent_email",
            "title": f"{crit} رسالة حرجة غير مقروءة",
            "reason": "رسائل ذات أولوية حرجة",
            "why_now": "لم تُقرأ بعد",
            "severity": "high", "priority_score": 75 + min(10, crit * 3),
            "action_label": "افتح البريد",
            "action_target": "/master-ai/sub-email", "status": "action_needed",
            "freshness_minutes": 0,
            "source": {"endpoint": "/dashboard/extended", "field": "email_critical"},
            "meta": {"count": crit}
        })

    high = extended.get("email_high", 0)
    if high > 0:
        subj = ""
        for msg in extended.get("email_messages", []):
            if msg.get("_priority") == 3:
                subj = msg.get("subject", "")[:40]
                break
        candidates.append({
            "id": f"email_high_{ds}", "domain": "email", "type": "important_unread",
            "title": f"{high} رسالة مهمة غير مقروءة",
            "reason": subj or "رسائل ذات أولوية عالية",
            "why_now": "تنتظر المراجعة",
            "severity": "medium", "priority_score": 55 + min(15, high * 4),
            "action_label": "راجع البريد أو حوّله لمهمة",
            "action_target": "/master-ai/sub-email", "status": "action_needed",
            "freshness_minutes": 0,
            "source": {"endpoint": "/dashboard/extended", "field": "email_high"},
            "meta": {"count": high, "subject_hint": subj}
        })

    return candidates


def _pe_extract_system(dash, extended):
    """Extract system priorities."""
    candidates = []
    now = datetime.now()
    ds = now.strftime("%Y%m%d")

    dm = dash.get("degraded_mode", "normal")
    if dm not in ("normal", None):
        candidates.append({
            "id": f"sys_degraded_{ds}", "domain": "system", "type": "system_degraded",
            "title": f"النظام في وضع {dm}",
            "reason": "وضع التشغيل ليس طبيعياً",
            "why_now": "مستمر الآن",
            "severity": "critical", "priority_score": 90,
            "action_label": "افتح النظام",
            "action_target": "/master-ai/sub-system-health", "status": "action_needed",
            "freshness_minutes": 0,
            "source": {"endpoint": "/dashboard", "field": "degraded_mode"},
            "meta": {"mode": dm}
        })

    cpu = dash.get("cpu", 0)
    if cpu > 80:
        candidates.append({
            "id": f"sys_cpu_{ds}_{now.hour}", "domain": "system", "type": "cpu_high",
            "title": f"CPU عالي: {cpu}%",
            "reason": "الحمل على المعالج مرتفع",
            "why_now": f"القراءة الحالية {cpu}%",
            "severity": "high" if cpu > 90 else "medium",
            "priority_score": 60 + int((cpu - 80) * 0.75),
            "action_label": "افتح النظام",
            "action_target": "/master-ai/sub-system-health", "status": "watch",
            "freshness_minutes": 1,
            "source": {"endpoint": "/dashboard", "field": "cpu"},
            "meta": {"cpu_pct": cpu}
        })

    temp = dash.get("temperature", 0)
    if temp > 70:
        candidates.append({
            "id": f"sys_temp_{ds}_{now.hour}", "domain": "system", "type": "temperature_warning",
            "title": f"حرارة الجهاز: {temp}°C",
            "reason": "حرارة RPi مرتفعة",
            "why_now": f"القراءة الحالية {temp}°C",
            "severity": "high" if temp > 80 else "medium",
            "priority_score": 65 + int((temp - 70) * 1.5),
            "action_label": "افتح النظام",
            "action_target": "/master-ai/sub-system-health", "status": "watch",
            "freshness_minutes": 1,
            "source": {"endpoint": "/dashboard", "field": "temperature"},
            "meta": {"temperature": temp}
        })

    if extended.get("email_errors"):
        candidates.append({
            "id": f"sys_email_err_{ds}", "domain": "system", "type": "integration_problem",
            "title": "مشكلة في نظام البريد",
            "reason": str(extended["email_errors"][:1])[:80],
            "why_now": "أخطاء نشطة",
            "severity": "medium", "priority_score": 55,
            "action_label": "افتح النظام",
            "action_target": "/master-ai/sub-system-health", "status": "watch",
            "freshness_minutes": 0,
            "source": {"endpoint": "/dashboard/extended", "field": "email_errors"},
            "meta": {"errors": extended["email_errors"][:2]}
        })

    return candidates


def _pe_build_empty_state():
    """Fallback when no priorities found."""
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "stale": False,
        "empty_state": True,
        "summary_line": "لا توجد أولوية حرجة الآن",
        "top_priority": {
            "id": "stable", "domain": "system", "type": "stable_state",
            "title": "الوضع العام مستقر",
            "reason": "لا توجد تنبيهات حرجة",
            "why_now": "", "severity": "info", "priority_score": 15,
            "action_label": "افتح الرئيسية",
            "action_target": "/master-ai", "status": "info",
            "freshness_minutes": 0,
            "source": {"endpoint": "/dashboard", "field": "system"},
            "meta": {}
        },
        "priorities": []
    }


def _pe_make_summary(top):
    """Generate Arabic summary line from top priority."""
    title = top.get("title", "")
    if title:
        return f"أهم شي الحين: {title}"
    return "لا توجد أولوية حرجة الآن"


# ── Assistant Surface Layer (A1: Action Reframing) ─────────
_ACTION_TEMPLATES = {
    "live_opportunity": {
        "verb": "\u0631\u0627\u062c\u0639",
        "headline": "\u0631\u0627\u062c\u0639 \u0634\u0627\u0631\u062a {symbol}",
        "why_now": "\u0627\u0644\u0625\u0634\u0627\u0631\u0629 \u0638\u0647\u0631\u062a {age} \u0648\u0627\u0644\u0633\u0648\u0642 {market_status}",
        "consequence": "\u0625\u0630\u0627 \u062a\u062c\u0627\u0647\u0644\u062a\u0647\u0627 \u0642\u062f \u062a\u0646\u062a\u0647\u064a \u0635\u0644\u0627\u062d\u064a\u0629 \u0627\u0644\u0641\u0631\u0635\u0629 \u0645\u0639 \u0627\u0644\u0625\u063a\u0644\u0627\u0642",
        "primary_label": "\u0627\u0641\u062a\u062d \u0627\u0644\u062a\u062f\u0627\u0648\u0644",
        "primary_target": "/master-ai/sub-radar",
        "recommendation": "فرصة حية الآن. تأكد من حجم التداول والمقاومة قبل الدخول.",
    },
    "daily_candidate": {
        "verb": "\u0627\u0641\u062d\u0635",
        "headline": "\u0627\u0641\u062d\u0635 {symbol}",
        "why_now": "\u0645\u0631\u0634\u062d \u064a\u0648\u0645\u064a \u0638\u0627\u0647\u0631 \u0627\u0644\u0622\u0646 \u0648\u064a\u062d\u062a\u0627\u062c \u062a\u0623\u0643\u064a\u062f",
        "consequence": "\u0642\u062f \u062a\u0641\u0642\u062f \u0627\u0644\u062a\u0648\u0642\u064a\u062a \u0627\u0644\u0623\u0641\u0636\u0644 \u0625\u0630\u0627 \u062a\u0623\u062e\u0631 \u0627\u0644\u062a\u062d\u0642\u0642",
        "primary_label": "\u0627\u0641\u062a\u062d \u0627\u0644\u062a\u062f\u0627\u0648\u0644",
        "primary_target": "/master-ai/sub-radar",
        "recommendation": "السهم عنده إشارة يومية إيجابية. راجع الشارت وحدد نقطة الدخول قبل افتتاح السوق.",
    },
    "radar_disabled": {
        "verb": "\u0634\u063a\u0651\u0644",
        "headline": "\u0634\u063a\u0651\u0644 \u0627\u0644\u0631\u0627\u062f\u0627\u0631",
        "why_now": "\u0627\u0644\u0633\u0648\u0642 \u0645\u0641\u062a\u0648\u062d \u0648\u0627\u0644\u0631\u0627\u062f\u0627\u0631 \u0645\u0637\u0641\u064a",
        "consequence": "\u0644\u0646 \u062a\u0635\u0644\u0643 \u0625\u0634\u0627\u0631\u0627\u062a \u0627\u0644\u062a\u062f\u0627\u0648\u0644",
        "primary_label": "\u0634\u063a\u0651\u0644 \u0627\u0644\u0631\u0627\u062f\u0627\u0631",
        "primary_target": "/master-ai/sub-radar",
        "recommendation": "فعّل الرادار عشان ما تفوتك فرص.",
    },
    "event_starting_soon": {
        "verb": "\u0627\u0633\u062a\u0639\u062f \u0644\u0640",
        "headline": "\u0627\u0633\u062a\u0639\u062f \u0644\u0640 {event_name}",
        "why_now": "\u0627\u0644\u0645\u0648\u0639\u062f \u064a\u0628\u062f\u0623 \u062e\u0644\u0627\u0644 {minutes} \u062f\u0642\u064a\u0642\u0629",
        "consequence": "\u0642\u062f \u064a\u0641\u0648\u062a\u0643 \u0627\u0644\u0645\u0648\u0639\u062f \u0623\u0648 \u062a\u062f\u062e\u0644 \u0645\u062a\u0623\u062e\u0631\u0627\u064b",
        "primary_label": "\u0627\u0641\u062a\u062d \u0627\u0644\u0645\u0648\u0627\u0639\u064a\u062f",
        "primary_target": "/master-ai/sub-calendar-tasks",
        "recommendation": "جهّز {event_name} — باقي {minutes} دقيقة.",
    },
    "upcoming_event": {
        "verb": "\u062a\u0630\u0643\u0651\u0631",
        "headline": "\u0645\u0648\u0639\u062f \u0642\u0627\u062f\u0645: {event_name}",
        "why_now": "\u062e\u0644\u0627\u0644 {minutes} \u062f\u0642\u064a\u0642\u0629",
        "consequence": "",
        "primary_label": "\u0627\u0641\u062a\u062d \u0627\u0644\u0645\u0648\u0627\u0639\u064a\u062f",
        "primary_target": "/master-ai/sub-calendar-tasks",
        "recommendation": "شيك التفاصيل وحضّر اللي تحتاجه مقدماً.",
    },
    "shift_soon": {
        "verb": "\u0627\u0633\u062a\u0639\u062f \u0644\u0640",
        "headline": "\u0627\u0633\u062a\u0639\u062f \u0644\u0644\u0634\u0641\u062a \u0627\u0644{shift}",
        "why_now": "\u064a\u0628\u062f\u0623 \u062e\u0644\u0627\u0644 {hours} \u0633\u0627\u0639\u0629",
        "consequence": "",
        "primary_label": "\u0627\u0641\u062a\u062d \u0627\u0644\u062c\u062f\u0648\u0644",
        "primary_target": "/master-ai/sub-calendar-tasks",
        "recommendation": "حضّر أغراضك للشفت وشيك الجدول.",
    },
    "high_task_load": {
        "verb": "\u0623\u0646\u062c\u0632",
        "headline": "\u0639\u0646\u062f\u0643 {count} \u0645\u0647\u0627\u0645 \u0639\u0627\u062c\u0644\u0629",
        "why_now": "\u0645\u0647\u0627\u0645 \u0639\u0627\u0644\u064a\u0629 \u0627\u0644\u0623\u0648\u0644\u0648\u064a\u0629 \u062a\u0646\u062a\u0638\u0631",
        "consequence": "\u0643\u0644 \u0645\u0627 \u062a\u0623\u062e\u0631\u062a \u0632\u0627\u062f \u0627\u0644\u062a\u0631\u0627\u0643\u0645",
        "primary_label": "\u0627\u0641\u062a\u062d \u0627\u0644\u0645\u0647\u0627\u0645",
        "primary_target": "/master-ai/sub-calendar-tasks",
        "recommendation": "عندك مهام كثيرة اليوم — رتّب الأولويات وابدأ بالأهم.",
    },
    "overdue_task": {
        "verb": "\u0623\u0646\u062c\u0632",
        "headline": "\u0645\u0647\u0645\u0629 \u0645\u062a\u0623\u062e\u0631\u0629: {title}",
        "why_now": "\u062a\u062c\u0627\u0648\u0632\u062a \u0627\u0644\u0645\u0648\u0639\u062f \u0627\u0644\u0645\u062d\u062f\u062f",
        "consequence": "\u0627\u0644\u062a\u0623\u062e\u064a\u0631 \u064a\u0632\u064a\u062f",
        "primary_label": "\u0627\u0641\u062a\u062d \u0627\u0644\u0645\u0647\u0627\u0645",
        "primary_target": "/master-ai/sub-calendar-tasks",
        "recommendation": "هالمهمة متأخرة — إما أنجزها الحين أو عدّل الموعد.",
    },
    "urgent_email": {
        "verb": "\u0631\u0627\u062c\u0639",
        "headline": "\u0631\u0627\u062c\u0639 \u0628\u0631\u064a\u062f \u0639\u0627\u062c\u0644 ({count})",
        "why_now": "\u0631\u0633\u0627\u0626\u0644 \u062a\u062d\u062a\u0627\u062c \u0627\u0646\u062a\u0628\u0627\u0647\u0627\u064b \u0641\u0648\u0631\u064a\u0627\u064b",
        "consequence": "\u0642\u062f \u064a\u062a\u0623\u062e\u0631 \u0627\u0644\u0631\u062f \u0639\u0644\u0649 \u0623\u0645\u0631 \u0645\u0647\u0645",
        "primary_label": "\u0627\u0641\u062a\u062d \u0627\u0644\u0628\u0631\u064a\u062f",
        "primary_target": "/master-ai/sub-email",
        "recommendation": "رسالة عاجلة تحتاج رد سريع.",
    },
    "important_unread": {
        "verb": "\u0631\u0627\u062c\u0639",
        "headline": "\u0631\u0627\u062c\u0639 {count} \u0631\u0633\u0627\u0626\u0644 \u0645\u0647\u0645\u0629",
        "why_now": "\u0631\u0633\u0627\u0626\u0644 \u0628\u0627\u0646\u062a\u0638\u0627\u0631 \u0627\u0644\u0645\u0631\u0627\u062c\u0639\u0629",
        "consequence": "",
        "primary_label": "\u0627\u0641\u062a\u062d \u0627\u0644\u0628\u0631\u064a\u062f",
        "primary_target": "/master-ai/sub-email",
        "recommendation": "رسائل مهمة ما قريتها — خذ لها 5 دقايق.",
    },
    "lights_high": {
        "verb": "\u062a\u062d\u0642\u0642 \u0645\u0646",
        "headline": "\u062a\u062d\u0642\u0642 \u0645\u0646 \u0627\u0644\u0623\u0646\u0648\u0627\u0631 ({count} \u0645\u0634\u062a\u063a\u0644\u0629)",
        "why_now": "\u0639\u062f\u062f \u063a\u064a\u0631 \u0637\u0628\u064a\u0639\u064a \u0641\u064a \u0647\u0630\u0627 \u0627\u0644\u0648\u0642\u062a",
        "consequence": "\u0642\u062f \u062a\u0633\u062a\u0645\u0631 \u0627\u0644\u0645\u0634\u0643\u0644\u0629 \u062f\u0648\u0646 \u0645\u0639\u0627\u0644\u062c\u0629",
        "primary_label": "\u0627\u0641\u062a\u062d \u0627\u0644\u0628\u064a\u062a",
        "primary_target": "/master-ai/sub-home",
        "recommendation": "أنوار كثيرة مولعة — طفّ اللي ما تحتاجه.",
    },
    "system_degraded": {
        "verb": "\u0631\u0627\u062c\u0639",
        "headline": "\u0631\u0627\u062c\u0639 \u062d\u0627\u0644\u0629 \u0627\u0644\u0646\u0638\u0627\u0645",
        "why_now": "\u0628\u0639\u0636 \u0627\u0644\u0645\u0643\u0648\u0646\u0627\u062a \u0644\u0627 \u062a\u0639\u0645\u0644 \u0628\u0634\u0643\u0644 \u0635\u062d\u064a\u062d",
        "consequence": "\u0642\u062f \u062a\u0639\u062a\u0645\u062f \u0639\u0644\u0649 \u062d\u0627\u0644\u0629 \u063a\u064a\u0631 \u0645\u062d\u062f\u062b\u0629",
        "primary_label": "\u0627\u0641\u062a\u062d \u0627\u0644\u0646\u0638\u0627\u0645",
        "primary_target": "/master-ai/sub-system-health",
        "recommendation": "النظام فيه مشكلة — شيك الحالة وسوي restart إذا لزم.",
    },
}


def _as_format_age(minutes):
    """Format minutes into Arabic age phrase."""
    if minutes < 1:
        return "\u0627\u0644\u0622\u0646"
    if minutes < 60:
        return f"\u0642\u0628\u0644 {int(minutes)} \u062f\u0642\u064a\u0642\u0629"
    hours = minutes / 60
    if hours < 24:
        return f"\u0642\u0628\u0644 {round(hours, 1)} \u0633\u0627\u0639\u0629"
    return f"\u0642\u0628\u0644 {int(hours / 24)} \u064a\u0648\u0645"


def _as_reframe_priority(priority, dash_context):
    """Convert a PE priority into an assistant action."""
    ptype = priority.get("type", "")
    meta = priority.get("meta", {})
    template = _ACTION_TEMPLATES.get(ptype)

    if not template:
        # Fallback: use PE data as-is with generic framing
        return {
            "headline": priority.get("title", ""),
            "why_now": priority.get("reason", ""),
            "consequence": "",
            "recommendation": "",
            "urgency": priority.get("severity", "info"),
            "confidence": "moderate",
            "domain": priority.get("domain", "system"),
            "primary_action": {"label": priority.get("action_label", ""), "target": priority.get("action_target", "")},
            "secondary_action": None,
            "source_priority_id": priority.get("id", ""),
        }

    # Build headline from template + meta
    headline = template["headline"]
    try:
        headline = headline.format(
            symbol=meta.get("symbol", ""),
            event_name=meta.get("event_name", ""),
            minutes=meta.get("minutes_until", ""),
            hours=meta.get("hours_until", ""),
            shift=meta.get("shift", ""),
            count=meta.get("count", meta.get("lights_on", "")),
            title=meta.get("title", priority.get("title", "")[:30]),
        )
    except (KeyError, IndexError):
        headline = priority.get("title", "")

    # Build why_now
    why_now = template["why_now"]
    try:
        age_min = priority.get("freshness_minutes", 0)
        market_open = dash_context.get("market_open", False)
        why_now = why_now.format(
            age=_as_format_age(age_min),
            market_status="\u0645\u0641\u062a\u0648\u062d" if market_open else "\u0645\u063a\u0644\u0642",
            minutes=meta.get("minutes_until", ""),
            hours=meta.get("hours_until", ""),
            count=meta.get("count", ""),
            shift=meta.get("shift", ""),
        )
    except (KeyError, IndexError):
        why_now = priority.get("reason", "")

    # Determine confidence from score
    score = priority.get("priority_score", 50)
    if score >= 80:
        confidence = "strong"
    elif score >= 55:
        confidence = "moderate"
    else:
        confidence = "tentative"

    # Build recommendation from template + meta
    rec = template.get("recommendation", "")
    try:
        rec = rec.format(
            symbol=meta.get("symbol", ""),
            event_name=meta.get("event_name", ""),
            minutes=meta.get("minutes_until", ""),
            hours=meta.get("hours_until", ""),
            shift=meta.get("shift", ""),
            count=meta.get("count", meta.get("lights_on", "")),
            title=meta.get("title", priority.get("title", "")[:30]),
        )
    except (KeyError, IndexError):
        pass

    return {
        "headline": headline,
        "why_now": why_now,
        "consequence": template.get("consequence", ""),
        "recommendation": rec,
        "urgency": priority.get("severity", "info"),
        "confidence": confidence,
        "domain": priority.get("domain", ""),
        "primary_action": {"label": template["primary_label"], "target": template["primary_target"]},
        "secondary_action": {"label": "\u062a\u062c\u0627\u0647\u0644", "type": "dismiss"},
        "source_priority_id": priority.get("id", ""),
    }


# ── A2-v1: Temporal Intelligence ─────────────────────────────────────

def _as_compute_temporal_context(dash_data):
    """Compute current temporal context for action timing."""
    from datetime import datetime, timedelta
    now = datetime.now()
    hour = now.hour
    market_open = (dash_data or {}).get("market_open", False)
    if 5 <= hour < 8:
        time_mode = "morning"
    elif 9 <= hour < 14 and market_open:
        time_mode = "market"
    elif 22 <= hour or hour < 5:
        time_mode = "night"
    elif 17 <= hour < 22:
        time_mode = "evening"
    else:
        time_mode = "day"
    shift_str = (dash_data or {}).get("shift_today", "")
    shift_name = shift_str.split()[0] if shift_str else ""
    shift_hours = {"صباحي": 6, "عصري": 14, "ليلي": 22}
    shift_start_hour = shift_hours.get(shift_name)
    hours_to_shift = None
    if shift_start_hour is not None:
        shift_time = now.replace(hour=shift_start_hour, minute=0, second=0)
        if shift_time < now:
            shift_time += timedelta(days=1)
        hours_to_shift = (shift_time - now).total_seconds() / 3600
    return {
        "time_mode": time_mode, "hour": hour, "market_open": market_open,
        "hours_to_shift": round(hours_to_shift, 1) if hours_to_shift is not None else None,
    }


_TEMPORAL_WEIGHTS = {
    "morning":  {"trading": 0.6, "calendar": 1.5, "email": 1.2, "tasks": 1.0, "home": 0.5, "system": 0.5},
    "market":   {"trading": 1.8, "calendar": 1.0, "email": 0.7, "tasks": 0.5, "home": 0.3, "system": 0.3},
    "day":      {"trading": 0.5, "calendar": 1.2, "email": 1.0, "tasks": 1.0, "home": 0.8, "system": 0.5},
    "evening":  {"trading": 0.4, "calendar": 1.0, "email": 0.8, "tasks": 1.2, "home": 1.0, "system": 0.5},
    "night":    {"trading": 0.1, "calendar": 0.3, "email": 0.2, "tasks": 0.3, "home": 1.5, "system": 1.0},
}


def _as_apply_temporal_weight(priority, temporal_ctx):
    """Apply temporal multiplier. Returns (weighted_score, time_bucket, deadline_min, delay_cost).
    A2 deepened: lower thresholds, gentler staleness, smart passive handling."""
    domain = priority.get("domain", "system")
    ptype = priority.get("type", "")
    score = priority.get("priority_score", 50)
    sev = priority.get("severity", "info")
    meta = priority.get("meta", {})
    freshness = priority.get("freshness_minutes", 0)
    time_mode = temporal_ctx.get("time_mode", "day")

    # Critical always bypasses
    if sev == "critical":
        return (score * 10, "now", 0, "عاجل جداً — لا يمكن التأخير")

    weights = _TEMPORAL_WEIGHTS.get(time_mode, _TEMPORAL_WEIGHTS["day"])
    domain_w = weights.get(domain, 1.0)

    # Deadline detection
    deadline_min = None
    if meta.get("minutes_until"):
        deadline_min = int(meta["minutes_until"])
    elif meta.get("hours_until"):
        deadline_min = int(float(meta["hours_until"]) * 60)

    # Deadline boost
    deadline_boost = 0
    if deadline_min is not None:
        if deadline_min <= 15:
            deadline_boost = 300
        elif deadline_min <= 60:
            deadline_boost = 150
        elif deadline_min <= 120:
            deadline_boost = 50

    # A2d: Gentler staleness (3% per hour instead of 5%, min 0.5 instead of 0.3)
    stale_penalty = max(0.5, 1.0 - (freshness / 60) * 0.03) if freshness > 0 else 1.0

    # Market boosts
    market_boost = 0
    if temporal_ctx.get("market_open"):
        if ptype == "live_opportunity":
            market_boost = 100
        elif ptype == "daily_candidate":
            market_boost = 30

    # Shift proximity boost
    shift_boost = 0
    h2s = temporal_ctx.get("hours_to_shift")
    if h2s is not None and h2s <= 2 and domain in ("calendar", "tasks"):
        shift_boost = 80

    weighted = (score * domain_w * stale_penalty) + deadline_boost + market_boost + shift_boost

    # --- A2d: Smart bucket assignment ---
    if deadline_min is not None and deadline_min <= 15:
        bucket = "now"
    elif deadline_min is not None and deadline_min <= 60:
        bucket = "soon"
    elif sev == "high" or weighted > 70:
        bucket = "soon"
    elif weighted > 25:
        bucket = "later_today"
    # A2d: Force daily_candidate and email to at least later_today (never fully disappear)
    elif ptype in ("daily_candidate", "live_opportunity"):
        bucket = "later_today"
        weighted = max(weighted, 26)
    elif domain == "email" and score >= 50:
        bucket = "later_today"
        weighted = max(weighted, 26)
    else:
        bucket = "passive"

    # --- A2d: Context-aware delay_cost ---
    if bucket == "now":
        delay_cost = "لا يمكن التأخير"
    elif deadline_min is not None and deadline_min <= 60:
        delay_cost = f"ينتهي خلال {deadline_min} دقيقة"
    elif bucket == "soon":
        delay_cost = "الأفضل الآن"
    elif bucket == "later_today":
        if domain == "trading":
            if temporal_ctx.get("market_open"):
                delay_cost = "السوق مفتوح — راجعه قبل الإغلاق"
            else:
                delay_cost = "يمكن مراجعته قبل افتتاح السوق"
        elif domain == "email":
            delay_cost = "يمكن التعامل معها لاحقاً"
        else:
            delay_cost = "يمكن تأخيره لوقت لاحق"
    else:
        delay_cost = "يمكن تجاهله اليوم"

    return (weighted, bucket, deadline_min, delay_cost)


def build_assistant_surface(pe_result, dash_data=None):
    """Transform PE output into assistant-style action surface.
    A2-v1: Action Reframing + Temporal Intelligence."""
    dash_context = {"market_open": (dash_data or {}).get("market_open", False)}
    temporal_ctx = _as_compute_temporal_context(dash_data)
    priorities = pe_result.get("priorities", [])
    changes = pe_result.get("changes", {})
    is_empty = pe_result.get("empty_state", True)
    if is_empty or not priorities:
        return {
            "top_action": {
                "headline": "كل شيء تحت السيطرة",
                "why_now": "لا توجد عناصر عاجلة الآن",
                "consequence": "", "urgency": "none", "confidence": "strong",
                "domain": "system", "primary_action": None, "secondary_action": None,
                "source_priority_id": "quiet", "recommendation": "",
                "time_bucket": "passive", "deadline_minutes": None, "delay_cost": "",
            },
            "next_actions": [], "later_today": [],
            "changes": {"summary_natural": changes.get("summary", "")},
            "meta": {"quiet_mode": True, "generated_at": pe_result.get("generated_at", ""),
                     "time_mode": temporal_ctx.get("time_mode", "day")},
        }
    scored = []
    for p in priorities:
        tw, bucket, deadline, delay_cost = _as_apply_temporal_weight(p, temporal_ctx)
        scored.append((tw, bucket, deadline, delay_cost, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    top_items = []
    later_items = []
    for tw, bucket, deadline, delay_cost, p in scored:
        if bucket in ("now", "soon") and len(top_items) < 3:
            top_items.append((tw, bucket, deadline, delay_cost, p))
        elif bucket == "later_today" and len(later_items) < 3:
            later_items.append((tw, bucket, deadline, delay_cost, p))
        elif len(top_items) < 3:
            top_items.append((tw, bucket, deadline, delay_cost, p))
    # A2d: If no now/soon items, promote best later_today to top
    if not top_items and later_items:
        top_items.append(later_items.pop(0))
    if top_items:
        tw0, bucket0, deadline0, delay0, p0 = top_items[0]
        top_action = _as_reframe_priority(p0, dash_context)
        top_action["time_bucket"] = bucket0
        top_action["deadline_minutes"] = deadline0
        top_action["delay_cost"] = delay0
        top_action["temporal_weight"] = round(tw0, 1)
    else:
        top_action = _as_reframe_priority(priorities[0], dash_context)
        top_action["time_bucket"] = "later_today"
        top_action["deadline_minutes"] = None
        top_action["delay_cost"] = ""
        top_action["temporal_weight"] = 0
    next_actions = []
    for tw, bucket, deadline, delay_cost, p in top_items[1:]:
        if len(next_actions) >= 2:
            break
        reframed = _as_reframe_priority(p, dash_context)
        next_actions.append({
            "headline": reframed["headline"],
            "recommendation": reframed.get("recommendation", ""),
            "domain": reframed["domain"],
            "primary_action": reframed["primary_action"],
            "time_bucket": bucket,
            "delay_cost": delay_cost,
        })
    later_today = []
    for tw, bucket, deadline, delay_cost, p in later_items:
        reframed = _as_reframe_priority(p, dash_context)
        later_today.append({
            "headline": reframed["headline"],
            "recommendation": reframed.get("recommendation", ""),
            "domain": reframed["domain"],
            "delay_cost": delay_cost,
        })
    change_natural = ""
    if changes.get("has_changes"):
        new_ids = changes.get("new", [])
        resolved_ids = changes.get("resolved", [])
        parts = []
        if new_ids:
            for p in priorities:
                if p.get("id") in new_ids:
                    reframed = _as_reframe_priority(p, dash_context)
                    parts.append("جديد: " + reframed["headline"])
                    break
        if resolved_ids:
            parts.append(str(len(resolved_ids)) + " تم حلها")
        change_natural = " · ".join(parts)
    return {
        "top_action": top_action,
        "next_actions": next_actions,
        "later_today": later_today,
        "changes": {"summary_natural": change_natural},
        "meta": {"quiet_mode": False, "generated_at": pe_result.get("generated_at", ""),
                 "time_mode": temporal_ctx.get("time_mode", "day")},
    }

_pe_last_state = {"ids": set(), "severities": {}, "scores": {}, "timestamp": None, "cycle": 0}


def _pe_compute_changes(current_priorities):
    """Compare current priorities with last state. Returns changes dict."""
    global _pe_last_state
    cycle = _pe_last_state.get("cycle", 0)
    now_ids = {p.get("id", "") for p in current_priorities if p.get("id")}
    now_sev = {p["id"]: p.get("severity", "info") for p in current_priorities if p.get("id")}
    now_scores = {p["id"]: p.get("priority_score", 0) for p in current_priorities if p.get("id")}

    # Cold start grace: first 2 cycles after restart, just record state
    if cycle < 2:
        _pe_last_state = {"ids": now_ids, "severities": now_sev, "scores": now_scores,
                          "timestamp": datetime.utcnow().isoformat() + "Z", "cycle": cycle + 1}
        return {"has_changes": False, "new": [], "resolved": [], "escalated": [],
                "summary": "", "since": _pe_last_state["timestamp"]}
    prev_ids = _pe_last_state.get("ids", set())
    prev_sev = _pe_last_state.get("severities", {})

    new_ids = now_ids - prev_ids
    resolved_ids = prev_ids - now_ids

    sev_rank = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
    escalated = []
    for pid in now_ids & prev_ids:
        old_r = sev_rank.get(prev_sev.get(pid, "info"), 1)
        new_r = sev_rank.get(now_sev.get(pid, "info"), 1)
        if new_r > old_r:
            escalated.append(pid)

    parts = []
    if new_ids:
        for p in current_priorities:
            if p.get("id") in new_ids:
                parts.append("🆕 " + p.get("title", p.get("id", "")))
                break
    if resolved_ids:
        parts.append("✅ " + str(len(resolved_ids)) + " تم حلها")
    if escalated:
        parts.append("⚠ " + str(len(escalated)) + " ارتفعت")

    summary = " | ".join(parts) if parts else ""

    _pe_last_state = {
        "ids": now_ids,
        "severities": now_sev,
        "scores": now_scores,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "cycle": cycle + 1
    }

    return {
        "has_changes": bool(new_ids or resolved_ids or escalated),
        "new": list(new_ids),
        "resolved": list(resolved_ids),
        "escalated": escalated,
        "summary": summary,
        "since": _pe_last_state.get("timestamp", "")
    }


def build_priority_engine(dash_data, pe_extended=None, pe_radar=None):
    """Main priority engine orchestrator. Returns priority_engine dict."""
    try:
        if pe_extended is None:
            pe_extended = _pe_get_extended_snapshot()
        if pe_radar is None:
            pe_radar = _pe_get_radar_snapshot()

        candidates = []
        candidates += _pe_extract_trading(dash_data, pe_radar)
        candidates += _pe_extract_calendar(dash_data, pe_extended)
        candidates += _pe_extract_home(dash_data, pe_extended)
        candidates += _pe_extract_email(pe_extended)
        candidates += _pe_extract_system(dash_data, pe_extended)

        displayable = [c for c in candidates
                       if c.get("priority_score", 0) >= 35
                       or c.get("severity") in ("critical", "high")]

        sev_w = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
        displayable.sort(key=lambda x: (x.get("priority_score", 0) * 10 + sev_w.get(x.get("severity","info"), 0)), reverse=True)

        top3 = []
        dc = {}
        for item in displayable:
            d = item.get("domain", "")
            if dc.get(d, 0) < 2:
                top3.append(item)
                dc[d] = dc.get(d, 0) + 1
            if len(top3) >= 3:
                break

        if not top3:
            changes = _pe_compute_changes([])
            es = _pe_build_empty_state()
            es["changes"] = changes
            return es

        changes = _pe_compute_changes(top3)
        return {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "stale": False,
            "empty_state": False,
            "summary_line": _pe_make_summary(top3[0]),
            "top_priority": top3[0],
            "priorities": top3,
            "changes": changes
        }
    except Exception as e:
        logger.warning("build_priority_engine error: %s", e)
        return _pe_build_empty_state()
