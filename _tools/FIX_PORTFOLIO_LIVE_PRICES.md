# FIX: Portfolio Live Prices from Bridge API
# تاريخ: 2026-03-29
# المنفذ: Claude Code على RPi

## المشكلة
صفحة المراكز المفتوحة (`/dashboard/portfolio`) تعرض أسعار من `radar_daily` snapshot.
النتيجة: `quote_source: "radar_daily"` و `quote_stale: true` — السعر مو حي.

## السبب
الـ endpoint يقرأ `current_price` من جدول `stock_radar_daily` بدل ما يسحب السعر الحي من Bridge.

## المطلوب
عدّل حساب `current_price` في endpoint الـ portfolio بحيث:

### 1. يسحب السعر الحي من Bridge أولاً
```python
# استخدم bridge_client.py الموجود
# Bridge endpoint: GET http://192.168.111.158:8059/quote?symbol=SYMBOL
# Response: {"price": 134.0, "change_percent": -0.74, ...}
```

### 2. Fallback للسعر اليومي إذا Bridge فشل
```python
# إذا Bridge مو متصل أو رجع error → استخدم السعر من radar_daily (الحالي)
```

### 3. غيّر quote_source و quote_stale
```python
# إذا السعر من Bridge:
#   quote_source = "bridge_live"
#   quote_stale = False
# إذا السعر من daily fallback:
#   quote_source = "radar_daily"  
#   quote_stale = True (الحالي)
```

## أين الكود
ابحث عن المكان اللي يحسب `current_price` للمراكز المفتوحة:
- غالباً في `server.py` أو `dashboard_api.py`
- ابحث عن: `current_price` أو `quote_source` أو `portfolio` endpoint
- الـ endpoint هو `GET /dashboard/portfolio`

## طريقة سحب السعر من Bridge
```python
# bridge_client.py موجود ويشتغل — استخدمه
# أو urllib مباشرة:
import urllib.request, json

def get_live_price(symbol):
    """Get live price from Bridge API"""
    try:
        url = f"http://192.168.111.158:8059/quote?symbol={symbol}"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read().decode())
        return data.get("price")
    except:
        return None
```

## شروط مهمة
- لا تكسر الـ endpoint الحالي
- إذا Bridge فشل → fallback للقديم (لا يكسر)
- minimal change — بس غيّر مصدر السعر
- لا تعدّل حساب P&L أو الفورمولا — بس current_price

## الاختبار
بعد التعديل:
1. `python3 _tools/quick_check.py`
2. `bash _tools/restart_master_ai.sh`
3. `curl -s http://localhost:9000/dashboard/portfolio | python3 -m json.tool | grep -E "current_price|quote_source|quote_stale"`

## النتيجة المتوقعة
```json
{
  "current_price": 134.0,
  "quote_source": "bridge_live",
  "quote_stale": false
}
```
بدل:
```json
{
  "current_price": 133.0,
  "quote_source": "radar_daily",
  "quote_stale": true
}
```
