#!/usr/bin/env python3
"""Phase 1B: Fix audit_log route_type — add route_type to all 3 audit_log calls."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_text_patch import apply_patches

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

patches = [
    # 1. /ask endpoint audit_log — add route_type="llm_chat"
    (
        '    await audit_log(\n'
        '        task=body.message, actions=result.get("actions"), results=result.get("results"),\n'
        '        status=result.get("task_state", "complete"), duration=duration,\n'
        '        request_id=request_id, task_id=task_id\n'
        '    )',
        '    await audit_log(\n'
        '        task=body.message, actions=result.get("actions"), results=result.get("results"),\n'
        '        status=result.get("task_state", "complete"), duration=duration,\n'
        '        request_id=request_id, task_id=task_id,\n'
        '        route_type="llm_chat"\n'
        '    )'
    ),
    # 2. /agent endpoint audit_log — add route_type="llm_chat"
    (
        '    await audit_log(\n'
        '        task=body.message, actions=[], results=[],\n'
        '        status="ok", duration=duration, request_id=trace.request_id, task_id=task_id\n'
        '    )',
        '    await audit_log(\n'
        '        task=body.message, actions=[], results=[],\n'
        '        status="ok", duration=duration, request_id=trace.request_id, task_id=task_id,\n'
        '        route_type="llm_chat"\n'
        '    )'
    ),
    # 3. TG chat path audit_log — add route_type="tg_command"
    (
        '    await audit_log(\n'
        '        task=text, actions=result.get("actions"),\n'
        '        results=result.get("results"),\n'
        '        status="ok", duration=duration,\n'
        '        request_id=trace.request_id, task_id=task_id,\n'
        '    )',
        '    await audit_log(\n'
        '        task=text, actions=result.get("actions"),\n'
        '        results=result.get("results"),\n'
        '        status="ok", duration=duration,\n'
        '        request_id=trace.request_id, task_id=task_id,\n'
        '        route_type="tg_command"\n'
        '    )'
    ),
]

result = apply_patches(FILE, patches)
import json
print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
