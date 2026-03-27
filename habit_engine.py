"""
habit_engine.py — Habit Learning for Master AI (Phase 2 Week 7)
Uses: data/home_brain.db (state_changes + climate_log)
"""
import sqlite3, logging, os
from datetime import datetime
from collections import defaultdict
logger = logging.getLogger("habit_engine")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "home_brain.db")

def _get_db():
    if not os.path.exists(DB_PATH): return None
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn

def learn_lights_off_time():
    conn = _get_db()
    if not conn: return None
    try:
        rows = conn.execute("SELECT hour, COUNT(*) as c FROM state_changes WHERE domain='light' AND new_state='off' AND (hour>=20 OR hour<=3) GROUP BY hour ORDER BY c DESC LIMIT 3").fetchall()
        if rows:
            ph = rows[0]["hour"]
            tot = sum(r["c"] for r in rows)
            return {"habit":"lights_off","peak_hour":ph,"confidence":round(rows[0]["c"]/max(tot,1),2),"description":f"عادة تطفي الأنوار حوالي الساعة {ph}:00"}
    except Exception as e: logger.error(f"lights_off: {e}")
    finally: conn.close()
    return None

def learn_ac_patterns():
    conn = _get_db()
    if not conn: return []
    habits = []
    try:
        rows = conn.execute("SELECT entity_id, ROUND(AVG(target_temp),1) as avg_t, COUNT(*) as n, MIN(target_temp) as min_t, MAX(target_temp) as max_t FROM climate_log WHERE state!='off' AND target_temp>0 GROUP BY entity_id HAVING n>=5").fetchall()
        for r in rows:
            nm = r["entity_id"].split(".")[-1].replace("_"," ")
            habits.append({"habit":"ac_pattern","entity_id":r["entity_id"],"avg_temp":r["avg_t"],"range":f"{r['min_t']}-{r['max_t']}","samples":r["n"],"description":f"{nm}: معدل {r['avg_t']}°C (بين {r['min_t']}-{r['max_t']}°C)"})
    except Exception as e: logger.error(f"ac_patterns: {e}")
    finally: conn.close()
    return habits

def learn_morning_routine():
    conn = _get_db()
    if not conn: return None
    try:
        rows = conn.execute("SELECT entity_id,domain,new_state,COUNT(*) as c FROM state_changes WHERE hour>=6 AND hour<=9 GROUP BY entity_id,new_state HAVING c>=3 ORDER BY c DESC LIMIT 10").fetchall()
        if rows:
            acts = [{"entity":r["entity_id"],"action":r["new_state"],"count":r["c"],"desc":f"{r['entity_id'].split('.')[-1].replace('_',' ')} → {r['new_state']}"} for r in rows]
            return {"habit":"morning_routine","actions":acts[:5],"description":"روتين الصباح: "+", ".join(a["desc"] for a in acts[:3])}
    except Exception as e: logger.error(f"morning: {e}")
    finally: conn.close()
    return None

def learn_night_routine():
    conn = _get_db()
    if not conn: return None
    try:
        rows = conn.execute("SELECT entity_id,domain,new_state,COUNT(*) as c FROM state_changes WHERE hour>=22 OR hour=0 GROUP BY entity_id,new_state HAVING c>=3 ORDER BY c DESC LIMIT 10").fetchall()
        if rows:
            acts = [{"entity":r["entity_id"],"action":r["new_state"],"count":r["c"],"desc":f"{r['entity_id'].split('.')[-1].replace('_',' ')} → {r['new_state']}"} for r in rows]
            return {"habit":"night_routine","actions":acts[:5],"description":"روتين الليل: "+", ".join(a["desc"] for a in acts[:3])}
    except Exception as e: logger.error(f"night: {e}")
    finally: conn.close()
    return None

def learn_device_frequency():
    conn = _get_db()
    if not conn: return []
    habits = []
    try:
        rows = conn.execute("SELECT entity_id,domain,COUNT(*) as c,COUNT(DISTINCT date(ts)) as d FROM state_changes WHERE date(ts)>=date('now','-7 days','localtime') GROUP BY entity_id HAVING c>=5 ORDER BY c DESC LIMIT 15").fetchall()
        for r in rows:
            nm = r["entity_id"].split(".")[-1].replace("_"," ")
            avg = round(r["c"]/max(r["d"],1),1)
            habits.append({"habit":"device_frequency","entity_id":r["entity_id"],"domain":r["domain"],"total_changes":r["c"],"active_days":r["d"],"avg_per_day":avg,"description":f"{nm}: {avg}/يوم ({r['c']} تغيير بـ {r['d']} يوم)"})
    except Exception as e: logger.error(f"dev_freq: {e}")
    finally: conn.close()
    return habits

def get_suggestions():
    suggestions = []
    h = datetime.now().hour
    if h >= 23 or h < 1:
        lo = learn_lights_off_time()
        if lo and lo["peak_hour"] <= h:
            suggestions.append({"type":"lights_off","message":f"عادة تطفي الأنوار الساعة {lo['peak_hour']}. تبيني أطفي كل شي؟","action":"scene.tfwy_kl_shy","confidence":lo["confidence"]})
    if 6 <= h <= 8:
        mr = learn_morning_routine()
        if mr and mr["actions"]:
            fa = mr["actions"][0]
            suggestions.append({"type":"morning_routine","message":f"صباح الخير! عادة تبدأ بـ {fa['desc']}. تبيني أشغل روتين الصباح؟","action":"scene.sbh_lkhyr","confidence":0.6})
    return suggestions

def get_habit_report():
    report = {"generated_at":datetime.now().isoformat(),"habits":[]}
    lo = learn_lights_off_time()
    if lo: report["habits"].append(lo)
    report["habits"].extend(learn_ac_patterns())
    mr = learn_morning_routine()
    if mr: report["habits"].append(mr)
    nr = learn_night_routine()
    if nr: report["habits"].append(nr)
    report["habits"].extend(learn_device_frequency()[:5])
    report["suggestions"] = get_suggestions()
    return report

def format_habit_report():
    r = get_habit_report()
    if not r["habits"]: return "U0001f4ca ما فيه بيانات كافية للتعلم بعد"
    lines = [f"U0001f9e0 تحليل العادات ({len(r['habits'])} نمط):",""]
    for h in r["habits"]: lines.append(f"  • {h['description']}")
    if r["suggestions"]:
        lines.append("")
        lines.append("U0001f4a1 اقتراحات:")
        for s in r["suggestions"]: lines.append(f"  ➡ {s['message']}")
    return chr(10).join(lines)
