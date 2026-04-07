# Fix: التيليقرام ما يرسل — TELEGRAM_CHAT_ID مو موجود
# التاريخ: 2026-03-30
# المنفذ: Claude Code

## المشكلة
`_send_review_telegram()` في signal_review.py سطر 554 يدور:
- `TELEGRAM_CHAT_ID` ← **مو موجود** بالـ .env
- `~/.telegram_chat_id` ← **الملف مو موجود**
→ يرجع False بدون إرسال!

الموجود بالـ .env: `ADMIN_TELEGRAM_ID=669769765`

**نفس المشكلة** موجودة بـ kse_data_collector.py سطر 403!

## الحل

### تعديل signal_review.py سطر ~554:

```python
# القديم:
chat_id = os.environ.get("TELEGRAM_CHAT_ID") or _read_file("~/.telegram_chat_id")

# الجديد:
chat_id = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("ADMIN_TELEGRAM_ID") or _read_file("~/.telegram_chat_id")
```

### تعديل kse_data_collector.py سطر ~403 (نفس الفكس):

```python
# القديم:
chat_id = os.environ.get("TELEGRAM_CHAT_ID") or _read_file("~/.telegram_chat_id")

# الجديد:
chat_id = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("ADMIN_TELEGRAM_ID") or _read_file("~/.telegram_chat_id")
```

## بعد التنفيذ:
```bash
python3 _tools/quick_check.py
sudo systemctl restart master-ai

# اختبار فوري:
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from signal_review import _send_review_telegram
result = _send_review_telegram({
    'market_date': '2026-03-29',
    'total_reviewed': 3,
    'results': {'partial': 2, 'ongoing': 1},
    'top_error': None,
    'reviews': [
        {'symbol': 'ALDEERA', 'result': 'partial', 'pnl_pct': 1.58},
        {'symbol': 'NBK', 'result': 'partial', 'pnl_pct': 1.05},
        {'symbol': 'INOVEST', 'result': 'ongoing', 'pnl_pct': -0.68},
    ]
})
print('Telegram sent:', result)
"
```
