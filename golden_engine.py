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
    rsi        = float(live.get("rsi_14") or live.get("rsi") or 99)
    vol        = float(live.get("vol_ratio") or 0)
    adx        = float(live.get("adx") or 0)
    stoch      = float(live.get("stoch_k") or 99)
    macd_state = str(live.get("macd_state") or live.get("macd_cross") or "").lower()
    ema_state  = str(live.get("ema_state") or live.get("daily_ema_cross") or "").lower()
    bb_squeeze = live.get("bb_squeeze")
    confluence = float(live.get("confluence_score") or 0)
    price      = float(live.get("price") or 0)
    support    = float(live.get("support") or 0)
    resistance = float(live.get("resistance") or 0)
    atr        = float(live.get("atr_14") or live.get("atr") or 0)

    # RSI
    if rsi < 30:           atoms.add("rsi_lt_30")
    if 30 <= rsi < 45:     atoms.add("rsi_30_45")
    if rsi > 70:           atoms.add("rsi_gt_70")

    # MACD
    if "bullish" in macd_state: atoms.add("macd_bullish")
    if "bearish" in macd_state: atoms.add("macd_bearish")

    # EMA
    if "bullish" in ema_state: atoms.add("ema_bullish")
    if "bearish" in ema_state: atoms.add("ema_bearish")

    # ADX
    if adx >= 25: atoms.add("adx_ge_25")
    if adx < 20:  atoms.add("adx_lt_20")

    # Volume
    if vol >= 1.5: atoms.add("vol_ge_1_5")
    if vol >= 2.0: atoms.add("vol_ge_2")

    # Stochastic
    if stoch < 20: atoms.add("stoch_lt_20")
    if stoch > 80: atoms.add("stoch_gt_80")

    # Bollinger
    if bb_squeeze: atoms.add("bb_squeeze")

    # Confluence
    if confluence >= 70: atoms.add("confluence_ge_70")

    # S/R proximity (within 3%)
    if price > 0 and support > 0:
        dist = (price - support) / support
        if 0 <= dist <= 0.03: atoms.add("near_support")
        if dist < 0:          atoms.add("below_support")

    if price > 0 and resistance > 0:
        dist = (resistance - price) / resistance
        if 0 <= dist <= 0.03:  atoms.add("near_resistance")
        if price > resistance: atoms.add("above_resistance")

    # ATR volatility
    if price > 0 and atr > 0:
        atr_pct = atr / price
        if atr_pct > 0.03:  atoms.add("high_atr")
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
    wr        = float(pattern.get("win_rate") or 0)
    occ       = int(pattern.get("occurrences") or 0)
    avg_gain  = float(pattern.get("avg_gain_pct") or 0)
    pat_score = float(pattern.get("pattern_score") or 0)
    baseline  = float(profile.get("baseline_win_rate") or 0.3)

    # 1. Match quality (35%)
    match_score = match_ratio * 100

    # 2. Win rate vs baseline (20%)
    excess   = (wr - baseline) * 100
    wr_score = max(0, min(100, (excess + 10) / 30 * 100))

    # 3. Sample size (15%)
    sample_score = min(100, math.log1p(occ) / math.log1p(50) * 100)

    # 4. Pattern score (10%)
    ps_norm = min(100, pat_score)

    # 5. Gain quality (10%)
    gain_score = min(100, avg_gain / 12 * 100)

    # 6. Profile alignment (10%) — dominant driver matches pattern?
    align = 50
    dom          = str(profile.get("dominant_driver") or "").lower()
    pat_atoms_str = str(pattern.get("pattern_atoms") or "").lower()
    if "stoch"  in dom and "stoch" in pat_atoms_str:  align = 90
    elif "volume" in dom and "vol"  in pat_atoms_str: align = 85
    elif "macd"  in dom and "macd" in pat_atoms_str:  align = 80
    elif "rsi"   in dom and "rsi"  in pat_atoms_str:  align = 80
    elif "ema"   in dom and "ema"  in pat_atoms_str:  align = 75

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
    price      = float(live.get("price") or 0)
    atr        = float(live.get("atr_14") or live.get("atr") or 0)
    support    = float(live.get("support") or 0)
    if price <= 0:
        return {"method": "N/A", "stop_price": None, "distance_pct": None}
    if support > 0 and atr > 0:
        stop = support - 0.5 * atr
        return {"method": "support_atr", "stop_price": round(stop, 3),
                "distance_pct": round((price - stop) / price * 100, 1)}
    if atr > 0:
        stop = price - 1.2 * atr
        return {"method": "atr_only", "stop_price": round(stop, 3),
                "distance_pct": round(1.2 * atr / price * 100, 1)}
    return {"method": "N/A", "stop_price": None, "distance_pct": None}


# ═══════════════════════════════════
# ARABIC LABELS
# ═══════════════════════════════════

ATOM_AR = {
    "rsi_lt_30": "RSI < 30",       "rsi_30_45": "RSI 30-45",   "rsi_gt_70": "RSI > 70",
    "macd_bullish": "MACD صاعد",   "macd_bearish": "MACD هابط",
    "ema_bullish": "EMA صاعد",     "ema_bearish": "EMA هابط",
    "adx_ge_25": "ADX ≥ 25",       "adx_lt_20": "ADX < 20",
    "vol_ge_1_5": "حجم 1.5x",      "vol_ge_2": "حجم 2x",
    "stoch_lt_20": "Stoch < 20",   "stoch_gt_80": "Stoch > 80",
    "bb_squeeze": "BB ضغط",        "confluence_ge_70": "Confluence ≥ 70",
    "near_support": "قرب دعم",     "near_resistance": "قرب مقاومة",
    "above_resistance": "اختراق",  "below_support": "كسر دعم",
    "high_atr": "تذبذب عالي",      "low_atr": "تذبذب منخفض",
}

def atoms_to_ar(atoms_str: str) -> str:
    return " + ".join(ATOM_AR.get(a.strip(), a.strip()) for a in atoms_str.split(",") if a.strip())


# ═══════════════════════════════════
# MAIN ENGINE
# ═══════════════════════════════════

MIN_OCCURRENCES = 8
MIN_WIN_RATE    = 0.55
MIN_MATCH_RATIO = 0.75
MIN_CONFIDENCE  = 65


def scan_opportunities(live_data: list) -> dict:
    """
    Main entry point.
    live_data: list of dicts with live indicator data per symbol.
    Each dict needs: symbol, price, rsi_14, vol_ratio, adx, stoch_k,
                     macd_state/macd_cross, ema_state/daily_ema_cross,
                     bb_squeeze, support, resistance, atr_14, confluence_score
    Returns ranked opportunities.
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row

    profiles = {}
    for r in conn.execute("SELECT * FROM stock_profiles").fetchall():
        profiles[r["symbol"]] = dict(r)

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

        live_atoms  = build_live_atoms(live)
        profile     = profiles.get(sym, {"baseline_win_rate": 0.3})
        sym_patterns = patterns_by_sym.get(sym, [])

        best_opp = None

        for pat in sym_patterns:
            ratio, matched, missing = match_pattern(live_atoms, pat.get("pattern_atoms", ""))
            if ratio < MIN_MATCH_RATIO:
                continue

            confidence = calc_confidence(pat, profile, ratio)
            if confidence < MIN_CONFIDENCE:
                continue

            if confidence >= 80:
                opp_type = "🔥 فرصة ذهبية"
            elif confidence >= 70:
                opp_type = "🟢 مرشح"
            else:
                opp_type = "🟡 مراقبة"

            opp = {
                "symbol":        sym,
                "name_ar":       profile.get("name_ar") or "",
                "personality_ar": profile.get("personality_ar") or "",
                "opportunity_type": opp_type,
                "confidence":    confidence,
                "price":         float(live.get("price") or 0),
                "change_pct":    float(live.get("change_pct") or 0),
                "pattern_ar":    atoms_to_ar(pat.get("pattern_atoms", "")),
                "pattern_atoms": pat.get("pattern_atoms", ""),
                "matched_atoms": ",".join(matched),
                "missing_atoms": ",".join(missing),
                "match_ratio":   round(ratio, 2),
                "occurrences":   pat.get("occurrences", 0),
                "hits":          pat.get("hits", 0),
                "win_rate":      round(float(pat.get("win_rate", 0)) * 100, 1),
                "avg_gain_pct":  round(float(pat.get("avg_gain_pct", 0)), 1),
                "pattern_score": pat.get("pattern_score", 0),
                "current_rsi":   float(live.get("rsi_14") or live.get("rsi") or 0),
                "current_vol":   float(live.get("vol_ratio") or 0),
                "current_adx":   float(live.get("adx") or 0),
                "current_stoch": float(live.get("stoch_k") or 0),
                "live_atoms":    sorted(list(live_atoms)),
                "stop_loss":     suggest_stop(live),
                "dominant_driver": profile.get("dominant_driver", ""),
                "baseline_wr":   round(float(profile.get("baseline_win_rate", 0)) * 100, 1),
            }

            if best_opp is None or confidence > best_opp["confidence"]:
                best_opp = opp

        if best_opp:
            all_opportunities.append(best_opp)

    all_opportunities.sort(key=lambda x: x["confidence"], reverse=True)
    for i, opp in enumerate(all_opportunities):
        opp["rank"] = i + 1

    golden     = [o for o in all_opportunities if o["confidence"] >= 80]
    candidates = [o for o in all_opportunities if 70 <= o["confidence"] < 80]
    watch      = [o for o in all_opportunities if o["confidence"] < 70]

    return {
        "generated_at":        datetime.utcnow().isoformat(),
        "total_scanned":       len(live_data),
        "total_opportunities": len(all_opportunities),
        "golden_count":        len(golden),
        "candidate_count":     len(candidates),
        "watch_count":         len(watch),
        "top_10":              all_opportunities[:10],
        "all_opportunities":   all_opportunities,
    }
