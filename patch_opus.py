import re

path = "/home/pi/master_ai/server.py"
with open(path) as f:
    code = f.read()

# Backup
with open(path + ".pre_opus_bak", "w") as f:
    f.write(code)

changes = 0

# 1. Add anthropic import after openai import
if "from anthropic import" not in code:
    code = code.replace(
        "from openai import AsyncOpenAI, OpenAIError",
        "from openai import AsyncOpenAI, OpenAIError\nfrom anthropic import AsyncAnthropic"
    )
    changes += 1
    print("+ Added anthropic import")

# 2. Add ANTHROPIC_API_KEY loading after OPENAI key loading
if "ANTHROPIC_API_KEY" not in code:
    code = code.replace(
        'logger.info("OPENAI_API_KEY loaded (ends ...%s)", api_key[-4:])',
        'logger.info("OPENAI_API_KEY loaded (ends ...%s)", api_key[-4:])\n\nanthropic_key = os.getenv("ANTHROPIC_API_KEY", "")\nif anthropic_key:\n    logger.info("ANTHROPIC_API_KEY loaded (ends ...%s)", anthropic_key[-4:])\nelse:\n    logger.warning("ANTHROPIC_API_KEY not found - will use OpenAI only")'
    )
    changes += 1
    print("+ Added ANTHROPIC_API_KEY loading")

# 3. Add anthropic client after openai client
if "anthropic_client" not in code:
    code = code.replace(
        "openai_client = AsyncOpenAI(api_key=api_key)",
        "openai_client = AsyncOpenAI(api_key=api_key)\nanthropic_client = AsyncAnthropic(api_key=anthropic_key) if anthropic_key else None"
    )
    changes += 1
    print("+ Added anthropic_client")

# 4. Replace plan_actions to use Claude Opus
# Find the plan_actions function and replace the LLM call
old_plan = '''completion = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},'''

new_plan = '''# Use Claude Opus if available, fallback to OpenAI
        if anthropic_client:
            response = await anthropic_client.messages.create(
                model="claude-opus-4-6",
                max_tokens=2000,
                system=PLANNER_SYSTEM_PROMPT,
                messages=['''

# Simpler: just replace model references and add a wrapper
# Let's replace all 3 LLM calls

# Count gpt-4o-mini occurrences
count = code.count('model="gpt-4o-mini"')
print(f"Found {count} gpt-4o-mini references")

# Write the patched code
with open(path, "w") as f:
    f.write(code)

print(f"Applied {changes} changes to server.py")
print("NOTE: Model swap requires rewriting the LLM call functions - see below")
