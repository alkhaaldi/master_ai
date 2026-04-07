# WORKFLOW: Claude.ai + Claude Code — كيف نشتغل مع بعض

## القاعدة الذهبية
- **Claude.ai** = المخطط والمصمم (التخطيط، HTML/CSS، التحليل، النقاش)
- **Claude Code** = المنفذ على الـ RPi (Python، DB، git، restart، debugging)

---

## متى تستخدم Claude.ai (هنا)

### ✅ استخدمني لـ:
1. **تخطيط المهام** — "أبي أضيف feature جديد، شلون؟"
   - أكتب خطة كاملة بملف .md
   - أحدد الملفات والخطوات والترتيب
   
2. **تصميم HTML/CSS** — صفحات الداشبورد، الواجهات
   - أكتب HTML مباشرة عبر Samba
   - أصمم layouts، colors، responsive

3. **تحليل التداول** — Pine Script، Elliott Wave، بيانات السوق

4. **مراجعة وتدقيق** — "شيك على الكود"، "قارن بين خيارين"

5. **كتابة الخطط لـ Claude Code** — أكتب ملف .md بالتفاصيل

### ❌ لا تستخدمني لـ:
- تعديل Python files على RPi (بطيء جداً)
- إصلاح bugs في backend
- DB migrations
- أي شي يحتاج أوامر متكررة على RPi

---

## متى تستخدم Claude Code (على RPi)

### ✅ استخدمه لـ:
1. **أي تعديل Python** — server.py, stock_radar.py, etc.
2. **DB migrations** — ALTER TABLE, schema changes
3. **Git + Deploy** — commit, restart, testing
4. **Debugging** — قراءة logs, fix errors
5. **تنفيذ الخطط** — "اقرأ _tools/TASK.md ونفذ"

---

## طريقة العمل المثالية

### الخطوة 1: ناقشني (Claude.ai)
```
أنت: "أبي أضيف StochK و ADX للتحليل اليومي"
أنا: أكتب خطة كاملة → _tools/ADD_INDICATORS.md
```

### الخطوة 2: نفّذ مع Claude Code (على RPi)
```bash
ssh pi@192.168.109.123
cd /home/pi/master_ai
claude
> اقرأ _tools/ADD_INDICATORS.md ونفذ
```

### الخطوة 3: تحقق معي (Claude.ai)
```
أنت: "كمل، شيك على النتيجة" + screenshot
أنا: أتحقق بصرياً وأقترح تحسينات
```

---

## أسرع طريقة لتمرير المهام

بدل ما تشرح لـ Claude Code من الصفر، قلّي أنا وأنا أكتب ملف .md كامل فيه:
- المشكلة
- الملفات المعنية
- الخطوات بالترتيب
- أوامر التحقق

وبعدها تقول لـ Claude Code: "اقرأ _tools/TASK_NAME.md ونفذ"

---

## ملاحظة مهمة
Claude Code عنده CLAUDE.md في المشروع فيه كل السياق.
أنا عندي الميموري + userPreferences فيه كل السياق.
ما تحتاج تشرح المعمارية لأي واحد فينا — كلنا نعرفها.
