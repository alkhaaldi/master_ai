"""
Multi-Layer Context Management for Master AI chat (Tier3 #15).

Manages conversation context to prevent token overflow.
4 layers, cheapest first — expensive layers only run if needed.

Based on Claude Code's query.ts 4-layer compaction:
1. TRIM — remove old messages (free)
2. COMPRESS — truncate long tool outputs (free)
3. SUMMARIZE — LLM summarizes old messages (expensive)
4. EMERGENCY — hard truncate (last resort)
"""

import logging
from typing import Optional

logger = logging.getLogger("context_manager")

# Token estimates (rough: 1 token ~ 3 chars for mixed Arabic/English)
MAX_CONTEXT_TOKENS = 180000
TRIM_THRESHOLD = 120000
COMPRESS_THRESHOLD = 150000
SUMMARIZE_THRESHOLD = 170000


def estimate_tokens(messages: list[dict]) -> int:
    """Rough token estimate for a message list."""
    total_chars = sum(len(m.get("content", "")) for m in messages)
    return total_chars // 3


def layer1_trim(messages: list[dict], keep_last: int = 10) -> list[dict]:
    """Layer 1: TRIM — Remove old messages, keep recent ones. FREE."""
    if len(messages) <= keep_last + 1:
        return messages

    system_msgs = [m for m in messages[:2] if m.get("role") == "system"]
    recent = messages[-keep_last:]

    trimmed = system_msgs + [{
        "role": "system",
        "content": f"[تم اختصار {len(messages) - len(system_msgs) - keep_last} رسالة سابقة]"
    }] + recent

    logger.info("[context] Layer 1 TRIM: %d -> %d messages", len(messages), len(trimmed))
    return trimmed


def layer2_compress(messages: list[dict], max_tool_chars: int = 500) -> list[dict]:
    """Layer 2: COMPRESS — Truncate long tool outputs. FREE."""
    compressed = []
    for m in messages:
        content = m.get("content", "")
        if len(content) > max_tool_chars and m.get("role") == "assistant":
            if any(ind in content[:200] for ind in ['{', '[', '|', 'RSI', 'MACD', 'EMA']):
                short = content[:max_tool_chars] + f"\n... [{len(content) - max_tool_chars} chars truncated]"
                compressed.append({**m, "content": short})
                continue
        compressed.append(m)
    return compressed


async def layer3_summarize(messages: list[dict], anthropic_client=None) -> list[dict]:
    """Layer 3: SUMMARIZE — LLM summarizes old conversation. EXPENSIVE."""
    if len(messages) <= 6:
        return messages

    to_summarize = messages[:-5]
    to_keep = messages[-5:]

    summary_text = "\n".join([
        f"{m.get('role', '?')}: {m.get('content', '')[:200]}"
        for m in to_summarize
    ])

    summary = f"ملخص: {len(to_summarize)} رسالة سابقة"

    if anthropic_client:
        try:
            _ctx_model = __import__("model_tiers").MODEL_CHEAP
            response = await anthropic_client.messages.create(
                model=_ctx_model,
                max_tokens=500,
                system="Summarize this conversation in Arabic. Focus on decisions, topics, current state. Max 200 words.",
                messages=[{"role": "user", "content": summary_text}],
            )
            summary = response.content[0].text
            try:
                from cost_tracker import track_cost
                track_cost(response.usage, _ctx_model, source="context_mgr")
            except Exception:
                pass
        except Exception as e:
            logger.warning("[context] Layer 3 summarize LLM failed: %s", e)

    result = [{
        "role": "system",
        "content": f"ملخص المحادثة السابقة:\n{summary}"
    }] + to_keep

    logger.info("[context] Layer 3 SUMMARIZE: %d -> %d messages", len(messages), len(result))
    return result


def layer4_emergency(messages: list[dict], max_messages: int = 5) -> list[dict]:
    """Layer 4: EMERGENCY — Hard truncate. Last resort."""
    if len(messages) <= max_messages:
        return messages
    result = [{
        "role": "system",
        "content": "تم اختصار المحادثة بسبب طول السياق"
    }] + messages[-max_messages:]
    logger.warning("[context] Layer 4 EMERGENCY: %d -> %d", len(messages), len(result))
    return result


async def manage_context(messages: list[dict], anthropic_client=None) -> list[dict]:
    """Main entry point. Apply layers as needed (cheapest first)."""
    tokens = estimate_tokens(messages)

    if tokens < TRIM_THRESHOLD:
        return messages

    # Layer 1: TRIM
    messages = layer1_trim(messages)
    tokens = estimate_tokens(messages)
    if tokens < COMPRESS_THRESHOLD:
        return messages

    # Layer 2: COMPRESS
    messages = layer2_compress(messages)
    tokens = estimate_tokens(messages)
    if tokens < SUMMARIZE_THRESHOLD:
        return messages

    # Layer 3: SUMMARIZE
    messages = await layer3_summarize(messages, anthropic_client)
    tokens = estimate_tokens(messages)
    if tokens < MAX_CONTEXT_TOKENS:
        return messages

    # Layer 4: EMERGENCY
    return layer4_emergency(messages)
