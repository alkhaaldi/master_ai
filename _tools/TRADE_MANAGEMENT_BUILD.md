# Trade Management System — Claude Code Task
# Date: 2026-03-26
# Priority: HIGH
# Scope: Add/Close/Manage trades from positions.html + fix pricing + sell alerts
# Source: ChatGPT consultation + user requirements

## READ FIRST
1. Read CLAUDE.md
2. Read _tools/OPERATIONAL_ACCESS_MATRIX.md
3. Read this file completely before starting

---

## GOAL
Enable the user to manage trades directly from the positions.html dashboard:
- Add new trades (شريت المعدات، أرجان، الأولى للاستثمار)
- Close trades
- Update stop loss
- Get "SELL" alerts when signals fail

---

## PROBLEM 1: current_price is stale
The /dashboard/portfolio endpoint reads current_price from bridge cache which may be old.

### Fix: 2-layer pricing
In journal_engine.py or wherever open_positions are enriched:
```python
def get_fresh_price(symbol):
    """Try bridge cache first, fallback to stock_radar_daily."""
    # 1. Try bridge cache (if fresh — age < 300s for closed market, < 30s for open)
    # 2. Fallback: last price from stock_radar_daily table
    # 3. Return price + source + stale flag
```

Add to each position in /dashboard/portfolio response:
- `quote_source`: "bridge" | "radar_daily" | "stale"
- `quote_stale`: true/false

---

## PROBLEM 2: Add/Close/Manage trades from HTML

### New API Endpoints (add to dashboard_api.py or new file trade_api.py):

```
POST /api/trade/open      — open new trade
POST /api/trade/close     — close existing trade  
POST /api/trade/update    — update stop loss / take profit
GET  /api/symbols         — list all 128 stock symbols
```

ALL endpoints must be in OPEN_PATHS (no auth — same as other trading endpoints).

### POST /api/trade/open
Request body:
```json
{
  "symbol": "EQUIPMENT",
  "entry_price": 385,
  "quantity": 1000,
  "strategy": "Confluence breakout",
  "direction": "long",
  "stop_loss": 370,
  "take_profit": 420,
  "timeframe": "1D",
  "notes": "شريت المعدات"
}
```

Response:
```json
{
  "success": true,
  "trade_id": 5,
  "message": "Trade opened"
}
```

Implementation: Call existing journal_engine.open_trade() function.

### POST /api/trade/close
Request body:
```json
{
  "trade_id": 5,
  "exit_price": 395,
  "reason": "Hit target"
}
```

### POST /api/trade/update
Request body:
```json
{
  "trade_id": 5,
  "stop_loss": 380,
  "take_profit": 430
}
```

### GET /api/symbols
Returns list of all tracked symbols from stock_radar_daily:
```json
{
  "symbols": [
    {"symbol": "EQUIPMENT", "name_ar": "المعدات القابضة"},
    {"symbol": "ARGAN", "name_ar": "أرجان"},
    ...
  ]
}
```

---

## PROBLEM 3: Update positions.html with trade management

### Add to positions.html:

1. **"إضافة صفقة" button** (gold, prominent) at top of page
2. **Modal form** that opens when clicked:
   - Symbol (searchable input with datalist from /api/symbols)
   - Entry Price (number)
   - Quantity (number)
   - Strategy (text)
   - Stop Loss (number, optional)
   - Take Profit (number, optional)
   - Notes (textarea, optional)
   - "حفظ" button → POST /api/trade/open
   - "إلغاء" button → close modal

3. **For each open position card**, add action buttons:
   - "إغلاق" → modal asking for exit_price + reason → POST /api/trade/close
   - "تعديل وقف" → inline edit stop_loss → POST /api/trade/update

4. **Alert badges** on positions that have sell signals:
   - If confluence < 40 → red badge "⚠️ بيع"
   - If RSI divergence bearish → amber badge "⚠️ مراجعة"
   - These come from signal_engine data for the same symbol

### Modal styling:
- Dark navy background matching the theme
- Gold accent borders
- RTL Arabic
- Responsive

---

## PROBLEM 4: Sell alerts when signal fails

### Enrich /dashboard/portfolio with signal health
For each open position, also return signal data from /dashboard/signals:
```json
{
  "symbol": "CLEANING",
  "entry_price": 132,
  "current_price": 135,
  "pnl_pct": 2.27,
  "signal_health": {
    "confluence_score": 100,
    "verdict": "مراجعة",
    "rsi_14": 68,
    "macd_momentum": "decelerating_bullish",
    "rsi_divergence": "bearish",
    "adx": 35
  },
  "alerts": [
    {"level": "warning", "message": "RSI divergence bearish"}
  ]
}
```

### Alert rules:
- confluence < 40 → alert "بيع — confluence ضعيف"
- rsi_divergence == "bearish" → alert "مراجعة — divergence سلبي"
- price < stop_loss → alert "بيع فوراً — وقف الخسارة"
- macd_momentum contains "bearish" AND confluence < 50 → alert "مراجعة"

### Display in positions.html:
- Alert badge on position card (red/amber)
- Alert message text
- "إغلاق" button becomes more prominent when alert is active

---

## EXECUTION STEPS

1. Fix pricing in journal_engine.py — get_fresh_price fallback
2. Create trade API endpoints in dashboard_api.py (or trade_api.py)
3. Add /api/trade/open, /api/trade/close, /api/trade/update, /api/symbols to OPEN_PATHS
4. Update /dashboard/portfolio to include signal_health + alerts
5. Update positions.html:
   - Add trade form modal
   - Add close/edit-stop buttons per position
   - Add alert badges
   - Load symbols for datalist
6. quick_check + smoke_test
7. Git commit + restart
8. Test: open positions.html, add a trade, verify it appears

## IMPORTANT RULES
- Python edits via apply_text_patch.py
- HTML files can be edited directly (they're in www/trading/)
- Backward compatible — existing endpoints must still work
- Use existing journal_engine functions (open_trade, close_trade)
- No external dependencies — pure Python + existing DB
