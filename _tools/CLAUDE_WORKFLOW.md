# WORKFLOW: Claude.ai + Claude Code — قواعد التعاون

## القاعدة الذهبية
- **Claude.ai** = المهندس المعماري (يخطط، يصمم، يراجع)
- **Claude Code** = المقاول (ينفذ، يعدّل، يختبر على الـ RPi)

---

## متى تستخدم Claude.ai (هذا الشات)

### ✅ استخدمه لـ:
- تخطيط مهمة كبيرة وكتابة خطة تنفيذ (ملف .md)
- تصميم HTML/CSS (صفحات الداشبورد)
- تحليل تداول / Pine Script / بيانات بورصة
- كتابة YAML لـ Home Assistant
- مراجعة كود ومناقشة architecture
- كتابة ملفات على Samba مباشرة (HTML, YAML, config)
- بحث الويب وأي شي يحتاج تفكير

### ❌ لا تستخدمه لـ:
- تعديل ملفات Python على RPi (بطيء + SSH معقد)
- تشغيل أوامر على RPi (git, pip, restart)
- إصلاح bugs في backend
- DB migrations

---

## متى تستخدم Claude Code (على الـ RPi)

### ✅ استخدمه لـ:
- أي تعديل Python (server.py, stock_radar.py, إلخ)
- تشغيل أوامر (git, pip, restart, tests)
- إصلاح bugs وديباقينق
- DB schema changes
- أي شي يحتاج access مباشر لملفات RPi

### ❌ لا تستخدمه لـ:
- تصميم HTML طويل (ما يشوف النتيجة بصرياً)
- تخطيط كبير يحتاج نقاش
- بحث ويب

---

## الـ Workflow المثالي

### لمهمة جديدة:
1. **تجي لـ Claude.ai** وتقول شنو تبي
2. **Claude.ai يكتب خطة** في ملف `_tools/TASK_NAME.md`
3. **تروح لـ Claude Code** وتقوله: `اقرأ _tools/TASK_NAME.md ونفذ`
4. **Claude Code ينفذ** ويسوي commit
5. **ترجع لـ Claude.ai** للمراجعة أو المهمة اللي بعدها

### لمهمة HTML/Dashboard:
1. **Claude.ai يبني** الصفحات HTML ويكتبها على Samba
2. **Claude Code يسوي** git add + commit + restart

### لمهمة تحليل تداول:
1. **Claude.ai يحلل** الشارت ويعطي توصيات
2. لو يحتاج تعديل backend → يكتب خطة → **Claude Code ينفذ**

---

## كيف تمرر السياق بينهم

### من Claude.ai → Claude Code:
- اكتب الخطة في `_tools/` كملف .md
- Claude Code يقرأها وينفذ
- لا تحتاج تنسخ شات طويل

### من Claude Code → Claude.ai:
- Claude Code يسوي commit message واضح
- أنت تقول لـ Claude.ai: "Claude Code سوّى commit X، كمّل"
- أو انسخ summary من Claude Code

---

## مثال عملي

**أنت:** "أبي صفحة portfolio جديدة في الداشبورد"

**Claude.ai:**
1. يصمم HTML كامل
2. يكتبه على Samba
3. يكتب `_tools/ADD_PORTFOLIO_PAGE.md` فيه:
   - أي endpoint يحتاج
   - أي تعديل backend
   - خطوات الاختبار

**أنت تروح Claude Code:** "اقرأ _tools/ADD_PORTFOLIO_PAGE.md ونفذ"

**Claude Code:** ينفذ backend + git + restart

**النتيجة:** 10 دقايق بدل ساعة
