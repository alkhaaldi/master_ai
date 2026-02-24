path = "/home/pi/master_ai/server.py"
with open(path) as f:
    content = f.read()

with open(path + ".pre_ask_bak", "w") as f:
    f.write(content)

old = """@app.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest):
    t0 = time.time()
    try:
        result = await llm_call("You are Master AI, a helpful home automation assistant for Bu Khalifa. Answer concisely in Kuwaiti Arabic.", body.prompt, max_tokens=1024, temperature=0.7)
        return AskResponse(response=result)
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": "AI error", "detail": str(e)})"""

new = """@app.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest):
    t0 = time.time()
    try:
        ask_prompt = "You are Master AI, Bu Khalifa's personal smart home assistant. Answer in Kuwaiti Arabic. Be concise and helpful."
        try:
            ctx = await build_context('bu_khalifa', 'ask')
            mem = ctx.get('memories') or {}
            parts = []
            for k in ['facts', 'preferences', 'patterns']:
                items = mem.get(k) or []
                if items:
                    parts.append('; '.join(m['content'] for m in items[:5]))
            if parts:
                ask_prompt += chr(10) + 'What you know: ' + ' | '.join(parts)
        except Exception:
            pass
        try:
            await save_message('ask', 'user', body.prompt)
        except Exception:
            pass
        result = await llm_call(ask_prompt, body.prompt, max_tokens=1024, temperature=0.7)
        try:
            await save_message('ask', 'assistant', result)
        except Exception:
            pass
        return AskResponse(response=result)
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": "AI error", "detail": str(e)})"""

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
        shutil.copy(path + ".pre_ask_bak", path)
        print("RESTORED")
else:
    print("NOT FOUND")
