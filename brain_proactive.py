"""
Master AI Brain — Proactive Intelligence (Phase 4)
Safe Mode: if this module crashes, it does NOT affect the main API.
"""

import asyncio
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("brain.proactive")

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "audit.db"
POLICY_PATH = BASE_DIR / "policy.json"

HA_URL = os.getenv("HA_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")

CHECK_INTERVAL = 300


def _load_policy():
    try:
        with open(POLICY_PATH) as f:
            return json.load(f).get("proactive", {})
    except Exception:
        return {"enabled": False}


def _ensure_alerts_table():
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proactive_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type TEXT NOT NULL,
                entity_id TEXT,
                message TEXT NOT NULL,
                severity TEXT DEFAULT 'low',
                sent INTEGER DEFAULT 0,
                acknowledged INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_type_entity
            ON proactive_alerts(alert_type, entity_id, created_at)
        """)
        conn.commit()
        conn.close()
        logger.info("proactive_alerts table ready")
    except Exception as e:
        logger.error(f"Failed to create alerts table: {e}")


def _save_alert(alert_type, entity_id, message, severity="low"):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO proactive_alerts (alert_type, entity_id, message, severity, sent) VALUES (?,?,?,?,1)",
            (alert_type, entity_id, message, severity)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to save alert: {e}")


def _get_recent_alerts(alert_type, entity_id, hours=6):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        row = conn.execute(
            "SELECT COUNT(*) FROM proactive_alerts WHERE alert_type=? AND entity_id=? AND created_at>?",
            (alert_type, entity_id, cutoff)
        ).fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception:
        return 0


def _count_alerts_today():
    try:
        conn = sqlite3.connect(str(DB_PATH))
        today = datetime.utcnow().strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT COUNT(*) FROM proactive_alerts WHERE created_at >= ? AND sent=1", (today,)
        ).fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception:
        return 0


def _count_alerts_last_hour():
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cutoff = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        row = conn.execute(
            "SELECT COUNT(*) FROM proactive_alerts WHERE created_at >= ? AND sent=1", (cutoff,)
        ).fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception:
        return 0


async def _fetch_ha_states():
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{HA_URL}/api/states",
                headers={"Authorization": f"Bearer {HA_TOKEN}"}
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch HA states: {e}")
    return []


async def _send_telegram(text):
    chat_id = ADMIN_CHAT_ID
    if not chat_id:
        # Fallback: read from auto-saved file
        admin_file = BASE_DIR / "data" / "admin_chat_id.txt"
        if admin_file.exists():
            chat_id = admin_file.read_text().strip()
    if not chat_id:
        logger.warning("No admin chat_id available")
        return False
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not tg_token:
        return False
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Sanitize surrogates
            clean = text.encode("utf-8", errors="replace").decode("utf-8")
            resp = await client.post(
                f"https://api.telegram.org/bot{tg_token}/sendMessage",
                json={"chat_id": chat_id, "text": clean}
            )
            return resp.status_code == 200
    except Exception as e:
        logger.error(f"TG send failed: {e}")
        return False


def _in_quiet_hours(policy):
    try:
        now = datetime.utcnow() + timedelta(hours=3)
        current_time = now.strftime("%H:%M")
        start = policy.get("quiet_hours_start", "00:00")
        end = policy.get("quiet_hours_end", "07:00")
        if start <= end:
            return start <= current_time <= end
        else:
            return current_time >= start or current_time <= end
    except Exception:
        return False


def _rate_limit_ok(policy):
    max_hour = policy.get("rate_limit_per_hour", 4)
    max_day = policy.get("rate_limit_per_day", 15)
    if _count_alerts_last_hour() >= max_hour:
        return False
    if _count_alerts_today() >= max_day:
        return False
    return True


def _parse_duration_minutes(state_obj):
    try:
        last_changed = state_obj.get("last_changed", "")
        if not last_changed:
            return 0
        changed_dt = datetime.fromisoformat(last_changed.replace("Z", "+00:00"))
        now = datetime.now(changed_dt.tzinfo)
        delta = (now - changed_dt).total_seconds() / 60
        return max(0, delta)
    except Exception:
        return 0


async def _run_checks(states):
    alerts = []
    for s in states:
        eid = s.get("entity_id", "")
        state = s.get("state", "")
        fname = s.get("attributes", {}).get("friendly_name", eid)
        duration_min = _parse_duration_minutes(s)

        # Device unavailable > 60 min (important devices only)
        if state == "unavailable" and duration_min > 60:
            skip_prefixes = ["update.", "button.", "number.", "select.", "sensor.", "binary_sensor.", "switch."]
            skip_keywords = ["alexa", "iphone", "geocoded", "shuffle", "repeat", "next_track", "media_player"]
            if not any(eid.startswith(p) for p in skip_prefixes) and not any(kw in eid.lower() for kw in skip_keywords):
                alerts.append({
                    "type": "device_unavailable",
                    "entity_id": eid,
                    "message": f"\u26a0\ufe0f {fname} \u0645\u0648 \u0645\u062a\u0635\u0644 \u0645\u0646 {int(duration_min)} \u062f\u0642\u064a\u0642\u0629",
                    "severity": "high"
                })

        # Door/Lock open too long
        if (eid.startswith("binary_sensor.") and "door" in eid and state == "on" and duration_min > 30) or \
           (eid.startswith("lock.") and state == "unlocked" and duration_min > 60):
            alerts.append({
                "type": "door_open_long",
                "entity_id": eid,
                "message": f"\ud83d\udecf {fname} \u0645\u0641\u062a\u0648\u062d \u0645\u0646 {int(duration_min)} \u062f\u0642\u064a\u0642\u0629",
                "severity": "medium"
            })

        # Light on > 3 hours
        if eid.startswith("light.") and state == "on" and duration_min > 180:
            alerts.append({
                "type": "light_on_long",
                "entity_id": eid,
                "message": f"\ud83d\udca1 {fname} \u0634\u063a\u0627\u0644 \u0645\u0646 {int(duration_min // 60)} \u0633\u0627\u0639\u0629",
                "severity": "low"
            })

        # AC running > 8 hours
        if eid.startswith("climate.") and state not in ("off", "unavailable") and duration_min > 480:
            alerts.append({
                "type": "ac_long_run",
                "entity_id": eid,
                "message": f"\u2744\ufe0f {fname} \u0634\u063a\u0627\u0644 \u0645\u0646 {int(duration_min // 60)} \u0633\u0627\u0639\u0629 \u0645\u062a\u0648\u0627\u0635\u0644\u0629",
                "severity": "low"
            })

    return alerts


async def _build_daily_briefing(states):
    lights_on = []
    ac_on = []
    unavailable = []
    doors_open = []

    for s in states:
        eid = s.get("entity_id", "")
        state = s.get("state", "")
        fname = s.get("attributes", {}).get("friendly_name", eid)

        if eid.startswith("light.") and state == "on":
            lights_on.append(fname)
        if eid.startswith("climate.") and state not in ("off", "unavailable"):
            temp = s.get("attributes", {}).get("current_temperature", "?")
            target = s.get("attributes", {}).get("temperature", "?")
            ac_on.append(f"{fname} ({temp}\u00b0\u2192{target}\u00b0)")
        if state == "unavailable" and not any(skip in eid for skip in ["update.", "button.", "number.", "select.", "scene."]):
            unavailable.append(fname)
        if (eid.startswith("lock.") and state == "unlocked") or \
           (eid.startswith("binary_sensor.") and "door" in eid and state == "on"):
            doors_open.append(fname)

    now_kw = datetime.utcnow() + timedelta(hours=3)
    msg = f"\u2600\ufe0f \u0635\u0628\u0627\u062d \u0627\u0644\u062e\u064a\u0631 \u0628\u0648 \u062e\u0644\u064a\u0641\u0629 \u2014 {now_kw.strftime('%A %d/%m')}\n\n"

    if not lights_on and not doors_open and len(unavailable) <= 2:
        msg += "\u2705 \u0627\u0644\u0628\u064a\u062a \u062a\u0645\u0627\u0645\n"

    if lights_on:
        msg += f"\n\ud83d\udca1 \u0623\u0636\u0648\u0627\u0621 \u0634\u063a\u0627\u0644\u0629 ({len(lights_on)}):\n"
        for l in lights_on[:10]:
            msg += f"  \u2022 {l}\n"
        if len(lights_on) > 10:
            msg += f"  ... \u0648 {len(lights_on) - 10} \u062b\u0627\u0646\u064a\n"

    if ac_on:
        msg += f"\n\u2744\ufe0f \u0645\u0643\u064a\u0641\u0627\u062a ({len(ac_on)}):\n"
        for a in ac_on:
            msg += f"  \u2022 {a}\n"

    if doors_open:
        msg += f"\n\ud83d\udeaa \u0645\u0641\u062a\u0648\u062d:\n"
        for d in doors_open:
            msg += f"  \u2022 {d}\n"

    if unavailable:
        msg += f"\n\u26a0\ufe0f \u063a\u064a\u0631 \u0645\u062a\u0635\u0644 ({len(unavailable)}):\n"
        for u in unavailable[:5]:
            msg += f"  \u2022 {u}\n"
        if len(unavailable) > 5:
            msg += f"  ... \u0648 {len(unavailable) - 5} \u062b\u0627\u0646\u064a\n"

    try:
        conn = sqlite3.connect(str(DB_PATH))
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT COUNT(*) FROM proactive_alerts WHERE created_at >= ?", (yesterday,)
        ).fetchone()
        conn.close()
        alert_count = row[0] if row else 0
        if alert_count > 0:
            msg += f"\n\ud83d\udcca \u062a\u0646\u0628\u064a\u0647\u0627\u062a \u0623\u0645\u0633: {alert_count}\n"
    except Exception:
        pass

    return msg


def _should_send_briefing(policy):
    now_kw = datetime.utcnow() + timedelta(hours=3)
    current_hour = now_kw.hour
    current_min = now_kw.minute
    today = now_kw.strftime("%Y-%m-%d")

    if current_hour == 7 and current_min < 10:
        try:
            conn = sqlite3.connect(str(DB_PATH))
            row = conn.execute(
                "SELECT COUNT(*) FROM proactive_alerts WHERE alert_type='daily_briefing' AND created_at >= ?",
                (today,)
            ).fetchone()
            conn.close()
            if row and row[0] > 0:
                return False
        except Exception:
            pass
        return True
    return False


def get_proactive_stats():
    try:
        conn = sqlite3.connect(str(DB_PATH))
        total = conn.execute("SELECT COUNT(*) FROM proactive_alerts").fetchone()[0]
        today_count = conn.execute(
            "SELECT COUNT(*) FROM proactive_alerts WHERE created_at >= date('now')"
        ).fetchone()[0]
        by_type = {}
        for row in conn.execute(
            "SELECT alert_type, COUNT(*) FROM proactive_alerts GROUP BY alert_type"
        ):
            by_type[row[0]] = row[1]
        last_alert = conn.execute(
            "SELECT created_at FROM proactive_alerts ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        policy = _load_policy()
        return {
            "enabled": policy.get("enabled", False),
            "total_alerts": total,
            "alerts_today": today_count,
            "by_type": by_type,
            "last_alert": last_alert[0] if last_alert else None,
            "rate_limit_ok": _rate_limit_ok(policy)
        }
    except Exception as e:
        return {"enabled": False, "error": str(e)}


async def proactive_loop():
    _ensure_alerts_table()
    logger.info("Proactive engine starting...")
    await asyncio.sleep(30)

    while True:
        try:
            policy = _load_policy()
            if not policy.get("enabled", False):
                await asyncio.sleep(60)
                continue
            admin_id = ADMIN_CHAT_ID
            if not admin_id:
                admin_file = BASE_DIR / "data" / "admin_chat_id.txt"
                if admin_file.exists():
                    admin_id = admin_file.read_text().strip()
            if not admin_id:
                logger.warning("ADMIN_CHAT_ID not set (env or file)")
                await asyncio.sleep(300)
                continue

            states = await _fetch_ha_states()
            if not states:
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            # Daily Briefing
            if _should_send_briefing(policy):
                briefing = await _build_daily_briefing(states)
                sent = await _send_telegram(briefing)
                if sent:
                    _save_alert("daily_briefing", "system", briefing, "info")
                    logger.info("Daily briefing sent")

            # Proactive Checks
            alerts = await _run_checks(states)
            dedup_hours = policy.get("dedup_window_hours", 6)

            # Filter alerts (dedup + quiet hours)
            filtered = []
            for alert in alerts:
                if _get_recent_alerts(alert["type"], alert["entity_id"], dedup_hours) > 0:
                    continue
                if _in_quiet_hours(policy) and alert["severity"] != "high":
                    continue
                filtered.append(alert)

            if not filtered:
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            if not _rate_limit_ok(policy):
                logger.warning("Rate limit hit, skipping alerts")
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            # Build batched summary
            by_type = {}
            for a in filtered:
                by_type.setdefault(a["type"], []).append(a)

            parts = ["🚨 *Smart Home Alerts*"]

            high_alerts = [a for a in filtered if a["severity"] == "high"]
            if high_alerts:
                parts.append("🔴 *Urgent:*")
                for a in high_alerts[:5]:
                    parts.append("  " + a["message"])

            for atype, items in by_type.items():
                non_high = [a for a in items if a["severity"] != "high"]
                if not non_high:
                    continue
                if atype == "light_on_long":
                    parts.append(f"💡 {len(non_high)} lights on > 8h")
                elif atype == "device_unavailable":
                    names = [a["entity_id"].split(".")[1] for a in non_high[:3]]
                    extra = f" +{len(non_high)-3}" if len(non_high) > 3 else ""
                    parts.append(f"⚠️ {len(non_high)} offline: " + ", ".join(names) + extra)
                elif atype == "ac_long_run":
                    parts.append(f"❄️ {len(non_high)} ACs running long")
                elif atype == "door_open_long":
                    for a in non_high:
                        parts.append(a["message"])

            summary = chr(10).join(parts)
            sent = await _send_telegram(summary)
            if sent:
                for a in filtered:
                    _save_alert(a["type"], a["entity_id"], a["message"], a["severity"])
                logger.info(f"Batch alert sent: {len(filtered)} alerts")

            await asyncio.sleep(CHECK_INTERVAL)

        except Exception as e:
            logger.error(f"Proactive loop error (non-fatal): {e}")
            await asyncio.sleep(CHECK_INTERVAL)
