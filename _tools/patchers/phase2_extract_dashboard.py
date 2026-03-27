#!/usr/bin/env python3
"""Phase 2: Replace inline dashboard endpoints with import from dashboard_api.py Router."""
import os, sys, shutil, time as _time

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

with open(FILE, "r", encoding="utf-8") as f:
    content = f.read()

# Backup
bak = FILE + f".bak.dash_extract_{int(_time.time())}"
shutil.copy2(FILE, bak)
print(f"Backup: {bak}")

# Find markers
dash_start = "# ═══════════════════════════════════════════════════\n# HA DASHBOARD ENDPOINT — Single call for all sensors\n# ═══════════════════════════════════════════════════\n"
# After dashboard/extended, the file ends. Let's find the position after ha_dashboard_extended returns.
# The last line of dashboard section should be followed by nothing or end-of-file

idx_dash = content.find(dash_start)
if idx_dash == -1:
    print("ERROR: Could not find dashboard section marker")
    sys.exit(1)

# Find the end: look for next top-level section after the dashboard code
# The dashboard/extended endpoint ends with "    return data\n" followed by end of file or next section
# Let's find the last "return data" in the dashboard/extended function
# The file should end after dashboard/extended since we already extracted PE

# Search for end of ha_dashboard_extended by finding the last occurrence of the function
lines = content.split("\n")
dash_start_line = content[:idx_dash].count("\n")
print(f"Dashboard section starts at line {dash_start_line + 1}")

# Find end of last dashboard function - it's the end of ha_dashboard_extended
# which should be near the end of the file
end_line = len(lines) - 1
# Walk backwards from end to find the last non-empty line
while end_line > 0 and not lines[end_line].strip():
    end_line -= 1

# The dashboard section goes from idx_dash to end of file
# But we need to check if there's code after dashboard/extended
after_dash = content[idx_dash:]
print(f"Dashboard section is {len(after_dash)} chars, {after_dash.count(chr(10))} lines")

# The replacement: import router and wire it
replacement = """# ═══════════════════════════════════════════════════
# HA DASHBOARD — imported from dashboard_api.py (Router)
# ═══════════════════════════════════════════════════
from dashboard_api import router as dashboard_router, init_dashboard_context
"""

new_content = content[:idx_dash] + replacement

# Syntax check
import py_compile, tempfile
with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
    tmp.write(new_content)
    tmp_path = tmp.name
try:
    py_compile.compile(tmp_path, doraise=True)
    print("Syntax check: OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
    shutil.copy2(bak, FILE)
    os.unlink(tmp_path)
    sys.exit(1)
os.unlink(tmp_path)

with open(FILE, "w", encoding="utf-8") as f:
    f.write(new_content)

old_lines = content.count("\n")
new_lines = new_content.count("\n")
print(f"Lines: {old_lines} -> {new_lines} (removed {old_lines - new_lines})")
print("SUCCESS")
