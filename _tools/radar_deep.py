import os
os.chdir("/var/lib/homeassistant/share/master_ai")

# 1. Check if "Stock radar loop started" ever appears (from inside radar_loop)
print("=== Looking for 'loop started' vs 'loop scheduled' ===")
for logfile in ["server.log", "server.log.1", "server.log.2"]:
    try:
        with open(logfile) as f:
            lines = f.readlines()
        started = [l.strip() for l in lines if "radar loop started" in l.lower()]
        scheduled = [l.strip() for l in lines if "radar loop scheduled" in l.lower()]
        print(f"{logfile}: scheduled={len(scheduled)}, started={len(started)}")
        if started:
            for s in started[-5:]:
                print(f"  STARTED: {s[:150]}")
    except:
        pass

# 2. Check for errors/exceptions near radar
print("\n=== Errors in server.log today ===")
try:
    with open("server.log") as f:
        lines = f.readlines()
    errors = [l.strip() for l in lines if ("ERROR" in l or "exception" in l.lower() or "traceback" in l.lower()) and "2026-03-17" in l]
    for e in errors[-15:]:
        print(e[:250])
    if not errors:
        print("No errors today")
except Exception as e:
    print(f"Error: {e}")

# 3. Check how many times lifespan/startup runs
print("\n=== Startup events ===")
try:
    startups = [l.strip() for l in lines if "Master AI v8" in l or "lifespan" in l.lower() or "Schema up to date" in l or "migration" in l.lower()]
    for s in startups[-10:]:
        print(s[:200])
except:
    pass
