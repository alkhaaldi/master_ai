"""
Coalesced Background Execution (Tier2 #12).

Prevents overlapping background operations. When a background operation
is already running and a new request comes in, stash the request and
run ONE trailing execution after the current one finishes.

Usage:
    executor = CoalescedExecutor("radar_refresh")
    result = await executor.run(refresh_all_stocks, symbols=symbols)
    # If called again while running, second call waits for trailing run
"""

import asyncio
import logging
from typing import Optional, Callable, Awaitable, Any

logger = logging.getLogger("coalesced_executor")


class CoalescedExecutor:
    """Ensures only one instance of an operation runs at a time.
    Additional requests are coalesced — only the latest is kept."""

    def __init__(self, name: str):
        self.name = name
        self._in_progress = False
        self._pending_args: Optional[dict] = None
        self._pending_future: Optional[asyncio.Future] = None
        self._run_count = 0
        self._coalesced_count = 0

    @property
    def is_running(self) -> bool:
        return self._in_progress

    async def run(self, func: Callable[..., Awaitable], **kwargs) -> Any:
        """Run func if not already running. If running, stash for trailing run."""
        if self._in_progress:
            self._coalesced_count += 1
            logger.debug("[%s] coalescing request (%d coalesced)", self.name, self._coalesced_count)
            self._pending_args = kwargs
            if self._pending_future is None:
                loop = asyncio.get_running_loop()
                self._pending_future = loop.create_future()
            return await self._pending_future

        self._in_progress = True
        self._run_count += 1
        try:
            result = await func(**kwargs)
            return result
        finally:
            self._in_progress = False
            if self._pending_args is not None:
                trailing_args = self._pending_args
                trailing_future = self._pending_future
                self._pending_args = None
                self._pending_future = None
                logger.debug("[%s] executing trailing run", self.name)
                try:
                    trailing_result = await self.run(func, **trailing_args)
                    if trailing_future and not trailing_future.done():
                        trailing_future.set_result(trailing_result)
                except Exception as e:
                    if trailing_future and not trailing_future.done():
                        trailing_future.set_exception(e)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "is_running": self._in_progress,
            "run_count": self._run_count,
            "coalesced_count": self._coalesced_count,
        }


# Pre-built executors for major operations
radar_executor = CoalescedExecutor("radar_refresh")
daily_snapshot_executor = CoalescedExecutor("daily_snapshot")
news_executor = CoalescedExecutor("news_fetch")
