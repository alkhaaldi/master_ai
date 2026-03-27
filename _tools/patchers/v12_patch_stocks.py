#!/usr/bin/env python3
"""Fix: add TG_STOCKS_OK guard to /stocks handler at line 5416."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_text_patch import apply_patch

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

OLD = '''    if cmd == "/stocks":
        return await cmd_stocks()'''

NEW = '''    if cmd == "/stocks":
        if not TG_STOCKS_OK:
            return "❌ stocks module not loaded"
        return await cmd_stocks()'''

result = apply_patch(FILE, OLD, NEW, backup=True)
import json
print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
