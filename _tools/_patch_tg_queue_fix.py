"""Fix tg_send queue fallback — don't force Markdown when parse_mode is None."""
import os, shutil

with open("server.py", "r") as f:
    content = f.read()

# Replace all 3 occurrences: parse_mode or "Markdown" → parse_mode or ""
old = 'kairos_agent.tg_queue.enqueue(int(chat_id), text, parse_mode or "Markdown")'
new = 'kairos_agent.tg_queue.enqueue(int(chat_id), text, parse_mode or "")'

count = content.count(old)
content = content.replace(old, new)
print(f"Fixed {count} queue enqueue calls (removed Markdown default)")

with open("/tmp/server_patched.py", "w") as f:
    f.write(content)
os.remove("server.py")
shutil.move("/tmp/server_patched.py", "server.py")
print("Done.")
