"""
anomaly_engine.py — Smart anomaly detection for Master AI
Phase 2 Week 6: Detects unusual patterns by comparing current behavior vs historical.

Uses: data/home_brain.db (state_changes + climate_log)
Integrates with: tg_alerts.py (sends proactive TG messages)

Anomaly types:
1. AC runtime anomaly — running longer than usual for this hour/day
2. Door/cover open too long
3. Baby room temperature out of range
4. Unusual device activity for time of day
5. Device went offline and didn't recover
"""

import sqlite3
import logging
import os
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger("anomaly_engine")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "home_brain.db")

# ═══ CONFIG ═══
BABY_ROOM_CLIMATE = "climate.mkyyf_ghrf_lnwm"  # مكيف غرفة النوم (عبود)
BABY_TEMP_MIN = 21.0
BABY_TEMP_MAX = 25.0

COVER_OPEN_MAX_HOURS = 3  # alert if cover open > 3 hours at night
NIGHT_HOURS = range(22, 24)  # 10PM-6AM (including 0-5)
NIGHT_HOURS_EARLY = range(0, 6)

AC_RUNTIME_THRESHOLD = 1.5  # alert if AC runs 1.5x longer than average


def _get_db():
    """Get DB connection."""
    if not os.path.exists(DB_PATH):
        return None
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _is_night():
    h = datetime.now().hour
    return h >= 22 or h < 6

def _is_daytime():
    """Check if daytime in Kuwait (6AM-5PM conservative window)."""
    h = datetime.now().hour
    return 6 <= h < 17


def check_ac_runtime():
    """Compare current AC runtime today vs historical average for same day of week."""
    conn = _get_db()
    if not conn:
        return []
    alerts = []
    now = datetime.now()
    dow = now.weekday()
    try:
        today_on = conn.execute("""
            SELECT entity_id, COUNT(*) as on_events
            FROM state_changes
            WHERE domain = 'climate' AND new_state != 'off'
                AND date(ts) = date('now', 'localtime')
            GROUP BY entity_id
        """).fetchall()
        for row in today_on:
            eid = row["entity_id"]
            today_count = row["on_events"]
            hist = conn.execute("""
                SELECT AVG(c) as avg_events FROM (
                    SELECT date(ts) as d, COUNT(*) as c
                    FROM state_changes
                    WHERE entity_id = ? AND domain = 'climate' AND new_state != 'off'
                        AND day_of_week = ?
                        AND date(ts) < date('now', 'localtime')
                    GROUP BY date(ts)
                )
            """, (eid, dow)).fetchone()
            avg = hist["avg_events"] if hist and hist["avg_events"] else 0
            if avg > 0 and today_count > avg * AC_RUNTIME_THRESHOLD:
                name = eid.split(".")[-1].replace("_inverted", "").replace("_", " ").strip()
                alerts.append({"type": "ac_runtime_high", "severity": "info", "entity_id": eid, "message": f"❄️ {name} يشتغل أكثر من المعتاد ({today_count} vs avg {avg:.0f})", "suggestion": None})
    except Exception as e:
        logger.error(f"AC runtime check: {e}")
    finally:
        conn.close()
    return alerts


def check_baby_room_temp():
    """Check if baby room temperature is out of safe range."""
    conn = _get_db()
    if not conn:
        return []
    alerts = []
    try:
        row = conn.execute("""
            SELECT current_temp, target_temp, state, ts
            FROM climate_log
            WHERE entity_id = ?
            ORDER BY ts DESC LIMIT 1
        """, (BABY_ROOM_CLIMATE,)).fetchone()
        if row and row["current_temp"]:
            temp = row["current_temp"]
            if temp < BABY_TEMP_MIN:
                alerts.append({"type": "baby_room_cold", "severity": "warning", "entity_id": BABY_ROOM_CLIUATE, "message": f"🥶 غرفة عبود باردة: {temp}°C (الحد {BABY_TEMP_MIN}°C)", "suggestion": f"تبيني أشغل المكيف على {BABY_TEMP_MIN + 1}°C؟"})
            elif temp > BABY_TEMP_MAX:
                alerts.append({"type": "baby_room_hot", "severity": "warning", "entity_id": BABY_ROOM_CLIUATE, "message": f"🥵 غرفة عبود حارة: {temp}°C (الحد {BABY_TEMP_MAX}°C)", "suggestion": f"تبيني أنزل المكيف على {BABY_TEMP_MAX - 1}°C؟"})
    except Exception as e:
        logger.error(f"Baby room check: {e}")
    finally:
        conn.close()
    return alerts


def check_covers_open():
    """Alert if covers open too long."""
    conn = _get_db()
    if not conn:
        return []
    alerts = []
    try:
        open_covers = conn.execute("""
            SELECT entity_id, MAX(ts) as opened_at
            FROM state_changes
            WHERE domain = 'cover' AND new_state = 'open'
                AND date(ts) >= date('now', '-1 day', 'localtime')
            GROUP BY entity_id
            HAVING entity_id NOT IN (
                SELECT entity_id FROM state_changes
                WHERE domain = 'cover' AND new_state IN ('closed', 'closing')
                    AND ts > opened_at
            )
        """).fetchall()
        for row in open_covers:
            eid = row["entity_id"]
            opened_at = datetime.fromisoformat(row["opened_at"])
            hours_open = (datetime.now() - opened_at).total_seconds() / 3600
            if _is_night() and hours_open > 1:
                name = eid.split(".")[-1].replace("_inverted", "").replace("_", " ").strip()
                alerts.append({"type": "cover_open_night", "severity": "warning", "entity_id": eid, "message": f"🌙 {name} مفتوحة من {hours_open:.1f} ساعة بالليل", "suggestion": "تبيني أسكرها؟"})
            elif hours_open > COVER_OPEN_MAX_HOURS and not _is_daytime():
                name = eid.split(".")[-1].replace("_inverted", "").replace("_", " ").strip()
                alerts.append({"type": "cover_open_long", "severity": "info", "entity_id": eid, "message": f"🚟 {name} مفتوحة من {hours_open:.1f} ساعة", "suggestion": None})
    except Exception as e:
        logger.error(f"Cover check: {e}")
    finally:
        conn.close()
    return alerts


def check_unusual_activity():
    """Detect unusual activity level."""
    conn = _get_db()
    if not conn:
        return []
    alerts = []
    hour = datetime.now().hour
    try:
        recent = conn.execute("""
            SELECT COUNT(*) as c FROM state_changes
            WHERE ts > datetime('now', '-1 hour', 'localtime')
        """).fetchone()["c"]
        hist = conn.execute("""
            SELECT AVG(c) as avg_c, MAX(c) as max_c FROM (
                SELECT date(ts) as d, COUNT(*) as c
                FROM state_changes
                WHERE hour = ? AND date(ts) < date('now', 'localtime')
                GROUP BY date(ts)
            )
        """, (hour,)).fetchone()
        avg = hist["avg_c"] if hist and hist["avg_c"] else 0
        max_c = hist["max_c"] if hist and hist["max_c"] else 0
        if avg > 5 and recent > avg * 2 and recent > max_c:
            alerts.append({"type": "unusual_activity", "severity": "info", "entity_id": None, "message": f"📊 نشاط غير معتاد: {recent} تغيير بالساعة الأخيرة (المعدل {avg:.0f})", "suggestion": None})
    except Exception as e:
        logger.error(f"Activity check: {e}")
    finally:
        conn.close()
    return alerts


def check_lights_unusual():
    """Detect lights on at unusual hours (1AM-5AM)."""
    conn = _get_db()
    if not conn:
        return []
    alerts = []
    hour = datetime.now().hour
    if hour < 1 or hour >= 5:
        return []
    try:
        on_lights = conn.execute("""
            SELECT DISTINCT sc1.entity_id
            FROM state_changes sc1
            WHERE sc1.domain = 'light' AND sc1.new_state = 'on'
                AND sc1.ts = (
                    SELECT MAX(ts) FROM state_changes
                    WHERE entity_id = sc1.entity_id AND date(ts) = date('now', 'localtime')
                )
                AND sc1.ts > datetime('now', '-6 hours', 'localtime')
        """).fetchall()
        if len(on_lights) > 3:
            names = [r["entity_id"].split(".")[-1].replace("_"," ") for r in on_lights[:5]]
            alerts.append({"type": "lights_on_late", "severity": "info", "entity_id": None, "message": f"💡 {len(on_lights)} أنوار شغالة الساعة {hour} الفجر: {', '.join(names[:3])}", "suggestion": "تبيني أطفي كل شيٟ (scene.tfwy_kl_shy)"})
    except Exception as e:
        logger.error(f"Lights check: {e}")
    finally:
        conn.close()
    return alerts


async def run_anomaly_checks():
    """Run all anomaly checks."""
    all_alerts = []
    for name, fn in [("ac_runtime", check_ac_runtime), ("baby_room", check_baby_room_temp), ("covers", check_covers_open), ("activity", check_unusual_activity), ("lights", check_lights_unusual)]:
        try:
            results = fn()
            if results:
                all_alerts.extend(results)
                logger.info(f"Anomaly {name}: {len(results)} alerts")
        except Exception as e:
            logger.error(f"Anomaly {name} failed: {e}")
    return all_alerts


def get_anomaly_summary():
    """Sync version for quick_query."""
    alerts = []
    for fn in [check_ac_runtime, check_baby_room_temp, check_covers_open, check_unusual_activity, check_lights_unusual]:
        try:
            alerts.extend(fn())
        except:
            pass
    return alerts
