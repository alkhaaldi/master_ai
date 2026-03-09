"""
chat_v7.py — Direct LLM + Tool Use (Anthropic native)
NO planner. NO JSON. NO synthesis. NO truncation.
"""
import json, time, logging
logger = logging.getLogger("chat_v7")

TOOLS = [
    {
        "name": "ha_get_state",
        "description": "Get Home Assistant entity state. entity_id='*' for ALL, or patterns: 'climate.*', 'light.*living*', 'camera.*', 'automation.*', 'cover.*', 'lock.*'",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity ID or pattern. '*'=all, 'climate.*'=ACs, 'automation.*'=automations"}
            },
            "required": ["entity_id"]
        }
    },
    {
        "name": "ha_call_service",
        "description": "Call HA service. Controls: lights, ACs, covers(INVERTED!), automations, scenes, locks, fans(شفاط/منقي/معطر).",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "service": {"type": "string"},
                "service_data": {"type": "object"}
            },
            "required": ["domain", "service", "service_data"]
        }
    },
    {
        "name": "ssh_run",
        "description": "Run shell command on RPi. For: system health, logs, services, network diagnostics.",
        "input_schema": {
            "type": "object",
            "properties": {"cmd": {"type": "string"}},
            "required": ["cmd"]
        }
    },
    {
        "name": "http_request",
        "description": "HTTP request. Internal: localhost:9000/health, /brain/stats, /brain/expertise?domain=X, /system/knowledge",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "method": {"type": "string", "default": "GET"}
            },
            "required": ["url"]
        }
    }
]

MAX_ROUNDS = 8

async def execute_tool(name, args, executors):
    try:
        if name == "ha_get_state":
            r = await executors["ha_get_state"](args["entity_id"])
            return json.dumps(r, ensure_ascii=False, default=str)[:8000]
        elif name == "ha_call_service":
            r = await executors["ha_call_service"](args["domain"], args["service"], args.get("service_data", {}))
            return json.dumps(r, ensure_ascii=False, default=str)[:4000]
        elif name == "ssh_run":
            r = await executors["ssh_run"](args["cmd"])
            return json.dumps(r, ensure_ascii=False, default=str)[:4000]
        elif name == "http_request":
            import httpx
            async with httpx.AsyncClient(timeout=10) as c:
                resp = await c.get(args["url"])
                return resp.text[:4000]
        return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def handle_chat_v7(user_text, system_prompt, client, executors, model="claude-opus-4-20250514", max_tokens=4096):
    t0 = time.time()
    messages = [{"role": "user", "content": user_text}]
    tools_used = []
    
    for _ in range(MAX_ROUNDS):
        try:
            resp = await client.messages.create(
                model=model, max_tokens=max_tokens, system=system_prompt,
                messages=messages, tools=TOOLS, temperature=0.3
            )
        except Exception as e:
            logger.error(f"chat_v7 LLM error: {e}")
            return f"خطأ: {e}"
        
        if resp.stop_reason == "tool_use":
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    logger.info(f"chat_v7 tool: {block.name}({json.dumps(block.input, ensure_ascii=False)[:80]})")
                    tools_used.append(block.name)
                    result = await execute_tool(block.name, block.input, executors)
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content": tool_results})
        
        elif resp.stop_reason == "end_turn":
            parts = [b.text for b in resp.content if hasattr(b, "text")]
            final = "\n".join(parts)
            logger.info(f"chat_v7: {len(tools_used)} tools, {time.time()-t0:.1f}s, {len(final)} chars")
            return final
        else:
            parts = [b.text for b in resp.content if hasattr(b, "text")]
            return "\n".join(parts) if parts else "ما قدرت أكمل"
    
    return "وصلت الحد الأقصى — جرب سؤال أبسط"
