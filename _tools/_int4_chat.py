"""Integration 4: Wire context_manager into chat_v7.py."""
import sys, py_compile

FILE = "/home/pi/master_ai/chat_v7.py"
with open(FILE) as f:
    content = f.read()

# 1. Add import at top
old_log = 'logger = logging.getLogger("chat_v7")'
if old_log not in content:
    old_log = 'logger = logging.getLogger(__name__)'
if old_log not in content:
    # Find any logger line
    import re
    m = re.search(r'logger = logging\.getLogger\([^)]+\)', content)
    if m:
        old_log = m.group(0)
    else:
        print("Could not find logger line")
        sys.exit(1)

new_log = old_log + """

# Integration: context management (Tier3 #15)
try:
    from context_manager import manage_context as _manage_ctx
    _CTX_MGR_OK = True
except ImportError:
    _CTX_MGR_OK = False"""

content = content.replace(old_log, new_log, 1)

# 2. Add context management before the LLM call
# Find the messages copy + loop
old_call = """    messages = list(history)  # copy for this request
    tools_used = []
    tool_results = []

    for _ in range(MAX_ROUNDS):
        try:
            resp = await client.messages.create("""

new_call = """    messages = list(history)  # copy for this request
    # Context management: trim/compress if too large (Tier3 #15)
    if _CTX_MGR_OK and len(messages) > 12:
        try:
            messages = await _manage_ctx(messages, anthropic_client=client)
        except Exception:
            pass
    tools_used = []
    tool_results = []

    for _ in range(MAX_ROUNDS):
        try:
            resp = await client.messages.create("""

if old_call in content:
    content = content.replace(old_call, new_call, 1)
    print("Wired context_manager before LLM call")
else:
    print("WARN: Could not find exact LLM call pattern — skipping context_manager wiring")

with open(FILE, "w") as f:
    f.write(content)

try:
    py_compile.compile(FILE, doraise=True)
    print("Integration 4 DONE — syntax OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
    sys.exit(1)
