import os
os.chdir("/var/lib/homeassistant/share/master_ai")

# Check all log files for radar
for logfile in ["server.log", "server.log.1", "server.log.2"]:
    try:
        with open(logfile, "r") as f:
            lines = f.readlines()
        radar = [l.strip() for l in lines if "radar" in l.lower() or "Radar" in l or "market" in l.lower()]
        if radar:
            print(f"\n=== {logfile} ({len(radar)} radar lines) ===")
            for l in radar[-20:]:
                print(l[:250])
    except:
        pass

# Check today specifically
print("\n=== TODAY's RADAR ACTIVITY ===")
for logfile in ["server.log", "server.log.1"]:
    try:
        with open(logfile, "r") as f:
            lines = f.readlines()
        today = [l.strip() for l in lines if "2026-03-17" in l and ("radar" in l.lower() or "check_symbol" in l.lower() or "scan" in l.lower() or "market" in l.lower() or "tvDatafeed" in l.lower() or "tv_data" in l.lower())]
        if today:
            print(f"\n{logfile}:")
            for l in today[:30]:
                print(l[:250])
    except:
        pass
