# Telegram Cleanup Plan — April 2026
# Claude Code: اقرأ هذا الملف ونفذ الخطوات

## المشكلة 1: تكرار tg_alert_loop (server.py)

### الوضع الحالي:
- **سطر ~2659** (في TG_ALERTS_OK): `asyncio.create_task(tg_alert_loop(_alert_sender))`
- **سطر ~2689** (في TG_NEWS_OK): `asyncio.create_task(tg_alert_loop(_stock_sender))`
- نفس الـ `tg_alert_loop` مستدعى مرتين = تنبيهات مكررة!

### الإصلاح:
احذف السطر في TG_NEWS_OK block:
```python
# قبل (سطر ~2689):
asyncio.create_task(tg_alert_loop(_stock_sender))  # ← احذف هذا
asyncio.create_task(news_scheduler(_news_sender))   # ← هذا يبقى

# بعد:
asyncio.create_task(news_scheduler(_news_sender))
```

## المشكلة 2: proactive_suggestion_loop — تحقق

### التحقق:
1. `grep -n "proactive_suggestion_loop" server.py` — شوف التعريف
2. `grep -n "proactive_suggestion_loop" *.py` — شوف إذا مستخدم
3. شيك اللوقز: هل يرسل رسائل فعلياً؟
4. إذا ما يرسل شي مفيد ← علّق عليه (لا تحذفه)

### إذا قررت تعلّقه:
```python
# سطر ~2660-2661:
# asyncio.create_task(proactive_suggestion_loop(_alert_sender))
# logger.info("Proactive suggestions loop scheduled")
```

## بعد التعديل:
1. `python3 _tools/quick_check.py`
2. `python3 _tools/smoke_test.py`
3. `git add -A && git commit -m "fix: remove duplicate tg_alert_loop, check proactive_suggestion_loop"`
4. `bash _tools/restart_master_ai.sh`
5. تأكد من اللوقز
