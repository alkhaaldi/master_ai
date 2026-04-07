# TRADING V2 PHASE 2 — Complete Enhancement Plan
# Date: 2026-04-04
# Status: READY FOR EXECUTION
# Source: Consensus of Claude + Gemini Pro + ChatGPT (GPT-5.4)
# Predecessor: TRADING_V2_PLAN.md (8 phases complete)

# ═══════════════════════════════════════════════════════
# IMPORTANT — INTEGRATION RULES (apply to ALL items)
# ═══════════════════════════════════════════════════════
#
# Every feature MUST include ALL of the following:
#
# 1. BACKEND: Python logic in appropriate file
# 2. ENDPOINT: FastAPI endpoint returning JSON (in dashboard_api.py or server.py)
# 3. DASHBOARD: Update relevant HTML page(s) to display the data
# 4. TELEGRAM: Alert via telegram_queue when relevant thresholds are hit
# 5. DB: New tables/columns if needed (migration in server.py startup)
# 6. FLAGS: Feature flag in feature_flags table (toggleable via API)
# 7. SWING.HTML: Update Trading Hub if the feature affects trading decisions
# 8. HOME.HTML: Update teaser if it changes the top-level signal
# 9. GIT: Commit after each item with descriptive message
# 10. TESTS: quick_check.py + smoke_test.py after each change
#
# Files reference:
# - Trading logic: signal_engine.py, stock_radar.py
# - Dashboard API: dashboard_api.py
# - Server: server.py
# - Bridge: bridge_client.py (on RPi), TradingView Bridge (on PC)
# - HTML pages: www/trading/*.html (claude.ai builds these)
# - Telegram: telegram_queue table + send functions in server.py
# - Feature flags: feature_flags table + get_trading_flags()
# - DB: data/life.db (SQLite)
# ═══════════════════════════════════════════════════════

---


## ITEM 1: Portfolio Risk Engine
### Priority: #1 (CRITICAL — must exist before paper trading)
### Effort: Medium
### Source: All 3 AIs agree

### What it does:
Calculates position size for every signal based on account risk.
Enforces maximum portfolio exposure. Prevents over-concentration.

### Logic:
```python
# Constants (configurable via feature_flags or DB config)
ACCOUNT_CAPITAL = 10000  # KWD — user sets this
RISK_PER_TRADE_PCT = 2.0  # max 2% of capital risked per trade
MAX_OPEN_POSITIONS = 3
MAX_PORTFOLIO_HEAT_PCT = 6.0  # total open risk cannot exceed 6%
MAX_SECTOR_POSITIONS = 2  # max 2 stocks from same sector

# Position sizing formula
def calculate_position_size(entry_price, stop_price, capital, risk_pct):
    risk_kwd = capital * (risk_pct / 100)
    risk_per_share = entry_price - stop_price
    if risk_per_share <= 0:
        return 0
    shares = int(risk_kwd / risk_per_share)
    position_value = shares * entry_price
    return {
        "shares": shares,
        "position_value_kwd": round(position_value, 3),
        "risk_kwd": round(risk_kwd, 3),
        "risk_per_share": round(risk_per_share, 3),
        "pct_of_capital": round((position_value / capital) * 100, 1)
    }

# Portfolio heat check
def check_portfolio_heat(open_positions, new_risk_kwd, capital):
    current_heat = sum(p['risk_kwd'] for p in open_positions)
    new_heat = current_heat + new_risk_kwd
    heat_pct = (new_heat / capital) * 100
    return {
        "allowed": heat_pct <= MAX_PORTFOLIO_HEAT_PCT,
        "current_heat_pct": round((current_heat/capital)*100, 1),
        "new_heat_pct": round(heat_pct, 1),
        "max_heat_pct": MAX_PORTFOLIO_HEAT_PCT
    }
```

### DB Changes:
```sql
-- New table for risk config
CREATE TABLE IF NOT EXISTS risk_config (
    key TEXT PRIMARY KEY,
    value REAL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
-- Seed defaults
INSERT OR IGNORE INTO risk_config VALUES ('account_capital', 10000, CURRENT_TIMESTAMP);
INSERT OR IGNORE INTO risk_config VALUES ('risk_per_trade_pct', 2.0, CURRENT_TIMESTAMP);
INSERT OR IGNORE INTO risk_config VALUES ('max_open_positions', 3, CURRENT_TIMESTAMP);
INSERT OR IGNORE INTO risk_config VALUES ('max_portfolio_heat_pct', 6.0, CURRENT_TIMESTAMP);
INSERT OR IGNORE INTO risk_config VALUES ('max_sector_positions', 2, CURRENT_TIMESTAMP);

-- Add sector to stock_profiles if not exists
ALTER TABLE stock_profiles ADD COLUMN sector TEXT DEFAULT 'unknown';
```

### Endpoint:
```
GET /dashboard/risk-status
Returns:
{
  "capital": 10000,
  "open_positions": 2,
  "max_positions": 3,
  "portfolio_heat_pct": 3.2,
  "max_heat_pct": 6.0,
  "can_open_new": true,
  "sector_exposure": {"banking": 1, "industrial": 1},
  "position_sizing": {
    "next_signal": {
      "symbol": "ACICO",
      "entry": 0.150,
      "stop": 0.142,
      "shares": 2500,
      "risk_kwd": 200,
      "position_value": 375
    }
  }
}
```

### Feature Flag:
```
RISK_ENGINE = True  (in feature_flags table)
```

### Dashboard Integration:
- **swing.html**: Add risk card below hero showing portfolio heat + position sizing for top signal
- **swing.html**: Each opportunity row shows "shares to buy" and "risk KWD"
- **swing.html**: Block "ادخل" button if max positions reached or heat exceeded
- **positions.html**: Show total portfolio heat bar

### Telegram Integration:
- When portfolio heat > 5%: "⚠️ مخاطرة محفظتك 5.2% — قريبة من الحد الأقصى 6%"
- When max positions reached: "🚫 الحد الأقصى 3 مراكز مفتوحة — لا تفتح مراكز جديدة"
- Include position size in every signal alert: "📊 ACICO — ادخل 2,500 سهم (مخاطرة 200 د.ك)"

### Files to modify:
- NEW: risk_engine.py (position sizing + portfolio heat)
- MODIFY: signal_engine.py (add risk check before generating signal)
- MODIFY: dashboard_api.py (add /dashboard/risk-status endpoint)
- MODIFY: server.py (DB migration + risk config)
- MODIFY: www/trading/swing.html (claude.ai — risk card + sizing display)
- MODIFY: www/trading/positions.html (claude.ai — heat bar)

---


## ITEM 2: Liquidity & Spread Filter (KSE-Specific)
### Priority: #2 (CRITICAL — KSE-specific, both Gemini & ChatGPT emphasized)
### Effort: Low
### Source: ChatGPT (unique addition — Claude & Gemini missed this)

### What it does:
Filters out stocks that look good technically but are untradable due to
low liquidity or wide spreads. KSE has many stocks with thin order books.

### Logic:
```python
# Liquidity filter constants
MIN_AVG_DAILY_VALUE_KWD = 50000  # 20-day average traded value
MIN_AVG_DAILY_VOLUME = 100000    # 20-day average volume
MAX_SPREAD_PCT = 1.5             # max bid-ask spread as % of price
MAX_POSITION_PCT_OF_ADV = 10.0   # position can't exceed 10% of avg daily value

def check_liquidity(symbol, daily_bars_20d, current_bid, current_ask, position_value):
    avg_volume = mean([b['volume'] for b in daily_bars_20d])
    avg_value = mean([b['close'] * b['volume'] for b in daily_bars_20d])
    spread_pct = ((current_ask - current_bid) / current_bid) * 100 if current_bid > 0 else 999

    passed = True
    reasons = []
    
    if avg_value < MIN_AVG_DAILY_VALUE_KWD:
        passed = False
        reasons.append(f"avg daily value {avg_value:.0f} < {MIN_AVG_DAILY_VALUE_KWD}")
    if avg_volume < MIN_AVG_DAILY_VOLUME:
        passed = False
        reasons.append(f"avg volume {avg_volume:.0f} < {MIN_AVG_DAILY_VOLUME}")
    if spread_pct > MAX_SPREAD_PCT:
        passed = False
        reasons.append(f"spread {spread_pct:.1f}% > {MAX_SPREAD_PCT}%")
    if position_value > avg_value * (MAX_POSITION_PCT_OF_ADV / 100):
        passed = False
        reasons.append(f"position {position_value:.0f} > {MAX_POSITION_PCT_OF_ADV}% of ADV")
    
    return {
        "passed": passed,
        "avg_daily_volume": int(avg_volume),
        "avg_daily_value_kwd": round(avg_value, 0),
        "spread_pct": round(spread_pct, 2),
        "reasons": reasons
    }
```

### DB Changes:
```sql
-- Add liquidity columns to stock_radar_daily
ALTER TABLE stock_radar_daily ADD COLUMN avg_daily_volume INTEGER DEFAULT 0;
ALTER TABLE stock_radar_daily ADD COLUMN avg_daily_value REAL DEFAULT 0;
ALTER TABLE stock_radar_daily ADD COLUMN spread_pct REAL DEFAULT 0;
ALTER TABLE stock_radar_daily ADD COLUMN liquidity_pass INTEGER DEFAULT 1;
```

### Endpoint:
```
GET /dashboard/swing  (existing — add liquidity fields)
Each opportunity now includes:
{
  "symbol": "ACICO",
  "liquidity": {
    "passed": true,
    "avg_daily_volume": 250000,
    "avg_daily_value_kwd": 125000,
    "spread_pct": 0.8,
    "tradable": true
  }
}
```

### Feature Flag:
```
LIQUIDITY_FILTER = True
```

### Dashboard Integration:
- **swing.html**: Opportunities that fail liquidity → show dimmed with "سيولة ضعيفة" badge
- **swing.html**: Liquidity bar (green/amber/red) on each stock card
- **radar.html**: Add liquidity column to market overview table
- **personality.html**: Show stock liquidity profile

### Telegram Integration:
- If top signal fails liquidity: "⚠️ ACICO إشارة قوية لكن سيولة ضعيفة — حجم يومي 30K فقط"
- Never send "ادخل" alert for stocks that fail liquidity filter

### Files to modify:
- MODIFY: signal_engine.py (add liquidity check after confluence)
- MODIFY: stock_radar.py (calculate avg volume/value during daily scan)
- MODIFY: dashboard_api.py (add liquidity to swing endpoint response)
- MODIFY: www/trading/swing.html (claude.ai — liquidity badges)
- MODIFY: www/trading/radar.html (claude.ai — liquidity column)

---

## ITEM 3: Market Regime Filter (Index-Level)
### Priority: #3 (HIGH — all 3 AIs agree)
### Effort: Low
### Source: All 3 AIs

### What it does:
Checks the Kuwait All Share Index (KWSE) trend before allowing any buy signal.
If the overall market is bearish, blocks ALL new buy signals regardless of
individual stock strength.

### Logic:
```python
# Add KWSE index to Bridge watchlist
INDEX_SYMBOL = "KWSE"  # Kuwait All Share Index on TradingView

async def check_market_regime(bridge_client):
    """
    Returns market regime status.
    Uses SMA 50 (longer than individual stock SMA 20) + ADX.
    """
    bars = await bridge_client.get_bars(INDEX_SYMBOL, interval='1D', bars=60)
    if not bars or len(bars) < 50:
        return {"regime": "UNKNOWN", "allow_buy": True, "reason": "insufficient data"}
    
    closes = [b['close'] for b in bars]
    sma50 = mean(closes[-50:])
    current = closes[-1]
    
    # ADX calculation (use Bridge API if available)
    analysis = await bridge_client.get_analysis(INDEX_SYMBOL, interval='1D')
    adx = analysis.get('ADX', 0) if analysis else 0
    
    above_sma = current > sma50
    trending = adx > 20
    
    if above_sma and trending:
        regime = "BULLISH"
        allow_buy = True
    elif above_sma and not trending:
        regime = "NEUTRAL"
        allow_buy = True  # allow but with caution
    elif not above_sma and trending:
        regime = "BEARISH"
        allow_buy = False  # strong downtrend — block buys
    else:
        regime = "CHOPPY"
        allow_buy = False  # below SMA and no trend — worst case
    
    return {
        "regime": regime,
        "allow_buy": allow_buy,
        "index_price": current,
        "index_sma50": round(sma50, 2),
        "index_adx": round(adx, 1),
        "above_sma50": above_sma,
        "reason": f"Index {'above' if above_sma else 'below'} SMA50, ADX={adx:.0f}"
    }
```

### DB Changes:
```sql
-- Store daily regime snapshot
CREATE TABLE IF NOT EXISTS market_regime (
    date TEXT PRIMARY KEY,
    regime TEXT,
    allow_buy INTEGER,
    index_close REAL,
    index_sma50 REAL,
    index_adx REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### Endpoint:
```
GET /dashboard/swing  (existing — add regime to response)
{
  "market_regime": {
    "regime": "BULLISH",
    "allow_buy": true,
    "index_price": 7250.5,
    "index_sma50": 7180.2,
    "index_adx": 28.5
  }
}
```

### Feature Flag:
```
MARKET_REGIME_FILTER = True
```

### Dashboard Integration:
- **swing.html**: Hero section changes color based on regime:
  - BULLISH = green hero "السوق صاعد — ابحث عن فرص"
  - NEUTRAL = amber "السوق محايد — حذر"
  - BEARISH = red "السوق نازل — لا تشتري"
  - CHOPPY = red "السوق مشوش — انتظر"
- **swing.html**: If regime blocks buys → all opportunities show "محظور بسبب اتجاه السوق"
- **home.html**: Teaser shows regime badge
- **radar.html**: Market regime banner at top

### Telegram Integration:
- Daily morning alert (8:45 AM before market): "📊 نظام السوق اليوم: صاعد ✅ — SMA50: 7180 | ADX: 28"
- When regime changes: "🔴 تحول السوق من صاعد إلى نازل — تم إيقاف جميع إشارات الشراء"

### Files to modify:
- MODIFY: signal_engine.py (add regime check before any signal)
- MODIFY: stock_radar.py (fetch index data during scan)
- MODIFY: dashboard_api.py (add regime to /dashboard/swing)
- MODIFY: bridge_client.py (add INDEX_SYMBOL to watchlist)
- MODIFY: www/trading/swing.html (claude.ai — regime hero)
- MODIFY: www/trading/home.html (claude.ai — regime badge in teaser)
- MODIFY: www/trading/radar.html (claude.ai — regime banner)

---


## ITEM 4: Realistic Paper Trading + Slippage Tracking
### Priority: #4 (HIGH — validates everything before real money)
### Effort: Medium
### Source: ChatGPT + Gemini

### What it does:
Simulates real trading without using actual money.
Tracks the gap between signal price and actual executable price (slippage).
After 3 months, produces a truthful performance report.

### Logic:
```python
# Paper trade lifecycle
# Signal fires → system "buys" at signal price + estimated slippage
# Daily check → if stop hit or target hit → system "sells"
# All recorded in paper_trades table

ESTIMATED_SLIPPAGE_PCT = 0.15  # 0.15% slippage assumption for KSE
BROKER_COMMISSION_PCT = 0.125  # 0.125% each way (0.25% round trip)

def open_paper_trade(signal):
    slippage = signal['entry_price'] * (ESTIMATED_SLIPPAGE_PCT / 100)
    actual_entry = signal['entry_price'] + slippage  # worse entry
    commission = actual_entry * signal['shares'] * (BROKER_COMMISSION_PCT / 100)
    return {
        "symbol": signal['symbol'],
        "signal_price": signal['entry_price'],
        "actual_entry": round(actual_entry, 3),
        "slippage_fils": round(slippage * 1000, 1),
        "shares": signal['shares'],
        "stop_loss": signal['stop_loss'],
        "target": signal['target'],
        "commission_kwd": round(commission, 3),
        "status": "open",
        "opened_at": now()
    }

def close_paper_trade(trade, exit_price, exit_reason):
    slippage = exit_price * (ESTIMATED_SLIPPAGE_PCT / 100)
    actual_exit = exit_price - slippage  # worse exit
    commission = actual_exit * trade['shares'] * (BROKER_COMMISSION_PCT / 100)
    pnl = (actual_exit - trade['actual_entry']) * trade['shares']
    pnl_net = pnl - trade['commission_kwd'] - commission
    return {
        "exit_price": round(actual_exit, 3),
        "exit_slippage_fils": round(slippage * 1000, 1),
        "exit_commission_kwd": round(commission, 3),
        "pnl_gross_kwd": round(pnl, 3),
        "pnl_net_kwd": round(pnl_net, 3),
        "exit_reason": exit_reason,  # stop_hit | target_hit | manual | time_exit
        "closed_at": now(),
        "holding_days": days_between(trade['opened_at'], now())
    }
```

### DB Changes:
```sql
CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    direction TEXT DEFAULT 'long',
    signal_price REAL,
    actual_entry REAL,
    entry_slippage REAL,
    shares INTEGER,
    stop_loss REAL,
    target REAL,
    entry_commission REAL,
    status TEXT DEFAULT 'open',  -- open, closed, cancelled
    exit_price REAL,
    exit_slippage REAL,
    exit_commission REAL,
    exit_reason TEXT,  -- stop_hit, target_hit, manual, time_exit
    pnl_gross REAL,
    pnl_net REAL,
    holding_days INTEGER,
    regime_at_entry TEXT,
    confluence_at_entry REAL,
    adx_at_entry REAL,
    volume_at_entry REAL,
    opened_at TEXT,
    closed_at TEXT,
    notes TEXT
);
```

### Endpoint:
```
GET /dashboard/paper-trading
{
  "mode": "paper",
  "account_start": 10000,
  "account_current": 10350,
  "total_trades": 15,
  "open_trades": 2,
  "closed_trades": 13,
  "win_rate": 46.2,
  "avg_win_kwd": 180,
  "avg_loss_kwd": -95,
  "avg_rr_actual": 1.89,
  "total_slippage_kwd": 12.5,
  "total_commission_kwd": 45.2,
  "max_drawdown_pct": 3.1,
  "sharpe_ratio": 1.2,
  "open_positions": [...],
  "recent_closed": [...]
}

POST /api/paper-trade/open  (auto-triggered by signal engine)
POST /api/paper-trade/close (auto-triggered by stop/target hit)
```

### Feature Flag:
```
PAPER_TRADING = True
```

### Dashboard Integration:
- **swing.html**: Badge "📝 Paper Mode" on hero
- **swing.html**: When signal fires, show "Paper trade opened: 2,500 shares @ 0.150"
- **positions.html**: Paper trades shown with "PAPER" badge, separate from real trades
- **journal.html**: Paper trade P&L history with slippage column
- NEW **paper.html**: Dedicated paper trading dashboard (equity curve + stats + all trades)

### Telegram Integration:
- Paper trade opened: "📝 [PAPER] شراء ACICO — 2,500 سهم @ 0.150 | ستوب 0.142 | هدف 0.168"
- Paper trade closed: "📝 [PAPER] إغلاق ACICO — ربح 180 د.ك (بعد العمولة والانزلاق) | 5 أيام"
- Weekly summary (Friday): "📊 ملخص Paper Trading: 3 صفقات | 2 ربح 1 خسارة | صافي +285 د.ك"

### Files to modify:
- NEW: paper_trading.py (open/close/daily check logic)
- MODIFY: signal_engine.py (auto-open paper trade on signal)
- MODIFY: stock_radar.py (daily stop/target check for paper trades)
- MODIFY: dashboard_api.py (add /dashboard/paper-trading endpoint)
- MODIFY: server.py (DB migration + scheduled daily paper trade check)
- NEW: www/trading/paper.html (claude.ai — paper trading dashboard)
- MODIFY: www/trading/swing.html (claude.ai — paper mode badge)
- MODIFY: www/trading/positions.html (claude.ai — paper positions section)

---

## ITEM 5: Equity Curve + Drawdown + Trade Journal
### Priority: #5 (HIGH — can't improve what you don't measure)
### Effort: Medium
### Source: All 3 AIs

### What it does:
Daily snapshot of portfolio value. Calculates drawdown from peak.
Produces an equity curve chart on dashboard.
Enhanced trade journal with reason codes and setup analysis.

### DB Changes:
```sql
CREATE TABLE IF NOT EXISTS equity_snapshots (
    date TEXT PRIMARY KEY,
    cash_kwd REAL,
    open_positions_value REAL,
    total_equity REAL,
    daily_pnl REAL,
    peak_equity REAL,
    drawdown_pct REAL,
    open_count INTEGER,
    win_count_total INTEGER,
    loss_count_total INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Add reason codes to paper_trades / trades
-- (already in paper_trades schema above)
-- Additional fields for journal analysis:
ALTER TABLE paper_trades ADD COLUMN setup_type TEXT;  -- trend_follow, bounce, breakout
ALTER TABLE paper_trades ADD COLUMN pre_trade_checklist TEXT;  -- JSON of checklist results
```

### Endpoint:
```
GET /dashboard/equity
{
  "current_equity": 10350,
  "peak_equity": 10500,
  "drawdown_pct": 1.4,
  "max_drawdown_pct": 3.1,
  "total_return_pct": 3.5,
  "win_rate": 46.2,
  "expectancy_kwd": 42.5,
  "avg_holding_days": 4.2,
  "equity_curve": [
    {"date": "2026-04-06", "equity": 10000},
    {"date": "2026-04-07", "equity": 10120},
    ...
  ]
}
```

### Feature Flag:
```
EQUITY_TRACKER = True
```

### Dashboard Integration:
- **swing.html**: Small equity badge in hero "📈 10,350 KWD (+3.5%)"
- **journal.html**: Equity curve chart (line chart with drawdown shading)
- **journal.html**: Enhanced trade table with setup type + slippage + R:R actual
- **home.html**: Teaser shows equity trend (up/down arrow)

### Telegram Integration:
- Daily close (1:00 PM): "📈 رأس المال: 10,350 د.ك (+120 اليوم) | Drawdown: 1.4%"
- When drawdown > 3%: "🔴 تحذير: Drawdown وصل 3.2% — راجع المراكز"
- Weekly summary: "📊 الأسبوع: +2.1% | 4 صفقات | Win Rate 50% | Max DD 1.8%"

### Files to modify:
- NEW: equity_tracker.py (daily snapshot + drawdown calc)
- MODIFY: dashboard_api.py (add /dashboard/equity endpoint)
- MODIFY: server.py (schedule daily equity snapshot at 1:00 PM)
- MODIFY: www/trading/journal.html (claude.ai — equity curve chart)
- MODIFY: www/trading/swing.html (claude.ai — equity badge)
- MODIFY: www/trading/home.html (claude.ai — equity in teaser)

---


## ITEM 6: Execution Checklist (Pre-Trade Gate)
### Priority: #6 (MEDIUM — prevents emotional/impulsive trades)
### Effort: Low
### Source: ChatGPT (unique — missed by Claude & Gemini)

### What it does:
Before every trade, the system runs a comprehensive checklist.
ALL checks must pass before the system says "ادخل".
Displayed as a compact card on swing.html and sent via Telegram.

### Logic:
```python
def pre_trade_checklist(symbol, signal, regime, risk_status, liquidity):
    checks = [
        {"name": "market_regime", "label": "اتجاه السوق", "passed": regime['allow_buy']},
        {"name": "daily_trend", "label": "اتجاه السهم (SMA20)", "passed": signal['daily_trend'] == 'UP'},
        {"name": "adx_valid", "label": "ADX > 25", "passed": signal.get('adx', 0) >= 25},
        {"name": "volume_valid", "label": "حجم 1-3x", "passed": 1 <= signal.get('vol_ratio', 0) <= 3},
        {"name": "spread_ok", "label": "سبريد مقبول", "passed": liquidity['spread_pct'] <= 1.5},
        {"name": "liquidity_ok", "label": "سيولة كافية", "passed": liquidity['passed']},
        {"name": "risk_ok", "label": "مخاطرة ضمن الحد", "passed": risk_status['can_open_new']},
        {"name": "max_positions", "label": "مراكز < الحد", "passed": risk_status['open_positions'] < risk_status['max_positions']},
        {"name": "sector_ok", "label": "قطاع غير مكرر", "passed": risk_status['sector_check']},
        {"name": "rr_valid", "label": "R:R > 1.5", "passed": signal.get('swing_rr', 0) >= 1.5},
        {"name": "not_duplicate", "label": "ليس مركز مفتوح", "passed": symbol not in [p['symbol'] for p in risk_status['positions']]},
    ]
    all_passed = all(c['passed'] for c in checks)
    return {
        "symbol": symbol,
        "all_passed": all_passed,
        "passed_count": sum(1 for c in checks if c['passed']),
        "total_checks": len(checks),
        "checks": checks,
        "verdict": "ادخل" if all_passed else "لا تدخل",
        "failed": [c['label'] for c in checks if not c['passed']]
    }
```

### Endpoint:
```
GET /dashboard/swing  (existing — add checklist to each opportunity)
Each opportunity includes:
{
  "checklist": {
    "all_passed": true,
    "passed_count": 11,
    "total_checks": 11,
    "checks": [...],
    "verdict": "ادخل"
  }
}
```

### No new DB tables needed — computed on the fly.

### Feature Flag:
```
PRE_TRADE_CHECKLIST = True
```

### Dashboard Integration:
- **swing.html**: Each opportunity card has expandable checklist (green/red dots)
- **swing.html**: Verdict badge: "✅ 11/11 — ادخل" or "❌ 9/11 — لا تدخل (سيولة + قطاع)"
- **swing.html**: Failed checks highlighted in red with reason

### Telegram Integration:
- Signal alert includes compact checklist:
  "📋 ACICO — Checklist 11/11 ✅
   السوق ✅ | الاتجاه ✅ | ADX ✅ | حجم ✅ | سيولة ✅ | مخاطرة ✅ | R:R 2.1x ✅
   ▶️ ادخل 2,500 سهم @ 0.150 | ستوب 0.142 | هدف 0.168"
- If not all passed:
  "📋 ACICO — Checklist 9/11 ❌
   ❌ سيولة ضعيفة | ❌ قطاع مكرر
   ⏸️ لا تدخل"

### Files to modify:
- MODIFY: signal_engine.py (add checklist computation)
- MODIFY: dashboard_api.py (include checklist in swing response)
- MODIFY: www/trading/swing.html (claude.ai — checklist card per opportunity)

---

## ITEM 7: Sector Exposure Limits
### Priority: #7 (MEDIUM — prevents hidden concentration risk)
### Effort: Low
### Source: ChatGPT + Gemini

### What it does:
Maps each whitelist stock to its KSE sector.
Limits max positions per sector to prevent taking the same directional bet
through different stocks.

### Data:
```python
STOCK_SECTORS = {
    "INOVEST": "financial_services",
    "URC": "industrial",
    "ACICO": "industrial",
    "AAYANRE": "real_estate",
    "OOREDOO": "telecom",
    "ALFTAQA": "financial_services",
    "NINV": "financial_services",
    "MUBARRAD": "industrial",
    "NRE": "real_estate",
    "RASIYAT": "real_estate",
}

# Risk: INOVEST + ALFTAQA + NINV = 3 financial_services stocks
# Without sector limits, could have all 3 open = one bet on financials
```

### Logic:
Already included in ITEM 1 (Portfolio Risk Engine) via MAX_SECTOR_POSITIONS.
This item adds the sector mapping data and integrates it.

### DB Changes:
```sql
-- Update stock_profiles with sector data
UPDATE stock_profiles SET sector = 'financial_services' WHERE symbol = 'INOVEST';
UPDATE stock_profiles SET sector = 'industrial' WHERE symbol = 'URC';
UPDATE stock_profiles SET sector = 'industrial' WHERE symbol = 'ACICO';
UPDATE stock_profiles SET sector = 'real_estate' WHERE symbol = 'AAYANRE';
UPDATE stock_profiles SET sector = 'telecom' WHERE symbol = 'OOREDOO';
UPDATE stock_profiles SET sector = 'financial_services' WHERE symbol = 'ALFTAQA';
UPDATE stock_profiles SET sector = 'financial_services' WHERE symbol = 'NINV';
UPDATE stock_profiles SET sector = 'industrial' WHERE symbol = 'MUBARRAD';
UPDATE stock_profiles SET sector = 'real_estate' WHERE symbol = 'NRE';
UPDATE stock_profiles SET sector = 'real_estate' WHERE symbol = 'RASIYAT';
```

### Dashboard Integration:
- **swing.html**: Sector badge on each stock card
- **positions.html**: Sector exposure bar chart
- **swing.html**: If sector full → opportunity shows "⚠️ القطاع مشبع"

### Telegram:
- Part of checklist (ITEM 6): "❌ قطاع مكرر — عندك مركزين صناعي"

### Files to modify:
- MODIFY: signal_engine.py (sector check in signal generation)
- MODIFY: server.py (DB migration — seed sector data)
- MODIFY: www/trading/swing.html (claude.ai — sector badges)
- MODIFY: www/trading/positions.html (claude.ai — sector exposure chart)

---

## ITEM 8: Dynamic Whitelist Review
### Priority: #8 (LOW — monthly/quarterly task)
### Effort: Low
### Source: Claude + Gemini

### What it does:
Monthly script that re-evaluates all 128 stocks based on recent performance.
Produces a report suggesting whitelist additions/removals.
Does NOT auto-change the whitelist — user decides.

### Logic:
```python
async def review_whitelist():
    """
    Run monthly. Analyzes last 90 days of signal outcomes.
    Ranks all stocks by composite score.
    """
    results = []
    for symbol in ALL_128_SYMBOLS:
        outcomes = db.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as wins,
                   AVG(CASE WHEN outcome='win' THEN gain_pct ELSE NULL END) as avg_win,
                   AVG(CASE WHEN outcome='loss' THEN gain_pct ELSE NULL END) as avg_loss
            FROM signal_outcomes
            WHERE symbol = ? AND created_at > date('now', '-90 days')
        """, (symbol,)).fetchone()
        
        if outcomes['total'] < 5:
            continue
        
        win_rate = outcomes['wins'] / outcomes['total']
        rr = abs(outcomes['avg_win'] / outcomes['avg_loss']) if outcomes['avg_loss'] else 0
        score = win_rate * rr  # simple composite
        
        results.append({
            "symbol": symbol,
            "signals_90d": outcomes['total'],
            "win_rate": round(win_rate * 100, 1),
            "avg_win_pct": round(outcomes['avg_win'] or 0, 2),
            "avg_loss_pct": round(outcomes['avg_loss'] or 0, 2),
            "rr": round(rr, 2),
            "score": round(score, 3)
        })
    
    results.sort(key=lambda x: x['score'], reverse=True)
    
    return {
        "review_date": today(),
        "top_10_recommended": results[:10],
        "current_whitelist_performance": [r for r in results if r['symbol'] in WHITELIST],
        "suggest_add": [r for r in results[:10] if r['symbol'] not in WHITELIST],
        "suggest_remove": [r for r in results if r['symbol'] in WHITELIST and r['score'] < results[9]['score']]
    }
```

### Endpoint:
```
GET /api/whitelist-review (API key protected)
```

### Dashboard Integration:
- **decisions.html**: Monthly review card (if stale > 30 days, show reminder)

### Telegram:
- Monthly reminder: "📊 مراجعة Whitelist الشهرية جاهزة — افتح decisions.html"

### Files to modify:
- NEW: whitelist_review.py (analysis script)
- MODIFY: dashboard_api.py (add /api/whitelist-review endpoint)
- MODIFY: server.py (monthly scheduler)

---


## ═══════════════════════════════════════════════════════
## EXECUTION ORDER & DEPENDENCIES
## ═══════════════════════════════════════════════════════

```
ITEM 3 (Market Regime)     ← FIRST — needs Bridge online (Sunday)
  ↓
ITEM 2 (Liquidity Filter)  ← needs daily_bars data
  ↓
ITEM 1 (Risk Engine)       ← needs sector data + liquidity results
  ↓
ITEM 7 (Sector Limits)     ← part of Risk Engine, same commit
  ↓
ITEM 6 (Checklist)         ← combines regime + liquidity + risk into one gate
  ↓
ITEM 4 (Paper Trading)     ← uses all above to simulate trades
  ↓
ITEM 5 (Equity Tracker)    ← tracks paper trading results
  ↓
ITEM 8 (Whitelist Review)  ← monthly, after enough paper data exists
```

## ═══════════════════════════════════════════════════════
## NEW FILES CREATED (Claude Code)
## ═══════════════════════════════════════════════════════
- risk_engine.py         (ITEM 1 + 7)
- paper_trading.py       (ITEM 4)
- equity_tracker.py      (ITEM 5)
- whitelist_review.py    (ITEM 8)

## ═══════════════════════════════════════════════════════
## NEW HTML PAGES (claude.ai)
## ═══════════════════════════════════════════════════════
- www/trading/paper.html  (ITEM 4 — paper trading dashboard)

## ═══════════════════════════════════════════════════════
## MODIFIED HTML PAGES (claude.ai)
## ═══════════════════════════════════════════════════════
- www/trading/swing.html     (ITEMS 1,2,3,4,5,6,7 — major update)
- www/trading/home.html      (ITEMS 3,5 — regime badge + equity)
- www/trading/positions.html (ITEMS 1,7 — heat bar + sector chart)
- www/trading/journal.html   (ITEM 5 — equity curve)
- www/trading/radar.html     (ITEMS 2,3 — liquidity + regime)
- www/trading/decisions.html (ITEM 8 — whitelist review reminder)
- www/trading/personality.html (ITEM 2 — liquidity profile)

## ═══════════════════════════════════════════════════════
## NEW DB TABLES
## ═══════════════════════════════════════════════════════
- risk_config (ITEM 1)
- market_regime (ITEM 3)
- paper_trades (ITEM 4)
- equity_snapshots (ITEM 5)

## ═══════════════════════════════════════════════════════
## NEW ENDPOINTS
## ═══════════════════════════════════════════════════════
- GET  /dashboard/risk-status      (ITEM 1)
- GET  /dashboard/paper-trading    (ITEM 4)
- POST /api/paper-trade/open       (ITEM 4)
- POST /api/paper-trade/close      (ITEM 4)
- GET  /dashboard/equity           (ITEM 5)
- GET  /api/whitelist-review       (ITEM 8)

## ═══════════════════════════════════════════════════════
## FEATURE FLAGS
## ═══════════════════════════════════════════════════════
- RISK_ENGINE = True          (ITEM 1)
- LIQUIDITY_FILTER = True     (ITEM 2)
- MARKET_REGIME_FILTER = True (ITEM 3)
- PAPER_TRADING = True        (ITEM 4)
- EQUITY_TRACKER = True       (ITEM 5)
- PRE_TRADE_CHECKLIST = True  (ITEM 6)

## ═══════════════════════════════════════════════════════
## TELEGRAM ALERTS (new)
## ═══════════════════════════════════════════════════════
- Daily morning regime alert (8:45 AM)
- Regime change alert (real-time)
- Portfolio heat warning (>5%)
- Max positions warning
- Paper trade open/close alerts
- Weekly paper trading summary (Friday)
- Daily equity + drawdown (1:00 PM)
- Drawdown warning (>3%)
- Monthly whitelist review reminder

## ═══════════════════════════════════════════════════════
## NAV BAR UPDATE
## ═══════════════════════════════════════════════════════
# swing.html nav becomes 8 links (add paper):
# سوينق | تحليل فني | المراكز | Paper | Gemini | السوق | السجل | العقل
# Or paper.html accessible from swing hero badge only (cleaner)

## ═══════════════════════════════════════════════════════
## HA DASHBOARD YAML
## ═══════════════════════════════════════════════════════
# Add sub-paper view for paper.html (if created as separate page)
# Update home iframe URL ?v=3 for cache bust

## ═══════════════════════════════════════════════════════
## CLAUDE CODE COMMAND
## ═══════════════════════════════════════════════════════
# اقرأ _tools/TRADING_V2_PHASE2_PLAN.md وابدأ بـ ITEM 3 (Market Regime)
# ثم ITEM 2 (Liquidity) ثم ITEM 1+7 (Risk+Sector) ثم ITEM 6 (Checklist)
# ثم ITEM 4 (Paper Trading) ثم ITEM 5 (Equity Tracker)
# ITEM 8 (Whitelist Review) يكون آخر شي
# بعد كل ITEM: quick_check.py + smoke_test.py + git commit
