# Brain Decision Authority — خطة تحكّم العقل بالقرار النهائي
# Date: 2026-03-27
# Author: claude.ai → Claude Code
# Scope: Brain يتحكم بالـ thresholds + verdict + regime-awareness

---

## المشكلة

الـ Brain يأثر فقط على **الـ score** (أوزان المؤشرات).
بس القرار النهائي (شراء/مراقبة/تجنب) مبني على **حدود ثابتة بالكود**:

```python
# signal_engine.py — ثوابت لا تتغير:
if score >= 60 and vol > 1.2:  return "ready"     # ← ثابت
if score >= 40:                return "setup"      # ← ثابت
if state == "ready" and "bullish" in direction:    return "buy"  # ← ثابت
if score < 30:                 return "avoid"      # ← ثابت
```

هذا يعني:
- لو الـ Brain تعلّم إن الإشارات اللي فوق 45 ناجحة أكثر من اللي فوق 60 → ما يقدر يغيّر
- لو السوق عرضي وكل الإشارات تفشل → نفس الحدود تشتغل
- الـ verdict ما يراعي الـ regime أبداً

## الحل: 3 تغييرات

---

## CHANGE 1 — Dynamic Thresholds من الـ Brain

### ملف: `trading_brain.py` — إضافة function جديدة

```python
def get_optimal_thresholds():
    """Calculate optimal thresholds from historical backfill data.
    Returns thresholds for trade state assignment and verdict decisions.
    Falls back to defaults if insufficient data."""

    DEFAULTS = {
        "ready_min_score": 60,
        "ready_min_vol": 1.2,
        "setup_min_score": 40,
        "avoid_max_score": 30,
        "watch_min_score": 50,
    }

    conn = _conn()
    try:
        # Need at least 100 evaluated signals
        total = conn.execute(
            "SELECT COUNT(*) FROM signal_snapshots WHERE outcome IN ('hit','miss')"
        ).fetchone()[0]

        if total < 100:
            return {**DEFAULTS, "source": "defaults", "data_points": total}

        # Find the confluence_score where hit_rate > 50% (sweet spot)
        rows = conn.execute("""
            SELECT confluence_score,
                   COUNT(*) as total,
                   SUM(CASE WHEN outcome='hit' THEN 1 ELSE 0 END) as hits
            FROM signal_snapshots
            WHERE outcome IN ('hit','miss')
            GROUP BY confluence_score
            ORDER BY confluence_score
        """).fetchall()

        # Build cumulative hit rate from top down
        # "ready" = score where cumulative hit rate >= 55%
        # "setup" = score where cumulative hit rate >= 45%
        # "avoid" = score where cumulative hit rate < 35%
        score_hits = [(r["confluence_score"], r["hits"], r["total"]) for r in rows]

        # Cumulative from high to low
        cum_hits = 0
        cum_total = 0
        ready_threshold = DEFAULTS["ready_min_score"]
        setup_threshold = DEFAULTS["setup_min_score"]
        avoid_threshold = DEFAULTS["avoid_max_score"]

        for score, hits, tot in sorted(score_hits, reverse=True):
            cum_hits += hits
            cum_total += tot
            rate = cum_hits / cum_total if cum_total > 0 else 0

            if rate >= 0.55 and score < ready_threshold:
                ready_threshold = max(score, 35)  # don't go below 35
            if rate >= 0.45 and score < setup_threshold:
                setup_threshold = max(score, 25)  # don't go below 25

        # Avoid = score where hit rate is consistently bad
        cum_hits_low = 0
        cum_total_low = 0
        for score, hits, tot in sorted(score_hits):
            cum_hits_low += hits
            cum_total_low += tot
            rate = cum_hits_low / cum_total_low if cum_total_low > 0 else 0
            if rate < 0.35:
                avoid_threshold = max(score + 5, 20)  # don't go below 20

        result = {
            "ready_min_score": ready_threshold,
            "ready_min_vol": 1.2,  # keep volume requirement fixed
            "setup_min_score": setup_threshold,
            "avoid_max_score": avoid_threshold,
            "watch_min_score": int((ready_threshold + setup_threshold) / 2),
            "source": "brain_learned",
            "data_points": total,
        }
        return result

    except Exception as e:
        logger.warning(f"get_optimal_thresholds failed: {e}")
        return {**DEFAULTS, "source": "defaults_error"}
    finally:
        conn.close()
```

### Test:
```bash
venv/bin/python3 -c "
from trading_brain import get_optimal_thresholds
import json
t = get_optimal_thresholds()
print(json.dumps(t, indent=2))
"
# Expected: source='brain_learned', data_points>100, thresholds may differ from defaults
```

---

## CHANGE 2 — signal_engine يستخدم الـ Dynamic Thresholds

### ملف: `signal_engine.py` — تعديل `_assign_trade_state()` و `_compute_verdict()`

### 2A: Cache thresholds (don't query DB every call)

أضف في أعلى الملف:
```python
import time as _time

_cached_thresholds = None
_thresholds_ts = 0
_THRESHOLDS_TTL = 300  # refresh every 5 min


def _get_thresholds():
    """Get brain-learned thresholds with 5-min cache."""
    global _cached_thresholds, _thresholds_ts
    now = _time.time()
    if _cached_thresholds and (now - _thresholds_ts) < _THRESHOLDS_TTL:
        return _cached_thresholds
    try:
        from trading_brain import get_optimal_thresholds
        _cached_thresholds = get_optimal_thresholds()
        _thresholds_ts = now
    except Exception:
        _cached_thresholds = {
            "ready_min_score": 60, "ready_min_vol": 1.2,
            "setup_min_score": 40, "avoid_max_score": 30,
            "watch_min_score": 50, "source": "fallback",
        }
    return _cached_thresholds
```

### 2B: Replace hardcoded thresholds in `_assign_trade_state()`:

```python
def _assign_trade_state(symbol: str, bridge: dict, radar: dict, trade: dict) -> str:
    if trade:
        if symbol in _get_bridge_symbols_set():
            return "manage"
        return "entered"

    confluence = _extract_confluence(bridge)
    score = confluence.get("score", 0)
    vol = bridge.get("vol_ratio") or 0

    t = _get_thresholds()  # ← Brain-learned thresholds

    if score >= t["ready_min_score"] and vol > t["ready_min_vol"]:
        return "ready"
    if score >= t["setup_min_score"]:
        return "setup"
    if radar:
        return "discovery"
    return None
```

### 2C: Replace hardcoded thresholds in `_compute_verdict()`:

```python
def _compute_verdict(bridge: dict, state: str) -> str:
    confluence = _extract_confluence(bridge)
    score = confluence.get("score", 0)
    direction = confluence.get("direction", "")
    regime = confluence.get("regime", "unknown")
    momentum = (bridge.get("signals") or {}).get("macd_momentum", "")

    t = _get_thresholds()  # ← Brain-learned thresholds

    if state == "ready" and "bullish" in direction:
        return "buy"
    if state == "setup" and score >= t["watch_min_score"]:
        return "watch"
    if state in ("entered", "manage") and "decelerating" in momentum:
        return "review"
    if score < t["avoid_max_score"] or "bearish" in direction:
        return "avoid"
    return "neutral"
```

---

## CHANGE 3 — Regime-Aware Verdict

### ملف: `signal_engine.py` — تعديل `_compute_verdict()`

الحين الـ verdict ما يراعي الـ regime. المفروض:
- سوق عرضي + EMA cross → ثقة أقل (false signals كثيرة)
- سوق اتجاهي + momentum → ثقة أعلى

```python
def _compute_verdict(bridge: dict, state: str) -> str:
    confluence = _extract_confluence(bridge)
    score = confluence.get("score", 0)
    direction = confluence.get("direction", "")
    regime = confluence.get("regime", "unknown")
    momentum = (bridge.get("signals") or {}).get("macd_momentum", "")

    t = _get_thresholds()

    # Regime adjustment: في السوق العرضي، نرفع الحد (أكثر حذر)
    regime_penalty = 0
    if regime == "ranging":
        regime_penalty = 10  # need 10 more points in ranging market
    elif regime == "trending":
        regime_penalty = -5  # slightly easier in trending market

    adjusted_watch = t["watch_min_score"] + regime_penalty
    adjusted_avoid = t["avoid_max_score"] + regime_penalty

    if state == "ready" and "bullish" in direction:
        # Even "ready" gets downgraded in ranging market
        if regime == "ranging" and score < 75:
            return "watch"  # ranging market = مراقبة مو شراء
        return "buy"
    if state == "setup" and score >= adjusted_watch:
        return "watch"
    if state in ("entered", "manage") and "decelerating" in momentum:
        return "review"
    if score < adjusted_avoid or "strong_bearish" in direction:
        return "avoid"
    if "bearish" in direction and regime != "ranging":
        # bearish direction matters more in trending market
        return "avoid"
    return "neutral"
```

### التأثير العملي:
- **سوق اتجاهي:** حدود أقل بـ 5 نقاط → أسهل تطلع "شراء"
- **سوق عرضي:** حدود أعلى بـ 10 نقاط → أصعب تطلع "شراء"، "ready" يصير "مراقبة"
- **سوق عرضي + score < 75:** حتى لو "ready" → يقول "مراقبة" بدل "شراء"

---

## CHANGE 4 — Dashboard Endpoint يعرض الـ Thresholds

### ملف: `dashboard_api.py` — تحديث `/dashboard/brain` و `/dashboard/signals`

#### في `/dashboard/brain`:
```python
from trading_brain import get_optimal_thresholds
thresholds = get_optimal_thresholds()
# Add to return dict:
result["thresholds"] = thresholds
```

#### في `/dashboard/signals`:
```python
# Add thresholds info to the response root
from trading_brain import get_optimal_thresholds
# ... existing code ...
return {
    ...existing fields...,
    "thresholds": get_optimal_thresholds(),
}
```

---

## CHANGE 5 — Confluence detail يعرض مقارنة

### ملف: `trading_brain.py` → `get_adjusted_confluence()`

أضف للـ return dict:
```python
    return {
        "score": score,
        "direction": direction,
        "bullish": bullish,
        "bearish": bearish,
        "total": len(votes),
        "brain_weighted": True,
        "regime": regime,
        # NEW: show what would have been without brain
        "raw_score": int(round((bullish / len(votes)) * 100)) if len(votes) > 0 else 0,
        "brain_delta": score - (int(round((bullish / len(votes)) * 100)) if len(votes) > 0 else 0),
    }
```

هذا يعطي الداشبورد القدرة يقول:
"Confluence: 67 (Brain: +5 عن الأوزان الثابتة)"

---

## TESTING

### After all changes:
```bash
cd /home/pi/master_ai

# 1. Test thresholds:
venv/bin/python3 -c "
from trading_brain import get_optimal_thresholds
import json
print(json.dumps(get_optimal_thresholds(), indent=2))
"

# 2. Test signal engine uses brain thresholds:
venv/bin/python3 -c "
from signal_engine import _get_thresholds
import json
print(json.dumps(_get_thresholds(), indent=2))
"

# 3. Full smoke test:
venv/bin/python3 _tools/quick_check.py
venv/bin/python3 _tools/smoke_test.py

# 4. Test endpoints:
KEY=\$(cat ~/.master_ai_key)
curl -s -H \"X-API-Key: \$KEY\" http://localhost:9000/dashboard/brain | python3 -m json.tool | grep -A5 thresholds
curl -s -H \"X-API-Key: \$KEY\" http://localhost:9000/dashboard/signals | python3 -m json.tool | grep -A5 thresholds

# 5. Commit:
git add trading_brain.py signal_engine.py dashboard_api.py
git commit -m 'feat: brain controls thresholds + regime-aware verdict + raw_score delta'
bash _tools/restart_master_ai.sh
```

---

## SUMMARY — قبل وبعد

### قبل (الحين):
```
Brain يأثر على: Score فقط (أوزان المؤشرات)
Thresholds: ثابتة (60/40/30) — ما تتغير أبداً
Verdict: ما يراعي الـ Regime
```

### بعد (هالخطة):
```
Brain يأثر على:
  ✅ Score (أوزان المؤشرات) — كان شغال
  ✅ Thresholds (حدود القرار) — جديد: Brain يحسبها من البيانات التاريخية
  ✅ Verdict (الحكم النهائي) — جديد: يراعي الـ Regime
  ✅ الداشبورد يعرض الفرق (raw_score vs brain_score)
```

### مثال عملي:
سهم CLEANING: confluence 58, ADX 15 (سوق عرضي)

**قبل:**
- state = setup (58 >= 40 ✅)
- verdict = "مراقبة" (58 >= 50 ✅)

**بعد (لو Brain تعلّم إن الحد الأمثل 45):**
- state = setup (58 >= 45 ✅)
- verdict = "مراقبة" (58 >= 55 ✅ — بسبب regime penalty +10)
- **بس** لو كان score 52:
  - **قبل:** verdict = "مراقبة" (52 >= 50)
  - **بعد:** verdict = "حياد" (52 < 55 بعد regime penalty) ← **Brain منع إشارة كاذبة**

---

## HOW TO EXECUTE

1. File at: `/home/pi/master_ai/_tools/BRAIN_DECISION_AUTHORITY.md`

2. Tell Claude Code:
```
اقرأ _tools/BRAIN_DECISION_AUTHORITY.md ونفذ:
Change 1: أضف get_optimal_thresholds() لـ trading_brain.py
Change 2: عدّل signal_engine.py يستخدم dynamic thresholds
Change 3: عدّل _compute_verdict يراعي الـ regime
Change 4: حدّث endpoints
Change 5: أضف raw_score و brain_delta
ثم اختبر وسوي commit + restart
```
