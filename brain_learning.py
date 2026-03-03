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
