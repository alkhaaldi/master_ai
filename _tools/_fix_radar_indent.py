"""Fix the broken try/while/try nesting in stock_radar.py from Tier1 #6."""

FILE = "/home/pi/master_ai/stock_radar.py"
with open(FILE) as f:
    content = f.read()

# The broken pattern:
#     try:
#         while True:
#             try:
#             # Feature flag check
# Should be:
#     try:
#       while True:
#         try:
#             # Feature flag check

broken = """    try:
        while True:
            try:
            # Feature flag check"""

fixed = """    try:
      while True:
        try:
            # Feature flag check"""

if broken in content:
    content = content.replace(broken, fixed, 1)
    print("Fixed outer try/while/try nesting")
else:
    print("Pattern not found (may already be different)")

# Also fix the finally block indentation — find it
# The finally should match the outer try:
# "    finally:" (4 spaces, matching "    try:")
broken_finally = """            _radar_cycle_count += 1
            except Exception as e:
                logger.error(f"Radar loop error (non-fatal): {e}")
                await asyncio.sleep(120)
    finally:
        _radar_running = False"""

fixed_finally = """            _radar_cycle_count += 1
          except Exception as e:
            logger.error(f"Radar loop error (non-fatal): {e}")
            await asyncio.sleep(120)
    finally:
        _radar_running = False"""

if broken_finally in content:
    content = content.replace(broken_finally, fixed_finally, 1)
    print("Fixed finally block indentation")
else:
    # Try different pattern
    print("Finally pattern not found, checking alt...")

with open(FILE, "w") as f:
    f.write(content)

# Verify
import py_compile
try:
    py_compile.compile(FILE, doraise=True)
    print("SYNTAX OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
