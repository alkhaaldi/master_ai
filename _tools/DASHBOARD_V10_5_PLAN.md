# MASTER AI Dashboard V10.5 — Visual Polish (Desktop Readability)
# ================================================================
# تاريخ: 2026-03-20
# الهدف: تحسين القراءة على شاشة desktop — خطوط أكبر + max-width
# الحالة: خطة جاهزة للتنفيذ بواسطة Claude Code
# ================================================================
# هذي خطة بسيطة — كلها card_mod CSS فقط
# لا تعديل content أو Jinja templates
# ================================================================

---

# المشكلة

الداشبورد مصمم لـ mobile/tablet (panel view = card واحد يملأ العرض).
على desktop عريض (~1500px+):
- الكروت تمتد لكل العرض
- النص صغير نسبياً ومبعثر
- الجداول في صفحة التداول تظهر صغيرة
- صفحة البيت والأخبار تبدو فاضية لأن النص ضايع في مساحة كبيرة

# الحل: 3 تعديلات CSS فقط

## التعديل 1: زيادة حجم الخط الأساسي
كل markdown card يحتاج font-size أكبر.

### القاعدة:
- Hero cards: `ha-markdown { font-size: 14px; }` → لا تغيير (حجم مناسب)
- Body cards: `ha-markdown { font-size: 13px; }` أو `12px` → رفعها لـ `14px`
- Table cards: `ha-markdown { font-size: 13px; }` → رفعها لـ `14px`
- Footer/diagnostic: `ha-markdown { font-size: 11px; }` → رفعها لـ `12px`

### التنفيذ:
ابحث عن كل `font-size: 12px` و `font-size: 13px` في ha-markdown وبدّلها:
- `font-size: 12px` → `font-size: 14px` (body cards)
- `font-size: 13px` → `font-size: 14px` (body cards)  
- `font-size: 11px` → `font-size: 12px` (footers فقط)

⚠️ **استثناءات — لا تغيّر:**
- `font-size: 14px` الموجود حالياً (مناسب)
- `font-size: 12px` في status grid cards (أعداد صغيرة — مناسبة)
- `font-size: 11px` في navigation buttons names
- أي h2 font-size (العناوين)

### Git: V10.5-S1: increase base font sizes for desktop readability

---

## التعديل 2: max-width للمحتوى
أضف max-width للـ vertical-stack الرئيسي في كل صفحة عشان المحتوى ما يمتد لكل العرض.

### الطريقة:
كل صفحة عندها `type: vertical-stack` كأول card في panel view.
أضف card_mod style للـ vertical-stack:

```yaml
- type: vertical-stack
  card_mod:
    style: |
      ha-card {
        max-width: 900px;
        margin: 0 auto;
      }
  cards:
    # ... existing cards
```

⚠️ **مشكلة**: HA vertical-stack ما يدعم card_mod style بنفس الطريقة.

### البديل الأفضل:
أضف CSS على كل كارت فردياً:
```yaml
ha-card {
  max-width: 900px;
  margin-left: auto;
  margin-right: auto;
}
```

**لكن هذا كثير كروت!** الطريقة الأسهل:

### الحل الأمثل: theme أو card-mod على مستوى الداشبورد
لا — هذا يحتاج theme file وهو أعقد.

### الحل العملي الأبسط:
لا تضيف max-width — فقط زد الخطوط. المستخدم يستخدم الداشبورد أصلاً على tablet/mobile.
إذا أراد desktop، يقدر يصغّر النافذة.

**القرار: نتجاوز التعديل 2 — نركز على الخطوط فقط.**

---

## التعديل 3: تحسين line-height للجداول
الجداول في صفحة التداول عندها `line-height: 2.0` — هذا كبير جداً ويباعد الأسطر.

### التغيير:
- `line-height: 2.0` في Table cards → `line-height: 1.8`

هذا يخلي الجداول أكثف وأسهل قراءة.

---

# الملخص — تعديلات مطلوبة

## S1: Font Size Increase
ابحث واستبدل في master_ai_dashboard.yaml:

### القاعدة البسيطة:
1. كل `ha-markdown { font-size: 12px;` → `ha-markdown { font-size: 14px;`
2. كل `ha-markdown { font-size: 13px;` → `ha-markdown { font-size: 14px;`
3. كل `ha-markdown { font-size: 11px;` في diagnostic/footer → `ha-markdown { font-size: 12px;`

### الاستثناءات (لا تغيّر):
- `opacity: 0.85; }` — أحياناً font-size 12px مع opacity يكون Hero sub text — هذا OK غيّره
- Grid cards اللي فيها أرقام كبيرة + كلمة تحتها (مثل "مواعيد", "مفتوحة") — ممكن يبقون 13px
- لكن الأبسط: غيّر الكل لـ 14px والـ footers لـ 12px

## S2: Table Line Height
ابحث واستبدل:
- `line-height: 2.0;` → `line-height: 1.8;` (في الجداول فقط — sub-radar section)

---

# Claude Code Instructions

```bash
# الملف الوحيد: master_ai_dashboard.yaml
# المسار: /var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml

# S1: Font sizes
# استبدل كل font-size: 12px في ha-markdown بـ 14px
# استبدل كل font-size: 13px في ha-markdown بـ 14px  
# استبدل كل font-size: 11px في diagnostic footers بـ 12px

# S2: Line height
# في sub-radar section: line-height: 2.0 → 1.8

# بعد التعديل:
python3 -c "import yaml; yaml.safe_load(open('/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml'))" && echo "YAML OK"
cd /var/lib/homeassistant/homeassistant && git add master_ai_dashboard.yaml && git commit -m "V10.5: increase font sizes for desktop readability"
curl -X POST http://localhost:8123/api/services/homeassistant/reload_all -H "Authorization: Bearer $(cat ~/.ha_token)"
```

---

# Acceptance Criteria
- [ ] لا font-size: 12px أو 13px متبقي في body cards (كلهم 14px)
- [ ] footer/diagnostic cards عند 12px
- [ ] جداول التداول line-height: 1.8
- [ ] YAML valid
- [ ] الصفحات تعرض بشكل أوضح على desktop
