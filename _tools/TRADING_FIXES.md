# Trading Platform Fixes — Claude Code Task
# Date: 2026-03-26
# Priority: HIGH
# Context: QA audit found these issues in the trading platform HTML pages

## Issues to Fix

### 1. BB Squeeze shows raw "false"/"true" instead of visual badge
**Files:** `www/trading/radar.html` and `www/trading/signals.html`
**Problem:** The BB Squeeze field in hero card and tables shows the literal text "false" or "true" 
instead of a visual indicator (e.g., "—" for false, "⬤ ضغط" for true with amber color).
**Fix:** In the rendering function, replace raw boolean with:
- `false` → `<span style="color:var(--text-3)">—</span>`
- `true` → `<span style="color:var(--amber)">⬤ ضغط</span>`

### 2. Filter chips on radar.html are not clickable
**File:** `www/trading/radar.html`
**Problem:** The 6 filter chips (fc-all, fc-manage, fc-entered, fc-ready, fc-setup, fc-discovery) 
have no onclick handlers registered. They should filter the opportunities table by trade_state.
**Fix:** Add onclick event listeners to each chip that:
- Set active class on clicked chip (remove from others)
- Filter the table rows by trade_state
- "all" shows all rows
**Also:** The "all" chip should be active by default on page load.

### 3. Arabic stock names empty (LOW priority)
**Problem:** `name_ar` field is empty string for all stocks from the API. 
This is a backend issue, not HTML fix. Can be addressed later.
**Action:** Leave as-is for now. The HTML already handles empty name_ar gracefully.

## Validation
After fixing, test:
1. Open radar.html — BB Squeeze should show "—" or "⬤ ضغط" (not "false"/"true")
2. Click each filter chip — table should filter
3. "الكل" chip should be active (highlighted) by default
4. Open signals.html — same BB Squeeze fix should work
5. All 4 nav links still work between pages

## Files to edit
- /home/pi/master_ai/www/trading/radar.html
- /home/pi/master_ai/www/trading/signals.html

## After fix
- quick_check.py (optional, HTML only)
- git commit -m "fix: BB Squeeze display + filter chips onclick in trading platform"
