path = "/home/pi/master_ai/telegram_bot.py"
with open(path) as f:
    content = f.read()

with open(path + ".bak2", "w") as f:
    f.write(content)

old = '''    # Send to /agent
    result = await call_master("/agent", method="POST", data={"task": user_text})
    
    if "error" in result:
        await update.message.reply_text(f"\\u274C \\u062E\\u0637\\u0623: {result['error']}")
        return
    
    summary = result.get("summary", "\\u062A\\u0645")
    needs_approval = result.get("needs_approval", False)
    approval_id = result.get("approval_id")
    
    if needs_approval and approval_id:
        actions_text = ""
        for a in result.get("actions", []):
            actions_text += f"  \\u2022 {a.get('type')}: {a.get('why', '')}\\n"
        await update.message.reply_text(
            f"\\u26A0\\uFE0F \\u064A\\u0628\\u064A \\u0645\\u0648\\u0627\\u0641\\u0642\\u0629:\\n{actions_text}\\n"
            f"\\u0627\\u0631\\u0633\\u0644: /approve_{approval_id}"
        )
    else:
        await update.message.reply_text(summary)'''

new = '''    # Send to /agent
    result = await call_master("/agent", method="POST", data={"task": user_text})
    
    if "error" in result:
        await update.message.reply_text(f"\\u274C {result['error']}")
        return
    
    summary = result.get("summary", "")
    needs_approval = result.get("needs_approval", False)
    approval_id = result.get("approval_id")
    
    if needs_approval and approval_id:
        actions_text = ""
        for a in result.get("actions", []):
            actions_text += f"  - {a.get('type')}: {a.get('why', '')}\\n"
        await update.message.reply_text(f"\\u26A0 \\u064A\\u0628\\u064A \\u0645\\u0648\\u0627\\u0641\\u0642\\u0629:\\n{actions_text}\\n/approve_{approval_id}")
        return
    
    # Check if any win jobs were queued
    has_win_job = any(a.get("type", "").startswith("win_") for a in result.get("actions", []))
    if has_win_job:
        await update.message.reply_text("\\u23F3 \\u062C\\u0627\\u0631\\u064A \\u0627\\u0644\\u062A\\u0646\\u0641\\u064A\\u0630...")
        # Wait for result (poll /win/jobs up to 30 seconds)
        import asyncio
        for i in range(12):
            await asyncio.sleep(5)
            jobs = await call_master("/win/jobs")
            results = jobs.get("recent_results", {})
            if results:
                last = list(results.values())[-1]
                if last.get("success"):
                    output = last.get("stdout", "")[:3500]
                    await update.message.reply_text(f"\\u2705 \\u062A\\u0645!\\n\\n{output}" if output else "\\u2705 \\u062A\\u0645!")
                else:
                    err = last.get("stderr", "")[:1000]
                    await update.message.reply_text(f"\\u274C \\u0641\\u0634\\u0644:\\n{err}")
                return
        await update.message.reply_text("\\u23F0 \\u0627\\u0644\\u0623\\u0645\\u0631 \\u0623\\u062E\\u0630 \\u0648\\u0642\\u062A \\u0623\\u0643\\u062B\\u0631 \\u0645\\u0646 \\u0627\\u0644\\u0645\\u062A\\u0648\\u0642\\u0639")
    else:
        await update.message.reply_text(summary if summary else "\\u2705")'''

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
        import shutil
        shutil.copy(path + ".bak2", path)
        print("RESTORED")
else:
    print("NOT_FOUND")
