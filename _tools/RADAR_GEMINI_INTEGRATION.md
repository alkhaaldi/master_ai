# RADAR_GEMINI_INTEGRATION.md
# ربط تحليل Gemini + التحديثات الأخيرة بصفحة الرادار
# التاريخ: 2026-04-04

## الهدف
صفحة الرادار (`radar.html`) حالياً تعتمد على `signal_engine.build_signals()` فقط.
التحديثات الأخيرة بنت قدرات جديدة (Gemini deep analysis, partial sell/add more, risk config)
لكن ما ربطتها بالرادار. هذي الخطة تربطها.

---

## المهمة: تعديل endpoint `/dashboard/signals-daily` في `dashboard_api.py`

### ما نريده:
الـ endpoint يرجع بيانات إضافية مع كل signal:

```python
# لكل signal في all_signals:
sig["gemini"] = {
    "signal": "شراء قريب من دعم",    # من stock_analysis_cache.signal
    "confidence": 65,                   # من stock_analysis_cache.confidence
    "direction": "صاعد مع حذر",       # من structured_json.direction
    "targets": ["94.7", "96.0"],       # من structured_json.targets
    "stop_loss": "84.9",              # من structured_json.stop_loss
    "analysis_date": "2026-04-04",    # عمر التحليل
    "stale": false,                    # true إذا أقدم من 3 أيام
}

# أو null إذا ما فيه تحليل:
sig["gemini"] = null

# وأيضاً conflict detection:
sig["gemini_conflict"] = true/false  
# true إذا الرادار يقول شراء وGemini يقول بيع/انتظار أو العكس
```

### الخطوات (Claude Code):

#### الخطوة 1: تعديل `dashboard_api.py` — دالة `dashboard_signals_daily()`

**بعد** السطر الحالي:
```python
data["timeframe"] = "1D"
data["price_note"] = "Prices are daily closing prices from DB, not live 30m."
```

**أضف:**
```python
# ═══ Gemini Analysis Overlay ═══
try:
    from stock_analyzer import get_all_cached_analyses
    _analyses = {}
    for a in get_all_cached_analyses():
        _analyses[a["symbol"]] = a
    
    for sig in data.get("all_signals", []):
        sym = sig.get("symbol", "")
        ga = _analyses.get(sym)
        if ga and ga.get("structured_json"):
            sj = ga["structured_json"]
            a_date = ga.get("analysis_date", "")
            # Staleness check: >3 days old = stale
            _stale = False
            try:
                from datetime import datetime, timedelta
                _ad = datetime.strptime(a_date, "%Y-%m-%d")
                _stale = (datetime.now() - _ad) > timedelta(days=3)
            except Exception:
                pass
            
            sig["gemini"] = {
                "signal": ga.get("signal", ""),
                "confidence": ga.get("confidence", 0),
                "direction": sj.get("direction", ""),
                "targets": sj.get("targets", []),
                "stop_loss": sj.get("stop_loss", ""),
                "entry": sj.get("entry", ""),
                "support": sj.get("support", []),
                "resistance": sj.get("resistance", []),
                "analysis_date": a_date,
                "stale": _stale,
            }
            
            # Conflict detection
            radar_verdict = sig.get("verdict_key", "")
            gemini_signal = (ga.get("signal") or "").lower()
            _conflict = False
            if radar_verdict == "buy" and any(w in gemini_signal for w in ["بيع", "انتظار"]):
                _conflict = True
            elif radar_verdict == "avoid" and any(w in gemini_signal for w in ["شراء"]):
                _conflict = True
            sig["gemini_conflict"] = _conflict
        else:
            sig["gemini"] = None
            sig["gemini_conflict"] = False
    
    # Gemini-boosted decision card
    dc = data.get("decision_card")
    if dc and dc.get("gemini") and not dc["gemini"].get("stale"):
        gc = dc["gemini"].get("confidence", 0)
        if gc >= 70:
            # Boost confluence by Gemini confidence factor
            old_score = dc.get("confluence_score", 0)
            boost = min(15, int((gc - 50) * 0.3))  # max +15
            dc["confluence_score_raw"] = old_score
            dc["gemini_boost"] = boost
except Exception as e:
    import logging
    logging.getLogger("dashboard_api").warning("Gemini overlay failed: %s", e)
```

#### الخطوة 2: إضافة risk summary للـ response

**في نفس الدالة `dashboard_signals_daily()`، بعد الكود أعلاه أضف:**

```python
# ═══ Risk Summary ═══
try:
    from risk_engine import _get_risk_config, check_can_open
    rc = _get_risk_config()
    open_count = len(data.get("open_positions", []))
    max_pos = rc.get("max_positions", 5)
    data["risk_summary"] = {
        "capital": rc.get("capital", 0),
        "risk_per_trade_pct": rc.get("risk_per_trade_pct", 2),
        "max_positions": max_pos,
        "open_positions_count": open_count,
        "slots_available": max(0, max_pos - open_count),
        "portfolio_heat_pct": round(open_count / max(max_pos, 1) * 100, 1),
    }
except Exception:
    data["risk_summary"] = None
```

#### الخطوة 3: إضافة transaction count للمراكز المفتوحة

**في نفس الدالة، في قسم "Open positions with live P&L":**

حالياً الكود يبني `result["open_positions"]`. 
**بعد بناء كل position، أضف:**

```python
# Transaction history for this trade
try:
    import sqlite3 as _sq
    _db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "life.db")
    _tc = _sq.connect(_db, timeout=5)
    _txs = _tc.execute(
        "SELECT COUNT(*) as cnt, SUM(CASE WHEN tx_type='partial_sell' THEN quantity ELSE 0 END) as sold_qty "
        "FROM trade_transactions WHERE trade_id=?",
        (trade.get("id"),)
    ).fetchone()
    _tc.close()
    pos_entry["tx_count"] = _txs[0] if _txs else 0
    pos_entry["qty_sold"] = _txs[1] if _txs and _txs[1] else 0
except Exception:
    pos_entry["tx_count"] = 0
    pos_entry["qty_sold"] = 0
```

**ملاحظة:** `pos_entry` هو كل item في `result["open_positions"].append({...})`.
الحل الأنظف: أضف الحقول بعد الـ append loop.

---

## التحقق بعد التعديل

```bash
# 1. Quick check
python3 _tools/quick_check.py

# 2. Smoke test
python3 _tools/smoke_test.py

# 3. تحقق من الـ endpoint
curl -s http://localhost:9000/dashboard/signals-daily | python3 -m json.tool | head -50

# 4. تحقق إن gemini موجود
curl -s http://localhost:9000/dashboard/signals-daily | python3 -c "
import sys, json
d = json.load(sys.stdin)
sigs = d.get('all_signals', [])
gemini_count = sum(1 for s in sigs if s.get('gemini'))
conflict_count = sum(1 for s in sigs if s.get('gemini_conflict'))
print(f'Total signals: {len(sigs)}')
print(f'With Gemini: {gemini_count}')
print(f'Conflicts: {conflict_count}')
print(f'Risk summary: {d.get(\"risk_summary\")}')
if sigs:
    s = sigs[0]
    print(f'First signal gemini: {json.dumps(s.get(\"gemini\"), ensure_ascii=False, indent=2)}')
"

# 5. Restart
bash _tools/restart_master_ai.sh
```

---

## ملاحظات مهمة
- **لا تغير** بنية `build_signals()` في `signal_engine.py` — التعديل كله في `dashboard_api.py`
- **backward-compatible**: حقول `gemini` و `gemini_conflict` و `risk_summary` كلها إضافية
- الأسهم اللي ما عندها تحليل Gemini ترجع `gemini: null`
- الـ conflict detection بسيط (keyword matching) — ممكن نحسنه لاحقاً
- إذا `stock_analyzer` ما يتحمل (import error) → يتجاوز بدون خطأ
