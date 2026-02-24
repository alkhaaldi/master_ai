#!/home/pi/master_ai/venv/bin/python3
"""Ruijie Cloud API → Home Assistant Integration
Runs every 5 minutes via cron. Updates HA sensors with AP status and client info.
"""
import os, json, time, logging, requests
from datetime import datetime
from pathlib import Path

# --- Config ---
RUIJIE_BASE = "https://cloud.ruijienetworks.com"
APPID = "open928f647a7972"
SECRET = "8084e28c239c4c6aad94b3adf7a98c0a"
GROUP_ID = "9108988"
TOKEN_FILE = "/home/pi/master_ai/data/ruijie_token.json"
HA_URL = "http://localhost:8123"
HA_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI1ZDVlZWRkMzk0MjY0MDk2OTY0YThlNjYyZDU0NTYzYiIsImlhdCI6MTc3MTI1NDI4NywiZXhwIjoyMDg2NjE0Mjg3fQ.Ws_86k8u0abSGfBZMYxKVSxzO8r6kX2yyIXPicjyFd0"

LOG_FILE = "/var/log/ruijie_integration.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger("ruijie")

def get_token():
    """Get or refresh Ruijie API token (cached 25 days)."""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            cached = json.load(f)
        if time.time() - cached.get("timestamp", 0) < 86400 * 25:
            return cached["token"]

    url = f"{RUIJIE_BASE}/service/api/oauth20/client/access_token?token=d63dss0a81e4415a889ac5b78fsc904a"
    r = requests.post(url, json={"appid": APPID, "secret": SECRET}, timeout=15)
    data = r.json()
    if data.get("code") == 0:
        token = data["accessToken"]
        Path(TOKEN_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "w") as f:
            json.dump({"token": token, "timestamp": time.time()}, f)
        log.info(f"New token acquired: {token[:10]}...")
        return token
    raise Exception(f"Token error: {data}")

def get_ap_list(token):
    """Get all AP devices."""
    url = f"{RUIJIE_BASE}/service/api/maint/devices?common_type=AP&group_id={GROUP_ID}&page=1&per_page=50&access_token={token}"
    r = requests.get(url, timeout=15)
    data = r.json()
    if data.get("code") == 0:
        return data.get("deviceList", [])
    log.warning(f"AP list error: {data}")
    return []

def get_clients(token):
    """Get current online clients."""
    url = f"{RUIJIE_BASE}/logbizagent/logbiz/api/sta/sta_users?access_token={token}"
    r = requests.post(url, json={
        "groupId": GROUP_ID, "pageSize": 300, "pageIndex": 0, "staType": "currentUser"
    }, timeout=15)
    data = r.json()
    if data.get("code") == 0:
        return data.get("list", []), data.get("count", 0)
    log.warning(f"Clients error: {data}")
    return [], 0

def update_ha_sensor(entity_id, state, attributes):
    """Update HA sensor via API."""
    url = f"{HA_URL}/api/states/{entity_id}"
    headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
    payload = {"state": str(state), "attributes": attributes}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        return r.status_code in (200, 201)
    except Exception as e:
        log.error(f"HA sensor update failed for {entity_id}: {e}")
        return False

def run():
    """Main integration."""
    token = get_token()

    # Get APs
    aps = get_ap_list(token)
    online_aps = sum(1 for a in aps if a.get("onlineStatus") == "ON")
    total_aps = len(aps)

    # Update per-AP sensors with CORRECT field names
    for ap in aps:
        name = (ap.get("aliasName") or ap.get("name") or ap.get("serialNumber", "unknown"))
        entity_name = name.lower().replace(" ", "_").replace("-", "_").replace("@", "_")
        entity = f"sensor.ruijie_ap_{entity_name}"

        # Count clients per AP
        ap_sn = ap.get("serialNumber", "")
        ap_clients = ap.get("staNums", 0)

        # Radio info
        r1_ch = ap.get("radio1Channel", "")
        r2_ch = ap.get("radio2Channel", "")
        r1_pwr = ap.get("radio1Power", "")
        r2_pwr = ap.get("radio2Power", "")
        r1_util = ap.get("radio1ChannelUtil", "")
        r2_util = ap.get("radio2ChannelUtil", "")

        update_ha_sensor(entity, ap.get("onlineStatus", "UNKNOWN"), {
            "friendly_name": f"AP: {name}",
            "icon": "mdi:access-point",
            "ip": ap.get("localIp", ""),
            "mac": ap.get("mac", ""),
            "model": ap.get("productClass", ""),
            "sw_version": ap.get("softwareVersion", ""),
            "serial": ap.get("serialNumber", ""),
            "online_status": ap.get("onlineStatus", ""),
            "clients": ap_clients,
            "radio_2g_channel": r1_ch,
            "radio_5g_channel": r2_ch,
            "radio_2g_power": r1_pwr,
            "radio_5g_power": r2_pwr,
            "radio_2g_util": r1_util,
            "radio_5g_util": r2_util,
        })

    # Update network overview
    update_ha_sensor("sensor.ruijie_network_overview", f"{online_aps}/{total_aps} APs online", {
        "friendly_name": "Ruijie Network Overview",
        "icon": "mdi:access-point-network",
        "online_aps": online_aps,
        "total_aps": total_aps,
        "last_update": datetime.now().isoformat(),
    })

    # Get clients
    clients, total_clients = get_clients(token)
    # Fix band detection: API returns "2.4G" and "5G"
    band_2g = sum(1 for c in clients if c.get("band", "") == "2.4G")
    band_5g = sum(1 for c in clients if c.get("band", "") == "5G")

    update_ha_sensor("sensor.ruijie_clients_total", total_clients, {
        "friendly_name": "Network Clients",
        "icon": "mdi:devices",
        "band_2_4ghz": band_2g,
        "band_5ghz": band_5g,
        "last_update": datetime.now().isoformat(),
        "unit_of_measurement": "clients",
    })

    # Weak signal clients (RSSI < -75)
    weak = [c for c in clients if c.get("rssi") and int(c.get("rssi", 0)) < -75]
    weak_info = []
    # Build AP serial→name map
    ap_name_map = {a.get("serialNumber", ""): (a.get("aliasName") or a.get("name") or "?") for a in aps}
    for c in weak:
        weak_info.append({
            "mac": c.get("mac", ""),
            "rssi": c.get("rssi"),
            "ap": ap_name_map.get(c.get("sn", ""), c.get("sn", "?")),
            "band": c.get("band", ""),
            "ssid": c.get("ssid", ""),
        })

    update_ha_sensor("sensor.ruijie_weak_clients", len(weak), {
        "friendly_name": "Weak Signal Clients",
        "icon": "mdi:wifi-strength-1-alert",
        "clients": weak_info[:15],
        "unit_of_measurement": "clients",
    })

    log.info(f"Updated: {online_aps}/{total_aps} APs, {total_clients} clients ({band_2g} 2.4G, {band_5g} 5G), {len(weak)} weak")

if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        log.error(f"Error: {e}")
