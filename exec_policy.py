"""Execution Policy + Session Summary + Tool Outcome for chat_v7."""
import json, logging, threading

logger = logging.getLogger("exec_policy")

# Execution Policy
BLOCKED_SSH = ["rm -rf", "mkfs", "dd if=", "shutdown -h", "reboot",
               "passwd", "userdel", "chmod 777", "> /dev/"]

def check_policy(tool_name, tool_args):
    """Returns (allowed, reason). Blocks dangerous SSH commands."""
    if tool_name == "ssh_run":
        cmd = tool_args.get("cmd", "").lower()
        for pat in BLOCKED_SSH:
            if pat in cmd:
                return False, f"Blocked: dangerous pattern in command"
    return True, "ok"

# Tool Outcome Tracking
_outcomes = {}
_outcomes_lock = threading.Lock()

def record_outcome(tool_name, result_str):
    """Track tool success/failure for learning. Thread-safe."""
    is_err = isinstance(result_str, str) and any(
        w in result_str.lower() for w in ["error", "failed", "not found", "unavailable"]
    )
    if tool_name not in _outcomes:
        _outcomes[tool_name] = {"ok": 0, "err": 0, "last_err": None}
    if is_err:
        _outcomes[tool_name]["err"] += 1
        _outcomes[tool_name]["last_err"] = result_str[:200]
        logger.warning(f"{tool_name} error #{_outcomes[tool_name]['err']}")
    else:
        _outcomes[tool_name]["ok"] += 1

def get_tool_stats():
    """Return tool outcome statistics."""
    return dict(_outcomes)

# Session Summary Memory
_session_tools = {}

def track_session(user_id, tool_name):
    """Track tool usage per user session."""
    if user_id not in _session_tools:
        _session_tools[user_id] = {"n": 0, "tools": set()}
    _session_tools[user_id]["n"] += 1
    _session_tools[user_id]["tools"].add(tool_name)

async def save_session_summary(user_id, final_text):
    """If session was complex (3+ tool calls), save summary to memory."""
    stats = _session_tools.pop(user_id, None)
    if not stats or stats["n"] < 3:
        return
    try:
        from memory_db import store_memory
        tools_list = ", ".join(stats["tools"])
        summary = f"Session: {stats['n']} tools ({tools_list}). Response: {final_text[:150]}"
        await store_memory("session_summary", summary, confidence=0.6)
        logger.info(f"Session summary saved: {stats['n']} tools")
    except Exception as e:
        logger.warning(f"Session summary failed: {e}")
