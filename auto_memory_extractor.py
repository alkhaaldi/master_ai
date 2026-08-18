"""
Automatic Memory Extraction from Conversations (Tier3 #16).

After each meaningful Telegram conversation, runs a background task
that analyzes what happened and extracts durable observations.

Based on Claude Code's extractMemories.ts pattern.
Uses: processing_cursor.py (Tier1 #7), coalesced_executor.py (Tier2 #12)
"""

import asyncio
import json
import logging
import sqlite3
import os
import time
from typing import Optional

from processing_cursor import ProcessingCursor
from coalesced_executor import CoalescedExecutor

logger = logging.getLogger("auto_memory")

_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "audit.db")

MIN_MESSAGES_FOR_EXTRACTION = 3

EXTRACTION_PROMPT = """You are analyzing a conversation between a user and an AI assistant.
Extract any DURABLE observations worth remembering for future conversations.

Focus on:
- Decisions the user made (bought/sold stock, changed HA setting, etc.)
- Preferences expressed (likes/dislikes, preferred approaches)
- Facts learned about the user's situation (new position, schedule change)
- Problems encountered and their solutions

Do NOT extract:
- Temporary states ("Bridge is offline right now")
- Generic information (stock prices, weather)
- Anything already in the existing observations

Return a JSON array of observations:
[
  {"category": "trading", "type": "decision", "scope": "stock",
   "content": "observation text here"}
]

Valid categories: trading, ha, personal, preference, pattern
Valid scopes: global, stock, device
Valid types: fact, decision, preference, pattern

Return ONLY valid JSON. If nothing worth extracting, return [].
"""


class AutoMemoryExtractor:
    """Background memory extraction from Telegram conversations."""

    def __init__(self, anthropic_client=None):
        self._cursor = ProcessingCursor("auto_memory_extraction")
        self._executor = CoalescedExecutor("memory_extraction")
        self._messages: list[dict] = []
        self._msg_count_since_last = 0
        self._client = anthropic_client

    def set_client(self, client):
        self._client = client

    def record_message(self, role: str, content: str):
        """Record a message and maybe trigger extraction."""
        self._messages.append({
            "role": role,
            "content": content[:1000],
            "timestamp": time.time(),
        })
        if role == "user":
            self._msg_count_since_last += 1

        if (role == "assistant" and
                self._msg_count_since_last >= MIN_MESSAGES_FOR_EXTRACTION):
            asyncio.create_task(self._maybe_extract())

    async def _maybe_extract(self):
        await self._executor.run(self._do_extraction)

    async def _do_extraction(self):
        if not self._messages:
            return

        messages_to_process = self._messages[-20:]
        conv_text = "\n".join([
            f"{'User' if m['role'] == 'user' else 'AI'}: {m['content']}"
            for m in messages_to_process
        ])

        # Get existing observations to avoid duplicates
        try:
            from brain_core import get_observation_manifest, format_observation_manifest
            existing = format_observation_manifest(
                get_observation_manifest(max_items=30)
            )
        except Exception:
            existing = ""

        observations = []

        if self._client:
            try:
                response = await self._client.messages.create(
                    model=__import__("model_tiers").MODEL_CHEAP,
                    max_tokens=1024,
                    system=EXTRACTION_PROMPT,
                    messages=[{
                        "role": "user",
                        "content": f"Existing observations (avoid duplicates):\n{existing}\n\n---\n\nConversation:\n{conv_text}",
                    }],
                )
                text = response.content[0].text.strip()
                text = text.replace("```json", "").replace("```", "").strip()
                observations = json.loads(text)
            except Exception as e:
                logger.warning("[auto_mem] LLM extraction failed: %s", e)
                observations = []
        else:
            # Fallback: simple keyword extraction (no LLM)
            observations = self._keyword_extract(conv_text)

        if not observations or not isinstance(observations, list):
            logger.debug("[auto_mem] No observations extracted")
            self._msg_count_since_last = 0
            return

        # Save to memory table
        try:
            conn = sqlite3.connect(_DB_PATH, timeout=5)
            saved = 0
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            for obs in observations:
                if not isinstance(obs, dict):
                    continue
                cat = obs.get("category", "general")
                typ = obs.get("type", "fact")
                scope = obs.get("scope", "global")
                content = obs.get("content", "")
                if not content or len(content) < 10:
                    continue
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO memory "
                        "(category, type, content, scope, source, confidence, created_at, updated_at, active) "
                        "VALUES (?, ?, ?, ?, 'auto_extract', 0.7, ?, ?, 1)",
                        (cat, typ, content, scope, now, now),
                    )
                    saved += 1
                except sqlite3.IntegrityError:
                    pass  # duplicate
            conn.commit()
            conn.close()
            if saved:
                logger.info("[auto_mem] Extracted %d observations from %d messages", saved, len(messages_to_process))
        except Exception as e:
            logger.warning("[auto_mem] DB save failed: %s", e)

        self._msg_count_since_last = 0

    @staticmethod
    def _keyword_extract(text: str) -> list:
        """Simple fallback: extract obvious decisions/preferences without LLM."""
        import re
        observations = []
        # Look for stock decisions
        stock_pattern = r'(شريت|بعت|قررت|اشتري|ابيع)\s+(\w+)'
        for match in re.finditer(stock_pattern, text):
            action, entity = match.groups()
            observations.append({
                "category": "trading",
                "type": "decision",
                "scope": "stock",
                "content": f"{action} {entity}",
            })
        # Look for preference statements
        pref_pattern = r'(أفضل|أبي|ابي|حط|خل)\s+(.{10,60})'
        for match in re.finditer(pref_pattern, text):
            _, detail = match.groups()
            observations.append({
                "category": "preference",
                "type": "preference",
                "scope": "global",
                "content": detail.strip(),
            })
        return observations[:3]  # max 3 from keyword fallback
