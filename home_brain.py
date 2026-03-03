"""Home Brain — يفهم البيت من خلال مراقبة التغييرات.
كل 5 دقايق يسحب snapshot من HA ويقارن التغييرات.
كل ليلة يحلل ويبني فهم.
"""
import sqlite3, os, json, logging, httpx
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger("home_brain")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "home_brain.db")
HA_URL = os.environ.get("HA_URL", "http://localhost:8123")
HA_TOKEN = os.environ.get("HA_TOKEN", "")
TRACKED = {"light","switch","climate","cover","fan","media_player"}
SKIP = {"backlight","update.","sensor.","binary_sensor.","automation.","script."}
_last_snap = {}

def _db():
    cn = sqlite3.connect(DB_PATH); cn.row_factory = sqlite3.Row
    cn.execute("PRAGMA journal_mode=WAL")
    cn.execute("""CREATE TABLE IF NOT EXISTS state_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT DEFAULT (datetime('now','localtime')),
        entity_id TEXT, old_state TEXT, new_state TEXT,
        domain TEXT, hour INTEGER, day_of_week INTEGER,
        shift TEXT DEFAULT '', source TEXT DEFAULT 'ha')""")
    cn.execute("""CREATE TABLE IF NOT EXISTS daily_digest (
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT UNIQUE,
        total_changes INTEGER, summary TEXT, insights TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')))""")
    cn.execute("CREATE INDEX IF NOT EXISTS idx_sc_ts ON state_changes(ts)")
    cn.execute("CREATE INDEX IF NOT EXISTS idx_sc_eid ON state_changes(entity_id)")
    cn.commit(); return cn

def _ok(eid):
    d = eid.split(".")[0]
    return d in TRACKED and not any(s in eid for s in SKIP)

async def take_snapshot(shift=""):
    global _last_snap
    changes = []
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{HA_URL}/api/states", headers={"Authorization": f"Bearer {HA_TOKEN}"})
            if r.status_code != 200: return {"changes": 0, "error": "HA down"}
            states = r.json()
    except Exception as e: return {"changes": 0, "error": str(e)}
    now = datetime.now(); cur = {}
    for s in states:
        eid = s["entity_id"]
        if not _ok(eid): continue
        st = s["state"]; cur[eid] = st
        prev = _last_snap.get(eid)
        if prev and prev != st:
            changes.append({"eid": eid, "old": prev, "new": st,
                "domain": eid.split(".")[0], "hour": now.hour, "dow": now.weekday()})
    _last_snap = cur
    if changes:
        try:
            cn = _db()
            for c in changes:
                cn.execute("INSERT INTO state_changes (entity_id,old_state,new_state,domain,hour,day_of_week,shift) VALUES (?,?,?,?,?,?,?)",
                    (c["eid"],c["old"],c["new"],c["domain"],c["hour"],c["dow"],shift))
            cn.commit(); cn.close()
        except: pass
    return {"changes": len(changes), "tracked": len(cur)}

def get_daily_summary(date_str=None):
    if not date_str: date_str = datetime.now().strftime("%Y-%m-%d")
    try:
        cn = _db()
        total = cn.execute("SELECT COUNT(*) FROM state_changes WHERE date(ts)=?",(date_str,)).fetchone()[0]
        doms = cn.execute("SELECT domain,COUNT(*) as c FROM state_changes WHERE date(ts)=? GROUP BY domain ORDER BY c DESC",(date_str,)).fetchall()
        hrs = cn.execute("SELECT hour,COUNT(*) as c FROM state_changes WHERE date(ts)=? GROUP BY hour ORDER BY hour",(date_str,)).fetchall()
        top = cn.execute("SELECT entity_id,COUNT(*) as c FROM state_changes WHERE date(ts)=? GROUP BY entity_id ORDER BY c DESC LIMIT 10",(date_str,)).fetchall()
        cn.close()
        return {"date":date_str,"total":total,"by_domain":{r[0]:r[1] for r in doms},"by_hour":{r[0]:r[1] for r in hrs},"top":[(r[0],r[1]) for r in top]}
    except: return {"date":date_str,"total":0}

def detect_patterns(days=14, min_freq=5):
    try:
        cn = _db()
        rows = cn.execute("""SELECT entity_id,new_state,hour,shift,COUNT(DISTINCT date(ts)) as d,COUNT(*) as t,MAX(ts) as ls
            FROM state_changes WHERE ts>datetime('now',? || ' days','localtime')
            GROUP BY entity_id,new_state,hour HAVING d>=? ORDER BY d DESC,t DESC""",(f"-{days}",min_freq)).fetchall()
        cn.close()
        return [{"entity_id":r[0],"name":r[0].split(".")[-1].replace("_"," "),"action":r[1],"hour":r[2],"shift":r[3] or "","frequency":r[4],"total":r[5]} for r in rows]
    except: return []

def format_insights_ar(patterns):
    if not patterns: return "\u23f3 \u0644\u0633\u0627 \u0623\u062a\u0639\u0644\u0645... \u0627\u0633\u062a\u062e\u062f\u0645 \u0627\u0644\u0628\u0648\u062a \u0648\u0628\u0639\u062f \u0643\u0645 \u064a\u0648\u0645 \u0628\u0642\u062a\u0631\u062d \u0639\u0644\u064a\u0643"
    lines = ["\U0001f9e0 *\u0623\u0646\u0645\u0627\u0637 \u0644\u0627\u062d\u0638\u062a\u0647\u0627:*", ""]
    acts = {"on":"\u064a\u0634\u062a\u063a\u0644","off":"\u064a\u0637\u0641\u064a","heat":"\u062a\u062f\u0641\u0626\u0629","cool":"\u062a\u0628\u0631\u064a\u062f","open":"\u064a\u0641\u062a\u062d","closed":"\u064a\u0633\u0643\u0631"}
    for p in patterns[:8]:
        a = acts.get(p["action"], p["action"]); h = p["hour"]
        per = "\u0627\u0644\u0635\u0628\u062d" if 5<=h<12 else "\u0627\u0644\u0638\u0647\u0631" if 12<=h<17 else "\u0627\u0644\u0645\u0633\u0627" if 17<=h<22 else "\u0627\u0644\u0644\u064a\u0644"
        lines.append(f"\u2022 {p['name']} \u062f\u0627\u064a\u0645 {a} \u0627\u0644\u0633\u0627\u0639\u0629 {h:02d}:00 {per} ({p['frequency']} \u064a\u0648\u0645 \u0645\u0646 14)")
    return chr(10).join(lines)

def build_digest_prompt(summary):
    if not summary.get("total", 0): return ""
    p = [f"\u062a\u062d\u0644\u064a\u0644 \u0646\u0634\u0627\u0637 \u0627\u0644\u0628\u064a\u062a \u0644\u064a\u0648\u0645 {summary['date']}:", f"\u0625\u062c\u0645\u0627\u0644\u064a: {summary['total']}"]
    if summary.get("by_domain"):
        p.append("\u062d\u0633\u0628 \u0627\u0644\u0646\u0648\u0639: " + ", ".join(f"{d}={c}" for d,c in summary["by_domain"].items()))
    if summary.get("top"):
        p.append("\u0623\u0643\u062b\u0631 \u0627\u0644\u0623\u062c\u0647\u0632\u0629: " + ", ".join(f"{e.split('.')[-1].replace('_',' ')}({c})" for e,c in summary["top"][:5]))
    return chr(10).join(p)

def get_brain_stats():
    try:
        cn = _db()
        t = cn.execute("SELECT COUNT(*) FROM state_changes").fetchone()[0]
        td = cn.execute("SELECT COUNT(*) FROM state_changes WHERE date(ts)=date('now','localtime')").fetchone()[0]
        ds = cn.execute("SELECT COUNT(DISTINCT date(ts)) FROM state_changes").fetchone()[0]
        ps = len(detect_patterns(14,5))
        cn.close()
        return {"total":t,"today":td,"days":ds,"patterns":ps}
    except: return {"total":0,"today":0,"days":0,"patterns":0}
