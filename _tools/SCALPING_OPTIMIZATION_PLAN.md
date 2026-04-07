# 🔥 Scalping Optimization Plan — Master AI v9.0
# Priority: bugs → VWAP → confluence → exit rules → endpoint

## Context
تحليل Gemini Pro لـ 66,937 إشارة Brain كشف:
- Hit rate عام: 22.1%
- Volume (65% hit) و ADX (63% hit) هم الأقوى
- RSI (25% hit) و MACD (37% hit) يضعّفون الإشارات
- Golden Engine بطيء جداً للمضاربة السريعة (50/200 crossover)
- S/R ثابت وقديم — المضارب يحتاج VWAP + PDH/PDL

---

## Phase 1: Bug Fixes (CRITICAL)
### 1.1 risk_engine.py — ZeroDivisionError (سطر ~28)
```
المشكلة: إذا entry_price == stop_loss → قسمة على صفر
الموقع: risk_engine.py سطر 28 تقريباً (ابحث عن division بـ entry - stop)
الحل:
  - أضف guard clause:
    if abs(entry_price - stop_loss) < 0.001:
        return {"error": "entry equals stop loss", "risk_reward": 0, "position_size": 0}
  - ارجع نتيجة آمنة بدل crash
```

### 1.2 signal_engine.py — Timestamp Misalignment (سطر ~421)
```
المشكلة: data misalignment بالـ timestamps — الشموع ممكن تكون مختلفة التوقيت
الموقع: signal_engine.py سطر 421 تقريباً
الحل:
  - ابحث عن المكان اللي يقارن timestamps بين datasets مختلفة
  - أضف alignment check:
    # تأكد إن كل الـ series على نفس index
    if len(close_prices) != len(volumes):
        logger.warning(f"Data misalignment: close={len(close_prices)}, vol={len(volumes)}")
        # استخدم أقصر length
        min_len = min(len(close_prices), len(volumes), len(high_prices), len(low_prices))
        close_prices = close_prices[-min_len:]
        volumes = volumes[-min_len:]
        high_prices = high_prices[-min_len:]
        low_prices = low_prices[-min_len:]
```

---

## Phase 2: VWAP Calculation
### 2.1 إضافة VWAP لـ signal_engine.py

```python
# VWAP = Σ(Typical Price × Volume) / Σ(Volume)
# Typical Price = (High + Low + Close) / 3
# يُحسب من بداية يوم التداول (reset يومي)

def calculate_vwap(high: list, low: list, close: list, volume: list, timestamps: list = None) -> dict:
    """
    حساب VWAP للمضاربة السريعة
    
    Returns:
        vwap: القيمة الحالية
        vwap_distance_pct: بُعد السعر عن VWAP كنسبة مئوية
        price_vs_vwap: 'above' أو 'below'
    """
    if not high or len(high) < 2:
        return {"vwap": 0, "vwap_distance_pct": 0, "price_vs_vwap": "unknown"}
    
    typical_prices = [(h + l + c) / 3 for h, l, c in zip(high, low, close)]
    
    cum_tp_vol = 0
    cum_vol = 0
    vwap_values = []
    
    for tp, v in zip(typical_prices, volume):
        cum_tp_vol += tp * v
        cum_vol += v
        if cum_vol > 0:
            vwap_values.append(cum_tp_vol / cum_vol)
        else:
            vwap_values.append(tp)
    
    current_vwap = vwap_values[-1] if vwap_values else 0
    current_price = close[-1]
    
    distance_pct = ((current_price - current_vwap) / current_vwap * 100) if current_vwap > 0 else 0
    
    return {
        "vwap": round(current_vwap, 3),
        "vwap_distance_pct": round(distance_pct, 2),
        "price_vs_vwap": "above" if current_price > current_vwap else "below"
    }
```

### 2.2 إضافة PDH/PDL (Previous Day High/Low)
```python
def calculate_pdh_pdl(daily_bars: list) -> dict:
    """
    حساب Previous Day High و Low
    daily_bars: list of dicts مع high, low, close
    يحتاج على الأقل 2 bars (أمس واليوم)
    """
    if not daily_bars or len(daily_bars) < 2:
        return {"pdh": 0, "pdl": 0, "daily_open": 0}
    
    prev_day = daily_bars[-2]  # أمس
    today = daily_bars[-1]     # اليوم (للـ open)
    
    return {
        "pdh": prev_day.get("high", 0),
        "pdl": prev_day.get("low", 0),
        "daily_open": today.get("open", 0)
    }
```

### 2.3 دمج VWAP في Signal Pipeline
```
الموقع: signal_engine.py — الـ function اللي تولّد الإشارات
أضف:
1. استدعاء calculate_vwap() بعد ما تجهز bars
2. أضف الحقول للنتيجة: vwap, vwap_distance_pct, price_vs_vwap
3. أضف حقل scalping_vwap_ok: True إذا السعر فوق VWAP (للشراء)
```

---

## Phase 3: Confluence Optimization
### 3.1 Feature Flag
```python
# أضف في أعلى signal_engine.py أو في config
SCALPING_MODE = True  # Feature flag — يتحكم بمنطق المضاربة

# أو الأفضل: اقرأه من DB/config
# scalping_mode = get_config("scalping_mode", default=True)
```

### 3.2 تعديل Confluence Score
```
المنطق الحالي (تقريباً):
  confluence = weighted_sum(RSI, MACD, EMA, Volume, ADX, Stoch, ...)

المنطق الجديد (scalping_mode=True):
  
  # المؤشرات المعتمدة فقط (من Brain data):
  SCALPING_WEIGHTS = {
      "volume_surge": 1.15,    # 65% hit rate — الملك
      "adx_strong":   1.13,    # 63% hit rate
      "stoch_signal":  1.05,   # 55% hit rate
      "vwap_aligned":  1.20,   # جديد — شرط إلزامي
  }
  
  # المؤشرات المُلغاة:
  # RSI: 25% hit → أسوأ من random → شيله
  # MACD: 37% hit → ضعيف → شيله
  # EMA crossover: بطيء للمضاربة (بس EMA 9/21 للـ exit)
  # Golden Cross (50/200): بطيء جداً → شيله من 30m
  
  # الحساب:
  score = 0
  factors = []
  
  # شرط إلزامي: VWAP
  if price_vs_vwap != "above":
      return {"confluence": 0, "action": "NO_ENTRY", "reason": "Price below VWAP"}
  score += SCALPING_WEIGHTS["vwap_aligned"]
  factors.append("VWAP✓")
  
  # Volume Surge (> 3x average)
  if volume_ratio >= 3.0:
      score += SCALPING_WEIGHTS["volume_surge"]
      factors.append(f"VOL:{volume_ratio:.1f}x")
  
  # ADX > 25 (trending)
  if adx >= 25:
      score += SCALPING_WEIGHTS["adx_strong"]
      factors.append(f"ADX:{adx:.0f}")
  
  # Stochastic signal (K > D, not overbought)
  if stoch_k > stoch_d and stoch_k < 80:
      score += SCALPING_WEIGHTS["stoch_signal"]
      factors.append(f"STOCH:{stoch_k:.0f}")
  
  # النتيجة
  max_possible = sum(SCALPING_WEIGHTS.values())  # 4.53
  confluence_pct = (score / max_possible) * 100
  
  # القرار
  if confluence_pct >= 75:
      action = "STRONG_BUY"
  elif confluence_pct >= 50:
      action = "BUY"
  else:
      action = "WATCH"
```

### 3.3 إيقاف Golden Engine للـ 30m
```
الموقع: حيث ما ينادي golden_engine.py من signal pipeline
الحل: 
  if scalping_mode and timeframe == "30m":
      # تخطي Golden Engine — بطيء للمضاربة
      golden_signal = None
  else:
      golden_signal = golden_engine.analyze(...)
```

---

## Phase 4: Exit Rules
### 4.1 Stop Loss — أضيق وأذكى
```python
def calculate_scalping_stop(entry_price: float, candle_low: float, ema21: float) -> dict:
    """
    ستوب المضاربة: الأقرب من:
    1. low الشمعة الحالية
    2. EMA 21
    3. 0.5% تحت الدخول (maximum stop)
    """
    max_stop = entry_price * 0.995  # 0.5% max
    
    # الأقرب للسعر (أضيق ستوب)
    stop_options = [candle_low, ema21, max_stop]
    # بس الخيارات اللي تحت سعر الدخول
    valid_stops = [s for s in stop_options if s < entry_price]
    
    if not valid_stops:
        stop = max_stop
    else:
        stop = max(valid_stops)  # الأقرب للسعر = أضيق ستوب
    
    risk_pct = abs(entry_price - stop) / entry_price * 100
    target = entry_price + (entry_price - stop) * 1.5  # 1.5R
    
    return {
        "stop_loss": round(stop, 3),
        "target": round(target, 3),
        "risk_pct": round(risk_pct, 2),
        "reward_pct": round(risk_pct * 1.5, 2),
        "risk_reward": 1.5,
        "stop_type": "candle_low" if stop == candle_low else ("ema21" if stop == ema21 else "max_0.5pct")
    }
```

### 4.2 Exit Rules — 3 Bars Timeout + EMA9 Break
```python
def check_scalping_exit(bars_since_entry: int, current_pnl_pct: float, 
                         current_close: float, ema9: float) -> dict:
    """
    قواعد الخروج للمضاربة السريعة:
    1. 3 شموع بدون ربح = اخرج (timeout)
    2. إقفال تحت EMA 9 = اخرج (trend break)
    3. وصل الهدف 1.5R = اخرج (target hit)
    """
    exit_signal = False
    exit_reason = None
    
    # Rule 1: Timeout — 3 bars بدون ربح
    if bars_since_entry >= 3 and current_pnl_pct <= 0:
        exit_signal = True
        exit_reason = "TIMEOUT_3BARS"
    
    # Rule 2: Close below EMA 9
    elif current_close < ema9:
        exit_signal = True
        exit_reason = "BELOW_EMA9"
    
    return {
        "should_exit": exit_signal,
        "exit_reason": exit_reason,
        "bars_held": bars_since_entry,
        "current_pnl_pct": round(current_pnl_pct, 2)
    }
```

---

## Phase 5: API Endpoint
### 5.1 إضافة endpoint جديد أو تعديل الحالي
```
Endpoint: GET /dashboard/scalper
يرجع:
{
    "scalper_active": true,
    "scan_time": "2026-04-03T10:30:00",
    "market_status": "open",
    "hot_stocks": [
        {
            "symbol": "HUMANSOFT",
            "price": 3.200,
            "change_pct": 2.5,
            "volume_ratio": 4.2,
            "adx": 32,
            "stoch_k": 65,
            "stoch_d": 58,
            "vwap": 3.150,
            "vwap_distance_pct": 1.6,
            "price_vs_vwap": "above",
            "confluence_pct": 82,
            "action": "STRONG_BUY",
            "factors": ["VWAP✓", "VOL:4.2x", "ADX:32", "STOCH:65"],
            "stop_loss": 3.150,
            "target": 3.275,
            "risk_pct": 0.47,
            "reward_pct": 0.70,
            "stop_type": "ema21",
            "ema9": 3.190,
            "ema21": 3.150
        }
    ],
    "active_scalps": [
        {
            "symbol": "ALIMTIAZ",
            "entry_price": 0.450,
            "current_price": 0.455,
            "bars_held": 2,
            "pnl_pct": 1.1,
            "stop_loss": 0.445,
            "target": 0.458,
            "exit_check": {
                "should_exit": false,
                "bars_held": 2
            }
        }
    ],
    "stats": {
        "total_scanned": 128,
        "hot_count": 5,
        "active_scalps": 1,
        "avg_confluence": 68
    },
    "filters_applied": {
        "min_volume_ratio": 3.0,
        "min_adx": 25,
        "vwap_required": true,
        "scalping_mode": true
    }
}
```

### 5.2 Filtering Logic
```
من 128 سهم:
1. فلتر أول: Bridge online? → بس الأسهم اللي عندها بيانات حية
2. فلتر ثاني: Volume Ratio >= 3.0
3. فلتر ثالث: ADX >= 25
4. فلتر رابع: Price > VWAP
5. ترتيب: حسب confluence_pct تنازلي
6. Top 10 فقط → hot_stocks
```

---

## Phase 6: Testing
```bash
# بعد كل phase:
python3 _tools/quick_check.py
python3 _tools/smoke_test.py

# تحقق من الـ endpoint:
curl -s -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000/dashboard/scalper | python3 -m json.tool

# تحقق VWAP:
curl -s -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000/dashboard/signals | python3 -m json.tool | grep vwap
```

---

## Execution Order
```
Phase 1 → git commit "fix: risk_engine ZeroDivisionError + signal timestamp alignment"
Phase 2 → git commit "feat: add VWAP calculation + PDH/PDL"  
Phase 3 → git commit "feat: scalping confluence (Volume+ADX+Stoch+VWAP only)"
Phase 4 → git commit "feat: scalping exit rules (3-bar timeout + EMA9 break)"
Phase 5 → git commit "feat: /dashboard/scalper endpoint"
Phase 6 → smoke test + restart

كل phase مستقل — لو أي واحد فشل، الباقي ما يتأثر.
```

---

## Files to Modify
| File | Phase | Changes |
|------|-------|---------|
| risk_engine.py | 1 | ZeroDivisionError guard |
| signal_engine.py | 1,2,3 | Timestamp fix + VWAP + Confluence |
| golden_engine.py | 3 | Skip for 30m scalping |
| trading_decision_engine.py | 4 | Exit rules |
| dashboard_api.py | 5 | /dashboard/scalper endpoint |
| server.py | 5 | Route registration (if needed) |

## Feature Flag
```python
# في config أو أعلى signal_engine.py
SCALPING_MODE = True  # Toggle: True=scalping logic, False=original logic
# هذا يخلي كل التعديلات reversible
```

## ⚠️ Important Notes
- لا تحذف المنطق القديم — لفّه بـ `if not SCALPING_MODE:`
- كل function جديدة لازم يكون لها fallback
- VWAP يحتاج bars كافية (20+ bar على الأقل)
- Bridge لازم يكون online عشان البيانات تشتغل
- أي خطأ = log واضح مو silent failure
