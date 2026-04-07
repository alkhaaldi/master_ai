"""Patch brain_core.py to support scope filtering in manifest (Tier3 #19)."""
import sys

FILE = "/home/pi/master_ai/brain_core.py"
with open(FILE) as f:
    content = f.read()

# Replace get_observation_manifest signature and body
old_sig = 'def get_observation_manifest(category: str = None, max_items: int = 200) -> list:'
new_sig = 'def get_observation_manifest(category: str = None, scope: str = None, max_items: int = 200) -> list:'

if old_sig not in content:
    print("Could not find get_observation_manifest signature")
    sys.exit(1)

content = content.replace(old_sig, new_sig, 1)

# Replace the SQL query section to support scope
old_query_block = '''    try:
        conn = sqlite3.connect(_AUDIT_DB, timeout=5)
        conn.row_factory = sqlite3.Row
        if category:
            rows = conn.execute(
                "SELECT id, category, type, SUBSTR(content, 1, 100) AS summary, "
                "COALESCE(updated_at, created_at) AS ts "
                "FROM memory WHERE active=1 AND category=? "
                "ORDER BY COALESCE(updated_at, created_at) DESC LIMIT ?",
                (category, max_items)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, category, type, SUBSTR(content, 1, 100) AS summary, "
                "COALESCE(updated_at, created_at) AS ts "
                "FROM memory WHERE active=1 "
                "ORDER BY COALESCE(updated_at, created_at) DESC LIMIT ?",
                (max_items,)
            ).fetchall()'''

new_query_block = '''    try:
        conn = sqlite3.connect(_AUDIT_DB, timeout=5)
        conn.row_factory = sqlite3.Row
        where_parts = ["active=1"]
        params = []
        if category:
            where_parts.append("category=?")
            params.append(category)
        if scope:
            where_parts.append("scope=?")
            params.append(scope)
        where_clause = " AND ".join(where_parts)
        params.append(max_items)
        rows = conn.execute(
            f"SELECT id, category, type, SUBSTR(content, 1, 100) AS summary, "
            f"COALESCE(updated_at, created_at) AS ts, "
            f"COALESCE(scope, 'global') AS scope "
            f"FROM memory WHERE {where_clause} "
            f"ORDER BY COALESCE(updated_at, created_at) DESC LIMIT ?",
            params
        ).fetchall()'''

if old_query_block not in content:
    print("Could not find old query block")
    sys.exit(1)

content = content.replace(old_query_block, new_query_block, 1)

# Update the dict comprehension to include scope
old_dict = '''"age_str": memory_age(r["ts"]),
                "timestamp": r["ts"],'''
new_dict = '''"age_str": memory_age(r["ts"]),
                "timestamp": r["ts"],
                "scope": r["scope"] if "scope" in r.keys() else "global",'''

content = content.replace(old_dict, new_dict, 1)

with open(FILE, "w") as f:
    f.write(content)

print("PATCHED brain_core.py with scope support OK")
