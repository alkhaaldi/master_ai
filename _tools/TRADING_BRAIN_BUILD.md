# TRADING BRAIN — Signal Learning Engine
# Master AI v9.x — Claude Code Task
# Date: 2026-03-26
# Priority: HIGH
# Status: APPROVED — Ready for execution

---

## GOAL
Build a "Trading Brain" that tracks every signal, evaluates it against real market outcome,
learns which indicators work best, and auto-adjusts confluence weights over time.

**User's words:** "أبيه يتحسن و يقارن بين واقع السوق و بين التحليل الفني"

---

## ARCHITECTURE OVERVIEW

### New file: `trading_brain.py` (~400-500 lines)
Location: `/home/pi/master_ai/trading_brain.py`

### What it does:
1. **TRACK** — Every signal gets logged with a snapshot of all indicators at that moment
2. **FOLLOW** — After 1/3/5/7 days, check what actually happened to the stock price
3. **EVALUATE** — Compare prediction vs reality → mark signal as HIT or MISS
4. **LEARN** — Calculate hit rate per indicator → adjust weights
5. **REPORT** — Weekly summary: what worked, what failed, which indicators to trust

---

## EXISTING SYSTEM (DO NOT BREAK)

### Files that trading_brain.py reads from:
- `signal_engine.py` — current signal generation (confluence scores, verdicts)
- `stock_radar.py` — 128 stock daily data (stock_radar_daily table)
- `journal_engine.py` — open/closed trades, P&L
- `bridge_client.py` — live TradingView data

### Files that need PATCHING:
- `server.py` — add init_trading_brain_context() to lifespan + scheduler
- `dashboard_api.py` — add /dashboard/brain endpoint for dashboard display

---

## DATABASE TABLES (in data/life.db)

### Table 1: signal_snapshots
Stores every signal at the moment it was generated, with ALL indicator values frozen.
```sql
CREATE TABLE IF NOT EXISTS signal_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    signal_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Signal info
    trade_state TEXT,              -- discovery/setup/ready/entered/manage
    verdict TEXT,                  -- شراء/مراقبة/مراجعة/تجنب/حياد
    verdict_key TEXT,              -- buy/watch/review/avoid/neutral
    confluence_score INTEGER,      -- 0-100
    -- Frozen indicator snapshot (what the brain saw)
    price_at_signal REAL,
    rsi_14 REAL,
    macd_state TEXT,               -- bullish/bearish
    macd_momentum TEXT,            -- accelerating_bullish/decelerating_bullish/etc
    ema_state TEXT,                -- bullish/bearish
    adx REAL,
    vol_ratio REAL,
    stoch_k REAL,
    bb_squeeze BOOLEAN,
    rsi_divergence TEXT,           -- bullish/bearish/none
    ema_cross_type TEXT,           -- golden/death/null
    ema_cross_bars_ago INTEGER,
    support REAL,
    resistance REAL,
    atr_14 REAL,
    -- Individual indicator contribution (1=bullish, 0=bearish for each)
    ind_rsi INTEGER,               -- 1 if RSI>50, 0 if RSI<50
    ind_macd INTEGER,              -- 1 if MACD hist>0, 0 otherwise
    ind_ema INTEGER,               -- 1 if price>EMA20/50/200, 0 otherwise
    ind_adx INTEGER,               -- 1 if ADX>25 and trend aligned, 0 otherwise
    ind_vol INTEGER,               -- 1 if OBV rising, 0 otherwise
    ind_stoch INTEGER,             -- 1 if StochK>50, 0 otherwise
    ind_obv INTEGER,               -- 1 if OBV trend positive, 0 otherwise
    -- Outcome tracking
    outcome TEXT DEFAULT 'pending', -- pending/hit/miss/expired
    price_1d REAL,                 -- price after 1 day
    price_3d REAL,                 -- price after 3 days
    price_5d REAL,                 -- price after 5 days
    price_7d REAL,                 -- price after 7 days
    max_gain_pct REAL,             -- max gain in 7-day window
    max_loss_pct REAL,             -- max loss in 7-day window
    outcome_pct REAL,              -- final % change at evaluation
    outcome_evaluated_at TIMESTAMP,
    -- Metadata
    source TEXT DEFAULT 'auto',    -- auto/manual
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_ss_symbol ON signal_snapshots(symbol);
CREATE INDEX IF NOT EXISTS idx_ss_outcome ON signal_snapshots(outcome);
CREATE INDEX IF NOT EXISTS idx_ss_time ON signal_snapshots(signal_time);
```

### Table 2: indicator_performance
Running statistics for each indicator's accuracy.
```sql
CREATE TABLE IF NOT EXISTS indicator_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator_name TEXT UNIQUE NOT NULL, -- rsi/macd/ema/adx/vol/stoch/obv
    total_signals INTEGER DEFAULT 0,
    total_hits INTEGER DEFAULT 0,
    hit_rate REAL DEFAULT 0.5,          -- 0.0 to 1.0
    current_weight REAL DEFAULT 1.0,    -- adaptive weight
    base_weight REAL DEFAULT 1.0,       -- original weight (never changes)
    last_updated TIMESTAMP,
    -- Rolling window stats (last 50 signals)
    rolling_hits INTEGER DEFAULT 0,
    rolling_total INTEGER DEFAULT 0,
    rolling_hit_rate REAL DEFAULT 0.5
);
```

### Table 3: brain_weekly_reports
Weekly performance summaries.
```sql
CREATE TABLE IF NOT EXISTS brain_weekly_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL,           -- ISO date string
    week_end TEXT NOT NULL,
    total_signals INTEGER,
    total_evaluated INTEGER,
    hits INTEGER,
    misses INTEGER,
    hit_rate REAL,
    avg_gain_on_hits REAL,             -- average % gain on correct signals
    avg_loss_on_misses REAL,           -- average % loss on wrong signals
    best_indicator TEXT,
    best_indicator_rate REAL,
    worst_indicator TEXT,
    worst_indicator_rate REAL,
    weight_adjustments TEXT,            -- JSON of weight changes made
    market_summary TEXT,               -- brief text summary
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## CORE FUNCTIONS

### 1. `snapshot_signals()` — Called after each radar scan
```
When signal_engine produces signals, trading_brain snapshots them:
- For each signal with confluence_score >= 50 (worth tracking):
  - Freeze all indicator values at that moment
  - Record each indicator's individual bullish/bearish vote
  - Store in signal_snapshots with outcome='pending'
- Dedup: don't re-snapshot same symbol if already pending within 24h
```

### 2. `evaluate_pending_signals()` — Called daily at 13:30 KWT (after market close)
```
For each pending signal older than evaluation_days:
- Get current price from stock_radar_daily or bridge
- Calculate:
  - price_change_pct = (current_price - price_at_signal) / price_at_signal * 100
  - Also record price at 1d, 3d, 5d, 7d checkpoints
  - max_gain and max_loss during the window
  
Outcome rules (for BUY/WATCH signals with confluence >= 50):
  HIT if:
    - price went UP by >= ATR*0.5 within 7 days (meaningful move)
    - OR price went UP by >= 3% within 7 days
  MISS if:
    - price went DOWN by >= ATR*0.5 within 7 days
    - OR price went DOWN by >= 3% within 7 days
  EXPIRED if:
    - 7 days passed and price barely moved (< ATR*0.3 in either direction)
    
For AVOID signals:
  HIT if price went DOWN (correctly predicted weakness)
  MISS if price went UP significantly despite avoid signal
```

### 3. `update_indicator_performance()` — Called after evaluate_pending_signals
```
For each evaluated signal:
  For each of the 7 indicators:
    - If indicator voted BULLISH (ind_xxx=1) and outcome=HIT → indicator was RIGHT
    - If indicator voted BULLISH and outcome=MISS → indicator was WRONG
    - Update indicator_performance: total_signals++, total_hits++ (if right)
    - Recalculate hit_rate = total_hits / total_signals
    
Rolling window (last 50 signals):
  - Keep only last 50 evaluated signals for rolling stats
  - This prevents ancient history from dominating recent performance
```

### 4. `adjust_weights()` — Called weekly (Sunday before market opens)
```
For each indicator:
  new_weight = base_weight * (0.5 + rolling_hit_rate)
  
  Example:
  - RSI has rolling_hit_rate = 0.70 → weight = 1.0 * (0.5 + 0.70) = 1.20
  - MACD has rolling_hit_rate = 0.35 → weight = 1.0 * (0.5 + 0.35) = 0.85
  
  Clamp weights: min=0.3, max=2.0 (never fully disable or over-amplify)
  
  Store the adjustment in brain_weekly_reports as JSON
```

### 5. `get_adjusted_confluence(symbol_data)` — Used by signal_engine
```
Instead of equal-weight confluence, use brain's adaptive weights:
  
  weighted_bullish = sum(ind_vote * indicator_weight for each indicator)
  weighted_total = sum(indicator_weight for each indicator)
  adjusted_score = (weighted_bullish / weighted_total) * 100
  
This replaces the simple count-based confluence in signal_engine.
```

### 6. `generate_weekly_report()` — Called Friday 14:00 KWT
```
Aggregate all signals from the past week:
- Total signals tracked
- Hits vs Misses vs Expired
- Hit rate overall
- Hit rate per indicator (with ranking)
- Best and worst indicator
- Average gain on hits vs average loss on misses
- Weight adjustments made
- Text summary in Arabic

Send via Telegram:
🧠 تقرير عقل التداول — الأسبوع XX
━━━━━━━━━━━━━━━━━━━━
📊 إشارات: 15 | تقييم: 12
✅ صحيحة: 8 (67%) | ❌ خاطئة: 3 | ⏳ منتهية: 1
━━━━━━━━━━━━━━━━━━━━
📈 أفضل مؤشر: RSI (78% دقة)
📉 أسوأ مؤشر: MACD (42% دقة)
━━━━━━━━━━━━━━━━━━━━
⚖️ تعديل الأوزان:
  RSI: 1.0 → 1.28 ▲
  EMA: 1.0 → 1.15 ▲
  MACD: 1.0 → 0.85 ▼
  ADX: 1.0 → 0.92 ▼
━━━━━━━━━━━━━━━━━━━━
💰 متوسط ربح الإشارات الصحيحة: +4.2%
📉 متوسط خسارة الإشارات الخاطئة: -2.1%
━━━━━━━━━━━━━━━━━━━━
🎯 الخلاصة: النظام يتحسن — RSI و EMA الأقوى هالأسبوع
```

---

## DASHBOARD ENDPOINT

### GET /dashboard/brain
```json
{
  "brain_active": true,
  "total_tracked": 156,
  "total_evaluated": 120,
  "overall_hit_rate": 0.63,
  "pending_count": 15,
  "indicator_weights": {
    "rsi": {"weight": 1.28, "hit_rate": 0.78, "signals": 45},
    "macd": {"weight": 0.85, "hit_rate": 0.42, "signals": 45},
    "ema": {"weight": 1.15, "hit_rate": 0.65, "signals": 45},
    "adx": {"weight": 0.92, "hit_rate": 0.48, "signals": 45},
    "vol": {"weight": 1.05, "hit_rate": 0.55, "signals": 45},
    "stoch": {"weight": 1.10, "hit_rate": 0.60, "signals": 45},
    "obv": {"weight": 0.95, "hit_rate": 0.52, "signals": 45}
  },
  "recent_evaluations": [
    {"symbol": "CLEANING", "signal_time": "...", "verdict": "شراء", "outcome": "hit", "gain_pct": 6.8},
    {"symbol": "ZAIN", "signal_time": "...", "verdict": "مراقبة", "outcome": "miss", "loss_pct": -2.1}
  ],
  "weekly_summary": {
    "hit_rate": 0.67,
    "best_indicator": "RSI",
    "worst_indicator": "MACD"
  },
  "last_weight_adjustment": "2026-03-23T10:00:00",
  "last_evaluation": "2026-03-26T13:30:00"
}
```

---

## INTEGRATION POINTS

### 1. Wire into server.py lifespan:
```python
from trading_brain import init_brain_context
init_brain_context(server_globals)
```

### 2. Scheduler hooks:
- After radar scan completes → call `snapshot_signals()`
- Daily 13:30 KWT → call `evaluate_pending_signals()` + `update_indicator_performance()`
- Sunday 09:00 KWT → call `adjust_weights()`
- Friday 14:00 KWT → call `generate_weekly_report()` → send TG

### 3. Signal engine integration:
- `signal_engine.py` calls `get_adjusted_confluence()` instead of simple counting
- This is the KEY integration — makes the brain actually influence decisions

### 4. Dashboard HTML page:
- New page: `www/trading/brain.html` — shows brain stats, indicator weights, recent evaluations
- Add to HA dashboard as 5th iframe page

---

## ALGORITHM CHOICE

### Why Simple Adaptive Scoring (NOT ML/RL):
1. **RPi 5 constraint** — 4GB RAM, can't run sklearn/pytorch effectively
2. **Small dataset** — 128 stocks, ~10-20 signals/week = ~1000/year. ML needs thousands minimum
3. **Interpretability** — user needs to understand WHY weights changed, not black box
4. **Stability** — ML models can overfit and crash on small data; simple scoring is robust
5. **Incrementality** — weights adjust gradually, no catastrophic forgetting

### The Adaptive Weighted Scoring formula:
```
new_weight = base_weight × (0.5 + rolling_hit_rate_50)

Where:
- base_weight = 1.0 (starting equal weight for all)
- rolling_hit_rate_50 = hits / total for last 50 evaluated signals per indicator
- 0.5 is the "anchor" — ensures weights don't go to zero even if hit_rate is 0
- Result range: 0.5 (terrible indicator) to 1.5 (excellent indicator)
- Clamped to [0.3, 2.0] for safety
```

### Future ML upgrade path (Phase 2, when data > 2000 signals):
- Can add lightweight logistic regression: `sklearn.linear_model.SGDClassifier`
- Input: 7 indicator values → Output: probability of hit
- But this is 6+ months away at current signal frequency

---

## PITFALLS TO AVOID

1. **Survivorship bias** — Track ALL signals, not just the ones acted upon
2. **Look-ahead bias** — Evaluate using only data available at signal time
3. **Overfitting to recent data** — Use rolling 50 window, not all-time
4. **Market regime changes** — Bull market inflates all hit rates; bear market deflates
   → Consider adding a "market regime" tag to each signal
5. **Low sample size** — Don't adjust weights until at least 30 signals per indicator
6. **Feedback loop** — Brain adjusts weights → changes which signals are generated → changes hit rates
   → Monitor for instability; add dampening (slow learning rate)
7. **Weekend/holiday gaps** — KSE is Sun-Thu; evaluation must account for non-trading days

---

## EXECUTION ORDER (for Claude Code)

1. Create `trading_brain.py` (new file, ~400 lines)
2. Create DB tables (in life.db, called from init_brain_context)
3. Wire `init_brain_context()` into server.py lifespan (patch)
4. Add scheduler hooks in server.py (patch)
5. Add `/dashboard/brain` endpoint to dashboard_api.py (patch)
6. Add `/dashboard/brain` to OPEN_PATHS (patch)
7. Integrate `get_adjusted_confluence()` into signal_engine.py (patch)
8. Create `www/trading/brain.html` dashboard page
9. Add to HA dashboard YAML as 5th iframe card
10. quick_check + smoke_test + db_sanity
11. Git commit: "feat: trading brain — signal learning engine with adaptive weights"

## IMPORTANT RULES
- All Python edits on RPi via apply_text_patch.py
- New files can be written directly
- DB tables created with IF NOT EXISTS (safe for restart)
- init_*_context pattern same as other modules
- Backward compatible: existing signal_engine keeps working even if brain fails
- Brain is ADVISORY — it adjusts weights but doesn't block signals
- Minimum 30 signals before any weight adjustment
