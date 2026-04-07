# WORKFLOW: Claude.ai + Claude Code — قواعد التنسيق

## المبدأ الأساسي
- **Claude.ai** = المخطط والمصمم (HTML/CSS, خطط, تحليل, بحث, مناقشة)
- **Claude Code** = المنفّذ على الـ RPi (Python, DB, git, restart, testing)

## متى تستخدم Claude.ai
- تخطيط مهام جديدة وكتابة خطط (مثل FULL_MIGRATION.md)
- بناء صفحات HTML/CSS/JS (يكتبها ويدفعها عبر Samba)
- تحليل تداول وبيانات السوق
- مراجعة كود واقتراح حلول
- كتابة Pine Script
- أي شي يحتاج نقاش أو قرار أو تصميم

## متى تستخدم Claude Code
- أي تعديل Python على الـ RPi
- إصلاح bugs في backend
- DB migrations / ALTER TABLE
- git commit + restart + testing
- تثبيت packages (pip install)
- أي شي يحتاج SSH أو terminal مباشر

## طريقة التنسيق (مهم)

### إذا Claude.ai يحتاج شغل backend:
1. يكتب ملف خطة في `_tools/` (مثل FIX_SOMETHING.md)
2. يقول لك: "شغّل Claude Code وقله: اقرأ _tools/FIX_SOMETHING.md ونفذ"
3. Claude Code ينفّذ ويبلّغك بالنتيجة

### إذا Claude Code يحتاج HTML/تصميم:
1. يكتب spec في `_tools/` يوصّف المطلوب
2. ترجع لـ Claude.ai وتقله: "اقرأ _tools/SPEC.md ونفذ"

### القاعدة الذهبية:
**لا تخلي Claude.ai يعدّل Python عبر SSH/Samba**
**لا تخلي Claude Code يبني HTML من الصفر (مو تخصصه)**

## ملفات التنسيق
كل خطة تتحط في: `_tools/` بأسماء واضحة:
- `_tools/FIX_*.md` — إصلاحات
- `_tools/FEAT_*.md` — ميزات جديدة
- `_tools/MIGRATION_*.md` — تحويلات كبيرة

## CLAUDE.md Reference
Claude Code يقرأ `/home/pi/master_ai/CLAUDE.md` تلقائياً.
أي تعليمات دائمة لازم تكون هناك.
