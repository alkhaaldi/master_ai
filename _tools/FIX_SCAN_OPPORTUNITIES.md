# Fix: scan_opportunities() missing live_data argument
# Date: 2026-04-03
# Priority: HIGH — /فرص command broken

## Problem
server.py line 6303 calls `scan_opportunities()` without the required `live_data` argument.
The function signature is: `def scan_opportunities(live_data: list) -> dict`

## Fix
At server.py line ~6301-6303, change from:
```python
from golden_engine import scan_opportunities
result = scan_opportunities()
```

To:
```python
from golden_engine import scan_opportunities
from bridge_client import get_cached_analysis
# Get live data from Bridge cache (same as /dashboard/decisions endpoint at line 3522)
live_list = []
try:
    cached = get_cached_analysis()
    if cached:
        live_list = [{"symbol": sym, **data} for sym, data in cached.items()]
except Exception:
    pass
result = scan_opportunities(live_list)
```

Or simpler — look at how line 3554 does it (the working endpoint) and copy that pattern.

## Test
After fix: send /فرص to the Telegram bot. Should return opportunities or "لا توجد فرص".
