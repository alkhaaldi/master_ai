"""Phase B3: Home Monitoring Alerts for Telegram.

Background task that checks HA every 5 minutes and sends alerts for:
- Devices offline > 10 min
- Cover/door opened after 11 PM
- AC temperature exceeded guard limit
"""
import httpx, logging, os, asyncio
from datetime import datetime

logger = logging.getLogger("tg_alerts")

HA_URL = os.environ.get("HA_URL", "http://localhost:8123")
HA_TOKEN = os.environ.get("HA_TOKEN", "")

# Track state to avoid duplicate alerts
_warmup_done = False  # First check populates baseline
_prev_offline = set()
_prev_open_covers = set()
_prev_hot_acs = set()
_alert_cooldown = {}  # entity_id -> last_alert_time

OFFLINE_DOMAINS = ["light.", "switch.", "climate.", "cover.", "fan."]
AC_TEMP_LIMIT = 24.0  # Alert if current temp > this
NIGHT_START = 23  # 11 PM
NIGHT_END = 6     # 6 AM
CHECK_INTERVAL = 300  # 5 minutes
COOLDOWN_MINUTES = 120  # Don't re-alert same entity within 30 min


def _in_cooldown(entity_id: str) -> bool:
    last = _alert_cooldown.get(entity_id)
    if not last:
        return False
    return (datetime.now() - last).total_seconds() < COOLDOWN_MINUTES * 60


def _mark_alerted(entity_id: str):
    _alert_cooldown[entity_id] = datetime.now()


async def _get_states():
    if not HA_TOKEN:
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{HA_URL}/api/states",
                            headers={"Authorization": f"Bearer {HA_TOKEN}"})
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.error(f"HA states error: {e}")
    return []


async def check_alerts(send_fn) -> list[str]:
    """Check for alert conditions and send via send_fn(text).
    
    Args:
        send_fn: async function that sends a telegram message (text)
    Returns:
        list of alert messages sent
    """
    global _prev_offline, _prev_open_covers, _prev_hot_acs
    
    states = await _get_states()
    if not states:
        return []
    
    alerts = []
    now = datetime.now()
    is_night = now.hour >= NIGHT_START or now.hour < NIGHT_END
    
    # --- Warmup: first run captures baseline ---
    global _warmup_done
    if not _warmup_done:
        _warmup_done = True
        for s in states:
            eid = s.get("entity_id", "")
            st = s.get("state", "")
            if st == "unavailable" and any(eid.startswith(d) for d in OFFLINE_DOMAINS):
                _prev_offline.add(eid)
            if eid.startswith("cover.") and st == "open":
                _prev_open_covers.add(eid)
        logger.info(f"Warmup: {len(_prev_offline)} offline, {len(_prev_open_covers)} open covers baselined")
        return []

    # --- 1. New offline devices ---
    current_offline = set()
    for s in states:
        eid = s.get("entity_id", "")
        state = s.get("state", "")
        if state == "unavailable" and any(eid.startswith(d) for d in OFFLINE_DOMAINS):
            current_offline.add(eid)
    
    new_offline = current_offline - _prev_offline
    if new_offline:
        # Only alert for devices that weren't offline before and not in cooldown
        alert_eids = [e for e in new_offline if not _in_cooldown(e)]
        if alert_eids:
            names = []
            for eid in alert_eids[:5]:
                for s in states:
                    if s["entity_id"] == eid:
                        names.append(s.get("attributes", {}).get("friendly_name", eid))
                        _mark_alerted(eid)
                        break
            if names:
                msg = f"⚠️ أجهزة صارت offline ({len(alert_eids)}):\n"
                msg += "\n".join(f"  • {n}" for n in names)
                if len(alert_eids) > 5:
                    msg += f"\n  ... و {len(alert_eids)-5} أجهزة أخرى"
                alerts.append(msg)
    
    # Track recovered devices
    recovered = _prev_offline - current_offline
    if recovered and _prev_offline:  # Don't alert on first run
        rec_names = []
        for eid in list(recovered)[:3]:
            for s in states:
                if s["entity_id"] == eid:
                    rec_names.append(s.get("attributes", {}).get("friendly_name", eid))
                    break
        if rec_names:
            msg = f"✅ أجهزة رجعت online:\n"
            msg += "\n".join(f"  • {n}" for n in rec_names)
            alerts.append(msg)
    
    _prev_offline = current_offline
    
    # --- 2. Night cover/door alerts ---
    if is_night:
        current_open = set()
        for s in states:
            eid = s.get("entity_id", "")
            if eid.startswith("cover.") and s.get("state") == "open":
                current_open.add(eid)
        
        new_open = current_open - _prev_open_covers
        if new_open:
            alert_eids = [e for e in new_open if not _in_cooldown(e)]
            if alert_eids:
                names = []
                for eid in alert_eids:
                    for s in states:
                        if s["entity_id"] == eid:
                            names.append(s.get("attributes", {}).get("friendly_name", eid))
                            _mark_alerted(eid)
                            break
                if names:
                    msg = f"🌙 ستائر انفتحت بالليل:\n"
                    msg += "\n".join(f"  • {n}" for n in names)
                    alerts.append(msg)
        
        _prev_open_covers = current_open
    
    # --- 3. AC temperature alerts ---
    current_hot = set()
    for s in states:
        eid = s.get("entity_id", "")
        if eid.startswith("climate.") and s.get("state") not in ("unavailable", "off"):
            curr_temp = s.get("attributes", {}).get("current_temperature")
            if curr_temp and float(curr_temp) > AC_TEMP_LIMIT:
                current_hot.add(eid)
    
    new_hot = current_hot - _prev_hot_acs
    if new_hot:
        alert_eids = [e for e in new_hot if not _in_cooldown(e)]
        if alert_eids:
            lines = []
            for eid in alert_eids:
                for s in states:
                    if s["entity_id"] == eid:
                        name = s.get("attributes", {}).get("friendly_name", eid)
                        temp = s.get("attributes", {}).get("current_temperature")
                        target = s.get("attributes", {}).get("temperature")
                        lines.append(f"  🌡 {name}: {temp}° (هدف {target}°)")
                        _mark_alerted(eid)
                        break
            if lines:
                msg = f"🔥 مكيفات تجاوزت {AC_TEMP_LIMIT}°:\n"
                msg += "\n".join(lines)
                alerts.append(msg)
    
    _prev_hot_acs = current_hot
    
    # Send all alerts
    for alert in alerts:
        try:
            await send_fn(alert)
        except Exception as e:
            logger.error(f"Alert send error: {e}")
    
    return alerts


async def alert_loop(send_fn):
    """Background loop — call this from server startup."""
    logger.info("🔔 Alert monitor started (every 5 min)")
    # Wait 60 seconds on startup to let HA stabilize
    await asyncio.sleep(60)
    
    while True:
        try:
            alerts = await check_alerts(send_fn)
            if alerts:
                logger.info(f"Sent {len(alerts)} alerts")
        except Exception as e:
            logger.error(f"Alert loop error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)
