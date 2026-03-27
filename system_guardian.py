"""
system_guardian.py — System Guardian for Master AI
Monitors: Router (BE800), RPi (self), HA (Docker), NVR, Internet
Sends TG alerts when infrastructure goes down/recovers.
"""
import subprocess, logging, time, os
from datetime import datetime

logger = logging.getLogger("guardian")

# Targets to monitor
TARGETS = {
    "router": {"host": "192.168.108.1", "name": "راوتر BE800", "icon": "U0001f310"},
    "nvr": {"host": "192.168.108.44", "name": "NVR", "icon": "U0001f4f9"},
    "ha": {"url": "http://192.168.109.123:8123/api/", "name": "Home Assistant", "icon": "U0001f3e0"},
    "internet": {"host": "8.8.8.8", "name": "الإنترنت", "icon": "U0001f30d"},
}

_status = {}       # {target: True/False}
_last_change = {}  # {target: timestamp}
_initialized = False
COOLDOWN = 300     # 5 min between alerts for same target


def _ping(host, timeout=3):
    """Ping a host. Returns True if reachable."""
    try:
        r = subprocess.run(["ping", "-c", "1", "-W", str(timeout), host],
                          capture_output=True, timeout=timeout+2)
        return r.returncode == 0
    except:
        return False


def _check_ha():
    """Check HA API is responding."""
    try:
        import httpx
        r = httpx.get("http://192.168.109.123:8123/api/", timeout=5)
        return r.status_code in (200, 401)  # 401 = auth needed but HA is up
    except:
        return False


def _check_rpi():
    """Check RPi self-health."""
    try:
        temp = subprocess.getoutput("vcgencmd measure_temp").replace("temp=","").replace("'C","")
        temp_f = float(temp)
        if temp_f > 80:
            return False, f"⚠️ RPi حرارة عالية: {temp_f}°C"
        load = subprocess.getoutput("cat /proc/loadavg").split()[0]
        if float(load) > 3.0:
            return False, f"⚠️ RPi load عالي: {load}"
        disk = subprocess.getoutput("df / | tail -1 | awk '{print $5}'").replace("%","")
        if int(disk) > 90:
            return False, f"⚠️ RPi disk ممتلئ: {disk}%"
        return True, None
    except:
        return True, None


def check_all():
    """Check all targets. Returns list of alerts."""
    global _status, _last_change, _initialized
    alerts = []
    now = time.time()
    
    for tid, cfg in TARGETS.items():
        if "host" in cfg:
            ok = _ping(cfg["host"])
        elif "url" in cfg:
            ok = _check_ha()
        else:
            continue
        
        prev = _status.get(tid)
        _status[tid] = ok
        
        if not _initialized:
            continue  # First run = baseline
        
        # State changed
        if prev is not None and prev != ok:
            last = _last_change.get(tid, 0)
            if now - last > COOLDOWN:
                _last_change[tid] = now
                if not ok:
                    alerts.append({
                        "type": "system_down",
                        "target": tid,
                        "message": f"{cfg['icon']} {cfg['name']} طاح!",
                        "severity": "critical",
                    })
                else:
                    alerts.append({
                        "type": "system_recovered",
                        "target": tid,
                        "message": f"✅ {cfg['name']} رجع شغال",
                        "severity": "info",
                    })
    
    # RPi self-check
    rpi_ok, rpi_msg = _check_rpi()
    if not rpi_ok and rpi_msg:
        last = _last_change.get("rpi_health", 0)
        if now - last > COOLDOWN:
            _last_change["rpi_health"] = now
            alerts.append({"type": "rpi_health", "target": "rpi", "message": rpi_msg, "severity": "warning"})
    
    if not _initialized:
        _initialized = True
        logger.info(f"Guardian initialized: {dict(_status)}")
    
    return alerts


def get_status():
    """Get current status of all targets (for /guardian command)."""
    if not _status:
        check_all()  # Initialize if not yet
        check_all()  # Second run to detect changes
    
    lines = ["U0001f6e1 System Guardian:"]
    for tid, cfg in TARGETS.items():
        ok = _status.get(tid)
        icon = "✅" if ok else "❌"
        lines.append(f"  {icon} {cfg['icon']} {cfg['name']}")
    
    # RPi health
    rpi_ok, rpi_msg = _check_rpi()
    temp = subprocess.getoutput("vcgencmd measure_temp").replace("temp=","").replace("'C","")
    load = subprocess.getoutput("cat /proc/loadavg").split()[0]
    disk = subprocess.getoutput("df / | tail -1 | awk '{print $5}'")
    icon = "✅" if rpi_ok else "⚠️"
    lines.append(f"  {icon} U0001f4bb RPi: {temp}°C | load {load} | disk {disk}")
    
    return chr(10).join(lines)
