"""
HA Doctor — يراقب صحة Home Assistant ويكتشف المشاكل.
1. Anomaly Detection: أجهزة شغالة أكثر من اللازم، تذبذب، offline
2. Logbook Analysis: يقرأ الأحداث ويلخصها
3. Health Report: تقرير أسبوعي بالمشاكل والاقتراحات
"""
import os, logging, httpx, json
from datetime import datetime, timedelta
from collections import Counter, defaultdict

logger = logging.getLogger("ha_doctor")
HA_URL = os.environ.get("HA_URL", "http://localhost:8123")
HA_TOKEN = os.environ.get("HA_TOKEN", "")

# Only report these domains as issues (ignore scene, button, sensor, stt, tts, ai_task)
IMPORTANT_DOMAINS = {"light", "switch", "climate", "cover", "fan", "media_player"}
# Skip known entities that are normally unavailable
SKIP_ENTITIES = {"stt.", "tts.", "ai_task.", "scene.", "button.", "number.", "select.", "update."}
# Skip by substring in entity_id
SKIP_SUBSTRINGS = {"alexa_", "blaupunkt", "everywhere_", "air_freshener", "_cartridge_", "_ionizer"}

DOMAIN_AR = {
    "light": "\u0636\u0648\u0621", "switch": "\u0645\u0641\u062a\u0627\u062d",
    "climate": "\u0645\u0643\u064a\u0641", "cover": "\u0633\u062a\u0627\u0631\u0629",
    "fan": "\u0645\u0631\u0648\u062d\u0629", "media_player": "\u0633\u0645\u0627\u0639\u0629",
    "sensor": "\u062d\u0633\u0627\u0633", "binary_sensor": "\u062d\u0633\u0627\u0633",
}


async def get_unavailable_entities():
    """Get all unavailable/unknown entities."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(HA_URL + "/api/states",
                headers={"Authorization": "Bearer " + HA_TOKEN})
            if r.status_code != 200: return []
            states = r.json()
        bad = []
        for s in states:
            eid = s["entity_id"]
            st = s["state"]
            if st in ("unavailable", "unknown"):
                domain = eid.split(".")[0]
                if domain not in IMPORTANT_DOMAINS: continue
                if any(skip in eid for skip in SKIP_ENTITIES): continue
                if any(sub in eid for sub in SKIP_SUBSTRINGS): continue
                if "backlight" in eid: continue
                attrs = s.get("attributes", {})
                # Climate with temperature reading = working (Midea shows 'unknown' state)
                if domain == "climate" and attrs.get("current_temperature") is not None:
                    continue
                name = attrs.get("friendly_name", eid)
                # Skip orphan/ghost entities
                if eid.endswith(".none") or name == "None": continue
                bad.append({"entity_id": eid, "name": name, "state": st, "domain": domain, "since": s.get("last_changed","")[:10]})
        return bad
    except Exception as e:
        logger.error("get_unavailable: " + str(e))
        return []


async def get_logbook(hours=24):
    """Get HA logbook entries for last N hours."""
    try:
        t = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(HA_URL + "/api/logbook/" + t,
                headers={"Authorization": "Bearer " + HA_TOKEN})
            if r.status_code != 200: return []
            return r.json()
    except Exception as e:
        logger.error("get_logbook: " + str(e))
        return []


async def detect_anomalies():
    """Detect anomalies from HA state + Brain data."""
    issues = []

    # 1. Unavailable entities
    unav = await get_unavailable_entities()
    if unav:
        # Group by domain
        by_domain = defaultdict(list)
        for u in unav:
            by_domain[u["domain"]].append(u)
        for domain, ents in by_domain.items():
            dar = DOMAIN_AR.get(domain, domain)
            names = [e["name"] for e in ents[:5]]
            more = f" +{len(ents)-5}" if len(ents) > 5 else ""
            since = ents[0].get("since", "")
            since_txt = f" (\u0645\u0646 {since})" if since else ""
            issues.append({
                "type": "unavailable",
                "severity": "warning" if len(ents) < 10 else "critical",
                "message": f"\u26a0\ufe0f {len(ents)} {dar} offline{since_txt}: {', '.join(names)}{more}",
                "entities": [e["entity_id"] for e in ents],
                "domain": domain,
            })

    # 2. Check Brain data for flapping (on/off/on/off rapidly)
    try:
        import sqlite3
        db_path = os.path.join(os.path.dirname(__file__), "data", "home_brain.db")
        if os.path.exists(db_path):
            cn = sqlite3.connect(db_path)
            cn.row_factory = sqlite3.Row
            # Entities with >20 changes today = flapping
            flap = cn.execute("""
                SELECT entity_id, COUNT(*) as c
                FROM state_changes
                WHERE date(ts) = date('now','localtime')
                GROUP BY entity_id HAVING c > 20
                ORDER BY c DESC
            """).fetchall()
            cn.close()
            for f in flap:
                name = f["entity_id"].split(".")[-1].replace("_", " ")
                issues.append({
                    "type": "flapping",
                    "severity": "warning",
                    "message": f"\U0001f504 {name} \u062a\u0630\u0628\u0630\u0628: {f['c']} \u062a\u063a\u064a\u064a\u0631 \u0627\u0644\u064a\u0648\u0645!",
                    "entity_id": f["entity_id"],
                    "changes": f["c"],
                })
    except Exception as e:
        logger.error("flapping check: " + str(e))

    # 3. Lights on for too long (>8 hours) - check from Brain
    try:
        if os.path.exists(db_path):
            cn = sqlite3.connect(db_path)
            cn.row_factory = sqlite3.Row
            # Lights that turned on >8 hours ago and never turned off
            stuck = cn.execute("""
                SELECT entity_id, MIN(ts) as first_on
                FROM state_changes
                WHERE date(ts) = date('now','localtime')
                    AND new_state = 'on' AND domain = 'light'
                    AND entity_id NOT IN (
                        SELECT entity_id FROM state_changes
                        WHERE date(ts) = date('now','localtime')
                            AND new_state = 'off' AND domain = 'light'
                            AND ts > (SELECT MAX(ts) FROM state_changes sc2
                                WHERE sc2.entity_id = state_changes.entity_id
                                AND sc2.new_state = 'on'
                                AND date(sc2.ts) = date('now','localtime'))
                    )
                GROUP BY entity_id
                HAVING (julianday('now','localtime') - julianday(first_on)) * 24 > 8
            """).fetchall()
            cn.close()
            for s in stuck:
                name = s["entity_id"].split(".")[-1].replace("_", " ")
                hrs = round((datetime.now() - datetime.fromisoformat(s["first_on"])).total_seconds() / 3600, 1)
                issues.append({
                    "type": "stuck_on",
                    "severity": "info",
                    "message": f"\U0001f4a1 {name} \u0634\u063a\u0627\u0644 {hrs} \u0633\u0627\u0639\u0629 \u0628\u062f\u0648\u0646 \u062a\u0648\u0642\u0641",
                    "entity_id": s["entity_id"],
                })
    except Exception as e:
        logger.error("stuck check: " + str(e))

    return issues


async def format_health_report():
    """Generate full health report in Arabic."""
    issues = await detect_anomalies()
    if not issues:
        return "\u2705 \u0627\u0644\u0628\u064a\u062a \u0628\u062e\u064a\u0631! \u0645\u0627 \u0641\u064a \u0645\u0634\u0627\u0643\u0644."

    lines = ["\U0001f3e5 *\u062a\u0642\u0631\u064a\u0631 \u0635\u062d\u0629 \u0627\u0644\u0628\u064a\u062a:*", ""]

    critical = [i for i in issues if i["severity"] == "critical"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    info = [i for i in issues if i["severity"] == "info"]

    if critical:
        lines.append("\U0001f534 *\u062d\u0631\u062c:*")
        for i in critical:
            lines.append(i["message"])
        lines.append("")

    if warnings:
        lines.append("\U0001f7e1 *\u062a\u062d\u0630\u064a\u0631:*")
        for i in warnings:
            lines.append(i["message"])
        lines.append("")

    if info:
        lines.append("\U0001f535 *\u0645\u0644\u0627\u062d\u0638\u0627\u062a:*")
        for i in info:
            lines.append(i["message"])

    lines.append("")
    lines.append(f"\U0001f4cb \u0625\u062c\u0645\u0627\u0644\u064a: {len(issues)} \u0645\u0644\u0627\u062d\u0638\u0629")
    return chr(10).join(lines)


async def suggest_fixes(issues=None):
    """Suggest fixes for detected issues."""
    if issues is None:
        issues = await detect_anomalies()
    fixes = []
    for i in issues:
        if i["type"] == "unavailable":
            domain = i.get("domain", "")
            if domain in ("light", "switch", "fan"):
                fixes.append("\U0001f527 " + domain + ": \u062c\u0631\u0628 reload Tuya integration")
            elif domain == "climate":
                fixes.append("\U0001f527 \u0645\u0643\u064a\u0641\u0627\u062a: \u0634\u064a\u0643 \u0627\u0644\u0643\u0647\u0631\u0628\u0627 + restart Midea integration")
            elif domain == "cover":
                fixes.append("\U0001f527 \u0633\u062a\u0627\u0626\u0631: reload Tuya integration")
        elif i["type"] == "flapping":
            fixes.append("\U0001f527 " + i.get("entity_id","") + ": \u0634\u064a\u0643 \u0627\u0644\u0634\u0628\u0643\u0629/\u0627\u0644\u0643\u0647\u0631\u0628\u0627 \u0644\u0647\u0627\u0644\u062c\u0647\u0627\u0632")
        elif i["type"] == "stuck_on":
            fixes.append("\U0001f4a1 \u0645\u0645\u0643\u0646 \u0646\u0627\u0633\u064a\u0647 \u0634\u063a\u0627\u0644 - \u062a\u0628\u064a \u0623\u0637\u0641\u064a\u0647\u061f")
    return fixes
