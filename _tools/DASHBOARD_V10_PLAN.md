# MASTER AI Dashboard V10 — Stability + UX Overhaul
# ================================================================
# تاريخ: 2026-03-20
# الهدف: إصلاح مشاكل الاستقرار + تحسينات UX للداشبورد
# الحالة: خطة جاهزة للتنفيذ بواسطة Claude Code
# ================================================================
# هذي خطة تكميلية لـ V9.5 — تركز على الاستقرار والعرض
# V9.5 أضاف البيانات (backend) — V10 يصلح العرض ويحسّنه
# ================================================================

---

# السياق الحالي

## الحالة:
- Version: 8.0.0 (لم يتغير)
- Git: 549 commits, branch=main
- Schema: 3.4.0
- Dashboard: 7 pages, ~1427 lines YAML
- Sensors: dashboard (30s), extended (120s), radar (120s)
- كل البيانات موجودة في الـ endpoints — المشكلة في العرض فقط

## ما تم في V9.5:
- A1-A6: Backend enrichment (timeframe, volume, EMA, action, watchlist enrichment)
- B1-tables: جداول markdown حقيقية في صفحة التداول ✅
- B2: News page fixed ✅
- news-split: Digest split into category fields (urgent/economic/local/tech/other) ✅

## البيانات المتاحة الآن (تحققت بالفعل):
- radar_daily_context: 24 fields لكل سهم (price, trend, rsi, support, resistance, score, vol_ratio, ema9, ema21, ema_cross, ema_gap_pct, action, action_ar, source_timeframe...)
- radar_recent_signals: 20 fields لكل إشارة (enriched)
- radar_watchlist: 6 fields (price, change_pct, timeframe, watch_reason)
- news_digest: split fields — urgent, economic, local, tech, other (كل واحد string مستقل)
- assistant_surface: rich structure — top_action (headline, why_now, consequence, recommendation, urgency, confidence, domain, primary_action, secondary_action...), next_actions[], later_today[], changes[], meta
- priority_engine: summary_line, top_priority, priorities[], changes[]
- rooms_summary: 24 rooms مع lights_on, ac_state, ac_temp, covers_total, covers_closed

---

# المشاكل المكتشفة

## P0-1: صفحة البيت فاضية بصرياً
- البيانات موجودة (13 نور, 24 غرفة, 0 مكيف, 8 ستارة)
- لكن الصفحة تظهر فاضية تماماً على desktop
- السبب المرجّح: الكروت تعرض بس النص صغير جداً أو الـ card_mod يخفي المحتوى
- أو: HA يحتاج YAML reload بعد آخر تعديل

## P0-2: صفحة الأخبار نص بلا هيكل
- الأخبار موجودة (88 خبر, split fields متاحة)
- لكن الداشبورد لا يزال يستخدم `d.summary.split('\n')` مع emoji guessing القديم
- الـ split fields (urgent, economic, local, tech, other) لم تُستخدم في YAML بعد!

## P0-3: الصفحة الرئيسية — Decision Card ناقص
- assistant_surface فيه بيانات غنية (headline, why_now, consequence, recommendation, urgency, confidence, primary_action, secondary_action)
- لكن الداشبورد يعرض فقط headline + why_now + recommendation
- next_actions[] و later_today[] متاحة لكن ما تُعرض

---

# تقسيم العمل

## المبدأ: YAML فقط — لا تعديل Python
كل V10 = تعديل `master_ai_dashboard.yaml` فقط.
البيانات كلها جاهزة من V9.5.
لا تلمس server.py أو أي ملف Python.

---

# Phase 1 — Critical Fixes (YAML only)

## Package P1: Fix News Page — Use Split Fields
الأولوية: عالية
الملف: master_ai_dashboard.yaml (sub-news section)
المشكلة: الداشبورد يستخدم `d.summary.split('\n')` القديم مع emoji guessing
الحل: استخدم الـ split fields مباشرة

### التغيير:
استبدل الكروت الثلاث (URGENT/ECONOMY/TECH) بكروت تقرأ من الـ fields الجديدة:

**كارت "🔥 أخبار عاجلة":**
```yaml
content: |
  **🔥 أخبار عاجلة**
  {% set e = 'sensor.master_ai_extended' %}
  {% set d = state_attr(e,'news_digest') %}
  {% if d and d.urgent %}
  {{ d.urgent }}
  {% else %}
  ✅ لا أخبار عاجلة
  {% endif %}
```

**كارت "💰 اقتصاد وأسواق":**
```yaml
content: |
  **💰 اقتصاد وأسواق**
  {% set e = 'sensor.master_ai_extended' %}
  {% set d = state_attr(e,'news_digest') %}
  {% if d and d.economic %}
  {{ d.economic }}
  {% else %}
  📊 لا أخبار اقتصادية
  {% endif %}
```

**كارت "🇰🇼 محلي":** (كارت جديد!)
```yaml
content: |
  **🇰🇼 أخبار محلية**
  {% set e = 'sensor.master_ai_extended' %}
  {% set d = state_attr(e,'news_digest') %}
  {% if d and d.local %}
  {{ d.local }}
  {% else %}
  🇰🇼 لا أخبار محلية
  {% endif %}
```

**كارت "⚡ تقنية ومتفرقات":**
```yaml
content: |
  **⚡ تقنية ومتفرقات**
  {% set e = 'sensor.master_ai_extended' %}
  {% set d = state_attr(e,'news_digest') %}
  {% set content = '' %}
  {% if d and d.tech %}{% set content = content ~ d.tech %}{% endif %}
  {% if d and d.other %}{% set content = content ~ '\n' ~ d.other %}{% endif %}
  {% if content %}
  {{ content }}
  {% else %}
  ⚡ لا أخبار تقنية
  {% endif %}
```

### ملاحظات:
- الـ json_attributes في configuration.yaml لازم يشمل split fields
- تحقق: `state_attr('sensor.master_ai_extended','news_digest').urgent` — هل يرجع بيانات؟
- الجواب: نعم — تحققت. الـ fields موجودة: urgent, economic, local, tech, other
- لا تحتاج تعديل configuration.yaml لأن news_digest هو attribute واحد (object) والـ fields داخله

### Git: V10-P1: news page uses split category fields instead of emoji guessing

---

## Package P2: Fix Home Page Rendering
الأولوية: عالية
الملف: master_ai_dashboard.yaml (sub-home section)
المشكلة: صفحة البيت تظهر فاضية

### خطوات التشخيص (نفذها أولاً):
1. `curl http://192.168.109.123:9000/dashboard -H "X-API-Key: $(cat ~/.master_ai_key)"` → تحقق أن rooms_summary ترجع بيانات
2. في HA Developer Tools → States → sensor.master_ai_dashboard → تحقق من rooms_summary attribute
3. إذا rooms_summary = [] رغم وجود بيانات في الـ API → مشكلة في configuration.yaml (json_attributes)
4. إذا rooms_summary فيها بيانات في HA → مشكلة في الـ Jinja template

### الإصلاح المحتمل (إذا كانت البيانات موجودة في HA):
المشكلة الأرجح: الـ Jinja filters مثل `selectattr('lights_on','gt',0)` قد تفشل لأن `lights_on` يرجع string مش int.

Fix: أضف `| int(0)` أو `| float(0)` لكل comparison:
```yaml
{% if rooms | selectattr('lights_on','defined') | selectattr('lights_on','gt',0) | list | length == 0 %}
```
بدّلها بـ:
```yaml
{% set active = [] %}
{% for r in rooms %}
  {% if r.lights_on | int(0) > 0 or r.ac_state | default('off') != 'off' %}
    {% set active = active + [r] %}
  {% endif %}
{% endfor %}
{% if active | length == 0 %}
```

### الإصلاح المحتمل (إذا الصفحة كلها ما تظهر):
- أحياناً HA يخزّن YAML cache قديم
- جرّب: HA Settings → Dashboards → Master AI → ⋮ → Reload
- إذا ما اشتغل: تحقق من YAML syntax (yamllint)
- إذا ما اشتغل: جرّب حذف card_mod styles مؤقتاً من كارت واحد وشوف إذا يظهر

### Git: V10-P2: fix home page rendering issue

---

## Package P3: Enrich Main Page Decision Card
الأولوية: متوسطة-عالية
الملف: master_ai_dashboard.yaml (master-ai main view)
المشكلة: Decision Card يعرض فقط headline + why_now

### التغيير:
استبدل content الـ Decision Card بنسخة أغنى:

```yaml
content: >
  {% set d = 'sensor.master_ai_dashboard' %}
  {% set asf = state_attr(d,'assistant_surface') %}
  {% if asf and asf.top_action and asf.top_action.headline %}
  {% set ta = asf.top_action %}
  {% set urg = ta.urgency | default('info') %}
  {% if urg == 'critical' %}🚨{% elif urg == 'high' %}🔴{% elif urg == 'medium' %}🟡{% else %}🟢{% endif %}
  **{{ ta.headline }}**

  {{ ta.why_now | default('') }}
  {% if ta.consequence %}

  ⚠️ {{ ta.consequence }}
  {% endif %}
  {% if ta.recommendation %}

  💡 {{ ta.recommendation }}
  {% endif %}
  {% if ta.primary_action %}

  ⬅️ **{{ ta.primary_action.label | default('') }}**{% if ta.secondary_action %} · {{ ta.secondary_action.label | default('') }}{% endif %}
  {% endif %}
  {% if ta.confidence and ta.confidence != 'high' %}

  📊 ثقة: {{ ta.confidence }}
  {% endif %}
  {% elif asf and asf.meta and asf.meta.quiet_mode %}
  ✅ **كل شيء تحت السيطرة** — لا توجد عناصر عاجلة
  {% else %}
  🤖 {{ state_attr(d,'ai_insight') | default('جاري التحميل...') }}
  {% endif %}
```

### إضافة: Next Actions (كارت جديد بعد Decision Card)
```yaml
# ── 2b. NEXT ACTIONS ──
- type: markdown
  card_mod:
    style: |
      ha-card {
        {% set d = 'sensor.master_ai_dashboard' %}
        {% set asf = state_attr(d,'assistant_surface') %}
        {% if not asf or not asf.next_actions or asf.next_actions | length == 0 %}
        display: none;
        {% else %}
        background: rgba(255,255,255,0.02);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 16px;
        padding: 8px 14px;
        margin: 4px 8px 0;
        {% endif %}
      }
      ha-markdown { font-size: 12px; direction: rtl; line-height: 1.7; }
  content: >
    {% set d = 'sensor.master_ai_dashboard' %}
    {% set asf = state_attr(d,'assistant_surface') %}
    {% if asf and asf.next_actions and asf.next_actions | length > 0 %}
    {% for item in asf.next_actions[:3] %}
    {% set urg = item.urgency | default('info') %}
    {% if urg == 'high' %}🔴{% elif urg == 'medium' %}🟡{% else %}🔵{% endif %}
    {{ item.headline }}{% if item.why_now %} · {{ item.why_now }}{% endif %}

    {% endfor %}
    {% endif %}
```

### Git: V10-P3: enrich decision card with consequence and next actions

---

# Phase 2 — UX Improvements (YAML only)

## Package P4: Trading Page — Decision Card Enhancement
الأولوية: متوسطة
الملف: master_ai_dashboard.yaml (sub-radar, L2 section)
المشكلة: Decision Card الأقوى فرصة ناقص fields جديدة

### التغيير في L2 Decision Card:
أضف EMA + Volume + Action + Timeframe:

```yaml
content: |
  {% set r = 'sensor.master_ai_radar' %}
  {% set ctx = state_attr(r,'radar_daily_context') %}
  {% set sig = state_attr(r,'radar_recent_signals') or [] %}
  {% set sig_syms = sig | map(attribute='symbol') | list %}
  {% if ctx and ctx | length > 0 %}
  {% set s = ctx[0] %}
  {% if s.score_class == 'A' %}⭐{% elif s.score_class == 'B' %}🔵{% else %}⚪{% endif %} **{{ s.name_ar | default(s.symbol) }}** — {{ s.price }} فلس

  {% if s.change_pct is not none %}{% if s.change_pct >= 0 %}🟢 **▲ +{{ s.change_pct | round(1) }}%**{% else %}🔴 **▼ {{ s.change_pct | round(1) }}%**{% endif %}{% endif %} · تقييم **{{ s.score }}/{{ s.score_class }}** · RSI {{ s.rsi | round(0) if s.rsi is not none else '—' }}

  📊 فريم: {{ s.source_timeframe | default('—') }} · Volume: {% if s.vol_ratio is not none %}×{{ s.vol_ratio | round(1) }}{% else %}—{% endif %}{% if s.symbol in sig_syms %} · 📡 **إشارة 30m**{% endif %}

  {% if s.ema_cross == 'bullish' %}📈 EMA: تقاطع صاعد{% elif s.ema_cross == 'bearish' %}📉 EMA: تقاطع هابط{% else %}➡️ EMA: محايد{% endif %}{% if s.ema_gap_pct is not none %} ({{ s.ema_gap_pct | round(1) }}%){% endif %}

  {% if s.trend == 'صاعد' %}📈 صاعد{% elif s.trend == 'هابط' %}📉 هابط{% else %}➡️ محايد{% endif %}{% if s.verdict %} — {{ s.verdict[:40] }}{% endif %}

  💡 **{{ s.action_ar | default('—') }}**{% if s.support is not none %} · دعم: {{ s.support }}{% endif %}{% if s.resistance is not none %} · مقاومة: {{ s.resistance }}{% endif %}
  {% else %}
  📊 لا بيانات يومية — السوق مغلق أو لم يُحدّث
  {% endif %}
```

### Git: V10-P4: enrich trading decision card with EMA volume action

---

## Package P5: News Hero — Freshness Warning + Better Counter
الأولوية: متوسطة
الملف: master_ai_dashboard.yaml (sub-news, HERO section)

### التغيير:
استبدل hero الأخبار بنسخة تحسب الفئات من split fields + تحذير الطزاجة:

```yaml
content: |
  ## الأخبار
  {% set e = 'sensor.master_ai_extended' %}
  {% set d = state_attr(e,'news_digest') %}
  {% if d %}
  {% set urgent_count = d.urgent.split('\n') | select('string') | select('ne','') | list | length if d.urgent else 0 %}
  {% set econ_count = d.economic.split('\n') | select('string') | select('ne','') | list | length if d.economic else 0 %}
  {% set local_count = d.local.split('\n') | select('string') | select('ne','') | list | length if d.local else 0 %}
  {% if urgent_count > 0 %}🔴 {{ urgent_count }} عاجل{% endif %}{% if econ_count > 0 %} · 💰 {{ econ_count }} اقتصادي{% endif %}{% if local_count > 0 %} · 🇰🇼 {{ local_count }} محلي{% endif %} · 📰 {{ d.item_count | default(0) }} خبر · {{ d.date | default('') }}
  {% set created = d.created_at | default('') %}
  {% if created %}
  {% set hours_ago = ((as_timestamp(now()) - as_timestamp(created)) / 3600) | round(1) %}
  {% if hours_ago > 12 %}

  🔴 **قديمة** — آخر تحديث قبل {{ hours_ago | round(0) | int }} ساعة
  {% elif hours_ago > 6 %}

  🟡 آخر تحديث قبل {{ hours_ago | round(0) | int }} ساعة
  {% endif %}
  {% endif %}
  {% else %}
  📰 لا أخبار — استخدم /news_now
  {% endif %}
```

### Git: V10-P5: news hero with category counts and freshness warning

---

## Package P6: Main Page — Stock Teaser Enhancement
الأولوية: منخفضة
الملف: master_ai_dashboard.yaml (main view, TOP STOCK TEASER)

### التغيير:
أضف action + EMA للتيزر:

```yaml
content: >
  {% set r = 'sensor.master_ai_radar' %}
  {% set ctx = state_attr(r,'radar_daily_context') %}
  {% if ctx and ctx | length > 0 %}
  {% set s = ctx[0] %}
  ⭐ **{{ s.name_ar | default(s.symbol) }}** — {{ s.price }}ف {% if s.change_pct is not none %}{% if s.change_pct >= 0 %}🟢 +{{ s.change_pct | round(1) }}%{% else %}🔴 {{ s.change_pct | round(1) }}%{% endif %}{% endif %} · {{ s.score }}/{{ s.score_class }}
  {% if s.action_ar %} · 💡 {{ s.action_ar }}{% endif %}{% if s.ema_cross == 'bullish' %} · 📈 EMA{% elif s.ema_cross == 'bearish' %} · 📉 EMA{% endif %}
  {% if ctx | length > 1 %} · +{{ ctx | length - 1 }} أسهم{% endif %}
  {% else %}
  📊 لا بيانات — السوق مغلق
  {% endif %}
```

### Git: V10-P6: stock teaser with action and EMA

---

# Execution Order

```
Phase 1 (Critical — بالترتيب):
P2 → P1 → P3
(البيت أولاً لأنه فاضي — ثم الأخبار — ثم الرئيسية)

Phase 2 (UX — بالترتيب):
P4 → P5 → P6
(التداول — ثم hero الأخبار — ثم التيزر)
```

---

# Claude Code Instructions

## لكل Package:
```
1. اقرأ هذا الملف (_tools/DASHBOARD_V10_PLAN.md)
2. افتح master_ai_dashboard.yaml (H:\ أو /var/lib/homeassistant/homeassistant/)
3. ابحث عن القسم المحدد (comment markers: # ── NAME ──)
4. عدّل YAML فقط — لا تلمس Python
5. تأكد YAML valid (no tab characters, proper indentation)
6. git commit
7. YAML Reload في HA (أو restart HA إذا لزم)
8. تحقق بصرياً
```

## قبل أي تعديل:
```bash
# تأكد النظام شغال
curl -s http://localhost:9000/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'], d['version'])"

# تأكد البيانات موجودة
curl -s http://localhost:9000/dashboard -H "X-API-Key: $(cat ~/.master_ai_key)" | python3 -c "import sys,json; d=json.load(sys.stdin); print('rooms:', len(d.get('rooms_summary',[])))"
curl -s http://localhost:9000/dashboard/extended -H "X-API-Key: $(cat ~/.master_ai_key)" | python3 -c "import sys,json; d=json.load(sys.stdin); print('news:', list(d.get('news_digest',{}).keys()))"
```

## بعد أي تعديل YAML:
```bash
# Validate YAML
python3 -c "import yaml; yaml.safe_load(open('/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml'))" && echo "YAML OK"

# Git commit
cd /var/lib/homeassistant/homeassistant && git add master_ai_dashboard.yaml && git commit -m "MESSAGE"

# Reload (اختر واحد):
# Option A: YAML reload via HA API
curl -X POST http://localhost:8123/api/services/homeassistant/reload_all -H "Authorization: Bearer $(cat ~/.ha_token)"
# Option B: Full HA restart (إذا YAML reload ما اشتغل)
# sudo systemctl restart home-assistant@homeassistant
```

## ما لا يُلمس:
- لا تعدل server.py أو أي ملف Python
- لا تعدل configuration.yaml
- لا تعدل الـ REST sensor definitions
- لا تعدل صفحة التداول (L3/L5/Watchlist) — مكتملة من V9.5
- لا تحذف أي كارت — فقط تعديل content

## ملاحظات تقنية مهمة:
1. Arabic text in YAML: استخدم `content: |` (literal block) مش `content: >` إذا فيه أسطر متعددة مع template
2. Jinja2 في HA: `state_attr('sensor.name','attr')` يرجع الـ attribute
3. التحقق من None: استخدم `is not none` مش `!= None`
4. الـ card_mod style يحتاج تضمين CSS صحيح
5. `display: none` في card_mod يخفي الكارت بالكامل — استخدمه للإخفاء الشرطي

---

# Acceptance Criteria

## بعد Phase 1:
- [ ] صفحة البيت تعرض الغرف والحرارة والأنوار
- [ ] صفحة الأخبار تعرض فئات مفصّلة (عاجل/اقتصادي/محلي/تقني)
- [ ] الصفحة الرئيسية Decision Card يعرض consequence + recommendation + next actions

## بعد Phase 2:
- [ ] Decision Card التداول يعرض EMA + Volume + Action + Support/Resistance
- [ ] Hero الأخبار يحسب الفئات من split fields + تحذير طزاجة
- [ ] تيزر الأسهم في الصفحة الرئيسية يعرض action + EMA

## المعيار النهائي:
- [ ] لا صفحة فاضية — كل صفحة تعرض بيانات أو رسالة واضحة
- [ ] الأخبار تستخدم split fields الجديدة بدل emoji guessing
- [ ] كل كارت فيه بيانات جديدة تستخدم fields الموجودة من V9.5

---

# ملخص

| المرحلة | Packages | النوع | المدة المتوقعة |
|---------|----------|-------|---------------|
| 1: Critical | P1-P3 | YAML only | ساعة واحدة |
| 2: UX | P4-P6 | YAML only | 30 دقيقة |
| **المجموع** | **6 packages** | **YAML only** | **~1.5 ساعة** |

هذي خطة خفيفة — كلها YAML — لا تعديل backend.
كل البيانات جاهزة من V9.5 — فقط نعرضها صح.
