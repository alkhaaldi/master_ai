import ast
path = "/home/pi/master_ai/telegram_bot.py"
with open(path) as f:
    content = f.read()

# Restore from backup if broken
if 'SyntaxError' in content or 'split = text[:4000].rfind' in content:
    with open(path + ".bak2") as f:
        content = f.read()

helper = '''
async def send_long(msg, text):
    MAX = 4000
    if len(text) <= MAX:
        await msg.reply_text(text)
        return
    while text:
        if len(text) <= MAX:
            await msg.reply_text(text)
            break
        idx = text[:MAX].rfind(chr(10))
        if idx < 100:
            idx = MAX
        await msg.reply_text(text[:idx])
        text = text[idx:].lstrip(chr(10))

'''

old_marker = "# --- Helper: Call Master AI ---"
if old_marker in content and 'send_long' not in content:
    content = content.replace(old_marker, helper + old_marker)

# Replace the final reply in handle_message
old_reply = "await update.message.reply_text(summary if summary else"
new_reply = "await send_long(update.message, summary if summary else"
if old_reply in content:
    content = content.replace(old_reply, new_reply, 1)

with open(path, "w") as f:
    f.write(content)

import py_compile
try:
    py_compile.compile(path, doraise=True)
    print("OK")
except py_compile.PyCompileError as e:
    print(f"ERR: {e}")
    # Restore
    with open(path + ".bak2") as f:
        backup = f.read()
    with open(path, "w") as f:
        f.write(backup)
    print("RESTORED")
