"""
Memory Prefetch — Speculative Loading (Tier3 #21).

Start Brain observation lookup BEFORE intent parsing completes.
While the LLM or intent router is processing, memories are being
retrieved in the background.

Based on Claude Code's QueryEngine memory prefetch pattern.

Usage:
    prefetch = MemoryPrefetcher(user_message, anthropic_client)
    # ... do intent routing, validation, etc ...
    memories = await prefetch.get_result()  # usually already done
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger("memory_prefetch")


class MemoryPrefetcher:
    """Start memory retrieval as soon as a message arrives.
    Don't wait for intent routing to complete."""

    def __init__(self, query: str, anthropic_client=None, scope: str = None):
        self._query = query
        self._client = anthropic_client
        self._scope = scope
        self._result: Optional[list] = None
        self._task = asyncio.create_task(self._fetch())

    async def _fetch(self) -> list:
        try:
            from memory_recall import find_relevant_memories
            return await find_relevant_memories(
                query=self._query,
                anthropic_client=self._client,
                category=self._scope,
                max_selected=5,
            )
        except Exception as e:
            logger.debug("[prefetch] fetch failed: %s", e)
            return []

    async def get_result(self, timeout: float = 5.0) -> list:
        """Get prefetched results. If not ready, wait up to timeout."""
        if self._result is not None:
            return self._result
        try:
            self._result = await asyncio.wait_for(self._task, timeout=timeout)
        except asyncio.TimeoutError:
            logger.debug("[prefetch] timeout after %.1fs", timeout)
            self._result = []
        except Exception:
            self._result = []
        return self._result

    @property
    def is_ready(self) -> bool:
        return self._task.done()

    def cancel(self):
        """Cancel prefetch if no longer needed."""
        if not self._task.done():
            self._task.cancel()
