# Trading V2 — Remaining Phases (1, 7, 8)
# Date: 2026-04-04
# Status: READY FOR EXECUTION
# Prereqs: Phases 2-6 complete (cf2b64a, 576efcc)

---

## Phase 1: Fix Timeframe Mixing (CRITICAL BUG)

### Problem:
`signals.html` fetchData() mixes 30m live prices with daily indicators.
Tab "يومي" shows hybrid data — live 30m price with daily RSI/MACD/EMA.
This generates false signals.

### Fix — Backend (signal_engine.py / dashboard_api.py):

#### 1.1 Add `timeframe` field to every signal
```python
# In generate_signals() or wherever signals are built:
signal['timeframe'] = '30m'  # or '1D'
signal['valid_until'] = timestamp  # 30m expires after 30 min, daily expires end of day
```

#### 1.2 Split endpoints
```python
# dashboard_api.py — add new endpoint:

@app.get("/dashboard/signals-30m")
async def signals_30m():
    """30m signals ONLY — live prices from Bridge"""
    # Use bridge_client for live 30m data
    # Never mix with daily indicators
    # Return: symbol, price (live), timeframe="30m", 
    #   30m_rsi, 30m_macd, 30m_ema9, 30m_ema21, volume_ratio
    # valid_until = now + 30 minutes
    pass

@app.get("/dashboard/signals-daily")  
async def signals_daily():
    """Daily signals ONLY — closing prices from DB"""
    # Use stock_radar_daily for daily data
    # Price = yesterday's close (NOT live price)
    # Return: symbol, price (close), timeframe="1D",
    #   daily_rsi, daily_sma20, daily_trend, adx, volume,
    #   swing_stop, swing_target, swing_rr, confluence
    # valid_until = end of today
    pass
```

#### 1.3 Fix signals.html tabs
```
Tab "30 دقيقة" → fetch /dashboard/signals-30m ONLY
Tab "يومي" → fetch /dashboard/signals-daily ONLY
NO shared data between tabs
NO mixing live prices with daily indicators
```

#### 1.4 Implementation steps:
1. Add `timeframe` field to signal dict in signal_engine.py
2. Create `/dashboard/signals-30m` endpoint in dashboard_api.py
3. Create `/dashboard/signals-daily` endpoint in dashboard_api.py
4. Keep `/dashboard/signals` as-is for backward compat (returns both with timeframe tag)
5. Update signals.html — each tab fetches its own endpoint
6. Test: verify 30m tab shows ONLY 30m data, daily tab shows ONLY daily data
7. git commit

**Files:** signal_engine.py, dashboard_api.py
**Frontend:** signals.html (claude.ai updates after backend)

---

## Phase 7: S/R Outcome Tracking (DB Migration)

### Goal:
Track support/resistance levels with each signal so we can later analyze:
- "Signals near S1 → hit rate?"
- "Daily trend UP + near support → better than without?"

### 7.1 DB Migration — ALTER TABLE signal_snapshots
```sql
ALTER TABLE signal_snapshots ADD COLUMN daily_pp REAL DEFAULT 0;
ALTER TABLE signal_snapshots ADD COLUMN daily_s1 REAL DEFAULT 0;
ALTER TABLE signal_snapshots ADD COLUMN daily_s2 REAL DEFAULT 0;
ALTER TABLE signal_snapshots ADD COLUMN daily_r1 REAL DEFAULT 0;
ALTER TABLE signal_snapshots ADD COLUMN daily_r2 REAL DEFAULT 0;
ALTER TABLE signal_snapshots ADD COLUMN pdh REAL DEFAULT 0;
ALTER TABLE signal_snapshots ADD COLUMN pdl REAL DEFAULT 0;
ALTER TABLE signal_snapshots ADD COLUMN distance_to_support_pct REAL DEFAULT 0;
ALTER TABLE signal_snapshots ADD COLUMN distance_to_resistance_pct REAL DEFAULT 0;
ALTER TABLE signal_snapshots ADD COLUMN near_support BOOLEAN DEFAULT 0;
ALTER TABLE signal_snapshots ADD COLUMN daily_sma20 REAL DEFAULT 0;
ALTER TABLE signal_snapshots ADD COLUMN daily_trend TEXT DEFAULT 'UNKNOWN';
```

### 7.2 Populate S/R fields in signal pipeline
```python
# In signal_engine.py — when saving a signal snapshot:
# After calculating pivots (from Phase 4), add them to the snapshot:

snapshot['daily_pp'] = pivots.get('pp', 0)
snapshot['daily_s1'] = pivots.get('s1', 0)
snapshot['daily_s2'] = pivots.get('s2', 0)
snapshot['daily_r1'] = pivots.get('r1', 0)
snapshot['daily_r2'] = pivots.get('r2', 0)
snapshot['pdh'] = prev_day_high or 0
snapshot['pdl'] = prev_day_low or 0
snapshot['daily_sma20'] = sma20 or 0
snapshot['daily_trend'] = trend or 'UNKNOWN'

# Distance calculations:
price = snapshot.get('price', 0)
nearest_support = min([s for s in [pivots.get('s1',0), pivots.get('s2',0), pdl] if s > 0 and s < price], default=0)
nearest_resistance = min([r for r in [pivots.get('r1',0), pivots.get('r2',0), pdh] if r > price], default=0)

if nearest_support > 0:
    snapshot['distance_to_support_pct'] = round(((price - nearest_support) / price) * 100, 2)
    atr = snapshot.get('atr_14', 0)
    snapshot['near_support'] = (price - nearest_support) < atr if atr > 0 else False
if nearest_resistance > 0:
    snapshot['distance_to_resistance_pct'] = round(((nearest_resistance - price) / price) * 100, 2)
```

### 7.3 Implementation steps:
1. Run ALTER TABLE statements on life.db
2. Update signal snapshot saving code to include S/R fields
3. Verify new columns are populated on next radar scan
4. git commit

**Files:** signal_engine.py, life.db migration
**Note:** After 1 month of data, we can analyze S/R effectiveness

---

## Phase 8: Feature Flags + Backward Compatibility

### 8.1 Add feature flags to config
```python
# Top of signal_engine.py (or separate config.py):

# Trading Mode Feature Flags
SWING_MODE = True           # True = daily swing logic (V2)
SCALPING_MODE = False       # True = 30m scalping logic (V1, deprecated)
WHITELIST_MODE = True       # True = trade whitelist only
DAILY_TREND_FILTER = True   # True = block buys when trend DOWN
SWING_CONFLUENCE = True     # True = VOL+ADX only, False = old RSI+MACD+all

# These should already exist from Phase 2+3, just verify they're all present
```

### 8.2 Wrap old logic with flags
```python
# In signal pipeline:
if SCALPING_MODE:
    # Old 30m scalping logic (RSI, MACD, Stoch, EMA cross, VWAP)
    confluence = old_confluence_scoring(...)
    stop = fixed_percentage_stop(0.5)
    target = fixed_rr_target(1.5)
elif SWING_MODE:
    # New daily swing logic (VOL, ADX only)
    confluence = swing_confluence(...)  # Phase 5
    stop = calculate_swing_stop(...)    # Phase 4
    target = calculate_swing_target(...)  # Phase 4
```

### 8.3 Add flags to API response
```python
# In /dashboard/swing and /dashboard/signals responses:
response['mode'] = 'swing' if SWING_MODE else 'scalping'
response['flags'] = {
    'swing_mode': SWING_MODE,
    'scalping_mode': SCALPING_MODE,
    'whitelist_mode': WHITELIST_MODE,
    'daily_trend_filter': DAILY_TREND_FILTER,
    'swing_confluence': SWING_CONFLUENCE,
}
```

### 8.4 DB-backed toggle (optional, use existing feature_flags table)
```python
# If feature_flags table exists, read from it:
# Otherwise use hardcoded defaults above
try:
    row = db.execute("SELECT value FROM feature_flags WHERE key='SWING_MODE'").fetchone()
    if row:
        SWING_MODE = row[0] == '1' or row[0] == 'true'
except:
    pass  # Use hardcoded default
```

### 8.5 Implementation steps:
1. Verify all flags exist at top of signal_engine.py
2. Wrap any remaining old logic with `if SCALPING_MODE:` guards
3. Add `mode` and `flags` to API responses
4. Optionally integrate with existing feature_flags DB table
5. Test: toggle SWING_MODE=False → verify old behavior returns
6. Toggle back to SWING_MODE=True
7. git commit

**Files:** signal_engine.py, dashboard_api.py

---

## Execution Order

```
Phase 1 → FIRST (critical bug fix)
Phase 7 → SECOND (DB migration, non-breaking)
Phase 8 → THIRD (flags, backward compat)

Each phase → git commit → quick_check → smoke_test
```

## After All Phases Complete:

### signals.html update (claude.ai):
After Claude Code finishes Phase 1 backend:
- Update signals.html tabs to use separate endpoints
- Tab "30 دقيقة" → /dashboard/signals-30m
- Tab "يومي" → /dashboard/signals-daily
