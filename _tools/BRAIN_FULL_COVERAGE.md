# Brain Full Coverage — 30m + 1D لكل الأسهم مع أوزان الـ Brain
# Date: 2026-03-27
# Author: claude.ai → Claude Code
# Scope: Fix 3 problems — 30m real data, Brain weights everywhere, all 128 symbols

---

## المشاكل الثلاث

### مشكلة 1: signal_engine يستخدم 1D فقط (حتى لتاب 30m)
`bridge_client.get_analysis()` و `get_multi_analysis()` hardcoded على `interval="1D"`.
يعني تاب "30m الحية" فعلياً يعرض بيانات يومية.

### مشكلة 2: stock_radar.check_symbol (30m) ما يستخدم أوزان الـ Brain
`_compute_score()` فيها أوزان ثابتة (EMA=25, RSI=15, VWAP=15, Vol=20...).
ما تسأل الـ Brain أبداً. نظام scoring مستقل ومنفصل.

### مشكلة 3: signal_engine يغطي 15 سهم فقط
`candidates[:15]` و `wl[:10]` — يعني أغلب الـ 128 سهم ما يظهرون بصفحة الإشارات.

---

## CHANGE 1 — bridge_client يدعم 30m interval

### ملف: `bridge_client.py`

### 1A: أضف method جديد `get_analysis_30m`:
```python
async def get_analysis_30m(self, symbol: str, exchange: str = DEFAULT_EXCHANGE, force: bool = False) -> dict:
    """Get 30m analysis for a symbol."""
    cache_key = f"analysis_30m:{exchange}:{symbol}"
    if not force:
        cached = self._cache_get(cache_key, 60)  # 60s cache for 30m data
        if cached:
            return {**cached, "source": "cache", "stale": False}

    data = await self._request("/analysis", {
        "symbol": symbol, "exchange": exchange,
        "interval": "30m", "bars": 60
    })
    if data:
        normalized = self._normalize_analysis(data)
        normalized["timeframe"] = "30m"
        self._cache_set(cache_key, normalized)
        return {**normalized, "source": "live", "stale": False}

    stale = self._cache_get_stale(cache_key)
    if stale:
        return {**stale, "source": "cache", "stale": True}
    return {"symbol": symbol, "exchange": exchange, "source": "none", "stale": True, "error": "bridge_unreachable"}
```

### 1B: أضف method `get_multi_analysis_30m`:
```python
async def get_multi_analysis_30m(self, symbols: list[str], exchange: str = DEFAULT_EXCHANGE) -> dict:
    """Get 30m analysis for multiple symbols."""
    results = {}
    errors = []
    to_fetch = []

    for sym in symbols:
        cached = self._cache_get(f"analysis_30m:{exchange}:{sym}", 60)
        if cached:
            results[sym] = {**cached, "source": "cache", "stale": False}
            continue
        to_fetch.append(sym)

    BATCH_SIZE = 5
    for i in range(0, len(to_fetch), BATCH_SIZE):
        batch = to_fetch[i:i + BATCH_SIZE]
        data = await self._request("/multi-analysis", {
            "symbols": ",".join(batch),
            "exchange": exchange,
            "interval": "30m",
            "bars": 60,
        })
        if data and "results" in data:
            for item in data["results"]:
                sym = item.get("symbol", "").split(":")[-1]
                normalized = self._normalize_analysis(item)
                normalized["timeframe"] = "30m"
                self._cache_set(f"analysis_30m:{exchange}:{sym}", normalized)
                results[sym] = {**normalized, "source": "live", "stale": False}
        else:
            for sym in batch:
                stale = self._cache_get_stale(f"analysis_30m:{exchange}:{sym}")
                if stale:
                    results[sym] = {**stale, "source": "cache", "stale": True}
                else:
                    errors.append(sym)

    return {
        "bridge_online": self._online,
        "symbols_count": len(results),
        "symbols": results,
        "errors": errors,
        "timeframe": "30m",
    }
```

---

## CHANGE 2 — signal_engine يدعم كل الأسهم + timeframe parameter

### ملف: `signal_engine.py`

### 2A: رفع حد الأسهم من 15 إلى all

في `_get_bridge_data_safe()`:
```python
# OLD:
for item in wl[:10]:        # ← حد 10
symbols = list(candidates)[:15]  # ← حد 15

# NEW:
for item in wl:             # ← كل الـ watchlist
symbols = list(candidates)  # ← كل الأسهم (no limit)
```

**ملاحظة:** Bridge يتعامل مع batches من 5 — لو 128 سهم = 26 batch = ~130 ثانية.
لازم نزيد الـ timeout:
```python
# OLD:
return future.result(timeout=35)

# NEW:
return future.result(timeout=180)  # 3 min for 128 symbols
```

### 2B: أضف `_get_bridge_data_30m_safe()` — version جديدة لـ 30m:
```python
def _get_bridge_data_30m_safe() -> dict:
    """Get bridge 30m analysis for all watchlist symbols."""
    try:
        from bridge_client import get_bridge_client
        import asyncio
        client = get_bridge_client()

        # Get ALL watchlist symbols
        candidates = set()
        for t in _get_open_trades_safe():
            if t.get("symbol"):
                candidates.add(t["symbol"].upper())
        try:
            from stock_radar import get_watchlist
            wl = get_watchlist()
            for item in wl:
                sym = item.get("symbol", "")
                if sym:
                    candidates.add(sym.upper())
        except Exception:
            pass

        if not candidates:
            return {"bridge_online": client._online, "symbols_count": 0, "symbols": {}}

        symbols = list(candidates)

        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, client.get_multi_analysis_30m(symbols))
                return future.result(timeout=180)
        else:
            return asyncio.run(client.get_multi_analysis_30m(symbols))
    except Exception as e:
        logger.warning("Bridge 30m data fetch failed: %s", e)
        return {"bridge_online": False, "symbols_count": 0, "symbols": {}}
```

### 2C: أضف `build_signals_30m()` — function منفصلة لإشارات 30m:
```python
def build_signals_30m() -> dict:
    """Build 30m signals from Bridge — uses Brain weights."""
    now = datetime.now()
    result = {
        "timeframe": "30m",
        "market_open": _is_market_open_safe(),
        "bridge_online": False,
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "signals": [],
        "thresholds": _get_thresholds(),
    }

    bridge_data = _get_bridge_data_30m_safe()
    result["bridge_online"] = bridge_data.get("bridge_online", False)
    bridge_symbols = bridge_data.get("symbols", {})

    open_trades = _get_open_trades_safe()
    open_syms = {t["symbol"].upper(): t for t in open_trades if t.get("symbol")}

    signals = []
    for sym, bd in bridge_symbols.items():
        sym_upper = sym.upper()
        trade = open_syms.get(sym_upper)

        # Use brain confluence (same as 1D)
        confluence = _extract_confluence(bd)
        score = confluence.get("score", 0)
        direction = confluence.get("direction", "")
        regime = confluence.get("regime", "unknown")

        t = _get_thresholds()

        # Trade state using brain thresholds
        if trade:
            state = "manage"
        elif score >= t["ready_min_score"] and (bd.get("vol_ratio") or 0) > t["ready_min_vol"]:
            state = "ready"
        elif score >= t["setup_min_score"]:
            state = "setup"
        else:
            state = "discovery"

        # Verdict using brain + regime
        regime_penalty = 10 if regime == "ranging" else -5 if regime == "trending" else 0
        adjusted_watch = t["watch_min_score"] + regime_penalty
        adjusted_avoid = t["avoid_max_score"] + regime_penalty

        if state == "ready" and "bullish" in direction:
            if regime == "ranging" and score < 75:
                verdict_key = "watch"
            else:
                verdict_key = "buy"
        elif state == "setup" and score >= adjusted_watch:
            verdict_key = "watch"
        elif score < adjusted_avoid or "strong_bearish" in direction:
            verdict_key = "avoid"
        elif "bearish" in direction and regime != "ranging":
            verdict_key = "avoid"
        else:
            verdict_key = "neutral"

        verdict = _VERDICT_MAP.get(verdict_key, verdict_key)

        sig = {
            "symbol": sym_upper,
            "name_ar": (trade or {}).get("name_ar", bd.get("description", "")),
            "price": bd.get("price", 0),
            "change_pct": round(bd.get("change_pct", 0) or 0, 2),
            "verdict": verdict,
            "verdict_key": verdict_key,
            "trade_state": state,
            "confluence_score": score,
            "ema_state": (bd.get("ema") or {}).get("stack", ""),
            "rsi_14": bd.get("rsi_14", 0),
            "macd_state": (bd.get("macd") or {}).get("state", ""),
            "macd_momentum": (bd.get("signals") or {}).get("macd_momentum", ""),
            "adx": bd.get("adx"),
            "vol_ratio": bd.get("vol_ratio"),
            "support": (bd.get("support") or [None])[0],
            "resistance": (bd.get("resistance") or [None])[0],
            "atr_14": bd.get("atr_14"),
            "bb_squeeze": (bd.get("bb") or {}).get("squeeze"),
            "stoch_k": (bd.get("stoch_rsi") or {}).get("k"),
            "rsi_divergence": (bd.get("signals") or {}).get("rsi_divergence"),
            "ema_cross": (bd.get("signals") or {}).get("ema_cross"),
            "confluence_detail": confluence,
            "timeframe": "30m",
            "source": bd.get("source", ""),
            "stale": bd.get("stale", False),
        }
        signals.append(sig)

    signals.sort(key=lambda s: s.get("confluence_score", 0), reverse=True)
    result["signals"] = signals
    result["count"] = len(signals)
    return result
```

---

## CHANGE 3 — stock_radar.check_symbol يستخدم أوزان الـ Brain

### ملف: `stock_radar.py`

### 3A: تعديل `_compute_score()` ليستخدم brain weights:

بدل الأوزان الثابتة، نستخدم brain weights:
```python
def _compute_score(signal, rsi, vwap, price, vol_sig, ema_f, ema_s, sr):
    """Compute score using Brain weights if available."""
    if not signal:
        return 0, "D"

    # Try brain weights
    try:
        from trading_brain import get_indicator_weights
        weights = get_indicator_weights()
    except Exception:
        weights = {}

    w_ema = weights.get("ema", 1.0)
    w_rsi = weights.get("rsi", 1.0)
    w_vol = weights.get("vol", 1.0)
    w_macd = weights.get("macd", 1.0)
    w_adx = weights.get("adx", 1.0)
    w_stoch = weights.get("stoch", 1.0)

    score = 0
    vol_type = vol_sig.get("signal", "normal") if vol_sig else "normal"
    vol_ratio = vol_sig.get("ratio", 0) if vol_sig else 0
    is_bull = signal == "bullish_cross"

    # EMA cross base (weighted)
    score += int(25 * w_ema)

    # RSI alignment (weighted)
    if rsi:
        if is_bull:
            if 40 <= rsi <= 65: score += int(15 * w_rsi)
            elif rsi < 35: score += int(10 * w_rsi)
            elif rsi > 75: score -= int(10 * w_rsi)
        else:
            if 35 <= rsi <= 60: score += int(15 * w_rsi)
            elif rsi > 65: score += int(10 * w_rsi)
            elif rsi < 25: score -= int(10 * w_rsi)

    # VWAP alignment (weighted by macd as proxy)
    if vwap and price:
        if is_bull and price > vwap: score += int(15 * w_macd)
        elif not is_bull and price < vwap: score += int(15 * w_macd)
        elif is_bull and price < vwap * 0.97: score += int(5 * w_macd)

    # Volume confirmation (weighted)
    if vol_ratio >= 2.5: score += int(20 * w_vol)
    elif vol_ratio >= 1.5: score += int(15 * w_vol)
    elif vol_ratio >= 1.0: score += int(5 * w_vol)
    elif vol_ratio < 0.3: score -= int(15 * w_vol)

    # S/R proximity (weighted by adx)
    if sr and price:
        res1 = sr.get("resistance_1", 0)
        sup1 = sr.get("support_1", 0)
        if is_bull and res1 and price > res1 * 0.98: score -= int(10 * w_adx)
        if not is_bull and sup1 and price < sup1 * 1.02: score -= int(10 * w_adx)

    # Trend confirmation (EMA gap)
    if ema_f and ema_s:
        gap_pct = abs(ema_f - ema_s) / ema_s * 100 if ema_s else 0
        if gap_pct > 1.5: score += int(10 * w_ema)
        elif gap_pct > 0.5: score += int(5 * w_ema)

    score = max(0, min(100, score))
    if score >= 75: cls = "A"
    elif score >= 50: cls = "B"
    elif score >= 30: cls = "C"
    else: cls = "D"
    return score, cls
```

---

## CHANGE 4 — Dashboard endpoint جديد لـ 30m signals

### ملف: `dashboard_api.py` أو `server.py`

```python
@app.get("/dashboard/signals-30m")
async def dashboard_signals_30m():
    """30m signals for all watchlist symbols using Brain weights."""
    from signal_engine import build_signals_30m
    return build_signals_30m()
```

---

## CHANGE 5 — signals.html يستخدم الـ endpoints الصحيحة

### ملف: `www/trading/signals.html` (claude.ai يعدّل)

تاب 30m يسحب من `/dashboard/signals-30m` بدل `/dashboard/signals`.
تاب 1D يبقى يسحب من `/dashboard/signals` (اللي بدوره يسحب 1D).

هذا التعديل يسويه claude.ai بعد ما Claude Code يخلص.

---

## CHANGE 6 — Brain Backfill لـ 30m أيضاً

### ملف: `brain_backfill.py` — أضف function:

```python
def backfill_symbol_30m(symbol, bars=None):
    """Backfill one symbol with 30m data."""
    if bars is None:
        try:
            r = requests.get(
                f"{BRIDGE_URL}/analysis",
                params={"symbol": symbol, "exchange": "KSE", "interval": "30m", "bars": 500},
                timeout=60
            )
            if r.status_code != 200:
                return {"symbol": symbol, "error": "bridge_http_" + str(r.status_code)}
            data = r.json()
            bars = data.get("bars", [])
        except Exception as e:
            return {"symbol": symbol, "error": str(e)}

    if not bars or len(bars) < MIN_WARMUP + EVAL_DAYS + 10:
        return {"symbol": symbol, "error": "insufficient_bars", "count": len(bars) if bars else 0}

    # For 30m: eval_days = 14 bars (7 hours of 30m = ~1 day of trading)
    EVAL_BARS_30M = 14
    conn = _conn()
    stats = {"symbol": symbol, "timeframe": "30m", "snapshots": 0, "hit": 0, "miss": 0, "expired": 0}

    for i in range(MIN_WARMUP, len(bars) - EVAL_BARS_30M):
        bar = bars[i]
        snap = _compute_snapshot(bar)
        if snap["confluence"] < MIN_CONFLUENCE:
            continue

        bar_time = bar.get("time", 0)
        if not bar_time:
            continue
        signal_time = datetime.utcfromtimestamp(bar_time).strftime("%Y-%m-%d %H:%M:%S")

        # Evaluate using next 14 bars (30m × 14 = 7 hours)
        future = bars[i+1:i+1+EVAL_BARS_30M]
        if len(future) < EVAL_BARS_30M:
            continue

        price_at = snap["price"]
        atr = snap["atr_14"] or price_at * 0.02
        if not price_at or price_at <= 0:
            continue

        max_high = max(b.get("high", 0) for b in future)
        min_low = min(b.get("low", 999999) for b in future)
        price_end = future[-1].get("close", price_at)

        max_gain_pct = ((max_high - price_at) / price_at) * 100
        max_loss_pct = ((price_at - min_low) / price_at) * 100
        outcome_pct = ((price_end - price_at) / price_at) * 100

        # For 30m, lower threshold (ATR * 0.3 or 1.5%)
        hit_threshold_pct = max((atr * 0.3 / price_at) * 100, 1.5)

        verdict_key = snap["verdict_key"]
        if verdict_key in ("buy", "watch"):
            if max_gain_pct >= hit_threshold_pct and max_loss_pct < hit_threshold_pct:
                outcome = "hit"
            elif max_loss_pct >= hit_threshold_pct and max_gain_pct < hit_threshold_pct:
                outcome = "miss"
            else:
                outcome = "expired"
        else:
            outcome = "expired"

        conn.execute("""
            INSERT INTO signal_snapshots
            (symbol, signal_time, trade_state, verdict, verdict_key, confluence_score,
             price_at_signal, rsi_14, macd_state, macd_momentum, ema_state,
             adx, vol_ratio, stoch_k, bb_squeeze, rsi_divergence,
             ema_cross_type, ema_cross_bars_ago, support, resistance, atr_14,
             ind_rsi, ind_macd, ind_ema, ind_adx, ind_vol, ind_stoch,
             outcome, price_7d, outcome_pct, max_gain_pct, max_loss_pct,
             outcome_evaluated_at, source, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,'historical_backfill_30m','30m backfill')
        """, (
            symbol, signal_time, snap["trade_state"], snap["verdict"], snap["verdict_key"],
            snap["confluence"], snap["price"], snap["rsi_14"], snap["macd_state"],
            snap["macd_momentum"], snap["ema_state"], snap["adx"], snap["vol_ratio"],
            snap["stoch_k"], snap["bb_squeeze"], snap["rsi_divergence"],
            snap["ema_cross_type"], snap["ema_cross_bars_ago"],
            snap["support"], snap["resistance"], snap["atr_14"],
            snap["ind_rsi"], snap["ind_macd"], snap["ind_ema"],
            snap["ind_adx"], snap["ind_vol"], snap["ind_stoch"],
            outcome, round(price_end, 3), round(outcome_pct, 2),
            round(max_gain_pct, 2), round(max_loss_pct, 2),
        ))
        stats["snapshots"] += 1
        stats[outcome] = stats.get(outcome, 0) + 1

    conn.commit()
    conn.close()
    return stats


def run_full_backfill_30m():
    """Run 30m backfill for all watchlist symbols."""
    from stock_radar import get_watchlist
    wl = get_watchlist()
    symbols = [w["symbol"] for w in wl]
    logger.info(f"Starting 30m backfill for {len(symbols)} symbols...")

    all_stats = []
    total = 0
    for idx, sym in enumerate(symbols):
        logger.info(f"[{idx+1}/{len(symbols)}] 30m backfill {sym}...")
        stats = backfill_symbol_30m(sym)
        all_stats.append(stats)
        total += stats.get("snapshots", 0)
        time.sleep(0.5)

    # Update brain
    from trading_brain import update_indicator_performance, adjust_weights
    update_indicator_performance()
    adjust_weights()

    logger.info(f"30m backfill complete: {total} snapshots")
    return {"total_symbols": len(symbols), "total_snapshots": total, "symbols": all_stats}
```

---

## TESTING & DEPLOYMENT

```bash
cd /home/pi/master_ai

# 1. Test bridge_client 30m:
venv/bin/python3 -c "
import asyncio
from bridge_client import get_bridge_client
async def test():
    c = get_bridge_client()
    r = await c.get_analysis_30m('CLEANING')
    print(f'30m: price={r.get(\"price\")}, rsi={r.get(\"rsi_14\")}, tf={r.get(\"timeframe\")}')
asyncio.run(test())
"

# 2. Test signal_engine 30m endpoint:
KEY=\$(cat ~/.master_ai_key)
curl -s -H "X-API-Key: \$KEY" http://localhost:9000/dashboard/signals-30m | python3 -m json.tool | head -20

# 3. Test all 128 symbols in 1D:
curl -s -H "X-API-Key: \$KEY" http://localhost:9000/dashboard/signals | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'1D: {len(d.get(\"all_signals\",[]))} signals')"

# 4. Run 30m backfill:
venv/bin/python3 -c "
from brain_backfill import run_full_backfill_30m
import json
r = run_full_backfill_30m()
print(json.dumps({'total': r['total_snapshots']}, indent=2))
"

# 5. Full test:
venv/bin/python3 _tools/quick_check.py
venv/bin/python3 _tools/smoke_test.py

# 6. Commit + restart:
git add bridge_client.py signal_engine.py stock_radar.py dashboard_api.py brain_backfill.py server.py
git commit -m 'feat: 30m real signals + brain weights everywhere + all 128 symbols + 30m backfill'
bash _tools/restart_master_ai.sh
```

---

## SUMMARY — قبل وبعد

### قبل:
| المكان | Timeframe | يستخدم Brain؟ | عدد الأسهم |
|--------|-----------|--------------|-----------|
| Signals tab 30m | ❌ فعلياً 1D | ✅ | 15 فقط |
| Signals tab 1D | ✅ 1D | ✅ | 15 فقط |
| Radar 30m | ✅ 30m | ❌ | كل الـ watchlist |
| Brain backfill | ✅ 1D فقط | — | 128 |

### بعد:
| المكان | Timeframe | يستخدم Brain؟ | عدد الأسهم |
|--------|-----------|--------------|-----------|
| Signals tab 30m | ✅ 30m فعلي | ✅ | **128 كلهم** |
| Signals tab 1D | ✅ 1D | ✅ | **128 كلهم** |
| Radar 30m | ✅ 30m | ✅ **(جديد)** | 128 |
| Brain backfill | ✅ 1D + **30m** | — | 128 |

---

## ما يحتاج تعديل من claude.ai (بعد Claude Code يخلص):

### signals.html:
- تاب 30m → fetch من `/dashboard/signals-30m` بدل `/dashboard/signals`
- تاب 1D يبقى كما هو

---

## HOW TO EXECUTE

1. File at: `/home/pi/master_ai/_tools/BRAIN_FULL_COVERAGE.md`

2. Tell Claude Code:
```
اقرأ _tools/BRAIN_FULL_COVERAGE.md ونفذ:
Change 1: أضف get_analysis_30m + get_multi_analysis_30m لـ bridge_client.py
Change 2: عدّل signal_engine — رفع حد الأسهم + أضف _get_bridge_data_30m_safe + build_signals_30m
Change 3: عدّل _compute_score في stock_radar.py يستخدم brain weights
Change 4: أضف /dashboard/signals-30m endpoint
Change 5: (يسويه claude.ai)
Change 6: أضف backfill_symbol_30m + run_full_backfill_30m لـ brain_backfill.py
ثم اختبر وسوي commit + restart
ثم شغّل run_full_backfill_30m()
```
