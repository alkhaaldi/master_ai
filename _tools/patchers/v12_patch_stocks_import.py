#!/usr/bin/env python3
"""Fix: remove tg_alert_loop from tg_stocks import (wrong name, already imported from tg_alerts)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_text_patch import apply_patch

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

OLD = "    from tg_stocks import cmd_stocks, cmd_price, tg_alert_loop"
NEW = "    from tg_stocks import cmd_stocks, cmd_price"

result = apply_patch(FILE, OLD, NEW, backup=True)
import json
print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
