# Fix: Parallelize Analysis Refresh — Use ParallelCoordinator
# Date: 2026-04-04
# Priority: HIGH — 128 stocks taking 30+ min sequentially

## Problem:
refresh_all_analyses() in stock_analyzer.py runs SEQUENTIALLY:
  for sym in symbols:
      analyze_stock(sym)
      time.sleep(4)
128 stocks × 14 sec each = ~30 minutes. Too slow.

## Fix:
Use ParallelCoordinator (Tier3 #18, already built) to run
5 stocks in parallel. 128 / 5 = 26 batches × 14 sec = ~6 minutes.

## Changes to stock_analyzer.py:

```python
import asyncio
from parallel_coordinator import ParallelCoordinator

async def refresh_all_analyses_parallel(send_update=None, max_concurrent=5):
    """Refresh ALL 128 stocks using ParallelCoordinator."""
    symbols = get_all_kse_symbols()
    if not symbols:
        return {"error": "no symbols found"}
    if not _bridge_available():
        return {"error": "Bridge offline"}

    total = len(symbols)
    done = 0
    errors = 0
    error_list = []

    # Process in batches of max_concurrent
    for i in range(0, total, max_concurrent):
        batch = symbols[i:i+max_concurrent]
        coord = ParallelCoordinator(f"analysis_batch_{i}")
        
        for sym in batch:
            async def _analyze(s=sym):
                return analyze_stock(s)  # existing sync function
            coord.add_worker(sym, _analyze)
        
        results = await coord.run(max_concurrent=max_concurrent, timeout=60)
        
        for wr in results:
            if wr.success and wr.result and not wr.result.get('error'):
                store_analysis(wr.name, wr.result)
                done += 1
            else:
                errors += 1
                err = wr.error or (wr.result.get('error') if wr.result else 'unknown')
                error_list.append(f"{wr.name}: {err}")
        
        if send_update and (done + errors) % 20 < max_concurrent:
            send_update(f"تحليل: {done+errors}/{total} ({errors} أخطاء)")
        
        await asyncio.sleep(1)  # brief pause between batches

    return {"total": total, "done": done, "errors": errors, "error_details": error_list[:10]}
```

## Changes to server.py:
Update POST /api/analyze/refresh-all to call refresh_all_analyses_parallel instead of refresh_all_analyses.

## Expected improvement:
Sequential: 128 × 14 sec = ~30 min
Parallel (5): 26 batches × 14 sec = ~6 min
Parallel (10): 13 batches × 14 sec = ~3 min

## Note on Gemini rate limits:
Free tier = 15 req/min. With 5 parallel = 5 req per 14 sec ≈ 21 req/min.
May need to reduce to max_concurrent=3 if hitting rate limits.
Or add per-request delay inside _analyze.

## Claude Code command:
> Read _tools/PARALLEL_ANALYSIS_FIX.md — refresh_all_analyses is too slow (sequential). Use ParallelCoordinator to run 5 stocks in parallel. Keep the old sync function as fallback. Update the /api/analyze/refresh-all endpoint to use the parallel version.
