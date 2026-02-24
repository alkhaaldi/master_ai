"""Safe patch for thinking capabilities."""
import re, json

path = "/home/pi/master_ai/server.py"
with open(path) as f:
    code = f.read()
with open(path + ".pre_think2_bak", "w") as f:
    f.write(code)

changes = 0

# 1. plan_actions signature
old1 = "async def plan_actions(task: str) -> list[dict]:"
new1 = "async def plan_actions(task: str, context: dict = None) -> list[dict]:"
if old1 in code and "context: dict" not in code:
    code = code.replace(old1, new1)
    changes += 1
    print("1. plan_actions signature OK")

# 2. Context injection in plan_actions
old2 = "        raw = await llm_call(PLANNER_SYSTEM_PROMPT, task, max_tokens=1024, temperature=0.1)"
new2 = '''        # Build context-enriched prompt
        enriched_prompt = PLANNER_SYSTEM_PROMPT
        if context:
            ctx_lines = []
            u = context.get("user") or {}
            if u.get("name"):
                ctx_lines.append("User: " + u["name"])
            mem = context.get("memories") or {}
            for mtype in ["patterns", "preferences", "facts"]:
                items = mem.get(mtype) or []
                if items:
                    texts = [m.get("content", "") for m in items[:5]]
                    ctx_lines.append(mtype.title() + ": " + "; ".join(texts))
            tasks_info = context.get("tasks") or {}
            urgent = tasks_info.get("urgent_tasks") or []
            if urgent:
                ctx_lines.append("Urgent: " + "; ".join(t.get("title", "") for t in urgent[:3]))
            if ctx_lines:
                enriched_prompt += "\nUSER CONTEXT:\n" + "\n".join(ctx_lines)
        raw = await llm_call(enriched_prompt, task, max_tokens=1024, temperature=0.1)'''
if old2 in code:
    code = code.replace(old2, new2)
    changes += 1
    print("2. Context injection OK")

# 3. Agent loads context
old3 = '''    task = body.task.strip()
    logger.info("POST /agent: %s (dry_run=%s)", task[:100], body.dry_run)
    actions = await plan_actions(task)'''
new3 = '''    task = body.task.strip()
    logger.info("POST /agent: %s (dry_run=%s)", task[:100], body.dry_run)
    ctx = None
    try:
        ctx = await build_context("bu_khalifa", "agent")
        logger.info("Context: %d memories", ctx.get("memories", {}).get("total", 0))
    except Exception as exc:
        logger.warning("Context failed: %s", exc)
    try:
        await save_message("agent", "user", task)
    except Exception:
        pass
    actions = await plan_actions(task, context=ctx)'''
if old3 in code:
    code = code.replace(old3, new3)
    changes += 1
    print("3. Agent context OK")

# 4. Learning after agent
old4 = '    return {"summary": summary, "actions": actions, "results": results,\n            "needs_approval": False, "approval_id": None, "dry_run": False, "elapsed": round(elapsed, 3)}'
# Try to find this pattern
ret_pattern = 'return {"summary": summary, "actions": actions, "results": results,'
ret_idx = code.find(ret_pattern)
if ret_idx > 0:
    # Find the full return statement
    ret_end = code.find("}", ret_idx + len(ret_pattern))
    full_ret = code[ret_idx:ret_end+1]
    learning = '''# --- SMART: Save + Learn ---
    try:
        await save_message("agent", "assistant", summary)
    except Exception:
        pass
    try:
        learn_in = "User: " + task + "\nResult: " + summary
        learn_sys = "Extract NEW facts from this interaction. Return JSON array: [{\\"category\\":\\"ha\\",\\"type\\":\\"fact\\",\\"content\\":\\"Arabic text\\",\\"confidence\\":0.5,\\"tags\\":\\"x\\"}]. Return [] if nothing."
        raw_l = await llm_call(learn_sys, learn_in, max_tokens=400, temperature=0.2)
        raw_l = raw_l.strip()
        if raw_l.startswith("["):
            for m in json.loads(raw_l):
                if m.get("content"):
                    await add_memory(m.get("category","ha"), m.get("type","fact"), m["content"], source="auto", confidence=m.get("confidence",0.5), tags=m.get("tags",""))
                    logger.info("Learned: %s", m["content"][:50])
    except Exception as exc:
        logger.debug("Learn skip: %s", exc)
    ''' + full_ret
    code = code[:ret_idx] + learning + code[ret_end+1:]
    changes += 1
    print("4. Learning OK")

with open(path, "w") as f:
    f.write(code)
print(f"\nTotal: {changes} changes")
