# ربط التيليقرام بالتحديثات الجديدة — خطة شاملة
# التاريخ: 2026-03-30
# المنفذ: Claude Code

## الحالة الحالية — شنو موجود وشنو ناقص

### ✅ موجود ويشتغل:
- `/report` — تقرير صباحي (طقس + وردية + بيت + أسهم + برين)
- `/stocks` — المحفظة
- `/radar` — إشارات الرادار
- `/brain` — حالة العقل
- `/trade` — سجل صفقة
- `/trades` — قائمة الصفقات
- `/trade_review` — مراجعة صفقة
- تنبيهات الرادار (EMA crossover) — كل 90 ثانية ✅

### ❌ ناقص — لازم يضاف:

#### 1. أمر `/فرص` أو `/decisions` — الفرص الذهبية الحالية
```python
# أضف في server.py بعد سطر /stocks (~5735):

    if cmd == "/فرص" or cmd == "/decisions":
        try:
            from golden_engine import scan_opportunities
            result = scan_opportunities()
            opps = result.get("all_opportunities", [])
            enters = [o for o in opps if o.get("smart_decision") == "ENTER"]
            if not enters:
                return "⚪ لا توجد فرص ادخل حالياً"
            lines = [f"🟢 <b>{len(enters)} فرصة ادخل الآن</b>\n"]
            for o in enters[:5]:
                cp = o.get("chosen_plan", {})
                lines.append(
                    f"<b>{o['symbol']}</b> — {o.get('price',0)}\n"
                    f"  🎯 دخول: {cp.get('entry','-')} | هدف: {cp.get('target1','-')} | ستوب: {cp.get('stop','-')}\n"
                    f"  📊 R/R: {cp.get('rr',0):.1f}x | ثقة: {o.get('confidence',0):.0f}%\n"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"❌ خطأ: {e}"
```

#### 2. أمر `/تقييم` أو `/review` — تقييم إشارات أمس
```python
    if cmd == "/تقييم" or cmd == "/review":
        try:
            from signal_review import get_reviews_for_dashboard
            d = get_reviews_for_dashboard()
            if not d.get("reviews"):
                return "⚪ لا توجد تقييمات بعد"
            res = d.get("results", {})
            lines = [
                f"📊 <b>تقييم إشارات {d['date']}</b>\n",
                f"✅ نجاح: {res.get('success',0)} | ⚠️ جزئي: {res.get('partial',0)} | ❌ فشل: {res.get('fail',0)} | ⏳ مستمر: {res.get('ongoing',0)}",
                f"📈 نسبة النجاح: {d.get('success_rate',0)}%\n",
            ]
            for r in d["reviews"]:
                if r["result"] in ("no_data", "pending"):
                    continue
                emoji = {"success":"✅","partial":"⚠️","fail":"❌","ongoing":"⏳"}.get(r["result"],"❓")
                pnl = r.get("pnl_pct")
                pnl_str = f"{pnl:+.1f}%" if pnl is not None else "--"
                lines.append(f"{emoji} <b>{r['symbol']}</b> {pnl_str} — {r.get('reason_ar','')}")
                if r.get("lesson_ar"):
                    lines.append(f"   💡 {r['lesson_ar']}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ خطأ: {e}"
```

#### 3. التقرير الصباحي — إضافة ملخص تقييم أمس
في `tg_morning_report.py`، أضف section جديد بعد الأسهم:

```python
async def _get_review_summary():
    """Yesterday's signal review summary for morning report."""
    try:
        from signal_review import get_reviews_for_dashboard
        d = get_reviews_for_dashboard()
        if not d or not d.get("reviews"):
            return None
        res = d.get("results", {})
        real = [r for r in d["reviews"] if r["result"] not in ("no_data", "pending")]
        if not real:
            return None
        succ = res.get("success", 0)
        part = res.get("partial", 0)
        fail = res.get("fail", 0)
        ong = res.get("ongoing", 0)
        total = len(real)
        rate = round(succ / total * 100) if total > 0 else 0
        line = f"📊 تقييم أمس ({d['date']}): ✅{succ} ⚠️{part} ❌{fail} ⏳{ong} — نجاح {rate}%"
        best = d.get("best")
        if best:
            line += f"\n   🏆 أفضل: {best['symbol']} +{best['pnl']}%"
        return line
    except Exception:
        return None
```

ثم في `build_morning_report()` بعد stocks section:
```python
    # Signal review summary
    review_sum = await _get_review_summary()
    if review_sum:
        report += f"\n\n{review_sum}"
```

#### 4. أمر `/help` — تحديث قائمة الأوامر
أضف الأوامر الجديدة لقائمة الـ help.

## بعد التنفيذ:
```bash
python3 _tools/quick_check.py
sudo systemctl restart master-ai

# اختبار:
# أرسل /فرص في تيليقرام
# أرسل /تقييم في تيليقرام
# أرسل /report في تيليقرام (لازم يطلع ملخص التقييم)
```
