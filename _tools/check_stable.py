import subprocess

# Check watchdog timer status
print("=== Watchdog timer status ===")
result = subprocess.run(["systemctl", "is-active", "master-ai-watchdog.timer"], capture_output=True, text=True)
print(f"Timer: {result.stdout.strip()}")

result = subprocess.run(["systemctl", "is-enabled", "master-ai-watchdog.timer"], capture_output=True, text=True)
print(f"Enabled: {result.stdout.strip()}")

# Check master-ai service stability
print("\n=== master-ai.service ===")
result = subprocess.run(["systemctl", "is-active", "master-ai.service"], capture_output=True, text=True)
print(f"Status: {result.stdout.strip()}")

# Check uptime
import os
os.chdir("/var/lib/homeassistant/share/master_ai")
with open("server.log") as f:
    lines = f.readlines()

# Count startups in last 5 minutes
from datetime import datetime, timedelta
now_str = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M")
startups_recent = [l for l in lines if "Master AI v8" in l and "started" in l]
print(f"\nTotal startups in log: {len(startups_recent)}")
if startups_recent:
    print(f"Last startup: {startups_recent[-1].strip()[:80]}")

# Check if radar started
started = [l for l in lines if "radar loop started" in l.lower()]
print(f"Radar 'started' count: {len(started)}")

# Check health endpoint
result = subprocess.run(["curl", "-s", "--max-time", "5", "http://localhost:9000/health"], capture_output=True, text=True, timeout=10)
print(f"\n/health: {result.stdout[:100]}")
