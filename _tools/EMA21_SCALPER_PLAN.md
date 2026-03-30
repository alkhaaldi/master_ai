# EMA 21 Migration + Scalper Dashboard Plan
# Date: 2026-03-30
# Executor: Claude Code (RPi) + بو خليفة (Bridge on PC)
# Reviewer: claude.ai

## Summary
بو خليفة يريد EMA 21 بدل EMA 20 في كل النظام + صفحة مضارب جديدة (scalper.html)
تعرض تقاطعات EMA 9/21 الحية على 128 سهم كويتي فريم 30m مع إشعارات تلقرام.

## Current State
- Bridge API (`app/indicators.py`) يحسب `ema(closes, 20)` — هذا يحتاج يتغير لـ 21
- كل الأماكن تستخدم key name `ema_20` — يحتاج rename لـ `ema_21`
- stock_radar.py يقرأ `ema_20` من Bridge response
- bridge_client.py يقرأ `ema_20` من Bridge response  
- signal_engine.py يقرأ `ema_cross` signal (indirect — no direct ema_20 read)
- Dashboard HTML pages تعرض "EMA 20" labels

## IMPORTANT: Backward Compatibility
- Keep `ema_20` as alias for `ema_21` everywhere in responses
- This prevents breaking any page that still reads `ema_20`

---

## Phase A: Bridge API (Windows PC) — بو خليفة ينفذ يدوي أو Claude Code على PC

### File: `C:\Users\MS1\tradingview-bridge\app\indicators.py`

#### Change 1: `add_indicators_to_bars()` — line ~265
```python
# OLD:
ema20 = ema(closes, 20)

# NEW:
ema21 = ema(closes, 21)
```

#### Change 2: Same function — output keys (~line 280)
```python
# OLD:
row["ema_20"] = _r(ema20[i])

# NEW:
row["ema_21"] = _r(ema21[i])
row["ema_20"] = _r(ema21[i])  # backward compat alias
```

#### Change 3: `compute_signals()` — confluence section
```python
# OLD:
for ema_key in ["ema_20", "ema_50", "ema_200"]:

# NEW:
for ema_key in ["ema_21", "ema_50", "ema_200"]:
```

#### Change 4: `compute_signals()` — EMA Cross events
```python
# OLD:
ema20_vals = [b.get("ema_20") for b in bars[-20:]]

# NEW:
ema20_vals = [b.get("ema_21") or b.get("ema_20") for b in bars[-20:]]
```

#### Change 5: `summarize_latest_snapshot()` — indicators dict
```python
# OLD:
"ema_20": latest.get("ema_20"),

# NEW:
"ema_21": latest.get("ema_21"),
"ema_20": latest.get("ema_21"),  # backward compat
```

### After Bridge changes:
```bash
cd C:\Users\MS1\tradingview-bridge
.venv313\Scripts\python -m uvicorn app.main:app --port 8059 --host 0.0.0.0
# Test:
curl "http://localhost:8059/analysis?symbol=BOURSA:ZAIN&interval=30m" | python -m json.tool | findstr ema
# Verify both ema_21 and ema_20 appear
```

---

## Phase B: RPi Master AI — Claude Code ينفذ

### File: `bridge_client.py` (~line 286-343)

#### Change 1: Parse EMA from Bridge response
```python
# OLD:
ema20 = ind.get("ema_20", 0)

# NEW:
ema21 = ind.get("ema_21") or ind.get("ema_20") or 0
```

#### Change 2: Output dict
```python
# OLD:
"ema20": round(ema20, 2),
"above_ema20": price > ema20 if ema20 else None,

# NEW:
"ema21": round(ema21, 2),
"ema20": round(ema21, 2),  # backward compat
"above_ema21": price > ema21 if ema21 else None,
"above_ema20": price > ema21 if ema21 else None,  # backward compat
```

#### Change 3: EMA stack detection
```python
# OLD:
if ema9 > ema20 > ema50 > ema200:
elif ema9 < ema20 < ema50 < ema200:

# NEW:
if ema9 > ema21 > ema50 > ema200:
elif ema9 < ema21 < ema50 < ema200:
```

### File: `stock_radar.py` (~line 703)

#### Change 1: `check_symbol()` — read EMA slow
```python
# OLD:
ema_s = float(ind.get("ema_20") or ind.get("ema21") or 0)

# NEW:
ema_s = float(ind.get("ema_21") or ind.get("ema_20") or 0)
```

### Other files to grep and fix:
```bash
grep -rn "ema_20\|ema20" *.py | grep -v __pycache__
# Fix any remaining references with same pattern: ema_21 primary, ema_20 fallback
```

---

## Phase C: New Endpoints — Claude Code ينفذ

### Add to `server.py` or `dashboard_api.py`:

### Endpoint 1: `/dashboard/ema-crosses`
```python
@app.get("/dashboard/ema-crosses")
async def dashboard_ema_crosses(hours: int = 4, signal_type: str = "all"):
    """Recent EMA 9/21 cross events for scalper page."""
    import sqlite3
    from datetime import datetime, timedelta
    
    conn = sqlite3.connect("data/audit.db")
    conn.row_factory = sqlite3.Row
    
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    
    where_signal = ""
    if signal_type == "bullish":
        where_signal = "AND signal_type = 'bullish_cross'"
    elif signal_type == "bearish":
        where_signal = "AND signal_type = 'bearish_cross'"
    
    rows = conn.execute(f"""
        SELECT symbol, signal_type, price, candle_time, ema_fast, ema_slow,
               rsi, volume, score, score_class, verdict, support, resistance, 
               vol_ratio, created_at
        FROM stock_radar_events
        WHERE created_at >= ? {where_signal}
        ORDER BY created_at DESC
        LIMIT 100
    """, (cutoff,)).fetchall()
    conn.close()
    
    from tv_data import KSE_STOCKS
    
    events = []
    for r in rows:
        events.append({
            "symbol": r["symbol"],
            "name_ar": KSE_STOCKS.get(r["symbol"], r["symbol"]),
            "signal": r["signal_type"],
            "price": r["price"],
            "candle_time": r["candle_time"],
            "ema9": r["ema_fast"],
            "ema21": r["ema_slow"],
            "rsi": r["rsi"],
            "volume": r["volume"],
            "score": r["score"],
            "score_class": r["score_class"],
            "verdict": r["verdict"],
            "support": r["support"],
            "resistance": r["resistance"],
            "vol_ratio": r["vol_ratio"],
            "time": r["created_at"],
        })
    
    bull = sum(1 for e in events if e["signal"] == "bullish_cross")
    bear = sum(1 for e in events if e["signal"] == "bearish_cross")
    
    return {
        "total": len(events),
        "bullish_count": bull,
        "bearish_count": bear,
        "hours": hours,
        "events": events,
        "timestamp": datetime.utcnow().isoformat(),
    }
```

### Endpoint 2: `/dashboard/ema-proximity`
```python
@app.get("/dashboard/ema-proximity")
async def dashboard_ema_proximity(threshold_pct: float = 1.5):
    """Stocks where EMA9 and EMA21 are close — about to cross."""
    import sqlite3
    
    conn = sqlite3.connect("data/audit.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT symbol, prev_ema_fast, prev_ema_slow, updated_at
        FROM stock_radar_state
        WHERE timeframe = '30m' AND prev_ema_fast > 0 AND prev_ema_slow > 0
    """).fetchall()
    conn.close()
    
    from tv_data import KSE_STOCKS
    
    approaching = []
    for r in rows:
        fast = r["prev_ema_fast"]
        slow = r["prev_ema_slow"]
        if not slow:
            continue
        gap_pct = abs(fast - slow) / slow * 100
        if gap_pct <= threshold_pct:
            direction = "bullish_approach" if fast > slow else "bearish_approach"
            approaching.append({
                "symbol": r["symbol"],
                "name_ar": KSE_STOCKS.get(r["symbol"], r["symbol"]),
                "ema9": round(fast, 3),
                "ema21": round(slow, 3),
                "gap_pct": round(gap_pct, 3),
                "direction": direction,
                "updated_at": r["updated_at"],
            })
    
    approaching.sort(key=lambda x: x["gap_pct"])
    
    return {
        "threshold_pct": threshold_pct,
        "count": len(approaching),
        "stocks": approaching,
    }
```

---

## Phase D: HTML Labels — claude.ai ينفذ
Search all HTML files in www/trading/ for "EMA 20" or "ema_20" display text.
Replace visible labels with "EMA 21". Keep JS data reads backward-compatible.
Then build scalper.html page.

---

## Execution Order
1. Phase A — Bridge on PC (بو خليفة manually or guided)
2. Phase B — RPi Python (Claude Code)
3. Phase C — New endpoints (Claude Code)
4. Phase D — HTML + scalper.html (claude.ai)

## Testing
```bash
# Phase A test (on PC):
curl "http://localhost:8059/analysis?symbol=BOURSA:ZAIN&interval=30m" | findstr ema

# Phase B+C test (on RPi):
curl "http://localhost:9000/dashboard/ema-crosses?hours=24"
curl "http://localhost:9000/dashboard/ema-proximity?threshold_pct=2"

# Full test: wait for market, check Telegram alerts
```

## Risk: LOW
- Backward compat aliases everywhere
- No DB schema changes
- New endpoints are additive (don't touch existing)
- Bridge restart = ~30s gap (acceptable)
