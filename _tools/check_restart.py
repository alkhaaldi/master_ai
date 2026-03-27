import os
os.chdir("/var/lib/homeassistant/share/master_ai")

# 1. Check journalctl for restart reasons
import subprocess
result = subprocess.run(
    ["journalctl", "-u", "master-ai.service", "--since", "2026-03-17 17:00", "--no-pager", "-n", "100"],
    capture_output=True, text=True, timeout=15
)
lines = result.stdout.split("\n")
print("=== journalctl (last 50 lines) ===")
for l in lines[-50:]:
    print(l[:200])

# 2. Check if ctl.sh or restart script has a loop
print("\n=== ctl.sh ===")
try:
    with open("ctl.sh") as f:
        print(f.read())
except:
    print("not found")

# 3. Check crontab
print("\n=== crontab ===")
result2 = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
print(result2.stdout or "empty")
if result2.stderr:
    print("stderr:", result2.stderr)
