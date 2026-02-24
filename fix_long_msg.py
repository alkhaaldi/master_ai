path = "/home/pi/master_ai/telegram_bot.py"
with open(path) as f:
    content = f.read()

# Add a helper function to split long messages
old = "# --- Helper: Call Master AI ---"

new = """# --- Helper: Send long messages (split at 4000 chars) ---
async def send_long_message(message, text, parse_mode=None):
    if len(text) <= 4000:
        await message.reply_text(text, parse_mode=parse_mode)
    else:
        chunks = []
        while text:
            if len(text) <= 4000:
                chunks.append(text)
                break
            split = text[:4000].rfind('\n')
            if split == -1:
                split = 4000
            chunks.append(text[:split])
            text = text[split:].lstrip('\n')
        for chunk in chunks:
            await message.reply_text(chunk, parse_mode=parse_mode)

# --- Helper: Call Master AI ---"""

if old in content:
    content = content.replace(old, new)

# Now replace reply_text calls in handle_message to use send_long_message
content = content.replace(
    'await update.message.reply_text(summary if summary else',
    'await send_long_message(update.message, summary if summary else'
)
content = content.replace(
    'await update.message.reply_text(f"\\u2705 \\u062A\\u0645!\\n\\n{output}" if output else "\\u2705 \\u062A\\u0645!")',
    'await send_long_message(update.message, f"\\u2705 \\u062A\\u0645!\\n\\n{output}" if output else "\\u2705 \\u062A\\u0645!")'
)

with open(path, "w") as f:
    f.write(content)

import py_compile
try:
    py_compile.compile(path, doraise=True)
    print("OK")
except py_compile.PyCompileError as e:
    print(f"ERR: {e}")
