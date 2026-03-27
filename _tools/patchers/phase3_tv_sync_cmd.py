#!/usr/bin/env python3
"""Phase 3b: Add /tv_sync command handler."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_text_patch import apply_patch

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

OLD = '''    if cmd == "/tv_stats":
        if TV_BRIDGE_OK:
            return handle_tv_stats()
        return "TV bridge not loaded"

    if cmd == "/kpi":'''

NEW = '''    if cmd == "/tv_stats":
        if TV_BRIDGE_OK:
            return handle_tv_stats()
        return "TV bridge not loaded"
    if cmd == "/tv_sync":
        if TV_BRIDGE_OK:
            return sync_tv_from_radar()
        return "TV bridge not loaded"

    if cmd == "/kpi":'''

result = apply_patch(FILE, OLD, NEW, backup=True)
import json
print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
