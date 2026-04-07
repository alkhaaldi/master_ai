# Fix: تنبيهات الفرص الذهبية ما توصل — ثغرتين
# التاريخ: 2026-03-30
# المنفذ: Claude Code

## المشكلة 1: TELEGRAM_CHAT_ID ناقص بـ golden_engine.py
سطر ~626: نفس مشكلة signal_review — يدور TELEGRAM_CHAT_ID اللي مو موجود.
alert_history فيه 0 سجلات = ما أرسل ولا تنبيه من يوم ما بنينا النظام!

### الحل:
```python
# سطر ~626 في golden_engine.py - القديم:
chat_id = os.environ.get("TELEGRAM_CHAT_ID") or _read_file("~/.telegram_chat_id")

# الجديد:
chat_id = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("ADMIN_TELEGRAM_ID") or _read_file("~/.telegram_chat_id")
```

## المشكلة 2: scan_opportunities ما يشتغل وقت السوق
حالياً scan_opportunities يشتغل:
- لما أحد يفتح صفحة القرارات (يدوي)
- مرة وحدة الساعة 1:30م بعد جمع البيانات (الفيكس اللي سويناه)

لكن الفرص تظهر **وقت السوق** (9:00ص - 1:00م) — لازم يسوي scan دوري.

### الحل:
أضف في daily_collection_scheduler أو أنشئ scheduler جديد يشتغل كل 15 دقيقة وقت السوق:

```python
# أضف بعد الـ daily_collection_scheduler في kse_data_collector.py:

async def market_hours_scanner():
    """Scan for golden opportunities every 15 min during market hours."""
    import asyncio
    _log = logging.getLogger("market_scanner")
    _log.info("Market hours scanner started")
    await asyncio.sleep(120)  # let startup complete

    while True:
        try:
            now = datetime.utcnow()
            kwt = now + timedelta(hours=3)
            
            # KSE: Sun-Thu, 9:00 AM - 1:00 PM KWT
            is_trading_day = kwt.weekday() not in (4, 5)  # not Fri/Sat
            is_market_hours = 9 <= kwt.hour < 13
            
            if is_trading_day and is_market_hours:
                _log.info("Market open — scanning opportunities...")
                loop = asyncio.get_event_loop()
                try:
                    from golden_engine import scan_opportunities
                    result = await loop.run_in_executor(None, scan_opportunities)
                    enter_count = result.get("enter_count", 0)
                    _log.info("Scan: %d ENTER from %d stocks", enter_count, result.get("total_scanned", 0))
                except Exception as e:
                    _log.warning("Scan failed: %s", e)
                
                await asyncio.sleep(900)  # 15 minutes
            else:
                # Outside market hours — check every 30 min
                await asyncio.sleep(1800)
                
        except Exception as e:
            _log.error("Market scanner error: %s", e, exc_info=True)
            await asyncio.sleep(300)
```

### تشغيل في server.py:
```python
# بعد سطر daily_collection_scheduler (حوالي 2613):
try:
    from kse_data_collector import market_hours_scanner
    asyncio.create_task(market_hours_scanner())
    logger.info("Market hours scanner started (every 15 min)")
except Exception as _e:
    logger.warning("Market hours scanner not loaded: %s", _e)
```

## التسلسل الجديد:
```
9:00 ص - 1:00 م (وقت السوق):
  كل 15 دقيقة → scan_opportunities() → يسجل ENTER + يرسل تنبيه تيليقرام فوري

1:30 م (بعد الإغلاق):
  → collect_daily_bars() → يجمع بيانات نهاية اليوم
  → scan_opportunities() → آخر scan بالبيانات النهائية

2:00 م:
  → review_signals() → يقيّم إشارات أمس
```

## بعد التنفيذ:
```bash
python3 _tools/quick_check.py
sudo systemctl restart master-ai

# تحقق (وقت السوق):
# انتظر 15 دقيقة وشوف هل وصلتك رسالة
# أو شغّل يدوي:
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from golden_engine import scan_opportunities
r = scan_opportunities()
print('Enter:', r.get('enter_count'), 'Alerts:', r.get('alerts_sent', 0))
"
```
