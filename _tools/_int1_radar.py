"""Integration 1: Wire coalesced_executor + processing_cursor into stock_radar.py"""
import sys

FILE = "/home/pi/master_ai/stock_radar.py"
with open(FILE) as f:
    content = f.read()

# 1. Add imports after existing imports
old_imports = "from datetime import datetime, timedelta\nfrom pathlib import Path"
new_imports = """from datetime import datetime, timedelta
from pathlib import Path

# Tier2/3 integrations
try:
    from coalesced_executor import CoalescedExecutor
    _radar_coalesced = CoalescedExecutor("radar_refresh")
except ImportError:
    _radar_coalesced = None
try:
    from processing_cursor import ProcessingCursor
    _signal_cursor = ProcessingCursor("radar_last_signal_id", cursor_type="id")
except ImportError:
    _signal_cursor = None"""

if old_imports not in content:
    print("Could not find imports marker")
    sys.exit(1)
content = content.replace(old_imports, new_imports, 1)

# 2. After _record_signal, update cursor
old_record = '                        _record_signal(sym, signal, result["candle_time"],'
new_record = """                        _record_signal(sym, signal, result["candle_time"],"""

# Actually, safest approach: just update the cursor after each signal alert is sent
old_alert_sent = '                            logger.info(f"Radar alert sent: {sym} {signal}")'
new_alert_sent = """                            logger.info(f"Radar alert sent: {sym} {signal}")
                            if _signal_cursor:
                                _signal_cursor.set(f"{sym}:{signal}:{result['candle_time']}")"""

if old_alert_sent in content:
    content = content.replace(old_alert_sent, new_alert_sent, 1)
    print("Wired processing_cursor into signal alerts")
else:
    print("WARN: Could not find alert sent line for cursor wiring")

with open(FILE, "w") as f:
    f.write(content)

print("Integration 1 DONE")
