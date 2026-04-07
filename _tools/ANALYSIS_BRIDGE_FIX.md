# Fix: stock_analyzer.py — Bridge Health Check Before Analysis
# Date: 2026-04-04
# Status: READY

## Problem:
stock_analyzer.py calls Bridge with 30s timeout.
When Bridge is offline, it hangs for 30 seconds before returning error.
No DegradedMode protection.

## Fix:
In stock_analyzer.py, add a quick health check (2s timeout) before doing the full analysis:

```python
def _bridge_available():
    """Quick check if Bridge is reachable (2s timeout)."""
    try:
        req = urllib.request.urlopen(f"{BRIDGE_BASE}/health", timeout=2)
        return req.status == 200
    except:
        return False

def analyze_stock(symbol):
    # Check cache first
    cached = _analysis_cache.get(symbol)
    if cached and (time.time() - cached['ts']) < CACHE_TTL:
        return cached['data']
    
    # Quick Bridge check BEFORE heavy calls
    if not _bridge_available():
        return {"error": "Bridge offline — التحليل يحتاج Bridge شغّال"}
    
    # ... rest of analysis
```

## Files:
- MODIFY: stock_analyzer.py (add _bridge_available check)

## Claude Code command:
> في stock_analyzer.py، أضف function _bridge_available() يسوي health check بـ 2 ثانية timeout. واستدعيها أول شي في analyze_stock() — لو رجعت False، ارجع error فوراً بدون ما تحاول تسحب بيانات.
