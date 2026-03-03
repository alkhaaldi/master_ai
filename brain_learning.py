"""
brain_learning.py - Pattern Learning from HA History
Learns daily usage patterns for all tracked entities.
Stores patterns in brain_patterns.db for predictions and suggestions.

Usage:
    from brain_learning import learn_patterns, get_patterns, suggest_automations, format_patterns_report
    
    # Run nightly — analyzes last N days of history
    results = await learn_patterns(days=7)
    
    # Get patterns for specific entity
    patterns = get_patterns("light.parking_light_switch_1")
    
    # Get automation suggestions
    suggestions = await suggest_automations()
"""
import os, json, logging, sqlite3, httpx
from datetime import datetime, timedelta, timezone
from collections import defaultdict, Counter

logger = logging.getLogger("brain_learning")

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "data", "brain_patterns.db")
HA_URL = os.environ.get("HA_URL", "http://localhost:8123")
HA_TOKEN = os.environ.get("HA_TOKEN", "")

_KW_TZ = timezone(timedelta(hours=3))
TRACKED_DOMAINS = {"light", "climate", "cover", "fan", "media_player", "switch"}
SKIP_SUBS = {"backlight", "_curtain", "update.", "sensor.", "binary_sensor.",
             "automation.", "script.", "alexa_", "blaupunkt", "everywhere_",
             "none", "googletv"}  # skip known non-trackable


def _init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS device_patterns (
        entity_id TEXT,
        pattern_type TEXT,
        day_of_week INTEGER,
        hour INTEGER,
        value TEXT,
        confidence REAL,
        sample_count INTEGER,
        updated_at TEXT DEFAULT (datetime('now','localtime')),
        PRIMARY KEY (entity_id, pattern_type, day_of_week, hour)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS daily_summary (
        date TEXT,
        entity_id TEXT,
        on_count INTEGER DEFAULT 0,
        off_count INTEGER DEFAULT 0,
        total_on_seconds REAL DEFAULT 0,
        avg_temp REAL,
        temp_changes INTEGER DEFAULT 0,
        first_on TEXT,
        last_off TEXT,
        PRIMARY KEY (date, entity_id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS learning_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date TEXT DEFAULT (datetime('now','localtime')),
        days_analyzed INTEGER,
        entities_processed INTEGER,
        patterns_found INTEGER,
        duration_seconds REAL
    )""")
    conn.commit()
    return conn


def _headers():
    return {"Authorization": f"Bearer {HA_TOKEN}"}


def _should_track(entity_id):
    domain = entity_id.split(".")[0]
    if domain not in TRACKED_DOMAINS:
        return False
    for skip in SKIP_SUBS:
        if skip in entity_id:
            return False
    return True


async def _fetch_history(entity_id, start, end):
    """Fetch history from HA API."""
    url = f"{HA_URL}/api/history/period/{start.isoformat()}"
    params = {
        "filter_entity_id": entity_id,
        "end_time": end.isoformat(),
        "significant_changes_only": "true",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=_headers(), params=params)
            r.raise_for_status()
            data = r.json()
            if data and data[0]:
                return data[0]
    except Exception as e:
        logger.debug(f"History fetch {entity_id}: {e}")
    return []


def _analyze_light_pattern(history, date_str):
    """Analyze on/off patterns for a light/switch/fan entity."""
    on_times = []
    off_times = []
    on_start = None
    total_on = 0.0

    for entry in history:
        state = entry.get("state", "")
        ts_str = entry.get("last_changed", "")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone(_KW_TZ)
        except:
            continue
        
        if state == "on" and on_start is None:
            on_start = ts
            on_times.append(ts.hour)
        elif state != "on" and on_start is not None:
            dur = (ts - on_start).total_seconds()
            total_on += dur
            off_times.append(ts.hour)
            on_start = None
    
    return {
        "on_hours": on_times,
        "off_hours": off_times,
        "total_on_seconds": total_on,
        "on_count": len(on_times),
        "off_count": len(off_times),
        "first_on": min(on_times) if on_times else None,
        "last_off": max(off_times) if off_times else None,
    }


def _analyze_climate_pattern(history):
    """Analyze temperature patterns for climate entity."""
    temp_by_hour = defaultdict(list)
    changes = 0
    prev_temp = None

    for entry in history:
        attrs = entry.get("attributes", {})
        temp = attrs.get("temperature")
        ts_str = entry.get("last_changed", "")
        if not ts_str or not temp:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone(_KW_TZ)
        except:
            continue
        
        temp_by_hour[ts.hour].append(temp)
        if temp != prev_temp:
            changes += 1
            prev_temp = temp
    
    # Average temp per hour
    avg_by_hour = {}
    for h, temps in temp_by_hour.items():
        avg_by_hour[h] = round(sum(temps) / len(temps), 1)
    
    return {
        "avg_temp_by_hour": avg_by_hour,
        "temp_changes": changes,
        "all_temps": [t for temps in temp_by_hour.values() for t in temps],
    }


async def learn_patterns(days=7):
    """Main learning function — analyze last N days of HA history."""
    import time as _time
    t0 = _time.time()
    conn = _init_db()
    c = conn.cursor()
    
    now = datetime.now(timezone.utc)
    end = now
    start = now - timedelta(days=days)
    
    # Get all entities from HA
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{HA_URL}/api/states", headers=_headers())
            all_states = r.json()
    except Exception as e:
        logger.error(f"Cannot fetch HA states: {e}")
        return {"error": str(e)}
    
    entities = [s["entity_id"] for s in all_states if _should_track(s["entity_id"])]
    logger.info(f"Learning patterns for {len(entities)} entities over {days} days")
    
    patterns_found = 0
    
    for eid in entities:
        domain = eid.split(".")[0]
        history = await _fetch_history(eid, start, end)
        if not history or len(history) < 3:
            continue
        
        if domain in ("light", "switch", "fan"):
            # Group history by date
            by_date = defaultdict(list)
            for entry in history:
                ts_str = entry.get("last_changed", "")
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone(_KW_TZ)
                        by_date[ts.strftime("%Y-%m-%d")].append(entry)
                    except:
                        pass
            
            # Analyze each day
            hour_on_counts = Counter()
            hour_off_counts = Counter()
            total_days_active = 0
            
            for date_str, day_history in by_date.items():
                result = _analyze_light_pattern(day_history, date_str)
                if result["on_count"] > 0:
                    total_days_active += 1
                for h in result["on_hours"]:
                    hour_on_counts[h] += 1
                for h in result["off_hours"]:
                    hour_off_counts[h] += 1
                
                # Save daily summary
                dow = datetime.strptime(date_str, "%Y-%m-%d").weekday()
                c.execute("""INSERT OR REPLACE INTO daily_summary 
                    (date, entity_id, on_count, off_count, total_on_seconds, first_on, last_off)
                    VALUES (?,?,?,?,?,?,?)""",
                    (date_str, eid, result["on_count"], result["off_count"],
                     result["total_on_seconds"],
                     str(result["first_on"]) if result["first_on"] is not None else None,
                     str(result["last_off"]) if result["last_off"] is not None else None))
            
            # Build patterns: "usually turns on at hour X"
            total_days = max(len(by_date), 1)
            if total_days_active >= 2:
                for hour, count in hour_on_counts.items():
                    confidence = min(count / total_days, 1.0)
                    if confidence >= 0.3:  # at least 30% of days
                        c.execute("""INSERT OR REPLACE INTO device_patterns
                            (entity_id, pattern_type, day_of_week, hour, value, confidence, sample_count)
                            VALUES (?,?,?,?,?,?,?)""",
                            (eid, "on", -1, hour, "on", round(confidence, 2), count))
                        patterns_found += 1
                
                for hour, count in hour_off_counts.items():
                    confidence = min(count / total_days, 1.0)
                    if confidence >= 0.3:
                        c.execute("""INSERT OR REPLACE INTO device_patterns
                            (entity_id, pattern_type, day_of_week, hour, value, confidence, sample_count)
                            VALUES (?,?,?,?,?,?,?)""",
                            (eid, "off", -1, hour, "off", round(confidence, 2), count))
                        patterns_found += 1
        
        elif domain == "climate":
            result = _analyze_climate_pattern(history)
            if result["avg_temp_by_hour"]:
                for hour, avg_temp in result["avg_temp_by_hour"].items():
                    c.execute("""INSERT OR REPLACE INTO device_patterns
                        (entity_id, pattern_type, day_of_week, hour, value, confidence, sample_count)
                        VALUES (?,?,?,?,?,?,?)""",
                        (eid, "avg_temp", -1, hour, str(avg_temp), 1.0,
                         len(result["all_temps"])))
                    patterns_found += 1
    
    duration = _time.time() - t0
    c.execute("""INSERT INTO learning_runs (days_analyzed, entities_processed, patterns_found, duration_seconds)
        VALUES (?,?,?,?)""", (days, len(entities), patterns_found, round(duration, 1)))
    conn.commit()
    conn.close()
    
    result = {
        "entities_processed": len(entities),
        "patterns_found": patterns_found,
        "days_analyzed": days,
        "duration_seconds": round(duration, 1),
    }
    logger.info(f"Learning complete: {result}")
    return result


def get_patterns(entity_id=None):
    """Get learned patterns, optionally filtered by entity."""
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if entity_id:
        rows = c.execute(
            "SELECT * FROM device_patterns WHERE entity_id=? ORDER BY hour",
            (entity_id,)).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM device_patterns ORDER BY entity_id, hour").fetchall()
    conn.close()
    
    cols = ["entity_id", "pattern_type", "day_of_week", "hour", "value",
            "confidence", "sample_count", "updated_at"]
    return [dict(zip(cols, row)) for row in rows]


async def suggest_automations():
    """Analyze patterns and suggest automations."""
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    suggestions = []
    
    # Find consistent ON patterns (confidence >= 60%)
    rows = c.execute("""
        SELECT entity_id, hour, confidence, sample_count
        FROM device_patterns
        WHERE pattern_type='on' AND confidence >= 0.6
        ORDER BY confidence DESC
    """).fetchall()
    
    for eid, hour, conf, cnt in rows:
        suggestions.append({
            "type": "schedule_on",
            "entity_id": eid,
            "hour": hour,
            "confidence": conf,
            "sample_count": cnt,
            "suggestion_ar": f"\u0647\u0627\u0644\u062c\u0647\u0627\u0632 \u062f\u0627\u064a\u0645 \u064a\u0634\u062a\u063a\u0644 \u0627\u0644\u0633\u0627\u0639\u0629 {hour}:00 ({int(conf*100)}% \u062b\u0628\u0627\u062a) \u2014 \u062a\u0628\u064a \u0623\u062a\u0645\u062a\u0629\u061f",
        })
    
    # Find consistent OFF patterns
    rows = c.execute("""
        SELECT entity_id, hour, confidence, sample_count
        FROM device_patterns
        WHERE pattern_type='off' AND confidence >= 0.6
        ORDER BY confidence DESC
    """).fetchall()
    
    for eid, hour, conf, cnt in rows:
        suggestions.append({
            "type": "schedule_off",
            "entity_id": eid,
            "hour": hour,
            "confidence": conf,
            "sample_count": cnt,
            "suggestion_ar": f"\u0647\u0627\u0644\u062c\u0647\u0627\u0632 \u062f\u0627\u064a\u0645 \u064a\u0646\u0637\u0641\u064a \u0627\u0644\u0633\u0627\u0639\u0629 {hour}:00 ({int(conf*100)}% \u062b\u0628\u0627\u062a) \u2014 \u062a\u0628\u064a \u0623\u062a\u0645\u062a\u0629\u061f",
        })
    
    # Climate: consistent temp at certain hours
    rows = c.execute("""
        SELECT entity_id, hour, value, sample_count
        FROM device_patterns
        WHERE pattern_type='avg_temp'
        ORDER BY entity_id, hour
    """).fetchall()
    
    # Group by entity
    climate_by_eid = defaultdict(list)
    for eid, hour, val, cnt in rows:
        climate_by_eid[eid].append({"hour": hour, "temp": float(val)})
    
    for eid, hours_data in climate_by_eid.items():
        temps = [d["temp"] for d in hours_data]
        if len(set(temps)) > 1:
            night = [d for d in hours_data if d["hour"] in range(22, 24) or d["hour"] in range(0, 7)]
            day = [d for d in hours_data if d["hour"] in range(7, 22)]
            if night and day:
                avg_night = sum(d["temp"] for d in night) / len(night)
                avg_day = sum(d["temp"] for d in day) / len(day)
                if abs(avg_night - avg_day) >= 1.5:
                    suggestions.append({
                        "type": "climate_schedule",
                        "entity_id": eid,
                        "night_temp": round(avg_night, 1),
                        "day_temp": round(avg_day, 1),
                        "suggestion_ar": f"\u0647\u0627\u0644\u0645\u0643\u064a\u0641 \u0639\u0627\u062f\u0629 {avg_night:.0f}\u00b0 \u0628\u0627\u0644\u0644\u064a\u0644 \u0648 {avg_day:.0f}\u00b0 \u0628\u0627\u0644\u0646\u0647\u0627\u0631 \u2014 \u062a\u0628\u064a \u062c\u062f\u0648\u0644\u0629 \u062a\u0644\u0642\u0627\u0626\u064a\u0629\u061f",
                    })
    
    conn.close()
    return suggestions


async def format_patterns_report(entity_id=None):
    """Generate Arabic report of learned patterns."""
    patterns = get_patterns(entity_id)
    if not patterns:
        return "\u0644\u0627 \u062a\u0648\u062c\u062f \u0623\u0646\u0645\u0627\u0637 \u0645\u062a\u0639\u0644\u0645\u0629 \u0628\u0639\u062f \u2014 \u0634\u063a\u0651\u0644 learn_patterns \u0623\u0648\u0644"
    
    lines = ["\U0001f9e0 \u0627\u0644\u0623\u0646\u0645\u0627\u0637 \u0627\u0644\u0645\u062a\u0639\u0644\u0645\u0629:", ""]
    
    by_entity = defaultdict(list)
    for p in patterns:
        by_entity[p["entity_id"]].append(p)
    
    for eid, pats in by_entity.items():
        lines.append(f"\U0001f4cc {eid}:")
        on_hours = sorted([p["hour"] for p in pats if p["pattern_type"] == "on"])
        off_hours = sorted([p["hour"] for p in pats if p["pattern_type"] == "off"])
        temp_hours = {p["hour"]: p["value"] for p in pats if p["pattern_type"] == "avg_temp"}
        
        if on_hours:
            lines.append(f"  \u25b6 \u064a\u0634\u062a\u063a\u0644 \u0639\u0627\u062f\u0629: {', '.join(str(h)+':00' for h in on_hours)}")
        if off_hours:
            lines.append(f"  \u23f9 \u064a\u0646\u0637\u0641\u064a \u0639\u0627\u062f\u0629: {', '.join(str(h)+':00' for h in off_hours)}")
        if temp_hours:
            for h in sorted(temp_hours.keys()):
                lines.append(f"  \U0001f321 {h}:00 \u2192 {temp_hours[h]}\u00b0")
        lines.append("")
    
    return "\n".join(lines)


def get_learning_stats():
    """Get stats about learning runs."""
    if not os.path.exists(DB_PATH):
        return {"runs": 0, "patterns": 0}
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    runs = c.execute("SELECT COUNT(*) FROM learning_runs").fetchone()[0]
    patterns = c.execute("SELECT COUNT(*) FROM device_patterns").fetchone()[0]
    entities = c.execute("SELECT COUNT(DISTINCT entity_id) FROM device_patterns").fetchone()[0]
    last = c.execute("SELECT run_date, patterns_found, duration_seconds FROM learning_runs ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return {
        "runs": runs,
        "total_patterns": patterns,
        "entities_with_patterns": entities,
        "last_run": {"date": last[0], "patterns": last[1], "duration": last[2]} if last else None,
    }


def get_maturity_report():
    """Get brain learning maturity assessment."""
    if not os.path.exists(DB_PATH):
        return {"level": 0, "label": "لم يبدأ", "label_en": "not_started"}
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Stats
    runs = c.execute("SELECT COUNT(*) FROM learning_runs").fetchone()[0]
    total_patterns = c.execute("SELECT COUNT(*) FROM device_patterns").fetchone()[0]
    entities = c.execute("SELECT COUNT(DISTINCT entity_id) FROM device_patterns").fetchone()[0]
    
    # Confidence distribution
    high = c.execute("SELECT COUNT(*) FROM device_patterns WHERE confidence >= 0.8").fetchone()[0]
    medium = c.execute("SELECT COUNT(*) FROM device_patterns WHERE confidence >= 0.5 AND confidence < 0.8").fetchone()[0]
    low = c.execute("SELECT COUNT(*) FROM device_patterns WHERE confidence < 0.5").fetchone()[0]
    
    # Days of data
    days_data = c.execute("SELECT COUNT(DISTINCT date) FROM daily_summary").fetchone()[0]
    
    # Last run
    last = c.execute("SELECT run_date, days_analyzed FROM learning_runs ORDER BY id DESC LIMIT 1").fetchone()
    
    # Top suggestions (confidence >= 80%)
    top_sugs = c.execute("""
        SELECT entity_id, pattern_type, hour, confidence, sample_count
        FROM device_patterns WHERE confidence >= 0.8 AND pattern_type IN ('on','off')
        ORDER BY confidence DESC, sample_count DESC LIMIT 20
    """).fetchall()
    
    conn.close()
    
    # Calculate maturity level
    # Level 1: started (< 3 days data)
    # Level 2: learning (3-7 days, some patterns)
    # Level 3: confident (7-14 days, many high-confidence patterns)
    # Level 4: expert (14+ days, stable patterns)
    # Level 5: master (30+ days, very stable)
    
    if days_data < 3:
        level, label = 1, "مبتدئ"
        emoji = "\U0001f331"
        advice = "يحتاج أيام أكثر عشان يتعلم أنماطك — خله يجمع بيانات"
    elif days_data < 7:
        level, label = 2, "يتعلم"
        emoji = "\U0001f4d6"
        advice = "بدأ يشوف أنماط بس يحتاج أسبوع كامل عشان يثبت"
    elif days_data < 14:
        if high > 50:
            level, label = 3, "واثق"
            emoji = "\U0001f4aa"
            advice = "الأنماط القوية (80%+) تقدر تعتمد عليها"
        else:
            level, label = 2, "يتعلم"
            emoji = "\U0001f4d6"
            advice = "عنده بيانات بس الأنماط لسا ما ثبتت بالكامل"
    elif days_data < 30:
        level, label = 4, "خبير"
        emoji = "\U0001f393"
        advice = "أنماطه ثابتة — اقتراحاته موثوقة"
    else:
        level, label = 5, "متمكن"
        emoji = "\U0001f9e0"
        advice = "بيانات شهر+ — يعرف عاداتك بدقة عالية"
    
    # Trust meter
    if total_patterns == 0:
        trust_pct = 0
    else:
        trust_pct = round(high / total_patterns * 100)
    
    trust_bar_len = trust_pct // 5
    trust_bar = "\u2588" * trust_bar_len + "\u2591" * (20 - trust_bar_len)
    
    return {
        "level": level,
        "label": label,
        "emoji": emoji,
        "advice": advice,
        "runs": runs,
        "days_data": days_data,
        "total_patterns": total_patterns,
        "entities": entities,
        "high_confidence": high,
        "medium_confidence": medium,
        "low_confidence": low,
        "trust_pct": trust_pct,
        "trust_bar": trust_bar,
        "last_run": last[0][:16] if last else None,
        "top_suggestions": [
            {"entity_id": r[0], "type": r[1], "hour": r[2], "confidence": r[3], "samples": r[4]}
            for r in top_sugs
        ],
    }


def _get_friendly_name(entity_id):
    """Get Arabic friendly name from entity_map.json."""
    try:
        import json
        emap_path = os.path.join(BASE_DIR, "entity_map.json")
        if not os.path.exists(emap_path):
            return entity_id.split(".")[-1].replace("_", " ")
        with open(emap_path) as ef:
            emap = json.load(ef)
        for room, entries in emap.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if "=" in entry:
                    eid, ename = entry.split("=", 1)
                    if eid == entity_id:
                        return ename
        return entity_id.split(".")[-1].replace("_", " ")
    except Exception:
        return entity_id.split(".")[-1].replace("_", " ")


def format_maturity_report():
    """Telegram-ready maturity report."""
    m = get_maturity_report()
    if m["level"] == 0:
        return "\U0001f9e0 Brain Learning\n\nلم يبدأ التعلم بعد — استخدم /learn"
    
    lines = [
        f"{m['emoji']} Brain Learning — {m['label']} (مستوى {m['level']}/5)",
        "",
        f"\U0001f4ca البيانات:",
        f"  \U0001f4c5 {m['days_data']} يوم بيانات",
        f"  \U0001f504 {m['runs']} عملية تعلم",
        f"  \U0001f50d {m['total_patterns']} نمط من {m['entities']} جهاز",
        f"  \u23f0 آخر تعلم: {m['last_run'] or '—'}",
        "",
        f"\U0001f3af مقياس الثقة: {m['trust_pct']}%",
        f"  [{m['trust_bar']}]",
        f"  \U0001f7e2 قوي (80%+): {m['high_confidence']}",
        f"  \U0001f7e1 متوسط: {m['medium_confidence']}",
        f"  \U0001f534 مبكر: {m['low_confidence']}",
        "",
        f"\U0001f4ac {m['advice']}",
    ]
    
    if m["top_suggestions"]:
        lines.append("")
        lines.append("\U0001f4a1 أقوى الاقتراحات (تقدر تعتمد عليها):")
        seen = set()
        for s in m["top_suggestions"]:
            eid = s["entity_id"]
            if eid in seen:
                continue
            seen.add(eid)
            name = _get_friendly_name(eid)
            action = "يشتغل" if s["type"] == "on" else "ينطفي"
            lines.append(f"  \u2705 {name}: {action} الساعة {s['hour']}:00 ({int(s['confidence']*100)}% ثبات)")
            if len(seen) >= 8:
                break
    
    return "\n".join(lines)


async def detect_anomalies():
    """Compare today's behavior against learned patterns.
    Returns list of anomalies with severity and description."""
    if not os.path.exists(DB_PATH):
        return []
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Check if we have enough patterns
    pat_count = c.execute("SELECT COUNT(*) FROM device_patterns WHERE confidence >= 0.6").fetchone()[0]
    if pat_count < 10:
        conn.close()
        return []
    
    now = datetime.now(_KW_TZ)
    current_hour = now.hour
    today_str = now.strftime("%Y-%m-%d")
    
    anomalies = []
    
    # 1. Devices that usually turn ON by this hour but haven't
    on_patterns = c.execute("""
        SELECT entity_id, hour, confidence, sample_count
        FROM device_patterns
        WHERE pattern_type='on' AND confidence >= 0.7 AND hour <= ?
        ORDER BY entity_id, hour
    """, (current_hour,)).fetchall()
    
    # Group by entity — get the entities that should be on by now
    expected_on = {}
    for eid, hour, conf, samples in on_patterns:
        if eid not in expected_on or conf > expected_on[eid]["confidence"]:
            expected_on[eid] = {"hour": hour, "confidence": conf, "samples": samples}
    
    # Check if they actually turned on today
    today_summary = {}
    rows = c.execute("SELECT entity_id, on_count, first_on FROM daily_summary WHERE date=?", (today_str,)).fetchall()
    for eid, on_cnt, first_on in rows:
        today_summary[eid] = {"on_count": on_cnt, "first_on": first_on}
    
    for eid, pattern in expected_on.items():
        ts = today_summary.get(eid)
        if not ts or ts["on_count"] == 0:
            # Device didn't turn on but usually does
            name = _get_friendly_name(eid)
            anomalies.append({
                "type": "missing_on",
                "severity": "medium" if pattern["confidence"] >= 0.8 else "low",
                "entity_id": eid,
                "name": name,
                "expected_hour": pattern["hour"],
                "confidence": pattern["confidence"],
                "description_ar": f"{name} \u0639\u0627\u062f\u0629 \u064a\u0634\u062a\u063a\u0644 \u0627\u0644\u0633\u0627\u0639\u0629 {pattern['hour']}:00 \u0628\u0633 \u0627\u0644\u064a\u0648\u0645 \u0645\u0627 \u0627\u0634\u062a\u063a\u0644 ({int(pattern['confidence']*100)}% \u062b\u0628\u0627\u062a)",
            })
    
    # 2. Devices ON for unusually long time
    # Compare today's on_seconds vs historical average
    hist_avg = {}
    rows = c.execute("""
        SELECT entity_id, AVG(total_on_seconds) as avg_on, 
               MAX(total_on_seconds) as max_on,
               COUNT(*) as days
        FROM daily_summary 
        WHERE date != ? AND total_on_seconds > 0
        GROUP BY entity_id
        HAVING days >= 3
    """, (today_str,)).fetchall()
    for eid, avg_on, max_on, days in rows:
        hist_avg[eid] = {"avg": avg_on, "max": max_on, "days": days}
    
    for eid, ts in today_summary.items():
        if eid in hist_avg and ts["on_count"] > 0:
            hist = hist_avg[eid]
            today_on = ts.get("on_count", 0)
            # If today's on_count is 3x the average, flag it
            if hist["avg"] > 0:
                daily_avg_on = c.execute(
                    "SELECT AVG(on_count) FROM daily_summary WHERE entity_id=? AND date!=?",
                    (eid, today_str)).fetchone()[0]
                if daily_avg_on and daily_avg_on > 0 and today_on > daily_avg_on * 3:
                    name = _get_friendly_name(eid)
                    anomalies.append({
                        "type": "excessive_usage",
                        "severity": "medium",
                        "entity_id": eid,
                        "name": name,
                        "today_count": today_on,
                        "avg_count": round(daily_avg_on, 1),
                        "description_ar": f"{name} \u0627\u0634\u062a\u063a\u0644 {today_on} \u0645\u0631\u0629 \u0627\u0644\u064a\u0648\u0645 (\u0627\u0644\u0645\u0639\u062f\u0644 {daily_avg_on:.0f}) \u2014 \u0627\u0633\u062a\u062e\u062f\u0627\u0645 \u063a\u064a\u0631 \u0637\u0628\u064a\u0639\u064a",
                    })
    
    # 3. Climate anomalies — temp set way different than pattern
    climate_patterns = c.execute("""
        SELECT entity_id, hour, CAST(value AS REAL) as expected_temp
        FROM device_patterns
        WHERE pattern_type='avg_temp' AND hour=?
    """, (current_hour,)).fetchall()
    
    # Get current climate states from HA
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{HA_URL}/api/states", headers=_headers())
            all_states = {s["entity_id"]: s for s in r.json()}
    except:
        all_states = {}
    
    for eid, hour, expected_temp in climate_patterns:
        state = all_states.get(eid, {})
        attrs = state.get("attributes", {})
        current_temp = attrs.get("temperature")
        if current_temp and abs(current_temp - expected_temp) >= 3:
            name = _get_friendly_name(eid)
            anomalies.append({
                "type": "climate_deviation",
                "severity": "low",
                "entity_id": eid,
                "name": name,
                "current_temp": current_temp,
                "expected_temp": expected_temp,
                "description_ar": f"{name} \u0645\u0636\u0628\u0648\u0637 \u0639\u0644\u0649 {current_temp}\u00b0 \u0628\u0633 \u0639\u0627\u062f\u0629 \u064a\u0643\u0648\u0646 {expected_temp:.0f}\u00b0 \u0647\u0627\u0644\u0648\u0642\u062a",
            })
    
    conn.close()
    
    # Dedup: keep one anomaly per entity_id+type, prefer higher severity
    seen = set()
    deduped = []
    for a in anomalies:
        key = (a["entity_id"], a["type"])
        base_eid = a["entity_id"].split(".")[-1]
        base_key = (base_eid, a["type"])
        if key not in seen and base_key not in seen:
            seen.add(key)
            seen.add(base_key)
            deduped.append(a)
    anomalies = deduped
    
    # Sort by severity
    sev_order = {"high": 0, "medium": 1, "low": 2}
    anomalies.sort(key=lambda x: sev_order.get(x["severity"], 3))
    
    return anomalies


async def format_anomaly_report():
    """Generate Telegram-ready anomaly report."""
    anomalies = await detect_anomalies()
    if not anomalies:
        return "\u2705 \u0644\u0627 \u064a\u0648\u062c\u062f \u0634\u0630\u0648\u0630 \u0627\u0644\u064a\u0648\u0645 \u2014 \u0643\u0644 \u0634\u064a \u0637\u0628\u064a\u0639\u064a"
    
    sev_emoji = {"high": "\U0001f534", "medium": "\U0001f7e1", "low": "\U0001f7e2"}
    
    lines = [f"\U0001f50d \u0634\u0630\u0648\u0630 \u0627\u0644\u064a\u0648\u0645 ({len(anomalies)}):", ""]
    
    for a in anomalies[:15]:
        emoji = sev_emoji.get(a["severity"], "\u2753")
        lines.append(f"{emoji} {a['description_ar']}")
    
    if len(anomalies) > 15:
        lines.append(f"\n... \u0648 {len(anomalies)-15} \u0634\u0630\u0648\u0630 \u0622\u062e\u0631")
    
    return "\n".join(lines)
