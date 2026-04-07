# Signal Review Engine — خطة التنفيذ
# الملف: signal_review.py (جديد)
# التاريخ: 2026-03-30
# المنفذ: Claude Code على RPi

## الهدف
نظام تقييم يومي تلقائي يراجع إشارات ENTER من `decision_audit` بعد إغلاق السوق،
يقارنها بالأسعار الفعلية من `daily_bars`، ويصنف النتيجة + يحلل السبب + يرسل ملخص تيليقرام.

---

## 1. جدول جديد: `signal_reviews`

```sql
CREATE TABLE IF NOT EXISTS signal_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_date DATE NOT NULL,          -- تاريخ المراجعة
    market_date DATE NOT NULL,          -- تاريخ الإشارة الأصلية
    symbol TEXT NOT NULL,
    smart_decision TEXT NOT NULL,       -- ENTER (من decision_audit)
    chosen_plan_source TEXT,            -- strategy / golden / manual
    strategy_id TEXT,                   -- من decision_audit
    
    -- الأسعار
    entry_price REAL,                   -- السعر المقترح للدخول
    stop_price REAL,                    -- الستوب من الخطة
    target_1 REAL,                      -- الهدف الأول
    target_2 REAL,                      -- الهدف الثاني
    next_day_open REAL,                 -- سعر فتح اليوم التالي
    next_day_high REAL,                 -- أعلى سعر اليوم التالي
    next_day_low REAL,                  -- أدنى سعر اليوم التالي  
    next_day_close REAL,               -- سعر إغلاق اليوم التالي
    next_day_volume INTEGER,            -- حجم اليوم التالي
    
    -- النتيجة
    result TEXT NOT NULL DEFAULT 'pending',  -- success / partial / fail / ongoing / no_data
    pnl_pct REAL,                       -- نسبة الربح/الخسارة من entry إلى close
    max_favorable REAL,                 -- أقصى حركة إيجابية (high vs entry)
    max_adverse REAL,                   -- أقصى حركة سلبية (low vs entry)
    hit_target_1 BOOLEAN DEFAULT 0,     -- هل وصل الهدف 1؟
    hit_stop BOOLEAN DEFAULT 0,         -- هل ضرب الستوب؟
    
    -- التحليل
    error_type TEXT,                     -- volume / trend / zone / stop / market / pattern / none
    reason_ar TEXT,                      -- السبب بالعربي
    lesson_ar TEXT,                      -- الدرس المستفاد
    
    -- المؤشرات وقت الإشارة (من decision_audit)
    confidence REAL,
    data_quality INTEGER,
    rr_ratio REAL,
    risk_flags TEXT,
    sector TEXT,
    
    -- التتبع
    decision_audit_id INTEGER,           -- FK to decision_audit.id
    days_tracked INTEGER DEFAULT 1,      -- كم يوم تم تتبعه
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(market_date, symbol)           -- إشارة واحدة لكل سهم لكل يوم
);

CREATE INDEX IF NOT EXISTS idx_sr_review_date ON signal_reviews(review_date);
CREATE INDEX IF NOT EXISTS idx_sr_result ON signal_reviews(result);
CREATE INDEX IF NOT EXISTS idx_sr_symbol ON signal_reviews(symbol);
```

---

## 2. ملف signal_review.py — الهيكل الكامل

### الموقع: `/home/pi/master_ai/signal_review.py`

### Imports المطلوبة:
```python
import sqlite3
import logging
import os
import asyncio
from datetime import datetime, date, timedelta
from typing import Optional
```

### الدوال المطلوبة:

---

### 2.1 `_conn()` — اتصال DB
```python
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c
```

---

### 2.2 `init_review_schema()` — إنشاء الجدول
- تنفذ CREATE TABLE IF NOT EXISTS من القسم 1 أعلاه
- تُستدعى عند أول استخدام

---

### 2.3 `_last_trading_day(ref_date=None)` — آخر يوم تداول
```
المنطق:
- ref_date افتراضي = اليوم
- إذا ref_date يوم جمعة (4) → ارجع الخميس
- إذا ref_date يوم سبت (5) → ارجع الخميس  
- (KSE: أحد-خميس = 0-4 weekday بتوقيت الكويت)
- ملاحظة: datetime.weekday(): Mon=0 ... Sun=6
  لكن KSE: Sun-Thu, so:
    Friday = weekday() 4  → ارجع Thursday (weekday 3)
    Saturday = weekday() 5 → ارجع Thursday (weekday 3)
    
  تحقق: استخدم نفس منطق kse_data_collector.py
  KWT = UTC+3, الكود يعمل بـ UTC على RPi
```

---

### 2.4 `_get_pending_decisions(market_date: str) -> list[dict]`
```
المنطق:
- يسحب من decision_audit كل القرارات حيث:
    market_date = market_date المعطى
    smart_decision = 'ENTER'
    outcome = 'pending'
- يرجع list of dicts مع كل الأعمدة المطلوبة

SQL:
SELECT id, symbol, smart_decision, chosen_plan_source, strategy_id,
       entry_price, stop_price, target_1, target_2, rr_ratio,
       confidence, data_quality, risk_flags, sector, strategy_ev
FROM decision_audit
WHERE market_date = ? AND smart_decision = 'ENTER'
ORDER BY confidence DESC
```

---

### 2.5 `_get_next_day_bars(symbol: str, after_date: str) -> dict | None`
```
المنطق:
- يسحب من daily_bars أول يوم تداول بعد after_date للسهم المحدد

SQL:
SELECT trading_date, open, high, low, close, volume
FROM daily_bars
WHERE symbol = ? AND trading_date > ?
ORDER BY trading_date ASC
LIMIT 1

- إذا ما لقى شيء → return None (البيانات مو متوفرة بعد)
```

---

### 2.6 `_classify_result(decision: dict, bar: dict) -> dict`
```
المنطق الأساسي:
- entry = decision['entry_price']
- stop = decision['stop_price']
- t1 = decision['target_1']
- t2 = decision['target_2']
- high = bar['high']
- low = bar['low']
- close = bar['close']

# حساب الأرقام
pnl_pct = ((close - entry) / entry) * 100
max_favorable = ((high - entry) / entry) * 100
max_adverse = ((entry - low) / entry) * 100

# ✅ نجاح: high وصل أو تجاوز target_1
hit_t1 = high >= t1 if t1 else False
hit_stop = low <= stop if stop else False

# التصنيف:
if hit_t1:
    result = 'success'
elif hit_stop:
    result = 'fail'
elif pnl_pct > 0:
    # تحرك بالاتجاه الصحيح لكن ما وصل الهدف
    result = 'partial'
elif pnl_pct <= -3.0:
    # خسارة كبيرة بدون ضرب ستوب رسمي
    result = 'fail'
else:
    # ما تحرك كثير أو حركة سلبية بسيطة
    result = 'ongoing'  # لسه ما حسم

return {
    'result': result,
    'pnl_pct': round(pnl_pct, 2),
    'max_favorable': round(max_favorable, 2),
    'max_adverse': round(max_adverse, 2),
    'hit_target_1': hit_t1,
    'hit_stop': hit_stop,
}
```

---

### 2.7 `_analyze_reason(decision: dict, bar: dict, result: str) -> dict`
```
المنطق — تحليل سبب الفشل أو النجاح:

error_type = 'none'
reason_ar = ''
lesson_ar = ''

if result == 'success':
    error_type = 'none'
    reason_ar = 'الإشارة نجحت — وصل الهدف الأول'
    if bar['high'] >= decision.get('target_2', 999999):
        reason_ar = 'الإشارة نجحت — وصل الهدف الثاني!'
    lesson_ar = 'نمط ناجح — يستحق التكرار'

elif result == 'fail':
    # تحليل السبب:
    
    # 1. حجم ضعيف
    # نقارن volume اليوم التالي بمتوسط الحجم (من daily_bars آخر 20 يوم)
    avg_vol = _get_avg_volume(decision['symbol'], bar['trading_date'], 20)
    vol_ratio = bar['volume'] / avg_vol if avg_vol > 0 else 0
    
    if vol_ratio < 0.8:
        error_type = 'volume'
        reason_ar = f'الحجم ضعيف ({vol_ratio:.1f}x) — ما أكّد الحركة'
        lesson_ar = 'لا تدخل بدون تأكيد الحجم (> 1.0x المتوسط)'
    
    # 2. ستوب قريب جداً
    elif decision.get('stop_price') and decision.get('entry_price'):
        stop_dist = abs(decision['entry_price'] - decision['stop_price']) / decision['entry_price'] * 100
        if stop_dist < 1.5:
            error_type = 'stop'
            reason_ar = f'الستوب قريب جداً ({stop_dist:.1f}%) — ضربه بتذبذب عادي'
            lesson_ar = 'وسّع الستوب — استخدم ATR بدل نسبة ثابتة'
    
    # 3. دخول بمنطقة غلط (السعر كان فوق المقاومة أو بعيد عن الدعم)
    # نتحقق: هل entry كان قريب من الهاي؟
    elif bar.get('high') and decision.get('entry_price'):
        # إذا الإنتري كان في أعلى 20% من رينج اليوم = دخول عالي
        day_range = bar['high'] - bar['low']
        if day_range > 0:
            entry_position = (decision['entry_price'] - bar['low']) / day_range
            if entry_position > 0.8:
                error_type = 'zone'
                reason_ar = 'الدخول كان بمنطقة مرتفعة — قريب من المقاومة'
                lesson_ar = 'انتظر pullback قبل الدخول'

    # 4. نمط ضعيف (win rate الاستراتيجية < 55%)
    if not error_type or error_type == 'none':
        strat_id = decision.get('strategy_id')
        if strat_id:
            strat = _get_strategy_stats(strat_id)
            if strat and strat.get('profitable_rate', 0) < 0.55:
                error_type = 'pattern'
                rate = strat['profitable_rate'] * 100
                reason_ar = f'نمط ضعيف — نسبة النجاح {rate:.0f}% فقط'
                lesson_ar = 'تجنب الاستراتيجيات بنسبة نجاح أقل من 55%'

    # 5. السوق ككل نزل
    if not error_type or error_type == 'none':
        market_drop = _check_market_drop(bar['trading_date'])
        if market_drop:
            error_type = 'market'
            reason_ar = 'السوق ككل نزل — ضغط بيع عام'
            lesson_ar = 'راقب المؤشر العام قبل الدخول'

    # 6. فولباك عام
    if not error_type or error_type == 'none':
        error_type = 'trend'
        reason_ar = 'الاتجاه عكس — الحركة لم تستمر'
        lesson_ar = 'تأكد من الاتجاه العام (ADX + EMA) قبل الدخول'

elif result == 'partial':
    error_type = 'none'
    pnl = ((bar['close'] - decision['entry_price']) / decision['entry_price']) * 100
    reason_ar = f'تحرك بالاتجاه الصحيح (+{pnl:.1f}%) لكن ما وصل الهدف'
    lesson_ar = 'خذ أرباح جزئية عند مستوى مناسب'

elif result == 'ongoing':
    error_type = 'none'
    reason_ar = 'الإشارة لسه مستمرة — ما وصل هدف ولا ستوب'
    lesson_ar = 'راقب وحدد نقطة خروج واضحة'

return {
    'error_type': error_type,
    'reason_ar': reason_ar,
    'lesson_ar': lesson_ar,
}
```

---

### 2.8 دوال مساعدة

#### `_get_avg_volume(symbol, before_date, days=20) -> float`
```
SQL:
SELECT AVG(volume) FROM daily_bars
WHERE symbol = ? AND trading_date < ?
ORDER BY trading_date DESC LIMIT ?

ملاحظة: daily_bars حالياً فيه 128 سهم ليوم واحد فقط (30 مارس).
إذا ما لقى بيانات كافية → return 0 (يعني ما يقدر يحكم على الحجم)
مستقبلاً: بعد ما يتراكم daily_bars لأيام متعددة، هالدالة بتصير أقوى.
```

#### `_get_strategy_stats(strategy_id) -> dict | None`
```
SQL:
SELECT profitable_rate, sample_size, ev, stop_pct, target_1_pct
FROM mined_strategies
WHERE strategy_id = ?
```

#### `_check_market_drop(trading_date) -> bool`
```
المنطق:
- نسحب بيانات أكثر الأسهم سيولة (مثلاً أول 20 سهم بالحجم)
- نحسب: كم سهم أغلق أقل من فتحه؟
- إذا أكثر من 70% → السوق ككل نازل = True

SQL:
SELECT 
    COUNT(CASE WHEN close < open THEN 1 END) as down_count,
    COUNT(*) as total
FROM daily_bars
WHERE trading_date = ?
AND volume > 0

market_drop = (down_count / total) > 0.70 if total > 10 else False
```

---

### 2.9 `review_signals(target_date: str = None) -> dict` — الدالة الرئيسية
```
المنطق:
1. init_review_schema()
2. target_date = target_date أو _last_trading_day()
3. review_date = اليوم
4. decisions = _get_pending_decisions(target_date)
5. إذا فاضي → return {"status": "no_decisions", "date": target_date}

6. لكل decision:
   a. bar = _get_next_day_bars(decision['symbol'], target_date)
   b. إذا bar == None:
      - result = 'no_data', سبب: 'بيانات اليوم التالي مو متوفرة'
      - سجل بـ signal_reviews مع result='no_data'
      - continue
   c. classification = _classify_result(decision, bar)
   d. analysis = _analyze_reason(decision, bar, classification['result'])
   e. INSERT OR REPLACE into signal_reviews
   f. UPDATE decision_audit SET outcome = classification['result'],
      outcome_date = review_date,
      actual_gain_pct = classification['pnl_pct']
      WHERE id = decision['id']

7. جمع الإحصائيات:
   results = {
       'success': count,
       'partial': count,
       'fail': count,
       'ongoing': count,
       'no_data': count,
   }
   
   # أكبر خطأ متكرر
   error_counts = Counter([r['error_type'] for r in all_reviews if r['result'] == 'fail'])
   top_error = error_counts.most_common(1)[0] if error_counts else None

8. return {
       'status': 'ok',
       'review_date': review_date,
       'market_date': target_date,
       'total_reviewed': len(decisions),
       'results': results,
       'top_error': top_error,
       'reviews': all_reviews,  # القائمة الكاملة
   }
```

---

### 2.10 `_send_review_telegram(summary: dict) -> bool`
```
المنطق:
- يستخدم نفس نمط _send_collection_alert من kse_data_collector.py
- يقرأ bot_token و chat_id من الملفات أو env vars

الرسالة:
📊 <b>تقييم إشارات {market_date}</b>

✅ نجاح: {success}
⚠️ جزئي: {partial}
❌ فشل: {fail}
⏳ مستمر: {ongoing}

📈 نسبة النجاح: {success_rate}%
💡 أكبر خطأ: {top_error_ar}

— أفضل إشارة: {best_symbol} (+{best_pnl}%)
— أسوأ إشارة: {worst_symbol} ({worst_pnl}%)

ملاحظة:
- top_error_ar يترجم error_type:
    volume → دخول بدون تأكيد حجم
    trend → الاتجاه عكس
    zone → دخول بمنطقة غلط
    stop → ستوب قريب
    market → السوق ككل نزل
    pattern → نمط ضعيف

- parse_mode='HTML'
- يستخدم requests.post مثل kse_data_collector._send_collection_alert
```

---

### 2.11 `async def review_scheduler()` — الـ Scheduler
```
المنطق:
- يعمل بنفس نمط daily_collection_scheduler من kse_data_collector.py
- الوقت: 2:00 PM Kuwait = 11:00 UTC (30 دقيقة بعد جمع البيانات)
- يتخطى الجمعة والسبت

while True:
    now = datetime.utcnow()
    kwt = now + timedelta(hours=3)
    
    # Target: 2:00 PM KWT = 11:00 UTC
    target = now.replace(hour=11, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    
    # Skip Friday(4) and Saturday(5) in KWT weekday
    kwt_target = target + timedelta(hours=3)
    while kwt_target.weekday() in (4, 5):  # Fri, Sat
        target += timedelta(days=1)
        kwt_target = target + timedelta(hours=3)
    
    wait_secs = (target - now).total_seconds()
    logger.info("Next signal review in %.1f hours", wait_secs / 3600)
    await asyncio.sleep(wait_secs)
    
    try:
        summary = review_signals()  # يراجع إشارات آخر يوم تداول
        if summary.get('status') == 'ok':
            _send_review_telegram(summary)
            logger.info("Signal review complete: %s", summary['results'])
        else:
            logger.info("No decisions to review: %s", summary)
    except Exception as e:
        logger.error("Signal review failed: %s", e, exc_info=True)
```

---

## 3. التكامل مع server.py

### 3.1 Import في server.py
```python
# أضف مع imports التداول (حوالي سطر 40-60):
try:
    from signal_review import review_signals, review_scheduler, init_review_schema
    REVIEW_OK = True
except Exception as e:
    logger.warning("signal_review import failed: %s", e)
    REVIEW_OK = False
```

### 3.2 Endpoints جديدة في server.py
```python
# GET /dashboard/reviews — لصفحة الداشبورد
@app.get("/dashboard/reviews")
async def dashboard_reviews(date: str = None):
    """Signal review results for dashboard."""
    if not REVIEW_OK:
        return {"error": "signal_review not loaded"}
    
    from signal_review import get_reviews_for_dashboard
    return get_reviews_for_dashboard(date)

# POST /api/review-now — تشغيل يدوي
@app.post("/api/review-now")
async def manual_review(date: str = None):
    """Manually trigger signal review."""
    if not REVIEW_OK:
        return {"error": "signal_review not loaded"}
    
    summary = review_signals(date)
    return summary
```

### 3.3 تشغيل Scheduler في server.py
```python
# في startup_event() (حوالي سطر 2590):
if REVIEW_OK:
    asyncio.create_task(review_scheduler())
    logger.info("Signal review scheduler started")
```

### 3.4 دالة `get_reviews_for_dashboard(date=None) -> dict`
```python
# في signal_review.py — يرجع البيانات بشكل جاهز للداشبورد

def get_reviews_for_dashboard(date: str = None) -> dict:
    """Return reviews formatted for dashboard HTML page."""
    init_review_schema()
    
    if not date:
        # آخر تاريخ فيه مراجعات
        with _conn() as c:
            row = c.execute(
                "SELECT MAX(review_date) FROM signal_reviews"
            ).fetchone()
            date = row[0] if row and row[0] else None
    
    if not date:
        return {"reviews": [], "summary": {}, "date": None}
    
    with _conn() as c:
        rows = c.execute("""
            SELECT * FROM signal_reviews
            WHERE review_date = ?
            ORDER BY 
                CASE result 
                    WHEN 'success' THEN 1 
                    WHEN 'partial' THEN 2 
                    WHEN 'ongoing' THEN 3 
                    WHEN 'fail' THEN 4 
                    WHEN 'no_data' THEN 5 
                END,
                pnl_pct DESC
        """, (date,)).fetchall()
    
    reviews = [dict(r) for r in rows]
    
    # ملخص
    results = {}
    for r in reviews:
        res = r.get('result', 'unknown')
        results[res] = results.get(res, 0) + 1
    
    total = len(reviews)
    success = results.get('success', 0)
    rate = round(success / total * 100) if total > 0 else 0
    
    # أكثر خطأ تكراراً
    from collections import Counter
    errors = Counter(r['error_type'] for r in reviews 
                     if r.get('result') == 'fail' and r.get('error_type'))
    top_error = errors.most_common(1)[0] if errors else None
    
    # أفضل وأسوأ
    sorted_pnl = sorted([r for r in reviews if r.get('pnl_pct') is not None], 
                         key=lambda x: x['pnl_pct'])
    best = sorted_pnl[-1] if sorted_pnl else None
    worst = sorted_pnl[0] if sorted_pnl else None
    
    return {
        "date": date,
        "total": total,
        "success_rate": rate,
        "results": results,
        "top_error": {
            "type": top_error[0] if top_error else None,
            "count": top_error[1] if top_error else 0,
        },
        "best": {"symbol": best['symbol'], "pnl": best['pnl_pct']} if best else None,
        "worst": {"symbol": worst['symbol'], "pnl": worst['pnl_pct']} if worst else None,
        "reviews": reviews,
    }
```

---

## 4. ملاحظات مهمة للتنفيذ

### 4.1 تسلسل الأحداث اليومي:
```
1:00 PM KWT → السوق يُغلق
1:30 PM KWT → kse_data_collector.py يجمع بيانات اليوم (daily_bars)
2:00 PM KWT → signal_review.py يراجع إشارات أمس (30 دقيقة بعد الجمع)
```

### 4.2 الحالة الأولية:
- حالياً `decision_audit` فيه 11 قرار ENTER من 30 مارس، كلهم pending
- `daily_bars` فيه 128 سهم ليوم 30 مارس فقط
- **أول مراجعة فعلية:** يوم 31 مارس (أحد) — يراجع إشارات 30 مارس مقابل أسعار 31 مارس
- إذا شغلنا المراجعة اليوم 30 مارس → ما بيلقى بيانات "next day" → كل شيء no_data

### 4.3 متعدد الأيام (مستقبلي):
- الإشارات اللي نتيجتها 'ongoing' يجب تتبعها لأيام إضافية
- حالياً نبدأ بيوم واحد فقط (T+1)
- مستقبلاً: نضيف tracking لـ T+2, T+3 (نزيد days_tracked)

### 4.4 قيود البيانات:
- `_get_avg_volume` ما بتشتغل صح إلا بعد تراكم بيانات عدة أيام
- في البداية: نعتمد على التصنيف الأساسي (hit_target / hit_stop / pnl)
- تحليل السبب المتقدم (volume/zone) بيتحسن مع تراكم البيانات

### 4.5 backward compatibility:
- لا تعدل على decision_audit schema — فقط UPDATE outcome/outcome_date/actual_gain_pct
- لا تعدل على daily_bars — read only
- الجدول الجديد signal_reviews منفصل تماماً

---

## 5. اختبار بعد التنفيذ

```bash
# 1. تحقق من syntax
python3 _tools/quick_check.py

# 2. تشغيل يدوي (سيرجع no_data لأنه ما فيه بيانات T+1 بعد)
python3 -c "from signal_review import review_signals; print(review_signals('2026-03-30'))"

# 3. تحقق من الجدول
sqlite3 data/life.db "SELECT COUNT(*) FROM signal_reviews;"

# 4. smoke test
python3 _tools/smoke_test.py

# 5. restart
bash _tools/restart_master_ai.sh

# 6. تحقق من endpoints
curl -s http://localhost:9000/dashboard/reviews | python3 -m json.tool
curl -s -X POST http://localhost:9000/api/review-now | python3 -m json.tool
```

---

## 6. صفحة reviews.html — مسؤولية claude.ai
سيتم بناؤها في محادثة منفصلة. الـ endpoint جاهز: `GET /dashboard/reviews`

الصفحة تعرض:
- ملخص: نجاح/فشل/جزئي مع نسبة
- فلاتر: كل النتائج / نجاح / فشل / جزئي / مستمر
- كارد لكل إشارة: السهم + القرار + النتيجة + السبب + الدرس
- أفضل وأسوأ إشارة
- نمط الخطأ الأكثر تكراراً

---

## 7. ملخص الملفات

| ملف | العملية | المنفذ |
|------|---------|--------|
| `signal_review.py` | **ملف جديد** — المحرك الكامل | Claude Code |
| `server.py` | إضافة import + endpoints + scheduler | Claude Code |
| `reviews.html` | **ملف جديد** — صفحة الداشبورد | claude.ai (محادثة ثانية) |
| `master_ai_dashboard.yaml` | إضافة iframe view لـ reviews | claude.ai |
| `CLAUDE_CONTEXT.md` | تحديث بالمحرك الجديد | Claude Code |

---

## 8. git commit message
```
feat: Signal Review Engine — daily ENTER decision evaluation

- New signal_review.py: daily review of ENTER decisions from decision_audit
- New table: signal_reviews (result/reason/lesson/pnl tracking)
- Classification: success/partial/fail/ongoing/no_data
- Root cause analysis: volume/trend/zone/stop/market/pattern
- Scheduler: 2:00 PM KWT daily (30min after data collection)
- Telegram summary: daily review digest
- Endpoints: GET /dashboard/reviews, POST /api/review-now
- Updates decision_audit.outcome on review
```
