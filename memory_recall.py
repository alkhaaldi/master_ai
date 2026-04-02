"""
LLM-Ranked Memory Recall for Master AI (Tier2 #10).

Given a user query/intent, uses Haiku to select the most relevant
Brain observations from the manifest (Pattern #9).

Based on Claude Code's findRelevantMemories.ts pattern:
- Scan manifest (lightweight headers only)
- Ask LLM to select top 5 most relevant
- Load full text only for selected items
- Tag stale items with warnings (Tier 1 staleness)
"""

import json
import logging
from typing import Optional

logger = logging.getLogger("memory_recall")

SELECT_MEMORIES_PROMPT = """You are selecting observations that will be useful for answering a user's query.
You will be given the query and a list of available observations with their summaries.

Return a JSON object with a "selected_ids" array containing the IDs of observations
that will clearly be useful (up to 5). Only include observations you are certain
will be helpful based on their summary and domain.

- If unsure, do not include it. Be selective.
- If nothing is clearly relevant, return an empty list.
- Prefer recent observations over old ones when relevance is similar.

Return ONLY valid JSON: {"selected_ids": [1, 5, 23]}"""


async def find_relevant_memories(
    query: str,
    anthropic_client=None,
    category: str = None,
    max_candidates: int = 200,
    max_selected: int = 5,
    already_surfaced: set = None,
) -> list:
    """
    Find the most relevant Brain observations for a query.

    Args:
        query: User's question or intent
        anthropic_client: AsyncAnthropic instance (from server.py)
        category: Optional filter (e.g., "trading", "ha")
        max_candidates: Max observations to consider
        max_selected: Max observations to return (default 5)
        already_surfaced: Set of observation IDs already shown (dedup)

    Returns:
        List of full observation dicts, each tagged with staleness warning
    """
    from brain_core import (
        get_observation_manifest,
        format_observation_manifest,
        get_full_observations,
    )

    already_surfaced = already_surfaced or set()

    # Step 1: Get lightweight manifest
    manifest = get_observation_manifest(category=category, max_items=max_candidates)

    # Filter already-surfaced
    manifest = [m for m in manifest if m["id"] not in already_surfaced]

    if not manifest:
        return []

    # Step 2: Format manifest for LLM
    manifest_text = format_observation_manifest(manifest)
    valid_ids = {m["id"] for m in manifest}

    # Step 3: Ask Haiku to select relevant observations
    selected_ids = []
    try:
        if anthropic_client:
            response = await anthropic_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=256,
                system=SELECT_MEMORIES_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Query: {query}\n\nAvailable observations:\n{manifest_text}",
                }],
            )
            text = response.content[0].text.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(text)
            selected_ids = parsed.get("selected_ids", [])
            selected_ids = [i for i in selected_ids if i in valid_ids]
            selected_ids = selected_ids[:max_selected]
        else:
            logger.info("[memory_recall] No LLM client — using recency fallback")
            selected_ids = [m["id"] for m in manifest[:max_selected]]
    except Exception as e:
        logger.warning("[memory_recall] LLM selection failed: %s — using recency fallback", e)
        selected_ids = [m["id"] for m in manifest[:max_selected]]

    if not selected_ids:
        return []

    # Step 4: Load full observations for selected IDs only
    return get_full_observations(selected_ids)
