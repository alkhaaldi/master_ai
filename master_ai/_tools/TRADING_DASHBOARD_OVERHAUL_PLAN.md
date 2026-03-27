# Trading Dashboard Overhaul — Complete Execution Plan
# Date: 2026-03-26
# Scope: Signal Engine + 3-page dashboard + pro visual design

## READ THIS FIRST
This plan has 3 phases. Execute in order. Each phase is independently testable.

## ARCHITECTURE OVERVIEW

### Current state (6 trading pages):
- sub-radar (11 sections, main trading page)
- sub-portfolio (duplicate open positions)
- sub-analysis (nearly empty)
- sub-journal (duplicate open positions again)
- sub-alerts (nearly empty)
- sub-confluence (separate scoring system)

### Target state (3 trading pages):
- **Trading** — live decisions (replaces sub-radar)
- **Signals** — investigate + validate (absorbs analysis + alerts + confluence)
- **Journal** — performance review (absorbs portfolio stats)

### Delete after migration:
- sub-portfolio
- sub-analysis
- sub-alerts
- sub-confluence

---

## PHASE A: Signal Engine (Backend)

### New file: signal_engine.py

Purpose: Merge radar + bridge + journal into composite signals with trade state model.

```
Trade State Model:
  discovery  — radar detected EMA cross, no bridge confirmation yet
  setup      — bridge confirms improving indicators (confluence >40)
  ready      — confluence >60, volume confirms, entry conditions met
  entered    — open position exists in journal
  manage     — tracking stop/target (entered + bridge monitoring)
  closed     — archived in journal
```

#### signal_engine.py responsibilities:
1. `build_signals()` — main function called by dashboard endpoint
   - Reads radar daily context (128 stocks from stock_radar.py)
   - Reads bridge analysis (top 15 from bridge_client.py)
   - Reads open trades (from journal_engine.py)
   - For each bridge-enriched stock:
     - Assigns trade_state based on rules
     - Computes composite_score from bridge confluence
     - Generates verdict (buy_setup / watch / hold / avoid)
     - Formats decision card data
   - Returns sorted list by composite_score descending

2. `_assign_trade_state(symbol, bridge_data, radar_data, open_trades)`:
   - If symbol in open_trades → "entered" or "manage"
   - If bridge confluence >= 60 and vol_ratio > 1.2 → "ready"
   - If bridge confluence >= 40 → "setup"
   - If radar has recent cross → "discovery"
   - Else → None (not tracked)

3. `_compute_verdict(bridge_data, trade_state)`:
   - ready + strong_bullish → "شراء"
   - setup + bullish → "مراقبة"
   - entered + decelerating → "مراجعة"
   - bearish or confluence < 30 → "تجنب"
   - Else → "حياد"

#### Context injection pattern (same as other modules):
```python
_ctx = {}
def init_signal_context(**kwargs):
    _ctx.update(kwargs)
```

Wire in server.py lifespan alongside other init_*_context calls.

### New endpoint: /dashboard/signals

Add to dashboard_api.py:

```python
@router.get("/dashboard/signals")
async def dashboard_signals():
    from signal_engine import build_signals
    result = build_signals()
    return result
```

Response shape:
```json
{
  "market_open": true,
  "bridge_online": true,
  "bridge_cached_count": 12,
  "timestamp": "2026-03-26T10:30:00",
  "decision_card": {
    "symbol": "CLEANING",
    "name_ar": "التنظيف",
    "price": 140,
    "change_pct": 6.87,
    "verdict": "مراقبة",
    "trade_state": "ready",
    "confluence_score": 100,
    "ema_state": "bullish",
    "rsi_14": 74.6,
    "macd_state": "bullish",
    "macd_momentum": "accelerating_bullish",
    "adx": 34.7,
    "vol_ratio": 4.08,
    "support": 126,
    "resistance": 153,
    "atr_14": 6.53
  },
  "opportunities": [
    {"symbol": "...", "confluence_score": 85, "verdict": "...", ...}
  ],
  "open_positions": [
    {"symbol": "CLEANING", "entry": 131, "current": 140, "pnl_pct": 6.87, "pnl_kwd": 9.0, "state": "manage"}
  ],
  "signal_counts": {
    "discovery": 3,
    "setup": 5,
    "ready": 2,
    "entered": 1
  }
}
```

### New HA sensor: sensor.master_ai_signals

Add to configuration.yaml:
```yaml
  - platform: rest
    name: Master AI Signals
    resource: http://192.168.109.123:9000/dashboard/signals
    headers:
      X-API-Key: !secret master_ai_key
    scan_interval: 120
    value_template: "{{ value_json.decision_card.verdict | default('—') }}"
    json_attributes:
      - market_open
      - bridge_online
      - bridge_cached_count
      - decision_card
      - opportunities
      - open_positions
      - signal_counts
      - timestamp
```

### PHASE A Validation:
1. quick_check.py passes
2. smoke_test.py passes
3. curl /dashboard/signals returns valid JSON
4. Git commit: "feat: signal_engine + /dashboard/signals endpoint"

---

## PHASE B: Dashboard Visual Rebuild (3 pages)

### Design System (from ChatGPT consultation)

#### Color palette (confluence-based, works light+dark):
```
Strong Bullish (>70):  border=#16A34A  bg=rgba(22,163,74,0.12)
Moderate Bullish (50-70):  border=#22C55E  bg=rgba(34,197,94,0.10)
Neutral (40-60):  border=#F59E0B  bg=rgba(245,158,11,0.10)
Moderate Bearish (30-50):  border=#F97316  bg=rgba(249,115,22,0.10)
Strong Bearish (<30):  border=#DC2626  bg=rgba(220,38,38,0.12)
```

#### Typography:
```
Page title: 28px weight 800
Section header: 20px weight 700
Card title: 16px weight 700
Primary number (price, score): 30px weight 800
Secondary big (change%): 22px weight 700
Table text: 13px weight 500
Table header: 12px weight 700 opacity 0.8
Label: 12px weight 600 opacity 0.72
Footnote: 11px weight 500 opacity 0.60
```

#### RTL rules:
- All cards: direction: rtl; text-align: right;
- Numbers/tickers: wrapped in span with direction: ltr; unicode-bidi: isolate;
- Colored borders: border-right (not left) for RTL
- font-variant-numeric: tabular-nums for all numbers

#### Card styling:
```
Base card: border-radius 16px, padding 16px 18px, border 1px solid rgba(128,128,128,0.16), box-shadow 0 2px 10px rgba(0,0,0,0.06)
Decision Card (action zone): border-radius 18px, border-right 8px solid [score color], box-shadow 0 8px 24px rgba(0,0,0,0.12), padding 18px
Info zone: border-radius 14px, lighter shadow, no strong tint
```

#### Spacing rhythm: 16 / 14 / 12 / 8 px between sections

### Page 1: Trading (path: sub-radar, rebuild in place)

Sections in order:
1. **Pulse bar** — market status + bridge online + best signal score + active signal count
2. **Quick Actions** — 4 buttons (same as current but restyled)
3. **Decision Card** — THE main card. Reads from sensor.master_ai_signals.decision_card
   - Row 1: Symbol + Price + Change% + Verdict badge
   - Row 2: Confluence score (large) + trade state badge
   - Row 3: EMA state | RSI | MACD state | ADX | Vol ratio (2-column compact)
   - Row 4: Support | Resistance | ATR
   - Colored border-right by confluence score
   - Tinted background by confluence
4. **Top 5 Opportunities** — table from sensor.master_ai_signals.opportunities
   - Columns: Symbol | Price | Change% | Confluence | Verdict | EMA | RSI | Vol
   - Rows tinted by confluence score
   - Arabic headers, LTR numbers
5. **Open Positions** — compact P&L from sensor.master_ai_signals.open_positions
   - Only shows if positions exist (auto-hide when empty)
   - Columns: Symbol | Entry | Current | P&L% | P&L KWD | State
6. **Nav** — 3 buttons: Signals | Journal | Home

### Page 2: Signals (path: sub-signals, NEW page replacing sub-confluence)

Sections:
1. **Signal Pulse** — discovery/setup/ready counts + avg confluence
2. **Signal State Table** — all tracked stocks with full indicator matrix
   - Columns: Symbol | State | Confluence | EMA | RSI | MACD | StochRSI | ADX | Vol | BB squeeze | RSI div
   - This is where all 19 indicators are visible
3. **30m Signal Flash** — recent radar events with status (from radar sensor)
4. **Bridge Diagnostics** — online/offline, last success, cached count, circuit breaker
5. **Nav** — Trading | Journal | Home

### Page 3: Journal (path: sub-journal, rebuild in place)

Sections:
1. **Journal Pulse** — win rate | total P&L | trades this month | avg hold
2. **Closed Trades** — table with exit reason
3. **Monthly Stats** — 4 metric cards
4. **Best/Worst** — top winning and losing trades
5. **Signal Accuracy** — signals generated vs confirmed vs skipped vs hit rate
6. **Nav** — Trading | Signals | Home

### Pages to DELETE after rebuild:
- sub-portfolio (absorbed into Trading open positions + Journal stats)
- sub-analysis (absorbed into Signals)
- sub-alerts (absorbed into Signals)
- sub-confluence (replaced by Signals)

### PHASE B Validation:
1. Dashboard YAML validates (yamllint)
2. All sensors load in HA
3. All 3 pages render correctly
4. Git commit: "feat: trading dashboard v14 — 3-page signal-driven layout"

---

## PHASE C: Polish + TG integration (optional, later)

1. TG notifications for new "ready" signals
2. Signal history tracking in DB
3. Hit rate computation
4. Weekly signal accuracy report

---

## EXECUTION ORDER FOR CLAUDE CODE

### Phase A (backend):
1. Create signal_engine.py (new file, ~200 lines)
2. Add /dashboard/signals to dashboard_api.py (patch)
3. Wire init_signal_context in server.py lifespan (patch)
4. Add sensor.master_ai_signals to configuration.yaml
5. quick_check + smoke_test
6. Test: curl /dashboard/signals
7. Git commit + restart

### Phase B (dashboard):
8. Write new Trading page YAML (sub-radar rebuild)
9. Write new Signals page YAML (sub-signals, new path)
10. Write new Journal page YAML (sub-journal rebuild)
11. Remove old pages from dashboard YAML (portfolio, analysis, alerts, confluence)
12. Update Home page nav buttons
13. Apply via rebuild_dashboard.py
14. HA YAML reload
15. Visual verification
16. Git commit

## IMPORTANT RULES
- All Python edits on RPi via apply_text_patch.py
- Arabic text: write via Filesystem:write_file → Samba copy → never Python \uXXXX
- Dashboard YAML encoding: UTF-8 Arabic via Filesystem:write_file
- Follow _tools/ADDING_NEW_DASHBOARD_FIELDS.md for new sensor
- Follow _tools/OPERATIONAL_ACCESS_MATRIX.md for edit strategy
- Backward compatible: existing sensors stay, new sensor added alongside

## DESIGN SPEC FILES
- C:\Users\MS1\Temp\chatgpt_design_answer.txt — full CSS/color/typography spec
- C:\Users\MS1\Temp\chatgpt_dashboard_answer.txt — architecture spec
