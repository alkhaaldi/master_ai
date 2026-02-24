import re

path = "/home/pi/master_ai/server.py"
with open(path) as f:
    code = f.read()

changes = 0

# Add a universal LLM call function after the clients section
helper_func = '''
# --- Universal LLM Call (Claude Opus primary, OpenAI fallback) ---
async def llm_call(system_prompt: str, user_message: str, max_tokens: int = 1024, temperature: float = 0.3) -> str:
    """Call Claude Opus 4.6, fallback to OpenAI gpt-4o-mini"""
    if anthropic_client:
        try:
            response = await anthropic_client.messages.create(
                model="claude-opus-4-6",
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.warning("Claude Opus failed, falling back to OpenAI: %s", e)
    # Fallback to OpenAI
    try:
        completion = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=max_tokens, temperature=temperature,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Both LLM calls failed: %s", e)
        raise

'''

# Insert helper after anthropic_client line
if "async def llm_call" not in code:
    code = code.replace(
        "anthropic_client = AsyncAnthropic(api_key=anthropic_key) if anthropic_key else None",
        "anthropic_client = AsyncAnthropic(api_key=anthropic_key) if anthropic_key else None" + helper_func
    )
    changes += 1
    print("+ Added llm_call helper function")

# Now replace plan_actions LLM call
old_plan = """        completion = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": task},
            ],
            max_tokens=1024, temperature=0.1,
        )
        raw = completion.choices[0].message.content.strip()"""

new_plan = """        raw = await llm_call(PLANNER_SYSTEM_PROMPT, task, max_tokens=1024, temperature=0.1)"""

if old_plan in code:
    code = code.replace(old_plan, new_plan)
    changes += 1
    print("+ Replaced plan_actions LLM call")
else:
    print("! Could not find plan_actions LLM call pattern")

# Replace _generate_summary LLM call
old_summary = """        completion = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Summarize smart home/PC action results in 1-2 sentences. Concise."},
                {"role": "user", "content": f"Task: {task}\nResults: {'; '.join(context_parts)}"},
            ],
            max_tokens=150, temperature=0.3,
        )
        return completion.choices[0].message.content.strip()"""

new_summary = """        return await llm_call("Summarize smart home/PC action results in 1-2 sentences. Concise.", f"Task: {task}\nResults: {'; '.join(context_parts)}", max_tokens=150, temperature=0.3)"""

if old_summary in code:
    code = code.replace(old_summary, new_summary)
    changes += 1
    print("+ Replaced _generate_summary LLM call")
else:
    print("! Could not find _generate_summary LLM call pattern")

# Replace /ask endpoint LLM call
old_ask = """        completion = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are Master AI, a helpful home automation assistant. Answer concisely."},
                {"role": "user", "content": body.prompt},
            ],
            max_tokens=1024, temperature=0.7,
        )
        return AskResponse(response=completion.choices[0].message.content.strip())"""

new_ask = """        result = await llm_call("You are Master AI, a helpful home automation assistant for Bu Khalifa. Answer concisely in Kuwaiti Arabic.", body.prompt, max_tokens=1024, temperature=0.7)
        return AskResponse(response=result)"""

if old_ask in code:
    code = code.replace(old_ask, new_ask)
    changes += 1
    print("+ Replaced /ask LLM call")
else:
    print("! Could not find /ask LLM call pattern")

# Also fix the error handler for plan_actions (OpenAIError -> general Exception)
code = code.replace(
    "except OpenAIError as e:\n        logger.error(\"Planner OpenAI error: %s\", e)\n        return [{\"type\": \"respond_text\", \"args\": {\"text\": f\"OpenAI error: {str(e)}\"}, \"risk\": \"low\", \"why\": \"API error\"}]",
    "except Exception as e:\n        logger.error(\"LLM planner error: %s\", e)\n        return [{\"type\": \"respond_text\", \"args\": {\"text\": f\"AI error: {str(e)}\"}, \"risk\": \"low\", \"why\": \"API error\"}]"
)

# Fix ask endpoint error handler too
code = code.replace(
    "except OpenAIError as e:\n        return JSONResponse(status_code=502, content={\"error\": \"OpenAI error\", \"detail\": str(e)})",
    "except Exception as e:\n        return JSONResponse(status_code=502, content={\"error\": \"AI error\", \"detail\": str(e)})"
)

with open(path, "w") as f:
    f.write(code)

remaining = code.count('gpt-4o-mini')
print(f"\nTotal changes: {changes}")
print(f"Remaining gpt-4o-mini refs: {remaining}")
print(f"Claude Opus references: {code.count('claude-opus')}")
