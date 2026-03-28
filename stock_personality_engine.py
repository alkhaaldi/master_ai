"""
stock_personality_engine.py — Stock Personality & Pattern Memory Engine.
Analyzes 66K+ historical signals to extract per-stock profiles,
winning patterns, and auto-generated Arabic notes.

Tables created:
  stock_profiles         — per-symbol personality (drivers, speed, move size)
  symbol_patterns        — pattern combinations + stats
  symbol_notes           — auto-generated Arabic insights

Run: python3 stock_personality_engine.py
Schedule: daily after market close or after brain backfill
"""
import os
import json
import sqlite3
import logging
from datetime import datetime
from itertools import combinations

logger = logging.getLogger("personality_engine")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")


# ═══════════════════════════════════════════════════
# SCHEMA
# ═══════════════════════════════════════════════════

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stock_profiles (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL DEFAULT '1D',
    signals_count INTEGER DEFAULT 0,
    hits INTEGER DEFAULT 0,
    misses INTEGER DEFAULT 0,
    baseline_win_rate REAL DEFAULT 0,
    avg_outcome_pct REAL,
    avg_max_gain_pct REAL,
    avg_max_loss_pct REAL,
    median_max_gain_pct REAL,
    reward_risk_ratio REAL,
    rsi_lift REAL,
    rsi_samples INTEGER DEFAULT 0,
    macd_lift REAL,
    macd_samples INTEGER DEFAULT 0,
    ema_lift REAL,
    ema_samples INTEGER DEFAULT 0,
    vol_lift REAL,
    vol_samples INTEGER DEFAULT 0,
    adx_lift REAL,
    adx_samples INTEGER DEFAULT 0,
    stoch_lift REAL,
    stoch_samples INTEGER DEFAULT 0,
    squeeze_lift REAL,
    squeeze_samples INTEGER DEFAULT 0,
    support_lift REAL,
    support_samples INTEGER DEFAULT 0,
    resistance_lift REAL,
    resistance_samples INTEGER DEFAULT 0,
    breakout_lift REAL,
    breakout_samples INTEGER DEFAULT 0,
    breakdown_lift REAL,
    breakdown_samples INTEGER DEFAULT 0,
    high_atr_lift REAL,
    high_atr_samples INTEGER DEFAULT 0,
    low_atr_lift REAL,
    low_atr_samples INTEGER DEFAULT 0,
    better_timeframe TEXT,
    tf_1d_win_rate REAL,
    tf_30m_win_rate REAL,
    tf_1d_signals INTEGER DEFAULT 0,
    tf_30m_signals INTEGER DEFAULT 0,
    key_support REAL,
    key_resistance REAL,
    dominant_driver TEXT,
    secondary_driver TEXT,
    personality_tags TEXT,
    personality_ar TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, timeframe)
);

CREATE TABLE IF NOT EXISTS symbol_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL DEFAULT '1D',
    pattern_key TEXT NOT NULL,
    pattern_atoms TEXT NOT NULL,
    pattern_ar TEXT,
    combo_size INTEGER DEFAULT 1,
    occurrences INTEGER DEFAULT 0,
    hits INTEGER DEFAULT 0,
    misses INTEGER DEFAULT 0,
    expired INTEGER DEFAULT 0,
    win_rate REAL DEFAULT 0,
    avg_gain_pct REAL,
    avg_loss_pct REAL,
    avg_outcome_pct REAL,
    pattern_score REAL DEFAULT 0,
    last_seen TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, timeframe, pattern_key)
);

CREATE TABLE IF NOT EXISTS symbol_notes (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL DEFAULT '1D',
    note_type TEXT NOT NULL DEFAULT 'auto',
    notes_ar TEXT,
    notes_en TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, timeframe, note_type)
);

CREATE INDEX IF NOT EXISTS idx_sp_symbol ON symbol_patterns(symbol);
CREATE INDEX IF NOT EXISTS idx_sp_score ON symbol_patterns(pattern_score);
CREATE INDEX IF NOT EXISTS idx_sn_symbol ON symbol_notes(symbol);
"""


# ═══════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════

def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c

def init_personality_schema():
    conn = _conn()
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    logger.info("Personality engine schema ready")

def _bayesian_rate(hits, total, alpha=5, beta=5):
    return (hits + alpha) / (total + alpha + beta)


# ═══════════════════════════════════════════════════
# S/R HELPER FUNCTIONS (defined before PATTERN_ATOMS)
# ═══════════════════════════════════════════════════

def _is_near_support(r):
    """Price within 3% of support level."""
    price = r.get("price_at_signal") or 0
    support = r.get("support") or 0
    if not price or not support or support <= 0:
        return False
    return 0 <= (price - support) / support <= 0.03

def _is_near_resistance(r):
    """Price within 3% below resistance level."""
    price = r.get("price_at_signal") or 0
    resistance = r.get("resistance") or 0
    if not price or not resistance or resistance <= 0:
        return False
    return 0 <= (resistance - price) / resistance <= 0.03

def _is_above_resistance(r):
    """Price broke above resistance."""
    price = r.get("price_at_signal") or 0
    resistance = r.get("resistance") or 0
    if not price or not resistance or resistance <= 0:
        return False
    return price > resistance

def _is_below_support(r):
    """Price broke below support."""
    price = r.get("price_at_signal") or 0
    support = r.get("support") or 0
    if not price or not support or support <= 0:
        return False
    return price < support

def _is_high_atr(r):
    """ATR is high relative to price (>3%)."""
    atr = r.get("atr_14") or 0
    price = r.get("price_at_signal") or 1
    return (atr / price) > 0.03 if price > 0 else False

def _is_low_atr(r):
    """ATR is low relative to price (<1.5%)."""
    atr = r.get("atr_14") or 0
    price = r.get("price_at_signal") or 1
    return (atr / price) < 0.015 if price > 0 else False


# ═══════════════════════════════════════════════════
# PATTERN ATOMS — الشروط الأساسية
# ═══════════════════════════════════════════════════

PATTERN_ATOMS = [
    # === RSI ===
    ("rsi_lt_30",        lambda r: (r.get("rsi_14") or 99) < 30,           "RSI < 30 (تشبع بيعي)"),
    ("rsi_30_45",        lambda r: 30 <= (r.get("rsi_14") or 0) < 45,      "RSI 30-45"),
    ("rsi_gt_70",        lambda r: (r.get("rsi_14") or 0) > 70,            "RSI > 70 (تشبع شرائي)"),
    # === MACD ===
    ("macd_bullish",     lambda r: str(r.get("macd_state") or "").lower() == "bullish", "MACD صاعد"),
    ("macd_bearish",     lambda r: str(r.get("macd_state") or "").lower() == "bearish", "MACD هابط"),
    # === EMA ===
    ("ema_bullish",      lambda r: str(r.get("ema_state") or "").lower() == "bullish",  "EMA صاعد"),
    ("ema_bearish",      lambda r: str(r.get("ema_state") or "").lower() == "bearish",  "EMA هابط"),
    # === ADX / Regime ===
    ("adx_ge_25",        lambda r: (r.get("adx") or 0) >= 25,              "ADX ≥ 25 (اتجاهي)"),
    ("adx_lt_20",        lambda r: (r.get("adx") or 99) < 20,              "ADX < 20 (عرضي)"),
    # === Volume ===
    ("vol_ge_1_5",       lambda r: (r.get("vol_ratio") or 0) >= 1.5,       "حجم ≥ 1.5x"),
    ("vol_ge_2",         lambda r: (r.get("vol_ratio") or 0) >= 2.0,       "حجم ≥ 2x"),
    # === Stochastic ===
    ("stoch_lt_20",      lambda r: (r.get("stoch_k") or 99) < 20,          "Stoch < 20"),
    ("stoch_gt_80",      lambda r: (r.get("stoch_k") or 0) > 80,           "Stoch > 80"),
    # === Bollinger ===
    ("bb_squeeze",       lambda r: bool(r.get("bb_squeeze")),               "BB ضغط"),
    # === Confluence ===
    ("confluence_ge_70", lambda r: (r.get("confluence_score") or 0) >= 70, "Confluence ≥ 70"),
    # === Support / Resistance proximity ===
    ("near_support",     _is_near_support,                                  "قرب الدعم"),
    ("near_resistance",  _is_near_resistance,                               "قرب المقاومة"),
    ("above_resistance", _is_above_resistance,                              "اختراق مقاومة"),
    ("below_support",    _is_below_support,                                 "كسر دعم"),
    # === ATR / Volatility ===
    ("high_atr",         _is_high_atr,                                      "تذبذب عالي"),
    ("low_atr",          _is_low_atr,                                       "تذبذب منخفض"),
]

ATOM_AR = {a[0]: a[2] for a in PATTERN_ATOMS}


# ═══════════════════════════════════════════════════
# 1. STOCK PROFILE — شخصية كل سهم
# ═══════════════════════════════════════════════════

def _calc_lift(rows, condition_fn, baseline_wr):
    """Calculate lift: how much does this condition improve win rate?"""
    matching = [r for r in rows if condition_fn(r)]
    n = len(matching)
    if n < 3 or baseline_wr <= 0:
        return None, n
    hits = sum(1 for r in matching if r["outcome"] == "hit")
    cond_wr = _bayesian_rate(hits, n)
    lift = round(cond_wr / baseline_wr, 3) if baseline_wr > 0 else None
    return lift, n


def build_stock_profile(symbol, rows):
    """Build personality profile for one symbol from its signal history."""
    if not rows:
        return None

    total = len(rows)
    hits = sum(1 for r in rows if r["outcome"] == "hit")
    misses = sum(1 for r in rows if r["outcome"] == "miss")
    baseline_wr = _bayesian_rate(hits, total)

    hit_rows = [r for r in rows if r["outcome"] == "hit"]
    gains = [r["max_gain_pct"] for r in rows if r.get("max_gain_pct") is not None]
    losses = [r["max_loss_pct"] for r in rows if r.get("max_loss_pct") is not None]
    outcomes = [r["outcome_pct"] for r in rows if r.get("outcome_pct") is not None]

    avg_gain = round(sum(gains) / len(gains), 3) if gains else None
    avg_loss = round(sum(losses) / len(losses), 3) if losses else None
    avg_outcome = round(sum(outcomes) / len(outcomes), 3) if outcomes else None

    sorted_gains = sorted(gains)
    median_gain = sorted_gains[len(sorted_gains) // 2] if sorted_gains else None
    rr_ratio = round(abs(avg_gain / avg_loss), 2) if avg_gain and avg_loss and avg_loss != 0 else None

    # Lift per indicator
    rsi_lift, rsi_n       = _calc_lift(rows, lambda r: (r.get("rsi_14") or 99) < 30, baseline_wr)
    macd_lift, macd_n     = _calc_lift(rows, lambda r: str(r.get("macd_state") or "").lower() == "bullish", baseline_wr)
    ema_lift, ema_n       = _calc_lift(rows, lambda r: str(r.get("ema_state") or "").lower() == "bullish", baseline_wr)
    vol_lift, vol_n       = _calc_lift(rows, lambda r: (r.get("vol_ratio") or 0) >= 2.0, baseline_wr)
    adx_lift, adx_n       = _calc_lift(rows, lambda r: (r.get("adx") or 0) >= 25, baseline_wr)
    stoch_lift, stoch_n   = _calc_lift(rows, lambda r: (r.get("stoch_k") or 99) < 20, baseline_wr)
    sq_lift, sq_n         = _calc_lift(rows, lambda r: bool(r.get("bb_squeeze")), baseline_wr)
    sup_lift, sup_n       = _calc_lift(rows, _is_near_support, baseline_wr)
    res_lift, res_n       = _calc_lift(rows, _is_near_resistance, baseline_wr)
    breakout_lift, breakout_n   = _calc_lift(rows, _is_above_resistance, baseline_wr)
    breakdown_lift, breakdown_n = _calc_lift(rows, _is_below_support, baseline_wr)
    high_atr_lift, high_atr_n   = _calc_lift(rows, _is_high_atr, baseline_wr)
    low_atr_lift, low_atr_n     = _calc_lift(rows, _is_low_atr, baseline_wr)

    # Timeframe analysis
    src_1d  = [r for r in rows if "1d" in str(r.get("source") or "").lower() or "1D" in str(r.get("source") or "")]
    src_30m = [r for r in rows if "30m" in str(r.get("source") or "").lower()]
    tf_1d_wr  = _bayesian_rate(sum(1 for r in src_1d  if r["outcome"] == "hit"), len(src_1d))  if src_1d  else None
    tf_30m_wr = _bayesian_rate(sum(1 for r in src_30m if r["outcome"] == "hit"), len(src_30m)) if src_30m else None
    if tf_1d_wr and tf_30m_wr:
        better_tf = "1D" if tf_1d_wr > tf_30m_wr else "30m"
    elif tf_1d_wr:
        better_tf = "1D"
    elif tf_30m_wr:
        better_tf = "30m"
    else:
        better_tf = None

    # Key price levels from successful signals
    hit_supports    = [r["support"]    for r in hit_rows if r.get("support")    and r["support"] > 0]
    hit_resistances = [r["resistance"] for r in hit_rows if r.get("resistance") and r["resistance"] > 0]
    key_support    = round(sum(hit_supports) / len(hit_supports), 3)       if hit_supports    else None
    key_resistance = round(sum(hit_resistances) / len(hit_resistances), 3) if hit_resistances else None

    # Dominant driver
    lifts = {
        "Volume": (vol_lift, vol_n), "MACD": (macd_lift, macd_n),
        "EMA": (ema_lift, ema_n),    "RSI":  (rsi_lift, rsi_n),
        "ADX": (adx_lift, adx_n),   "Stochastic": (stoch_lift, stoch_n),
    }
    valid_lifts = {k: v[0] for k, v in lifts.items() if v[0] is not None and v[1] >= 5}
    sorted_drivers = sorted(valid_lifts.items(), key=lambda x: x[1], reverse=True)
    dominant  = sorted_drivers[0][0] if sorted_drivers else None
    secondary = sorted_drivers[1][0] if len(sorted_drivers) > 1 else None

    # Personality tags
    tags, tags_ar = [], []
    if rsi_lift  and rsi_lift  >= 1.15: tags.append("mean_reversion");  tags_ar.append("ارتداد من تشبع")
    if macd_lift and macd_lift >= 1.15: tags.append("momentum");         tags_ar.append("زخم")
    if vol_lift  and vol_lift  >= 1.15: tags.append("volume_driven");    tags_ar.append("يعتمد على الحجم")
    if ema_lift  and ema_lift  >= 1.15: tags.append("trend_follower");   tags_ar.append("يتبع الاتجاه")
    if avg_gain  and avg_gain  >= 5:    tags.append("explosive");        tags_ar.append("انفجاري")
    elif avg_gain and avg_gain <= 2:    tags.append("slow_grinder");     tags_ar.append("بطيء الحركة")

    return {
        "symbol": symbol,
        "signals_count": total, "hits": hits, "misses": misses,
        "baseline_win_rate": round(baseline_wr, 4),
        "avg_outcome_pct": avg_outcome, "avg_max_gain_pct": avg_gain,
        "avg_max_loss_pct": avg_loss, "median_max_gain_pct": median_gain,
        "reward_risk_ratio": rr_ratio,
        "rsi_lift": rsi_lift, "rsi_samples": rsi_n,
        "macd_lift": macd_lift, "macd_samples": macd_n,
        "ema_lift": ema_lift, "ema_samples": ema_n,
        "vol_lift": vol_lift, "vol_samples": vol_n,
        "adx_lift": adx_lift, "adx_samples": adx_n,
        "stoch_lift": stoch_lift, "stoch_samples": stoch_n,
        "squeeze_lift": sq_lift, "squeeze_samples": sq_n,
        "support_lift": sup_lift, "support_samples": sup_n,
        "resistance_lift": res_lift, "resistance_samples": res_n,
        "breakout_lift": breakout_lift, "breakout_samples": breakout_n,
        "breakdown_lift": breakdown_lift, "breakdown_samples": breakdown_n,
        "high_atr_lift": high_atr_lift, "high_atr_samples": high_atr_n,
        "low_atr_lift": low_atr_lift, "low_atr_samples": low_atr_n,
        "better_timeframe": better_tf,
        "tf_1d_win_rate": tf_1d_wr, "tf_30m_win_rate": tf_30m_wr,
        "tf_1d_signals": len(src_1d), "tf_30m_signals": len(src_30m),
        "key_support": key_support, "key_resistance": key_resistance,
        "dominant_driver": dominant, "secondary_driver": secondary,
        "personality_tags": ",".join(tags),
        "personality_ar": " | ".join(tags_ar) if tags_ar else "عام",
    }


# ═══════════════════════════════════════════════════
# 2. PATTERN MEMORY — ذاكرة الأنماط
# ═══════════════════════════════════════════════════

def _pattern_key(atoms_tuple):
    return "|".join(sorted(atoms_tuple))

def _pattern_score(win_rate, occurrences, avg_gain, avg_loss):
    """Quality score — balances win rate, sample size, and profit potential."""
    if occurrences < 3 or win_rate is None:
        return 0
    pf = abs(avg_gain / avg_loss) if avg_loss and avg_loss != 0 else 1
    score = (
        win_rate * 45 +
        min(avg_gain or 0, 10) * 2 +
        min(occurrences, 20) / 20 * 20 +
        min(pf, 3) / 3 * 15
    )
    return round(score, 1)


def build_symbol_patterns(symbol, rows, max_combo=3, min_occurrences=3):
    """Find all pattern combinations for one symbol and compute stats."""
    if len(rows) < 10:
        return []

    atom_names = [a[0] for a in PATTERN_ATOMS]
    atom_fns   = [a[1] for a in PATTERN_ATOMS]

    # Pre-compute atom matches per row
    row_atoms = []
    for r in rows:
        matches = set()
        for i, fn in enumerate(atom_fns):
            try:
                if fn(r):
                    matches.add(atom_names[i])
            except Exception:
                pass
        row_atoms.append(matches)

    patterns = []
    for combo_size in range(1, max_combo + 1):
        for atoms in combinations(atom_names, combo_size):
            atoms_set = set(atoms)
            matched_indices = [i for i, ra in enumerate(row_atoms) if atoms_set.issubset(ra)]
            occ = len(matched_indices)
            if occ < min_occurrences:
                continue

            matched_rows = [rows[i] for i in matched_indices]
            hits    = sum(1 for r in matched_rows if r["outcome"] == "hit")
            misses  = sum(1 for r in matched_rows if r["outcome"] == "miss")
            expired = sum(1 for r in matched_rows if r["outcome"] == "expired")
            wr = _bayesian_rate(hits, occ)

            gains    = [r["max_gain_pct"]  for r in matched_rows if r.get("max_gain_pct")  is not None]
            losses   = [r["max_loss_pct"]  for r in matched_rows if r.get("max_loss_pct")  is not None]
            outcomes = [r["outcome_pct"]   for r in matched_rows if r.get("outcome_pct")   is not None]

            avg_g = round(sum(gains)    / len(gains),    3) if gains    else 0
            avg_l = round(sum(losses)   / len(losses),   3) if losses   else 0
            avg_o = round(sum(outcomes) / len(outcomes), 3) if outcomes else 0

            times     = [r.get("signal_time") for r in matched_rows if r.get("signal_time")]
            last_seen = max(times) if times else None

            score    = _pattern_score(wr, occ, avg_g, avg_l)
            atoms_ar = " + ".join(ATOM_AR.get(a, a) for a in atoms)

            patterns.append({
                "symbol": symbol,
                "pattern_key": _pattern_key(atoms),
                "pattern_atoms": ",".join(sorted(atoms)),
                "pattern_ar": atoms_ar,
                "combo_size": combo_size,
                "occurrences": occ,
                "hits": hits, "misses": misses, "expired": expired,
                "win_rate": round(wr, 4),
                "avg_gain_pct": avg_g, "avg_loss_pct": avg_l, "avg_outcome_pct": avg_o,
                "pattern_score": score,
                "last_seen": last_seen,
            })

    patterns.sort(key=lambda p: p["pattern_score"], reverse=True)
    return patterns


# ═══════════════════════════════════════════════════
# 3. AUTO NOTES — ملاحظات ذكية بالعربي
# ═══════════════════════════════════════════════════

def generate_notes(symbol, profile, top_patterns):
    """Generate Arabic notes from profile + patterns."""
    notes = []

    if not profile:
        return "⚪ لا توجد بيانات كافية"

    wr    = profile.get("baseline_win_rate", 0)
    dom   = profile.get("dominant_driver")
    sec   = profile.get("secondary_driver")
    avg_g = profile.get("avg_max_gain_pct")
    avg_l = profile.get("avg_max_loss_pct")
    rr    = profile.get("reward_risk_ratio")
    tags_ar = profile.get("personality_ar", "")

    if tags_ar:
        notes.append(f"🎯 شخصية السهم: {tags_ar}")

    driver_ar = {
        "Volume": "الحجم", "MACD": "MACD",
        "EMA": "المتوسطات", "RSI": "RSI",
        "ADX": "ADX", "Stochastic": "Stochastic",
    }
    if dom:
        d_ar = driver_ar.get(dom, dom)
        lift_key = dom.lower() + "_lift"
        lift = profile.get(lift_key)
        notes.append(f"📊 أقوى مؤشر: {d_ar}" + (f" (lift {lift:.2f}x)" if lift else ""))
    if sec:
        notes.append(f"📈 ثاني أفضل: {driver_ar.get(sec, sec)}")

    notes.append(f"✅ نسبة النجاح: {wr*100:.1f}% من {profile.get('signals_count', 0)} إشارة")

    if avg_g and avg_l:
        notes.append(f"💰 متوسط الحركة: +{avg_g:.1f}% / {avg_l:.1f}%")
    if rr:
        notes.append(f"⚖️ عائد/مخاطرة: {rr:.1f}x")

    vol_lift = profile.get("vol_lift")
    if vol_lift and vol_lift >= 1.2:
        notes.append("📊 الحجم مهم جداً — لا تدخل بدون تأكيد حجم")
    elif vol_lift and vol_lift < 0.9:
        notes.append("📊 الحجم غير مؤثر على هذا السهم")

    rsi_lift = profile.get("rsi_lift")
    if rsi_lift and rsi_lift >= 1.2:
        notes.append("🟢 يستجيب جيداً للتشبع البيعي (RSI < 30)")

    sup_lift = profile.get("support_lift")
    if sup_lift and sup_lift >= 1.15:
        notes.append("🛡️ يرتد جيداً من مستويات الدعم")
    breakout = profile.get("breakout_lift")
    if breakout and breakout >= 1.2:
        notes.append("🚀 اختراقات المقاومة ناجحة تاريخياً")
    elif breakout and breakout < 0.85:
        notes.append("⚠️ اختراقات المقاومة غالباً كاذبة — حذر")
    breakdown = profile.get("breakdown_lift")
    if breakdown and breakdown >= 1.15:
        notes.append("🔴 كسر الدعم يؤدي لهبوط حقيقي")

    key_sup = profile.get("key_support")
    key_res = profile.get("key_resistance")
    if key_sup:
        notes.append(f"📍 دعم رئيسي تاريخي: {key_sup}")
    if key_res:
        notes.append(f"📍 مقاومة رئيسية تاريخية: {key_res}")

    btf = profile.get("better_timeframe")
    if btf:
        tf_ar = "30 دقيقة" if btf == "30m" else "يومي"
        notes.append(f"⏰ أفضل فريم: {tf_ar}")

    high_atr = profile.get("high_atr_lift")
    if high_atr and high_atr >= 1.2:
        notes.append("💥 ينجح أكثر بالتذبذب العالي")
    low_atr = profile.get("low_atr_lift")
    if low_atr and low_atr >= 1.2:
        notes.append("💤 ينجح أكثر بالهدوء (ضغط قبل انفجار)")

    for i, pat in enumerate(top_patterns[:3]):
        p_ar  = pat.get("pattern_ar", pat.get("pattern_atoms", ""))
        wr_p  = pat.get("win_rate", 0) * 100
        occ   = pat.get("occurrences", 0)
        hits  = pat.get("hits", 0)
        avg   = pat.get("avg_gain_pct", 0)
        notes.append(
            f"🏆 نمط {i+1}: {p_ar} "
            f"→ {hits}/{occ} نجاح ({wr_p:.0f}%) "
            f"متوسط +{avg:.1f}%"
        )

    return " | ".join(notes)


# ═══════════════════════════════════════════════════
# 4. MAIN ENGINE — التشغيل الكامل
# ═══════════════════════════════════════════════════

def run_personality_analysis():
    """Main entry: analyze all symbols, build profiles + patterns + notes."""
    init_personality_schema()

    conn = _conn()
    rows = conn.execute("""
        SELECT symbol, signal_time, confluence_score, rsi_14,
               macd_state, ema_state, adx, vol_ratio, stoch_k, bb_squeeze,
               support, resistance, atr_14,
               outcome, outcome_pct, max_gain_pct, max_loss_pct, source
        FROM signal_snapshots
        WHERE outcome IN ('hit', 'miss', 'expired')
        ORDER BY symbol, signal_time
    """).fetchall()
    conn.close()

    if not rows:
        logger.warning("No evaluated signals found")
        return {"profiles": 0, "patterns": 0, "notes": 0}

    from collections import defaultdict
    by_symbol = defaultdict(list)
    for r in rows:
        by_symbol[r["symbol"]].append(dict(r))

    logger.info(f"Analyzing {len(by_symbol)} symbols with {len(rows)} total signals...")

    all_profiles, all_patterns, all_notes = [], [], []

    for symbol, sym_rows in by_symbol.items():
        profile = build_stock_profile(symbol, sym_rows)
        if profile:
            all_profiles.append(profile)

        patterns    = build_symbol_patterns(symbol, sym_rows, max_combo=3, min_occurrences=3)
        top_patterns = patterns[:50]
        all_patterns.extend(top_patterns)

        notes_text = generate_notes(symbol, profile, top_patterns)
        all_notes.append({
            "symbol": symbol, "timeframe": "1D",
            "note_type": "auto", "notes_ar": notes_text,
        })

    # Save to DB
    conn = _conn()
    conn.execute("DELETE FROM stock_profiles")
    conn.execute("DELETE FROM symbol_patterns")
    conn.execute("DELETE FROM symbol_notes WHERE note_type='auto'")

    now = datetime.utcnow().isoformat()

    for p in all_profiles:
        conn.execute("""
            INSERT OR REPLACE INTO stock_profiles
            (symbol, timeframe, signals_count, hits, misses, baseline_win_rate,
             avg_outcome_pct, avg_max_gain_pct, avg_max_loss_pct, median_max_gain_pct,
             reward_risk_ratio, rsi_lift, rsi_samples, macd_lift, macd_samples,
             ema_lift, ema_samples, vol_lift, vol_samples, adx_lift, adx_samples,
             stoch_lift, stoch_samples, squeeze_lift, squeeze_samples,
             support_lift, support_samples, resistance_lift, resistance_samples,
             breakout_lift, breakout_samples, breakdown_lift, breakdown_samples,
             high_atr_lift, high_atr_samples, low_atr_lift, low_atr_samples,
             better_timeframe, tf_1d_win_rate, tf_30m_win_rate,
             tf_1d_signals, tf_30m_signals, key_support, key_resistance,
             dominant_driver, secondary_driver, personality_tags, personality_ar, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            p["symbol"], "1D", p["signals_count"], p["hits"], p["misses"],
            p["baseline_win_rate"], p["avg_outcome_pct"], p["avg_max_gain_pct"],
            p["avg_max_loss_pct"], p["median_max_gain_pct"], p["reward_risk_ratio"],
            p["rsi_lift"], p["rsi_samples"], p["macd_lift"], p["macd_samples"],
            p["ema_lift"], p["ema_samples"], p["vol_lift"], p["vol_samples"],
            p["adx_lift"], p["adx_samples"], p["stoch_lift"], p["stoch_samples"],
            p["squeeze_lift"], p["squeeze_samples"],
            p["support_lift"], p["support_samples"],
            p["resistance_lift"], p["resistance_samples"],
            p["breakout_lift"], p["breakout_samples"],
            p["breakdown_lift"], p["breakdown_samples"],
            p["high_atr_lift"], p["high_atr_samples"],
            p["low_atr_lift"], p["low_atr_samples"],
            p["better_timeframe"], p["tf_1d_win_rate"], p["tf_30m_win_rate"],
            p["tf_1d_signals"], p["tf_30m_signals"],
            p["key_support"], p["key_resistance"],
            p["dominant_driver"], p["secondary_driver"],
            p["personality_tags"], p["personality_ar"], now
        ))

    for pat in all_patterns:
        conn.execute("""
            INSERT OR REPLACE INTO symbol_patterns
            (symbol, timeframe, pattern_key, pattern_atoms, pattern_ar,
             combo_size, occurrences, hits, misses, expired, win_rate,
             avg_gain_pct, avg_loss_pct, avg_outcome_pct, pattern_score,
             last_seen, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            pat["symbol"], "1D", pat["pattern_key"], pat["pattern_atoms"],
            pat["pattern_ar"], pat["combo_size"], pat["occurrences"],
            pat["hits"], pat["misses"], pat["expired"], pat["win_rate"],
            pat["avg_gain_pct"], pat["avg_loss_pct"], pat["avg_outcome_pct"],
            pat["pattern_score"], pat["last_seen"], now
        ))

    for n in all_notes:
        conn.execute("""
            INSERT OR REPLACE INTO symbol_notes
            (symbol, timeframe, note_type, notes_ar, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (n["symbol"], n["timeframe"], n["note_type"], n["notes_ar"], now))

    conn.commit()
    conn.close()

    logger.info(f"Done: {len(all_profiles)} profiles, {len(all_patterns)} patterns, {len(all_notes)} notes")
    return {
        "profiles": len(all_profiles),
        "patterns": len(all_patterns),
        "notes": len(all_notes),
    }


# ═══════════════════════════════════════════════════
# 5. API QUERY FUNCTIONS
# ═══════════════════════════════════════════════════

def get_symbol_personality(symbol, timeframe="1D"):
    """Get full personality data for one symbol — for dashboard API."""
    conn = _conn()

    profile = None
    row = conn.execute(
        "SELECT * FROM stock_profiles WHERE symbol=? AND timeframe=?",
        (symbol, timeframe)
    ).fetchone()
    if row:
        profile = dict(row)

    pat_rows = conn.execute(
        "SELECT * FROM symbol_patterns WHERE symbol=? AND timeframe=? ORDER BY pattern_score DESC LIMIT 10",
        (symbol, timeframe)
    ).fetchall()
    patterns = [dict(r) for r in pat_rows]

    note_row = conn.execute(
        "SELECT notes_ar FROM symbol_notes WHERE symbol=? AND timeframe=?",
        (symbol, timeframe)
    ).fetchone()
    notes = note_row["notes_ar"] if note_row else None

    conn.close()
    return {
        "symbol": symbol, "timeframe": timeframe,
        "profile": profile, "top_patterns": patterns, "notes": notes,
    }


def get_all_profiles_summary():
    """Get summary of all profiles — for dashboard overview."""
    conn = _conn()
    rows = conn.execute(
        "SELECT symbol, baseline_win_rate, dominant_driver, personality_ar, "
        "avg_max_gain_pct, signals_count FROM stock_profiles ORDER BY baseline_win_rate DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    result = run_personality_analysis()
    print(json.dumps(result, indent=2))
