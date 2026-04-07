"""Integration 3: Wire intent_state_machine + log_intent_audit into tg_intent_router."""
import sys, py_compile

FILE = "/home/pi/master_ai/tg_intent_router.py"
with open(FILE) as f:
    content = f.read()

# 1. Add imports at top (after existing imports)
old_import = "logger = logging.getLogger(\"tg_intent\")"
new_import = """logger = logging.getLogger("tg_intent")

# Integration: Tier3 intent state machine
try:
    from intent_state_machine import IntentContext, IntentState, log_intent_audit
    _INTENT_SM_OK = True
except ImportError:
    _INTENT_SM_OK = False"""

if old_import not in content:
    print("Could not find logger line")
    sys.exit(1)
content = content.replace(old_import, new_import, 1)

# 2. Wrap route_intent with IntentContext tracking
old_fn = '''async def route_intent(text: str) -> dict | None:
    """Try to route text to a fast-path handler.
    Returns dict {text, entities, action} or None."""
    # Step 9: Check learned aliases first'''

new_fn = '''async def route_intent(text: str) -> dict | None:
    """Try to route text to a fast-path handler.
    Returns dict {text, entities, action} or None."""
    # Intent state tracking (Tier3 #17)
    _ctx = None
    if _INTENT_SM_OK:
        import time as _t
        _ctx = IntentContext(message_id=str(int(_t.time()*1000)), raw_text=text)
    try:
        result = await _route_intent_inner(text)
        if _ctx:
            _ctx.intent = (result or {}).get("source", "unknown")
            _ctx.transition(IntentState.RESPONDED, f"{_ctx.duration_ms}ms")
        return result
    except Exception as _e:
        if _ctx:
            _ctx.error = str(_e)
            _ctx.transition(IntentState.FAILED, str(_e)[:80])
        raise
    finally:
        if _ctx:
            try:
                log_intent_audit(_ctx.to_audit_dict())
            except Exception:
                pass


async def _route_intent_inner(text: str) -> dict | None:
    """Inner routing logic (unwrapped)."""
    # Step 9: Check learned aliases first'''

content = content.replace(old_fn, new_fn, 1)

with open(FILE, "w") as f:
    f.write(content)

try:
    py_compile.compile(FILE, doraise=True)
    print("Integration 3 DONE — syntax OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
    sys.exit(1)
