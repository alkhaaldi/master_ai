# Fix: أوامر /فرص و /تقييم تعمل timeout + choose_model خطأ import
# التاريخ: 2026-03-30
# المنفذ: Claude Code

## المشاكل:

### 1. timeout 3 ثوانٍ على tg_handle_command
سطر 6844 في server.py:
```python
quick = await asyncio.wait_for(tg_handle_command(chat_id, text), timeout=3)
```
`/فرص` يستدعي `scan_opportunities()` اللي يسحب 128 سهم — يحتاج أكثر من 3 ثوانٍ.
يعمل timeout → يسقط للـ Stage 4 → يفشل بالـ import error.

**الحل:** زيّد الـ timeout لـ 30 ثانية:
```python
quick = await asyncio.wait_for(tg_handle_command(chat_id, text), timeout=30)
```

### 2. choose_model import error
سطر 6875:
```python
from chat_v7 import choose_model as _cm
```
`choose_model` مو موجودة بـ `chat_v7.py` — هذا خطأ قديم.

**الحل:** غلّفها بـ try/except مع fallback:
```python
# القديم:
from chat_v7 import choose_model as _cm
_model_tier = _cm(text)

# الجديد:
try:
    from chat_v7 import choose_model as _cm
    _model_tier = _cm(text)
except ImportError:
    _model_tier = "sonnet"
```

## بعد التنفيذ:
```bash
python3 _tools/quick_check.py
sudo systemctl restart master-ai
```

ثم أرسل `/فرص` بالتيليقرام — المفروض يشتغل.
