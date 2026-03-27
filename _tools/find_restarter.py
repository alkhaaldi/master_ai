import subprocess

# Check watchdog_tg.sh
print("=== watchdog_tg.sh ===")
try:
    with open("/var/lib/homeassistant/share/master_ai/watchdog_tg.sh") as f:
        print(f.read())
except:
    print("not found")

# Check if watchdog or any script restarts master-ai
print("\n=== Searching for master-ai restart triggers ===")
result = subprocess.run(
    ["grep", "-r", "master-ai", "/var/lib/homeassistant/share/master_ai/scripts/"],
    capture_output=True, text=True, timeout=10
)
print(result.stdout or "nothing in scripts/")

# Check systemd timers
print("\n=== Active timers ===")
result = subprocess.run(
    ["systemctl", "list-timers", "--all", "--no-pager"],
    capture_output=True, text=True, timeout=10
)
for l in result.stdout.split("\n"):
    if l.strip():
        print(l[:150])

# Check who sent SIGTERM - look at audit log
print("\n=== Who is stopping the service? ===")
result = subprocess.run(
    ["journalctl", "-u", "master-ai.service", "--since", "2026-03-17 17:35", "--no-pager", "-o", "verbose"],
    capture_output=True, text=True, timeout=15
)
lines = result.stdout.split("\n")
for l in lines:
    if "Stop" in l or "stop" in l or "TRIGGER" in l or "trigger" in l or "_PID" in l:
        print(l[:200])
