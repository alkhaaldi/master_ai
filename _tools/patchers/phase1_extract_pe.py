#!/usr/bin/env python3
"""Phase 1: Replace inline PE+AS code with import from priority_engine.py.
Removes lines 7818-8855 (PE section header + all PE/AS functions) and replaces
with a compact import block."""
import os, sys, re

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

# Read original
with open(FILE, "r", encoding="utf-8") as f:
    content = f.read()

# Backup
import shutil, time
bak = FILE + f".bak.pe_extract_{int(time.time())}"
shutil.copy2(FILE, bak)
print(f"Backup: {bak}")

# Find the PE section start marker and the dashboard section start marker
pe_start_marker = "# ═══════════════════════════════════════════════════\n# PRIORITY ENGINE — Cross-domain priority ranking\n# ═══════════════════════════════════════════════════\n"
dash_start_marker = "\n# ═══════════════════════════════════════════════════\n# HA DASHBOARD ENDPOINT — Single call for all sensors\n# ═══════════════════════════════════════════════════\n"

pe_start = content.find(pe_start_marker)
dash_start = content.find(dash_start_marker)

if pe_start == -1:
    print("ERROR: Could not find PE section start marker")
    sys.exit(1)
if dash_start == -1:
    print("ERROR: Could not find dashboard section start marker")
    sys.exit(1)

print(f"PE section: chars {pe_start}..{dash_start}")

# Replace PE section with import
replacement = """# ═══════════════════════════════════════════════════
# PRIORITY ENGINE — imported from priority_engine.py
# ═══════════════════════════════════════════════════
from priority_engine import (
    build_priority_engine, build_assistant_surface,
    _pe_get_extended_snapshot, _pe_get_radar_snapshot,
    set_inbox_cache_ref as _pe_set_inbox_cache_ref,
)

"""

new_content = content[:pe_start] + replacement + content[dash_start+1:]

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
    print("Reverting...")
    shutil.copy2(bak, FILE)
    os.unlink(tmp_path)
    sys.exit(1)
os.unlink(tmp_path)

# Write
with open(FILE, "w", encoding="utf-8") as f:
    f.write(new_content)

# Count lines removed
old_lines = content.count("\n")
new_lines = new_content.count("\n")
print(f"Lines: {old_lines} -> {new_lines} (removed {old_lines - new_lines})")
print("SUCCESS")
