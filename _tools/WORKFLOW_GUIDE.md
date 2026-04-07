# Workflow: Claude.ai + Claude Code — دليل التعاون

## القاعدة الذهبية
**Claude.ai يخطط ويصمم → Claude Code ينفذ على RPi**

---

## متى تستخدم Claude.ai (هنا)

### ✅ أستخدمه لـ:
- **تخطيط المهام** — كتابة خطة تنفيذ كاملة (مثل FULL_MIGRATION.md)
- **تصميم HTML/CSS** — بناء صفحات الداشبورد والواجهات
- **تحليل التداول** — Pine Script، مراجعة أسهم، خطط تداول
- **مناقشة القرارات** — "هل أدمج الصفحتين؟"، "شنو أفضل architecture؟"
- **كتابة YAML** — HA automations, configuration
- **بحث ومعلومات** — web search, أخبار, مقارنات
- **مراجعة كود** — "شيك على هالملف وقلي المشاكل"
- **كتابة ملفات PC** — أي شي على Windows (Samba, Temp, scripts)

### ❌ لا أستخدمه لـ:
- تعديل Python على RPi (بطيء، SSH escaping مزعج)
- تشغيل أوامر طويلة على RPi
- إصلاح bugs بالـ backend
- DB migrations

---

## متى تستخدم Claude Code (على RPi)

### ✅ أستخدمه لـ:
- **تعديل Python** — server.py, stock_radar.py, أي ملف backend
- **إصلاح bugs** — يشوف الـ error ويصلحه فوراً
- **DB operations** — ALTER TABLE, migrations, queries
- **Git operations** — commit, push, log
- **تشغيل أوامر** — restart, pip install, quick_check
- **Testing** — smoke_test, db_sanity

### ❌ لا أستخدمه لـ:
- تخطيط طويل ونقاش
- بحث على الإنترنت
- تحليل تداول معقد
- تصميم UI (ما يشوف النتيجة)

---

## طريقة العمل المثالية

### 1. ابدأ هنا (Claude.ai)
اشرح المهمة → أنا أكتب خطة كاملة → أحفظها كملف .md

### 2. انقل لـ Claude Code
```bash
ssh pi@192.168.109.123
cd /home/pi/master_ai
claude
> اقرأ _tools/[TASK_NAME].md ونفذ
```

### 3. ارجع هنا للمراجعة
"Claude Code خلص المهمة — شيك النتيجة"
أنا أفتح الصفحة بالـ Chrome وأتحقق بصرياً

---

## مثال عملي

**أنت:** "أبي صفحة جديدة للمحفظة"

**Claude.ai (هنا):**
1. أصمم الصفحة (HTML/CSS)
2. أكتب خطة التنفيذ
3. أحفظ: `_tools/BUILD_PORTFOLIO_PAGE.md`

**أنت → Claude Code:**
```
اقرأ _tools/BUILD_PORTFOLIO_PAGE.md
- أضف endpoint في dashboard_api.py
- أضف route في panel.py
- عدّل DB schema
- quick_check + smoke_test + git commit + restart
```

**أنت → Claude.ai:**
"خلص — شيك الصفحة"
→ أفتحها بالـ Chrome وأتحقق

---

## ملخص بسطر واحد
**أنا = المهندس المعماري 🏗️ | Claude Code = المقاول المنفذ 🔧**
