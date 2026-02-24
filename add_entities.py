import json

# Load entity map and build compact reference
with open('/home/pi/master_ai/entity_map.json') as f:
    emap = json.load(f)

# Build compact string: only lights/covers/climate per room (skip backlight/duplicates)
lines = []
for room in sorted(emap):
    items = emap[room]
    # Filter: only real controllable entities (no backlight, no duplicates)
    filtered = []
    seen = set()
    for item in items:
        eid, name = item.split('=', 1)
        if 'backlight' in eid.lower() or 'backlight' in name.lower():
            continue
        domain = eid.split('.')[0]
        if eid not in seen:
            seen.add(eid)
            short = eid.split('.',1)[1] if '.' in eid else eid
            filtered.append(f"{eid}({name})")
    if filtered:
        lines.append(f"{room}: {', '.join(filtered)}")

entity_ref = chr(10).join(lines)

# Read server.py
path = "/home/pi/master_ai/server.py"
with open(path) as f:
    content = f.read()

# Find PLANNER_SYSTEM_PROMPT and add entity reference
old_end = 'Return ONLY a JSON array. No markdown."""'
new_end = f"""IMPORTANT: Use ONLY these real entity_ids. NEVER invent entity names.
ENTITY REFERENCE:
{entity_ref}

When user says a room name in Arabic or English, match it to the entities above.
If unsure which entity, use ha_get_state with entity_id="*" first to check.
Return ONLY a JSON array. No markdown.\"\"\""""

if old_end in content:
    content = content.replace(old_end, new_end)
    with open(path, "w") as f:
        f.write(content)
    import py_compile
    try:
        py_compile.compile(path, doraise=True)
        print("OK")
    except py_compile.PyCompileError as e:
        print(f"ERR: {e}")
else:
    print("NOT_FOUND")
