# Fix: تسجيل الإشارات تلقائياً بعد جمع البيانات اليومي
# التاريخ: 2026-03-30
# المنفذ: Claude Code

## المشكلة الحرجة
`log_decision()` يُستدعى فقط من `scan_opportunities()` اللي يُستدعى فقط من
endpoint `/api/decisions-now`. يعني لو ما أحد فتح صفحة القرارات بعد الساعة 1:30 م،
**ما بتتسجل إشارات جديدة** بـ `decision_audit` → و signal_review ما بيلقى شيء يقيّمه!

## الحل

### تعديل `daily_collection_scheduler()` في kse_data_collector.py

بعد سطر `_send_collection_alert(result)` (حوالي سطر 487)، أضف:

```python
            # Phase 4: Auto-scan opportunities to log ENTER decisions
            try:
                from golden_engine import scan_opportunities
                scan_result = await loop.run_in_executor(None, scan_opportunities)
                enter_count = scan_result.get("enter_count", 0)
                total = scan_result.get("total_scanned", 0)
                _log.info("Auto-scan: %d ENTER decisions from %d stocks", enter_count, total)
            except Exception as _e:
                _log.warning("Auto-scan opportunities failed: %s", _e)
```

### التسلسل الجديد:
```
1:30 م → collect_and_refresh() → daily_bars + refresh_daily_snapshot
       → scan_opportunities() → يسجل كل ENTER بـ decision_audit  ← جديد
       → _send_collection_alert() → تيليقرام
       → run_daily_monitor() → position alerts

2:00 م → review_signals() → يقيّم إشارات أمس
       → _send_review_telegram() → ملخص التقييم
```

## بعد التنفيذ:
```bash
python3 _tools/quick_check.py
sudo systemctl restart master-ai
```

## تحقق:
بعد يوم تداول، تحقق:
```bash
sqlite3 data/life.db "SELECT market_date, COUNT(*) FROM decision_audit GROUP BY market_date ORDER BY market_date DESC LIMIT 5;"
```
لازم يكون فيه سجلات جديدة لكل يوم تداول.
