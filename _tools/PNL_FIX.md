# Price Freshness Fix — Claude Code Task
# Date: 2026-03-27
# Priority: CRITICAL

## PROBLEM
1. stock_radar_daily has prices from 2026-03-25 (yesterday) — radar didn't run today
2. /dashboard/portfolio shows stale prices (EQUIPMENT=169 but today's close was 180)
3. P&L calculations are wrong because of stale prices
4. pnl_pct and pnl_fils return None even when current_price exists

## TWO SEPARATE ISSUES

### Issue A: Radar not scanning today
Check why radar_enabled is False. The radar scan runs every 30min during market hours 
(Sun-Thu 9:00-12:40 KWT). Today is Wednesday — it should have scanned.

Action: Check radar_enabled status and fix if needed. Check logs for errors.

### Issue B: P&L calculation returning None
Even with stale prices, the P&L SHOULD still be calculated. The current_price IS populated 
(e.g., EQUIPMENT=169) but pnl_pct and pnl_fils are None.

This is a CODE BUG in the portfolio endpoint. Find where open_positions are built in 
dashboard_api.py and ensure P&L is computed:

```python
# For each open position:
entry_price = trade['entry_price']  # e.g., 183 fils
current_price = fresh_price         # e.g., 169 fils (or 180 if fresh)
quantity = trade['quantity']         # e.g., 1000

# P&L calculation (KSE prices in fils, 1 KWD = 1000 fils)
if entry_price and current_price and quantity:
    pnl_pct = round(((current_price - entry_price) / entry_price) * 100, 2)
    pnl_fils = round((current_price - entry_price) * quantity)
    pnl_kwd = round(pnl_fils / 1000, 3)
    
    # Broker fees (0.125% each way)
    buy_fee = entry_price * quantity * 0.00125 / 1000  # in KWD
    sell_fee = current_price * quantity * 0.00125 / 1000  # in KWD
    fees_kwd = round(buy_fee + sell_fee, 3)
    net_pnl_kwd = round(pnl_kwd - fees_kwd, 3)
```

### Issue C: Add price source indicator
Show where the price comes from and how old it is:
- quote_source: "bridge" | "radar_daily" | "unknown"
- quote_age: "2h ago" | "1d ago" etc.
- quote_stale: true/false

## FIX STEPS
1. Find the portfolio endpoint code (dashboard_api.py)
2. Find where open_positions response is built
3. Ensure pnl_pct and pnl_kwd are CALCULATED, not just read from DB
4. Add quote_source and quote_stale to response
5. Fix portfolio_summary to use calculated values
6. Check radar_enabled and fix if needed

## VALIDATION
After fix:
```bash
curl -s http://localhost:9000/dashboard/portfolio | python3 -m json.tool
```
Should show for each position:
- pnl_pct: number (not null)
- pnl_kwd: number (not null)
- fees_kwd: number
- net_pnl_kwd: number
- quote_source: string
- quote_stale: boolean

## FILES
- dashboard_api.py (portfolio endpoint)
- journal_engine.py (get_fresh_price, open_trade enrichment)
- Use apply_text_patch.py for all Python edits
