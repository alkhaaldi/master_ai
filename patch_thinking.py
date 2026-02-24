import json as json_mod

path = "/home/pi/master_ai/server.py"
with open(path) as f:
    code = f.read()

# Backup
with open(path + ".pre_thinking_bak", "w") as f:
    f.write(code)

changes = 0

# 1. Modify plan_actions to accept optional context
old_plan_sig = "async def plan_actions(task: str) -> list[dict]:"
new_plan_sig = "async def plan_actions(task: str, context: dict = None) -> list[dict]:"
if old_plan_sig in code and "context: dict" not in code:
    code = code.replace(old_plan_sig, new_plan_sig)
    changes += 1
    print("+ plan_actions now accepts context")

# 2. Replace the llm_call inside plan_actions to include context
old_plan_call = "        raw = await llm_call(PLANNER_SYSTEM_PROMPT, task, max_tokens=1024, temperature=0.1)"
new_plan_call = """        # Build context-aware prompt
        prompt = PLANNER_SYSTEM_PROMPT
        if context:
            ctx_parts = []
            # User info
            u = context.get("user", {})
            if u: ctx_parts.append(f"User: {u.get('name', 'unknown')} - speaks {u.get('language', 'ar')}")
            # Memories
            mem = context.get("memories", {})
            patterns = mem.get("patterns", [])
            prefs = mem.get("preferences", [])
            facts = mem.get("facts", [])
            if patterns: ctx_parts.append("Known patterns: " + "; ".join(m["content"] for m in patterns[:5]))
            if prefs: ctx_parts.append("User preferences: " + "; ".join(m["content"] for m in prefs[:5]))
            if facts: ctx_parts.append("Key facts: " + "; ".join(m["content"] for m in facts[:5]))
            # Tasks
            tasks = context.get("tasks", {})
            urgent = tasks.get("urgent_tasks", [])
            if urgent: ctx_parts.append("Urgent tasks: " + "; ".join(t["title"] for t in urgent[:3]))
            if ctx_parts:
                prompt += "\n\nCONTEXT ABOUT THE USER:\n" + "\n".join(ctx_parts)
        raw = await llm_call(prompt, task, max_tokens=1024, temperature=0.1)"""
if old_plan_call in code:
    code = code.replace(old_plan_call, new_plan_call)
    changes += 1
    print("+ plan_actions now uses context in prompt")

# 3. Modify /agent to load context, save conversation, and learn
old_agent_start = """    task = body.task.strip()
    logger.info("POST /agent: %s (dry_run=%s)", task[:100], body.dry_run)
    actions = await plan_actions(task)"""

new_agent_start = """    task = body.task.strip()
    logger.info("POST /agent: %s (dry_run=%s)", task[:100], body.dry_run)

    # SMART: Load full context before planning
    try:
        ctx = await build_context("bu_khalifa", "agent")
        logger.info("Context loaded: %d memories, %d tasks", ctx.get("memories", {}).get("total", 0), ctx.get("tasks", {}).get("total", 0))
    except Exception as e:
        logger.warning("Context load failed: %s", e)
        ctx = None

    # SMART: Save user message
    try:
        await save_message("agent", "user", task)
    except Exception as e:
        logger.warning("Save message failed: %s", e)

    actions = await plan_actions(task, context=ctx)"""

if old_agent_start in code:
    code = code.replace(old_agent_start, new_agent_start)
    changes += 1
    print("+ /agent now loads context and saves messages")

# 4. Add learning after agent execution (before the return)
old_agent_return = """    return {"summary": summary, "actions": actions, "results": results,
            "needs_approval": False, "approval_id": None, "dry_run": False, "elapsed": round(elapsed, 3)}"""

new_agent_return = """    # SMART: Save assistant response
    try:
        await save_message("agent", "assistant", summary)
    except:
        pass

    # SMART: Learn from interaction (background, don't block response)
    try:
        learning_input = f"User asked: {task}\nActions: {json.dumps(actions, ensure_ascii=False)[:500]}\nResult: {summary}"
        learning_prompt = "You are a memory extraction system. Analyze this interaction and extract NEW information worth remembering about the user or their home. Return a JSON array of memories. Each memory: {{\"category\": \"personal|ha|trading|work|pattern|preference\", \"type\": \"fact|pattern|preference|event\", \"content\": \"Arabic text\", \"confidence\": 0.5, \"tags\": \"comma,separated\"}}. Return [] if nothing new."
        raw_learning = await llm_call(learning_prompt, learning_input, max_tokens=500, temperature=0.2)
        if raw_learning.startswith("["):
            learnings = json.loads(raw_learning)
            for mem in learnings:
                await add_memory(mem.get("category","general"), mem.get("type","fact"), mem["content"], source="auto", confidence=mem.get("confidence",0.5), tags=mem.get("tags",""))
            if learnings:
                logger.info("Learned %d new memories from interaction", len(learnings))
    except Exception as e:
        logger.warning("Learning extraction failed: %s", e)

    return {"summary": summary, "actions": actions, "results": results,
            "needs_approval": False, "approval_id": None, "dry_run": False, "elapsed": round(elapsed, 3)}"""

if old_agent_return in code:
    code = code.replace(old_agent_return, new_agent_return)
    changes += 1
    print("+ /agent now saves responses and learns from interactions")

# 5. Also make /ask smart
old_ask_call = '        result = await llm_call("You are Master AI, a helpful home automation assistant for Bu Khalifa. Answer concisely in Kuwaiti Arabic.", body.prompt, max_tokens=1024, temperature=0.7)'
new_ask_call = """        # SMART: Load context for /ask too
        try:
            ctx = await build_context("bu_khalifa", "ask")
            ctx_text = ""
            mem = ctx.get("memories", {})
            facts = mem.get("facts", [])
            prefs = mem.get("preferences", [])
            if facts: ctx_text += "\nFacts: " + "; ".join(m["content"] for m in facts[:5])
            if prefs: ctx_text += "\nPreferences: " + "; ".join(m["content"] for m in prefs[:3])
            ask_prompt = "You are Master AI, Bu Khalifa's personal smart home assistant. Answer in Kuwaiti Arabic. Be concise." + ctx_text
        except:
            ask_prompt = "You are Master AI, a helpful home automation assistant for Bu Khalifa. Answer concisely in Kuwaiti Arabic."
        await save_message("ask", "user", body.prompt)
        result = await llm_call(ask_prompt, body.prompt, max_tokens=1024, temperature=0.7)
        await save_message("ask", "assistant", result)"""

if old_ask_call in code:
    code = code.replace(old_ask_call, new_ask_call)
    changes += 1
    print("+ /ask now loads context and saves conversations")

with open(path, "w") as f:
    f.write(code)

print(f"\nTotal changes: {changes}")
print("Master AI now THINKS!")
