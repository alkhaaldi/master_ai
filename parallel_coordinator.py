"""
Parallel Coordinator for Master AI (Tier3 #18).

Runs independent analysis tasks concurrently with structured result collection.
Based on Claude Code's coordinatorMode.ts pattern.

Usage:
    coord = ParallelCoordinator("analyze_stocks")
    coord.add_worker("CLEANING", analyze_stock, ticker="CLEANING")
    coord.add_worker("SENERGY", analyze_stock, ticker="SENERGY")
    results = await coord.run(max_concurrent=5, timeout=30)
"""

import asyncio
import logging
import time
from typing import Any, Callable, Awaitable, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("parallel_coordinator")


@dataclass
class WorkerResult:
    name: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    duration_ms: int = 0


class ParallelCoordinator:
    """Run multiple independent tasks in parallel and collect results."""

    def __init__(self, name: str):
        self.name = name
        self._workers: list[tuple[str, Callable, dict]] = []

    def add_worker(self, name: str, func: Callable[..., Awaitable], **kwargs):
        self._workers.append((name, func, kwargs))

    async def run(
        self,
        max_concurrent: int = 10,
        timeout: float = 60.0,
        on_progress: Optional[Callable] = None,
    ) -> list[WorkerResult]:
        """Run all workers with concurrency limit.
        on_progress(worker_name, completed, total) called after each worker."""
        semaphore = asyncio.Semaphore(max_concurrent)
        results: list[WorkerResult] = []
        completed = 0
        total = len(self._workers)

        async def run_one(wname: str, func: Callable, kwargs: dict):
            nonlocal completed
            async with semaphore:
                start = time.time()
                try:
                    result = await asyncio.wait_for(func(**kwargs), timeout=timeout)
                    wr = WorkerResult(
                        name=wname, success=True, result=result,
                        duration_ms=int((time.time() - start) * 1000),
                    )
                except asyncio.TimeoutError:
                    wr = WorkerResult(
                        name=wname, success=False, error="timeout",
                        duration_ms=int((time.time() - start) * 1000),
                    )
                except Exception as e:
                    wr = WorkerResult(
                        name=wname, success=False, error=str(e)[:200],
                        duration_ms=int((time.time() - start) * 1000),
                    )
                results.append(wr)
                completed += 1
                if on_progress:
                    try:
                        on_progress(wname, completed, total)
                    except Exception:
                        pass
                return wr

        tasks = [run_one(n, f, kw) for n, f, kw in self._workers]
        await asyncio.gather(*tasks, return_exceptions=True)
        return results

    def summarize(self, results: list[WorkerResult]) -> str:
        """Quick text summary of results."""
        ok = sum(1 for r in results if r.success)
        fail = sum(1 for r in results if not r.success)
        total_ms = sum(r.duration_ms for r in results)
        lines = [f"✅ {ok} succeeded, ❌ {fail} failed ({total_ms}ms total)"]
        for r in results:
            if not r.success:
                lines.append(f"  ❌ {r.name}: {r.error}")
        return "\n".join(lines)
