# Fix: /api/trade/update — Accept entry_price and quantity
# Date: 2026-04-04
# Status: READY

## Problem:
POST /api/trade/update currently only accepts stop_loss and take_profit.
Frontend now sends entry_price and quantity too but backend ignores them.

## Fix:
In the handler for POST /api/trade/update, add support for:
- entry_price: update the entry price (float)
- quantity: update the share count (int)

Example request:
```json
{
  "trade_id": 6,
  "entry_price": 180.0,
  "quantity": 250000,
  "stop_loss": 170.0,
  "take_profit": 200.0
}
```

The handler should:
1. Check if entry_price is provided → UPDATE journal SET entry_price = ? WHERE id = ?
2. Check if quantity is provided → UPDATE journal SET quantity = ? WHERE id = ?
3. Continue handling stop_loss and take_profit as before
4. Recalculate PnL after update

## Claude Code Command:
> POST /api/trade/update needs to accept entry_price and quantity in addition to stop_loss and take_profit. Update the handler to SET these fields in the journal table when provided.
