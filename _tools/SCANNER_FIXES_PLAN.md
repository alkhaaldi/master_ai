# Scanner Fixes — Two Issues
# Date: 2026-04-01
# Priority: HIGH — execute immediately

## Issue 1: Scanner blocks analysis outside market hours
### Problem
Manual scans and the prefilter shouldn't be blocked by market hours check.
The Scanner fetches HISTORICAL candle data from Bridge (100x 30m + 60x 1D),
not live streaming data. This data is always available regardless of market session.

### Fix
In `gemini_scanner.py`, the market hours check should ONLY skip SCHEDULED scans,
NOT manual scans. Change the logic:

```python
# BEFORE (wrong):
if market_session != "open" and scan_type != "manual":
    # skip

# AFTER (correct):
if scan_type == "scheduled" and market_session != "open":
    # skip scheduled scans outside market hours
    # BUT allow manual scans anytime
```

Make sure `scan_type="manual"` (from POST /api/scanner/scan) always runs regardless of market hours.

## Issue 2: Only 17 stocks analyzed instead of 92
### Problem
The prefilter is too aggressive — filtering 92 stocks down to only 17.
With the new filtered universe (92 active stocks), the prefilter should pass more candidates.

### Root Cause
The prefilter criteria (volume > 0, price movement, data freshness) may be
filtering out stocks that have valid historical data but no LIVE movement
(because market is closed).

### Fix
1. When market is CLOSED, relax the prefilter:
   - Don't require live volume > 0 (market is closed, no live volume)
   - Don't require price_change != 0 (no change when market closed)
   - Use historical daily data instead of live 30m data for prefilter
   
2. When market is OPEN, keep the current prefilter logic (it's correct).

3. The prefilter should pass AT LEAST 20-30 candidates to Gemini.
   If fewer than 20 pass, lower the threshold automatically.

### Suggested prefilter logic:
```python
async def _prefilter_universe(self):
    universe = get_scanner_universe()  # 92 stocks
    
    # Get indicators for all stocks (from Bridge cache or live)
    active = []
    for symbol in universe:
        data = await self.bridge.get_analysis(symbol, interval='1D')
        if data and data.get('indicators'):
            active.append({'symbol': symbol, 'data': data})
    
    # If market closed, all stocks with valid data pass Stage 1
    # If market open, filter by volume/movement
    if market_is_open():
        active = [s for s in active if s['data']['indicators'].get('volume', 0) > 0]
    
    return active  # Should be 60-80 stocks with valid data
```

4. Stage 2 (scoring) then picks top 15-20 by brain + golden + technical score.
5. Stage 3 (Gemini) analyzes those 15-20.

### Expected result after fix:
- Universe: 92 stocks
- Stage 1 (prefilter): ~60-80 with valid data
- Stage 2 (scoring): top 15-20 by score
- Stage 3 (Gemini): 15-20 analyzed
- Total scan time: ~15-20 minutes (acceptable for manual/scheduled)

## Testing
1. Trigger manual scan NOW (market closed): POST /api/scanner/scan
2. Verify 92 stocks enter prefilter
3. Verify ~15-20 reach Gemini analysis
4. Verify market column populated for all results
5. Check dashboard shows ~15-20 stocks with market badges

## Files to modify
| File | Change |
|------|--------|
| gemini_scanner.py | Fix market hours check + relax prefilter when closed |
