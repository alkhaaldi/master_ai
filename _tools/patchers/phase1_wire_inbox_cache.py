#!/usr/bin/env python3
"""Wire inbox cache ref to priority_engine after ha_dashboard_extended is defined."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_text_patch import apply_patch

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

OLD = '@app.get("/dashboard/extended")\nasync def ha_dashboard_extended():'
NEW = '@app.get("/dashboard/extended")\nasync def ha_dashboard_extended():'  # same, we'll add after

# Actually, add the wiring right after the PE import block
OLD2 = """from priority_engine import (
    build_priority_engine, build_assistant_surface,
    _pe_get_extended_snapshot, _pe_get_radar_snapshot,
    set_inbox_cache_ref as _pe_set_inbox_cache_ref,
)"""

NEW2 = """from priority_engine import (
    build_priority_engine, build_assistant_surface,
    _pe_get_extended_snapshot, _pe_get_radar_snapshot,
    set_inbox_cache_ref as _pe_set_inbox_cache_ref,
)
# Note: _pe_set_inbox_cache_ref(ha_dashboard_extended) is called
# after ha_dashboard_extended is defined (see below /dashboard/extended)"""

result = apply_patch(FILE, OLD2, NEW2, backup=True)
import json
print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))

# Now add the actual wiring call right after the dashboard/extended function is fully defined
# Find the end of the function and add after it. Simpler: add it in the lifespan startup.
