# Brain Historical Backfill + Smart Learning — خطة Claude Code
# Date: 2026-03-27
# Author: claude.ai (analysis + design) → Claude Code (execution)
# Scope: Backfill brain with 1yr historical data + Bayesian smoothing + regime-aware weights

---

## الهدف

بدل ما الـ Brain ينتظر أسابيع يجمع 30 إشارة، نستخدم البيانات التاريخية
من Bridge API (حتى 300 bar يومي = ~سنة) لتعبئة `signal_snapshots` بمئات
الإشارات المقيّمة فوراً. ثم نرقّي نظام التعلم بـ Bayesian smoothing و
regime-aware weights.

---

## PHASE 1 — Historical Backfill Script

### ملف جديد: `brain_backfill.py`
### المكان: `/home/pi/master_ai/brain_backfill.py`

### المنطق:

```
لكل سهم في watchlist (128 سهم):
  1. اسحب 300 bar يومي من Bridge API: GET /analysis?symbol=X&interval=1D&bars=300
  2. من الـ response.bars[] (مصفوفة 300 bar مع كل المؤشرات محسوبة):
     - امشِ bar-by-bar من bar[60] إلى bar[-8] (نترك أول 60 للـ warm-up وآخر 7 للتقييم)
     - لكل bar[i]:
       a. اقرأ المؤشرات: rsi_14, macd, macd_signal, macd_hist, ema_9, ema_20, ema_50, adx, vol_ratio, stoch_k, bb_squeeze, atr_14
       b. احسب confluence بنفس منطق signal_engine:
          - ind_rsi = 1 if rsi > 50 else 0
          - ind_macd = 1 if macd_hist > 0 else 0
          - ind_ema = 1 if ema_9 > ema_20 else 0  (أو ema_20 > ema_50)
          - ind_adx = 1 if adx > 25 else 0
          - ind_vol = 1 if vol_ratio > 1.0 else 0
          - ind_stoch = 1 if stoch_k > 50 else 0
          - confluence_score = (bullish_count / 6) * 100
       c. لو confluence >= 50:
          - سجّل snapshot في signal_snapshots مع source='historical_backfill'
          - قيّم فوراً: شوف bars[i+1] إلى bars[i+7]
            * max_gain = max(bar.high for bar in bars[i+1:i+8]) - bars[i].close
            * max_loss = bars[i].close - min(bar.low for bar in bars[i+1:i+8])
            * max_gain_pct = (max_gain / bars[i].close) * 100
            * max_loss_pct = (max_loss / bars[i].close) * 100
            * hit_threshold = max(atr_14 * 0.5, bars[i].close * 0.03)
            * outcome:
              - "hit" if max_gain >= hit_threshold and max_loss < hit_threshold
              - "miss" if max_loss >= hit_threshold and max_gain < hit_threshold
              - "expired" if neither hit nor miss
              - "ambiguous" if both hit and miss (هذا يصير بالـ daily bars)
          - سجّل price_7d = bars[i+7].close
          - سجّل outcome_pct = ((bars[i+7].close - bars[i].close) / bars[i].close) * 100
```

### Important: dedup
قبل INSERT → شيك:
```sql
SELECT id FROM signal_snapshots
WHERE symbol=? AND source='historical_backfill'
AND date(signal_time)=date(?)
```
لو موجود → skip (لا تكرر)

### Important: لا look-ahead
- المؤشرات في bar[i] محسوبة من Bridge على بيانات حتى i فقط ✅
  (Bridge يحسب RSI/MACD/EMA بشكل rolling — كل bar فيه مؤشرات حتى ذلك اليوم)
- التقييم يستخدم bars[i+1:i+8] فقط ✅
- ما نستخدم support/resistance المحسوبة على كل الفترة (نتجاهلها بالـ backfill)

### الكود المطلوب:

```python
"""
brain_backfill.py — Historical backfill for Trading Brain.
Fetches 1yr daily bars from Bridge API, generates signal snapshots,
evaluates outcomes immediately (since future is known), and stores
in signal_snapshots with source='historical_backfill'.
"""
import os
import sys
import json
import time
import sqlite3
import logging
import requests
from datetime import datetime, timedelta

logger = logging.getLogger("brain_backfill")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")
BRIDGE_URL = "http://192.168.111.158:8059"
EVAL_DAYS = 7
MIN_WARMUP = 60  # skip first 60 bars (indicator warm-up)
MIN_CONFLUENCE = 50

def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c

def _fetch_daily_bars(symbol, bars=300):
    """Fetch daily bars with indicators from Bridge API."""
    try:
        r = requests.get(
            f"{BRIDGE_URL}/analysis",
            params={"symbol": symbol, "exchange": "KSE", "interval": "1D", "bars": bars},
            timeout=60
        )
        if r.status_code != 200:
            return None
        data = r.json()
        return data.get("bars", [])
    except Exception as e:
        logger.warning(f"Bridge fetch failed for {symbol}: {e}")
        return None

def _compute_snapshot(bar):
    """Compute indicator votes and confluence from a single bar."""
    rsi = bar.get("rsi_14") or 0
    macd_hist = bar.get("macd_hist") or 0
    ema9 = bar.get("ema_9") or 0
    ema20 = bar.get("ema_20") or 0
    ema50 = bar.get("ema_50") or 0
    adx = bar.get("adx") or 0
    vol_ratio = bar.get("vol_ratio") or 0
    stoch_k = bar.get("stoch_k") or 0
    bb_squeeze = bar.get("bb_squeeze") or False
    atr = bar.get("atr_14") or 0

    # Indicator votes (same logic as signal_engine)
    ind_rsi = 1 if rsi > 50 else 0
    ind_macd = 1 if macd_hist > 0 else 0
    ind_ema = 1 if ema9 > ema20 > 0 else 0
    ind_adx = 1 if adx > 25 else 0
    ind_vol = 1 if vol_ratio > 1.0 else 0
    ind_stoch = 1 if stoch_k > 50 else 0

    bullish = ind_rsi + ind_macd + ind_ema + ind_adx + ind_vol + ind_stoch
    confluence = int(round((bullish / 6) * 100))

    # EMA stack state
    if ema9 > ema20 > ema50 > 0:
        ema_state = "bullish"
    elif ema9 < ema20 < ema50 and ema50 > 0:
        ema_state = "bearish"
    else:
        ema_state = "mixed"

    macd_state = "bullish" if macd_hist > 0 else "bearish"
    macd_momentum = "accelerating" if abs(macd_hist) > abs(bar.get("macd", 0) or 0) * 0.1 else "decelerating"

    # Verdict
    if confluence >= 70 and "bullish" in ema_state:
        verdict_key = "buy"
        verdict = "شراء"
    elif confluence >= 50:
        verdict_key = "watch"
        verdict = "مراقبة"
    elif confluence < 30:
        verdict_key = "avoid"
        verdict = "تجنب"
    else:
        verdict_key = "neutral"
        verdict = "حياد"

    # Trade state (simplified for backfill)
    if confluence >= 60 and vol_ratio > 1.2:
        trade_state = "ready"
    elif confluence >= 50:
        trade_state = "setup"
    else:
        trade_state = "discovery"

    # EMA cross detection
    ema_cross_type = None
    # We don't detect cross in backfill (would need previous bar comparison)
    # Leave as None — not critical for backfill

    # RSI divergence (simplified)
    rsi_divergence = None
    if rsi < 30:
        rsi_divergence = "oversold"
    elif rsi > 70:
        rsi_divergence = "overbought"

    return {
        "confluence": confluence,
        "trade_state": trade_state,
        "verdict": verdict,
        "verdict_key": verdict_key,
        "rsi_14": round(rsi, 2) if rsi else None,
        "macd_state": macd_state,
        "macd_momentum": macd_momentum,
        "ema_state": ema_state,
        "adx": round(adx, 1) if adx else None,
        "vol_ratio": round(vol_ratio, 2) if vol_ratio else None,
        "stoch_k": round(stoch_k, 1) if stoch_k else None,
        "bb_squeeze": 1 if bb_squeeze else 0,
        "rsi_divergence": rsi_divergence,
        "ema_cross_type": ema_cross_type,
        "ema_cross_bars_ago": None,
        "atr_14": round(atr, 3) if atr else None,
        "ind_rsi": ind_rsi,
        "ind_macd": ind_macd,
        "ind_ema": ind_ema,
        "ind_adx": ind_adx,
        "ind_vol": ind_vol,
        "ind_stoch": ind_stoch,
        "price": bar.get("close", 0),
        "support": None,  # skip for backfill (look-ahead risk)
        "resistance": None,
    }

def _evaluate_outcome(bars, idx, snapshot):
    """Evaluate outcome using bars[idx+1:idx+8] (7 days forward)."""
    price_at = snapshot["price"]
    atr = snapshot["atr_14"] or price_at * 0.03
    if not price_at or price_at <= 0:
        return None

    future = bars[idx+1:idx+1+EVAL_DAYS]
    if len(future) < EVAL_DAYS:
        return None  # not enough future bars

    max_high = max(b.get("high", 0) for b in future)
    min_low = min(b.get("low", 999999) for b in future)
    price_7d = future[-1].get("close", price_at)

    max_gain_pct = ((max_high - price_at) / price_at) * 100
    max_loss_pct = ((price_at - min_low) / price_at) * 100
    outcome_pct = ((price_7d - price_at) / price_at) * 100

    hit_threshold_pct = max((atr * 0.5 / price_at) * 100, 3.0)

    verdict_key = snapshot["verdict_key"]
    if verdict_key in ("buy", "watch"):
        if max_gain_pct >= hit_threshold_pct and max_loss_pct < hit_threshold_pct:
            outcome = "hit"
        elif max_loss_pct >= hit_threshold_pct and max_gain_pct < hit_threshold_pct:
            outcome = "miss"
        elif max_gain_pct >= hit_threshold_pct and max_loss_pct >= hit_threshold_pct:
            outcome = "ambiguous"
        else:
            outcome = "expired"
    elif verdict_key == "avoid":
        if max_loss_pct >= hit_threshold_pct and max_gain_pct < hit_threshold_pct:
            outcome = "hit"
        elif max_gain_pct >= hit_threshold_pct and max_loss_pct < hit_threshold_pct:
            outcome = "miss"
        else:
            outcome = "expired"
    else:
        outcome = "expired"

    return {
        "outcome": outcome,
        "price_7d": round(price_7d, 3),
        "outcome_pct": round(outcome_pct, 2),
        "max_gain_pct": round(max_gain_pct, 2),
        "max_loss_pct": round(max_loss_pct, 2),
    }

def backfill_symbol(symbol, bars=None):
    """Backfill one symbol. Returns {snapshots: N, hits: N, misses: N, ...}"""
    if bars is None:
        bars = _fetch_daily_bars(symbol, 300)
    if not bars or len(bars) < MIN_WARMUP + EVAL_DAYS + 10:
        return {"symbol": symbol, "error": "insufficient_bars", "count": len(bars) if bars else 0}

    conn = _conn()
    stats = {"symbol": symbol, "snapshots": 0, "hit": 0, "miss": 0, "expired": 0, "ambiguous": 0, "skipped": 0}

    for i in range(MIN_WARMUP, len(bars) - EVAL_DAYS):
        bar = bars[i]
        bar_time = bar.get("time", 0)
        if not bar_time:
            continue

        # Convert epoch to datetime
        signal_time = datetime.utcfromtimestamp(bar_time).strftime("%Y-%m-%d %H:%M:%S")
        signal_date = datetime.utcfromtimestamp(bar_time).strftime("%Y-%m-%d")

        # Dedup check
        existing = conn.execute(
            "SELECT id FROM signal_snapshots WHERE symbol=? AND source='historical_backfill' AND date(signal_time)=?",
            (symbol, signal_date)
        ).fetchone()
        if existing:
            stats["skipped"] += 1
            continue

        # Compute snapshot
        snap = _compute_snapshot(bar)
        if snap["confluence"] < MIN_CONFLUENCE:
            continue

        # Evaluate outcome
        outcome_data = _evaluate_outcome(bars, i, snap)
        if not outcome_data:
            continue

        # Insert
        conn.execute("""
            INSERT INTO signal_snapshots
            (symbol, signal_time, trade_state, verdict, verdict_key, confluence_score,
             price_at_signal, rsi_14, macd_state, macd_momentum, ema_state,
             adx, vol_ratio, stoch_k, bb_squeeze, rsi_divergence,
             ema_cross_type, ema_cross_bars_ago, support, resistance, atr_14,
             ind_rsi, ind_macd, ind_ema, ind_adx, ind_vol, ind_stoch,
             outcome, price_7d, outcome_pct, max_gain_pct, max_loss_pct,
             outcome_evaluated_at, source)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,'historical_backfill')
        """, (
            symbol, signal_time, snap["trade_state"], snap["verdict"], snap["verdict_key"],
            snap["confluence"], snap["price"], snap["rsi_14"], snap["macd_state"],
            snap["macd_momentum"], snap["ema_state"], snap["adx"], snap["vol_ratio"],
            snap["stoch_k"], snap["bb_squeeze"], snap["rsi_divergence"],
            snap["ema_cross_type"], snap["ema_cross_bars_ago"],
            snap["support"], snap["resistance"], snap["atr_14"],
            snap["ind_rsi"], snap["ind_macd"], snap["ind_ema"],
            snap["ind_adx"], snap["ind_vol"], snap["ind_stoch"],
            outcome_data["outcome"], outcome_data["price_7d"], outcome_data["outcome_pct"],
            outcome_data["max_gain_pct"], outcome_data["max_loss_pct"],
        ))

        stats["snapshots"] += 1
        stats[outcome_data["outcome"]] = stats.get(outcome_data["outcome"], 0) + 1

    conn.commit()
    conn.close()
    return stats


def run_full_backfill():
    """Run backfill for all watchlist symbols."""
    from stock_radar import get_watchlist
    wl = get_watchlist()
    symbols = [w["symbol"] for w in wl]
    if not symbols:
        logger.warning("Empty watchlist — nothing to backfill")
        return {"total": 0, "symbols": []}

    logger.info(f"Starting backfill for {len(symbols)} symbols...")
    all_stats = []
    total_snapshots = 0
    total_hits = 0

    for idx, sym in enumerate(symbols):
        logger.info(f"[{idx+1}/{len(symbols)}] Backfilling {sym}...")
        stats = backfill_symbol(sym)
        all_stats.append(stats)
        total_snapshots += stats.get("snapshots", 0)
        total_hits += stats.get("hit", 0)

        # Pace: avoid hammering Bridge
        time.sleep(0.5)

    logger.info(f"Backfill complete: {total_snapshots} snapshots, {total_hits} hits")

    # After backfill, update indicator performance
    from trading_brain import update_indicator_performance, adjust_weights
    update_indicator_performance()
    adjust_weights()
    logger.info("Indicator performance updated + weights adjusted")

    return {
        "total_symbols": len(symbols),
        "total_snapshots": total_snapshots,
        "total_hits": total_hits,
        "symbols": all_stats,
    }


if __name__ == "__main__":
    result = run_full_backfill()
    print(json.dumps(result, default=str, indent=2))
```

### Test:
```bash
cd /home/pi/master_ai
# Test with one symbol first:
venv/bin/python3 -c "
from brain_backfill import backfill_symbol
import json
result = backfill_symbol('CLEANING')
print(json.dumps(result, indent=2))
"
# Should show: {"symbol": "CLEANING", "snapshots": 50+, "hit": X, "miss": Y, ...}
```

### Full run:
```bash
venv/bin/python3 brain_backfill.py
# Takes ~5-10 min for 128 symbols
```



---

## PHASE 2 — Bayesian Smoothing for Hit Rates

### ملف: `trading_brain.py` — تعديل `update_indicator_performance()`

### المشكلة الحالية:
```python
hit_rate = hits / total  # 3/4 = 75% ← غير موثوق من عينة صغيرة
```

### الحل: Bayesian Beta-Binomial Smoothing
```python
def _bayesian_hit_rate(hits, total, alpha=5, beta=5):
    """Bayesian smoothed hit rate. Prior = Beta(5,5) = 50% with moderate confidence."""
    return (hits + alpha) / (total + alpha + beta)
```

### التعديل في `update_indicator_performance()`:
استبدل:
```python
hit_rate = hits / total if total > 0 else 0.5
rolling_hr = rolling_hits / rolling_total if rolling_total > 0 else 0.5
```

بـ:
```python
hit_rate = _bayesian_hit_rate(hits, total)
rolling_hr = _bayesian_hit_rate(rolling_hits, rolling_total)
```

### التأثير:
- 3 hits من 4 = 0.571 بدل 0.75 (أكثر واقعية)
- 30 hits من 50 = 0.583 (قريب من الحقيقي 0.6)
- 0 hits من 0 = 0.5 (neutral prior بدل 0)

### Test:
```python
assert abs(_bayesian_hit_rate(3, 4) - 0.571) < 0.01
assert abs(_bayesian_hit_rate(30, 50) - 0.583) < 0.01
assert abs(_bayesian_hit_rate(0, 0) - 0.5) < 0.01
```

---

## PHASE 3 — Regime-Aware Indicator Performance

### ملف: `trading_brain.py` — إضافة جدول + منطق جديد

### جدول جديد: `indicator_regime_stats`
```sql
CREATE TABLE IF NOT EXISTS indicator_regime_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator_name TEXT NOT NULL,
    regime TEXT NOT NULL,  -- 'trending', 'ranging', 'transition'
    total_signals INTEGER DEFAULT 0,
    total_hits INTEGER DEFAULT 0,
    smoothed_rate REAL DEFAULT 0.5,
    last_updated TIMESTAMP,
    UNIQUE(indicator_name, regime)
);
```

### منطق التحديث:
بعد evaluate كل snapshot:
1. حدد regime من ADX: >=25=trending, <=20=ranging, else=transition
2. لكل indicator، حدّث stats حسب الـ regime

```python
def update_regime_stats():
    """Update indicator performance per market regime."""
    conn = _conn()
    evaluated = conn.execute(
        "SELECT * FROM signal_snapshots WHERE outcome IN ('hit','miss') ORDER BY signal_time DESC"
    ).fetchall()
    conn.close()

    if not evaluated:
        return

    from collections import defaultdict
    stats = defaultdict(lambda: {"hits": 0, "total": 0})

    for row in evaluated:
        adx = row["adx"] or 0
        regime = "trending" if adx >= 25 else "ranging" if adx <= 20 else "transition"

        for ind in INDICATORS:
            col = f"ind_{ind}"
            vote = row[col]
            is_hit = row["outcome"] == "hit"
            correct = (vote == 1 and is_hit) or (vote == 0 and not is_hit)

            key = (ind, regime)
            stats[key]["total"] += 1
            if correct:
                stats[key]["hits"] += 1

    conn = _conn()
    for (ind, regime), val in stats.items():
        smoothed = _bayesian_hit_rate(val["hits"], val["total"])
        conn.execute("""
            INSERT OR REPLACE INTO indicator_regime_stats
            (indicator_name, regime, total_signals, total_hits, smoothed_rate, last_updated)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (ind, regime, val["total"], val["hits"], round(smoothed, 4)))
    conn.commit()
    conn.close()
```

### استخدامها في `get_adjusted_confluence()`:
```python
def get_adjusted_confluence(signal_data: dict) -> dict:
    """Use regime-aware weights if available, fallback to global weights."""
    adx = signal_data.get("adx") or 0
    regime = "trending" if adx >= 25 else "ranging" if adx <= 20 else "transition"

    # Try regime-specific weights first
    regime_weights = _get_regime_weights(regime)
    if regime_weights:
        weights = regime_weights
    else:
        weights = get_indicator_weights()  # fallback to global

    # ... rest of existing logic using weights ...
```

```python
def _get_regime_weights(regime):
    """Get weights tuned for a specific regime."""
    conn = _conn()
    rows = conn.execute(
        "SELECT indicator_name, smoothed_rate FROM indicator_regime_stats WHERE regime=?",
        (regime,)
    ).fetchall()
    conn.close()
    if len(rows) < len(INDICATORS):
        return None  # not enough data for this regime
    weights = {}
    for r in rows:
        # Convert smoothed_rate to weight: 0.5 + smoothed_rate
        weights[r["indicator_name"]] = round(0.5 + r["smoothed_rate"], 3)
    return weights
```

### Test:
```bash
venv/bin/python3 -c "
from trading_brain import update_regime_stats, _get_regime_weights
update_regime_stats()
for regime in ['trending', 'ranging', 'transition']:
    w = _get_regime_weights(regime)
    print(f'{regime}: {w}')
"
```



---

## PHASE 4 — Recency Decay for Weights

### المشكلة:
بيانات السنة الماضية لها نفس وزن بيانات الأسبوع الماضي.
السوق يتغير — البيانات الحديثة أهم.

### الحل: Time-weighted hit rate

في `update_indicator_performance()`, أضف decay:

```python
def _compute_decay_weight(signal_time_str, half_life_days=90):
    """Recent signals weighted more. Half-life = 90 days."""
    try:
        sig_time = datetime.fromisoformat(signal_time_str)
        age_days = (datetime.now() - sig_time).days
        import math
        return math.exp(-0.693 * age_days / half_life_days)  # 0.693 = ln(2)
    except:
        return 0.5
```

استخدامها:
```python
for i, row in enumerate(evaluated):
    decay = _compute_decay_weight(row["signal_time"])
    # ... existing logic ...
    weighted_total += decay
    if correct:
        weighted_hits += decay

weighted_hr = weighted_hits / weighted_total if weighted_total > 0 else 0.5
```

### التأثير:
- إشارة من أمس → weight = 0.99
- إشارة من 90 يوم → weight = 0.50
- إشارة من 180 يوم → weight = 0.25
- إشارة من سنة → weight = 0.06

يعني البيانات التاريخية تساهم بس ما تسيطر.

---

## PHASE 5 — Endpoint: Brain Stats Enhanced

### تعديل `/dashboard/brain` endpoint

أضف للـ response:
```python
# In get_brain_stats():
regime_stats = {}
try:
    conn = _conn()
    rows = conn.execute("SELECT * FROM indicator_regime_stats ORDER BY indicator_name, regime").fetchall()
    conn.close()
    for r in rows:
        ind = r["indicator_name"]
        if ind not in regime_stats:
            regime_stats[ind] = {}
        regime_stats[ind][r["regime"]] = {
            "hits": r["total_hits"],
            "total": r["total_signals"],
            "rate": r["smoothed_rate"],
        }
except:
    pass

# Add to return dict:
return {
    ...existing fields...,
    "regime_stats": regime_stats,
    "backfill_count": _get_backfill_count(),
    "learning_mode": "bayesian_regime_aware",
}

def _get_backfill_count():
    try:
        conn = _conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM signal_snapshots WHERE source='historical_backfill'"
        ).fetchone()
        conn.close()
        return row["cnt"] if row else 0
    except:
        return 0
```

---

## PHASE 6 — Testing & Deployment

### Execution order:
```bash
cd /home/pi/master_ai

# 1. Create brain_backfill.py (Phase 1)
# 2. Test single symbol:
venv/bin/python3 -c "
from brain_backfill import backfill_symbol
import json
r = backfill_symbol('CLEANING')
print(json.dumps(r, indent=2))
"
# Expected: snapshots > 30, hits > 0

# 3. Full backfill (128 symbols, ~5-10 min):
venv/bin/python3 brain_backfill.py
# Expected: total_snapshots > 500

# 4. Apply Bayesian + Regime changes to trading_brain.py (Phase 2+3)
# 5. Apply Decay (Phase 4)

# 6. Update indicator performance with new logic:
venv/bin/python3 -c "
from trading_brain import update_indicator_performance, adjust_weights, update_regime_stats
update_indicator_performance()
update_regime_stats()
w = adjust_weights()
import json
print(json.dumps(w, indent=2))
"
# Expected: weights != all 1.0

# 7. Verify brain dashboard shows data:
KEY=\$(cat ~/.master_ai_key)
curl -s -H "X-API-Key: \$KEY" http://localhost:9000/dashboard/brain | python3 -m json.tool | head -30
# Expected: total_tracked > 500, indicator_weights with real values

# 8. Commit:
git add brain_backfill.py trading_brain.py dashboard_api.py
git commit -m "feat: brain historical backfill + bayesian smoothing + regime-aware weights"
bash _tools/restart_master_ai.sh
```

---

## SUMMARY TABLE

| Phase | What | File | Impact |
|-------|------|------|--------|
| 1 | Historical Backfill script | brain_backfill.py (NEW) | 500+ إشارات فوراً |
| 2 | Bayesian Smoothing | trading_brain.py | أوزان أدق من عينات صغيرة |
| 3 | Regime-Aware Stats | trading_brain.py | أوزان مختلفة trending/ranging |
| 4 | Recency Decay | trading_brain.py | البيانات الحديثة أهم |
| 5 | Enhanced /brain endpoint | dashboard_api.py | الداشبورد يعرض regime stats |
| 6 | Testing & Deploy | — | تحقق كامل |

---

## HOW TO EXECUTE

1. File is at: `/home/pi/master_ai/_tools/BRAIN_BACKFILL_PLAN.md`

2. Tell Claude Code:
```
اقرأ _tools/BRAIN_BACKFILL_PLAN.md ونفذ:
Phase 1: أنشئ brain_backfill.py واختبره على سهم واحد
Phase 2: أضف Bayesian smoothing لـ trading_brain.py
Phase 3: أضف regime-aware stats table + logic
Phase 4: أضف recency decay
Phase 5: حدّث /dashboard/brain endpoint
Phase 6: شغّل الـ full backfill واختبر
```

3. After done, come back to claude.ai to update brain.html dashboard
   (add regime heatmap, backfill count badge, per-regime weight bars)
