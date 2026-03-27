#!/usr/bin/env python3
"""Fix: separate tg_tasks and tg_stocks imports to prevent cascading failure."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_text_patch import apply_patch

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

OLD = """try:
    from tg_tasks import cmd_tasks, cmd_task_add, cmd_task_done
    from tg_stocks import cmd_stocks, cmd_price, tg_alert_loop
    TG_STOCKS_OK = True
except Exception as _e:
    TG_STOCKS_OK = False
    logging.getLogger("master_ai").warning("tg_stocks not loaded: %s", _e)"""

NEW = """# -- tg_tasks --
TG_TASKS_OK = False
try:
    from tg_tasks import handle_tasks_command, llm_tool_task_create, llm_tool_task_update
    TG_TASKS_OK = True
except Exception as _e:
    logging.getLogger("master_ai").warning("tg_tasks not loaded: %s", _e)

# -- tg_stocks --
TG_STOCKS_OK = False
try:
    from tg_stocks import cmd_stocks, cmd_price, tg_alert_loop
    TG_STOCKS_OK = True
except Exception as _e:
    logging.getLogger("master_ai").warning("tg_stocks not loaded: %s", _e)"""

result = apply_patch(FILE, OLD, NEW, backup=True)
import json
print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
