# 🔄 Trading V2 Plan — Daily Swing Trading
# تحويل النظام من Scalping خاسر إلى Swing Trading مربح
# مبني على تحليل Gemini Pro لـ 66,937 إشارة حقيقية من بورصة الكويت

---

## لماذا هذا التحويل؟

### المشكلة: Scalping 30m = خسارة مضمونة
```
العمولة: 0.25% ذهاب وإياب
هدف Scalping: 0.75% (1.5R × 0.5% stop)
ربح صافي: 0.75% - 0.25% = +0.50%
خسارة صافية: 0.50% + 0.25% = -0.75%
R:R الحقيقي: 0.67:1 ← خسّار!
Win rate المطلوب للتعادل: 60% ← عندنا 22% بس!
```

### الحل: Daily Swing Trading
```
هدف Swing: 4-6% (صفقة 3-10 أيام)
ستوب: 2% (ATR-based)
ربح صافي: 4% - 0.25% = +3.75%
خسارة صافية: 2% + 0.25% = -2.25%
R:R الحقيقي: 1.67:1 ← مربح!
Win rate المطلوب للتعادل: 37.5%
Win rate المتوقع مع Whitelist: ~38-45%
```

---

## Phase 1: إصلاح خلط الفريمات (CRITICAL BUG)

### المشكلة (من مراجعة جيميني للكود):
`signals.html` → `fetchData()` يخلط بيانات 30m مع يومية:
```javascript
// هذا الكود يسبب إشارات كاذبة!
dailySignals = dailyCtx.map(w => {
    const liveMatch = liveSignals.find(s => s.symbol === w.symbol);
    const price = liveMatch ? liveMatch.price : w.price; // ← سعر 30m حي مع مؤشرات يومية!
});
```

### الحل:
```
1. signal_engine.py: أضف حقل واضح لكل إشارة
   - signal.timeframe = "30m" أو "1D"
   - signal.valid_until = timestamp (30m تنتهي بعد 30 دقيقة، يومية تنتهي آخر اليوم)
   
2. dashboard_api.py: endpoints منفصلة تماماً
   - GET /dashboard/signals-30m → بيانات 30m فقط
   - GET /dashboard/signals-daily → بيانات يومية فقط (سعر الإقفال أمس، مو سعر حي)
   - ممنوع خلطهم!

3. signals.html: كل tab يسحب من endpoint مختلف
   - Tab 30m → /dashboard/signals-30m
   - Tab يومي → /dashboard/signals-daily
   - لا يشاركون أي بيانات
```

**الملفات:** signal_engine.py, dashboard_api.py, signals.html
**المنفّذ:** Claude Code (Python) + claude.ai (HTML)

---

## Phase 2: فلتر Daily Trend (أهم تغيير)

### المنطق:
```python
def get_daily_trend(symbol: str, bars: list, sma_period: int = 20) -> dict:
    """
    فلتر الاتجاه اليومي — لا تشتري إلا السوق صاعد
    
    Input: daily OHLCV bars (من Bridge أو DB)
    Logic:
      - حساب SMA 20 من أسعار الإقفال اليومية
      - السعر فوق SMA 20 = UP (اسمح بالشراء)
      - السعر تحت SMA 20 = DOWN (ممنوع الشراء)
      - فرق أقل من 0.5% = SIDEWAYS (حذر)
    
    Returns:
      trend: "UP" / "DOWN" / "SIDEWAYS"
      sma20: قيمة SMA 20
      price_vs_sma: نسبة بُعد السعر عن SMA
      trend_strength: قوة الاتجاه (من ADX يومي)
    """
    if not bars or len(bars) < sma_period:
        return {"trend": "UNKNOWN", "sma20": 0, "allow_buy": False}
    
    closes = [b['close'] for b in bars]
    sma20 = sum(closes[-sma_period:]) / sma_period
    current_price = closes[-1]
    
    distance_pct = ((current_price - sma20) / sma20) * 100
    
    if distance_pct > 0.5:
        trend = "UP"
        allow_buy = True
    elif distance_pct < -0.5:
        trend = "DOWN"
        allow_buy = False
    else:
        trend = "SIDEWAYS"
        allow_buy = False  # حذر — لا تدخل بدون اتجاه واضح
    
    return {
        "trend": trend,
        "sma20": round(sma20, 3),
        "price_vs_sma_pct": round(distance_pct, 2),
        "allow_buy": allow_buy
    }
```

### القاعدة الحديدية:
```
إذا Daily Trend = DOWN أو SIDEWAYS:
    → ممنوع أي إشارة شراء
    → الداشبورد يعرض: "⛔ السوق نازل — لا تشتري"
    → حتى لو كل المؤشرات الثانية خضرا
```

**الملفات:** signal_engine.py (function جديدة)
**المنفّذ:** Claude Code

---

## Phase 3: Whitelist / Blacklist

### من بيانات Brain (66,937 إشارة):

#### Whitelist — أفضل 10 أسهم (hit rate > 30%):
```python
WHITELIST = [
    "INOVEST",    # 41.2% hit, avg gain 3.9%
    "URC",        # 38.6% hit, avg gain 3.54%
    "ACICO",      # 38.2% hit, avg gain 6.53% ← أعلى gain!
    "AAYANRE",    # 36.5% hit, avg gain 2.88%
    "OOREDOO",    # 36.2% hit, avg gain 3.10%
    "ALFTAQA",    # 35.9% hit, avg gain 3.18%
    "NINV",       # 35.6% hit, avg gain 2.05%
    "MUBARRAD",   # 33.6% hit, avg gain 2.76%
    "NRE",        # 33.5% hit, avg gain 1.96%
    "RASIYAT",    # 32.2% hit, avg gain 2.09%
]
```

#### Blacklist — أسوأ 10 أسهم (hit rate < 10%):
```python
BLACKLIST = [
    "KFH",          # 2.8% hit ← شبه مستحيل!
    "GINS",         # 4.5% hit, avg loss 12.86%!
    "KHOT",         # 5.2% hit
    "MUNTAZAHAT",   # 5.8% hit
    "PCEM",         # 6.4% hit
    "INJAZZAT",     # 6.9% hit
    "BOUBYAN",      # 8.4% hit
    "TAHSSILAT",    # 8.6% hit
    "GBK",          # 9.0% hit
    "PAPER",        # 9.4% hit
]
```

### التنفيذ:
```python
# في أعلى signal_engine.py أو config
WHITELIST_MODE = True  # True = تداول Whitelist فقط, False = تداول الكل ما عدا Blacklist

# في بداية signal pipeline
def should_trade(symbol: str) -> bool:
    if symbol in BLACKLIST:
        return False
    if WHITELIST_MODE and symbol not in WHITELIST:
        return False
    return True
```

### التأثير المتوقع:
```
قبل: 128 سهم × 21% hit rate = خاسر
بعد: 10 أسهم × 36-41% hit rate = ممكن مربح
```

**الملفات:** signal_engine.py, stock_radar.py
**المنفّذ:** Claude Code

---

## Phase 4: ATR-Based Stops + Daily Pivot Targets

### ستوب ذكي بـ ATR (بدل 0.5% ثابت):
```python
def calculate_swing_stop(entry_price: float, atr_14: float, 
                          support_level: float = None) -> dict:
    """
    ستوب Swing Trading مبني على ATR + دعم
    
    الأولوية:
    1. تحت مستوى الدعم (إذا متوفر) - ATR واحد تحته
    2. 2 × ATR تحت سعر الدخول (fallback)
    3. Maximum: 3% تحت الدخول (حماية قصوى)
    """
    # ATR-based stop
    atr_stop = entry_price - (2.0 * atr_14)
    
    # Support-based stop (أفضل)
    if support_level and support_level < entry_price:
        sr_stop = support_level - (1.0 * atr_14)  # تحت الدعم بـ ATR
    else:
        sr_stop = atr_stop
    
    # Maximum stop (حماية)
    max_stop = entry_price * 0.97  # 3% max
    
    # اختار الأقرب للسعر (الأضيق) بس مو أقل من max_stop
    stop = max(min(atr_stop, sr_stop), max_stop)
    
    risk_pct = abs(entry_price - stop) / entry_price * 100
    
    return {
        "stop_loss": round(stop, 3),
        "risk_pct": round(risk_pct, 2),
        "stop_type": "support_atr" if stop == sr_stop else ("atr_2x" if stop == atr_stop else "max_3pct"),
        "atr_14": round(atr_14, 4)
    }
```

### هدف عند المقاومة التالية (بدل 1.5R ثابت):
```python
def calculate_swing_target(entry_price: float, daily_levels: dict,
                            atr_14: float) -> dict:
    """
    هدف ديناميكي — عند أقرب مقاومة فوق سعر الدخول
    
    daily_levels يحتوي: pp, s1, s2, r1, r2, pdh, pdl, vwap
    """
    # مستويات المقاومة المحتملة (مرتبة من الأقرب)
    resistance_levels = []
    for key in ['pp', 'r1', 'pdh', 'r2', 'vwap']:
        val = daily_levels.get(key, 0)
        if val > entry_price * 1.005:  # على الأقل 0.5% فوق الدخول
            resistance_levels.append((key, val))
    
    resistance_levels.sort(key=lambda x: x[1])  # الأقرب أول
    
    if resistance_levels:
        target_key, target_price = resistance_levels[0]
    else:
        # fallback: 3 × ATR فوق الدخول
        target_price = entry_price + (3.0 * atr_14)
        target_key = "atr_3x"
    
    reward_pct = (target_price - entry_price) / entry_price * 100
    
    return {
        "target": round(target_price, 3),
        "reward_pct": round(reward_pct, 2),
        "target_type": target_key
    }
```

### Daily Pivot Points:
```python
def calculate_daily_pivots(prev_high: float, prev_low: float, 
                            prev_close: float) -> dict:
    """
    يتحسب مرة وحدة قبل السوق من بيانات أمس
    """
    pp = (prev_high + prev_low + prev_close) / 3
    s1 = (2 * pp) - prev_high
    s2 = pp - (prev_high - prev_low)
    r1 = (2 * pp) - prev_low
    r2 = pp + (prev_high - prev_low)
    
    return {
        "pp": round(pp, 3),
        "s1": round(s1, 3),
        "s2": round(s2, 3),
        "r1": round(r1, 3),
        "r2": round(r2, 3)
    }
```

**الملفات:** signal_engine.py, sr_engine.py
**المنفّذ:** Claude Code

---

## Phase 5: تبسيط Confluence — Volume + ADX فقط

### شيل المؤشرات الخاسرة:
```
من البيانات الحقيقية:
- RSI ON = 19.7% hit → OFF = 25.8% ← شيله! (يضر)
- MACD ON = 20.6% hit → OFF = 23.2% ← شيله! (يضر)
- Stoch ON = 20.7% hit → OFF = 22.4% ← شيله! (لا يفيد)
- Golden Cross 50/200 = بطيء جداً ← شيله!

خلّي بس:
- Volume 1-3x = 24.3% hit ✅
- ADX > 25 = 22.4-24.3% hit ✅
- RSI < 50 كفلتر عكسي (مو كإشارة) ✅
- Daily SMA 20 trend ✅ (جديد)
```

### Confluence الجديد (Swing Mode):
```python
SWING_MODE = True  # Feature flag — يحل محل SCALPING_MODE

def swing_confluence(symbol: str, daily_data: dict, 
                      intraday_data: dict = None) -> dict:
    """
    Confluence مبسّط للـ Swing Trading
    
    شروط الدخول (كلها لازم تتحقق):
    1. Daily Trend UP (SMA 20) — إلزامي
    2. Volume 1-3x average — إلزامي  
    3. ADX > 25 — إلزامي
    4. RSI < 50 — فلتر (لا تشتري فوق 50)
    5. سعر قريب من دعم (S1/PDL/VWAP) — مفضّل
    """
    score = 0
    factors = []
    blockers = []
    
    # 1. Daily Trend (إلزامي)
    trend = daily_data.get("trend", "UNKNOWN")
    if trend != "UP":
        return {
            "confluence_pct": 0,
            "action": "NO_ENTRY",
            "reason": f"Daily trend = {trend}",
            "factors": [],
            "blockers": [f"TREND:{trend}"]
        }
    score += 30
    factors.append("TREND:UP")
    
    # 2. Volume 1-3x (إلزامي)
    vol_ratio = daily_data.get("vol_ratio", 0)
    if 1.0 <= vol_ratio <= 3.0:
        score += 25
        factors.append(f"VOL:{vol_ratio:.1f}x")
    else:
        blockers.append(f"VOL:{vol_ratio:.1f}x (need 1-3x)")
    
    # 3. ADX > 25 (إلزامي)
    adx = daily_data.get("adx", 0)
    if adx >= 25:
        score += 25
        factors.append(f"ADX:{adx:.0f}")
        if adx >= 40:
            score += 5  # bonus للاتجاه القوي
            factors.append("ADX:STRONG")
    else:
        blockers.append(f"ADX:{adx:.0f} (need >25)")
    
    # 4. RSI < 50 (فلتر)
    rsi = daily_data.get("rsi_14", 50)
    if rsi < 50:
        score += 10
        factors.append(f"RSI:{rsi:.0f}<50")
    elif rsi < 30:
        score += 15  # bonus — oversold = فرصة أقوى
        factors.append(f"RSI:{rsi:.0f} OVERSOLD")
    else:
        blockers.append(f"RSI:{rsi:.0f} (need <50)")
    
    # 5. قرب من دعم (bonus)
    near_support = daily_data.get("near_support", False)
    if near_support:
        score += 10
        factors.append("NEAR_SUPPORT")
    
    # القرار
    if blockers:
        action = "NO_ENTRY"
        reason = " + ".join(blockers)
    elif score >= 80:
        action = "STRONG_BUY"
        reason = "All conditions met + bonus"
    elif score >= 60:
        action = "BUY"
        reason = "Core conditions met"
    else:
        action = "WATCH"
        reason = "Partial match"
    
    return {
        "confluence_pct": min(score, 100),
        "action": action,
        "reason": reason,
        "factors": factors,
        "blockers": blockers
    }
```

**الملفات:** signal_engine.py
**المنفّذ:** Claude Code

---

## Phase 6: تحويل الداشبورد

### المفهوم الجديد:
بدل 3 صفحات تداول مخربطة (radar + signals + scalper)، صفحة واحدة واضحة:

### صفحة `swing.html` — تحل محل scalper.html:

```
+--------------------------------------------------+
| ⛔ السوق نازل — لا تشتري (أو ✅ السوق صاعد)      |  ← Daily Trend فوق
+--------------------------------------------------+
| 🎯 أفضل فرصة الآن                                |
| ACICO — شراء قوي 85%                             |
| فريم: يومي | الاتجاه: صاعد                       |
| الدخول: 0.450 | الستوب: 0.430 (ATR×2)            |
| الهدف: 0.475 (R1 pivot) | R:R = 2.1:1            |
| الحالة: 🟡 راقب (يتحول لـ 🟢 ادخل الآن)          |
| العوامل: TREND:UP, VOL:2.1x, ADX:32, RSI:38     |
+--------------------------------------------------+
| 📊 فرص أخرى (Whitelist فقط)                       |
| سهم | اتجاه | فريم | confluence | قرار | حالة    |
| INOVEST | ↑ | 1D | 72% | شراء | راقب            |
| URC     | ↑ | 1D | 65% | راقب | -               |
| OOREDOO | → | 1D | 40% | لا   | اتجاه جانبي    |
+--------------------------------------------------+
| 📈 مراكز نشطة                                     |
| ACICO: دخول 0.450, حالي 0.460, +2.2%            |
|   ستوب: 0.430 | هدف: 0.475 | 3 أيام             |
|   حالة: ✅ مستمر                                  |
+--------------------------------------------------+
| تحديث كل 5 دقائق | المصدر: Daily + Bridge        |
+--------------------------------------------------+
```

### تفاصيل البناء:
```
1. Hero Section: Daily Trend indicator
   - أخضر كبير = السوق صاعد (فوق SMA 20) → ابحث عن فرص
   - أحمر كبير = السوق نازل (تحت SMA 20) → لا تشتري
   - رمادي = جانبي → حذر

2. Top Signal Card: أفضل فرصة واحدة حالياً
   - اسم السهم + confluence %
   - فريم واضح: "يومي" أو "30 دقيقة"
   - Entry / Stop / Target بأرقام واضحة
   - R:R بعد العمولة
   - حالة: راقب → ادخل الآن → نشط → اخرج

3. Signal Table: Whitelist فقط (10 أسهم max)
   - بس الأسهم اللي عندها إشارة
   - مرتبة حسب confluence
   - لون أخضر/أحمر/رمادي واضح

4. Active Positions: المراكز المفتوحة
   - PnL حي
   - أيام بالصفقة
   - قرب من ستوب أو هدف
   - تنبيه خروج إذا الاتجاه اليومي انعكس

5. Auto-refresh: كل 5 دقائق (مو 30 ثانية — swing مو scalping)
```

**الملفات:** swing.html (جديد), dashboard_api.py (endpoint جديد)
**المنفّذ:** claude.ai (HTML) + Claude Code (endpoint)

---

## Phase 7: S/R Outcome Tracking

### المشكلة:
- **صفر** إشارات بالبيانات عندها S/R tracking
- جيميني قال هذا "critical deficiency"
- ما نقدر نعرف تأثير الدعوم والمقاومات بدون بيانات

### الحل:
```python
# أضف لكل إشارة يتم تسجيلها في signal_snapshots:

# حقول S/R جديدة:
"daily_pp": 0.450,         # Daily Pivot Point
"daily_s1": 0.440,         # Support 1
"daily_s2": 0.430,         # Support 2
"daily_r1": 0.460,         # Resistance 1
"daily_r2": 0.470,         # Resistance 2
"pdh": 0.465,              # Previous Day High
"pdl": 0.438,              # Previous Day Low
"vwap": 0.448,             # VWAP
"distance_to_support_pct": 0.8,   # بُعد السعر عن أقرب دعم
"distance_to_resistance_pct": 2.1, # بُعد السعر عن أقرب مقاومة
"near_support": True,       # هل السعر قريب من دعم (< 1 ATR)
"near_resistance": False,   # هل السعر قريب من مقاومة
"daily_sma20": 0.445,      # SMA 20 يومي
"daily_trend": "UP"         # اتجاه يومي
```

### DB Migration:
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

### بعد شهر من التجميع:
```python
# نقدر نحلل:
# "الإشارات قريبة من S1 → hit rate كم؟"
# "الإشارات عند PDL + Volume 2x → hit rate كم؟"
# "Daily trend UP + near support → أحسن من بدون؟"
```

**الملفات:** signal_engine.py, life.db (migration)
**المنفّذ:** Claude Code

---

## Phase 8: Feature Flags + Backward Compatibility

### تحكم كامل:
```python
# config أو أعلى signal_engine.py
SWING_MODE = True          # True=swing logic, False=original
SCALPING_MODE = False      # إيقاف scalping
WHITELIST_MODE = True      # True=whitelist only, False=trade all except blacklist
DAILY_TREND_FILTER = True  # إلزامي — لا تشتري بسوق نازل

# المنطق القديم يبقى ملفوف بـ if:
if SCALPING_MODE:
    # المنطق القديم (30m scalping)
    ...
elif SWING_MODE:
    # المنطق الجديد (daily swing)
    ...
```

---

## ترتيب التنفيذ + الحالة

```
Phase 1 → fix: فصل 30m عن Daily بالكامل ✅ c88b291
Phase 2 → feat: Daily SMA 20 trend filter ✅ cf2b64a
Phase 3 → feat: Whitelist/Blacklist engine ✅ cf2b64a
Phase 4 → feat: ATR stops + Daily Pivots targets ✅ 576efcc
Phase 5 → refactor: تبسيط confluence (VOL+ADX فقط) ✅ 576efcc
Phase 6 → feat: صفحة swing.html + endpoint ✅ 576efcc
Phase 7 → feat: S/R outcome tracking (DB migration) ✅ 691b825
Phase 8 → feat: feature flags + backward compat ✅ 206a9dd

STATUS: ALL 8 PHASES COMPLETE ✅
```

---

## الملفات المتأثرة

| الملف | الـ Phase | التغييرات |
|-------|-----------|----------|
| signal_engine.py | 1,2,3,4,5,7 | الملف الأهم — معظم التغييرات فيه |
| dashboard_api.py | 1,6 | endpoints جديدة + فصل 30m/daily |
| stock_radar.py | 3 | Whitelist/Blacklist filtering |
| sr_engine.py | 4 | Daily Pivots calculation |
| risk_engine.py | 4 | ATR-based stops |
| signals.html | 1 | فصل tabs + منع خلط البيانات |
| swing.html | 6 | صفحة جديدة بالكامل |
| scalper.html | 6 | يُؤرشف (لا يُحذف) |
| life.db | 7 | ALTER TABLE migration |

---

## الأرقام المتوقعة بعد التحسين

### السيناريو المتحفظ:
```
Win Rate: 38% (Whitelist average)
R:R: 1.67:1 (4% target / 2% stop, بعد العمولة)
Expectancy: (0.38 × 3.75%) - (0.62 × 2.25%) = +0.03% ← breakeven
```

### السيناريو المتفائل (مع S/R + Daily Trend):
```
Win Rate: 45% (مع S/R filter + trend)
R:R: 1.67:1
Expectancy: (0.45 × 3.75%) - (0.55 × 2.25%) = +0.45% per trade ← مربح!
```

### السيناريو الأمثل (ADX > 40 + S/R + Whitelist top 5):
```
Win Rate: 48%
R:R: 2.0:1 (bigger targets at resistance)
Expectancy: (0.48 × 3.75%) - (0.52 × 2.25%) = +0.63% per trade ← جيد!
```

---

## خطة Paper Trading

### قبل أي فلوس حقيقية:
```
1. شغّل النظام الجديد 3-6 أشهر paper trading
2. تتبّع كل صفقة بالتفصيل
3. المقاييس المطلوبة:
   - Net Expectancy > +0.25% per trade → "يشتغل"
   - Max Drawdown < 15% → "مقبول"
   - Profit Factor > 1.5 → "يستاهل"
   - Win Rate > 37.5% → "فوق التعادل"

4. متى تتوقف:
   - Expectancy سالب بعد 3 أشهر → أوقف
   - Drawdown > 20% → أوقف
   - أقل من صفقتين بالشهر → النظام مقيّد زيادة
```

---

## ⚠️ قواعد صارمة

1. **لا تشتري بسوق نازل** — Daily Trend = DOWN → ممنوع
2. **Whitelist فقط** — 10 أسهم مجربة، الباقي تجاهل
3. **لا RSI ولا MACD كإشارة** — يُستخدمون كفلتر بس
4. **Volume 1-3x** (مو 3x+ — البيانات أثبتت إنه أسوأ)
5. **ستوب ATR** مو نسبة ثابتة — كل سهم له تذبذب مختلف
6. **هدف عند مقاومة** مو R:R ثابت — السوق يقرر الهدف
7. **Paper trade أول** — 3 أشهر minimum قبل فلوس حقيقية
8. **Feature flag** — كل شي reversible
