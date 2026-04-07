"""Clean integration 1: Add imports + cursor tracking to stock_radar.py without breaking structure."""
import sys, py_compile

FILE = "/home/pi/master_ai/stock_radar.py"
with open(FILE) as f:
    content = f.read()

# 1. Add imports
old = "from datetime import datetime, timedelta\nfrom pathlib import Path"
new = """from datetime import datetime, timedelta
from pathlib import Path

# Integration: Tier2/3 modules
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

content = content.replace(old, new, 1)

# 2. Add _radar_running tracking to radar_loop
old_loop = """    logger.info("Stock radar loop started")
    await asyncio.sleep(60)  # wait for system startup
    while True:
        try:"""
new_loop = """    _radar_running = True
    _radar_cycle_count = 0
    logger.info("Stock radar loop started")
    await asyncio.sleep(60)  # wait for system startup
    while True:
        try:"""
content = content.replace(old_loop, new_loop, 1)

# 3. Add cursor update after alert sent
old_alert = '                            logger.info(f"Radar alert sent: {sym} {signal}")'
new_alert = """                            logger.info(f"Radar alert sent: {sym} {signal}")
                            if _signal_cursor:
                                _signal_cursor.set(f"{sym}:{signal}:{result['candle_time']}")"""
content = content.replace(old_alert, new_alert, 1)

# 4. Add cycle counter + finally at the end of the while loop
old_tail = """        except Exception as e:
            logger.error(f"Radar loop error (non-fatal): {e}")
            await asyncio.sleep(120)


# ═══ Telegram Command Handlers ═══"""
new_tail = """            _radar_cycle_count += 1
        except Exception as e:
            logger.error(f"Radar loop error (non-fatal): {e}")
            await asyncio.sleep(120)


# ═══ Telegram Command Handlers ═══"""
content = content.replace(old_tail, new_tail, 1)

with open(FILE, "w") as f:
    f.write(content)

try:
    py_compile.compile(FILE, doraise=True)
    print("Integration 1 DONE — syntax OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
    sys.exit(1)
