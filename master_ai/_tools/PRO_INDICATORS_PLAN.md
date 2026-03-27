# Pro Indicators Upgrade — Claude Code Task
# Date: 2026-03-26
# Scope: Add 10 pro-level indicators to Bridge API + update normalization on RPi

## OVERVIEW
The Bridge API currently computes only basic indicators (RSI, MACD, EMA, S/R).
Professional traders need volume analysis, volatility tools, and computed SIGNALS (not raw numbers).
This upgrade adds 10 indicators to indicators.py on Windows Bridge, then updates bridge_client.py normalization on RPi.

## IMPORTANT: TWO SEPARATE SYSTEMS TO UPDATE

### System 1: Windows Bridge API (C:\Users\MS1\tradingview-bridge\)
- File: app/indicators.py — add new indicator functions + wire into add_indicators_to_bars()
- File: app/models.py — extend IndicatorsSnapshot + IndicatorBar models
- This runs on Windows PC, NOT on RPi

### System 2: RPi Master AI (/home/pi/master_ai/)
- File: bridge_client.py — update _normalize_analysis() to include new fields
- Use apply_text_patch.py for Python edits on RPi

---

## PHASE 1: New indicator functions in indicators.py (Windows Bridge)

Add these functions to indicators.py BEFORE the add_indicators_to_bars function.
All pure Python, no external libraries.

### 1. ATR (Average True Range) — position sizing + trailing stops
```python
def atr(bars: list[dict[str, Any]], period: int = 14) -> list[float]:
    """Average True Range - measures volatility. Used for position sizing and stops."""
    result = [None] * len(bars)
    if len(bars) < 2:
        return result
    tr_values = []
    for i in range(1, len(bars)):
        high = bars[i].get("high") or 0
        low = bars[i].get("low") or 0
        prev_close = bars[i - 1].get("close") or 0
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_values.append(tr)
    # First ATR = simple average of first `period` TR values
    if len(tr_values) < period:
        return result
    atr_val = sum(tr_values[:period]) / period
    result[period] = atr_val
    for i in range(period, len(tr_values)):
        atr_val = (atr_val * (period - 1) + tr_values[i]) / period
        result[i + 1] = atr_val
    return result
```

### 2. Bollinger Bands — squeeze detection + breakout signals
```python
def bollinger_bands(closes: list[float], period: int = 20, std_mult: float = 2.0):
    """Bollinger Bands. Returns (upper, middle, lower, bandwidth, squeeze)."""
    n = len(closes)
    upper = [None] * n
    middle = [None] * n
    lower = [None] * n
    bandwidth = [None] * n
    squeeze = [None] * n  # True when bandwidth is at 6-month low
    
    for i in range(period - 1, n):
        window = [c for c in closes[i - period + 1:i + 1] if c is not None]
        if len(window) < period:
            continue
        sma = sum(window) / len(window)
        variance = sum((x - sma) ** 2 for x in window) / len(window)
        std = variance ** 0.5
        middle[i] = sma
        upper[i] = sma + std_mult * std
        lower[i] = sma - std_mult * std
        bandwidth[i] = (upper[i] - lower[i]) / sma * 100 if sma else None
    
    # Squeeze: bandwidth is at 120-bar low (approx 6 months daily)
    for i in range(period - 1, n):
        if bandwidth[i] is None:
            continue
        lookback_bw = [bw for bw in bandwidth[max(0, i - 120):i + 1] if bw is not None]
        if lookback_bw and bandwidth[i] <= min(lookback_bw) * 1.05:
            squeeze[i] = True
        else:
            squeeze[i] = False
    
    return upper, middle, lower, bandwidth, squeeze
```

### 3. OBV (On-Balance Volume) — money flow direction
```python
def obv(closes: list[float], volumes: list[float]) -> list[float]:
    """On-Balance Volume. Positive trend = money flowing in."""
    result = [None] * len(closes)
    if len(closes) < 2:
        return result
    result[0] = volumes[0] or 0
    for i in range(1, len(closes)):
        c, pc = closes[i], closes[i - 1]
        v = volumes[i] or 0
        prev_obv = result[i - 1] or 0
        if c is not None and pc is not None:
            if c > pc:
                result[i] = prev_obv + v
            elif c < pc:
                result[i] = prev_obv - v
            else:
                result[i] = prev_obv
        else:
            result[i] = prev_obv
    return result
```

### 4. Volume Ratio — today's volume vs 20-day average
```python
def volume_ratio(volumes: list[float], period: int = 20) -> list[float]:
    """Volume relative to N-period average. >1.5 = spike, >2.0 = strong spike."""
    result = [None] * len(volumes)
    for i in range(period, len(volumes)):
        window = [v for v in volumes[i - period:i] if v is not None and v > 0]
        if window:
            avg = sum(window) / len(window)
            if avg > 0 and volumes[i] is not None:
                result[i] = volumes[i] / avg
    return result
```

### 5. ADX (Average Directional Index) — trend strength
```python
def adx(bars: list[dict[str, Any]], period: int = 14) -> list[float]:
    """ADX - trend strength. >25 = trending, >40 = strong trend, <20 = ranging."""
    n = len(bars)
    result = [None] * n
    if n < period * 2 + 1:
        return result
    
    plus_dm = []
    minus_dm = []
    tr_list = []
    
    for i in range(1, n):
        high = bars[i].get("high") or 0
        low = bars[i].get("low") or 0
        prev_high = bars[i - 1].get("high") or 0
        prev_low = bars[i - 1].get("low") or 0
        prev_close = bars[i - 1].get("close") or 0
        
        up_move = high - prev_high
        down_move = prev_low - low
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0)
        tr_list.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    
    if len(tr_list) < period:
        return result
    
    # Wilder smoothing
    atr_val = sum(tr_list[:period]) / period
    plus_di_smooth = sum(plus_dm[:period]) / period
    minus_di_smooth = sum(minus_dm[:period]) / period
    
    dx_values = []
    for i in range(period, len(tr_list)):
        atr_val = (atr_val * (period - 1) + tr_list[i]) / period
        plus_di_smooth = (plus_di_smooth * (period - 1) + plus_dm[i]) / period
        minus_di_smooth = (minus_di_smooth * (period - 1) + minus_dm[i]) / period
        
        if atr_val > 0:
            plus_di = (plus_di_smooth / atr_val) * 100
            minus_di = (minus_di_smooth / atr_val) * 100
        else:
            plus_di = minus_di = 0
        
        di_sum = plus_di + minus_di
        dx = abs(plus_di - minus_di) / di_sum * 100 if di_sum > 0 else 0
        dx_values.append(dx)
    
    if len(dx_values) < period:
        return result
    
    adx_val = sum(dx_values[:period]) / period
    result[period * 2] = adx_val
    for i in range(period, len(dx_values)):
        adx_val = (adx_val * (period - 1) + dx_values[i]) / period
        result[i + period + 1] = adx_val if i + period + 1 < n else None
    
    return result
```

### 6. Stochastic RSI — refined overbought/oversold
```python
def stoch_rsi(closes: list[float], rsi_period: int = 14, stoch_period: int = 14, smooth_k: int = 3, smooth_d: int = 3):
    """Stochastic RSI. Returns (k, d). K>80 = overbought, K<20 = oversold."""
    rsi_values = rsi(closes, rsi_period)
    n = len(closes)
    raw_k = [None] * n
    
    for i in range(rsi_period + stoch_period - 1, n):
        window = [r for r in rsi_values[i - stoch_period + 1:i + 1] if r is not None]
        if len(window) >= stoch_period:
            min_rsi = min(window)
            max_rsi = max(window)
            if max_rsi != min_rsi and rsi_values[i] is not None:
                raw_k[i] = ((rsi_values[i] - min_rsi) / (max_rsi - min_rsi)) * 100
    
    # Smooth K and D with SMA
    k_line = _sma_series(raw_k, smooth_k)
    d_line = _sma_series(k_line, smooth_d)
    return k_line, d_line


def _sma_series(values: list[float | None], period: int) -> list[float | None]:
    """Simple moving average for a series with None values."""
    result = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = [v for v in values[i - period + 1:i + 1] if v is not None]
        if len(window) == period:
            result[i] = sum(window) / period
    return result
```

### 7-10: Computed SIGNALS (add to summarize_latest_snapshot)

These are computed in the summary, not per-bar:

```python
def compute_signals(bars: list[dict[str, Any]], levels: dict) -> dict:
    """Compute actionable trading signals from indicator data."""
    if len(bars) < 30:
        return {}
    
    latest = bars[-1]
    prev = bars[-2]
    closes = [b.get("close") for b in bars if b.get("close") is not None]
    
    signals = {}
    
    # 7. RSI Divergence detection (last 20 bars)
    rsi_vals = [b.get("rsi_14") for b in bars[-20:]]
    close_vals = [b.get("close") for b in bars[-20:]]
    rsi_clean = [(i, r, c) for i, (r, c) in enumerate(zip(rsi_vals, close_vals)) if r is not None and c is not None]
    if len(rsi_clean) >= 10:
        # Bearish: price making higher high but RSI making lower high
        price_rising = close_vals[-1] and close_vals[-5] and close_vals[-1] > close_vals[-5]
        rsi_falling = rsi_vals[-1] and rsi_vals[-5] and rsi_vals[-1] < rsi_vals[-5]
        # Bullish: price making lower low but RSI making higher low
        price_falling = close_vals[-1] and close_vals[-5] and close_vals[-1] < close_vals[-5]
        rsi_rising = rsi_vals[-1] and rsi_vals[-5] and rsi_vals[-1] > rsi_vals[-5]
        
        if price_rising and rsi_falling:
            signals["rsi_divergence"] = "bearish"
        elif price_falling and rsi_rising:
            signals["rsi_divergence"] = "bullish"
        else:
            signals["rsi_divergence"] = "none"
    
    # 8. MACD Histogram slope (acceleration/deceleration)
    hist_vals = [b.get("macd_hist") for b in bars[-5:] if b.get("macd_hist") is not None]
    if len(hist_vals) >= 3:
        slope = hist_vals[-1] - hist_vals[-3]
        if hist_vals[-1] > 0 and slope > 0:
            signals["macd_momentum"] = "accelerating_bullish"
        elif hist_vals[-1] > 0 and slope < 0:
            signals["macd_momentum"] = "decelerating_bullish"
        elif hist_vals[-1] < 0 and slope < 0:
            signals["macd_momentum"] = "accelerating_bearish"
        elif hist_vals[-1] < 0 and slope > 0:
            signals["macd_momentum"] = "decelerating_bearish"
        else:
            signals["macd_momentum"] = "neutral"
    
    # 9. EMA Cross events (last cross in recent 20 bars)
    ema9_vals = [b.get("ema_9") for b in bars[-20:]]
    ema20_vals = [b.get("ema_20") for b in bars[-20:]]
    last_cross = None
    last_cross_bars_ago = None
    for i in range(1, len(ema9_vals)):
        if ema9_vals[i] is not None and ema20_vals[i] is not None and ema9_vals[i-1] is not None and ema20_vals[i-1] is not None:
            prev_diff = ema9_vals[i-1] - ema20_vals[i-1]
            curr_diff = ema9_vals[i] - ema20_vals[i]
            if prev_diff <= 0 and curr_diff > 0:
                last_cross = "golden"
                last_cross_bars_ago = len(ema9_vals) - 1 - i
            elif prev_diff >= 0 and curr_diff < 0:
                last_cross = "death"
                last_cross_bars_ago = len(ema9_vals) - 1 - i
    signals["ema_cross"] = {"type": last_cross, "bars_ago": last_cross_bars_ago}
    
    # 10. Confluence score (how many indicators agree on direction)
    bullish_count = 0
    bearish_count = 0
    total_checks = 0
    
    # RSI
    rsi_val = latest.get("rsi_14")
    if rsi_val is not None:
        total_checks += 1
        if rsi_val > 50: bullish_count += 1
        else: bearish_count += 1
    
    # MACD hist
    macd_h = latest.get("macd_hist")
    if macd_h is not None:
        total_checks += 1
        if macd_h > 0: bullish_count += 1
        else: bearish_count += 1
    
    # Price vs EMAs
    price = latest.get("close", 0)
    for ema_key in ["ema_20", "ema_50", "ema_200"]:
        ev = latest.get(ema_key)
        if ev is not None and price:
            total_checks += 1
            if price > ev: bullish_count += 1
            else: bearish_count += 1
    
    # ADX trend
    adx_val = latest.get("adx")
    if adx_val is not None and adx_val > 25:
        total_checks += 1
        # ADX doesn't show direction, but confirms trend
        if bullish_count > bearish_count:
            bullish_count += 1
        else:
            bearish_count += 1
    
    # OBV trend (last 5 bars)
    obv_vals = [b.get("obv") for b in bars[-5:] if b.get("obv") is not None]
    if len(obv_vals) >= 3:
        total_checks += 1
        if obv_vals[-1] > obv_vals[0]:
            bullish_count += 1
        else:
            bearish_count += 1
    
    if total_checks > 0:
        score = round((bullish_count / total_checks) * 100)
        if score >= 70:
            direction = "strong_bullish"
        elif score >= 55:
            direction = "bullish"
        elif score <= 30:
            direction = "strong_bearish"
        elif score <= 45:
            direction = "bearish"
        else:
            direction = "neutral"
        signals["confluence"] = {"score": score, "direction": direction, "bullish": bullish_count, "bearish": bearish_count, "total": total_checks}
    
    return signals
```

## PHASE 2: Wire new indicators into add_indicators_to_bars()

Update add_indicators_to_bars to compute and attach all new indicators per bar:

```python
def add_indicators_to_bars(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not bars:
        return bars
    closes = [b.get("close") for b in bars]
    volumes = [b.get("volume") or 0 for b in bars]
    
    # Existing
    ema9 = ema(closes, 9)
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    rsi14 = rsi(closes, 14)
    ml, sl, hi = macd(closes, 12, 26, 9)
    
    # New
    atr14 = atr(bars, 14)
    bb_upper, bb_mid, bb_lower, bb_bw, bb_squeeze = bollinger_bands(closes, 20, 2.0)
    obv_vals = obv(closes, volumes)
    vol_ratio = volume_ratio(volumes, 20)
    adx14 = adx(bars, 14)
    stoch_k, stoch_d = stoch_rsi(closes, 14, 14, 3, 3)
    
    out = []
    for i, b in enumerate(bars):
        row = dict(b)
        # Existing
        row["ema_9"] = _r(ema9[i])
        row["ema_20"] = _r(ema20[i])
        row["ema_50"] = _r(ema50[i])
        row["ema_200"] = _r(ema200[i])
        row["rsi_14"] = _r(rsi14[i])
        row["macd"] = _r(ml[i])
        row["macd_signal"] = _r(sl[i])
        row["macd_hist"] = _r(hi[i])
        # New
        row["atr_14"] = _r(atr14[i])
        row["bb_upper"] = _r(bb_upper[i])
        row["bb_middle"] = _r(bb_mid[i])
        row["bb_lower"] = _r(bb_lower[i])
        row["bb_bandwidth"] = _r(bb_bw[i])
        row["bb_squeeze"] = bb_squeeze[i]
        row["obv"] = _r(obv_vals[i])
        row["vol_ratio"] = _r(vol_ratio[i])
        row["adx"] = _r(adx14[i])
        row["stoch_k"] = _r(stoch_k[i])
        row["stoch_d"] = _r(stoch_d[i])
        out.append(row)
    return out
```

## PHASE 3: Update summarize_latest_snapshot()

Add signals and new indicators to the summary:

```python
def summarize_latest_snapshot(
    symbol: str, interval: str, quote_data: dict[str, Any],
    bars: list[dict[str, Any]], levels: dict[str, list[float]],
) -> dict[str, Any]:
    if not bars:
        raise ValueError("No bars to summarize")
    latest = bars[-1]
    
    # Compute signals
    signals = compute_signals(bars, levels)
    
    return {
        "symbol": symbol, "interval": interval,
        "price": quote_data.get("price") or latest.get("close"),
        "ohlcv": {
            "open": latest.get("open"), "high": latest.get("high"),
            "low": latest.get("low"), "close": latest.get("close"),
            "volume": latest.get("volume"), "time": latest.get("time"),
        },
        "indicators": {
            "rsi_14": latest.get("rsi_14"), "macd": latest.get("macd"),
            "macd_signal": latest.get("macd_signal"), "macd_hist": latest.get("macd_hist"),
            "ema_9": latest.get("ema_9"), "ema_20": latest.get("ema_20"),
            "ema_50": latest.get("ema_50"), "ema_200": latest.get("ema_200"),
            "atr_14": latest.get("atr_14"),
            "bb_upper": latest.get("bb_upper"), "bb_middle": latest.get("bb_middle"),
            "bb_lower": latest.get("bb_lower"), "bb_bandwidth": latest.get("bb_bandwidth"),
            "bb_squeeze": latest.get("bb_squeeze"),
            "obv": latest.get("obv"), "vol_ratio": latest.get("vol_ratio"),
            "adx": latest.get("adx"),
            "stoch_k": latest.get("stoch_k"), "stoch_d": latest.get("stoch_d"),
        },
        "signals": signals,
        "support": levels.get("support", []),
        "resistance": levels.get("resistance", []),
        "quote": quote_data, "bars_count": len(bars), "bars": bars,
    }
```

## PHASE 4: Update models.py

Update IndicatorsSnapshot and IndicatorBar:

Add to IndicatorBar:
```python
    atr_14: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    bb_bandwidth: float | None = None
    bb_squeeze: bool | None = None
    obv: float | None = None
    vol_ratio: float | None = None
    adx: float | None = None
    stoch_k: float | None = None
    stoch_d: float | None = None
```

Add to IndicatorsSnapshot (same fields).

Add to IndicatorSnapshotResponse:
```python
    signals: dict[str, Any] = Field(default_factory=dict)
```

## PHASE 5: Update bridge_client.py on RPi

Update _normalize_analysis() to include new fields. Use apply_text_patch.py.

The new normalization should extract:
- atr_14, bb_squeeze, bb_bandwidth, vol_ratio, adx, stoch_k, stoch_d
- signals: rsi_divergence, macd_momentum, ema_cross, confluence

New normalized output per symbol should look like:
```json
{
  "symbol": "CLEANING",
  "price": 140.0,
  "change_pct": 6.87,
  "volume": 36227888,
  "rsi_14": 74.64,
  "macd": {"macd": 7.34, "signal": 3.32, "hist": 4.02, "state": "bullish"},
  "ema": {"ema9": 125.33, "ema20": 116.51, "ema50": 113.46, "ema200": 105.04, "stack": "bullish"},
  "atr_14": 5.2,
  "adx": 42.3,
  "bb": {"squeeze": false, "bandwidth": 18.5},
  "stoch_rsi": {"k": 85.2, "d": 78.1},
  "vol_ratio": 3.4,
  "signals": {
    "rsi_divergence": "none",
    "macd_momentum": "accelerating_bullish",
    "ema_cross": {"type": "golden", "bars_ago": 3},
    "confluence": {"score": 85, "direction": "strong_bullish", "bullish": 6, "bearish": 1, "total": 7}
  },
  "support": [106, 108, 110],
  "resistance": [153, 163, 172]
}
```

## EXECUTION ORDER

### On Windows (Bridge API):
1. Edit app/indicators.py — add 6 new functions + update add_indicators_to_bars + add compute_signals + update summarize_latest_snapshot
2. Edit app/models.py — add new fields to IndicatorBar, IndicatorsSnapshot, IndicatorSnapshotResponse
3. Test: Start uvicorn, hit /analysis?symbol=CLEANING and verify new fields appear
4. Git commit if using git

### On RPi (Master AI) — Claude Code does this:
1. Read _tools/PRO_INDICATORS_PLAN.md (this file)
2. Update bridge_client.py _normalize_analysis() via apply_text_patch.py
3. Run quick_check.py + smoke_test.py
4. Restart + test /dashboard/bridge/CLEANING
5. Git commit

## DO NOT
- Do not use pandas, numpy, talib, or any external library
- Do not change the WebSocket protocol or tv_ws.py
- Do not modify existing indicator calculations (RSI, MACD, EMA)
- Do not change the /health, /quote, /ohlcv endpoints
- Do not break backward compatibility — old fields must still exist
