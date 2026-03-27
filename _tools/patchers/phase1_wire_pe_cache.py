#!/usr/bin/env python3
"""Wire priority_engine inbox cache ref in lifespan startup."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_text_patch import apply_patch

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

OLD = '    logger.info(f"Master AI v{VERSION} started")'
NEW = '    _pe_set_inbox_cache_ref(ha_dashboard_extended)\n    logger.info(f"Master AI v{VERSION} started")'

result = apply_patch(FILE, OLD, NEW, backup=True)
import json
print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
