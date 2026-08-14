# ARCHITECTURE_MAP.md — مخرج المرحلة 0

> تاريخ الفحص: 2026-08-14 · `master_ai` v9.0.0 · فرع `main` · commit `5529cb4`
> **قراءة فقط.** لا تعديل كود، لا commit، لا restart. المصدر: `/system/context` + الكود الحيّ.

---

## 0.1 — مصادر الحقيقة (مقروءة)

| المصدر | النتيجة |
|---|---|
| `GET /system/context` | 200 — v9.0.0، schema 3.4.0، drift=0، 34 جدول، 9 plugins، autonomy level 3 |
| `GET /health` | 200 — uptime وقت الفحص 2031s، `queued_jobs=1`، 94 حدث |
| `_tools/OPERATIONAL_ACCESS_MATRIX.md` | مقروء — يثبّت قاعدة "لا 5xx لأي endpoint يستهلكه الداشبورد" (Cloudflare يستبدلها بـ HTML) |
| `_tools/ADDING_NEW_DASHBOARD_FIELDS.md` | مقروء — سلسلة endpoint → `json_attributes` → sensor → بطاقة |
| `CLAUDE_CONTEXT.md` | مقروء |
| `git log -150` + `git show 651b154` | مقروء — انظر السؤال 7 |

### تصحيحات على افتراضات الخطة

| الخطة تقول | الواقع |
|---|---|
| 12 صفحة HTML | **20** صفحة في `www/trading/` |
| 125 مسار | **180** مسار حيّ (239 ديكوريتر في الكود، الفرق سكربتات patch في `_tools/` و`data/` غير محمّلة) |
| 258 استيراد داخل الدوال | **389** |
| `_tools/ARCHITECTURE_MAP.md` سيغطي كل شيء | تصنيف المجال في 0.3 استُنتج بأنماط أسماء؛ عمود **حية/ميتة** وحده مبني على تحليل AST فعلي وهو الموثوق |

### طوبولوجيا الوصول (مثبّتة عملياً)

- الخدمة: `192.168.109.123:9000` — RPi، اسم المضيف `homeassistant`، يشغّل HA و master_ai معاً.
- SSH: `ssh pi@192.168.109.123` ✅
- المستودع: `/var/lib/homeassistant/share/master_ai`. **`/home/pi/master_ai` رابط رمزي لنفسه** (نفس الـ inode) — نسخة واحدة لا نسختان.
- إعدادات HA: `/var/lib/homeassistant/homeassistant/configuration.yaml` (= `H:\`)
- الوحدة: `master-ai.service` → uvicorn، `WorkingDirectory=/home/pi/master_ai`.

---

## 0.2 — سلاسل البيانات

### السلسلة A — TradingView → Bridge → radar 30m ⛔ **مقطوعة الآن**

```
TradingView → Bridge (PC 192.168.111.214:8059) → bridge_client.py → radar 30m
            → /dashboard/signals-30m → signals.html (تاب حية)
```

**حالة الفحص: الـ Bridge لا يعمل.** لا شيء يستمع على 8059 لا من الـ RPi ولا محلياً على الـ PC نفسه (تأكدت من الجهتين: `curl` رجّع `000`، و`netstat` لا يُظهر منفذ 8059). الـ PC هو فعلاً `192.168.111.214`، فالعنوان صحيح والعملية متوقفة.

`BRIDGE_URL=http://192.168.111.214:8059` مضبوط في `.env` (commit `19dee73` نقله إلى متغير بيئة، و`4edc803` أعاد الـ IP إلى `.158` ثم عاد إلى `.214`).

### السلسلة B — اللقطة اليومية

```
refresh_daily_snapshot() → stock_radar_daily → /dashboard/radar → signals.html (تاب يومي)
```
`/dashboard/radar` في `OPEN_PATHS` + يستهلكه حسّاس HA بمفتاح (`scan_interval: 120`).

### السلسلة C — endpoint → HA sensor → بطاقة ✅ سليمة

9 حسّاسات `rest:` في `configuration.yaml`، **وكلها ترسل `X-API-Key`**:

| المسار | scan_interval | داخل OPEN_PATHS؟ |
|---|---|---|
| `/dashboard` | 30 | نعم |
| `/dashboard/extended` | 120 | نعم |
| `/dashboard/radar` | 120 | نعم |
| `/dashboard/portfolio` | 120 | نعم |
| `/dashboard/journal` | 120 | نعم |
| `/dashboard/signals` | 120 | نعم |
| `/dashboard/analysis` | 300 | **لا — يعتمد على المفتاح** |
| `/dashboard/alerts` | 300 | **لا — يعتمد على المفتاح** |
| `/dashboard/confluence` | 120 | **لا — يعتمد على المفتاح** |

نتيجة عملية: **إغلاق `/api/` لا يمسّ حسّاسات HA إطلاقاً.** الثلاثة الأخيرة تعمل بالمفتاح وحده، وهذا دليل مباشر أن مسار المفتاح شغّال لمن يرسله.

### السلسلة D — Autonomy

`/system/context` يؤكد العتبات المعلنة حرفياً: `auto_max=30` · `approval_max=60` · `block_min=61`، `enabled=true`, `level=3`, `allow_medium=false`, `allow_high=false`. `approval_ux.py` يعالج `ssh_run` ضمن مسار الموافقة.

⚠️ `/health` يُظهر **48 حدثاً في `waiting_approval`** و9 `expired`، وآخر حدث `2026-08-08` — أي منذ 6 أيام. طابور الموافقات متروك ولا أحد يصرّفه.

### السلسلة E — الحلقات المجدولة

~26 حلقة تُطلق في `lifespan` عبر `asyncio.create_task`، كثير منها خلف أعلام (`BRAIN_OK`, `CONFLUENCE_OK`, `JOURNAL_OK`…). حلقتان معطّلتان صراحة بتعليق:
- `analysis_daily_scheduler()` (سطر 2697)
- `proactive_suggestion_loop()` (سطر 2707 — "disabled: 0 activity")

**لا يوجد مراقب لفشل هذه الحلقات.** `create_task` بدون `add_done_callback`: أي استثناء غير ملتقط يقتل الحلقة بصمت ويبقى التطبيق يعمل. هذا بالضبط ما يبرّر البند P1-8، ويجب أن يقتصر عليها.

---

## 0.5 — دورات الاستيراد

**دورتان فقط (SCC حجمه > 1)، و3 أزواج مباشرة:**

| الدورة | الوحدات |
|---|---|
| SCC-1 | `journal_engine` ↔ `position_engine` |
| SCC-2 | `signal_engine` ↔ `trading_brain` ↔ `stock_radar` |

389 استيراد داخل الدوال، لكن الدورات الفعلية **دورتان**. الخلاصة المهمة: العدد الضخم ليس دليل تشابك بنيوي عميق — تفكيك `server.py` ممكن تقنياً، والعائق الحقيقي أن `server.py` يستورد **88** وحدة محلية ويحوي 141 ديكوريتر مسار في 9322 سطراً.

0 أخطاء تحليل نحوي في الـ130 وحدة.

---

## 🚪 البوابة — إجابات الأسئلة السبعة

### 1. إذا أغلقنا `/api/` — أي صفحة تنكسر بالضبط؟

**7 صفحات، عبر 22 مساراً.** لا تنكسر حسّاسات HA ولا Telegram.

| الصفحة | عدد مسارات `/api/` | ترسل مفتاحاً؟ |
|---|---|---|
| `system.html` | 10 | ❌ |
| `positions.html` | 8 | ✅ (`?key=` من الـ URL) |
| `analysis.html` | 2 | ❌ |
| `personality.html` | 2 | ❌ |
| `decisions.html` | 1 | ❌ |
| `radar.html` | 1 | ❌ |
| `signals.html` | 1 | ❌ (`/api/stocks/symbol/{symbol}`) |

**الجواب المباشر: نعم، الإغلاق الأعمى يكسر 6 صفحات من 7 فوراً.** `positions.html` وحدها تنجو — وفقط إذا فُتحت بـ `?key=…`.

هذا يثبت أن تحذير الخطة كان في محله. الطريق الآمن = allowlist صريح للقراءة (`GET`) للـ 14 مساراً غير المتحوّل، ثم إصلاح مصادقة الصفحات قبل إغلاق المسارات المتحوّلة الثمانية.

**9 مسارات `/api/` لا يستهلكها أحد إطلاقاً** — إغلاقها بلا أثر:
`POST /api/analyze/refresh-all` · `GET /api/hooks/log` · `GET /api/hooks/stats` · `GET /api/kairos/log` · `POST /api/news/refresh-boursa` · `POST /api/news/refresh-gemini` · `GET /api/portfolio/transactions/{trade_id}` · `POST /api/refresh-analysis` · `POST /api/review-now`

### 2. كيف تصادق صفحات الداشبورد نفسها؟

**في الغالب لا تصادق أصلاً.**

- **2 صفحتان من 20** ترسلان `X-API-Key`: `positions.html` و`journal.html`.
- `getApiKey()` موجودة في `positions.html` فقط، وتقرأ المفتاح من **query string الصفحة**: `new URLSearchParams(window.location.search).get('key')`. أي أن المفتاح يجب أن يكون مكتوباً في `src` الـ iframe داخل HA — ومن ثم يظهر في سجلات المتصفح والـ referrer.
- **الـ18 صفحة الباقية تعمل حصراً بفضل ثغرتين معماريتين**: `/trading/` متجاوَز فتُقدَّم الصفحة، و`/api/` + `OPEN_PATHS` متجاوزان فتُقدَّم البيانات.

**استنتاج**: لا توجد اليوم آلية مصادقة حقيقية للداشبورد. البند P0-3 ليس "أغلق `/api/`" بل "ابنِ للداشبورد مصادقة أولاً". هذه هي الفجوة الجوهرية التي أخفاها الفحص الثابت السابق.

### 3. ماذا يحدث للـ radar لو وقف الـ Bridge؟

الـ degraded mode **مطبّق فعلاً** في `dashboard_api.py` (وليس في `bridge_client.py`): `_check_bridge_health()` تُستدعى في 3 مواضع (أسطر 159، 382، 665)، وتضيف `degraded_mode: "bridge_offline"` و`degraded_reason: "Bridge offline: …"` إلى الاستجابة، مع علامة `⚠` في ملخص نصي (سطر 308–309). أما `bridge_client.py` نفسه فيرجع `None` بصمت عند الفشل (أسطر 52، 62، 77، 100).

**من يراه:** من يقرأ حقل `degraded_mode` في استجابة JSON. لا يوجد تنبيه Telegram ولا حسّاس HA مخصص له.

**وهذا ليس افتراضياً الآن — الـ Bridge متوقف فعلاً وقت هذا الفحص، ولم يلاحظ أحد.** وهو الدليل العملي على أن `degraded_mode` غير مرئي كفاية.

### 4. تاب "حية" وتاب "يومي" في `signals.html` — مصدر واحد أم مصدران؟

**مصدران منفصلان، ونقطة الالتقاء هي الصفحة نفسها فقط.** `signals.html` تنادي 4 مسارات:

| المسار | التاب | السلسلة |
|---|---|---|
| `/dashboard/signals-30m` | حية | A (يعتمد على Bridge) |
| `/dashboard/signals` | حية | A |
| `/dashboard/radar` | يومي | B (لقطة DB) |
| `/api/stocks/symbol/{symbol}` | مشترك عند النقر | — |

لا يوجد التقاء في الخادم ولا في قاعدة البيانات. النتيجة العملية: **عند توقف الـ Bridge يفرغ التاب الحيّ بينما يستمر التاب اليومي بعرض بيانات سليمة** — وهو ما يجعل العطل غير ملحوظ. هذا يفسّر مباشرة كيف مرّ توقف الـ Bridge دون انتباه.

### 5. أي جداول تكبر بلا سقف؟

6 قواعد بيانات حية (و6 ملفات `.db` بحجم صفر: `radar.db`, `kse_data.db`, `daily_snapshots.db`, `master_ai.db` ×2, وبقايا `audit.db` قديم 12K في جذر المستودع مقابل الحيّ `data/audit.db` 9.7MB).

| القاعدة | الجدول | صفوف | يقرأه الداشبورد مباشرة؟ |
|---|---|---|---|
| `life.db` (88 MB) | `signal_snapshots` | 67,109 | نعم — عبر مسارات الإشارات |
| `life.db` | `signal_outcomes` | 40,966 | جزئياً |
| `life.db` | **`confluence_signals`** | 15,474 | نعم — `/dashboard/confluence` |
| `life.db` | **`symbol_patterns`** | 6,400 | غير مباشر |
| `home_brain.db` (13 MB) | `state_changes` | 65,112 | لا |
| `home_brain.db` | `climate_log` | 18,325 | لا |
| `brain_patterns.db` (6.4 MB) | `daily_summary` | 38,891 | لا |
| `brain_patterns.db` | `device_patterns` | 6,541 | لا |
| `audit.db` | **`schema_migrations`** | **1,724** | لا |

**الأكبر ليس ما ذكرته الخطة.** البند P1-10 يستهدف `confluence_signals` (15K) و`symbol_patterns` (6K)، لكن `signal_snapshots` (67K) و`state_changes` (65K) و`daily_summary` (39K) أكبر منهما بأضعاف. الترتيب الصحيح للتقليم يبدأ من `life.db`.

`schema_migrations` بـ1,724 صفاً شذوذ قائم بذاته: جدول هجرات يُفترض أن يساوي عدد الهجرات (schema 3.4.0). يبدو أنه يُضيف صفاً في كل إقلاع.

### 6. `/ssh/run` — من يناديه فعلياً؟

**لا أحد.** المسار `POST /ssh/run` (`server.py:4225`) يظهر في 3 مواضع فقط، ولا واحد منها استدعاء:
- سطر 20 — docstring
- سطر 4225 — التعريف
- سطر 4465 — نص مساعدة `"ssh": "POST /ssh/run {cmd}"`

صفر نداءات من HTML أو YAML أو Telegram أو أي وحدة.

⚠️ **لكن انتبه للتمييز:** الـ **plugin** المسمى `ssh_run` شيء آخر تماماً وهو **حيّ ومسجّل** (`server.py:2061`، منطق التنفيذ `_exec_ssh_run` سطر 1878، ومعالجة الموافقة في `approval_ux.py:45`). يصله الطلب عبر نظام الوكلاء/الخطط لا عبر مسار HTTP.

**الأثر على P0-4:** حذف مسار HTTP `/ssh/run` آمن ولا يكسر شيئاً. لكن حذفه **لا يغلق** تنفيذ الأوامر — الـ plugin يظل الطريق الفعلي، وهو ما يجب أن تُوجَّه إليه المراجعة الأمنية. أضف أن المسار الآن `KEY REQUIRED` أصلاً، فهو ليس الثغرة المفتوحة التي قد يوحي بها اسمه.

### 7. commit `651b154` كسر ماذا؟

الرسالة تقول: *"Cleanup: archive 58 maintenance scripts to `_archive/`, organize codebase"*.
الواقع: **3 ملفات، 151 حذفاً** — نقل واحد (`dev_tools/quick_query.py`) و**حذف نهائي** لملفين لم يُؤرشفا:
- `daily_stats.py` (54 سطراً) — محذوف
- `recovery.py` (97 سطراً) — محذوف

**ما انكسر:** `server.py` ما زال يستورد `daily_stats` في موضعين:
- `server.py:4384` — `from daily_stats import get_daily_stats`
- `server.py:4393` — `from daily_stats import capture_stats`

كلاهما داخل `try/except` يرجع `{"error": "daily_stats module not available"}`. فالمسارات لا تنهار، لكنها **ترجع خطأ ثابتاً منذ 2 مارس 2026 — أكثر من 5 أشهر — بلا سطر سجل واحد.**

ملاحظة دقيقة: إرجاع 200 مع خطأ في الجسم موافق لقاعدة Cloudflare في `OPERATIONAL_ACCESS_MATRIX.md`، فالنمط ليس خاطئاً بذاته. الخلل أن الفشل **لا يُسجَّل**، فبقي غير مرئي. جدول `daily_stats` نفسه ما زال موجوداً في `audit.db` بـ7 صفوف — بيانات متجمدة منذ الحذف.

`recovery.py` لا مستورد له (الإشارات النصية إلى "recovery" في وحدات أخرى غير ذات صلة).

---

## الخلاصة قبل المرحلة 1

ثلاث نتائج تغيّر ترتيب الخطة:

1. **`/api/` لا يمكن إغلاقها كبند مستقل.** 6 صفحات لا ترسل مفتاحاً أصلاً. المصادقة للداشبورد شرط سابق، لا نتيجة لاحقة.
2. **الـ Bridge متوقف الآن** والسلسلة A ميتة، ولم يُنبّه أحد. هذه مشكلة تشغيلية قائمة تسبق أي إعادة هيكلة.
3. **`/ssh/run` ليس الخطر؛ الـ plugin `ssh_run` هو الخطر** — وهو خارج نطاق البند P0-4 كما كُتب.

**توقف. بانتظار موافقة المستخدم قبل المرحلة 1.**

---
## 0.3 — تصنيف الوحدات (130 وحدة top-level)

| الوحدة | المجال | #يستوردها | #تستورد | الحالة |
|---|---|---|---|---|
| `anomaly_engine` | ? | 3 | 0 | حية |
| `approval_ux` | infra | 1 | 0 | حية |
| `auto_memory_extractor` | llm | 3 | 3 | حية |
| `benchmark_runner` | trading | 0 | 0 | **ميتة** |
| `brain` | llm | 3 | 7 | حية |
| `brain_analytics` | llm | 1 | 0 | حية |
| `brain_backfill` | llm | 0 | 2 | **ميتة** |
| `brain_core` | llm | 7 | 0 | حية |
| `brain_learning` | llm | 4 | 0 | حية |
| `brain_multiuser` | llm | 1 | 0 | حية |
| `brain_observability` | llm | 1 | 0 | حية |
| `brain_personality` | life | 1 | 0 | حية |
| `brain_proactive` | llm | 1 | 0 | حية |
| `bridge_client` | trading | 13 | 0 | حية |
| `bridge_client_new` | trading | 0 | 0 | **ميتة** |
| `calendar_db` | life | 3 | 0 | حية |
| `calendar_engine` | life | 4 | 2 | حية |
| `calendar_reminders` | life | 1 | 1 | حية |
| `calendar_reporting` | life | 4 | 1 | حية |
| `chat_v7` | ? | 1 | 29 | حية |
| `circuit_breaker` | ? | 3 | 0 | حية |
| `coalesced_executor` | ? | 4 | 0 | حية |
| `confidence_engine` | ? | 1 | 1 | حية |
| `confluence_engine` | trading | 2 | 0 | حية |
| `context_compactor` | ? | 2 | 0 | حية |
| `context_manager` | ? | 2 | 0 | حية |
| `corrections_loop` | ? | 2 | 0 | حية |
| `cost_tracker` | infra | 5 | 0 | حية |
| `dashboard_api` | ? | 3 | 22 | حية |
| `data_integrity` | ? | 1 | 1 | حية |
| `db_backup` | infra | 1 | 0 | حية |
| `degraded_mode` | ? | 1 | 0 | حية |
| `discovery` | home/HA | 2 | 0 | حية |
| `domain_kpis` | ? | 1 | 0 | حية |
| `dream_consolidator` | ? | 1 | 0 | حية |
| `dropzone_watcher` | infra | 0 | 0 | **ميتة** |
| `entity_health` | home/HA | 1 | 0 | حية |
| `entity_map_generator` | home/HA | 0 | 0 | **ميتة** |
| `equity_tracker` | trading | 1 | 1 | حية |
| `exec_policy` | ? | 2 | 1 | حية |
| `expenses_engine` | life | 4 | 0 | حية |
| `family_assistant` | ? | 2 | 0 | حية |
| `feature_flags` | ? | 6 | 0 | حية |
| `feedback_learner` | llm | 2 | 0 | حية |
| `gemini_scanner` | llm | 0 | 6 | **ميتة** |
| `golden_engine` | ? | 2 | 6 | حية |
| `google_auth_ext` | ? | 3 | 0 | حية |
| `ha_doctor` | home/HA | 1 | 0 | حية |
| `ha_history` | home/HA | 2 | 0 | حية |
| `habit_engine` | life | 3 | 0 | حية |
| `habit_tracker` | life | 0 | 0 | **ميتة** |
| `health_engine` | life | 3 | 0 | حية |
| `home_brain` | home/HA | 1 | 0 | حية |
| `hooks` | infra | 2 | 0 | حية |
| `inbox_engine` | life | 7 | 2 | حية |
| `intent_state_machine` | llm | 2 | 0 | حية |
| `journal_engine` | trading | 9 | 2 | حية |
| `kairos` | infra | 4 | 2 | حية |
| `kse_data_collector` | trading | 4 | 2 | حية |
| `life_expenses` | life | 2 | 0 | حية |
| `life_health` | life | 1 | 0 | حية |
| `life_router` | life | 1 | 0 | حية |
| `life_stocks` | trading | 3 | 0 | حية |
| `life_work` | life | 7 | 0 | حية |
| `master_ai_tool` | ? | 0 | 0 | **ميتة** |
| `memory_db` | llm | 3 | 1 | حية |
| `memory_prefetch` | llm | 0 | 1 | **ميتة** |
| `memory_recall` | llm | 1 | 1 | حية |
| `mini_planner` | ? | 2 | 0 | حية |
| `news_engine` | life | 8 | 2 | حية |
| `paper_trading` | trading | 1 | 1 | حية |
| `parallel_coordinator` | ? | 1 | 0 | حية |
| `plan_engine` | ? | 1 | 0 | حية |
| `position_engine` | trading | 3 | 1 | حية |
| `priority_engine` | ? | 4 | 3 | حية |
| `proactive_engine` | ? | 0 | 2 | **ميتة** |
| `proactive_suggestions` | ? | 1 | 2 | حية |
| `processing_cursor` | ? | 5 | 0 | حية |
| `quick_query` | ? | 2 | 18 | حية |
| `relationships_engine` | ? | 4 | 0 | حية |
| `risk_engine` | trading | 5 | 1 | حية |
| `scanner_universe` | ? | 1 | 0 | حية |
| `sector_map` | ? | 2 | 0 | حية |
| `self_check` | ? | 1 | 1 | حية |
| `server` | infra | 3 | 88 | جذر/entrypoint |
| `service_health` | life | 8 | 0 | حية |
| `session_memory` | llm | 2 | 0 | حية |
| `signal_engine` | trading | 3 | 6 | حية |
| `signal_review` | trading | 1 | 0 | حية |
| `skill_loader` | ? | 2 | 0 | حية |
| `smart_router` | ? | 1 | 0 | حية |
| `smart_tools` | ? | 1 | 0 | حية |
| `sr_engine` | ? | 2 | 0 | حية |
| `stock_alerts` | trading | 1 | 0 | حية |
| `stock_analyzer` | trading | 4 | 1 | حية |
| `stock_personality_engine` | trading | 1 | 0 | حية |
| `stock_radar` | trading | 21 | 7 | حية |
| `structured_memory` | llm | 4 | 0 | حية |
| `system_guardian` | infra | 3 | 0 | حية |
| `task_engine` | life | 6 | 0 | حية |
| `task_manager` | life | 3 | 0 | حية |
| `tasks_db` | life | 1 | 0 | حية |
| `tg_alerts` | infra | 2 | 2 | حية |
| `tg_email` | trading | 5 | 1 | حية |
| `tg_home` | home/HA | 1 | 0 | حية |
| `tg_intent_router` | llm | 1 | 4 | حية |
| `tg_logbook` | infra | 0 | 0 | **ميتة** |
| `tg_morning_report` | infra | 1 | 13 | حية |
| `tg_news` | life | 1 | 0 | حية |
| `tg_ops` | infra | 1 | 0 | حية |
| `tg_reminders` | life | 1 | 0 | حية |
| `tg_report` | infra | 1 | 3 | حية |
| `tg_session` | infra | 2 | 2 | حية |
| `tg_session_resolver` | infra | 1 | 0 | حية |
| `tg_stocks` | trading | 3 | 3 | حية |
| `tg_suggestions` | infra | 1 | 0 | حية |
| `tg_tasks` | life | 4 | 1 | حية |
| `tips_engine` | ? | 1 | 0 | حية |
| `tool_cache` | ? | 1 | 0 | حية |
| `tool_registry` | ? | 1 | 0 | حية |
| `tool_summary` | ? | 1 | 0 | حية |
| `trading_brain` | trading | 6 | 3 | حية |
| `trading_decision_engine` | trading | 1 | 0 | حية |
| `trading_engine` | trading | 3 | 0 | حية |
| `tradingview_bridge` | trading | 3 | 2 | حية |
| `tv_advisor` | trading | 1 | 1 | حية |
| `tv_analysis` | trading | 4 | 0 | حية |
| `tv_data` | trading | 17 | 0 | حية |
| `world_state` | home/HA | 2 | 1 | حية |
| `world_state_delta` | home/HA | 4 | 0 | حية |

### الوحدات الميتة (0 مستورد)

- `benchmark_runner` — trading
- `brain_backfill` — llm
- `bridge_client_new` — trading
- `dropzone_watcher` — infra
- `entity_map_generator` — home/HA
- `gemini_scanner` — llm
- `habit_tracker` — life
- `master_ai_tool` — ?
- `memory_prefetch` — llm
- `proactive_engine` — ?
- `tg_logbook` — infra

---

## 0.4 — جدول استهلاك الـ endpoints (180 مسار حيّ)

| المسار | Method | منو يستهلكه | يحتاج مفتاح؟ | يغيّر حالة؟ |
|---|---|---|---|---|
| `/action/execute` | POST | server.py (server.py) | نعم | نعم |
| `/agent` | POST | server.py (server.py) | نعم | نعم |
| `/aliases` | GET | **لا أحد** | نعم | لا |
| `/anomalies` | GET | server.py (server.py) | نعم | لا |
| `/api/analyze` | GET | dashboard HTML (analysis.html, positions.html)<br>server.py (server.py) | **لا — تجاوز بادئة** | لا |
| `/api/analyze/refresh` | POST | dashboard HTML (analysis.html)<br>server.py (server.py) | **لا — تجاوز بادئة** | نعم |
| `/api/analyze/refresh-all` | POST | **لا أحد** | **لا — تجاوز بادئة** | نعم |
| `/api/brain/stats` | GET | dashboard HTML (system.html)<br>internal py (dashboard_api.py) | **لا — تجاوز بادئة** | لا |
| `/api/collect-now` | POST | internal py (dashboard_api.py) | **لا — تجاوز بادئة** | نعم |
| `/api/context-health` | GET | dashboard HTML (system.html)<br>internal py (dashboard_api.py) | **لا — تجاوز بادئة** | لا |
| `/api/data-freshness` | GET | internal py (dashboard_api.py) | **لا — تجاوز بادئة** | لا |
| `/api/data-health` | GET | internal py (dashboard_api.py) | **لا — تجاوز بادئة** | لا |
| `/api/decisions-now` | GET | dashboard HTML (decisions.html)<br>internal py (golden_engine.py) | **لا — تجاوز بادئة** | لا |
| `/api/flags` | GET | dashboard HTML (system.html)<br>server.py (server.py) | **لا — تجاوز بادئة** | لا |
| `/api/flags/{name}/toggle` | POST | dashboard HTML (system.html)<br>server.py (server.py) | **لا — تجاوز بادئة** | نعم |
| `/api/hooks/log` | GET | **لا أحد** | **لا — تجاوز بادئة** | لا |
| `/api/hooks/stats` | GET | **لا أحد** | **لا — تجاوز بادئة** | لا |
| `/api/intent-analytics` | GET | dashboard HTML (system.html)<br>internal py (dashboard_api.py) | **لا — تجاوز بادئة** | لا |
| `/api/kairos/log` | GET | **لا أحد** | **لا — تجاوز بادئة** | لا |
| `/api/kairos/status` | GET | dashboard HTML (system.html) | **لا — تجاوز بادئة** | لا |
| `/api/latency-stats` | GET | dashboard HTML (system.html)<br>internal py (dashboard_api.py) | **لا — تجاوز بادئة** | لا |
| `/api/memory-extraction/stats` | GET | dashboard HTML (system.html)<br>internal py (dashboard_api.py) | **لا — تجاوز بادئة** | لا |
| `/api/news` | GET | server.py (server.py) | **لا — تجاوز بادئة** | لا |
| `/api/news/refresh-boursa` | POST | **لا أحد** | **لا — تجاوز بادئة** | نعم |
| `/api/news/refresh-gemini` | POST | **لا أحد** | **لا — تجاوز بادئة** | نعم |
| `/api/paper-trade/close` | POST | internal py (dashboard_api.py) | **لا — تجاوز بادئة** | نعم |
| `/api/paper-trade/open` | POST | internal py (dashboard_api.py) | **لا — تجاوز بادئة** | نعم |
| `/api/portfolio-alert-ack` | POST | internal py (dashboard_api.py) | **لا — تجاوز بادئة** | نعم |
| `/api/portfolio-monitor` | POST | internal py (dashboard_api.py) | **لا — تجاوز بادئة** | نعم |
| `/api/portfolio-status` | GET | internal py (dashboard_api.py) | **لا — تجاوز بادئة** | لا |
| `/api/portfolio/add-more` | POST | dashboard HTML (positions.html) | **لا — تجاوز بادئة** | نعم |
| `/api/portfolio/partial-sell` | POST | dashboard HTML (positions.html) | **لا — تجاوز بادئة** | نعم |
| `/api/portfolio/transactions/{trade_id}` | GET | **لا أحد** | **لا — تجاوز بادئة** | لا |
| `/api/radar/progress` | GET | internal py (dashboard_api.py) | **لا — تجاوز بادئة** | لا |
| `/api/refresh-analysis` | POST | **لا أحد** | **لا — تجاوز بادئة** | نعم |
| `/api/review-now` | POST | **لا أحد** | **لا — تجاوز بادئة** | نعم |
| `/api/risk-config` | GET,POST | dashboard HTML (positions.html)<br>internal py (dashboard_api.py) | **لا — تجاوز بادئة** | نعم |
| `/api/service-health` | GET | dashboard HTML (system.html) | **لا — تجاوز بادئة** | لا |
| `/api/skills` | GET | internal py (dashboard_api.py) | **لا — تجاوز بادئة** | لا |
| `/api/stocks/profiles` | GET | dashboard HTML (personality.html) | **لا — تجاوز بادئة** | لا |
| `/api/stocks/symbol/{symbol}` | GET | dashboard HTML (personality.html, radar.html, signals.html) | **لا — تجاوز بادئة** | لا |
| `/api/symbols` | GET | dashboard HTML (positions.html)<br>internal py (dashboard_api.py) | **لا — تجاوز بادئة** | لا |
| `/api/tasks` | GET | dashboard HTML (system.html) | **لا — تجاوز بادئة** | لا |
| `/api/tools` | GET | server.py (server.py) | **لا — تجاوز بادئة** | لا |
| `/api/tools/{name}` | GET | server.py (server.py) | **لا — تجاوز بادئة** | لا |
| `/api/trade/close` | POST | dashboard HTML (positions.html)<br>internal py (dashboard_api.py) | **لا — تجاوز بادئة** | نعم |
| `/api/trade/open` | POST | dashboard HTML (positions.html)<br>internal py (dashboard_api.py) | **لا — تجاوز بادئة** | نعم |
| `/api/trade/update` | POST | dashboard HTML (positions.html)<br>internal py (dashboard_api.py) | **لا — تجاوز بادئة** | نعم |
| `/approvals/pending` | GET | **لا أحد** | نعم | لا |
| `/approve/{approval_id}` | POST | server.py (server.py) | نعم | نعم |
| `/ask` | POST | server.py (server.py)<br>internal py (benchmark_runner.py) | نعم | نعم |
| `/audit` | GET | internal py (dashboard_api.py, db_backup.py, degraded_mode.py…)<br>server.py (server.py) | نعم | لا |
| `/brain/analytics` | GET | **لا أحد** | نعم | لا |
| `/brain/diag` | GET | **لا أحد** | نعم | لا |
| `/brain/expertise` | GET | internal py (brain_core.py, chat_v7.py) | نعم | لا |
| `/brain/feedback` | POST | **لا أحد** | نعم | نعم |
| `/brain/stats` | GET | dashboard HTML (system.html)<br>internal py (chat_v7.py, dashboard_api.py) | نعم | لا |
| `/brain/users` | GET | **لا أحد** | نعم | لا |
| `/calendar/stats` | GET | **لا أحد** | نعم | لا |
| `/calendar/sync` | POST | **لا أحد** | نعم | نعم |
| `/chat/clear` | POST | internal py (benchmark_runner.py) | نعم | نعم |
| `/classify` | POST | **لا أحد** | نعم | نعم |
| `/claude` | GET | **لا أحد** | نعم | لا |
| `/corrections` | GET | server.py (server.py) | نعم | لا |
| `/corrections/decay` | POST | **لا أحد** | نعم | نعم |
| `/cost` | GET | internal py (cost_tracker.py, quick_query.py)<br>server.py (server.py) | نعم | لا |
| `/dashboard` | GET | dashboard HTML (analysis.html, assistant.html, brain.html…)<br>internal py (dashboard_api.py, priority_engine.py, trading_brain.py)<br>server.py (server.py) | لا — OPEN_PATHS | لا |
| `/dashboard/alerts` | GET | internal py (dashboard_api.py) | نعم | لا |
| `/dashboard/analysis` | GET | internal py (dashboard_api.py) | نعم | لا |
| `/dashboard/brain` | GET | dashboard HTML (brain.html)<br>internal py (dashboard_api.py, trading_brain.py)<br>server.py (server.py) | لا — OPEN_PATHS | لا |
| `/dashboard/brain-insights` | GET | dashboard HTML (brain.html)<br>internal py (dashboard_api.py) | لا — OPEN_PATHS | لا |
| `/dashboard/bridge` | GET | internal py (dashboard_api.py) | نعم | لا |
| `/dashboard/bridge/{symbol}` | GET | internal py (dashboard_api.py) | نعم | لا |
| `/dashboard/cmd` | POST | internal py (dashboard_api.py) | نعم | نعم |
| `/dashboard/confluence` | GET | internal py (dashboard_api.py) | نعم | لا |
| `/dashboard/ema-active` | GET | server.py (server.py) | لا — OPEN_PATHS | لا |
| `/dashboard/ema-crosses` | GET | server.py (server.py) | لا — OPEN_PATHS | لا |
| `/dashboard/ema-live` | GET | server.py (server.py) | لا — OPEN_PATHS | لا |
| `/dashboard/ema-proximity` | GET | server.py (server.py) | لا — OPEN_PATHS | لا |
| `/dashboard/equity` | GET | dashboard HTML (journal.html, swing.html)<br>internal py (dashboard_api.py) | لا — OPEN_PATHS | لا |
| `/dashboard/extended` | GET | dashboard HTML (assistant.html, calendar.html, email.html…)<br>internal py (dashboard_api.py, priority_engine.py) | لا — OPEN_PATHS | لا |
| `/dashboard/jobs` | GET | internal py (dashboard_api.py) | نعم | لا |
| `/dashboard/journal` | GET | dashboard HTML (journal.html)<br>internal py (dashboard_api.py) | لا — OPEN_PATHS | لا |
| `/dashboard/paper-trading` | GET | dashboard HTML (swing.html)<br>internal py (dashboard_api.py) | لا — OPEN_PATHS | لا |
| `/dashboard/portfolio` | GET | dashboard HTML (personality.html, positions.html)<br>internal py (dashboard_api.py) | لا — OPEN_PATHS | لا |
| `/dashboard/radar` | GET | dashboard HTML (personality.html, signals.html)<br>internal py (dashboard_api.py, priority_engine.py) | لا — OPEN_PATHS | لا |
| `/dashboard/regime` | GET | internal py (dashboard_api.py) | لا — OPEN_PATHS | لا |
| `/dashboard/reviews` | GET | dashboard HTML (reviews.html)<br>server.py (server.py) | لا — OPEN_PATHS | لا |
| `/dashboard/risk-status` | GET | dashboard HTML (positions.html, swing.html)<br>internal py (dashboard_api.py) | لا — OPEN_PATHS | لا |
| `/dashboard/scalper` | GET | dashboard HTML (scalper.html)<br>internal py (dashboard_api.py) | لا — OPEN_PATHS | لا |
| `/dashboard/signals` | GET | dashboard HTML (analysis.html, personality.html, radar.html…)<br>internal py (dashboard_api.py)<br>server.py (server.py) | لا — OPEN_PATHS | لا |
| `/dashboard/signals-30m` | GET | dashboard HTML (personality.html, signals.html)<br>internal py (dashboard_api.py) | لا — OPEN_PATHS | لا |
| `/dashboard/signals-daily` | GET | dashboard HTML (analysis.html, radar.html)<br>internal py (dashboard_api.py) | لا — OPEN_PATHS | لا |
| `/dashboard/strategies` | GET | dashboard HTML (strategies.html)<br>internal py (dashboard_api.py) | لا — OPEN_PATHS | لا |
| `/dashboard/swing` | GET | dashboard HTML (home.html, radar.html, swing.html)<br>internal py (dashboard_api.py) | لا — OPEN_PATHS | لا |
| `/debug/test_approval` | POST | **لا أحد** | نعم | نعم |
| `/decompose` | POST | **لا أحد** | نعم | نعم |
| `/deploy` | POST | server.py (server.py) | نعم | نعم |
| `/dev/context` | GET | server.py (server.py) | لا — OPEN_PATHS | لا |
| `/dream/run` | POST | **لا أحد** | نعم | نعم |
| `/dream/status` | GET | **لا أحد** | نعم | لا |
| `/entity-map/arabize` | POST | **لا أحد** | نعم | نعم |
| `/entity-map/health` | GET | **لا أحد** | نعم | لا |
| `/event` | POST | server.py (server.py)<br>internal py (plan_engine.py) | نعم | نعم |
| `/event_rules` | GET | **لا أحد** | نعم | لا |
| `/events` | GET | server.py (server.py) | نعم | لا |
| `/events/{event_id}` | GET | server.py (server.py) | نعم | لا |
| `/feedback/digest` | GET | **لا أحد** | نعم | لا |
| `/feedback/stats` | GET | **لا أحد** | نعم | لا |
| `/gmail/auth` | GET | server.py (server.py) | لا — OPEN_PATHS | لا |
| `/gmail/callback` | GET | server.py (server.py) | لا — OPEN_PATHS | لا |
| `/google/auth` | GET | internal py (calendar_engine.py, google_auth_ext.py)<br>Telegram (tg_email.py)<br>server.py (server.py) | لا — OPEN_PATHS | لا |
| `/google/auth/status` | GET | **لا أحد** | نعم | لا |
| `/google/callback` | GET | server.py (server.py)<br>internal py (google_auth_ext.py) | لا — OPEN_PATHS | لا |
| `/ha/service` | POST | server.py (server.py) | نعم | نعم |
| `/ha/states` | GET | server.py (server.py) | نعم | لا |
| `/ha/states/{entity_id}` | GET | server.py (server.py) | نعم | لا |
| `/health` | GET | internal py (bridge_client.py, bridge_client_new.py, chat_v7.py…)<br>server.py (server.py) | لا — OPEN_PATHS | لا |
| `/health/external` | GET | server.py (server.py) | نعم | لا |
| `/health/external/test` | POST | **لا أحد** | نعم | نعم |
| `/history/{entity_id}` | GET | internal py (brain_learning.py, ha_history.py)<br>server.py (server.py) | نعم | لا |
| `/knowledge` | GET,POST | server.py (server.py)<br>internal py (chat_v7.py) | نعم | نعم |
| `/knowledge/{kid}` | DELETE,GET,PUT | server.py (server.py)<br>internal py (chat_v7.py) | نعم | نعم |
| `/kpi` | GET | internal py (cost_tracker.py, domain_kpis.py)<br>server.py (server.py) | نعم | لا |
| `/memory` | GET,POST | dashboard HTML (system.html)<br>internal py (dashboard_api.py)<br>server.py (server.py) | نعم | نعم |
| `/memory/message` | POST | **لا أحد** | نعم | نعم |
| `/memory/recent` | GET | **لا أحد** | نعم | لا |
| `/memory/stats` | GET | **لا أحد** | نعم | لا |
| `/panel` | GET | server.py (server.py) | لا — OPEN_PATHS | لا |
| `/patterns` | GET | server.py (server.py) | نعم | لا |
| `/patterns/learn` | POST | server.py (server.py) | نعم | نعم |
| `/patterns/suggestions` | GET | **لا أحد** | نعم | لا |
| `/plugins` | GET | server.py (server.py) | نعم | لا |
| `/plugins/{name}/disable` | POST | server.py (server.py) | نعم | نعم |
| `/plugins/{name}/enable` | POST | server.py (server.py) | نعم | نعم |
| `/router/stats` | GET | **لا أحد** | نعم | لا |
| `/schema` | GET | server.py (server.py) | نعم | لا |
| `/schema/ensure` | POST | **لا أحد** | نعم | نعم |
| `/sessions` | GET,POST | server.py (server.py) | نعم | نعم |
| `/sessions/latest` | GET | **لا أحد** | نعم | لا |
| `/shift` | GET | internal py (smart_router.py)<br>server.py (server.py) | نعم | لا |
| `/ssh/run` | POST | server.py (server.py) | نعم | نعم |
| `/stability` | GET | **لا أحد** | نعم | لا |
| `/stats/capture` | POST | **لا أحد** | نعم | نعم |
| `/stats/daily` | GET | **لا أحد** | نعم | لا |
| `/stocks/alerts` | GET | **لا أحد** | نعم | لا |
| `/stocks/portfolio` | GET | **لا أحد** | نعم | لا |
| `/structured-memory` | GET | server.py (server.py) | نعم | لا |
| `/structured-memory/context` | GET | **لا أحد** | نعم | لا |
| `/structured-memory/correction` | POST | **لا أحد** | نعم | نعم |
| `/structured-memory/decay` | POST | **لا أحد** | نعم | نعم |
| `/structured-memory/event` | POST | **لا أحد** | نعم | نعم |
| `/structured-memory/fact` | POST | **لا أحد** | نعم | نعم |
| `/structured-memory/migrate` | POST | **لا أحد** | نعم | نعم |
| `/structured-memory/search` | GET | **لا أحد** | نعم | لا |
| `/structured-memory/seed` | POST | **لا أحد** | نعم | نعم |
| `/structured-memory/{memory_id}` | DELETE | server.py (server.py) | نعم | نعم |
| `/system/backup` | POST | **لا أحد** | نعم | نعم |
| `/system/context` | GET | server.py (server.py) | نعم | لا |
| `/system/diag` | GET | **لا أحد** | نعم | لا |
| `/system/knowledge` | GET | server.py (server.py)<br>internal py (chat_v7.py) | نعم | لا |
| `/system/knowledge/summary` | GET | **لا أحد** | نعم | لا |
| `/tasks` | GET | dashboard HTML (system.html)<br>Telegram (tg_tasks.py)<br>server.py (server.py) | نعم | لا |
| `/tasks/{task_id}` | GET | dashboard HTML (system.html)<br>Telegram (tg_tasks.py)<br>server.py (server.py) | نعم | لا |
| `/tg/stats` | GET | **لا أحد** | نعم | لا |
| `/tips` | GET | internal py (tips_engine.py) | نعم | لا |
| `/tool-stats` | GET | **لا أحد** | نعم | لا |
| `/traces` | GET | internal py (cost_tracker.py, db_backup.py, mini_planner.py)<br>server.py (server.py) | نعم | لا |
| `/traces/stats` | GET | **لا أحد** | نعم | لا |
| `/trading` | GET | dashboard HTML (assistant.html, calendar.html, email.html…)<br>internal py (tradingview_bridge.py)<br>server.py (server.py) | لا — OPEN_PATHS | لا |
| `/trading/{page}` | GET | dashboard HTML (assistant.html, calendar.html, email.html…)<br>internal py (tradingview_bridge.py)<br>server.py (server.py) | **لا — تجاوز بادئة** | لا |
| `/tradingview/webhook` | POST | internal py (tradingview_bridge.py)<br>server.py (server.py) | لا — OPEN_PATHS | نعم |
| `/users` | GET,POST | Telegram (tg_email.py)<br>server.py (server.py) | نعم | نعم |
| `/webhook/event` | POST | server.py (server.py) | **لا — تجاوز بادئة** | نعم |
| `/webhook/event/{token}` | POST | server.py (server.py) | **لا — تجاوز بادئة** | نعم |
| `/win/jobs` | GET | **لا أحد** | نعم | لا |
| `/win/poll` | GET | **لا أحد** | نعم | لا |
| `/win/register` | POST | **لا أحد** | نعم | نعم |
| `/win/report` | POST | **لا أحد** | نعم | نعم |
| `/world-state` | GET | internal py (world_state.py) | نعم | لا |