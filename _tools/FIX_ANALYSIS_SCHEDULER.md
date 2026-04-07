# FIX: Analysis Daily Scheduler — Silent Failure Debug + Manual Endpoint
# Date: 2026-04-07
# Author: claude.ai (plan) → Claude Code (execute)
# Priority: HIGH

## المشكلة

الـ `analysis_daily_scheduler()` يشتغل 14:15 KWT كل يوم بس **يفشل بصمت**.

### الأدلة:
- Log يقول `Analysis scheduler: starting daily refresh` عند 14:15:00
- بعد 6 دقائق يقول `Analysis scheduler: next run in 23.9h`
- **لكن 0 أسهم اتحللت اليوم** (Apr 7)
- DB يبيّن: Apr 4=127, Apr 5=76, Apr 6=53, Apr 7=0
- Bridge API شغال (health OK من RPi)
- الـ `refresh_all_analyses_parallel()` ما يكتب أي log — يرسل تيليقرام بس

### السبب الحقيقي (مُثبت):
**Gemini API يرجع HTTP 503 (Service Unavailable)**

```
urllib.error.HTTPError: HTTP Error 503: Service Unavailable
File "stock_analyzer.py", line 419, in analyze_stock
    resp = urllib.request.urlopen(req, timeout=120)
```

الـ Bridge شغال ✅, الـ symbols 128 ✅, الـ Gemini key موجود ✅
بس Gemini 2.5 Pro API يرفض الطلب بـ 503.

يستخدم: `gemini-2.5-pro:generateContent` مع `google_search` tool و `thinkingBudget: -1`

**احتمالات 503:**
- Rate limit (128 سهم × Gemini Pro = كثير)
- Model overloaded / quota exceeded
- الـ model name تغير أو الـ API version تغير

---

## الخطة (5 خطوات)

### Step 0: (الأهم) — صلّح 503 Gemini Error

**ملف:** `/home/pi/master_ai/stock_analyzer.py` (سطر ~419)

الكود الحالي ما يعمل retry ولا يمسك الـ HTTPError:
```python
resp = urllib.request.urlopen(req, timeout=120)
```

**الحل — أضف retry مع backoff:**
```python
import time as _time
for _attempt in range(3):
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        break
    except urllib.error.HTTPError as he:
        if he.code in (429, 503) and _attempt < 2:
            wait = (2 ** _attempt) * 10  # 10s, 20s
            logger.warning(f"Gemini {he.code} for {symbol}, retry in {wait}s (attempt {_attempt+1})")
            _time.sleep(wait)
        else:
            logger.error(f"Gemini HTTP {he.code} for {symbol}: {he.reason}")
            return {"error": f"Gemini HTTP {he.code}: {he.reason}"}
else:
    return {"error": "Gemini failed after 3 retries"}
```

**وأيضاً:** جرّب model fallback — إذا `gemini-2.5-pro` يعطي 503, جرّب `gemini-2.5-flash`:
```python
models_to_try = ["gemini-2.5-pro", "gemini-2.5-flash"]
```

### Step 0b: تحقق من Gemini quota

```bash
# اختبر Gemini API مباشرة
curl -s "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key=$(cat ~/.gemini_key)" \
  -H "Content-Type: application/json" \
  -d '{"contents":[{"role":"user","parts":[{"text":"test"}]}]}' | head -5
```

إذا رجع 503 حتى لطلب واحد → المشكلة في الـ API key أو الـ quota.
إذا نجح → المشكلة في الـ rate limiting عند 128 طلب.

### Step 1: أضف logging في stock_analyzer.py

**ملف:** `/home/pi/master_ai/stock_analyzer.py`

في دالة `refresh_all_analyses()` (سطر ~148), أضف logs بعد كل خطوة:

```python
def refresh_all_analyses(send_update=None):
    symbols = get_all_kse_symbols()
    if not symbols:
        logger.error("refresh_all: no symbols found in kse_stocks.csv")  # ← ADD
        return {"error": "no symbols found in kse_stocks.csv"}

    bridge_ok = _bridge_available()
    logger.info("refresh_all: symbols=%d, bridge=%s", len(symbols), bridge_ok)  # ← ADD

    if not bridge_ok:
        logger.error("refresh_all: Bridge offline — aborting")  # ← ADD
        return {"error": "Bridge offline — cant refresh analyses"}

    # ... rest of function
```

في دالة `refresh_all_analyses_parallel()` (سطر ~192), أضف logs مماثلة.

**ملاحظة مهمة:** الدالة `refresh_all_analyses_parallel` — تحقق هل هي فعلاً async ولا sync. إذا sync بس ملفوفة بـ async name، لازم تصير `await asyncio.to_thread(refresh_all_analyses)` أو تكون async حقيقية.

### Step 2: أضف logging في server.py للنتيجة

**ملف:** `/home/pi/master_ai/server.py` (سطر ~2675-2682)

الكود الحالي:
```python
logger.info("Analysis scheduler: starting daily refresh")
_cid = ADMIN_TELEGRAM_ID or "669769765"
await tg_send(int(_cid), "⏰ تحديث التحليل الفني اليومي (128 سهم)...")
from stock_analyzer import refresh_all_analyses_parallel
result = await refresh_all_analyses_parallel(max_concurrent=5)
msg = f"✅ تحليل يومي: {result.get('done', 0)}/{result.get('total', 0)} ({result.get('errors', 0)} أخطاء)"
await tg_send(int(_cid), msg)
```

**عدّل إلى:**
```python
logger.info("Analysis scheduler: starting daily refresh")
_cid = ADMIN_TELEGRAM_ID or "669769765"
await tg_send(int(_cid), "⏰ تحديث التحليل الفني اليومي (128 سهم)...")
from stock_analyzer import refresh_all_analyses_parallel
result = await refresh_all_analyses_parallel(max_concurrent=5)
logger.info("Analysis scheduler result: %s", result)  # ← ADD THIS
msg = f"✅ تحليل يومي: {result.get('done', 0)}/{result.get('total', 0)} ({result.get('errors', 0)} أخطاء)"
await tg_send(int(_cid), msg)
logger.info("Analysis scheduler: done — %s", msg)  # ← ADD THIS
```

### Step 3: أضف endpoint يدوي

**ملف:** `/home/pi/master_ai/server.py`

أضف endpoint جديد (ضعه قرب trading endpoints الموجودة):

```python
@app.post("/api/refresh-analysis")
async def api_refresh_analysis(request: Request):
    """Manual trigger for daily analysis refresh."""
    _check_api_key(request)
    from stock_analyzer import refresh_all_analyses_parallel, _bridge_available, get_all_kse_symbols
    bridge_ok = _bridge_available()
    symbols = get_all_kse_symbols()
    if not bridge_ok:
        return {"error": "Bridge offline", "bridge": False, "symbols_count": len(symbols)}
    if not symbols:
        return {"error": "No symbols found", "bridge": True, "symbols_count": 0}
    result = await refresh_all_analyses_parallel(max_concurrent=5)
    return {"ok": True, "bridge": True, "symbols_count": len(symbols), **result}
```

### Step 4: تحقق من ParallelCoordinator timeout

**ملف:** `/home/pi/master_ai/stock_analyzer.py` (سطر ~222)

الكود الحالي:
```python
results = await coord.run(max_concurrent=max_concurrent, timeout=120,
                          on_progress=_on_progress)
```

**المشكلة:** `timeout=120` — هذا 120 ثانية **إجمالي لكل الأسهم** (مو لكل سهم).
كل سهم يحتاج Bridge bars + Gemini API call = ~10-30 ثانية.
128 سهم ÷ 5 parallel = ~26 دفعة × 20 ثانية = ~520 ثانية minimum.

**الحل:** غيّر الـ timeout:
```python
results = await coord.run(max_concurrent=max_concurrent, timeout=900,
                          on_progress=_on_progress)
```

**أو:** تحقق من `ParallelCoordinator.run()` — هل الـ timeout هو per-worker أو total.
اقرأ `/home/pi/master_ai/parallel_coordinator.py` وشوف تعريف `timeout` parameter.

**ملاحظة:** الـ scheduler انتهى في 6 دقائق (360 ثانية) — وهو أكثر من 120 ثانية.
يعني الـ timeout ممكن يكون per-worker مو total. في هالحالة المشكلة مو الـ timeout.

### Step 4b: تحقق من kse_stocks.csv

```bash
wc -l /home/pi/master_ai/kse_stocks.csv
head -5 /home/pi/master_ai/kse_stocks.csv
# تأكد إنه موجود وفيه 128 سهم
```

### Step 4c: اختبر _bridge_available() من RPi

```bash
cd /home/pi/master_ai
python3 -c "
from stock_analyzer import _bridge_available, get_all_kse_symbols
print('Bridge available:', _bridge_available())
print('Symbols count:', len(get_all_kse_symbols()))
"
```

**هذا أهم اختبار** — إذا `_bridge_available()` رجعت `False` فالمشكلة واضحة.

---

## التنفيذ

```bash
# 1. عدّل الملفات حسب الخطوات أعلاه
# 2. تحقق
cd /home/pi/master_ai
python3 -c "from stock_analyzer import refresh_all_analyses_parallel, _bridge_available, get_all_kse_symbols; print('bridge:', _bridge_available()); print('symbols:', len(get_all_kse_symbols()))"

# 3. اختبر يدوي
python3 -c "from stock_analyzer import refresh_all_analyses; r = refresh_all_analyses(); print(r)"

# 4. بعد التعديلات
python3 _tools/quick_check.py
git add -A && git commit -m "fix: add logging to analysis scheduler + manual refresh endpoint"
bash _tools/restart_master_ai.sh

# 5. اختبر الـ endpoint
curl -s -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000/api/refresh-analysis
```

---

## بعد الإصلاح — المتوقع:
- server.log يبيّن: `refresh_all: symbols=128, bridge=True`
- الـ analysis يشتغل ويحلل الأسهم
- endpoint يدوي يشتغل للاختبار
- تيليقرام يوصل بالنتيجة
