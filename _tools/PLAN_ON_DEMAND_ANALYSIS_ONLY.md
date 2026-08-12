# PLAN: تحويل صفحة التحليل الفني (analysis.html) إلى On-Demand-Only

**التاريخ:** 2026-05-06
**المنفذ:** Claude Code على RPi
**الأولوية:** 🔴 عالية — توفير في تكلفة Gemini API

---

## 📌 سياق ما تم اكتشافه (من تشخيص سابق)

| البند | الحالة |
|-------|--------|
| `gemini_scanner.py` | ✅ متوقف منذ 2026-04-02 — لا scheduler ولا cron يشغّله |
| `GET /api/analyze` | ⚠️ يشتغل، يقرأ من جدول `stock_analysis_cache` (cache قديم) |
| `POST /api/analyze/refresh` | ⚠️ كود سليم، يفشل لأن Bridge مفصول |
| `_analysis_cache = {}` (memory cache) | ⚠️ موجود في `stock_analyzer.py` (TTL 1800) |
| `stock_analysis_cache` (DB table) | ⚠️ موجود — fields غير معروفة بدقة |
| Bridge (192.168.111.158:8059) | ❌ مفصول حالياً |

**الفرضية:** المستخدم يشك بأن فيه scheduler/cron يحلّل 128 سهم تلقائياً ويستهلك Gemini API. التشخيص السابق نفى وجود scheduler مرئي، لكن **يحتاج فحص أعمق** قبل التأكد.

---

## 🎯 الهدف النهائي

1. ✅ **تأكيد قاطع** أن لا scheduler خفي يستدعي Gemini تلقائياً
2. ✅ صفحة `analysis.html` تشتغل **on-demand-only** — كل ضغطة = Gemini live call
3. ✅ **بدون أي cache** (لا memory ولا DB)
4. ✅ Bridge شغّال — تأكد من اتصاله

---

## 🔍 المرحلة 1: بحث شامل عن أي مستهلك Gemini خفي

### 1.1 ابحث عن كل استدعاءات Gemini في الكود

```bash
cd ~/master_ai
source venv/bin/activate

echo "=== كل الملفات اللي تستدعي Gemini ==="
grep -rn "generativeai\|genai\.\|gemini\.\|GEMINI_KEY\|gemini_key\|gemini_api\|GenerativeModel" \
  --include="*.py" . | grep -v __pycache__ | grep -v "^Binary"

echo ""
echo "=== كل ملفات Python تحتوي gemini ==="
ls -la *gemini* 2>/dev/null
find . -name "*gemini*" -not -path "*/\.*" -not -path "*/venv/*" -not -path "*/__pycache__/*"
```

### 1.2 ابحث عن أي scheduler/loop/timer

```bash
echo "=== كل asyncio.create_task ==="
grep -rn "asyncio.create_task\|asyncio.ensure_future\|loop.create_task" \
  --include="*.py" . | grep -v __pycache__

echo ""
echo "=== أي scheduler/APScheduler/sched ==="
grep -rn "scheduler\|APScheduler\|BackgroundTasks\|@scheduler\|add_job\|cron" \
  --include="*.py" . | grep -v __pycache__ | head -50

echo ""
echo "=== أي while True في كود رئيسي ==="
grep -rn "while True:\|while 1:" --include="*.py" . | grep -v __pycache__ | head -30

echo ""
echo "=== systemd timers + cron ==="
sudo systemctl list-timers --no-pager
crontab -l 2>/dev/null
sudo crontab -l 2>/dev/null
ls -la /etc/cron.d/ /etc/cron.daily/ /etc/cron.hourly/ 2>/dev/null
```

### 1.3 ابحث في الكود عن دوال تحلل multiple symbols

```bash
echo "=== دوال تحلل قائمة من الأسهم ==="
grep -rn "for symbol in\|for sym in\|for s in.*symbols\|all_symbols\|128" \
  --include="*.py" . | grep -v __pycache__ | grep -i "analy\|gemini\|scan" | head -30

echo ""
echo "=== أي endpoint يستقبل list أو 'all' ==="
grep -rn "@app\.\|@router\." --include="*.py" . | grep -v __pycache__ | grep -i "analy\|scan\|batch\|all"
```

### 1.4 افحص logs لأي نشاط Gemini مشبوه

```bash
echo "=== آخر 24 ساعة من الـ logs — استدعاءات Gemini ==="
sudo journalctl -u master-ai --since "24 hours ago" --no-pager | \
  grep -iE "gemini|analyze|api.analyze" | tail -50

echo ""
echo "=== إحصائية: كم مرة تم استدعاء Gemini آخر 24 ساعة ==="
sudo journalctl -u master-ai --since "24 hours ago" --no-pager | \
  grep -ciE "gemini.*request|calling gemini|gemini api|generativeai"

echo ""
echo "=== هل فيه pattern زمني (كل 30د؟ كل ساعة؟) ==="
sudo journalctl -u master-ai --since "24 hours ago" --no-pager | \
  grep -iE "gemini|analyze" | awk '{print $3}' | cut -c1-5 | sort | uniq -c | sort -rn | head -20
```

### 1.5 افحص جدول `stock_analysis_cache` — كيف يمتلئ؟

```bash
# هل فيه entries جديدة؟ متى آخر update؟
sqlite3 data/audit.db "
SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%analy%';
" 2>/dev/null
sqlite3 data/life.db "
SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%analy%';
" 2>/dev/null

# دوّر على الجدول الصحيح، وبعدين:
# (استبدل DBPATH بالـ DB اللي فيه الجدول)
DBPATH=$(for db in data/*.db; do
  if sqlite3 "$db" "SELECT name FROM sqlite_master WHERE name='stock_analysis_cache';" 2>/dev/null | grep -q stock_analysis_cache; then
    echo "$db"; break
  fi
done)
echo "DB containing stock_analysis_cache: $DBPATH"

if [ -n "$DBPATH" ]; then
  echo "=== Schema ==="
  sqlite3 "$DBPATH" ".schema stock_analysis_cache"
  
  echo ""
  echo "=== عدد الصفوف ==="
  sqlite3 "$DBPATH" "SELECT COUNT(*) FROM stock_analysis_cache;"
  
  echo ""
  echo "=== توزيع زمني — متى تتم التحديثات؟ ==="
  # جرّب الـ columns المحتملة (analyzed_at, created_at, updated_at, timestamp)
  sqlite3 "$DBPATH" "
    SELECT * FROM stock_analysis_cache ORDER BY rowid DESC LIMIT 5;
  " 2>/dev/null | head -50
  
  echo ""
  echo "=== كم symbol موجود ==="
  sqlite3 "$DBPATH" "SELECT COUNT(DISTINCT symbol) FROM stock_analysis_cache;" 2>/dev/null
fi
```

### 1.6 سلّم تقرير المرحلة 1

اكتب تقرير يحتوي:

| البند | النتيجة |
|------|---------|
| عدد ملفات Python تستدعي Gemini | ? |
| أسماء الملفات | ? |
| asyncio.create_task للـ Gemini | موجود/لا |
| Scheduler/APScheduler يستدعي Gemini | موجود/لا |
| systemd timer أو cron | موجود/لا |
| عدد استدعاءات Gemini آخر 24س | ? |
| Pattern زمني واضح | (مثلاً: كل 30د / كل 6س / لا pattern) |
| `stock_analysis_cache` — آخر update | متى؟ كم symbol؟ |
| **الحكم النهائي** | "لا scheduler خفي" / "وجدت scheduler في X" |

**إذا اكتشفت scheduler خفي:** **توقف هنا** وأعطني التفاصيل قبل ما تكمل.

**إذا تأكدنا أن لا scheduler خفي:** أكمل للمرحلة 2.

---

## 🔧 المرحلة 2: إزالة كل آثار الـ Cache

### 2.1 من `stock_analyzer.py`

```bash
grep -n "_analysis_cache\|CACHE_TTL\|stock_analysis_cache" stock_analyzer.py
```

**التعديلات المطلوبة (minimal):**
- احذف/علّق `_analysis_cache = {}` و `CACHE_TTL = 1800`
- في دالة `analyze_stock()`: احذف الـ cache check في البداية
- احذف أي `_analysis_cache[key] = result` بعد الاستدعاء
- احذف أي `INSERT INTO stock_analysis_cache` و `UPDATE stock_analysis_cache`

**استبدل بـ comment واضح:**
```python
# DISABLED 2026-05-06: cache removed — every call goes to Gemini live.
# User decision: prefer fresh analysis over API cost savings.
```

### 2.2 من `server.py` — تحديث `GET /api/analyze`

**الحالة الحالية:** يقرأ من `stock_analysis_cache` ويرجّع cached result.

**المطلوب:** يحوّل لاستدعاء live بدون cache.

```python
@app.get("/api/analyze")
async def api_analyze(symbol: str):
    """
    On-demand stock analysis. NO CACHE.
    Each call triggers a fresh Gemini analysis.
    Frontend (analysis.html) calls this on stock click.
    """
    try:
        symbol = (symbol or "").upper().strip()
        if not symbol or len(symbol) > 20:
            return JSONResponse({"error": "invalid symbol"}, status_code=400)
        
        # NO cache lookup — go straight to live analysis
        result = await analyze_stock(symbol)  # from stock_analyzer.py
        return result
    except Exception as e:
        logger.exception("api_analyze failed for %s", symbol)
        return JSONResponse(
            {"error": str(e), "symbol": symbol},
            status_code=500
        )
```

### 2.3 من `server.py` — `POST /api/analyze/refresh`

نفس السلوك تماماً — وجوده فقط للتوافق مع الـ frontend الحالي:

```python
@app.post("/api/analyze/refresh")
async def api_analyze_refresh(symbol: str):
    """Same as GET /api/analyze. Kept for frontend backward compatibility."""
    return await api_analyze(symbol)
```

### 2.4 احتفظ بالجدول لكن لا تكتب فيه

```sql
-- لا تحذف الجدول (فيه history)
-- فقط لا تكتب فيه ولا تقرأ منه
-- الجدول يبقى read-only للـ debugging والـ history
```

### 2.5 تأكد أن الـ JSON response shape مطابق لـ frontend contract

`analysis.html` يتوقع (راجع السطور ~290-340):

```json
{
  "symbol": "NBK",
  "data": {
    "price": 1.234,
    "bars_30m": 100,
    "bars_daily": 60
  },
  "structured": {
    "signal": "شراء|بيع|انتظار|مراقبة",
    "confidence": 75,
    "direction": "صاعد|هابط|عرضي",
    "entry": 1.234,
    "stop_loss": 1.200,
    "targets": [1.250, 1.280, 1.310],
    "support": ["1.200", "1.180"],
    "resistance": ["1.260", "1.290"],
    "risk": "..."
  },
  "report": "Markdown text in Arabic",
  "analyzed_at": "2026-05-06 13:45:00"
}
```

**في حالة الخطأ:**
```json
{ "error": "رسالة واضحة بالعربي" }
```

لا ترجع HTML أبداً — حتى exceptions يجب أن تُغلَّف JSONResponse.

---

## 🌉 المرحلة 3: تأكيد Bridge شغّال (المتطلب الحرج)

```bash
# 1. اتصال أساسي
curl -s -o /dev/null -w "Bridge health: HTTP %{http_code}\n" \
  --connect-timeout 5 http://192.168.111.158:8059/health

# 2. اختبار جلب bars
curl -s "http://192.168.111.158:8059/bars?symbol=NBK&interval=30&count=10" | head -c 500
```

**إذا Bridge مفصول:** هذي مهمة المستخدم على PC. سلّم له:
- ❌ Bridge مفصول على 192.168.111.158:8059
- لازم يفتح Bridge على PC (`C:\Users\MS1\tradingview-bridge`)
- يتأكد Chrome مفتوح على CDP port 9222
- بدون Bridge، صفحة التحليل لن تشتغل أبداً (لا يوجد بدائل بيانات)

**لا تحاول تحلّ مشكلة Bridge من جانب RPi** — هي مشكلة على PC.

---

## ✅ المرحلة 4: Validation

### 4.1 اختبارات وظيفية

```bash
echo "=== 1. السيرفر صحي ==="
curl -s http://localhost:9000/health | head -c 200

echo ""
echo "=== 2. Endpoint يرد JSON ==="
curl -s "http://localhost:9000/api/analyze?symbol=NBK" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print('✅ Valid JSON')
    print('Keys:', list(d.keys())[:10])
    print('Has report:', bool(d.get('report')))
    print('Has structured:', bool(d.get('structured')))
    print('Has error:', bool(d.get('error')))
    if d.get('error'):
        print('Error msg:', d['error'])
except Exception as e:
    print('❌ NOT valid JSON:', e)
"

echo ""
echo "=== 3. لا cache: استدعيين متتاليين بنفس الوقت ==="
echo "Call 1:"; time curl -s -o /dev/null "http://localhost:9000/api/analyze?symbol=KFH"
echo "Call 2:"; time curl -s -o /dev/null "http://localhost:9000/api/analyze?symbol=KFH"
# لو الثاني تحت ثانية = ما زال فيه cache!

echo ""
echo "=== 4. تحقق من DB cache — ما فيه entries جديدة ==="
COUNT_BEFORE=$(sqlite3 data/audit.db "SELECT COUNT(*) FROM stock_analysis_cache;" 2>/dev/null || echo 0)
echo "Cache entries before test: $COUNT_BEFORE"
curl -s "http://localhost:9000/api/analyze?symbol=BOUBYAN" > /dev/null
COUNT_AFTER=$(sqlite3 data/audit.db "SELECT COUNT(*) FROM stock_analysis_cache;" 2>/dev/null || echo 0)
echo "Cache entries after test: $COUNT_AFTER"
[ "$COUNT_BEFORE" = "$COUNT_AFTER" ] && echo "✅ Cache NOT updated" || echo "❌ Cache STILL updates!"
```

### 4.2 من Tunnel + Frontend

```bash
KEY=$(cat ~/.master_ai_key)
curl -s -H "X-API-Key: $KEY" \
  "https://ai.salem-home.com/api/analyze?symbol=NBK" | head -c 500
```

ثم اطلب من المستخدم يفتح:
- https://ai.salem-home.com/trading/analysis
- يضغط على سهم
- يتأكد إن النتيجة تطلع بدون "Unexpected token '<'"

### 4.3 معيار النجاح النهائي

- ✅ المرحلة 1 سلّمت تقرير قاطع: "لا scheduler خفي" أو حدّدته وعطّلناه
- ✅ استدعيين متتاليين لـ `/api/analyze` يأخذان نفس الوقت تقريباً (دليل لا cache)
- ✅ عدد الصفوف في `stock_analysis_cache` ما يزيد بعد استدعاء جديد
- ✅ صفحة `analysis.html` تعرض التحليل بدون أخطاء (شرط Bridge شغّال)
- ✅ كل error يطلع JSON مو HTML

---

## 🚫 ممنوعات

- ❌ **لا تحذف** `gemini_scanner.py` ولا `stock_analyzer.py` — تعديل فقط
- ❌ **لا تحذف** جداول DB (احتفظ بالـ history)
- ❌ **لا تعدّل** `analysis.html` (frontend → claude.ai مسؤول)
- ❌ **لا تكسر** endpoints أخرى (`/dashboard/signals`, `/api/decisions-now`, إلخ)
- ❌ **لا تضف cache** بأي شكل
- ❌ **لا تحاول** إصلاح Bridge من جانب RPi (هذي مشكلة PC)

---

## 📦 ما يجب أن يُسلَّم

1. **تقرير المرحلة 1 (الأهم):** هل فيه scheduler خفي؟ نتائج كل الفحوصات
2. **Diff للتغييرات** في `server.py` و `stock_analyzer.py`
3. **نتيجة Validation** الكاملة (4.1)
4. **حالة Bridge:** شغّال / مفصول
5. **Git commit message** مقترح:
   ```
   feat(analyze): on-demand-only mode, remove all caching
   
   - Remove memory cache (_analysis_cache) from stock_analyzer.py
   - Stop reading/writing stock_analysis_cache DB table
   - GET /api/analyze now triggers live Gemini call every time
   - POST /api/analyze/refresh = same behavior (kept for compat)
   - Add JSON exception wrapper to prevent HTML error responses
   - Confirmed: no hidden scheduler consuming Gemini API
   ```
6. **Follow-up tasks** للمستخدم/claude.ai:
   - تشغيل Bridge على PC إذا مفصول
   - (اختياري) banner في `decisions.html` يوضح Scanner متوقف

---

## 🔗 ملفات مرجعية

- `_tools/STOCK_CLICK_ANALYZE.md` — الكود الأصلي للـ analyze endpoint
- `stock_analyzer.py` — الـ analyzer logic
- `server.py:8033-8081` — الـ endpoints الحاليين
- `share/master_ai/www/trading/analysis.html` — الصفحة (read-only)
- `~/.gemini_key` — مفتاح Gemini
- `data/life.db` و `data/audit.db` — DBs
