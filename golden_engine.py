"""
golden_engine.py — Golden Opportunities Engine.
Matches LIVE market data against historical winning patterns.
Produces ranked opportunities with confidence scores, entry decisions, and Telegram alerts.

Endpoint: GET /api/decisions-now
"""
import os
import math
import sqlite3
import logging
import json
from datetime import datetime

logger = logging.getLogger("golden_engine")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    return c


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

    if rsi < 30:           atoms.add("rsi_lt_30")
    if 30 <= rsi < 45:     atoms.add("rsi_30_45")
    if rsi > 70:           atoms.add("rsi_gt_70")

    if "bullish" in macd_state: atoms.add("macd_bullish")
    if "bearish" in macd_state: atoms.add("macd_bearish")

    if "bullish" in ema_state: atoms.add("ema_bullish")
    if "bearish" in ema_state: atoms.add("ema_bearish")

    if adx >= 25: atoms.add("adx_ge_25")
    if adx < 20:  atoms.add("adx_lt_20")

    if vol >= 1.5: atoms.add("vol_ge_1_5")
    if vol >= 2.0: atoms.add("vol_ge_2")

    if stoch < 20: atoms.add("stoch_lt_20")
    if stoch > 80: atoms.add("stoch_gt_80")

    if bb_squeeze: atoms.add("bb_squeeze")

    if confluence >= 70: atoms.add("confluence_ge_70")

    if price > 0 and support > 0:
        dist = (price - support) / support
        if 0 <= dist <= 0.03: atoms.add("near_support")
        if dist < 0:          atoms.add("below_support")

    if price > 0 and resistance > 0:
        dist = (resistance - price) / resistance
        if 0 <= dist <= 0.03:  atoms.add("near_resistance")
        if price > resistance: atoms.add("above_resistance")

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

    match_score  = match_ratio * 100
    excess       = (wr - baseline) * 100
    wr_score     = max(0, min(100, (excess + 10) / 30 * 100))
    sample_score = min(100, math.log1p(occ) / math.log1p(50) * 100)
    ps_norm      = min(100, pat_score)
    gain_score   = min(100, avg_gain / 12 * 100)

    align = 50
    dom           = str(profile.get("dominant_driver") or "").lower()
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
# STOP LOSS (simple — trading_decision_engine provides full plan)
# ═══════════════════════════════════

def suggest_stop(live: dict) -> dict:
    price   = float(live.get("price") or 0)
    atr     = float(live.get("atr_14") or live.get("atr") or 0)
    support = float(live.get("support") or 0)
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
# SMART TRADE DECISION (Phase 9)
# ═══════════════════════════════════

def recalc_rr(entry, stop, target):
    """Calculate real R/R from raw prices."""
    if not entry or not stop or not target:
        return None
    if entry <= 0 or stop <= 0 or target <= 0:
        return None
    if entry <= stop:    # stop above entry = error
        return None
    if target <= entry:  # target below entry = error
        return None
    risk = entry - stop
    reward = target - entry
    if risk <= 0:
        return None
    return round(reward / risk, 2)


def choose_best_plan(opp):
    """
    Compare Golden Engine plan vs Strategy Mining plan.
    Returns the best one with: entry, stop, target1, target2, rr, source.
    """
    tp = opp.get("trade_plan") or {}
    sm = opp.get("strategy_match") or {}
    price = float(opp.get("price", 0))

    # --- Golden Engine plan ---
    g_entry = tp.get("entry_mid") or price
    g_stop = tp.get("stop_loss", 0)
    g_t1 = tp.get("target_1", 0)
    g_t2 = tp.get("target_2")
    g_rr = recalc_rr(g_entry, g_stop, g_t1)
    g_stop_pct = ((g_entry - g_stop) / g_entry * 100) if g_entry > 0 and g_stop > 0 else 99

    # --- Strategy Mining plan ---
    s_entry = sm.get("entry_price") or price
    s_stop = sm.get("stop_price", 0) or 0
    s_t1 = sm.get("target_1_price", 0) or 0
    s_t2 = sm.get("target_2_price")
    s_rr = recalc_rr(s_entry, s_stop, s_t1) if s_stop > 0 and s_t1 > 0 else None
    s_stop_pct = ((s_entry - s_stop) / s_entry * 100) if s_entry > 0 and s_stop > 0 else 99

    # --- Scoring ---
    g_score = 0.0
    s_score = 0.0

    # R/R (most important)
    if g_rr and g_rr > 0:
        g_score += min(g_rr, 5) * 25
    if s_rr and s_rr > 0:
        s_score += min(s_rr, 5) * 25

    # Stop distance (1-6% ideal, penalize far stops)
    if 1.0 <= g_stop_pct <= 6.0:
        g_score += 15
    elif g_stop_pct > 6.0:
        g_score -= (g_stop_pct - 6) * 3

    if s_stop_pct and 1.0 <= s_stop_pct <= 6.0:
        s_score += 15
    elif s_stop_pct and s_stop_pct > 6.0:
        s_score -= (s_stop_pct - 6) * 3

    # Strategy win rate + EV
    s_wr = sm.get("profitable_rate", 0)
    s_ev = sm.get("ev", 0)
    if s_wr > 0.55:
        s_score += (s_wr - 0.5) * 100
    if s_ev > 3:
        s_score += min(s_ev, 15) * 3

    # Sample size
    s_n = sm.get("sample_size", 0)
    if s_n >= 50:
        s_score += 10
    elif s_n >= 20:
        s_score += 5

    # --- Pick best ---
    if s_score > g_score and s_rr and s_rr > 0 and s_stop > 0:
        return {
            "source": "strategy",
            "entry": round(s_entry, 3),
            "stop": round(s_stop, 3),
            "target1": round(s_t1, 3),
            "target2": round(s_t2, 3) if s_t2 else None,
            "rr": s_rr,
            "stop_pct": round(s_stop_pct, 1),
        }
    elif g_rr and g_rr > 0 and g_stop > 0:
        return {
            "source": "golden",
            "entry": round(g_entry, 3),
            "stop": round(g_stop, 3),
            "target1": round(g_t1, 3),
            "target2": round(g_t2, 3) if g_t2 else None,
            "rr": g_rr,
            "stop_pct": round(g_stop_pct, 1),
        }
    else:
        return None


def final_trade_decision(opp):
    """
    Single ENTER / WAIT / SKIP decision per stock,
    using all available data.
    """
    plan = choose_best_plan(opp)
    price = float(opp.get("price", 0))
    sm = opp.get("strategy_match") or {}

    if plan is None:
        return {
            "action": "SKIP",
            "action_ar": "\u23ed\ufe0f \u062a\u062c\u0627\u0648\u0632",
            "reason_ar": "\u0643\u0644\u0627 \u0627\u0644\u062e\u0637\u062a\u064a\u0646 \u0641\u064a\u0647\u0645 \u0645\u0634\u0627\u0643\u0644",
            "chosen_plan": None,
        }

    rr = plan["rr"]
    stop_pct = plan["stop_pct"]

    win_rate = sm.get("profitable_rate", 0)
    ev = sm.get("ev", 0)
    pattern_confidence = opp.get("confidence", 0)

    # Is price in entry zone? (within 0.3%)
    in_zone = price > 0 and (plan["entry"] * 0.997 <= price <= plan["entry"] * 1.003)

    # === Decision rules ===

    # ENTER: strong R/R + in zone
    if (rr >= 1.5
            and stop_pct <= 6.0
            and (win_rate >= 0.55 or ev >= 3.0 or pattern_confidence >= 85)
            and in_zone):
        return {
            "action": "ENTER",
            "action_ar": "\U0001f7e2 \u0627\u062f\u062e\u0644",
            "reason_ar": f"\u0627\u0644\u0639\u0627\u0626\u062f/\u0627\u0644\u0645\u062e\u0627\u0637\u0631\u0629 {rr:.1f}x \u0645\u0645\u062a\u0627\u0632\u060c \u0627\u0644\u0633\u0639\u0631 \u0628\u0645\u0646\u0637\u0642\u0629 \u0627\u0644\u062f\u062e\u0648\u0644",
            "chosen_plan": plan,
        }

    # ENTER cautious: high WR compensates moderate R/R
    if (rr >= 1.3
            and stop_pct <= 6.0
            and win_rate >= 0.60
            and ev >= 5.0
            and in_zone):
        return {
            "action": "ENTER",
            "action_ar": "\U0001f7e2 \u0627\u062f\u062e\u0644 \u0628\u062d\u0630\u0631",
            "reason_ar": f"\u0646\u0633\u0628\u0629 \u0627\u0644\u0646\u062c\u0627\u062d \u0639\u0627\u0644\u064a\u0629 ({win_rate:.0%}) \u062a\u0639\u0648\u0636 \u0627\u0644\u0639\u0627\u0626\u062f/\u0627\u0644\u0645\u062e\u0627\u0637\u0631\u0629 ({rr:.1f}x)",
            "chosen_plan": plan,
        }

    # WAIT: good plan but price not there yet
    if (rr >= 1.3
            and (win_rate >= 0.55 or ev >= 3.0)
            and not in_zone):
        trigger = round(plan["entry"], 3)
        return {
            "action": "WAIT",
            "action_ar": "\u23f3 \u0627\u0646\u062a\u0638\u0631",
            "reason_ar": f"\u0627\u0644\u0646\u0645\u0637 \u062d\u0644\u0648 \u2014 \u0627\u0646\u062a\u0638\u0631 \u0627\u0644\u0633\u0639\u0631 \u064a\u0648\u0635\u0644 {trigger}",
            "chosen_plan": plan,
        }

    # WAIT: acceptable R/R, needs confirmation
    if (rr >= 1.2
            and (win_rate >= 0.55 or ev >= 3.0)):
        return {
            "action": "WAIT",
            "action_ar": "\u23f3 \u0627\u0646\u062a\u0638\u0631 \u062a\u0623\u0643\u064a\u062f",
            "reason_ar": f"\u0627\u0644\u0646\u0645\u0637 \u062c\u064a\u062f \u0628\u0633 \u0627\u0644\u0639\u0627\u0626\u062f/\u0627\u0644\u0645\u062e\u0627\u0637\u0631\u0629 {rr:.1f}x \u064a\u062d\u062a\u0627\u062c \u062a\u0623\u0643\u064a\u062f",
            "chosen_plan": plan,
        }

    # SKIP: weak everything
    reason = f"\u0627\u0644\u0639\u0627\u0626\u062f/\u0627\u0644\u0645\u062e\u0627\u0637\u0631\u0629 {rr:.1f}x \u0636\u0639\u064a\u0641"
    if stop_pct > 6:
        reason += f" \u0648\u0627\u0644\u0633\u062a\u0648\u0628 \u0628\u0639\u064a\u062f ({stop_pct:.0f}%)"
    return {
        "action": "SKIP",
        "action_ar": "\u23ed\ufe0f \u062a\u062c\u0627\u0648\u0632",
        "reason_ar": reason,
        "chosen_plan": plan,
    }


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
# STRATEGY MINING — LIVE MATCHING
# ═══════════════════════════════════

def build_mining_atoms(live: dict) -> set:
    """
    Build atoms using the SAME discretisation as Phase 2 mining.
    These atoms must match the ones stored in mined_strategies.pattern_atoms.
    """
    atoms = set()

    # RSI (5 bins — matches mining)
    rsi = live.get("rsi_14") or live.get("rsi")
    if rsi is not None:
        rsi = float(rsi)
        if rsi < 30:      atoms.add("rsi_lt_30")
        elif rsi < 45:    atoms.add("rsi_30_45")
        elif rsi < 55:    atoms.add("rsi_45_55")
        elif rsi < 70:    atoms.add("rsi_55_70")
        else:             atoms.add("rsi_gt_70")

    # MACD state
    macd_state = str(live.get("macd_state") or live.get("macd_cross") or "").lower()
    if "bullish" in macd_state:  atoms.add("macd_bullish")
    elif "bearish" in macd_state: atoms.add("macd_bearish")

    # MACD momentum
    macd_mom = str(live.get("macd_momentum") or "").lower()
    if "accel" in macd_mom:   atoms.add("macd_accel")
    elif "decel" in macd_mom: atoms.add("macd_decel")

    # EMA state
    ema_state = str(live.get("ema_state") or live.get("daily_ema_cross") or "").lower()
    if "bullish" in ema_state:  atoms.add("ema_bullish")
    elif "bearish" in ema_state: atoms.add("ema_bearish")

    # ADX (5 bins)
    adx = live.get("adx")
    if adx is not None:
        adx = float(adx)
        if adx < 15:      atoms.add("adx_lt_15")
        elif adx < 20:    atoms.add("adx_15_20")
        elif adx < 25:    atoms.add("adx_20_25")
        elif adx <= 35:   atoms.add("adx_25_35")
        else:             atoms.add("adx_gt_35")

    # Stochastic (5 bins)
    stoch = live.get("stoch_k")
    if stoch is not None:
        stoch = float(stoch)
        if stoch < 20:    atoms.add("stoch_lt_20")
        elif stoch < 40:  atoms.add("stoch_20_40")
        elif stoch < 60:  atoms.add("stoch_40_60")
        elif stoch < 80:  atoms.add("stoch_60_80")
        else:             atoms.add("stoch_gt_80")

    # Volume ratio (4 bins)
    vol = live.get("vol_ratio")
    if vol is not None:
        vol = float(vol)
        if vol < 0.8:     atoms.add("vol_lt_0_8")
        elif vol < 1.2:   atoms.add("vol_0_8_1_2")
        elif vol < 2.0:   atoms.add("vol_1_2_2_0")
        else:             atoms.add("vol_ge_2")

    # ATR % (3 bins)
    atr = live.get("atr_14") or live.get("atr")
    price = live.get("price")
    if atr and price:
        atr, price = float(atr), float(price)
        if price > 0:
            atr_pct = atr / price * 100
            if atr_pct < 1.5:   atoms.add("low_atr")
            elif atr_pct < 3.0: atoms.add("medium_atr")
            else:               atoms.add("high_atr")

    # BB Squeeze
    if live.get("bb_squeeze"):
        atoms.add("bb_squeeze")

    # Trend direction (from regime classifier)
    # ADX + directional votes → trend_up / trend_down
    adx_val = float(live.get("adx") or 0)
    bull_votes = sum([
        1 if "bullish" in str(live.get("ema_state") or live.get("daily_ema_cross") or "").lower() else 0,
        1 if "bullish" in str(live.get("macd_state") or live.get("macd_cross") or "").lower() else 0,
        1 if "accel" in str(live.get("macd_momentum") or "").lower() else 0,
    ])
    bear_votes = sum([
        1 if "bearish" in str(live.get("ema_state") or live.get("daily_ema_cross") or "").lower() else 0,
        1 if "bearish" in str(live.get("macd_state") or live.get("macd_cross") or "").lower() else 0,
        1 if "decel" in str(live.get("macd_momentum") or "").lower() else 0,
    ])
    if adx_val >= 23:
        if bull_votes >= 2:   atoms.add("trend_up")
        elif bear_votes >= 2: atoms.add("trend_down")

    return atoms


def classify_live_regime(live: dict) -> str:
    """Classify regime from live data — same logic as Phase 2.5."""
    adx = float(live.get("adx") or 0)
    if adx >= 23:
        return "trending"
    elif adx <= 18:
        return "ranging"
    else:
        return "transition"


def match_strategies(live: dict, timeframe: str = "1D", top_n: int = 5) -> list:
    """
    Match live signal against mined strategies.

    Args:
        live: dict with keys rsi_14/rsi, adx, stoch_k, vol_ratio, atr_14/atr,
              macd_state, macd_momentum, ema_state, bb_squeeze, price
        timeframe: '1D' or '30m'
        top_n: max strategies to return

    Returns:
        list of matched strategies sorted by final_score, each with:
        - strategy_id, pattern_ar, ev, target, stop, rr, confidence info
    """
    live_atoms = build_mining_atoms(live)
    regime = classify_live_regime(live)

    if not live_atoms:
        return []

    conn = _conn()
    try:
        rows = conn.execute("""
            SELECT * FROM mined_strategies
            WHERE timeframe = ? AND regime = ?
              AND status IN ('production', 'candidate')
            ORDER BY final_score DESC
        """, (timeframe, regime)).fetchall()
    except Exception as e:
        logger.warning("match_strategies query failed: %s", e)
        return []
    finally:
        conn.close()

    matches = []
    for row in rows:
        try:
            pattern_atoms = set(json.loads(row["pattern_atoms"]))
        except Exception:
            continue

        if not pattern_atoms.issubset(live_atoms):
            continue

        price = float(live.get("price") or 0)
        entry_disc = float(row["entry_discount_pct"] or 0)
        target_1 = float(row["target_1_pct"] or 3)
        target_2 = float(row["target_2_pct"] or 5)
        stop_val = float(row["stop_pct"] or -3)

        entry_price = round(price * (1 + entry_disc / 100), 3) if price > 0 else None
        target_1_price = round(price * (1 + target_1 / 100), 3) if price > 0 else None
        target_2_price = round(price * (1 + target_2 / 100), 3) if price > 0 else None
        stop_price = round(price * (1 + stop_val / 100), 3) if price > 0 else None

        matches.append({
            "strategy_id": row["strategy_id"],
            "pattern_ar": row["pattern_ar"],
            "pattern_atoms": row["pattern_atoms"],
            "timeframe": timeframe,
            "regime": regime,
            "final_score": float(row["final_score"] or 0),
            "ev": float(row["ev"] or 0),
            "profitable_rate": float(row["profitable_rate"] or 0),
            "profit_factor": float(row["profit_factor"] or 0),
            "sample_size": int(row["sample_size"] or 0),
            "stability": float(row["stability"] or 0),
            "p_value": float(row["p_value"] or 1),
            # Trade plan — percentages
            "entry_method": row["entry_method"],
            "target_1_pct": target_1,
            "target_2_pct": target_2,
            "stop_pct": stop_val,
            "rr_ratio": float(row["rr_ratio"] or 0),
            "est_hold_days": float(row["est_hold_days"] or 3),
            # Trade plan — absolute prices
            "entry_price": entry_price,
            "target_1_price": target_1_price,
            "target_2_price": target_2_price,
            "stop_price": stop_price,
            "current_price": price,
        })

    matches.sort(key=lambda x: x["final_score"], reverse=True)
    return matches[:top_n]


# ═══════════════════════════════════
# TELEGRAM ALERTS
# ═══════════════════════════════════

def _read_file(path):
    try:
        p = os.path.expanduser(path)
        with open(p) as f:
            return f.read().strip()
    except Exception:
        return None


def _init_alert_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            pattern_key TEXT,
            entry_status TEXT,
            confidence REAL,
            dedup_key TEXT UNIQUE,
            sent_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def should_alert(conn, opp: dict) -> bool:
    """Return True if this opportunity should trigger a Telegram alert."""
    status = opp.get("entry_status", "")
    if status not in ("enter_now", "wait_pullback"):
        return False
    if opp.get("confidence", 0) < 75:
        return False
    dedup = f"{opp['symbol']}:{opp.get('pattern_atoms', '')}:{status}"
    row = conn.execute("SELECT id FROM alert_history WHERE dedup_key=?", (dedup,)).fetchone()
    return row is None


def record_alert(conn, opp: dict):
    """Record a sent alert to prevent duplicates."""
    dedup = f"{opp['symbol']}:{opp.get('pattern_atoms', '')}:{opp.get('entry_status', '')}"
    conn.execute(
        "INSERT OR IGNORE INTO alert_history (symbol, pattern_key, entry_status, confidence, dedup_key) VALUES (?,?,?,?,?)",
        (opp["symbol"], opp.get("pattern_atoms"), opp.get("entry_status"), opp.get("confidence"), dedup)
    )
    conn.commit()


def send_golden_alert(opp: dict) -> bool:
    """Send a Telegram alert for a golden opportunity."""
    import requests as _req
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN") or _read_file("~/.telegram_bot_token")
    chat_id   = os.environ.get("TELEGRAM_CHAT_ID")   or _read_file("~/.telegram_chat_id")
    if not bot_token or not chat_id:
        return False

    tp = opp.get("trade_plan") or {}

    text = (
        f"🚨 <b>فرصة ذهبية — {opp['symbol']}</b>\n\n"
        f"📊 <b>النمط:</b> {opp.get('pattern_ar', '')}\n"
        f"✅ <b>نسبة نجاح:</b> {opp.get('win_rate', 0):.0f}% ({opp.get('occurrences', 0)} مرة)\n"
        f"{opp.get('entry_status_ar', '')}\n\n"
        f"💰 <b>السعر:</b> {opp.get('price', 0)}\n"
        f"🎯 <b>منطقة الدخول:</b> {tp.get('entry_zone_low', '')} - {tp.get('entry_zone_high', '')}\n"
        f"🛑 <b>وقف:</b> {tp.get('stop_loss', '')} ({tp.get('stop_distance_pct', '')}%)\n"
        f"🏁 <b>هدف 1:</b> {tp.get('target_1', '')}\n"
        f"🏁 <b>هدف 2:</b> {tp.get('target_2', '')}\n"
        f"⚖️ <b>R/R:</b> {tp.get('rr_ratio', 0)}x\n\n"
    )
    reasons = opp.get("reasoning_ar", [])
    if reasons:
        text += "<b>السبب:</b>\n"
        text += "\n".join(f"- {r}" for r in reasons[:4])

    try:
        r = _req.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"Telegram alert failed: {e}")
        return False


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
    Returns ranked opportunities enriched with S/R, entry decisions, and trade plans.
    """
    from trading_decision_engine import compute_entry_status

    conn = _conn()
    _init_alert_table(conn)

    # Load profiles (includes sr_json from sr_engine)
    profiles = {}
    for r in conn.execute("SELECT * FROM stock_profiles").fetchall():
        profiles[r["symbol"]] = dict(r)

    # Load qualifying patterns
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

        live_atoms   = build_live_atoms(live)
        profile      = profiles.get(sym, {"baseline_win_rate": 0.3})
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
                "symbol":          sym,
                "name_ar":         profile.get("name_ar") or "",
                "personality_ar":  profile.get("personality_ar") or "",
                "opportunity_type": opp_type,
                "confidence":      confidence,
                "price":           float(live.get("price") or 0),
                "change_pct":      float(live.get("change_pct") or 0),
                "pattern_ar":      atoms_to_ar(pat.get("pattern_atoms", "")),
                "pattern_atoms":   pat.get("pattern_atoms", ""),
                "matched_atoms":   ",".join(matched),
                "missing_atoms":   ",".join(missing),
                "match_ratio":     round(ratio, 2),
                "occurrences":     pat.get("occurrences", 0),
                "hits":            pat.get("hits", 0),
                "win_rate":        round(float(pat.get("win_rate", 0)) * 100, 1),
                "avg_gain_pct":    round(float(pat.get("avg_gain_pct", 0)), 1),
                "pattern_score":   pat.get("pattern_score", 0),
                "current_rsi":     float(live.get("rsi_14") or live.get("rsi") or 0),
                "current_vol":     float(live.get("vol_ratio") or 0),
                "current_adx":     float(live.get("adx") or 0),
                "current_stoch":   float(live.get("stoch_k") or 0),
                "live_atoms":      sorted(list(live_atoms)),
                "stop_loss":       suggest_stop(live),
                "dominant_driver": profile.get("dominant_driver", ""),
                "baseline_wr":     round(float(profile.get("baseline_win_rate", 0)) * 100, 1),
            }

            if best_opp is None or confidence > best_opp["confidence"]:
                best_opp = opp

        if best_opp:
            # ── Phase 3: Enrich with S/R from profile ──────────
            sr_json = profile.get("sr_json")
            if sr_json:
                try:
                    sr_data = json.loads(sr_json) if isinstance(sr_json, str) else sr_json
                    best_opp["key_support"]          = sr_data.get("key_support")
                    best_opp["key_resistance"]        = sr_data.get("key_resistance")
                    best_opp["support_levels"]        = sr_data.get("support_levels", [])
                    best_opp["resistance_levels"]     = sr_data.get("resistance_levels", [])
                    best_opp["support_touches"]       = sr_data.get("key_support_touches", 0)
                    best_opp["resistance_touches"]    = sr_data.get("key_resistance_touches", 0)
                except Exception:
                    pass

            # Fallback: use live data S/R
            if not best_opp.get("key_support"):
                best_opp["key_support"]    = float(live.get("support") or 0) or None
            if not best_opp.get("key_resistance"):
                best_opp["key_resistance"] = float(live.get("resistance") or 0) or None

            # Also attach atr for decision engine
            best_opp["atr_14"] = float(live.get("atr_14") or live.get("atr") or 0)

            # ── Phase 3: Compute entry decision + trade plan ────
            decision = compute_entry_status(best_opp, profile)
            best_opp["entry_status"]    = decision["entry_status"]
            best_opp["entry_status_ar"] = decision["entry_status_ar"]
            best_opp["entry_score"]     = decision["entry_score"]
            best_opp["reasoning_ar"]    = decision["reasoning_ar"]
            best_opp["trade_plan"]      = decision["trade_plan"]

            # ── Phase 8: Match mined strategies ────────────────
            try:
                strat_matches = match_strategies(live, timeframe="1D", top_n=3)
                if strat_matches:
                    best_strat = strat_matches[0]
                    best_opp["strategy_match"] = {
                        "strategy_id": best_strat.get("strategy_id", ""),
                        "pattern_ar": best_strat.get("pattern_ar", ""),
                        "ev": best_strat.get("ev", 0),
                        "profitable_rate": best_strat.get("profitable_rate", 0),
                        "profit_factor": best_strat.get("profit_factor", 0),
                        "final_score": best_strat.get("final_score", 0),
                        "sample_size": best_strat.get("sample_size", 0),
                        "stability": best_strat.get("stability", 0),
                        "total_matches": len(strat_matches),
                        "target_1_pct": best_strat.get("target_1_pct", 0),
                        "target_2_pct": best_strat.get("target_2_pct", 0),
                        "stop_pct": best_strat.get("stop_pct", 0),
                        "rr_ratio": best_strat.get("rr_ratio", 0),
                        "est_hold_days": best_strat.get("est_hold_days", 0),
                        "entry_price": best_strat.get("entry_price"),
                        "target_1_price": best_strat.get("target_1_price"),
                        "target_2_price": best_strat.get("target_2_price"),
                        "stop_price": best_strat.get("stop_price"),
                    }
                    # Boost confidence if strong strategy match
                    strat_ev = best_strat.get("ev", 0)
                    strat_boost = min(strat_ev * 0.25, 5)  # max +5
                    best_opp["confidence"] = min(
                        best_opp["confidence"] + strat_boost, 99.9
                    )
                else:
                    best_opp["strategy_match"] = None
            except Exception as e:
                logger.warning("Strategy match error for %s: %s", sym, e)
                best_opp["strategy_match"] = None

            # ── Phase 9: Smart Trade Decision ────────────────
            try:
                ftd = final_trade_decision(best_opp)
                best_opp["smart_decision"]    = ftd["action"]
                best_opp["smart_decision_ar"] = ftd["action_ar"]
                best_opp["smart_reason_ar"]   = ftd["reason_ar"]
                best_opp["chosen_plan"]       = ftd["chosen_plan"]

                # Override opportunity_type with smart decision
                if ftd["action"] == "ENTER":
                    best_opp["opportunity_type"] = "\U0001f7e2 \u0627\u062f\u062e\u0644"
                elif ftd["action"] == "WAIT":
                    best_opp["opportunity_type"] = "\u23f3 \u0627\u0646\u062a\u0638\u0631"
                elif ftd["action"] == "SKIP":
                    best_opp["opportunity_type"] = "\u23ed\ufe0f \u062a\u062c\u0627\u0648\u0632"

                # Cap confidence based on decision quality
                if ftd["action"] == "SKIP":
                    best_opp["confidence"] = min(best_opp["confidence"], 60)
                elif ftd["action"] == "WAIT":
                    best_opp["confidence"] = min(best_opp["confidence"], 80)
            except Exception as e:
                logger.warning("Smart decision error for %s: %s", sym, e)

            all_opportunities.append(best_opp)

    # Sort: ENTER first, then WAIT, then SKIP; within each group by confidence
    action_priority = {"ENTER": 0, "WAIT": 1, "SKIP": 2}
    all_opportunities.sort(
        key=lambda x: (
            action_priority.get(x.get("smart_decision", "SKIP"), 2),
            -x.get("confidence", 0),
        )
    )
    for i, opp in enumerate(all_opportunities):
        opp["rank"] = i + 1

    # ── Phase 4: Telegram alerts for new "enter_now" opps ───────
    alert_conn = _conn()
    _init_alert_table(alert_conn)
    alerts_sent = 0
    for opp in all_opportunities:
        if opp.get("entry_status") == "enter_now" and opp.get("confidence", 0) >= 80:
            if should_alert(alert_conn, opp):
                if send_golden_alert(opp):
                    record_alert(alert_conn, opp)
                    alerts_sent += 1
    alert_conn.close()

    enter_list = [o for o in all_opportunities if o.get("smart_decision") == "ENTER"]
    wait_list  = [o for o in all_opportunities if o.get("smart_decision") == "WAIT"]
    skip_list  = [o for o in all_opportunities if o.get("smart_decision") == "SKIP"]

    return {
        "generated_at":        datetime.utcnow().isoformat(),
        "total_scanned":       len(live_data),
        "total_opportunities": len(all_opportunities),
        "enter_count":         len(enter_list),
        "wait_count":          len(wait_list),
        "skip_count":          len(skip_list),
        "alerts_sent":         alerts_sent,
        # backward compatible
        "golden_count":        len(enter_list),
        "candidate_count":     len(wait_list),
        "watch_count":         len(skip_list),
        "top_10":              all_opportunities[:10],
        "all_opportunities":   all_opportunities,
    }
