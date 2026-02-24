import sys

path = "/home/pi/master_ai/server.py"

with open(path) as f:
    lines = f.readlines()

with open(path + ".pre_think3_bak", "w") as f:
    f.writelines(lines)

new_lines = []
i = 0
changes = 0

while i < len(lines):
    line = lines[i]
    
    # 1. plan_actions signature
    if 'async def plan_actions(task: str) -> list[dict]:' in line and 'context' not in line:
        new_lines.append('async def plan_actions(task: str, context: dict = None) -> list[dict]:\n')
        changes += 1
        i += 1
        continue
    
    # 2. Before llm_call in plan_actions, add context
    if 'raw = await llm_call(PLANNER_SYSTEM_PROMPT' in line:
        sp = "        "
        new_lines.append(sp + "prompt = PLANNER_SYSTEM_PROMPT\n")
        new_lines.append(sp + "if context:\n")
        new_lines.append(sp + "    cp = []\n")
        new_lines.append(sp + "    mem = context.get('memories') or {}\n")
        new_lines.append(sp + "    for k in ['patterns','preferences','facts']:\n")
        new_lines.append(sp + "        items = mem.get(k) or []\n")
        new_lines.append(sp + "        if items:\n")
        new_lines.append(sp + "            cp.append(k + ': ' + '; '.join(m['content'] for m in items[:5]))\n")
        new_lines.append(sp + "    if cp:\n")
        new_lines.append(sp + "        prompt += chr(10) + 'CONTEXT: ' + '; '.join(cp)\n")
        new_lines.append(sp + "raw = await llm_call(prompt, task, max_tokens=1024, temperature=0.1)\n")
        changes += 1
        i += 1
        continue
    
    # 3. In agent, after task strip + logger, add context loading
    if 'task = body.task.strip()' in line and i > 600:
        new_lines.append(line)
        i += 1
        if i < len(lines) and 'logger.info' in lines[i]:
            new_lines.append(lines[i])
            i += 1
        sp = "    "
        new_lines.append(sp + "ctx = None\n")
        new_lines.append(sp + "try:\n")
        new_lines.append(sp + "    ctx = await build_context('bu_khalifa', 'agent')\n")
        new_lines.append(sp + "except Exception:\n")
        new_lines.append(sp + "    pass\n")
        new_lines.append(sp + "try:\n")
        new_lines.append(sp + "    await save_message('agent', 'user', task)\n")
        new_lines.append(sp + "except Exception:\n")
        new_lines.append(sp + "    pass\n")
        changes += 1
        continue
    
    # 4. Pass context to plan_actions in agent
    if 'actions = await plan_actions(task)' in line and i > 600:
        new_lines.append(line.replace('plan_actions(task)', 'plan_actions(task, context=ctx)'))
        changes += 1
        i += 1
        continue
    
    # 5. Before final return in agent, add save + learn
    if '"needs_approval": False, "approval_id": None, "dry_run": False' in line:
        sp = "    "
        new_lines.append(sp + "try:\n")
        new_lines.append(sp + "    await save_message('agent', 'assistant', summary)\n")
        new_lines.append(sp + "except Exception:\n")
        new_lines.append(sp + "    pass\n")
        new_lines.append(sp + "try:\n")
        new_lines.append(sp + "    lp = 'Extract NEW facts from this interaction as JSON array. Each item: category(personal/ha/trading/work), type(fact/pattern/preference), content(Arabic), confidence(0-1), tags. Return [] if nothing new.'\n")
        new_lines.append(sp + "    li = 'User: ' + task + ' | Result: ' + summary\n")
        new_lines.append(sp + "    lr = await llm_call(lp, li, max_tokens=500, temperature=0.2)\n")
        new_lines.append(sp + "    if lr.strip().startswith('['):\n")
        new_lines.append(sp + "        for mem in json.loads(lr):\n")
        new_lines.append(sp + "            await add_memory(mem.get('category','general'), mem.get('type','fact'), mem['content'], source='auto', confidence=mem.get('confidence',0.5), tags=mem.get('tags',''))\n")
        new_lines.append(sp + "except Exception:\n")
        new_lines.append(sp + "    pass\n")
        new_lines.append(line)
        changes += 1
        i += 1
        continue
    
    new_lines.append(line)
    i += 1

with open(path, "w") as f:
    f.writelines(new_lines)

print(f"Changes: {changes}")

import py_compile
try:
    py_compile.compile(path, doraise=True)
    print("SYNTAX OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
    import shutil
    shutil.copy(path + ".pre_think3_bak", path)
    print("RESTORED")
