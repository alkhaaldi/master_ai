# Golden Opportunities Engine — قرارات الآن
# Date: 2026-03-28
# Author: claude.ai + ChatGPT → Claude Code
# Scope: صفحة تطابق الحالة الحية مع الأنماط التاريخية وتعرض الفرص الذهبية

---

## الهدف
صفحة جديدة "قرارات الآن" تقارن الحالة الحية لكل سهم مع أنماطه التاريخية الناجحة.
لو سهم الآن عنده نمط تاريخي بنسبة نجاح > 60% → يظهر كفرصة.

## المنطق — 3 خطوات:
1. تحويل البيانات الحية لـ atoms (نفس atoms اللي بـ stock_personality_engine.py)
2. مطابقة مع symbol_patterns بالـ DB
3. حساب confidence score وعرض الفرص

---

## PHASE 1 — ملف جديد: `golden_engine.py`

### المكان: `/home/pi/master_ai/golden_engine.py`

```python
"""
golden_engine.py — Golden Opportunities Engine.
Matches LIVE market data against historical winning patterns.
Produces ranked opportunities with confidence scores.

Endpoint: GET /api/decisions-now
"""
import os
import math
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger("golden_engine")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")

# ═══════════════════════════════════
# ATOM BUILDER — same atoms as personality engine
# ═══════════════════════════════════

def build_live_atoms(live: dict) -> set:
    """Convert live indicator data into atom set."""
    atoms = set()
    rsi = float(live.get("rsi_14") or live.get("rsi") or 99)
    vol = float(live.get("vol_ratio") or 0)
    adx = float(live.get("adx") or 0)
    stoch = float(live.get("stoch_k") or 99)
    macd_state = str(live.get("macd_state") or live.get("macd_cross") or "").lower()
    ema_state = str(live.get("ema_state") or live.get("daily_ema_cross") or "").lower()
    bb_squeeze = live.get("bb_squeeze")
    confluence = float(live.get("confluence_score") or 0)
    price = float(live.get("price") or 0)
    support = float(live.get("support") or 0)
    resistance = float(live.get("resistance") or 0)
    atr = float(live.get("atr_14") or live.get("atr") or 0)

    # RSI
    if rsi < 30: atoms.add("rsi_lt_30")
    if 30 <= rsi < 45: atoms.add("rsi_30_45")
    if rsi > 70: atoms.add("rsi_gt_70")

    # MACD
    if "bullish" in macd_state: atoms.add("macd_bullish")
    if "bearish" in macd_state: atoms.add("macd_bearish")

    # EMA
    if "bullish" in ema_state: atoms.add("ema_bullish")
    if "bearish" in ema_state: atoms.add("ema_bearish")

    # ADX
    if adx >= 25: atoms.add("adx_ge_25")
    if adx < 20: atoms.add("adx_lt_20")

    # Volume
    if vol >= 1.5: atoms.add("vol_ge_1_5")
    if vol >= 2.0: atoms.add("vol_ge_2")

    # Stochastic
    if stoch < 20: atoms.add("stoch_lt_20")
    if stoch > 80: atoms.add("stoch_gt_80")

    # BB
    if bb_squeeze: atoms.add("bb_squeeze")

    # Confluence
    if confluence >= 70: atoms.add("confluence_ge_70")

    # S/R proximity (within 3%)
    if price > 0 and support > 0:
        dist = (price - support) / support
        if 0 <= dist <= 0.03: atoms.add("near_support")
        if dist < 0: atoms.add("below_support")

    if price > 0 and resistance > 0:
        dist = (resistance - price) / resistance
        if 0 <= dist <= 0.03: atoms.add("near_resistance")
        if price > resistance: atoms.add("above_resistance")

    # ATR volatility
    if price > 0 and atr > 0:
        atr_pct = atr / price
        if atr_pct > 0.03: atoms.add("high_atr")
        if atr_pct < 0.015: atoms.add("low_atr")

    return atoms


# ═══════════════════════════════════
# MATCHING & SCORING
# ═══════════════════════════════════

def match_pattern(live_atoms: set, pattern_atoms_str: str) -> tuple:
    """Match live atoms against pattern atoms. Returns (match_ratio, matched, missing)."""
    pat_atoms = set(a.strip() for a in pattern_atoms_str.split(",") if a.strip())
    if not pat_atoms:
        return 0, [], []
    matched = [a for a in pat_atoms if a in live_atoms]
    missing = [a for a in pat_atoms if a not in live_atoms]
    ratio = len(matched) / len(pat_atoms)
    return ratio, matched, missing


def calc_confidence(pattern: dict, profile: dict, match_ratio: float) -> float:
    """Calculate confidence score 0-100."""
    wr = float(pattern.get("win_rate") or 0)
    occ = int(pattern.get("occurrences") or 0)
    avg_gain = float(pattern.get("avg_gain_pct") or 0)
    pat_score = float(pattern.get("pattern_score") or 0)
    baseline = float(profile.get("baseline_win_rate") or 0.3)

    # 1. Match quality (35%)
    match_score = match_ratio * 100

    # 2. Win rate vs baseline (20%)
    excess = (wr - baseline) * 100
    wr_score = max(0, min(100, (excess + 10) / 30 * 100))

    # 3. Sample size (15%)
    sample_score = min(100, math.log1p(occ) / math.log1p(50) * 100)

    # 4. Pattern score (10%)
    ps_norm = min(100, pat_score)

    # 5. Gain quality (10%)
    gain_score = min(100, avg_gain / 12 * 100)

    # 6. Profile alignment (10%) — simple: does dominant driver match pattern?
    align = 50
    dom = str(profile.get("dominant_driver") or "").lower()
    pat_atoms_str = str(pattern.get("pattern_atoms") or "").lower()
    if "stoch" in dom and "stoch" in pat_atoms_str: align = 90
    elif "volume" in dom and "vol" in pat_atoms_str: align = 85
    elif "macd" in dom and "macd" in pat_atoms_str: align = 80
    elif "rsi" in dom and "rsi" in pat_atoms_str: align = 80
    elif "ema" in dom and "ema" in pat_atoms_str: align = 75

    confidence = (
        0.35 * match_score +
        0.20 * wr_score +
        0.15 * sample_score +
        0.10 * ps_norm +
        0.10 * gain_score +
        0.10 * align
    )
    return round(max(0, min(100, confidence)), 1)


# ═══════════════════════════════════
# STOP LOSS
# ═══════════════════════════════════

def suggest_stop(live: dict) -> dict:
    price = float(live.get("price") or 0)
    atr = float(live.get("atr_14") or live.get("atr") or 0)
    support = float(live.get("support") or 0)
    if price <= 0:
        return {"method": "N/A", "stop_price": None, "distance_pct": None}
    if support > 0 and atr > 0:
        stop = support - 0.5 * atr
        return {"method": "support_atr", "stop_price": round(stop, 3), "distance_pct": round((price - stop) / price * 100, 1)}
    if atr > 0:
        stop = price - 1.2 * atr
        return {"method": "atr_only", "stop_price": round(stop, 3), "distance_pct": round(1.2 * atr / price * 100, 1)}
    return {"method": "N/A", "stop_price": None, "distance_pct": None}


# ═══════════════════════════════════
# ARABIC LABELS
# ═══════════════════════════════════

ATOM_AR = {
    "rsi_lt_30": "RSI < 30", "rsi_30_45": "RSI 30-45", "rsi_gt_70": "RSI > 70",
    "macd_bullish": "MACD \u0635\u0627\u0639\u062f", "macd_bearish": "MACD \u0647\u0627\u0628\u0637",
    "ema_bullish": "EMA \u0635\u0627\u0639\u062f", "ema_bearish": "EMA \u0647\u0627\u0628\u0637",
    "adx_ge_25": "ADX \u2265 25", "adx_lt_20": "ADX < 20",
    "vol_ge_1_5": "\u062d\u062c\u0645 1.5x", "vol_ge_2": "\u062d\u062c\u0645 2x",
    "stoch_lt_20": "Stoch < 20", "stoch_gt_80": "Stoch > 80",
    "bb_squeeze": "BB \u0636\u063a\u0637", "confluence_ge_70": "Confluence \u2265 70",
    "near_support": "\u0642\u0631\u0628 \u062f\u0639\u0645", "near_resistance": "\u0642\u0631\u0628 \u0645\u0642\u0627\u0648\u0645\u0629",
    "above_resistance": "\u0627\u062e\u062a\u0631\u0627\u0642", "below_support": "\u0643\u0633\u0631 \u062f\u0639\u0645",
    "high_atr": "\u062a\u0630\u0628\u0630\u0628 \u0639\u0627\u0644\u064a", "low_atr": "\u062a\u0630\u0628\u0630\u0628 \u0645\u0646\u062e\u0641\u0636",
}

def atoms_to_ar(atoms_str):
    return " + ".join(ATOM_AR.get(a.strip(), a.strip()) for a in atoms_str.split(",") if a.strip())


# ═══════════════════════════════════
# MAIN ENGINE
# ═══════════════════════════════════

# Quality filters
MIN_OCCURRENCES = 8
MIN_WIN_RATE = 0.55
MIN_MATCH_RATIO = 0.75
MIN_CONFIDENCE = 65

def scan_opportunities(live_data: list) -> dict:
    """
    Main entry point.
    live_data: list of dicts with live indicator data per symbol.
    Each dict needs: symbol, price, rsi_14, vol_ratio, adx, stoch_k, macd_state/macd_cross,
                     ema_state/daily_ema_cross, bb_squeeze, support, resistance, atr_14, confluence_score
    Returns ranked opportunities.
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row

    # Load all profiles
    profiles = {}
    for r in conn.execute("SELECT * FROM stock_profiles").fetchall():
        profiles[r["symbol"]] = dict(r)

    # Load all patterns with decent quality
    patterns_by_sym = {}
    for r in conn.execute(
        "SELECT * FROM symbol_patterns WHERE occurrences >= ? AND win_rate >= ? ORDER BY pattern_score DESC",
        (MIN_OCCURRENCES, MIN_WIN_RATE)
    ).fetchall():
        sym = r["symbol"]
        if sym not in patterns_by_sym:
            patterns_by_sym[sym] = []
        patterns_by_sym[sym].append(dict(r))

    conn.close()

    all_opportunities = []

    for live in live_data:
        sym = (live.get("symbol") or "").upper()
        if not sym or sym not in patterns_by_sym:
            continue

        live_atoms = build_live_atoms(live)
        profile = profiles.get(sym, {"baseline_win_rate": 0.3})
        sym_patterns = patterns_by_sym.get(sym, [])

        best_opp = None

        for pat in sym_patterns:
            ratio, matched, missing = match_pattern(live_atoms, pat.get("pattern_atoms", ""))

            if ratio < MIN_MATCH_RATIO:
                continue

            confidence = calc_confidence(pat, profile, ratio)

            if confidence < MIN_CONFIDENCE:
                continue

            opp_type = "\U0001f525 \u0641\u0631\u0635\u0629 \u0630\u0647\u0628\u064a\u0629" if confidence >= 80 else "\u{1F7E2} \u0645\u0631\u0634\u062d" if confidence >= 70 else "\u{1F7E1} \u0645\u0631\u0627\u0642\u0628\u0629"

            opp = {
                "symbol": sym,
                "name_ar": profile.get("name_ar") or "",
                "personality_ar": profile.get("personality_ar") or "",
                "opportunity_type": opp_type,
                "confidence": confidence,
                "price": float(live.get("price") or 0),
                "change_pct": float(live.get("change_pct") or 0),
                "pattern_ar": atoms_to_ar(pat.get("pattern_atoms", "")),
                "pattern_atoms": pat.get("pattern_atoms", ""),
                "matched_atoms": ",".join(matched),
                "missing_atoms": ",".join(missing),
                "match_ratio": round(ratio, 2),
                "occurrences": pat.get("occurrences", 0),
                "hits": pat.get("hits", 0),
                "win_rate": round(float(pat.get("win_rate", 0)) * 100, 1),
                "avg_gain_pct": round(float(pat.get("avg_gain_pct", 0)), 1),
                "pattern_score": pat.get("pattern_score", 0),
                "current_rsi": float(live.get("rsi_14") or live.get("rsi") or 0),
                "current_vol": float(live.get("vol_ratio") or 0),
                "current_adx": float(live.get("adx") or 0),
                "current_stoch": float(live.get("stoch_k") or 0),
                "live_atoms": sorted(list(live_atoms)),
                "stop_loss": suggest_stop(live),
                "dominant_driver": profile.get("dominant_driver", ""),
                "baseline_wr": round(float(profile.get("baseline_win_rate", 0)) * 100, 1),
            }

            if best_opp is None or confidence > best_opp["confidence"]:
                best_opp = opp

        if best_opp:
            all_opportunities.append(best_opp)

    # Sort by confidence
    all_opportunities.sort(key=lambda x: x["confidence"], reverse=True)

    # Add rank
    for i, opp in enumerate(all_opportunities):
        opp["rank"] = i + 1

    golden = [o for o in all_opportunities if o["confidence"] >= 80]
    candidates = [o for o in all_opportunities if 70 <= o["confidence"] < 80]
    watch = [o for o in all_opportunities if o["confidence"] < 70]

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "total_scanned": len(live_data),
        "total_opportunities": len(all_opportunities),
        "golden_count": len(golden),
        "candidate_count": len(candidates),
        "watch_count": len(watch),
        "top_10": all_opportunities[:10],
        "all_opportunities": all_opportunities,
    }
```

---

## PHASE 2 — Endpoint

### ملف: `server.py` أو `dashboard_api.py`

```python
@app.get("/api/decisions-now")
async def api_decisions_now():
    """Golden opportunities — match live data with historical patterns."""
    from golden_engine import scan_opportunities

    # Get live data from signal engine (30m or 1D)
    try:
        from signal_engine import build_signals_30m
        sig_data = build_signals_30m()
        live_list = sig_data.get("signals", [])
    except Exception:
        live_list = []

    # Fallback: try 1D signals
    if not live_list:
        try:
            from signal_engine import build_signals
            sig_data = build_signals()
            live_list = sig_data.get("all_signals", [])
        except Exception:
            live_list = []

    return scan_opportunities(live_list)
```

---

## PHASE 3 — Testing

```bash
cd /home/pi/master_ai

# 1. Test golden engine:
venv/bin/python3 -c "
from golden_engine import scan_opportunities, build_live_atoms

# Simulate CLEANING live data
test = [{
    'symbol': 'CLEANING',
    'price': 135, 'rsi_14': 28, 'vol_ratio': 2.3,
    'macd_state': 'bearish', 'stoch_k': 18,
    'adx': 25, 'support': 106, 'resistance': 153,
    'atr_14': 6.5, 'bb_squeeze': False, 'confluence_score': 100,
    'ema_state': 'bullish', 'daily_ema_cross': 'bullish',
}]
atoms = build_live_atoms(test[0])
print('Atoms:', sorted(atoms))

result = scan_opportunities(test)
import json
print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
"

# 2. Test endpoint:
KEY=$(cat ~/.master_ai_key)
curl -s -H "X-API-Key: $KEY" http://localhost:9000/api/decisions-now | python3 -m json.tool | head -50

# 3. Commit:
git add golden_engine.py server.py
git commit -m 'feat: golden opportunities engine — pattern matching + confidence scoring + stop loss'
sudo systemctl restart master-ai.service
```

---

## PHASE 4 — Dashboard (claude.ai يبنيه بعد)

صفحة `decisions.html` بتعرض:
- Hero: "X فرصة ذهبية الآن"
- جدول مرتب بالـ confidence
- لكل فرصة: السهم + النمط + Win% + Confidence + Stop Loss
- ألوان: ذهبي (≥80) + أخضر (≥70) + أصفر (≥65)

---

## HOW TO EXECUTE

Tell Claude Code:
```
اقرأ _tools/GOLDEN_OPPORTUNITIES_PLAN.md وأنشئ:
1. golden_engine.py (الكود الكامل موجود بالخطة)
2. أضف /api/decisions-now endpoint
3. اختبر مع simulated data
4. Commit + restart
```
