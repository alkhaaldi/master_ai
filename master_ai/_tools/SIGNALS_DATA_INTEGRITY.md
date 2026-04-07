# تحسين صفحة الإشارات (المصفوفة) كمرجع موثوق
# الملف: signals.html (في HA iframe)
# المنفذ: Claude Code

---

## المشكلة
صفحة المصفوفة (signals.html) تعرض بيانات 128 سهم بس:
1. ما تعرض متى هالبيانات اتحسبت
2. ما تفرّق بين بيانات طازة وقديمة
3. الـ `daily_context` يتحسب من البردج بس — إذا البردج مطفي البيانات تبقى قديمة بدون تنبيه

## المطلوب

### 1. أضف `data_age_hours` و `updated_at` للـ radar endpoint

في `/dashboard/radar` — الـ `radar_daily_context` أصلاً فيه `updated_at` و `data_age_hours` و `is_stale`.
تأكد إن كل سهم يرجع هالحقول:
```python
{
    "updated_at": "2026-03-29T06:38:44",
    "data_age_hours": 12.9,
    "is_stale": false  # true إذا أكثر من 24 ساعة
}
```

### 2. عدّل منطق `is_stale` ليكون أدق:
```python
def compute_staleness(updated_at):
    age_hours = (datetime.utcnow() - updated_at).total_seconds() / 3600
    return {
        'data_age_hours': round(age_hours, 1),
        'is_stale': age_hours > 18,  # قديم إذا أكثر من 18 ساعة (يوم تداول + فترة)
        'freshness': 'fresh' if age_hours < 6 else 'aging' if age_hours < 18 else 'stale'
    }
```

### 3. أضف endpoint `/api/data-freshness` (إذا مو موجود):
يرجع:
```json
{
    "last_radar_update": "2026-03-29T06:38:44",
    "age_hours": 12.9,
    "is_stale": false,
    "bridge_online": false,
    "total_stocks_with_data": 128,
    "stocks_with_stale_data": 0
}
```

### 4. تأكد إن `refresh_daily_snapshot()` يحدّث `updated_at` بشكل صحيح

وإن كل الحقول في `stock_radar_daily` محسوبة من أرقام حقيقية (مو null أو صفر بدون سبب).

## ملاحظة
signals.html (المصفوفة) هذا ملف HTML في www/trading/ — أنا (claude.ai) بعدّله عشان يعرض الطزاجة.
كلاود كود يتأكد إن الـ backend يرجع البيانات صح.

## ترتيب:
1. Claude Code: تحقق من `refresh_daily_snapshot()` وتأكد `updated_at` + `data_age_hours` + `is_stale` ترجع صح
2. Claude Code: أضف `/api/data-freshness` إذا مو موجود
3. Claude Code: restart + smoke test + git commit
