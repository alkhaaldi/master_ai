import subprocess, sys
result = subprocess.run(
    ["journalctl", "-u", "master-ai.service", "--since", "2026-03-17 06:00", "--no-pager"],
    capture_output=True, text=True, timeout=15
)
lines = result.stdout.split("\n")
radar_lines = [l for l in lines if "radar" in l.lower() or "Radar" in l]
for l in radar_lines[-30:]:
    print(l)
if not radar_lines:
    print("NO RADAR LOGS FOUND")
    # Show last 10 lines of server log
    import os
    os.chdir("/var/lib/homeassistant/share/master_ai")
    with open("server.log", "r") as f:
        for line in f.readlines()[-20:]:
            if "radar" in line.lower():
                print("LOG:", line.strip())
