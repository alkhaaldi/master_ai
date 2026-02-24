path = "/home/pi/master_ai/server.py"

with open(path) as f:
    content = f.read()

with open(path + ".pre_think4_bak", "w") as f:
    f.write(content)

changes = 0

# 1. plan_actions accepts context
old1 = 'async def plan_actions(task: str) -> list[dict]:'
new1 = 'async def plan_actions(task: str, context: dict = None) -> list[dict]:'
if old1 in content and 'context: dict' not in content:
    content = content.replace(old1, new1)
    changes += 1

# 2. Add context to planner prompt
old2 = '        raw = await llm_call(PLANNER_SYSTEM_PROMPT, task, max_tokens=1024, temperature=0.1)'
new2 = """        prompt = PLANNER_SYSTEM_PROMPT
        if context:
            cp = []
            mem = context.get('memories') or {}
            for k in ['patterns', 'preferences', 'facts']:
                items = mem.get(k) or []
                if items:
                    cp.append(k + ': ' + '; '.join(m['content'] for m in items[:5]))
            if cp:
                prompt += chr(10) + 'CONTEXT: ' + '; '.join(cp)
        raw = await llm_call(prompt, task, max_tokens=1024, temperature=0.1)"""
if old2 in content:
    content = content.replace(old2, new2)
    changes += 1

# 3. In agent: add context loading + pass to plan_actions
# Replace the exact block
old3 = """    task = body.task.strip()
    logger.info("POST /agent: %s (dry_run=%s)", task[:100], body.dry_run)
    actions = await plan_actions(task)"""

new3 = """    task = body.task.strip()
    logger.info("POST /agent: %s (dry_run=%s)", task[:100], body.dry_run)
    ctx = None
    try:
        ctx = await build_context('bu_khalifa', 'agent')
    except Exception:
        pass
    try:
        await save_message('agent', 'user', task)
    except Exception:
        pass
    actions = await plan_actions(task, context=ctx)"""

if old3 in content:
    content = content.replace(old3, new3)
    changes += 1

# 4. Before final return, add save + learn
old4 = """    return {"summary": summary, "actions": actions, "results": results,
            "needs_approval": False, "approval_id": None, "dry_run": False, "elapsed": round(elapsed, 3)}"""

new4 = """    try:
        await save_message('agent', 'assistant', summary)
    except Exception:
        pass
    try:
        lp = 'Extract NEW facts from this interaction as JSON array. Each: category(personal/ha/trading/work), type(fact/pattern/preference), content(Arabic), confidence(0-1), tags. Return [] if nothing new.'
        lr = await llm_call(lp, 'User: ' + task + ' Result: ' + summary, max_tokens=500, temperature=0.2)
        if lr.strip().startswith('['):
            for mem in json.loads(lr):
                await add_memory(mem.get('category', 'general'), mem.get('type', 'fact'), mem['content'], source='auto', confidence=mem.get('confidence', 0.5), tags=mem.get('tags', ''))
    except Exception:
        pass
    return {"summary": summary, "actions": actions, "results": results,
            "needs_approval": False, "approval_id": None, "dry_run": False, "elapsed": round(elapsed, 3)}"""

if old4 in content:
    content = content.replace(old4, new4)
    changes += 1

with open(path, "w") as f:
    f.write(content)

print(f"Changes: {changes}")

import py_compile
try:
    py_compile.compile(path, doraise=True)
    print("SYNTAX OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
    import shutil
    shutil.copy(path + ".pre_think4_bak", path)
    print("RESTORED")
