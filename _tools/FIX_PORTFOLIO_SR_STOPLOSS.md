# FIX: Portfolio — Support/Resistance + Stop Loss
# تاريخ: 2026-03-29
# المنفذ: Claude Code على RPi

## المشكلة
صفحة المراكز (positions.html) جاهزة لعرض:
1. الدعم (`p.support`) والمقاومة (`p.resistance`) — سطر 831-832
2. وقف الخسارة (`p.stop_loss`) — سطر 836+
3. هدف الربح (`p.take_profit`) — سطر 844+

لكن الـ backend (`/dashboard/portfolio`) ما يرسل هالبيانات:
- `stop_loss: null`
- `take_profit: null`
- `support` و `resistance` غير موجودين

## المطلوب — 3 أشياء

### 1. إضافة Support/Resistance من sr_engine
```python
# sr_engine.py موجود ويحسب S/R levels
# لكل مركز مفتوح، اسحب أقرب support وأقرب resistance
# ضيفهم كـ fields في response: "support" و "resistance"
```

### 2. حساب Stop Loss المقترح
```python
# إذا المستخدم ما حدد stop_loss يدوياً:
# احسب وقف خسارة مقترح = أقرب support level تحت سعر الدخول
# أو = entry_price - (2 * ATR)
# ضيفه كـ "suggested_stop" في الـ response
# الـ HTML يعرض stop_loss إذا مو null
```

### 3. سحب السعر الحي من Bridge (من الخطة السابقة)
```python
# quote_source = "bridge_live" بدل "radar_daily"
# quote_stale = false
```

## أين تعدّل
ابحث في `server.py` أو `dashboard_api.py` عن endpoint `/dashboard/portfolio`.
ابحث عن المكان اللي يبني response للمراكز المفتوحة.

## الملفات المرتبطة
- `sr_engine.py` — فيه دوال حساب S/R levels
- `bridge_client.py` — لسحب السعر الحي
- `stock_radar.py` — فيه ATR data

## طريقة الحساب

### Support: أقرب مستوى دعم تحت السعر الحالي
```python
# من sr_engine أو من daily context
# أو من bridge /analysis → data.support array
```

### Resistance: أقرب مستوى مقاومة فوق السعر الحالي
```python
# من sr_engine أو من daily context
# أو من bridge /analysis → data.resistance array
```

### Stop Loss المقترح (إذا null):
```python
# الأولوية:
# 1. stop_loss اللي حدده المستخدم (إذا موجود)
# 2. أقرب support تحت entry_price
# 3. entry_price - (2 * ATR_14)
# 4. entry_price * 0.95 (5% default)
```

## الاختبار
```bash
python3 _tools/quick_check.py
bash _tools/restart_master_ai.sh
curl -s http://localhost:9000/dashboard/portfolio | python3 -m json.tool | head -50
```

## النتيجة المتوقعة
```json
{
  "symbol": "CLEANING",
  "current_price": 134.0,
  "quote_source": "bridge_live",
  "quote_stale": false,
  "support": 126.0,
  "resistance": 140.0,
  "stop_loss": 126.0,
  "suggested_stop": 126.0,
  "take_profit": null
}
```

## ملاحظة مهمة
الـ HTML (positions.html) **ما يحتاج تعديل** — بالفعل جاهز يعرض support/resistance/SL/TP.
المشكلة كلها في الـ backend endpoint.
