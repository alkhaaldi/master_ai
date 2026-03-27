# NEWS OVERHAUL PLAN — V11 Rich News Dashboard
# ================================================================
# تاريخ: 2026-03-20
# الهدف: تحويل نظام الأخبار من 11 مصدر/12 خبر إلى 25+ مصدر/60+ خبر
# المبدأ: Backend أولاً (news_engine.py + server.py) ثم Dashboard
# ================================================================

---

# السياق الحالي

## news_engine.py (299 سطر):
- SOURCES: 11 مصدر فقط
- CATEGORIES: 3 (kuwait, economy, technology)
- fetch_rss(): يسحب RSS/Atom feeds
- fetch_category(): يسحب كل مصادر فئة + dedupe
- generate_digest(): يسحب أخبار → LLM يلخّص → يحفظ بـ DB
- max_per_source: 8 عناوين لكل مصدر
- items[:30]: يرسل أقصى 30 عنوان لـ LLM
- LLM prompt يطلب 12-15 خبر

## server.py scheduler (سطر ~2595):
- Auto-digest كل 6 ساعات
- يستدعي generate_digest(slot="auto")

## المشاكل:
1. tech_len = 0 → TechCrunch/Ars Technica feeds ممكن ميتة أو محجوبة
2. 11 مصدر فقط — لا Reuters, لا CNBC, لا Verge, لا gadgets
3. كل 6 ساعات = أقصى 4 digest يومياً
4. 12-15 خبر فقط بالملخص — قليل جداً
5. لا فئة AI ولا gadgets
6. المصادر الكويتية = Google News proxy بدل مصادر مباشرة

---

# Phase A — Expand Sources (news_engine.py فقط)

## Package A1: Replace SOURCES list

### التغيير: استبدل SOURCES بالكامل

```python
SOURCES = [
    # ═══ BREAKING / WORLD ═══
    {"name": "Reuters World", "url": "https://feeds.reuters.com/reuters/worldNews", "category": "world", "mode": "rss"},
    {"name": "AP News", "url": "https://rsshub.app/apnews/topics/apf-topnews", "category": "world", "mode": "rss"},
    {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "category": "world", "mode": "rss"},
    {"name": "BBC Middle East", "url": "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml", "category": "world", "mode": "rss"},
    {"name": "Al Jazeera EN", "url": "https://www.aljazeera.com/xml/rss/all.xml", "category": "world", "mode": "rss"},

    # ═══ ECONOMY / MARKETS ═══
    {"name": "Reuters Business", "url": "https://feeds.reuters.com/reuters/businessNews", "category": "economy", "mode": "rss"},
    {"name": "CNBC Top", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "category": "economy", "mode": "rss"},
    {"name": "Bloomberg", "url": "https://feeds.bloomberg.com/markets/news.rss", "category": "economy", "mode": "rss"},
    {"name": "BBC Business", "url": "https://feeds.bbci.co.uk/news/business/rss.xml", "category": "economy", "mode": "rss"},
    {"name": "FT Markets", "url": "https://www.ft.com/markets?format=rss", "category": "economy", "mode": "rss"},
    {"name": "Google Boursa", "url": "https://news.google.com/rss/search?q=boursa+kuwait+stock+exchange&hl=en&gl=KW&ceid=KW:en", "category": "economy", "mode": "rss"},

    # ═══ KUWAIT / LOCAL ═══
    {"name": "Google Kuwait AR", "url": "https://news.google.com/rss/search?q=الكويت&hl=ar&gl=KW&ceid=KW:ar", "category": "kuwait", "mode": "rss"},
    {"name": "Google Kuwait EN", "url": "https://news.google.com/rss/search?q=kuwait&hl=en&gl=KW&ceid=KW:en", "category": "kuwait", "mode": "rss"},
    {"name": "Al Jazeera AR", "url": "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4571-a358-a3a4f68f135d/73d0e1b4-532f-45ef-b135-bfdba6e76a42", "category": "kuwait", "mode": "rss"},
    {"name": "BBC Arabic", "url": "https://feeds.bbci.co.uk/arabic/rss.xml", "category": "kuwait", "mode": "rss"},
    {"name": "KUNA", "url": "https://www.kuna.net.kw/RSS/ar_econ.xml", "category": "kuwait", "mode": "rss"},

    # ═══ TECHNOLOGY ═══
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "category": "technology", "mode": "rss"},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "category": "technology", "mode": "rss"},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "category": "technology", "mode": "rss"},
    {"name": "Wired", "url": "https://www.wired.com/feed/rss", "category": "technology", "mode": "rss"},
    {"name": "Hacker News", "url": "https://hnrss.org/frontpage?points=100", "category": "technology", "mode": "rss"},

    # ═══ AI ═══
    {"name": "Google AI News", "url": "https://news.google.com/rss/search?q=artificial+intelligence+OR+ChatGPT+OR+Claude+OR+GPT&hl=en&gl=US&ceid=US:en", "category": "ai", "mode": "rss"},
    {"name": "MIT AI", "url": "https://news.mit.edu/rss/topic/artificial-intelligence2", "category": "ai", "mode": "rss"},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/", "category": "ai", "mode": "rss"},

    # ═══ GADGETS ═══
    {"name": "9to5Mac", "url": "https://9to5mac.com/feed/", "category": "gadgets", "mode": "rss"},
    {"name": "9to5Google", "url": "https://9to5google.com/feed/", "category": "gadgets", "mode": "rss"},
    {"name": "GSMArena", "url": "https://www.gsmarena.com/rss-news-reviews.php3", "category": "gadgets", "mode": "rss"},
]
```

### أيضاً: حدّث CATEGORIES

```python
CATEGORIES = {
    "world": {"ar": "عالمي", "emoji": "🌍"},
    "economy": {"ar": "الاقتصاد", "emoji": "💰"},
    "kuwait": {"ar": "الكويت", "emoji": "🇰🇼"},
    "technology": {"ar": "التكنولوجيا", "emoji": "💻"},
    "ai": {"ar": "ذكاء اصطناعي", "emoji": "🤖"},
    "gadgets": {"ar": "أجهزة", "emoji": "📱"},
}
```

### ملاحظات:
- بعض الـ feeds قد تكون محجوبة من RPi — لازم يختبرهم واحد واحد
- Reuters feeds قد تحتاج user-agent header
- rsshub.app هو proxy لـ AP News — إذا ما اشتغل، استخدم Google News search بدل
- KUNA RSS قد يكون ميت — إذا ما اشتغل، شيله
- FT قد يكون paywall — إذا ما اشتغل، شيله

### الاختبار:
```bash
# اختبر كل feed
python3 -c "
import asyncio
from news_engine import fetch_rss, SOURCES
async def test():
    for s in SOURCES:
        items = await fetch_rss(s['url'], max_items=3)
        print(f'{s[\"name\"]:20s} → {len(items)} items')
asyncio.run(test())
"
```

إذا feed يرجع 0 items → شيله أو بدّله. لا تترك feeds ميتة.

### Git: V11-A1: expand news sources from 11 to 26 with 6 categories

---

## Package A2: Increase Digest Capacity

### التغيير في news_engine.py:

1. `max_per_source=8` → `max_per_source=10`
2. `items[:30]` → `items[:50]` (في generate_digest — أرسل أكثر لـ LLM)
3. في الـ prompt: "اكتب 12-15 خبر" → "اكتب 20-25 خبر"
4. `max_tokens=2000` → `max_tokens=3000`

### التغيير في الـ prompt:
أضف السطور الجديدة:
```
- اكتب 20-25 خبر (وليس أقل من 18)
- قسّم الأخبار بعناوين فرعية:
  ## 🔥 عاجل وعالمي
  ## 💰 اقتصاد وأسواق
  ## 🇰🇼 محلي
  ## 💻 تقنية
  ## 🤖 ذكاء اصطناعي
  ## 📱 أجهزة
```

### Git: V11-A2: increase digest capacity to 25 items with section headers

---

## Package A3: Fix Scheduler + Add Category Counts

### التغيير في server.py (~سطر 2596):
- `every 6h` → `every 3h` (غيّر الـ sleep)

### التغيير في server.py (endpoint /dashboard/extended — news section):
أضف category counts في الـ news_digest response:
```python
# بعد ما يجيب الـ digest
if digest and digest.get("summary_text"):
    text = digest["summary_text"]
    # Count by section headers or emoji
    urgent_lines = [l for l in text.split('\n') if l.strip().startswith(('🔥', '⚔️', '🌍'))]
    economy_lines = [l for l in text.split('\n') if l.strip().startswith('💰')]
    local_lines = [l for l in text.split('\n') if l.strip().startswith('🇰🇼')]
    tech_lines = [l for l in text.split('\n') if l.strip().startswith(('💻', '⚡'))]
    ai_lines = [l for l in text.split('\n') if l.strip().startswith('🤖')]
    gadget_lines = [l for l in text.split('\n') if l.strip().startswith('📱')]
```

**لكن هذا الكود موجود بالفعل** في V9.5 (news-split fields). تحقق أولاً:
- هل الـ split fields (urgent, economic, local, tech, other) تُملأ صح؟
- إذا فيه فئات جديدة (ai, gadgets) → لازم الـ split logic يتعرف عليهم

### إضافة split fields جديدة:
في الـ endpoint اللي يبني news_digest fields:
```python
# أضف بعد الـ existing splits:
ai_lines = [l for l in lines if l.strip().startswith('🤖')]
gadget_lines = [l for l in lines if l.strip().startswith('📱')]
news_data["ai"] = "\n".join(ai_lines) if ai_lines else ""
news_data["gadgets"] = "\n".join(gadget_lines) if gadget_lines else ""
```

### Git: V11-A3: scheduler every 3h + add ai/gadgets split fields

---

# Phase B — Dashboard (YAML only — بعد Phase A)

## Package B1: Add AI + Gadgets Sections to News Page

### الملف: master_ai_dashboard.yaml (sub-news section)

### إضافة كارتين جديدتين بعد "⚡ تقنية ومتفرقات":

**كارت "🤖 ذكاء اصطناعي":**
```yaml
- type: markdown
  card_mod:
    style: |
      ha-card {
        background: rgba(180,120,255,0.04);
        border: 1px solid rgba(180,120,255,0.10);
        border-right: 3px solid rgba(180,120,255,0.30);
        border-radius: 0;
        padding: 12px 16px;
        margin: 6px 8px 0;
      }
      ha-markdown { font-size: 14px; direction: rtl; line-height: 2.0; }
  content: |
    **🤖 ذكاء اصطناعي**
    {% set e = 'sensor.master_ai_extended' %}
    {% set d = state_attr(e,'news_digest') %}
    {% if d and d.ai %}
    {{ d.ai }}
    {% else %}
    🤖 لا أخبار AI
    {% endif %}
```

**كارت "📱 أجهزة":**
```yaml
- type: markdown
  card_mod:
    style: |
      ha-card {
        background: rgba(0,200,150,0.04);
        border: 1px solid rgba(0,200,150,0.10);
        border-right: 3px solid rgba(0,200,150,0.30);
        border-radius: 0;
        padding: 12px 16px;
        margin: 6px 8px 0;
      }
      ha-markdown { font-size: 14px; direction: rtl; line-height: 2.0; }
  content: |
    **📱 أجهزة وتقنيات**
    {% set e = 'sensor.master_ai_extended' %}
    {% set d = state_attr(e,'news_digest') %}
    {% if d and d.gadgets %}
    {{ d.gadgets }}
    {% else %}
    📱 لا أخبار أجهزة
    {% endif %}
```

### Git: V11-B1: add AI and gadgets sections to news dashboard

---

## Package B2: Update News Hero for 6 Categories

### تحديث hero ليعدّ 6 فئات:

```yaml
content: |
  ## الأخبار
  {% set e = 'sensor.master_ai_extended' %}
  {% set d = state_attr(e,'news_digest') %}
  {% if d %}
  {% set cats = [] %}
  {% if d.urgent %}{% set cats = cats + ['🔥 ' ~ d.urgent.split('\n') | reject('eq','') | list | length ~ ' عاجل'] %}{% endif %}
  {% if d.economic %}{% set cats = cats + ['💰 ' ~ d.economic.split('\n') | reject('eq','') | list | length ~ ' اقتصادي'] %}{% endif %}
  {% if d.local %}{% set cats = cats + ['🇰🇼 ' ~ d.local.split('\n') | reject('eq','') | list | length ~ ' محلي'] %}{% endif %}
  {% if d.tech %}{% set cats = cats + ['💻 ' ~ d.tech.split('\n') | reject('eq','') | list | length ~ ' تقني'] %}{% endif %}
  {% if d.ai %}{% set cats = cats + ['🤖 ' ~ d.ai.split('\n') | reject('eq','') | list | length ~ ' AI'] %}{% endif %}
  {% if d.gadgets %}{% set cats = cats + ['📱 ' ~ d.gadgets.split('\n') | reject('eq','') | list | length ~ ' أجهزة'] %}{% endif %}
  {{ cats | join(' · ') }} · 📰 {{ d.item_count | default(0) }} خبر · {{ d.date | default('') }}
  {% else %}
  📰 لا أخبار — استخدم /news_now
  {% endif %}
```

### Git: V11-B2: news hero counts all 6 categories

---

# Execution Order

```
Phase A (Backend — يحتاج apply_text_patch.py):
A1 → اختبار كل feed → A2 → A3 → trigger /news_now لاختبار
(المصادر أولاً → السعة → الجدولة)

Phase B (Dashboard — YAML فقط — بعد Phase A):
B1 → B2
(كروت جديدة → hero محدّث)
```

---

# Claude Code Instructions

## لـ A1 (أهم package):
```
1. اقرأ news_engine.py
2. استبدل SOURCES list بالكاملة
3. استبدل CATEGORIES dict
4. quick_check.py + smoke_test.py
5. اختبر كل feed واحد واحد:
   python3 -c "
   import asyncio
   from news_engine import fetch_rss, SOURCES
   async def test():
       for s in SOURCES:
           items = await fetch_rss(s['url'], max_items=3)
           status = '✅' if len(items) > 0 else '❌'
           print(f'{status} {s[\"name\"]:20s} → {len(items)} items')
   asyncio.run(test())
   "
6. احذف أي feed يرجع 0 items
7. git commit
8. restart
```

## لـ A2:
```
1. في news_engine.py: max_per_source → 10
2. في generate_digest: items[:30] → items[:50]
3. حدّث الـ prompt (20-25 خبر + عناوين فرعية)
4. max_tokens → 3000
5. quick_check + smoke_test
6. git commit + restart
```

## لـ A3:
```
1. في server.py: غيّر sleep من 6h إلى 3h
2. أضف ai/gadgets split fields في news endpoint
3. quick_check + smoke_test
4. git commit + restart
5. اختبر: /news_now من Telegram — تأكد الأخبار تجي
```

## لـ B1+B2:
```
1. عدّل master_ai_dashboard.yaml (sub-news section)
2. أضف كارتين: AI + Gadgets
3. حدّث Hero
4. YAML validate + git commit + YAML reload
```

## ما لا يُلمس:
- لا تعدل fetch_rss() logic
- لا تعدل DB schema
- لا تعدل endpoints الحالية — فقط أضف fields جديدة
- لا تعدل صفحات أخرى (التداول/البيت/البريد — مكتملة)

---

# Acceptance Criteria

## بعد Phase A:
- [ ] 20+ مصدر شغال (لا feeds ميتة)
- [ ] 6 فئات: world, economy, kuwait, technology, ai, gadgets
- [ ] كل digest يحتوي 20+ خبر
- [ ] Scheduler كل 3 ساعات
- [ ] split fields: urgent, economic, local, tech, ai, gadgets

## بعد Phase B:
- [ ] صفحة الأخبار فيها 6 أقسام
- [ ] Hero يعدّ 6 فئات
- [ ] أخبار AI ظاهرة
- [ ] أخبار أجهزة ظاهرة

## المعيار النهائي:
- [ ] أفتح صفحة الأخبار وأشوف 6 أقسام بأخبار طازجة ومتنوعة
