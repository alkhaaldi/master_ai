#!/usr/bin/env python3
"""Phase 1: Normalize price to fils in webhook handler."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_text_patch import apply_patch

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

OLD = '            _price = payload.get("price", "0")'
NEW = ('            _price = payload.get("price", "0")\n'
       '            try:\n'
       '                from tv_data import _normalize_price_to_fils\n'
       '                _price = str(_normalize_price_to_fils(float(_price))) if _price else "0"\n'
       '            except Exception:\n'
       '                pass')

result = apply_patch(FILE, OLD, NEW, backup=True)
import json
print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
