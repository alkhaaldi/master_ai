"""Trigger daily snapshot refresh."""
import sys, os, traceback, json
sys.path.insert(0, '/home/pi/master_ai')
os.chdir('/home/pi/master_ai')

try:
    from stock_radar import refresh_daily_snapshot
    r = refresh_daily_snapshot()
    print("RESULT:", json.dumps(r, default=str))
except Exception as e:
    traceback.print_exc()
    print("FAIL:", e)
