# Signal Legend (Key) — Claude Code Task
# Date: 2026-03-27
# Priority: LOW
# Scope: Add indicator legend/key below the signal matrix table in signals.html

## TASK
Add a visual legend/key section below the signal matrix table in signals.html
that explains what each indicator and badge means.

## DESIGN
The legend should match the existing navy+gold theme and be organized in a clean grid.
Use the same badge/pill styles already in the page so the legend is self-referencing.

## CONTENT (Arabic, RTL)

### Section title: "دليل المؤشرات"

### Grid layout — 2 or 3 columns, each item shows the indicator name + meaning:

**Confluence (0-100):**
- 🟢 71+ = إشارات قوية متفقة على الصعود
- 🟡 50-70 = أغلب المؤشرات إيجابية
- 🟠 40-49 = محايد / متضارب
- 🔴 أقل من 40 = أغلب المؤشرات سلبية

**الحالة (Trade State):**
- تحضير (setup) = المؤشرات تتحسن، قبل نقطة الدخول
- إدارة (manage) = مركز مفتوح قيد المتابعة
- استكشاف (discovery) = الرادار اكتشفه مبكراً

**القرار (Verdict):**
- مراقبة = راقب بدون دخول
- مراجعة = راجع مركزك
- تجنب = لا تدخل

**EMA (المتوسطات المتحركة):**
- ▲ صاعد = السعر فوق المتوسطات (ترند صاعد)
- ▼ هابط = السعر تحت المتوسطات

**RSI (مؤشر القوة النسبية 0-100):**
- فوق 70 = overbought — احتمال تصحيح
- 30-70 = منطقة طبيعية
- تحت 30 = oversold — احتمال ارتداد

**StochK (Stochastic):**
- فوق 80 = overbought
- تحت 20 = oversold

**Momentum (زخم MACD):**
- ▲▲ تسارع = زخم صاعد يزيد (أقوى شراء)
- ▲ تباطؤ = صاعد يضعف (حذر)
- ▼▼ تسارع = زخم هابط يزيد (أقوى بيع)
- ▼ تباطؤ = هابط يخف (ممكن ارتداد)

**ADX (قوة الترند):**
- فوق 25 = ترند واضح
- تحت 20 = السوق sideways

**Vol (نسبة الحجم):**
- فوق 1.5x = حجم عالي يدعم الحركة
- تحت 0.5x = حجم ضعيف (حركة مشكوك فيها)

**BB Sq (Bollinger Squeeze):**
- ⬤ = ضغط — حركة قوية قريبة
- — = لا ضغط

**RSI Div (RSI Divergence):**
- ▲ أخضر = divergence صاعد (إشارة ارتداد)
- ▼ أحمر = divergence هابط (إشارة تصحيح)

**EMA Cross:**
- رقم ★ أخضر = Golden Cross قبل N بار (إيجابي)

**الدعم / المقاومة:**
- الدعم = مستوى الارتداد المتوقع
- المقاومة = مستوى المقاومة المتوقع

**ATR (متوسط المدى):**
- كم يتحرك السهم يومياً — يفيد لوقف الخسارة (وقف = دخول - 2×ATR)

## PLACEMENT
Add AFTER the signal matrix table, BEFORE the nav bar.
Wrap in a collapsible section — starts collapsed with a toggle button "دليل المؤشرات ▼"
When clicked, expands to show the full legend.

## STYLING
- Same card background as other cards (navy-800 + card-border)
- Grid: 2 columns on desktop, 1 column on mobile
- Each item: indicator name in gold, description in text-2
- Use the actual CSS classes for badges (e.g., show real .ema-b span for "▲ صاعد")
- Border-radius: 10px, padding: 16px

## FILE TO EDIT
- /home/pi/master_ai/www/trading/signals.html

## AFTER
- git commit -m "feat: add indicator legend to signals page"
