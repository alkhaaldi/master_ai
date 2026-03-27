#!/usr/bin/env python3
"""Replace adhan_play_and_resume in scripts.yaml with v3 from adhan_script_v3.yaml"""
import yaml, sys, os, re

SCRIPTS_FILE = "/var/lib/homeassistant/homeassistant/scripts.yaml"
V3_FILE = "/var/lib/homeassistant/share/master_ai/_tools/adhan_script_v3.yaml"

# Read the v3 script file, skip comment lines at top
with open(V3_FILE, 'r', encoding='utf-8') as f:
    v2_raw = f.read()

# Extract just the YAML block (skip leading comments)
v2_lines = v2_raw.split('\n')
start_idx = None
for i, line in enumerate(v2_lines):
    if line.startswith('adhan_play_and_resume:'):
        start_idx = i
        break

if start_idx is None:
    print("ERROR: Could not find adhan_play_and_resume in v2 file")
    sys.exit(1)

v2_block = '\n'.join(v2_lines[start_idx:]).rstrip() + '\n'
print(f"V2 block: {len(v2_block)} chars, starts at line {start_idx}")

# Read current scripts.yaml
with open(SCRIPTS_FILE, 'r', encoding='utf-8') as f:
    scripts_raw = f.read()

# Find the old adhan_play_and_resume block
# It starts with "adhan_play_and_resume:" and ends before the next top-level key or EOF
lines = scripts_raw.split('\n')
block_start = None
block_end = None

for i, line in enumerate(lines):
    if line.startswith('adhan_play_and_resume:'):
        block_start = i
    elif block_start is not None and i > block_start:
        # A new top-level key (non-indented, non-comment, non-empty)
        if line and not line[0].isspace() and not line.startswith('#'):
            block_end = i
            break

if block_start is None:
    print("ERROR: Could not find adhan_play_and_resume in scripts.yaml")
    sys.exit(1)

if block_end is None:
    block_end = len(lines)

# Also include the comment line above if it's the adhan comment
if block_start > 0 and '=== Adhan' in lines[block_start - 1]:
    block_start -= 1

print(f"Old block: lines {block_start}-{block_end} ({block_end - block_start} lines)")

# Build new content
new_lines = lines[:block_start]
new_lines.append('# === Adhan Automation Script v3 (2026-03-23) ===')
# Don't add extra newline if previous line is already empty
new_content = '\n'.join(new_lines)
if not new_content.endswith('\n'):
    new_content += '\n'
new_content += v2_block

# Add remaining content after old block
remaining = lines[block_end:]
if remaining:
    remaining_text = '\n'.join(remaining)
    if remaining_text.strip():
        new_content += remaining_text
        if not new_content.endswith('\n'):
            new_content += '\n'

# Validate YAML before writing
try:
    yaml.safe_load(new_content)
    print("YAML validation: OK")
except Exception as e:
    print(f"YAML validation FAILED: {e}")
    sys.exit(1)

# Write back
with open(SCRIPTS_FILE, 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f"OK: Replaced adhan_play_and_resume in scripts.yaml ({len(new_content)} chars)")

# Final verify
with open(SCRIPTS_FILE, 'r', encoding='utf-8') as f:
    verify = f.read()
try:
    yaml.safe_load(verify)
    print("Post-write YAML check: OK")
except Exception as e:
    print(f"Post-write YAML ERROR: {e}")
    sys.exit(1)

# Check key changes are present
checks = ['repeat_1:', 'repeat_set', 'seconds: 245']
for c in checks:
    if c in verify:
        print(f"  CHECK: '{c}' found")
    else:
        print(f"  MISSING: '{c}' NOT found!")
        sys.exit(1)

print("\nDONE - v3 deployed successfully")
