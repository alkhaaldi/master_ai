# Fix: Default date يعرض آخر يوم فيه نتائج حقيقية
# التاريخ: 2026-03-30
# المنفذ: Claude Code

## المشكلة
`get_reviews_for_dashboard()` يسحب `MAX(market_date)` = 2026-03-30 (كلها no_data).
المستخدم يبي يشوف **آخر يوم فيه نتائج فعلية** = 2026-03-29 (partial/ongoing).

## الحل

### تعديل `get_reviews_for_dashboard()` في signal_review.py

**سطر ~452** — غيّر الـ default query:

```python
# القديم:
row = c.execute(
    "SELECT MAX(market_date) FROM signal_reviews"
).fetchone()

# الجديد — أولوية لآخر يوم فيه نتائج حقيقية:
row = c.execute(
    "SELECT MAX(market_date) FROM signal_reviews WHERE result NOT IN ('no_data', 'pending')"
).fetchone()
# إذا ما لقى نتائج حقيقية، fallback لأي يوم
if not row or not row[0]:
    row = c.execute(
        "SELECT MAX(market_date) FROM signal_reviews"
    ).fetchone()
```

## بعد التنفيذ:
```bash
python3 _tools/quick_check.py && sudo systemctl restart master-ai
```

النتيجة: `/dashboard/reviews` بدون date → يعرض 2026-03-29 (3 إشارات بنتائج حقيقية)
