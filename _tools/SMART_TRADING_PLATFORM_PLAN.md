# Smart Trading Platform — Build Plan for Claude Code
# Master AI v9.x — Confluence Decision Engine
# Date: 2026-03-22
# Status: APPROVED BY USER — Ready for execution

---

## GOAL
Build a Smart Trading Platform inside Master AI that tells the user **what to buy** —
not a screener that shows data. The system scans 128 KSE stocks, runs confluence analysis,
and sends a clear BUY/SKIP decision via Telegram + Dashboard.

**User's exact words:** "ابي الماستر ايه اي يكون هو اللي يقولي فرصة اشتر بدون ما ابحث انا و احلل"

---

## EXISTING SYSTEM (DO NOT BREAK)

### Current Trading Stack
- `stock_radar.py` (~1060 lines): EMA radar + MACD + confluence + daily snapshots
- `journal_engine.py` (~370 lines): Trading journal + P&L calculator + weekly report
- `dashboard_api.py` (~1280 lines): 8 endpoints including /dashboard/radar, /dashboard/portfolio, /dashboard/analysis
- `tradingview_bridge.py`: TV webhook handler + watchlist sync
- DB tables: `stock_radar_daily`, `trades`, `tv_alert_events`, `trade_journal`, `tv_watchlists`

### Current Dashboard Pages (10 pages)
- Trading (sub-radar): Market Pulse + Decision Card + Top Opportunities + 30m Signals + Watchlist + Journal
- Portfolio (sub-portfolio): Open positions + P&L + Signal vs Trade
- Analysis (sub-analysis): Signal history + TV alerts + Stats

### Current Sensors
- `sensor.master_ai_radar` — /dashboard/radar every 120s
- `sensor.master_ai_portfolio` — /dashboard/portfolio every 120s
- `sensor.master_ai_analysis` — /dashboard/analysis every 300s

### Current Webhook Flow
TradingView → POST /tv/webhook → tradingview_bridge.py save_tv_alert() →
TG message with شريت/تجاهلت buttons → journal_engine

### DO NOT MODIFY
- server.py routing (only add new routes via dashboard_api router)
- journal_engine.py (only call its existing functions)
- priority_engine.py (only add new trading domain types)
- Any existing /dashboard/* endpoints (backward compatible)
- Any existing sensor configurations

---

## WHAT TO BUILD — 3 Components

### Component 1: `confluence_engine.py` (NEW FILE)
Location: `/var/lib/homeassistant/share/master_ai/confluence_engine.py`

**Purpose:** The brain. Takes raw indicator data → outputs BUY/SKIP decisions with confidence.

```python
# Functions to implement:

def init_confluence_context(server_globals):
    """Called from server.py lifespan startup, same pattern as other modules"""
    pass

def run_confluence_scan():
    """
    Called every 30 min during market hours (9:00-12:40 KWT, Sun-Thu)
    OR on-demand via /tv/webhook when screener data arrives

    Steps:
    1. Read latest data from stock_radar_daily table (128 stocks)
    2. For each stock, compute confluence_checks:
       - check_rvol: volume / avg_volume >= 1.5 (from vol_ratio column)
       - check_macd: macd_cross == 'bullish' OR (macd > macd_signal AND macd_above_zero)
       - check_rsi: 40 <= rsi <= 65
       - check_trend: ema_fast > ema_slow (uptrend) or change_pct > -2 (not falling)
       - check_ema_position: price > daily_ema21
       - check_not_overbought: rsi < 70 AND change_pct < 25
    3. confluence_score = passed_checks / total_checks * 100
    4. conviction: HIGH if >= 83 (5/6), MEDIUM if >= 67 (4/6), LOW otherwise
    5. Only HIGH conviction + R:R >= 2.0 = actionable BUY signal
    6. Calculate: entry=price, stop=support, target=resistance, R:R, sl_pct
    7. Store results in DB table: confluence_signals
    8. Return list of actionable signals
    """
    pass

def get_actionable_signals(limit=5):
    """Read from confluence_signals table, return top HIGH conviction signals"""
    pass

def get_watchlist_signals(limit=10):
    """Return MEDIUM conviction signals for monitoring"""
    pass

def record_decision(symbol, decision, price):
    """
    Called when user clicks Buy or Skip on TG
    Stores in confluence_decisions table for learning loop
    """
    pass

def get_confluence_stats():
    """Stats for dashboard: total scanned, high/med/low counts, last scan time"""
    pass
```

**DB Tables (in life.db):**

```sql
CREATE TABLE IF NOT EXISTS confluence_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    price REAL,
    confluence_score INTEGER,
    conviction TEXT,
    checks_passed TEXT,
    rvol REAL,
    rsi REAL,
    macd_conf INTEGER,
    trend INTEGER,
    support REAL,
    resistance REAL,
    entry_price REAL,
    stop_loss REAL,
    target_price REAL,
    risk_reward REAL,
    sl_pct REAL,
    signal_type TEXT,
    timeframe TEXT DEFAULT '30',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);

CREATE TABLE IF NOT EXISTS confluence_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    symbol TEXT NOT NULL,
    decision TEXT,
    entry_price REAL,
    decided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (signal_id) REFERENCES confluence_signals(id)
);
```

### Component 2: Dashboard Endpoint + Sensor
Add to `dashboard_api.py` (PATCH, not rewrite):

```python
@router.get("/dashboard/confluence")
async def dashboard_confluence():
    """
    Returns:
    {
        "scan_active": true,
        "last_scan": "2026-03-22T10:30:00",
        "scan_stale": false,
        "stocks_scanned": 128,
        "actionable_count": 3,
        "watch_count": 12,
        "actionable": [
            {
                "symbol": "ZAIN",
                "name": "زين",
                "price": 566,
                "confluence_score": 100,
                "conviction": "HIGH",
                "checks": {"rvol":true,"macd":true,"rsi":true,"trend":true,"ema":true,"not_ob":true},
                "rvol": 1.49,
                "rsi": 56.4,
                "entry": 566,
                "stop": 547,
                "target": 610,
                "risk_reward": 2.3,
                "sl_pct": 3.4,
                "div_yield": 10.6,
                "analyst": "شراء",
                "sector": "الاتصالات"
            }
        ],
        "watchlist": [...],
        "market_summary": {
            "high_count": 15,
            "medium_count": 35,
            "low_count": 81,
            "avg_confluence": 54
        }
    }
    """
```

**HA Sensor** (add to configuration.yaml):
```yaml
- platform: rest
  name: master_ai_confluence
  resource: https://ai.salem-home.com/dashboard/confluence
  headers:
    X-API-Key: !secret master_ai_key
  scan_interval: 120
  json_attributes:
    - scan_active
    - last_scan
    - scan_stale
    - stocks_scanned
    - actionable_count
    - watch_count
    - actionable
    - watchlist
    - market_summary
  value_template: "{{ value_json.actionable_count }}"
```

### Component 3: Dashboard Page (NEW page: sub-confluence)
Add as new subview page in master_ai_dashboard.yaml

**Page Structure (follows APPROVED prototype exactly):**

```
LAYER 1 — Pulse Hero
├── Green dot + "Confluence engine active — 128 stocks scanned"
├── Actionable count (big number)
└── "buy signals now"

LAYER 2 — Actionable Cards (HIGH conviction, R:R >= 2.0)
├── For each signal:
│   ├── Symbol + Name + Sector
│   ├── Confluence score badge (e.g. "100% confluence")
│   ├── Grid 4: Price | RVOL | RSI | Div yield
│   ├── Check marks: ✓ RVOL | ✓ MACD | ✓ RSI zone | ✓ Trend | ✓ Not overbought
│   ├── Decision line: Entry: X | SL: Y (-Z%) | TP: W | R:R = N
│   └── Buttons: [شريت] [حلل] [تجاهلت]
├── If no signals: "No high-conviction signals — engine scanning every 30 min"

LAYER 3 — Watchlist (MEDIUM conviction)
├── Table: Symbol | Price | 1M% | RVOL | Confluence | R:R | Why watching

LAYER 4 — Market Pulse
├── Grid 4: High conviction | Medium watch | No signal | Avg confluence
└── Full table: Stock | Price | 1M% | RVOL | Confluence bar | Signal
```

**Navigation:** Add "Confluence" button to Trading page nav + Home page nav

---

## TG Alert Format (Arabic)

When confluence scan finds HIGH conviction signal:

```
🎯 فرصة شراء — ZAIN (زين)
━━━━━━━━━━━━━━━━━━━━
📊 Confluence: 100% (6/6)
💰 السعر: 566 فلس
📈 RVOL: 1.49x | RSI: 56
━━━━━━━━━━━━━━━━━━━━
✅ الفوليوم يدعم
✅ MACD صاعد
✅ RSI منطقة مثالية
✅ الترند صاعد
✅ فوق EMA21
✅ مو overbought
━━━━━━━━━━━━━━━━━━━━
🎯 الدخول: 566 | الوقف: 547 (-3.4%)
🏁 الهدف: 610 | R:R = 2.3
━━━━━━━━━━━━━━━━━━━━

[شريت ✅]  [تجاهلت ❌]
```

Use EXISTING inline keyboard pattern from v8.4.0 Trade Confirmation.
Callback: `confluence_buy:{signal_id}` → calls journal_engine.open_trade()
Callback: `confluence_skip:{signal_id}` → calls confluence_engine.record_decision()

---

## EXECUTION STEPS (for Claude Code)

### Step 1: Read context
```bash
cat /var/lib/homeassistant/share/master_ai/_tools/OPERATIONAL_ACCESS_MATRIX.md
cat /var/lib/homeassistant/share/master_ai/_tools/ADDING_NEW_DASHBOARD_FIELDS.md
```

### Step 2: Create confluence_engine.py
- New file at /var/lib/homeassistant/share/master_ai/confluence_engine.py
- Pattern: same as journal_engine.py (init_*_context, DB access via life.db)
- Read from stock_radar_daily table (already has all indicator data)
- Write to new confluence_signals + confluence_decisions tables

### Step 3: Wire into server.py (PATCH)
- Import confluence_engine in server.py
- Call init_confluence_context() in lifespan startup
- Add confluence scan to market-hours scheduler (exists already for daily summary at 13:00)
- Add TG callback handlers for confluence_buy/confluence_skip

### Step 4: Add /dashboard/confluence endpoint
- PATCH dashboard_api.py (add one new endpoint via existing router)
- Call confluence_engine.get_actionable_signals() and get_watchlist_signals()

### Step 5: Add HA sensor
- PATCH configuration.yaml — add sensor.master_ai_confluence

### Step 6: Build dashboard page
- New subview: sub-confluence
- Follow encoding workflow: write YAML on Windows → Samba → rebuild_dashboard.py
- Add nav button to existing trading page + home page

### Step 7: Validate
```bash
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
python3 _tools/db_sanity.py
bash _tools/restart_master_ai.sh
```

### Step 8: Git commit
```bash
cd /var/lib/homeassistant/share/master_ai
git add -A
git commit -m "feat: Smart Trading Platform v1 — Confluence Decision Engine"
```

---

## DATA FLOW (complete)

```
stock_radar.py (existing, runs every 30m)
    ↓ writes to stock_radar_daily (128 stocks)

confluence_engine.py (NEW, reads after radar scan)
    ↓ reads stock_radar_daily
    ↓ computes 6 confluence checks per stock
    ↓ writes confluence_signals table
    ↓ if HIGH conviction found:
        ↓ sends TG alert with [شريت][تجاهلت]

/dashboard/confluence (NEW endpoint)
    ↓ reads confluence_signals table
    ↓ returns JSON for HA sensor

sensor.master_ai_confluence (NEW, every 120s)
    ↓ feeds dashboard page

sub-confluence (NEW dashboard page)
    ↓ displays Pulse + Actionable Cards + Watchlist + Market Pulse
```

---

## WHAT'S NOT IN SCOPE (Phase 2, later)

- TradingView Pine Screener integration (CSV/webhook for fundamental data)
- Value score (PE, dividends, EPS growth) — needs external data source
- Learning loop (which signals actually profited) — needs trade closure tracking
- Screener CSV auto-import
- Strategy-specific signals (CLEANING V3, SENERGY V5)

Phase 1 uses ONLY data already in stock_radar_daily (price, RSI, MACD, EMA, volume, S/R).
This is enough for a working confluence engine. Fundamentals come in Phase 2.

---

## RISK DISCLAIMER (show on dashboard)

Bottom of confluence page:
"⚠️ هذا النظام يعطي إشارات بناءً على تحليل فني — مو توصية مالية.
كل قرار تداول مسؤوليتك. استخدم وقف خسارة دائمًا."
