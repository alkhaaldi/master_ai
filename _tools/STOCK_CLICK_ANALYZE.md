# Stock Deep Analysis — /api/analyze endpoint + /تحليل Telegram
# Claude Code: Execute on RPi
# PREREQUISITE: Bridge /bars endpoint is LIVE and TESTED ✅

## What's Available
Bridge `/bars` endpoint returns historical bars WITH indicators:
```
GET http://192.168.111.158:8059/bars?symbol=MANAZEL&interval=30&count=100
→ {"symbol":"KSE:MANAZEL","interval":"30","count":100,"bars":[
    {"time":1774944000,"open":46.2,"high":48.0,"low":46.2,"close":47.2,
     "volume":598729,"rsi_14":63.6,"macd":0.099,"macd_signal":0.05,
     "ema_9":45.82,"ema_21":45.5,"ema_50":45.9,"ema_200":47.6,
     "atr_14":0.88,"adx":20.1,"stoch_k":66.4,"obv":2688450}, ...
  ]}
```

## Goal
User clicks stock → Master AI fetches 100 bars (30m) + 60 bars (daily) from Bridge
→ Summarizes data intelligently → Sends to Gemini 2.5 Pro → Returns Arabic analysis

---

## Step 1: Add to server.py (or new file stock_analyzer.py)

### Core function:
```python
import time, json, urllib.request, urllib.error, logging, os

logger = logging.getLogger("stock_analyzer")

GEMINI_KEY = ""
_gk = os.path.expanduser("~/.gemini_key")
if os.path.exists(_gk):
    GEMINI_KEY = open(_gk).read().strip()

BRIDGE_BASE = "http://192.168.111.158:8059"

# TTL cache: 30 min per symbol
_analysis_cache = {}
CACHE_TTL = 1800

def _fetch_bridge_bars(symbol, interval, count):
    """Fetch enriched bars from Bridge API."""
    url = f"{BRIDGE_BASE}/bars?symbol={symbol}&interval={interval}&count={count}"
    req = urllib.request.urlopen(url, timeout=30)
    return json.loads(req.read().decode())

def _summarize_bars(bars_data, label):
    """Create smart summary of bars for Gemini — saves tokens but keeps key info."""
    bars = bars_data.get("bars", [])
    if not bars:
        return {"error": "no data"}
    
    # Last 5 bars full detail (short-term)
    latest_5 = bars[-5:]
    
    # RSI trajectory last 20 bars
    rsi_traj = [round(b.get("rsi_14", 0), 1) for b in bars[-20:]]
    
    # MACD trajectory last 20 bars
    macd_traj = [round(b.get("macd", 0), 3) for b in bars[-20:]]
    
    # Volume trend
    vols = [b.get("volume", 0) for b in bars]
    vol_20 = sum(vols[-20:]) / max(len(vols[-20:]), 1)
    vol_5 = sum(vols[-5:]) / max(len(vols[-5:]), 1)
    
    # Price range
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    
    # Find peak and trough
    peak_bar = max(bars, key=lambda b: b["high"])
    trough_bar = min(bars, key=lambda b: b["low"])
    
    return {
        "timeframe": label,
        "total_bars": len(bars),
        "latest": bars[-1],
        "latest_5_bars": latest_5,
        "price_range": {
            "period_high": max(highs),
            "period_low": min(lows),
            "first_open": bars[0]["open"],
            "last_close": bars[-1]["close"],
            "change_pct": round((bars[-1]["close"] - bars[0]["open"]) / bars[0]["open"] * 100, 2)
        },
        "peak": {"time": peak_bar["time"], "high": peak_bar["high"]},
        "trough": {"time": trough_bar["time"], "low": trough_bar["low"]},
        "rsi_last_20": rsi_traj,
        "macd_last_20": macd_traj,
        "volume": {
            "avg_20": round(vol_20),
            "avg_5": round(vol_5),
            "latest": bars[-1].get("volume", 0),
            "ratio_5_to_20": round(vol_5 / max(vol_20, 1), 2)
        },
        "ema_current": {
            "ema_9": bars[-1].get("ema_9"),
            "ema_21": bars[-1].get("ema_21"),
            "ema_50": bars[-1].get("ema_50"),
            "ema_200": bars[-1].get("ema_200"),
        },
        "adx": bars[-1].get("adx"),
        "stoch_k": bars[-1].get("stoch_k"),
        "atr": bars[-1].get("atr_14"),
    }
```

### Gemini prompt — designed to produce analysis like the CSV example:
```python
ANALYSIS_PROMPT = """أنت محلل فني محترف لبورصة الكويت. حلّل سهم {symbol} بالتفصيل.

**بيانات 30 دقيقة ({count_30m} شمعة):**
```json
{summary_30m}
```

**بيانات يومية ({count_daily} شمعة):**
```json
{summary_daily}
```

حلّل السهم كمحلل فني خبير:

1. **القمة والتصحيح:** أين كانت أعلى قمة؟ كم نسبة الهبوط منها؟ هل انتهى التصحيح؟
2. **إشارات البيع/الشراء المبكرة:** شنو الإشارات اللي ظهرت عند القمة أو القاع؟ (Volume climax, MACD divergence, RSI levels)
3. **الوضع الحالي:** هل السهم بترند صاعد/هابط/محايد؟ شنو تقول المؤشرات الحين؟
4. **مسار RSI:** تتبع مسار RSI آخر 20 شمعة — هل يرتفع أو ينخفض؟ هل كسر 50؟
5. **MACD:** هل فيه تقاطع إيجابي أو سلبي؟ هل فوق أو تحت الصفر؟
6. **حجم التداول:** هل فيه دخول سيولة؟ قارن حجم آخر 5 شموع بمتوسط 20
7. **مستويات الدعم والمقاومة** من EMA والأسعار التاريخية
8. **خطة التداول:** نقطة دخول، وقف خسارة، أهداف
9. **تقييم المخاطر والثقة (0-100)**

اكتب التحليل بالعربي الكويتي بأسلوب محلل محترف. كن محدداً بالأرقام.
اكتب كنص مفصّل (مو JSON) — فقرات واضحة مع عناوين.
بالنهاية أعطني JSON مختصر بالهيكل:

```json
{{
  "signal": "شراء / بيع / انتظار / مراقبة",
  "confidence": 75,
  "direction": "صاعد / هابط / محايد",
  "entry": "السعر",
  "stop_loss": "السعر",
  "targets": ["هدف1", "هدف2"],
  "support": ["دعم1", "دعم2"],
  "resistance": ["مقاومة1", "مقاومة2"],
  "risk": "وصف المخاطر"
}}
```

ابدأ التحليل الآن."""
```

### Main analyze function:
```python
def analyze_stock(symbol):
    """Full stock analysis with Gemini 2.5 Pro."""
    # 1. Check cache
    cached = _analysis_cache.get(symbol)
    if cached and (time.time() - cached["ts"]) < CACHE_TTL:
        return cached["data"]
    
    # 2. Fetch bars from Bridge
    try:
        bars_30m = _fetch_bridge_bars(symbol, "30", 100)
        bars_daily = _fetch_bridge_bars(symbol, "D", 60)
    except Exception as e:
        return {"error": f"Bridge error: {e}"}
    
    # 3. Summarize
    summary_30m = _summarize_bars(bars_30m, "30m")
    summary_daily = _summarize_bars(bars_daily, "daily")
    
    # 4. Build prompt
    prompt = ANALYSIS_PROMPT.format(
        symbol=symbol,
        count_30m=summary_30m.get("total_bars", 0),
        count_daily=summary_daily.get("total_bars", 0),
        summary_30m=json.dumps(summary_30m, indent=2, ensure_ascii=False),
        summary_daily=json.dumps(summary_daily, indent=2, ensure_ascii=False)
    )
    
    # 5. Call Gemini 2.5 Pro
    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={GEMINI_KEY}"
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 8192,
            "thinkingConfig": {"thinkingBudget": -1}
        }
    }).encode()
    
    req = urllib.request.Request(gemini_url, data=body,
        headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=120)
    result = json.loads(resp.read().decode())
    
    # 6. Extract non-thought text
    answer = ""
    for c in result.get("candidates", []):
        for p in c.get("content", {}).get("parts", []):
            if not p.get("thought", False):
                answer += p.get("text", "")
    
    # 7. Try to extract JSON from end of response
    analysis_json = {}
    try:
        # Find last JSON block in response
        import re
        json_matches = re.findall(r'\{[^{}]*"signal"[^{}]*\}', answer)
        if json_matches:
            analysis_json = json.loads(json_matches[-1])
    except:
        pass
    
    # 8. Build result
    analysis = {
        "symbol": symbol,
        "report": answer,  # Full Arabic text analysis
        "structured": analysis_json,  # Extracted JSON summary
        "analyzed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data": {
            "bars_30m": summary_30m.get("total_bars", 0),
            "bars_daily": summary_daily.get("total_bars", 0),
            "price": summary_30m.get("latest", {}).get("close"),
        }
    }
    
    # 9. Cache
    _analysis_cache[symbol] = {"data": analysis, "ts": time.time()}
    
    return analysis
```

## Step 2: FastAPI Endpoint

```python
@app.get("/api/analyze")
async def api_analyze_stock(symbol: str):
    """Gemini-powered deep stock analysis."""
    if not symbol:
        return {"error": "symbol required"}
    if not GEMINI_KEY:
        return {"error": "Gemini API key not configured"}
    try:
        result = await asyncio.to_thread(analyze_stock, symbol.upper())
        return result
    except Exception as e:
        logger.exception("analyze_stock failed for %s", symbol)
        return {"error": str(e)}
```

---

## Step 3: Telegram `/تحليل` command

Add to the command handler section in server.py:

```python
    if cmd in ("/تحليل", "/analyze") or text.strip().startswith(("/تحليل ", "/analyze ")):
        raw = text.strip()
        if raw.startswith("/تحليل"):
            args_t = raw[6:].strip()
        else:
            args_t = raw[8:].strip()
        symbol = args_t.upper()
        if not symbol:
            return "الاستخدام: /تحليل ZAIN"
        
        # Send "typing" indicator
        try:
            result = await asyncio.to_thread(analyze_stock, symbol)
        except Exception as e:
            return f"❌ خطأ: {e}"
        
        if result.get("error"):
            return f"❌ {result['error']}"
        
        # Format for Telegram — send the full report text
        report = result.get("report", "")
        structured = result.get("structured", {})
        
        # Truncate if too long for Telegram (4096 char limit)
        if len(report) > 3800:
            report = report[:3800] + "\n\n... (التحليل طويل، شوف الداشبورد للنسخة الكاملة)"
        
        # Add structured summary at top
        signal = structured.get("signal", "—")
        confidence = structured.get("confidence", "—")
        direction = structured.get("direction", "—")
        
        header = f"🔍 *تحليل {symbol}*\n"
        header += f"📊 {direction} | {signal} | ثقة: {confidence}%\n"
        header += "─" * 20 + "\n\n"
        
        return header + report
```

---

## Step 4: Import and register

Make sure `analyze_stock` is importable. Either:
A) Add it directly to server.py (simpler)
B) Create `stock_analyzer.py` and import it

Option A is simpler — add the functions near the news_engine section.

---

## Test Checklist
1. `curl "http://192.168.109.123:9000/api/analyze?symbol=MANAZEL"` → full analysis
2. Telegram: `/تحليل MANAZEL` → Arabic report
3. Second call to same symbol → instant (cached)
4. Different symbol → 15-20 sec then analysis

## Important Notes
- Bridge MUST be running on PC for /bars to work
- Gemini key: ~/.gemini_key on RPi (already configured)
- Cache TTL: 30 min per symbol
- Uses Gemini 2.5 Pro (not Flash) for deep analysis
- Google Search grounding enabled for market context
- Prompt asks for Arabic analysis in Kuwaiti style + JSON summary
