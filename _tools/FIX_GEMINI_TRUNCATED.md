# FIX: Gemini Truncated Reports — Missing structured data
# Date: 2026-04-07
# Priority: HIGH

## المشكلة
Gemini Flash يقطع التقرير قبل ما يكمل — الـ structured JSON (signal, confidence, targets) ما يوصل.
مثال: MANAZEL — report مقطوع، `structured: {}`, `signal: ""`, `confidence: 0`.

## السبب
`maxOutputTokens: 8192` + `thinkingBudget: -1` — الـ thinking tokens تاخذ حصة كبيرة من الـ 8192.

## الحل (Claude Code)

### Step 1: زيّد maxOutputTokens
**ملف:** `/home/pi/master_ai/stock_analyzer.py`

```python
"generationConfig": {
    "temperature": 0.4,
    "maxOutputTokens": 16384,  # was 8192
    "thinkingConfig": {"thinkingBudget": 2048},  # was -1 (unlimited)
},
```

### Step 2: أضف structured JSON كطلب منفصل (fallback)
إذا التقرير ما فيه structured JSON، أرسل طلب ثاني قصير:

بعد parsing الـ result، إذا `structured` فاضي:
```python
if not structured or not structured.get("signal"):
    # Short follow-up to extract signal
    followup_prompt = f"من التقرير التالي، استخرج JSON فقط:\n{report[:2000]}\n\nارجع JSON: {{signal, confidence, direction, entry, stop_loss, targets[], support[], resistance[], risk}}"
    # Call Gemini Flash with maxOutputTokens=1024
```

### Step 3: تحقق من parsing الـ structured JSON
الـ parser يمكن ما يلقى الـ JSON block لأنه مقطوع.
أضف fallback parser يستخرج ما يقدر من النص:
- ابحث عن "شراء" / "بيع" / "مراقبة" في النص
- ابحث عن أرقام بعد "دعم" / "مقاومة" / "هدف"

### التنفيذ:
```bash
cd /home/pi/master_ai
# عدّل stock_analyzer.py حسب الخطوات
python3 _tools/quick_check.py
git add -A && git commit -m "fix: increase Gemini tokens + fallback structured extraction"
bash _tools/restart_master_ai.sh

# اختبر
curl -s -X POST "http://localhost:9000/api/analyze/refresh?symbol=MANAZEL" | python3 -m json.tool | head -5
```
