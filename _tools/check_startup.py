import os
os.chdir("/var/lib/homeassistant/share/master_ai")

# Read master-ai.service
try:
    with open("/etc/systemd/system/master-ai.service") as f:
        print("=== master-ai.service ===")
        print(f.read())
except Exception as e:
    print(f"Error: {e}")

# Count startup messages with timestamps
print("\n=== Startup timestamps (server.log) ===")
with open("server.log") as f:
    lines = f.readlines()

startups = [(i,l.strip()) for i,l in enumerate(lines) if "Master AI v8" in l and "started" in l]
print(f"Total startups in log: {len(startups)}")
for i, (ln, l) in enumerate(startups[-10:]):
    print(f"  {l[:100]}")

# Check time gaps between radar scheduled messages
print("\n=== Radar scheduled gaps ===")
sched = [l.strip() for l in lines if "radar loop scheduled" in l.lower()]
if len(sched) >= 4:
    for s in sched[-6:]:
        print(f"  {s[:80]}")
