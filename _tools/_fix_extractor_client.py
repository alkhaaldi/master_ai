"""Wire anthropic_client into AutoMemoryExtractor so it can use Haiku for extraction."""
import sys, py_compile

FILE = "/home/pi/master_ai/server.py"
with open(FILE) as f:
    content = f.read()

# Find the extractor init and add client wiring
old = """    from auto_memory_extractor import AutoMemoryExtractor
    _memory_extractor = AutoMemoryExtractor()
except ImportError:
    _memory_extractor = None"""

new = """    from auto_memory_extractor import AutoMemoryExtractor
    _memory_extractor = AutoMemoryExtractor()
except ImportError:
    _memory_extractor = None

# Wire anthropic client into extractor (after lifespan creates it)
def _wire_extractor_client():
    if _memory_extractor and anthropic_client:
        _memory_extractor.set_client(anthropic_client)"""

if old not in content:
    print("Could not find extractor init")
    sys.exit(1)

content = content.replace(old, new, 1)

# Call _wire_extractor_client in the pipeline (at first use)
old_track = """    # Track incoming message (Tier3 integration)
    if _session_tracker:
        _session_tracker.add_message("user", text)
    if _memory_extractor:
        _memory_extractor.record_message("user", text)"""

new_track = """    # Track incoming message (Tier3 integration)
    if _session_tracker:
        _session_tracker.add_message("user", text)
    if _memory_extractor:
        if not _memory_extractor._client and anthropic_client:
            _memory_extractor.set_client(anthropic_client)
        _memory_extractor.record_message("user", text)"""

if old_track in content:
    content = content.replace(old_track, new_track, 1)
    print("Wired anthropic_client into extractor at first use")
else:
    print("WARN: Could not find tracking block")

with open(FILE, "w") as f:
    f.write(content)

try:
    py_compile.compile(FILE, doraise=True)
    print("Extractor client fix — syntax OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
    sys.exit(1)
