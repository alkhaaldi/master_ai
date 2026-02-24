path = "/home/pi/master_ai/telegram_bot.py"
with open(path) as f:
    content = f.read()

# Find the error handling in handle_message
old = '''    result = await call_master("/agent", method="POST", data={"task": user_text})
    
    if "error" in result:'''

new = '''    result = await call_master("/agent", method="POST", data={"task": user_text})
    
    # If agent failed or could not plan, fallback to /ask (conversational)
    summary = result.get("summary", "")
    if "Could not plan" in summary or "could not plan" in summary.lower():
        ask_result = await call_master("/ask", method="POST", data={"prompt": user_text})
        if "response" in ask_result:
            await send_long(update.message, ask_result["response"])
            return
    
    if "error" in result:'''

if old in content:
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    import py_compile
    try:
        py_compile.compile(path, doraise=True)
        print("OK")
    except py_compile.PyCompileError as e:
        print(f"ERR: {e}")
else:
    print("NOT_FOUND")
