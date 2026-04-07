"""Integration 5: Wire auto_memory_extractor + session_memory into server.py TG handler."""
import sys, py_compile

FILE = "/home/pi/master_ai/server.py"
with open(FILE) as f:
    content = f.read()

# 1. Add module-level initialization near top of file (after imports)
# Find the TG handler section marker
marker = 'async def _tg_v2_pipeline(chat_id: int, text: str, user: dict):'
idx = content.find(marker)
if idx < 0:
    print("Could not find _tg_v2_pipeline")
    sys.exit(1)

# Insert initialization before the function
init_code = """# Integration: session tracking + auto memory extraction (Tier3)
try:
    from session_memory import SessionTracker
    _session_tracker = SessionTracker()
except ImportError:
    _session_tracker = None
try:
    from auto_memory_extractor import AutoMemoryExtractor
    _memory_extractor = AutoMemoryExtractor()
except ImportError:
    _memory_extractor = None


"""

content = content[:idx] + init_code + content[idx:]

# 2. Add tracking calls at start of pipeline (after logging)
old_log = '    logger.info(f"TG_V2 user={user_profile.get(\'user_id\',\'?\')}'
new_log = """    # Track incoming message (Tier3 integration)
    if _session_tracker:
        _session_tracker.add_message("user", text)
    if _memory_extractor:
        _memory_extractor.record_message("user", text)
    logger.info(f"TG_V2 user={user_profile.get('user_id','?')}"""

if old_log in content:
    content = content.replace(old_log, new_log, 1)
    print("Wired user message tracking")
else:
    print("WARN: Could not find user log line")

# 3. Add tracking before response send
old_send = '    await tg_send(chat_id, response)\n\n\nasync def tg_handle_message'
new_send = """    # Track response (Tier3 integration)
    if _session_tracker:
        _session_tracker.add_message("assistant", response)
    if _memory_extractor:
        _memory_extractor.record_message("assistant", response)

    await tg_send(chat_id, response)


async def tg_handle_message"""

if old_send in content:
    content = content.replace(old_send, new_send, 1)
    print("Wired response tracking")
else:
    print("WARN: Could not find response send pattern")

with open(FILE, "w") as f:
    f.write(content)

try:
    py_compile.compile(FILE, doraise=True)
    print("Integration 5 DONE — syntax OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
    sys.exit(1)
