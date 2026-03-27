"""
degraded_mode.py - Reliability & Degraded Mode for Master AI
Phase 3D: Track component health, enable graceful degradation
"""
import logging
import time
import json
import sqlite3
import os
from datetime import datetime

log = logging.getLogger("degraded_mode")

DB_PATH = "data/audit.db"

# Component health state
_state = {
    "ha": {"ok": True, "last_check": 0, "fail_count": 0, "last_error": ""},
    "anthropic": {"ok": True, "last_check": 0, "fail_count": 0, "last_error": ""},
    "internet": {"ok": True, "last_check": 0, "fail_count": 0, "last_error": ""},
    "db": {"ok": True, "last_check": 0, "fail_count": 0, "last_error": ""},
    "telegram": {"ok": True, "last_check": 0, "fail_count": 0, "last_error": ""},
}

_CHECK_INTERVAL = 120  # seconds between checks


def mark_ok(component):
    """Mark a component as healthy."""
    if component in _state:
        _state[component]["ok"] = True
        _state[component]["last_check"] = time.time()
        _state[component]["fail_count"] = 0
        _state[component]["last_error"] = ""

def mark_fail(component, error=""):
    """Mark a component as failed."""
    if component in _state:
        _state[component]["ok"] = False
        _state[component]["last_check"] = time.time()
        _state[component]["fail_count"] += 1
        _state[component]["last_error"] = str(error)[:200]
        log.warning(f"[Degraded] {component} FAILED ({_state[component]['fail_count']}x): {error}")

def is_ok(component):
    """Check if a component is healthy."""
    return _state.get(component, {}).get("ok", False)

def is_degraded():
    """Check if system is in degraded mode (any component down)."""
    return any(not s["ok"] for s in _state.values())

def get_status():
    """Get full health status of all components."""
    result = {}
    for name, s in _state.items():
        emoji = "\u2705" if s["ok"] else "\u274c"
        result[name] = {
            "ok": s["ok"],
            "emoji": emoji,
            "fail_count": s["fail_count"],
            "last_error": s["last_error"],
            "since": int(time.time() - s["last_check"]) if s["last_check"] > 0 else -1,
        }
    return result

def get_mode():
    """Get current operating mode."""
    down = [k for k, v in _state.items() if not v["ok"]]
    if not down:
        return "normal"
    if "anthropic" in down and "ha" in down:
        return "emergency"
    if "anthropic" in down:
        return "fallback_llm"
    if "ha" in down:
        return "cached_ha"
    if "internet" in down:
        return "local_only"
    return "partial"

def format_status():
    """Format status for TG display."""
    status = get_status()
    mode = get_mode()
    mode_emoji = {"normal": "\u2705", "emergency": "\U0001f6a8", "fallback_llm": "\u26a0\ufe0f",
                  "cached_ha": "\u26a0\ufe0f", "local_only": "\U0001f4f4", "partial": "\u26a0\ufe0f"}
    lines = [f"{mode_emoji.get(mode, '?')} *System Mode: {mode}*", ""]
    for name, s in status.items():
        age = f" ({s['since']}s ago)" if s['since'] >= 0 else ""
        err = f" - {s['last_error']}" if s['last_error'] else ""
        lines.append(f"{s['emoji']} {name}{age}{err}")
    return "\n".join(lines)

def check_db():
    """Check database health."""
    try:
        c = sqlite3.connect(DB_PATH, timeout=3)
        c.execute("SELECT 1")
        c.close()
        mark_ok("db")
        return True
    except Exception as e:
        mark_fail("db", str(e))
        return False

def should_use_cache(component):
    """Decide if we should use cached data instead of live."""
    s = _state.get(component, {})
    return not s.get("ok", True)

def get_degraded_response(component):
    """Get a user-friendly message when component is down."""
    msgs = {
        "ha": "\u26a0\ufe0f Home Assistant \u0645\u0648 \u0645\u062a\u0648\u0641\u0631 \u062d\u0627\u0644\u064a\u0627\u064b. \u0623\u0633\u062a\u062e\u062f\u0645 \u0628\u064a\u0627\u0646\u0627\u062a \u0645\u062e\u0632\u0646\u0629.",
        "anthropic": "\u26a0\ufe0f Anthropic API \u0645\u0648 \u0645\u062a\u0648\u0641\u0631. \u0623\u0633\u062a\u062e\u062f\u0645 OpenAI \u0628\u062f\u0627\u0644.",
        "internet": "\U0001f4f4 \u0627\u0644\u0625\u0646\u062a\u0631\u0646\u062a \u0645\u0642\u0637\u0648\u0639. \u0648\u0636\u0639 \u0645\u062d\u0644\u064a \u0641\u0642\u0637.",
        "db": "\u26a0\ufe0f \u0645\u0634\u0643\u0644\u0629 \u0628\u0627\u0644\u0642\u0627\u0639\u062f\u0629. \u0631\u062f\u0648\u062f \u0645\u062e\u062a\u0635\u0631\u0629.",
        "telegram": "\u26a0\ufe0f Telegram \u0645\u0648 \u0645\u062a\u0648\u0641\u0631.",
    }
    return msgs.get(component, f"\u26a0\ufe0f {component} unavailable")


def init():
    """Initialize - mark all as OK."""
    check_db()
    log.info(f"[DegradedMode] Initialized. Mode: {get_mode()}")
