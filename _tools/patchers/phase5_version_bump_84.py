#!/usr/bin/env python3
"""Phase 5: Version bump 8.3.0 -> 8.4.0."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_text_patch import apply_patch

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

result = apply_patch(FILE, 'VERSION = "8.3.0"', 'VERSION = "8.4.0"', backup=True)
import json
print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
