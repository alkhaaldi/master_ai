# Trading Logic Fixes V2 — Master Plan for Claude Code
# Date: 2026-03-27
# Author: claude.ai analysis → Claude Code execution
# Scope: Fix all trading logic bugs + add missing features + update dashboard HTML

---

## OVERVIEW

This plan fixes **10 backend bugs** and adds **5 new features** identified in a full audit of:
- `stock_radar.py` (1118 lines)
- `signal_engine.py` (291 lines)
- `trading_brain.py` (666 lines)
- `journal_engine.py` (433 lines)
- `bridge_client.py` (319 lines)

**Rule: Each fix is atomic. Test after each. Commit after each group.**

---

## PHASE 1 — CRITICAL BUGS (P0)
> These bugs break core functionality. Fix first.

### Fix 1.1: `close_price` → `price` in trading_brain.py
**File:** `trading_brain.py`
**Function:** `_get_current_prices()` (~line 337)
**Bug:** `SELECT symbol, close_price FROM stock_radar_daily WHERE date >= ?`
- Column `close_price` does NOT exist → should be `price`
- Column `date` does NOT exist → should be `updated_at`
**Impact:** Brain evaluation ALWAYS fails → indicator weights never update → brain never learns.

**Fix:**
```python
# In _get_current_prices(), replace the entire try block for radar prices:

# OLD:
rows = conn.execute(
    "SELECT symbol, close_price FROM stock_radar_daily WHERE date >= ? ORDER BY date DESC",
    ((date.today() - timedelta(days=3)).isoformat(),),
).fetchall()
conn.close()
for r in rows:
    if r["symbol"] not in prices:
        prices[r["symbol"]] = r["close_price"]

# NEW:
rows = conn.execute(
    "SELECT symbol, price, updated_at FROM stock_radar_daily ORDER BY updated_at DESC",
).fetchall()
conn.close()
for r in rows:
    if r["symbol"] not in prices and r["price"]:
        prices[r["symbol"]] = float(r["price"])
```

**Test:**
```bash
cd /home/pi/master_ai
venv/bin/python3 -c "
from trading_brain import _get_current_prices
prices = _get_current_prices()
print(f'Got {len(prices)} prices')
for k,v in list(prices.items())[:5]: print(f'  {k}: {v}')
"
```


---

### Fix 1.2: EMA state persistence (memory → DB)
**File:** `stock_radar.py`
**Problem:** `_prev_ema` dict lives in memory. Server restart → lost → first poll cycle misses all crosses.

**Step A — Add columns to stock_radar_state:**
In `init_radar_db()`, add these ALTER TABLE statements (same pattern as existing ones):
```python
for col_sql in [
    "ALTER TABLE stock_radar_state ADD COLUMN prev_ema_fast REAL",
    "ALTER TABLE stock_radar_state ADD COLUMN prev_ema_slow REAL",
]:
    try:
        conn.execute(col_sql)
    except Exception:
        pass
```

**Step B — Add load function (put before check_symbol):**
```python
def _load_prev_ema():
    """Load previous EMA values from DB (survives restart)."""
    global _prev_ema
    try:
        conn = _db()
        rows = conn.execute(
            "SELECT symbol, prev_ema_fast, prev_ema_slow FROM stock_radar_state "
            "WHERE timeframe='30m' AND prev_ema_fast IS NOT NULL"
        ).fetchall()
        conn.close()
        for r in rows:
            _prev_ema[r["symbol"]] = (float(r["prev_ema_fast"]), float(r["prev_ema_slow"]))
        logger.info(f"Loaded {len(_prev_ema)} prev EMA states from DB")
    except Exception as e:
        logger.warning(f"Failed to load prev EMA: {e}")
```

**Step C — Call it in radar_loop:**
In `radar_loop()`, right after `init_radar_db()`:
```python
async def radar_loop(send_fn):
    init_radar_db()
    _load_prev_ema()  # ← ADD THIS LINE
    logger.info("Stock radar loop started")
```

**Step D — Save EMA after each check_symbol:**
At the end of `check_symbol()`, before `return`, add:
```python
    # Persist EMA state for restart survival
    try:
        conn = _db()
        conn.execute("""
            INSERT OR REPLACE INTO stock_radar_state
            (symbol, exchange, timeframe, fast_len, slow_len, prev_ema_fast, prev_ema_slow, updated_at)
            VALUES (?, 'KSE', '30m', 9, 21, ?, ?, ?)
        """, (ticker, ema_f, ema_s, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
    except Exception:
        pass
    
    return { ... }  # existing return dict
```

**Test:**
```bash
venv/bin/python3 -c "
from stock_radar import init_radar_db, _load_prev_ema, _prev_ema
init_radar_db()
_load_prev_ema()
print(f'Loaded {len(_prev_ema)} EMA states')
"
```


---

### Fix 1.3: Daily EMA Cross → actual cross detection
**File:** `stock_radar.py` → `refresh_daily_snapshot()`
**Problem:** Current logic says `if ema9 > ema21: daily_ema_cross = "bullish"`. This is DIRECTION not CROSS.
Cross = was below and now above. Direction = currently above.

**Fix:** Before the symbol loop in `refresh_daily_snapshot()`, load previous EMA + MACD values:
```python
        # Load previous daily EMA and MACD values for cross detection
        conn_prev = _db()
        prev_daily_ema = {}
        prev_daily_macd = {}
        for row in conn_prev.execute("SELECT symbol, ema_fast, ema_slow, macd, macd_signal FROM stock_radar_daily").fetchall():
            if row["ema_fast"] and row["ema_slow"]:
                prev_daily_ema[row["symbol"]] = (float(row["ema_fast"]), float(row["ema_slow"]))
            if row["macd"] is not None and row["macd_signal"] is not None:
                prev_daily_macd[row["symbol"]] = (float(row["macd"]), float(row["macd_signal"]))
        conn_prev.close()
```

Then inside the per-symbol loop, replace the EMA direction/cross logic:
```python
                prev_f, prev_s = prev_daily_ema.get(sym, (None, None))
                
                if ema9 and ema21:
                    # Direction (always set)
                    if ema9 > ema21:
                        trend_ar = "\u0635\u0627\u0639\u062f"
                    elif ema9 < ema21:
                        trend_ar = "\u0647\u0627\u0628\u0637"
                    else:
                        trend_ar = "\u0645\u062d\u0627\u064a\u062f"
                    
                    # Cross detection (requires previous data)
                    if prev_f is not None and prev_s is not None:
                        if prev_f <= prev_s and ema9 > ema21:
                            daily_ema_cross = "bullish"
                            daily_signal = "bullish_cross"
                        elif prev_f >= prev_s and ema9 < ema21:
                            daily_ema_cross = "bearish"
                            daily_signal = "bearish_cross"
                        else:
                            daily_ema_cross = "none"
                            daily_signal = None
                    else:
                        # No previous data — direction as fallback label, no signal
                        daily_ema_cross = "bullish" if ema9 > ema21 else "bearish" if ema9 < ema21 else "none"
                        daily_signal = None
                else:
                    trend_ar = "\u0645\u062d\u0627\u064a\u062f"
                    daily_ema_cross = "none"
                    daily_signal = None
```

Also fix MACD cross in same loop (Fix 2.2 combined here):
```python
                prev_m, prev_ms = prev_daily_macd.get(sym, (None, None))
                if prev_m is not None and prev_ms is not None:
                    prev_hist = prev_m - prev_ms
                    curr_hist = macd_val - macd_sig
                    if prev_hist <= 0 and curr_hist > 0:
                        macd_cross = "bullish"
                    elif prev_hist >= 0 and curr_hist < 0:
                        macd_cross = "bearish"
                    else:
                        macd_cross = "none"
                else:
                    macd_cross = "bullish" if macd_val > macd_sig else "bearish" if macd_val < macd_sig else "none"
```

**Test:**
```bash
venv/bin/python3 -c "
from stock_radar import refresh_daily_snapshot
# Note: Bridge must be running for this test
r = refresh_daily_snapshot()
print(r)
"
```

**Commit Phase 1:**
```bash
git add trading_brain.py stock_radar.py
git commit -m 'fix(P0): close_price->price in brain, EMA persistence, daily cross detection'
```


---

## PHASE 2 — IMPORTANT BUGS (P1)

### Fix 2.1: Unify Confluence Scoring
**File:** `stock_radar.py`
**Problem:** Two different confluence calculations:
1. `stock_radar._compute_confluence()` — fixed weights
2. `trading_brain.get_adjusted_confluence()` — adaptive weights
Same symbol can get different scores from different callers.

**Fix:** Make `_compute_confluence` try brain weights first, fallback to fixed:

Rename existing `_compute_confluence` → `_compute_confluence_fixed`.
Add new `_compute_confluence` wrapper:
```python
def _compute_confluence(signal_30m, daily_data):
    """Multi-timeframe confluence scoring. Uses brain weights if available."""
    try:
        from trading_brain import get_indicator_weights
        weights = get_indicator_weights()
        if weights and any(w != 1.0 for w in weights.values()):
            return _compute_confluence_weighted(signal_30m, daily_data, weights)
    except Exception:
        pass
    return _compute_confluence_fixed(signal_30m, daily_data)
```

Add `_compute_confluence_weighted()` — same logic as `_compute_confluence_fixed` but multiplies each component by the brain weight for that indicator category:
- EMA components × `weights.get("ema", 1.0)`
- MACD components × `weights.get("macd", 1.0)`
- RSI components × `weights.get("rsi", 1.0)`
- Volume components × `weights.get("vol", 1.0)`

Return dict adds `"brain_weighted": True`.

---

### Fix 2.2: MACD Cross (already included in Fix 1.3 above)
Already handled in Phase 1 Fix 1.3.

---

### Fix 2.3: Remove OBV duplicate from brain
**File:** `trading_brain.py`

**Step A:** Remove "obv" from INDICATORS:
```python
INDICATORS = ["rsi", "macd", "ema", "adx", "vol", "stoch"]  # removed "obv"
```

**Step B:** In `snapshot_signals()`, remove `ind_obv` from the INSERT statement and values.
Remove the line:
```python
1 if (sig.get("vol_ratio") or 0) > 1.2 else 0,  # OBV proxy via vol_ratio
```

**Step C:** In `get_adjusted_confluence()`, remove "obv" from votes dict:
```python
votes = {
    "rsi": 1 if (signal_data.get("rsi_14") or 0) > 50 else 0,
    "macd": 1 if signal_data.get("macd_state") == "bullish" else 0,
    "ema": 1 if signal_data.get("ema_state") == "bullish" else 0,
    "adx": 1 if (signal_data.get("adx") or 0) > 25 else 0,
    "vol": 1 if (signal_data.get("vol_ratio") or 0) > 1.0 else 0,
    "stoch": 1 if (signal_data.get("stoch_k") or 0) > 50 else 0,
    # "obv" removed — was duplicate of vol
}
```

**Note:** The `ind_obv` column stays in DB (backward compatible), just won't be populated anymore.

**Commit Phase 2:**
```bash
git add stock_radar.py trading_brain.py
git commit -m 'fix(P1): unify confluence scoring, remove OBV duplicate'
```


---

## PHASE 3 — NEW FEATURES (P2)

### Feature 3.1: Stop Loss Alert in signal_engine
**File:** `signal_engine.py` → `build_signals()`
At the end, after building `open_positions`, add:
```python
    # 9. Stop Loss alerts for open positions
    for pos in result["open_positions"]:
        trade_data = open_syms.get(pos["symbol"], {})
        stop = trade_data.get("stop_loss")
        if stop and pos["current"] and float(pos["current"]) <= float(stop):
            pos["stop_hit"] = True
            pos["stop_alert"] = f"\u26a0\ufe0f {pos['symbol']} \u0648\u0635\u0644 \u0627\u0644\u0633\u062a\u0648\u0628 {stop}! \u0627\u0644\u0633\u0639\u0631: {pos['current']}"
        else:
            pos["stop_hit"] = False
            pos["stop_alert"] = None
```

---

### Feature 3.2: Market Regime Filter
**File:** `stock_radar.py` — add function + integrate

Add helper:
```python
def _detect_market_regime(adx):
    """Detect market regime from ADX value."""
    if adx is None:
        return "unknown"
    if adx >= 25:
        return "trending"
    elif adx <= 20:
        return "ranging"
    return "transition"
```

In `_compute_confluence_fixed()` (and `_compute_confluence_weighted()`), add regime awareness:
```python
    # Regime adjustment
    adx = daily_data.get("adx")
    regime = _detect_market_regime(adx)
    if regime == "ranging":
        # Reduce EMA weight in ranging market (more false crosses)
        score = int(score * 0.7) if abs(score) > 20 else score
        reasons.append("\u0633\u0648\u0642 \u0639\u0631\u0636\u064a (ADX<20)")
    elif regime == "trending" and abs(score) > 30:
        score = int(score * 1.15)
        reasons.append("\u0633\u0648\u0642 \u0627\u062a\u062c\u0627\u0647\u064a (ADX>25)")
```

---

### Feature 3.3: ATR Trailing Stop Suggestion
**File:** `journal_engine.py` — add function

```python
def suggest_trailing_stop(trade_id, atr_multiplier=2.0):
    """Suggest trailing stop based on ATR from daily snapshot."""
    trade = get_trade(trade_id)
    if not trade or trade["status"] != "open":
        return None
    sym = trade["symbol"]
    try:
        conn = sqlite3.connect(DB_PATH, timeout=3)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT atr, price FROM stock_radar_daily WHERE symbol=?", (sym,)
        ).fetchone()
        conn.close()
    except Exception:
        return None
    if not row or not row["atr"]:
        return None
    atr = float(row["atr"])
    current_price = float(row["price"])
    if trade["direction"] == "long":
        trailing_stop = round(current_price - (atr * atr_multiplier), 3)
    else:
        trailing_stop = round(current_price + (atr * atr_multiplier), 3)
    return {
        "trade_id": trade_id,
        "symbol": sym,
        "current_price": current_price,
        "atr": round(atr, 3),
        "multiplier": atr_multiplier,
        "suggested_stop": trailing_stop,
        "distance_pct": round(abs(current_price - trailing_stop) / current_price * 100, 2),
    }
```

---

### Feature 3.4: Post-market daily refresh timing
**File:** `stock_radar.py` → replace `_daily_snapshot_is_fresh()`

```python
def _daily_snapshot_is_fresh():
    """Daily snapshot is fresh if updated after today's market close (12:40 KWT)."""
    conn = _db()
    try:
        row = conn.execute(
            "SELECT MAX(updated_at) as last_update FROM stock_radar_daily"
        ).fetchone()
    except Exception:
        return False
    finally:
        conn.close()
    if not row or not row["last_update"]:
        return False
    try:
        last = datetime.fromisoformat(row["last_update"])
        kwt_now = datetime.utcnow() + timedelta(hours=3)
        kwt_last = last + timedelta(hours=3)
        # Fresh if updated today after market close
        if kwt_last.date() == kwt_now.date() and (kwt_last.hour > 12 or (kwt_last.hour == 12 and kwt_last.minute >= 40)):
            return True
        # Also fresh within 4 hours (manual refresh fallback)
        if (datetime.utcnow() - last).total_seconds() < 4 * 3600:
            return True
        return False
    except Exception:
        return False
```

**Commit Phase 3:**
```bash
git add signal_engine.py stock_radar.py journal_engine.py
git commit -m 'feat: stop loss alerts, market regime, ATR trailing stop, daily timing'
```


---

## PHASE 4 — NEW API ENDPOINTS (Claude Code)

### 4.1: GET `/dashboard/regime` — NEW endpoint
**File:** `dashboard_api.py` (or `server.py` if dashboard_api doesn't exist as separate)

```python
@app.get("/dashboard/regime")
async def dashboard_regime():
    """Market regime analysis per symbol."""
    from stock_radar import get_daily_snapshot
    snapshot = get_daily_snapshot(top_n=None, min_score=0)
    regimes = {}
    for s in snapshot:
        adx = s.get("adx")
        if adx and adx >= 25:
            regime = "trending"
        elif adx and adx <= 20:
            regime = "ranging"
        else:
            regime = "transition"
        regimes[s["symbol"]] = {
            "regime": regime,
            "regime_ar": "\u0627\u062a\u062c\u0627\u0647\u064a" if regime == "trending" else "\u0639\u0631\u0636\u064a" if regime == "ranging" else "\u0627\u0646\u062a\u0642\u0627\u0644\u064a",
            "adx": round(adx, 1) if adx else None,
            "atr": s.get("atr"),
            "trend": s.get("trend"),
        }
    trending = sum(1 for r in regimes.values() if r["regime"] == "trending")
    ranging = sum(1 for r in regimes.values() if r["regime"] == "ranging")
    return {
        "regimes": regimes,
        "summary": {
            "trending": trending,
            "ranging": ranging,
            "transition": len(regimes) - trending - ranging,
            "total": len(regimes),
        }
    }
```

### 4.2: Update positions endpoint to include stop alerts + trailing stop
In the positions endpoint (wherever it builds the positions list), add:
```python
from journal_engine import suggest_trailing_stop
for pos in positions:
    # ATR trailing stop suggestion
    if pos.get("id"):
        ts = suggest_trailing_stop(pos["id"])
        if ts:
            pos["trailing_stop"] = ts["suggested_stop"]
            pos["atr"] = ts["atr"]
            pos["trailing_distance_pct"] = ts["distance_pct"]
```

### 4.3: Verify `/dashboard/brain` works after Fix 1.1
```bash
curl -s -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000/dashboard/brain | python3 -m json.tool | head -30
```
Should show `indicator_weights` with actual weight values, not all 1.0.

**Commit Phase 4:**
```bash
git add dashboard_api.py server.py
git commit -m 'feat: regime endpoint, positions stop+trailing, brain verification'
```


---

## PHASE 5 — TESTING & FINAL RESTART

### After ALL phases, run full test suite:
```bash
cd /home/pi/master_ai
venv/bin/python3 _tools/quick_check.py
venv/bin/python3 _tools/smoke_test.py
venv/bin/python3 _tools/db_sanity.py
bash _tools/restart_master_ai.sh
```

### Verify key endpoints:
```bash
KEY=$(cat ~/.master_ai_key)
echo "=== Health ==="
curl -s -H "X-API-Key: $KEY" http://localhost:9000/health | python3 -m json.tool

echo "=== Brain ==="
curl -s -H "X-API-Key: $KEY" http://localhost:9000/dashboard/brain | python3 -m json.tool | head -20

echo "=== Regime ==="
curl -s -H "X-API-Key: $KEY" http://localhost:9000/dashboard/regime | python3 -m json.tool | head -20

echo "=== Signals ==="
curl -s -H "X-API-Key: $KEY" http://localhost:9000/dashboard/signals | python3 -m json.tool | head -20
```

---

## SUMMARY TABLE

| # | Fix/Feature | File(s) | Type | Phase |
|---|------------|---------|------|-------|
| 1.1 | close_price → price | trading_brain.py | Bug | P1 |
| 1.2 | EMA state persistence | stock_radar.py | Bug | P1 |
| 1.3 | Daily EMA+MACD cross | stock_radar.py | Bug | P1 |
| 2.1 | Unify confluence | stock_radar.py | Bug | P2 |
| 2.2 | MACD actual cross | stock_radar.py | Bug | P1* |
| 2.3 | Remove OBV duplicate | trading_brain.py | Bug | P2 |
| 3.1 | Stop Loss alerts | signal_engine.py | Feature | P3 |
| 3.2 | Market Regime filter | stock_radar.py | Feature | P3 |
| 3.3 | ATR Trailing Stop | journal_engine.py | Feature | P3 |
| 3.4 | Post-market timing | stock_radar.py | Feature | P3 |
| 4.1 | Regime endpoint | dashboard_api.py | Feature | P4 |
| 4.2 | Positions stop+trail | dashboard_api.py | Feature | P4 |

*Fix 2.2 is combined with Fix 1.3

---

## DASHBOARD HTML UPDATES (claude.ai handles AFTER Claude Code finishes)

After all backend fixes are deployed, claude.ai will update these HTML pages:

### brain.html:
- Indicator weights visual bars (7→6 indicators)
- Hit rate per indicator with color coding
- Recent evaluations table with outcome (hit/miss/expired)
- Brain health indicator: "learning active" vs "insufficient data"
- Weekly report summary card

### signals.html:
- Market regime badge per symbol: 🟢 اتجاهي / 🟡 انتقالي / 🔴 عرضي
- Distinguish cross vs direction in EMA column
- Confluence source label: "⚡ brain" or "📊 fixed"
- Add ADX column to indicator matrix

### positions.html:
- Stop loss column with distance % and color (green=safe, amber=near, red=hit)
- ATR trailing stop suggestion with "update stop" button
- Stop hit alert: red flash banner at top
- P&L with broker fees (already exists, verify)

### radar.html:
- Regime column (trending/ranging/transition)
- EMA persistence status icon (has prev data? ✅/⚠️)
- Last refresh timestamp with staleness indicator
- Regime summary bar at top: "X trending, Y ranging, Z transition"

### home.html:
- Add "brain pulse" widget: hit rate trend arrow
- Add "market regime" summary: trending/ranging split
- Stop loss alerts bubble (count of positions near stop)

---

## HOW TO EXECUTE

1. File is already at: `/home/pi/master_ai/_tools/TRADING_LOGIC_FIXES_V2.md`

2. Tell Claude Code:
   ```
   اقرأ _tools/TRADING_LOGIC_FIXES_V2.md ونفذ Phase 1 أولاً (fixes 1.1, 1.2, 1.3)
   اختبر كل fix بالأمر المكتوب
   ثم Phase 2 (fixes 2.1, 2.3)
   ثم Phase 3 (features 3.1-3.4)
   ثم Phase 4 (endpoints 4.1-4.2)
   وأخيراً Phase 5 (testing + restart)
   ```

3. After Claude Code reports success, come back to claude.ai for dashboard HTML updates.
