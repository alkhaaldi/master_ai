# Fix: Signal Review — _last_trading_day() يرجع اليوم بدل أمس
# التاريخ: 2026-03-30
# المنفذ: Claude Code

## المشكلة
`_last_trading_day()` يرجع **اليوم** (30 مارس) بدل **أمس** (29 مارس).
المفروض يراجع إشارات **أمس** ويقارنها بأسعار **اليوم**.

## الحل

### تعديل 1: `_last_trading_day()` في signal_review.py

```python
# القديم:
def _last_trading_day(ref_date=None):
    d = ref_date or date.today()
    ...
    while d.weekday() in (4, 5):
        d -= timedelta(days=1)
    return d.isoformat()

# الجديد:
def _last_trading_day(ref_date=None):
    """Return last KSE trading day BEFORE today (or before ref_date)."""
    d = ref_date or date.today()
    if isinstance(d, str):
        d = datetime.strptime(d, "%Y-%m-%d").date()
    # Go back one day first (we want YESTERDAY's signals)
    d -= timedelta(days=1)
    # Skip Fri(4) and Sat(5)
    while d.weekday() in (4, 5):
        d -= timedelta(days=1)
    return d.isoformat()
```

### تعديل 2: `review_signals()` — أيضاً مراجعة كل الأيام pending

الدالة الحالية تراجع يوم واحد فقط. إضافة دالة `review_all_pending()`:

```python
def review_all_pending() -> list:
    """Review ALL pending decision_audit entries that have next-day bars available."""
    init_review_schema()
    with _conn() as c:
        # Find all distinct market_dates with pending decisions
        dates = c.execute("""
            SELECT DISTINCT market_date FROM decision_audit
            WHERE outcome = 'pending'
            ORDER BY market_date
        """).fetchall()
    
    results = []
    for row in dates:
        md = row[0]
        summary = review_signals(md)
        results.append(summary)
    return results
```

### تعديل 3: endpoint `/api/review-now` — إضافة `?all=true`

```python
@app.post("/api/review-now")
async def manual_review(date: str = None, all: bool = False):
    if not REVIEW_OK:
        return {"error": "signal_review not loaded"}
    if all:
        from signal_review import review_all_pending
        return {"results": review_all_pending()}
    return review_signals(date)
```

## بعد التنفيذ:

```bash
# 1. Quick check
python3 _tools/quick_check.py

# 2. Restart
sudo systemctl restart master-ai

# 3. شغّل المراجعة لكل الأيام المعلقة
curl -s -X POST "http://localhost:9000/api/review-now?all=true" | python3 -m json.tool

# 4. تحقق — لازم يراجع 29 مارس (3 إشارات) مقابل أسعار 30 مارس
sqlite3 data/life.db "SELECT review_date, market_date, symbol, result, pnl_pct FROM signal_reviews ORDER BY market_date, symbol;"
```

## ملاحظة مهمة:
- إشارات 29 مارس (ALDEERA, INOVEST, NBK) عندها daily_bars لـ 30 مارس → **يقدر يقيّمها فعلاً**
- إشارات 30 مارس ما عندها T+1 بعد → تبقى no_data حتى 31 مارس
- signal_reviews الحالية (8 rows من 30 مارس كلها no_data) → حذفها أو تحديثها


---

## Fix إضافي: get_reviews_for_dashboard() يفلتر بـ review_date بدل market_date

### المشكلة
سطر 461 في signal_review.py:
```python
WHERE review_date = ?
```
المستخدم يبي يشوف إشارات **أمس** = `market_date`، مو يوم المراجعة.

### الحل
غيّر سطر 451 و 461:

```python
# سطر ~451: MAX query
row = c.execute(
    "SELECT MAX(market_date) FROM signal_reviews"
).fetchone()

# سطر ~461: main query
WHERE market_date = ?
```

### أيضاً: default date
في `get_reviews_for_dashboard()`: إذا `date` فاضي، يسحب `MAX(market_date)` بدل `MAX(review_date)`.

### تنفيذ فوري:
```bash
cd /home/pi/master_ai
# Fix line ~451
sed -i 's/SELECT MAX(review_date) FROM signal_reviews/SELECT MAX(market_date) FROM signal_reviews/' signal_review.py
# Fix line ~461
sed -i 's/WHERE review_date = ?/WHERE market_date = ?/' signal_review.py
# Quick check + restart
python3 _tools/quick_check.py && sudo systemctl restart master-ai
```

بعد هالفيكس: `/dashboard/reviews?date=2026-03-29` بيرجع 3 إشارات (ALDEERA, INOVEST, NBK).
