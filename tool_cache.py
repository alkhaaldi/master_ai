"""
tool_cache.py — Tool result caching + parallel execution for Master AI
Phase 2 Performance: reduces response time by executing tools in parallel
and caching frequently-accessed read-only results.
"""

import asyncio
import time
import hashlib
import json
import logging

logger = logging.getLogger("tool_cache")

_cache = {}
CACHE_TTL = {
    "ha_get_state": 30,
    "get_weather": 300,
    "get_shift": 3600,
    "get_system_info": 60,
    "memory_search": 120,
    "structured_memory_search": 120,
}

CACHEABLE_TOOLS = set(CACHE_TTL.keys())
PARALLELIZABLE_TOOLS = {
    "ha_get_state", "get_weather", "get_shift", "get_system_info",
    "memory_search", "structured_memory_search",
}


def _cache_key(name, args):
    args_str = json.dumps(args, sort_keys=True, ensure_ascii=False)
    return f"{name}:{hashlib.md5(args_str.encode()).hexdigest()[:12]}"


def cache_get(name, args):
    if name not in CACHEABLE_TOOLS:
        return False, None
    key = _cache_key(name, args)
    if key in _cache:
        result, ts = _cache[key]
        ttl = CACHE_TTL.get(name, 30)
        if time.time() - ts < ttl:
            logger.debug(f"Cache HIT: {name}")
            return True, result
        else:
            del _cache[key]
    return False, None


def cache_set(name, args, result):
    if name not in CACHEABLE_TOOLS:
        return
    key = _cache_key(name, args)
    _cache[key] = (result, time.time())
    if len(_cache) > 100:
        oldest = sorted(_cache.items(), key=lambda x: x[1][1])[:20]
        for k, _ in oldest:
            del _cache[k]


def cache_clear():
    _cache.clear()


def cache_stats():
    now = time.time()
    active = sum(1 for k, (_, ts) in _cache.items()
                 if now - ts < CACHE_TTL.get(k.split(":")[0], 30))
    return {"total": len(_cache), "active": active}


async def execute_tools_parallel(tool_blocks, execute_tool_fn, executors):
    if len(tool_blocks) <= 1:
        name, args, tool_id = tool_blocks[0]
        hit, cached = cache_get(name, args)
        if hit:
            return [{"type": "tool_result", "tool_use_id": tool_id, "content": cached}]
        result = await execute_tool_fn(name, args, executors)
        cache_set(name, args, result)
        return [{"type": "tool_result", "tool_use_id": tool_id, "content": result}]

    parallel = []
    sequential = []
    for name, args, tool_id in tool_blocks:
        if name in PARALLELIZABLE_TOOLS:
            parallel.append((name, args, tool_id))
        else:
            sequential.append((name, args, tool_id))

    results = {}

    if parallel:
        async def _run(name, args, tool_id):
            hit, cached = cache_get(name, args)
            if hit:
                return tool_id, cached
            result = await execute_tool_fn(name, args, executors)
            cache_set(name, args, result)
            return tool_id, result

        tasks = [_run(n, a, tid) for n, a, tid in parallel]
        for pr in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(pr, Exception):
                logger.warning(f"Parallel tool error: {pr}")
                continue
            tool_id, result = pr
            results[tool_id] = result

    for name, args, tool_id in sequential:
        hit, cached = cache_get(name, args)
        if hit:
            results[tool_id] = cached
            continue
        result = await execute_tool_fn(name, args, executors)
        cache_set(name, args, result)
        results[tool_id] = result

    return [
        {"type": "tool_result", "tool_use_id": tid, "content": results.get(tid, "error: tool failed")}
        for _, _, tid in tool_blocks
    ]
