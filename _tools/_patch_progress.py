"""Patch server.py to add progress indicator for long Telegram operations (Tier1 #4)."""
import sys

FILE = "/home/pi/master_ai/server.py"
with open(FILE) as f:
    lines = f.readlines()

# Find the TELEGRAM-specific Stage 4
stage4_idx = None
for i, line in enumerate(lines):
    if "Stage 4: LLM primary (chat_v7)" in line:
        context = "".join(lines[max(0, i - 15):i])
        if "sendChatAction" in context or "Stage 3" in context:
            stage4_idx = i
            break

if stage4_idx is None:
    print("Could not find TG-specific Stage 4")
    sys.exit(1)

print(f"Found TG Stage 4 at line {stage4_idx + 1}")

# Find "response = await asyncio.wait_for(" after stage4_idx
await_idx = None
for i in range(stage4_idx, min(stage4_idx + 30, len(lines))):
    if "response = await asyncio.wait_for(" in lines[i]:
        await_idx = i
        break

if await_idx is None:
    print("Could not find await line")
    sys.exit(1)

print(f"Found await at line {await_idx + 1}")

# Find timeout=180 after that
timeout_idx = None
for i in range(await_idx, min(await_idx + 10, len(lines))):
    if "timeout=180" in lines[i]:
        timeout_idx = i
        break

if timeout_idx is None:
    print("Could not find timeout line")
    sys.exit(1)

# Find closing ) of wait_for
close_idx = None
for i in range(timeout_idx, min(timeout_idx + 3, len(lines))):
    stripped = lines[i].strip()
    if stripped == ")" or stripped.endswith(")"):
        close_idx = i
        break

if close_idx is None:
    close_idx = timeout_idx  # timeout and close on same line

print(f"Found close paren at line {close_idx + 1}")

# Get indentation of the await line
indent = len(lines[await_idx]) - len(lines[await_idx].lstrip())
base = " " * indent

# 1. Add helper function before tg_handle_command
helper_idx = None
for i, line in enumerate(lines):
    if line.strip().startswith("async def tg_handle_command("):
        helper_idx = i
        break

if helper_idx is None:
    print("Could not find tg_handle_command")
    sys.exit(1)

helper = [
    'async def _send_progress_after_delay(chat_id, delay: float = 2.0):\n',
    '    """Send progress indicator if LLM takes > delay seconds (Tier1 #4)."""\n',
    '    await asyncio.sleep(delay)\n',
    '    try:\n',
    '        await tg_send(chat_id, "\u23f3 \u062c\u0627\u0631\u064a \u0627\u0644\u062a\u062d\u0644\u064a\u0644...")\n',
    '    except Exception:\n',
    '        pass\n',
    '\n',
    '\n',
]
lines[helper_idx:helper_idx] = helper
off = len(helper)
stage4_idx += off
await_idx += off
timeout_idx += off
close_idx += off

# 2. Update Stage 4 comment
lines[stage4_idx] = lines[stage4_idx].replace(
    "Stage 4: LLM primary (chat_v7)",
    "Stage 4: LLM primary (chat_v7) \u2014 with progress (Tier1 #4)"
)

# 3. Insert progress task + try before await
insert = [
    f"{base}_progress_task = asyncio.create_task(_send_progress_after_delay(chat_id, 2.0))\n",
    f"{base}try:\n",
]
lines[await_idx:await_idx] = insert
off2 = len(insert)
await_idx += off2
timeout_idx += off2
close_idx += off2

# 4. Indent the await block by 4 spaces
for i in range(await_idx, close_idx + 1):
    lines[i] = "    " + lines[i]

# 5. Add finally block after close paren
finally_block = [
    f"{base}finally:\n",
    f"{base}    _progress_task.cancel()\n",
]
lines[close_idx + 1:close_idx + 1] = finally_block

with open(FILE, "w") as f:
    f.writelines(lines)

print("PATCHED OK")
