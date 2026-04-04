# Positions: Partial Sell + Add More — Backend Plan
# Date: 2026-04-04
# Status: READY

## New API Endpoints:

### POST /api/portfolio/partial-sell
```json
Request: { "trade_id": "xxx", "sell_qty": 500, "sell_price": 0.150 }
Response: { "success": true, "remaining_qty": 1500, "realized_pnl": 12.5 }
```
Logic:
1. Find trade by trade_id in journal table
2. Validate sell_qty <= current quantity
3. Calculate realized P&L for sold portion:
   - realized = (sell_price - entry_price) * sell_qty - fees
4. Update quantity: new_qty = old_qty - sell_qty
5. If new_qty == 0 → close the trade entirely
6. If new_qty > 0 → update quantity, keep entry_price same
7. Log the partial sell in journal with notes
8. Return new state

### POST /api/portfolio/add-more
```json
Request: { "trade_id": "xxx", "add_qty": 500, "add_price": 0.140 }
Response: { "success": true, "new_qty": 2500, "new_avg_price": 0.145 }
```
Logic:
1. Find trade by trade_id
2. Calculate new weighted average:
   - new_avg = (old_qty * old_price + add_qty * add_price) / (old_qty + add_qty)
3. Update quantity and entry_price (avg)
4. Log in journal
5. Return new avg price + total qty

### DB Changes:
- journal table may need: partial_sells JSON column (array of {qty, price, date})
- Or: create separate partial_transactions table

## Claude Code Command:
> Read _tools/PARTIAL_SELL_ADD_MORE.md — Add two new endpoints:
> POST /api/portfolio/partial-sell (sell part of position, update qty, calc P&L)
> POST /api/portfolio/add-more (buy more shares, recalc weighted avg price)
> Both need to update the journal table and return the new state.
