# CRITICAL FIX — Dashboard Not Showing What We Agreed On
# Date: 2026-03-26
# Priority: URGENT — The dashboard is broken relative to the plan

## THE PROBLEM
The backend (/dashboard/signals) returns ALL the data correctly:
- 11 tracked stocks with full pro indicators (24 fields each)
- Trade states: 6 discovery + 3 setup + 1 ready + 1 manage
- All pro indicators: ADX, vol_ratio, stoch_k, bb_squeeze, rsi_divergence, ema_cross, confluence

But the dashboard shows almost NONE of it:
1. opportunities capped at 5 — should be ALL non-entered signals (up to 10-15)
2. Trading page Decision Card — OK but ONLY 1 stock, need to see more
3. Signals page "Signal State Table" — supposed to show FULL indicator matrix for ALL tracked stocks but currently shows almost nothing useful
4. Top 5 table on Trading page — shows 5 rows but doesn't show all the pro indicators we built today

## FIX 1: signal_engine.py — Remove arbitrary caps

### Current (broken):
```python
result["opportunities"] = [
    s for s in signals if s["trade_state"] not in ("entered", "manage")
][:5]
```

### Fix:
```python
# ALL non-entered signals, sorted by confluence — no cap
result["opportunities"] = [
    s for s in signals if s["trade_state"] not in ("entered", "manage")
]

# Also add ALL signals (including entered/manage) for Signals page matrix
result["all_signals"] = signals
```

The `all_signals` field gives the Signals page the full matrix it needs.

## FIX 2: Trading page (sub-radar) — Top Opportunities table

### Current: Shows 5 stocks with basic columns
### Required: Show ALL opportunities (up to 10) with these columns:
- Symbol (Arabic name if available)
- Price + Change%
- Confluence score (colored badge)
- Verdict (Arabic)
- Trade state badge
- EMA state (↑/→/↓)
- RSI (colored: green <30, red >70)
- MACD momentum (arrow indicator)
- ADX (bold if >25)
- Vol ratio (bold if >1.5)

### Styling per row:
- Row tinted by confluence score (the 5-tier color system)
- border-right colored by confluence
- Compact but readable

## FIX 3: Signals page (sub-signals) — FULL Indicator Matrix

This is the BIG fix. The Signal State Table must show ALL tracked stocks with ALL pro indicators.

### Required columns (the full 19 we built):
| Column | Source | Display |
|--------|--------|---------|
| Symbol | symbol | Arabic name |
| State | trade_state | badge: discovery/setup/ready/entered/manage |
| Confluence | confluence_score | 0-100 colored |
| Verdict | verdict | Arabic |
| EMA | ema_state | ↑ bullish / → mixed / ↓ bearish |
| RSI | rsi_14 | number, colored by zone |
| MACD | macd_state | bullish/bearish + momentum |
| Stoch RSI | stoch_k | number, OB/OS indicator |
| ADX | adx | number, bold >25 |
| Vol Ratio | vol_ratio | number×, bold >1.5 |
| BB Squeeze | bb_squeeze | Yes/No |
| RSI Div | rsi_divergence | bullish/bearish/none |
| EMA Cross | ema_cross.type | golden/death + bars ago |
| Support | support | price level |
| Resistance | resistance | price level |
| ATR | atr_14 | volatility number |

### Data source: sensor.master_ai_signals attribute "all_signals"

### Table styling:
- direction: rtl
- Rows colored by confluence tier
- border-right per row by confluence
- Numbers in .ltr spans
- font-variant-numeric: tabular-nums
- Scrollable if needed (max-height with overflow)
- Arabic headers: الرمز | الحالة | التوافق | القرار | EMA | RSI | MACD | StochRSI | ADX | الحجم | BB | تباين | تقاطع | دعم | مقاومة | ATR

## FIX 4: Decision Card — add MACD momentum + Stoch RSI + BB squeeze

Currently the Decision Card shows 10 fields. Add 3 more that are critical:
- MACD momentum (accelerating/decelerating) — this tells you if momentum is GROWING
- Stoch RSI K value — refined overbought/oversold
- BB squeeze (Yes/No) — breakout alert

These 3 should appear as a small row between the indicator group and the S/R row.

## FIX 5: Pulse bar — show more useful info

Current pulse shows: market status + bridge status + signal count
Add: Best confluence score + best symbol name + bridge cached count

## EXECUTION ORDER FOR CLAUDE CODE

1. Patch signal_engine.py:
   - Remove [:5] cap on opportunities
   - Add "all_signals" field to response
   - Update HA sensor json_attributes to include all_signals

2. Patch configuration.yaml:
   - Add all_signals to sensor.master_ai_signals json_attributes

3. Rebuild sub-radar (Trading) page YAML:
   - Top opportunities: show ALL (for s in opps[:10]) with full columns
   - Decision Card: add macd_momentum + stoch_k + bb_squeeze row
   - Pulse: add best confluence + symbol

4. Rebuild sub-signals (Signals) page YAML:
   - Signal State Table reads from sensor.master_ai_signals.all_signals
   - Shows ALL stocks with ALL 16 indicator columns
   - Full 5-tier row coloring
   - Professional table design per DESIGN_SPEC.txt

5. Test:
   - quick_check + smoke_test
   - curl /dashboard/signals | check all_signals count
   - HA restart to load new sensor attributes
   - Visual verification of both pages

6. Git commit

## DESIGN RULES (from DESIGN_SPEC.txt — MUST follow)
- 5-tier color: #16A34A / #22C55E / #F59E0B / #F97316 / #DC2626
- border-right (RTL) colored by confluence
- Row background: rgba with 0.06-0.12 opacity
- Typography: 13px/500 for tables, 12px/700 for headers
- RTL: .ltr spans for ALL numbers/tickers
- tabular-nums for ALL numeric elements
- Auto-hide empty sections

## CRITICAL: DO NOT
- Do not reduce columns to "fit" — the Signal State Table MUST show all indicators
- Do not cap opportunities at 5 — show all
- Do not use old radar sensor for Signals page — use master_ai_signals.all_signals
- Do not lose the existing design system (colors, typography, RTL rules)
