# V9.5 Progress Summary — Session Handoff
# تاريخ: 2026-03-20
# الهدف: ملخص ما تم + ما باقي — للاستخدام في محادثة جديدة

---

## ✅ ما تم إنجازه (V9 + V9.5)

### V9 Dashboard Cleanup (13 packages — كلها ✅):
- P1-P4: حذف سهم الرجوع + أيقونات ضخمة + Git Log + نصوص غامضة
- P5: ضغط كل Heroes
- P6-P7: إعادة بناء الصفحة الرئيسية (Decision Card + Quick Actions)
- P8: غرف البيت grid
- P9: أخبار مصنّفة
- P10: دمج المساعد+النظام (8→7 صفحات, Nav 6)
- P11: تحسين التداول (action + EMA + volume)
- P12: Design System unification
- P13: Final polish

### V9.5 Backend Enrichment (كلها ✅):
- A1: radar_daily_context enriched (timeframe, volume, action, action_ar)
- A2: watchlist enriched (price, change_pct, watch_reason, timeframe)
- A3: News scheduler fix (auto every 6h)
- A4: News prompt overhaul (professional Arabic + sources)
- A4-fix: Prompt rewrite for agency-style + numbers + examples
- A5: Kuwait local sources (11 sources total)
- A5-fix: Fixed dead RSS (KUNA/AlRai/AlQabas → Google/AlJazeera/BBC Arabic/Bloomberg)
- A6: EMA 9/21 cross analysis (ema9, ema21, ema_cross, ema_gap_pct)
- B1: Trading page updated with new data (BUT NOT TABLES — still markdown text)
- B2: News page fixed
- news-split: Digest split into category fields (urgent/economic/local/tech/other) — no truncation

### Dashboard YAML: ~1446 lines, 7 pages, 6 nav icons
### Git commits: ~30+ commits across V9 and V9.5

---

## ⬜ ما باقي

### 1. B1-tables: تحويل صفحة التداول إلى جداول markdown حقيقية
Claude Code أضاف البيانات لكن عرضها كـ text مع pipes — HA ما يعرضها كجداول لأن الـ separator line (|---|) مفقود أو التنسيق خطأ.

المطلوب: تحويل 3 أقسام إلى جداول حقيقية + حذف كارت مكرر.

---

## الأمر الجاهز لـ Claude Code (B1-tables):

```
اقرأ _tools/DASHBOARD_V95_PLAN.md

المطلوب: تحويل 3 أقسام في sub-radar إلى جداول markdown حقيقية.

⚠️ مهم جداً — جدول markdown في HA يحتاج:
1. سطر header: | عمود1 | عمود2 |
2. سطر separator: |---|---| (بدونه HA ما يعرض جدول!)
3. سطور بيانات: | بيانات1 | بيانات2 |
4. لازم سطر فاضي قبل أول | في الجدول

التغيير 1: استبدل content في "L3: TOP OPPORTUNITIES" — ادمج فيه L4 (بقية السياق) عشان يصير جدول واحد:

content: |
  {% set r = 'sensor.master_ai_radar' %}
  {% set ctx = state_attr(r,'radar_daily_context') %}
  {% if ctx and ctx | length > 1 %}
  **📊 نظرة فنية** ({{ ctx | length - 1 }} سهم)

  | السهم | السعر | %Δ | Vol | RSI | EMA | Score | الاتجاه | Action |
  |:------|------:|---:|----:|:---:|:---:|:-----:|:-------:|:------:|
  {% for s in ctx[1:] %}| {{ s.name_ar | default(s.symbol) }} | {{ s.price }} | {% if s.change_pct is not none %}{{ s.change_pct | round(1) }}{% else %}—{% endif %} | {% if s.vol_ratio is not none %}×{{ s.vol_ratio | round(1) }}{% else %}—{% endif %} | {{ s.rsi | round(0) | int if s.rsi is not none else '—' }} | {% if s.ema_cross == 'bullish' %}📈{% elif s.ema_cross == 'bearish' %}📉{% else %}➡️{% endif %} | {{ s.score }}/{{ s.score_class }} | {% if s.trend == 'صاعد' %}📈{% elif s.trend == 'هابط' %}📉{% else %}➡️{% endif %} | {{ s.action_ar | default('—') }} |
  {% endfor %}
  {% else %}
  📊 لا بيانات
  {% endif %}

التغيير 2: احذف كارت "L4: DAILY CONTEXT BOARD" بالكامل (مدمج في الجدول فوق)

التغيير 3: استبدل content في "L5: 30m SIGNAL FLASH":

content: |
  {% set r = 'sensor.master_ai_radar' %}
  {% set signals = state_attr(r,'radar_recent_signals') %}
  {% if signals and signals | length > 0 %}
  **📡 إشارات 30m** ({{ signals | length }})

  | السهم | السعر | الوقت | النوع | Score | القوة |
  |:------|------:|:-----:|:-----:|:-----:|:-----:|
  {% for s in signals[:5] %}| {{ s.name_ar | default(s.symbol) }} | {{ s.price }}ف | {{ s.time[-5:] if s.time | length > 5 else s.time }} | {% if s.type_ar | default('') == 'صاعد' %}🟢{% else %}🔴{% endif %} | {{ s.score }}/{{ s.score_class }} | {{ s.strength | default('—') }} |
  {% endfor %}
  {% endif %}

التغيير 4: استبدل content في "WATCHLIST GRID":

content: |
  {% set wl = state_attr('sensor.master_ai_radar','radar_watchlist') %}
  {% if wl and wl | length > 0 %}
  **🔍 المراقبة** ({{ wl | length }} سهم)

  | السهم | السعر | %Δ | الفريم | السبب |
  |:------|------:|---:|:------:|:------|
  {% for s in wl[:12] %}| {{ s.name_ar | default(s.symbol) }} | {{ s.price | default('—') }} | {% if s.change_pct is not none %}{{ s.change_pct | round(1) }}%{% else %}—{% endif %} | {{ s.timeframe | default('—') }} | {{ s.watch_reason | default('مراقبة') }} |
  {% endfor %}
  {% endif %}

ملاحظات:
- Decision Card (L2) يبقى كما هو
- Hero + Stale Warning + Diagnostics تبقى كما هي
- تأكد كل جدول فيه سطر فاضي قبله
- تأكد separator |---| موجود في كل جدول
- تأكد YAML valid

git commit: "V95-B1-tables: convert trading sections to real markdown tables"
```

---

## ملفات الخطط على الـ RPi:
- _tools/DASHBOARD_V9_PLAN.md — خطة V9 الأصلية (مكتملة)
- _tools/DASHBOARD_V95_PLAN.md — خطة V9.5 + ADDENDUM (جداول + EMA)
- هذا الملف: _tools/V95_SESSION_HANDOFF.md — ملخص للمحادثة الجديدة
