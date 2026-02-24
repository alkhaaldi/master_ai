path = "/home/pi/master_ai/server.py"
with open(path) as f:
    lines = f.readlines()

# Find and replace lines 437-447 (the summary LLM call)
new_lines = []
skip_until = -1
for i, line in enumerate(lines):
    if skip_until > 0 and i < skip_until:
        continue
    skip_until = -1
    
    # Line 437 (0-indexed) = the openai_client call in summary
    if 'openai_client.chat.completions.create' in line and i > 430 and i < 450:
        # Replace from this line to "return completion.choices..."
        indent = "        "
        new_lines.append(indent + 'result = await llm_call("Summarize smart home/PC action results in 1-2 sentences. Concise.", f"Task: {task}\\nResults: {\'; \'.join(context_parts)}", max_tokens=150, temperature=0.3)\n')
        new_lines.append(indent + "return result\n")
        # Skip lines until "except:"
        j = i + 1
        while j < len(lines) and "except:" not in lines[j]:
            j += 1
        skip_until = j
        print(f"Replaced lines {i+1} to {j+1}")
        continue
    
    new_lines.append(line)

with open(path, "w") as f:
    f.writelines(new_lines)

# Verify
with open(path) as f:
    content = f.read()
count = content.count("gpt-4o-mini")
print(f"Remaining gpt-4o-mini: {count}")
print(f"llm_call refs: {content.count('llm_call')}")
