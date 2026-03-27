import subprocess

# Check watchdog service and timer
for unit in ["master-ai-watchdog.service", "master-ai-watchdog.timer"]:
    print(f"=== {unit} ===")
    result = subprocess.run(["systemctl", "cat", unit], capture_output=True, text=True, timeout=5)
    print(result.stdout or result.stderr)
    print()

# Also check self_heal_check.sh since it does restart
print("=== self_heal_check.sh ===")
try:
    with open("/var/lib/homeassistant/share/master_ai/scripts/self_heal_check.sh") as f:
        print(f.read())
except Exception as e:
    print(f"Error: {e}")
