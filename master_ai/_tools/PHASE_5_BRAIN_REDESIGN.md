# Phase 5: إعادة بناء صفحة العقل — من بيانات خام إلى اكتشافات
# التاريخ: 2026-03-29
# المنفذ: Claude Code (endpoint) + Claude.ai (HTML)

---

## الهدف
صفحة العقل الحالية تعرض بيانات خام مكررة (10 تقييمات لسهم واحد).
المطلوب: صفحة تعرض **اكتشافات النظام** — شنو تعلّم، شنو ينفع، شنو فاشل.

---

## الخطوة 1: Claude Code — أنشئ endpoint جديد

### Endpoint: `GET /dashboard/brain-insights`

### يرجع JSON فيه 5 أقسام:

```python
@app.get("/dashboard/brain-insights")
async def brain_insights():
    db = get_db("life.db")
    
    result = {
        "key_learnings": build_key_learnings(db),
        "edge_map": build_edge_map(db),
        "top_strategies": build_top_strategies(db),
        "decision_scorecard": build_decision_scorecard(db),
        "action_panel": build_action_panel(db),
    }
    return result
```

---

### القسم 1: `key_learnings` — أهم الاكتشافات

```python
def build_key_learnings(db):
    """4 بطاقات: أفضل فريم، أقوى نمط، أقوى مؤشر، أفضل بيئة"""
    
    # 1. مقارنة الفريمات
    timeframe_stats = db.execute("""
        SELECT 
            timeframe,
            COUNT(*) as samples,
            ROUND(100.0 * SUM(CASE WHEN outcome='hit' THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
            ROUND(AVG(CASE WHEN outcome='hit' THEN max_gain_pct ELSE -max_loss_pct END), 2) as avg_return
        FROM signal_snapshots
        WHERE outcome IN ('hit','miss')
        GROUP BY timeframe
        ORDER BY avg_return DESC
    """).fetchall()
    
    # 2. أقوى نمط (من mined_strategies)
    top_pattern = db.execute("""
        SELECT 
            pattern_atoms,
            pattern_label,
            timeframe,
            regime,
            ROUND(win_rate * 100, 1) as win_pct,
            ROUND(ev, 2) as ev,
            sample_size,
            ROUND(profit_factor, 2) as pf
        FROM mined_strategies
        WHERE sample_size >= 30
        ORDER BY ev DESC
        LIMIT 1
    """).fetchone()
    
    # 3. أقوى مؤشر (من brain_weights)
    best_indicator = db.execute("""
        SELECT indicator_name, ROUND(accuracy * 100, 1) as accuracy_pct
        FROM brain_weights
        ORDER BY accuracy DESC
        LIMIT 1
    """).fetchone()
    
    # 4. أفضل بيئة (من signal_outcomes)
    best_context = db.execute("""
        SELECT 
            regime_calc as regime,
            regime_dir as direction,
            COUNT(*) as samples,
            ROUND(100.0 * SUM(CASE WHEN outcome_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
            ROUND(AVG(outcome_pct), 2) as avg_return
        FROM signal_outcomes
        WHERE regime_calc IS NOT NULL
        GROUP BY regime_calc, regime_dir
        HAVING COUNT(*) >= 50
        ORDER BY avg_return DESC
        LIMIT 1
    """).fetchone()
    
    return {
        "timeframe_comparison": [dict(r) for r in timeframe_stats],
        "top_pattern": dict(top_pattern) if top_pattern else None,
        "best_indicator": dict(best_indicator) if best_indicator else None,
        "best_context": dict(best_context) if best_context else None,
    }
```

---

### القسم 2: `edge_map` — وين الفرصة الحقيقية

```python
def build_edge_map(db):
    """خريطة الأداء: فريم × نظام السوق × الاتجاه"""
    
    # أداء كل فريم
    by_timeframe = db.execute("""
        SELECT 
            s.timeframe,
            COUNT(*) as samples,
            ROUND(100.0 * SUM(CASE WHEN o.outcome_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
            ROUND(AVG(o.outcome_pct), 2) as avg_return
        FROM signal_outcomes o
        JOIN signal_snapshots s ON s.id = o.signal_id
        GROUP BY s.timeframe
    """).fetchall()
    
    # أفضل 5 بيئات
    top_contexts = db.execute("""
        SELECT 
            s.timeframe,
            o.regime_calc as regime,
            o.regime_dir as direction,
            COUNT(*) as samples,
            ROUND(100.0 * SUM(CASE WHEN o.outcome_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
            ROUND(AVG(o.outcome_pct), 2) as avg_return
        FROM signal_outcomes o
        JOIN signal_snapshots s ON s.id = o.signal_id
        WHERE o.regime_calc IS NOT NULL
        GROUP BY s.timeframe, o.regime_calc, o.regime_dir
        HAVING COUNT(*) >= 30
        ORDER BY avg_return DESC
        LIMIT 5
    """).fetchall()
    
    # أسوأ 5 بيئات
    worst_contexts = db.execute("""
        SELECT 
            s.timeframe,
            o.regime_calc as regime,
            o.regime_dir as direction,
            COUNT(*) as samples,
            ROUND(100.0 * SUM(CASE WHEN o.outcome_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
            ROUND(AVG(o.outcome_pct), 2) as avg_return
        FROM signal_outcomes o
        JOIN signal_snapshots s ON s.id = o.signal_id
        WHERE o.regime_calc IS NOT NULL
        GROUP BY s.timeframe, o.regime_calc, o.regime_dir
        HAVING COUNT(*) >= 30
        ORDER BY avg_return ASC
        LIMIT 5
    """).fetchall()
    
    return {
        "by_timeframe": [dict(r) for r in by_timeframe],
        "top_contexts": [dict(r) for r in top_contexts],
        "worst_contexts": [dict(r) for r in worst_contexts],
    }
```

---

### القسم 3: `top_strategies` — شنو ينفع وشنو فاشل

```python
def build_top_strategies(db):
    """أفضل وأسوأ 5 استراتيجيات + أفضل وأسوأ atoms"""
    
    # أفضل 5 استراتيجيات
    best = db.execute("""
        SELECT 
            strategy_id, pattern_label, timeframe, regime,
            sample_size as samples,
            ROUND(win_rate * 100, 1) as win_pct,
            ROUND(ev, 2) as ev,
            ROUND(profit_factor, 2) as pf,
            ROUND(walk_forward_stability, 2) as stability
        FROM mined_strategies
        WHERE sample_size >= 30
        ORDER BY ev DESC
        LIMIT 5
    """).fetchall()
    
    # أسوأ 5 (أقل EV من الـ validated)
    worst = db.execute("""
        SELECT 
            strategy_id, pattern_label, timeframe, regime,
            sample_size as samples,
            ROUND(win_rate * 100, 1) as win_pct,
            ROUND(ev, 2) as ev,
            ROUND(profit_factor, 2) as pf,
            ROUND(walk_forward_stability, 2) as stability
        FROM mined_strategies
        WHERE sample_size >= 30
        ORDER BY ev ASC
        LIMIT 5
    """).fetchall()
    
    # أفضل atoms (من signal_outcomes — atoms stored as comma-separated)
    # ملاحظة: إذا الـ atoms مخزنة كـ TEXT مفصول بفواصل، نحتاج split
    # الحل: نعمل query على الأنماط الأكثر تكراراً في الاستراتيجيات الناجحة
    helpful_atoms = db.execute("""
        SELECT pattern_atoms, COUNT(*) as strategy_count,
            ROUND(AVG(ev), 2) as avg_ev,
            ROUND(AVG(win_rate) * 100, 1) as avg_win_pct
        FROM mined_strategies
        WHERE ev > 3 AND sample_size >= 30
        GROUP BY pattern_atoms
        ORDER BY avg_ev DESC
        LIMIT 10
    """).fetchall()
    
    return {
        "best_5": [dict(r) for r in best],
        "worst_5": [dict(r) for r in worst],
        "helpful_patterns": [dict(r) for r in helpful_atoms],
    }
```

---

### القسم 4: `decision_scorecard` — أداء محرك القرارات

```python
def build_decision_scorecard(db):
    """أداء القرارات المسجّلة في decision_audit"""
    
    # إجمالي القرارات
    total = db.execute("""
        SELECT 
            smart_decision,
            COUNT(*) as count
        FROM decision_audit
        GROUP BY smart_decision
    """).fetchall()
    
    # أداء حسب مستوى الثقة (إذا في نتائج)
    by_confidence = db.execute("""
        SELECT 
            CASE 
                WHEN confidence >= 90 THEN '90+'
                WHEN confidence >= 80 THEN '80-89'
                WHEN confidence >= 70 THEN '70-79'
                ELSE '<70'
            END as bucket,
            COUNT(*) as count,
            ROUND(AVG(confidence), 1) as avg_conf,
            ROUND(AVG(data_quality), 1) as avg_quality
        FROM decision_audit
        WHERE smart_decision = 'ENTER'
        GROUP BY bucket
        ORDER BY bucket DESC
    """).fetchall()
    
    # أداء حسب جودة البيانات
    by_quality = db.execute("""
        SELECT 
            CASE 
                WHEN data_quality >= 80 THEN 'عالية'
                WHEN data_quality >= 60 THEN 'متوسطة'
                ELSE 'ضعيفة'
            END as quality_ar,
            COUNT(*) as count,
            ROUND(AVG(rr_ratio), 2) as avg_rr
        FROM decision_audit
        WHERE smart_decision = 'ENTER'
        GROUP BY quality_ar
    """).fetchall()
    
    # أكثر الاستراتيجيات استخداماً
    top_used = db.execute("""
        SELECT 
            strategy_id,
            COUNT(*) as used_count,
            ROUND(AVG(rr_ratio), 2) as avg_rr,
            ROUND(AVG(confidence), 1) as avg_conf
        FROM decision_audit
        WHERE smart_decision = 'ENTER' AND strategy_id IS NOT NULL
        GROUP BY strategy_id
        ORDER BY used_count DESC
        LIMIT 5
    """).fetchall()
    
    return {
        "total_by_decision": [dict(r) for r in total],
        "enter_by_confidence": [dict(r) for r in by_confidence],
        "enter_by_quality": [dict(r) for r in by_quality],
        "top_used_strategies": [dict(r) for r in top_used],
    }
```

---

### القسم 5: `action_panel` — خلاصة عملية

```python
def build_action_panel(db):
    """3 قوائم: زِد من / تجنّب / راقب"""
    
    # أفضل بيئة (زِد من)
    do_more = db.execute("""
        SELECT s.timeframe, o.regime_calc, o.regime_dir,
            COUNT(*) as samples,
            ROUND(AVG(o.outcome_pct), 2) as avg_return
        FROM signal_outcomes o
        JOIN signal_snapshots s ON s.id = o.signal_id
        WHERE o.regime_calc IS NOT NULL
        GROUP BY s.timeframe, o.regime_calc, o.regime_dir
        HAVING COUNT(*) >= 50 AND AVG(o.outcome_pct) > 2
        ORDER BY avg_return DESC
        LIMIT 3
    """).fetchall()
    
    # أسوأ بيئة (تجنّب)
    avoid = db.execute("""
        SELECT s.timeframe, o.regime_calc, o.regime_dir,
            COUNT(*) as samples,
            ROUND(AVG(o.outcome_pct), 2) as avg_return
        FROM signal_outcomes o
        JOIN signal_snapshots s ON s.id = o.signal_id
        WHERE o.regime_calc IS NOT NULL
        GROUP BY s.timeframe, o.regime_calc, o.regime_dir
        HAVING COUNT(*) >= 50 AND AVG(o.outcome_pct) < 0
        ORDER BY avg_return ASC
        LIMIT 3
    """).fetchall()
    
    # إحصائيات عامة
    stats = db.execute("""
        SELECT 
            (SELECT COUNT(*) FROM mined_strategies) as total_strategies,
            (SELECT COUNT(*) FROM signal_outcomes) as total_signals,
            (SELECT COUNT(*) FROM decision_audit) as total_decisions,
            (SELECT COUNT(*) FROM decision_audit WHERE smart_decision='ENTER') as total_enters
    """).fetchone()
    
    return {
        "do_more": [dict(r) for r in do_more],
        "avoid": [dict(r) for r in avoid],
        "system_stats": dict(stats) if stats else {},
    }
```

---

## الخطوة 2: أضف الـ endpoint لـ OPEN_PATHS

```python
# في server.py — أضف للمسارات المفتوحة
OPEN_PATHS.add("/dashboard/brain-insights")
```

---

## ترتيب التنفيذ:

1. أضف كل الـ functions أعلاه في `server.py` (أو ملف جديد `brain_insights.py` إذا يفضّل)
2. أضف الـ endpoint
3. أضف للـ OPEN_PATHS
4. `quick_check.py` → `restart` → اختبر بـ `curl http://localhost:9000/dashboard/brain-insights | python3 -m json.tool | head -100`
5. `git commit -m "feat: brain insights endpoint — 5 sections of trading learnings"`

## ملاحظات مهمة:
- الـ queries تعتمد على الأعمدة الموجودة فعلاً. إذا أي عمود غير موجود (مثل pattern_label)، استخدم pattern_atoms بدل.
- إذا signal_outcomes ما فيها regime_calc، استخدم regime بدل.
- إذا decision_audit فاضي (جديد)، ارجع {} فاضي مع رسالة "لا توجد بيانات بعد"
- لا تكسر أي endpoint حالي
