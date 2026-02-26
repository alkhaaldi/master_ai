#!/usr/bin/env python3
"""Apply minimal patches to server.py"""
import re

with open('server.py', 'r') as f:
    code = f.read()

# Patch 1: Remove win endpoints from OPEN_PATHS
old_open = '    OPEN_PATHS = {"/health", "/win/poll", "/win/report", "/win/register", "/panel"}'
new_open = '    OPEN_PATHS = {"/health", "/panel"}'
assert old_open in code, "OPEN_PATHS line not found"
code = code.replace(old_open, new_open, 1)
print('Patch 1 OK: OPEN_PATHS hardened')

# Patch 2: Add /brain/diag endpoint after feedback endpoint
marker = '    return {"success": ok}\n\n\n@app.get("/health")'
assert marker in code, f"Marker not found for brain/diag insertion"

brain_diag = '''    return {"success": ok}


@app.get("/brain/diag")
async def brain_diag_endpoint():
    """Brain diagnostics: DB state, learning stats, errors."""
    import sqlite3 as _sq, os as _os
    db_path = str(BASE_DIR / "data" / "audit.db")
    brain_db = str(BASE_DIR / "data" / "brain.db")
    result = {
        "brain_db_exists": _os.path.exists(brain_db),
        "brain_db_size": _os.path.getsize(brain_db) if _os.path.exists(brain_db) else 0,
        "brain_db_note": "orphan file - learning uses audit.db",
    }
    try:
        conn = _sq.connect(db_path)
        result["memory_count"] = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
        result["audit_db_ok"] = True
        conn.close()
    except Exception as e:
        result["audit_db_ok"] = False
        result["error"] = str(e)
    if BRAIN_AVAILABLE:
        result["brain_module"] = "loaded"
        try:
            result["brain_stats"] = get_brain_stats()
        except Exception as e:
            result["brain_stats_error"] = str(e)
    else:
        result["brain_module"] = "not loaded"
    return result


@app.get("/health")'''
code = code.replace(marker, brain_diag, 1)
print('Patch 2 OK: /brain/diag endpoint added')

with open('server.py', 'w') as f:
    f.write(code)
print('server.py updated successfully')
