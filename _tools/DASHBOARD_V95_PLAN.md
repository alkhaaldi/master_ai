# MASTER AI Dashboard V9.5 — Trading Page Rebuild + News Fix
# ================================================================
# تاريخ: 2026-03-20
# الهدف: إعادة بناء صفحة التداول + إصلاح الأخبار
# الحالة: خطة فقط — لا تنفيذ
# ================================================================
# هذي خطة تكميلية لـ V9 — تركز على المشاكل العميقة اللي V9 ما حلّها
# ================================================================

---

# التشخيص الصريح

## صفحة التداول — المشاكل الحقيقية

### 1. لا يوجد إطار زمني (Timeframe)
- الإشارات تقول "bullish cross" لكن على أي فريم؟ 30m؟ يومي؟
- البيانات تميّز بين 30m signals و daily context — لكن الداشبورد ما يوضّح هذا
- **المطلوب backend:** الـ radar_daily_context يحتوي field اسمه `timeframe` (موجود في DB لكن ما يظهر)
- **المطلوب dashboard:** عرض الفريم بوضوح في كل سهم

### 2. لا يوجد حجم تداول (Volume)
- Volume موجود في بعض الإشارات كـ `vol_ratio` — لكن يظهر فقط إذا > 1.5
- حجم التداول الفعلي غير معروض
- **المطلوب backend:** إضافة `volume` و `avg_volume` في radar_daily_context
- **المطلوب dashboard:** عرض Volume كمؤشر لكل سهم

### 3. المعرّفة (Watchlist) = أسماء بدون سياق
- radar_watchlist يرجع فقط: symbol + name_ar
- لا يوجد: سبب المراقبة، السعر، النسبة، القرب من support/resistance
- **المطلوب backend:** إضافة fields: price, change_pct, watch_reason
- **المطلوب dashboard:** عرض كل سهم مع سبب المراقبة

### 4. بقية السياق اليومي — verdict سطحي
- الـ verdict موجود لكنه كلمتين عامة ("ضغط بيعي" / "زخم ضعيف")
- لا يوجد: RSI, support/resistance levels, MACD status
- **المطلوب backend:** الـ daily_context يحتوي rsi — يحتاج إضافة support/resistance
- **المطلوب dashboard:** عرض RSI + مستويات + verdict مفصّل

### 5. Decision Board — ناقص
- يعرض: سعر + نسبة + RSI + score + trend + verdict
- **ناقص:** فريم + volume + target + stop loss + support/resistance
- **المطلوب backend:** إضافة هذي الـ fields في أول سهم بالـ context

### 6. لا يوجد "ماذا أفعل"
- الصفحة تعرض بيانات لكن ما تقول: اشترِ؟ بيع؟ راقب؟
- **المطلوب backend:** إضافة `action` field (buy/sell/watch/hold)
- **المطلوب dashboard:** عرض الـ action بوضوح

## صفحة الأخبار — المشاكل الحقيقية

### 1. الأخبار قديمة (3 أيام!)
- news_digest يعتمد على manual trigger أو scheduled job
- الجدولة ما تشتغل أو متوقفة
- **المطلوب backend:** التأكد من scheduler + إضافة auto-trigger
- **المطلوب dashboard:** تحذير واضح إذا الأخبار أقدم من 12 ساعة

### 2. اللغة عامية ركيكة
- الـ LLM prompt يطلب ترجمة مختصرة — والنتيجة ركيكة
- **المطلوب backend:** تحسين prompt بطلب لغة عربية فصيحة مختصرة + ذكر المصدر

### 3. لا أخبار محلية كويتية
- الـ news sources ما تشمل مصادر كويتية
- **المطلوب backend:** إضافة RSS feeds كويتية (الراي/القبس/KUNA/البورصة)
- **المطلوب dashboard:** فئة "محلي" في التصنيف

### 4. التصنيف يعتمد على emoji الـ LLM
- التصنيف الحالي يعتمد على أول emoji — هش وغير موثوق
- **المطلوب backend:** إضافة `category` field صريح من الـ LLM
- **المطلوب dashboard:** قراءة category بدل guessing من emoji

---

# تقسيم العمل: Backend vs Dashboard

هذا أهم فرق عن V9 — V9 كان dashboard-only.
V9.5 يحتاج تعديلات backend أولاً ثم dashboard.

## المرحلة A — Backend Changes (تحتاج apply_text_patch.py)

### A1: إثراء radar_daily_context
- أضف fields: timeframe, volume, avg_volume, support, resistance, action
- هذي البيانات موجودة في الـ DB أو قابلة للحساب
- الملف: server.py (endpoint /dashboard/radar)

### A2: إثراء radar_watchlist
- أضف fields: price, change_pct, watch_reason, timeframe
- الملف: server.py (endpoint /dashboard/radar)

### A3: إصلاح news digest scheduler
- التأكد من إن الـ scheduler يشتغل
- إضافة auto-trigger كل 6 ساعات
- الملف: server.py (scheduler section)

### A4: تحسين news LLM prompt
- لغة عربية فصيحة مختصرة
- ذكر المصدر (Reuters/BBC/etc)
- إضافة category field صريح
- الملف: الملف المسؤول عن الـ news digest generation

### A5: إضافة مصادر أخبار محلية
- RSS: الراي، القبس، KUNA، بورصة الكويت
- الملف: news_engine أو المسؤول عن الـ sources

## المرحلة B — Dashboard Changes (YAML فقط)

### B1: إعادة بناء صفحة التداول
- Decision Board: إضافة فريم + volume + support/resistance + action
- فرص إضافية: إضافة فريم + volume
- آخر الإشارات: إضافة فريم + نوع الإشارة
- بقية السياق: RSI + مستويات
- المعرّفة: سعر + نسبة + سبب المراقبة

### B2: إصلاح صفحة الأخبار
- تحذير إذا أقدم من 12 ساعة
- فئة "محلي" في التصنيف
- عرض المصدر
- عرض category من الـ field بدل emoji guessing

---

# Priority Matrix

## P0 — أساسيات مفقودة (تشوّه المنتج)
- A3: News scheduler fix — الأخبار قديمة 3 أيام = صفحة ميتة
- A1-partial: إضافة timeframe في radar_daily_context — بدون فريم لا قرار

## P1 — ترفع جودة القرار مباشرة
- A1-full: volume + support/resistance + action
- A2: watchlist مع سبب المراقبة
- B1: إعادة بناء صفحة التداول
- A4: تحسين اللغة العربية في الأخبار

## P2 — تحسينات مهمة
- A5: مصادر أخبار محلية
- B2: تصنيف أخبار محسّن

---

# Phased Execution Roadmap

## Phase A — Backend Enrichment (يحتاج Claude Code + apply_text_patch.py)

### Package A1: Enrich radar_daily_context
- الهدف: إضافة fields مفقودة في الـ daily context
- الملف: server.py (endpoint المسؤول عن /dashboard/radar)
- التغيير: في الـ query/builder اللي يبني radar_daily_context، أضف:
  - `timeframe`: "30m" أو "1D" حسب مصدر البيانات
  - `volume`: حجم التداول اليوم
  - `avg_volume`: متوسط حجم التداول (20 يوم)
  - `vol_ratio`: volume/avg_volume (ممكن موجود — تأكد)
  - `support`: أقرب مستوى دعم
  - `resistance`: أقرب مستوى مقاومة
  - `action`: "buy" / "sell" / "watch" / "hold" (بناءً على score + trend + signals)
- الخطورة: عالية — server.py
- التحقق: smoke_test.py + curl /dashboard/radar | jq '.radar_daily_context[0]'
- Git: V95-A1: enrich radar daily context with timeframe volume levels action

### Package A2: Enrich radar_watchlist
- الهدف: المعرّفة تعرض سبب المراقبة
- الملف: server.py (endpoint المسؤول عن radar_watchlist)
- التغيير: في الـ watchlist builder، أضف:
  - `price`: السعر الحالي
  - `change_pct`: نسبة التغيير
  - `watch_reason`: سبب المراقبة (نص مختصر — "قريب من support 500ف" أو "breakout candidate" أو "RSI oversold")
  - `timeframe`: الفريم المستخدم
- الخطورة: عالية — server.py
- التحقق: curl /dashboard/radar | jq '.radar_watchlist[0]'
- Git: V95-A2: enrich watchlist with price reason timeframe

### Package A3: Fix News Scheduler + Freshness
- الهدف: الأخبار تتحدث أوتوماتيكي
- الملف: server.py (scheduler section)
- التغيير:
  - تأكد من إن news_digest scheduled job يشتغل
  - إضافة auto-trigger كل 6 ساعات
  - إضافة `last_updated` timestamp واضح في news_digest
  - إضافة `hours_since_update` field محسوب
- الخطورة: متوسطة
- التحقق: tail logs + check timestamp
- Git: V95-A3: fix news scheduler and add freshness tracking

### Package A4: Improve News LLM Prompt
- الهدف: لغة عربية فصيحة + مصادر + تصنيف صريح
- الملف: الملف المسؤول عن news digest generation (قد يكون في server.py أو ملف منفصل)
- التغيير في الـ prompt:
  - "اكتب بالعربية الفصيحة المختصرة — لا عامية ولا ترجمة آلية"
  - "اذكر المصدر بين قوسين (Reuters) (BBC) (الراي)"
  - "أضف حقل category لكل خبر: local / global / economic / tech / military"
  - "رتّب حسب الأهمية والتأثير الشخصي"
- إضافة category field في الـ output structure
- الخطورة: متوسطة
- Git: V95-A4: improve news prompt for arabic quality and classification

### Package A5: Add Local Kuwait News Sources
- الهدف: أخبار محلية كويتية
- الملف: الملف المسؤول عن news sources
- التغيير: إضافة RSS feeds:
  - الراي: alrai.com
  - القبس: alqabas.com
  - KUNA: kuna.net.kw
  - بورصة الكويت: boursakuwait.com.kw
- الخطورة: متوسطة
- Dependencies: A4 (يحتاج category "local")
- Git: V95-A5: add Kuwait local news sources

---

## Phase B — Dashboard Rebuild (YAML فقط — بعد Phase A)

### Package B1: Rebuild Trading Page
- الهدف: صفحة تداول تعكس التحليل الفني بوضوح
- الملف: master_ai_dashboard.yaml (sub-radar section)
- الشكل الجديد المستهدف:

```
[Hero compact] — منصة التداول · السوق مفتوح/مغلق · 128 سهم

[⚠ تحذير بيانات قديمة] — يظهر فقط إذا > 1 ساعة (موجود ✅)

[Decision Board — أقوى فرصة]
  ⭐ الاتصالات المستقلة — 566.0 فلس
  🟢 ▲ +1.1% · تقييم 85/A · RSI 64
  📊 فريم: يومي · Volume: 2.3M (×1.5 avg)
  📈 صاعد — زخم صاعد · Support: 550 · Resistance: 580
  💡 Action: مراقبة — قريب من resistance
  ⬅️ افتح TradingView

[فرص إضافية — 4 أسهم]
  كل سهم: اسم · سعر · نسبة · score · فريم · volume
  بدون verdict طويل — compact

[📡 آخر الإشارات — 30m]
  لكل إشارة: نوع (bullish cross/bearish) · سهم · سعر · وقت · فريم: 30m
  واضح إنها 30m signals

[بقية السياق اليومي]
  كل سهم: اسم · سعر · نسبة · RSI · support/resistance · action
  فريم: يومي (واضح)

[المراقبة — 12 سهم]
  كل سهم: اسم · سعر · سبب المراقبة
  "قريب من support 500ف" / "RSI oversold" / "breakout candidate"

[Diagnostics] — آخر تحديث · عمر البيانات
```

- Dependencies: A1, A2 (يحتاج الـ fields الجديدة)
- الخطورة: متوسطة — YAML فقط
- Git: V95-B1: rebuild trading page with full technical data

### Package B2: Fix News Page
- الهدف: أخبار طازجة + مصنّفة + بلغة فصيحة + محلية
- الملف: master_ai_dashboard.yaml (sub-news section)
- التغيير:
  - Hero: إضافة تحذير إذا الأخبار أقدم من 12 ساعة (🔴 "قديمة — آخر تحديث قبل X ساعة")
  - إضافة فئة "🇰🇼 محلي" في التصنيف
  - عرض المصدر لكل خبر: "(Reuters)" / "(الراي)"
  - category field بدل emoji guessing
  - زر "تحديث الأخبار" — يرسل /news_now command
- Dependencies: A3, A4, A5
- الخطورة: منخفضة-متوسطة — YAML
- Git: V95-B2: fix news page with freshness and sources

---

# Execution Order

```
Phase A (Backend — كل package يحتاج apply_text_patch.py + smoke_test):
A3 → A1 → A2 → A4 → A5
(scheduler أولاً لأنه أبسط وأهم — ثم data enrichment — ثم news quality)

Phase B (Dashboard — YAML فقط — بعد A):
B1 → B2
```

## ⚠️ فرق مهم عن V9

V9 كان 100% dashboard YAML — حذف + ضغط + إعادة ترتيب.

V9.5 يحتاج **تعديل server.py** — وهذا يعني:
- كل تعديل Python يمر عبر `_tools/patchers/apply_text_patch.py`
- بعد كل تعديل: `quick_check.py` → `smoke_test.py` → `db_sanity.py` → restart
- لا append. لا direct edit. فقط patch system.
- **اقرأ `/system/context` أولاً** قبل أي تعديل

---

# Claude Code Handoff Instructions

## لكل Package في Phase A:
```
1. اقرأ _tools/DASHBOARD_V95_PLAN.md
2. اقرأ /system/context (أو https://ai.salem-home.com/dev/context)
3. حدد الملف والـ function المطلوب تعديلها
4. استخدم apply_text_patch.py فقط
5. شغّل quick_check.py
6. شغّل smoke_test.py
7. git commit
8. restart إذا لزم
```

## لكل Package في Phase B:
```
1. تأكد إن Phase A المقابل مكتمل (A1→B1, A3+A4+A5→B2)
2. عدّل master_ai_dashboard.yaml فقط
3. YAML reload
4. git commit
5. تحقق بصريًا
```

## ما لا يُلمس:
- لا تعدل endpoints الحالية — أضف fields فقط
- لا تحذف fields موجودة — backward compatible
- لا تعدل DB schema — اقرأ من الجداول الموجودة
- لا تعدل الصفحات الأخرى (الرئيسية/البيت/البريد/المواعيد/النظام — مكتملة من V9)

---

# Acceptance Criteria

## بعد Phase A:
- [ ] radar_daily_context يحتوي: timeframe, volume, support, resistance, action
- [ ] radar_watchlist يحتوي: price, change_pct, watch_reason
- [ ] news_digest يتحدث أوتوماتيكي كل 6 ساعات
- [ ] news_digest بلغة عربية فصيحة مع مصادر
- [ ] news_digest فيه category field صريح
- [ ] أخبار محلية كويتية موجودة

## بعد Phase B:
- [ ] صفحة التداول تعرض الفريم لكل سهم بوضوح
- [ ] Volume ظاهر في Decision Board وفي الفرص
- [ ] المعرّفة فيها سبب المراقبة لكل سهم
- [ ] كل سهم فيه support/resistance
- [ ] كل سهم فيه action مقترح (buy/sell/watch/hold)
- [ ] صفحة الأخبار تحذّر إذا قديمة
- [ ] صفحة الأخبار فيها أخبار محلية كويتية
- [ ] صفحة الأخبار فيها مصدر لكل خبر
- [ ] اللغة فصيحة مش عامية

## المعيار النهائي:
- [ ] أفتح صفحة التداول وأعرف خلال 5 ثوان: أي سهم؟ على أي فريم؟ كم الـ volume؟ شنو الـ action؟
- [ ] أفتح الأخبار وأشوف أخبار اليوم (مش قبل 3 أيام) بلغة محترمة

---

# ملخص

| المرحلة | Packages | النوع | المدة المتوقعة |
|---------|----------|-------|---------------|
| A: Backend | A1-A5 | Python patches | 2-3 أيام |
| B: Dashboard | B1-B2 | YAML only | 1 يوم |
| **المجموع** | **7 packages** | **mixed** | **3-4 أيام** |

هذي خطة واقعية — تعترف بأن المشاكل backend وليس مجرد عرض.


---

# ADDENDUM — Trading Page Table-Based Redesign
# تاريخ: 2026-03-20
# السبب: الصفحة الحالية كلها markdown text — ما فيه جداول ولا ترتيب فني

## المشكلة:
- كل الأقسام نفس الشكل (markdown text cards)
- لا يوجد تمييز بصري بين الأهم والأقل
- البيانات (سعر/نسبة/score/RSI/فريم/volume/action) مثالية لجداول
- الأسهم مرتبة حسب score فقط وليس حسب أفضل فرصة فنية
- المعرّفة = أسماء بدون سياق

## الحل: تحويل كل أقسام البيانات إلى جداول markdown

### B1 المحدّث — Trading Page Table Redesign

الترتيب الجديد:
```
1. [Hero compact] — السوق مفتوح/مغلق · عدد الأسهم · آخر تحديث
2. [⚠ تحذير قِدم] — إذا > 1 ساعة (موجود)
3. [🏆 أفضل فرصة — Decision Card] — أقوى سهم مع كل التفاصيل
4. [📊 جدول الفرص] — أسهم الـ daily context كجدول مرتب
5. [📡 جدول إشارات 30m] — الإشارات الأخيرة كجدول
6. [🔍 جدول المراقبة] — watchlist كجدول مع سبب المراقبة
7. [Diagnostics] — آخر تحديث
```

### جدول الفرص المستهدف (القسم 4):
```markdown
| # | السهم | السعر | %Δ | RSI | Vol | الفريم | الاتجاه | Action |
|---|-------|-------|----|-----|-----|--------|---------|--------|
| 1 | ⭐ الاتصالات | 566 | +1.1 | 64 | ×1.5 | 1D | 📈 صاعد | 🟢 مراقبة |
| 2 | 🟢 المعادن | 99.1 | +0.0 | 55 | ×0.8 | 1D | ➡️ محايد | ⏳ انتظار |
| 3 | 🔴 الكويتية | 569 | -1.9 | 42 | ×2.1 | 1D | 📉 هابط | ⚠️ حذر |
```

### جدول إشارات 30m (القسم 5):
```markdown
| السهم | السعر | الوقت | النوع | Score | القوة | Vol |
|-------|-------|-------|-------|-------|-------|-----|
| 🟢 Action Energy | 283 | 06:33 | صاعد | C/35 | متوسطة | ×1.2 |
| 🔴 البيوت | 357 | 06:17 | هابط | B/50 | متوسطة | ×0.9 |
```

### جدول المراقبة (القسم 6):
```markdown
| السهم | السعر | %Δ | الفريم | السبب |
|-------|-------|----|--------|-------|
| الاتصالات | 566 | +1.1 | 30m | 🟢 زخم صاعد قوي |
| بنك الكويت | 909 | -1.7 | 1D | 📉 قريب من الدعم |
| الساحل | 59.4 | -0.2 | 1D | ⏳ تقييم متوسط |
```

### ترتيب الأسهم في جدول الفرص (حسب الأفضل فنيًا):
- Primary sort: action (buy > watch > hold > sell)
- Secondary sort: score descending
- Tertiary sort: RSI (prefer 30-65 range)
- الفكرة: أفضل فرصة شراء فوق، أسوأ سهم تحت

### ملاحظة تقنية:
- HA markdown cards تدعم markdown tables ✅
- يحتاج Jinja2 templating لبناء الجداول ديناميكيًا
- الـ data كلها متاحة الآن من A1+A2 (timeframe, volume, action, watch_reason)
- card_mod style يحتاج: `direction: rtl; font-size: 12px;`
- الجداول تحتاج: `table { width: 100%; } th { text-align: right; }`

### Implementation Notes لـ Claude Code:
- استخدم Jinja2 for loops مع markdown table syntax
- كل صف = سهم واحد من الـ context/signals/watchlist
- الألوان عبر emoji فقط (HA markdown ما يدعم inline CSS في الجداول)
- RTL: الأعمدة من اليمين لليسار
- Decision Card (القسم 3) يبقى markdown عادي — مو جدول


---

# ADDENDUM: B1 Redesign Direction (Updated)

## المبدأ: جداول مرتبة حسب الأهمية — ليس سطور نصية

### التصميم المستهدف لصفحة التداول:

## Section 1: Hero (compact — موجود ✅)
سطر واحد: منصة التداول · السوق مفتوح/مغلق · 128 سهم

## Section 2: Decision Board (أقوى فرصة — كارت واحد بارز)
كارت واحد كبير نسبياً — أهم سهم فقط.
بدل نص متتالي → صفين أو ثلاثة بتنسيق واضح:

```
⭐ الاتصالات المستقلة — 566.0 فلس · ▲ +1.1%
📊 Score: 85/A · RSI: 64 · فريم: يومي · Volume: ×1.5
📈 صاعد — زخم صاعد · دعم: 550 · مقاومة: 580
💡 مراقبة — قريب من المقاومة
```

ألوان: border أصفر/ذهبي (أقوى فرصة)

## Section 3: فرص إضافية (جدول — مرتب حسب Score)
بدل سطور نصية متشابهة → جدول markdown:

```markdown
| السهم | السعر | النسبة | Score | فريم | Vol | Action |
|-------|-------|--------|-------|------|-----|--------|
| 🟢 المعادن | 99.1ف | +0.0% | A/85 | 1D | ×1.2 | شراء |
| 🟢 وريد | 176.0ف | +0.0% | A/80 | 1D | ×0.8 | انتظار |
| 🔴 الساحل | 59.4ف | -0.2% | A/80 | 1D | ×0.5 | انتظار |
| 🔴 الكويتية | 328.0ف | -3.2% | A/80 | 1D | — | بيع |
```

ملاحظة: HA markdown يدعم جداول — الخطوط والـ alignment محدودة لكن تشتغل.
الترتيب: حسب score تنازليًا (الأعلى أولاً)

## Section 4: 📡 إشارات 30m (جدول — أحدث أولاً)
```markdown
| الإشارة | السهم | السعر | الوقت | Score | قوة |
|---------|-------|-------|-------|-------|-----|
| 🟢 bullish cross | Action Energy | 283.0ف | 06:33 | C/35 | متوسطة |
| 🔴 bearish | البيوت القابضة | 357.0ف | 06:17 | B/50 | متوسطة |
| 🟢 bullish | المباني | 968.0ف | 06:16 | C/45 | متوسطة |
```

واضح إن هذي **30m signals** (الفريم مكتوب في العنوان)

## Section 5: بقية السياق اليومي (جدول مع verdict)
```markdown
| السهم | السعر | النسبة | Score | RSI | Verdict | Action |
|-------|-------|--------|-------|-----|---------|--------|
| 🟢 الخليج للتأمين | 790.0ف | +5.2% | A/80 | — | ضغط بيعي | ⚠️ حذر |
| 🟢 الشبك | 569.0ف | -1.9% | A/80 | — | ضغط بيعي | ⚠️ حذر |
| 🔴 بنك الكويت | 909.0ف | -1.7% | A/75 | — | زخم ضعيف | 🔴 حذر |
```

## Section 6: المراقبة (جدول مع السبب — الأهم)
بدل أسماء مرمية → جدول بسبب المراقبة:

```markdown
| السهم | السعر | النسبة | فريم | السبب |
|-------|-------|--------|------|-------|
| الاتصالات المستقلة | 566.0ف | +1.1% | 30m | زخم صاعد قوي |
| أسمنت بورتلاند | 328.0ف | -3.2% | 1D | قريب من الدعم |
| بورصة الكويت | — | — | 30m | تقييم متوسط |
```

الآن كل سهم في المراقبة عنده **سبب واضح**.

## Section 7: Diagnostics (سطر واحد — موجود ✅)

---

## ملاحظات تقنية لـ Claude Code:

1. **HA markdown يدعم جداول** — اختبر أولاً بجدول صغير
2. **RTL مع جداول:** يحتاج `direction: rtl` على الكارت + قد يحتاج `text-align: right` على الجدول
3. **الترتيب حسب الأهمية:** استخدم Jinja sort:
   `{% for s in ctx | sort(attribute='score', reverse=true) %}`
4. **الـ fields الجديدة من A1+A2:**
   - `source_timeframe`: "1D" أو "30m"
   - `vol_ratio`: مثل 2.59
   - `avg_volume`: مثل 6717103
   - `action`: "buy"/"sell"/"watch"/"hold"
   - `action_ar`: "شراء"/"بيع"/"مراقبة"/"انتظار"
   - `price` (في watchlist)
   - `change_pct` (في watchlist)
   - `watch_reason` (في watchlist)
5. **حجم الأيقونات:** لا أيقونات — emoji فقط في الجداول
6. **الفريم:** يكتب بوضوح في كل section header + في كل جدول


---

# ADDENDUM: B1 Table-Based Redesign

## المبدأ: جداول مرتبة حسب الأهمية — ليس سطور نصية

## تصميم مستهدف:

### Decision Board: كارت واحد بارز - أهم سهم
```
⭐ الاتصالات المستقلة — 566.0 فلس · +1.1%
📊 Score: 85/A · RSI: 64 · فريم: يومي · Volume: x1.5
📈 صاعد — دعم: 550 · مقاومة: 580
💡 مراقبة — قريب من المقاومة
```

### فرص إضافية: markdown table مرتب حسب Score
| السهم | السعر | النسبة | Score | فريم | Vol | Action |

### إشارات 30m: markdown table
| الإشارة | السهم | السعر | الوقت | Score | قوة |

### بقية السياق: markdown table مع verdict
| السهم | السعر | النسبة | Score | RSI | Verdict | Action |

### المراقبة: markdown table مع السبب
| السهم | السعر | النسبة | فريم | السبب |

## ملاحظات لـ Claude Code:
1. HA markdown يدعم جداول
2. RTL: يحتاج direction:rtl + text-align:right
3. ترتيب: sort(attribute=score, reverse=true)
4. Fields جديدة: source_timeframe, vol_ratio, action, action_ar, watch_reason
5. الفريم يكتب في header + في الجدول


---

# ADDENDUM 2 — EMA Cross Analysis
# تاريخ: 2026-03-20

## المطلوب: إضافة تقاطع EMA 9/21 في صفحة التداول

### لماذا مهم:
- EMA 9 فوق EMA 21 = صاعد (bullish cross)
- EMA 9 تحت EMA 21 = هابط (bearish cross)
- التقاطع الحديث = إشارة قوية
- المسافة بينهم = قوة الزخم

### المطلوب Backend (Package A6):
- حساب EMA 9 و EMA 21 لكل سهم في radar_daily_context
- إضافة fields:
  - `ema9`: قيمة EMA 9
  - `ema21`: قيمة EMA 21
  - `ema_cross`: "bullish" (9 فوق 21) / "bearish" (9 تحت 21) / "neutral" (متقاربين)
  - `ema_cross_days`: كم يوم من التقاطع (إذا متاح)
  - `ema_gap_pct`: نسبة الفارق بين EMA 9 و 21 (يوضّح قوة الزخم)
- الملف: server.py (في بناء radar_daily_context)
- البيانات: تحتاج closing prices آخر 21 يوم على الأقل
- Git: V95-A6: add EMA 9/21 cross analysis to radar context

### المطلوب Dashboard (ضمن Package B1):
- في جدول الفرص أضف عمود "EMA":
  | السهم | السعر | %Δ | RSI | Vol | EMA | الفريم | الاتجاه | Action |
  حيث EMA تعرض:
  - `📈 9>21` = bullish cross (أخضر)
  - `📉 9<21` = bearish cross (أحمر)
  - `➡️ متقارب` = neutral
  
- في Decision Card (أقوى فرصة) أضف سطر:
  "EMA: 📈 تقاطع صاعد (9: 560 > 21: 545) — منذ 3 أيام"

- في ترتيب الأسهم، EMA cross يؤثر على الأولوية:
  - bullish cross حديث (< 5 أيام) يرفع الأولوية
  - bearish cross يخفض الأولوية

### تحسين Action Logic (تحديث A1):
Action الحالي يعتمد على: score + trend + RSI + signals
المحدّث يضيف EMA cross:
- score ≥ 70 + صاعد + RSI < 70 + EMA bullish → `buy` (شراء — مؤكد)
- score ≥ 70 + صاعد + RSI < 70 + EMA bearish → `watch` (مراقبة — إشارات متضاربة)
- هابط + EMA bearish → `sell` (بيع — مؤكد)
- هابط + EMA bullish → `watch` (مراقبة — تقاطع إيجابي رغم الهبوط)

### الترتيب في التنفيذ:
A6 يُنفذ قبل B1 — لأن B1 يحتاج الـ fields الجديدة
```
A1 (done) → A2 (done) → A3 (done) → A4 → A5 → A6 → B1 → B2
```
