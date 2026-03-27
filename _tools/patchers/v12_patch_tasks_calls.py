#!/usr/bin/env python3
"""Fix: update /tasks and /task handlers to use handle_tasks_command."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_text_patch import apply_patch

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

OLD = '''    if cmd == "/tasks" or cmd.startswith("/tasks "):
        args = text.strip()[6:].strip() if len(text.strip()) > 6 else ""
        return await cmd_tasks(args)
    if cmd.startswith("/task "):
        sub = text.strip()[6:].strip()
        if sub.startswith("add "):
            return await cmd_task_add(sub[4:])
        elif sub.startswith("done "):
            return await cmd_task_done(sub[5:])
        else:
            return "الاستخدام: /task add <عنوان> | /task done <رقم>"'''

NEW = '''    if cmd == "/tasks" or cmd.startswith("/tasks "):
        if not TG_TASKS_OK:
            return "❌ tasks module not loaded"
        args = text.strip()[6:].strip() if len(text.strip()) > 6 else ""
        return handle_tasks_command(args)
    if cmd.startswith("/task "):
        if not TG_TASKS_OK:
            return "❌ tasks module not loaded"
        sub = text.strip()[6:].strip()
        if sub.startswith("add "):
            return str(llm_tool_task_create(title=sub[4:].strip()))
        elif sub.startswith("done "):
            return str(llm_tool_task_update(task_id=int(sub[5:].strip()), status="done"))
        else:
            return "الاستخدام: /task add <عنوان> | /task done <رقم>"'''

result = apply_patch(FILE, OLD, NEW, backup=True)
import json
print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
