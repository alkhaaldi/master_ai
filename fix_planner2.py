path = "/home/pi/master_ai/server.py"
with open(path) as f:
    content = f.read()

old = "- NEVER refuse or say \"could not plan\". Always try: use ha_get_state * if unsure, or respond_text to explain"
new = """- NEVER refuse or say "could not plan". ALWAYS return at least one action
- For ANY conversation, question, or chat that is NOT a command: use respond_text with a helpful answer in Kuwaiti Arabic
- respond_text is your default fallback. If you can't do an action, TALK to the user using respond_text
- You are a personal assistant, not just a device controller. Answer questions, have conversations, give advice"""

if old in content:
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    import py_compile
    try:
        py_compile.compile(path, doraise=True)
        print("OK")
    except:
        print("ERR")
else:
    print("NOT_FOUND")
