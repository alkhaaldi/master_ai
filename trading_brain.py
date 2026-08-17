"""
trading_brain.py — Signal Learning Engine for Master AI.
Tracks signals, evaluates outcomes against market reality,
learns which indicators work best, and adjusts confluence weights.
"""
import os
import time
import json
import sqlite3
import logging
from datetime import datetime, timedelta, date

logger = logging.getLogger("trading_brain")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")

# Indicators tracked by the brain
INDICATORS = ["rsi", "macd", "ema", "adx", "vol", "stoch"]

# Minimum signals before adjusting weights
MIN_SIGNALS_FOR_ADJUST = 30
ROLLING_WINDOW = 50
WEIGHT_MIN = 0.3
WEIGHT_MAX = 2.0

# Outcome thresholds
DEFAULT_HIT_PCT = 3.0   # 3% move = meaningful
DEFAULT_EVAL_DAYS = 7

# Context injection
_ctx = {}


def init_brain_context(**kwargs):
    _ctx.update(kwargs)


# ═══════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS signal_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    signal_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    trade_state TEXT,
    verdict TEXT,
    verdict_key TEXT,
    confluence_score INTEGER,
    price_at_signal REAL,
    rsi_14 REAL,
    macd_state TEXT,
    macd_momentum TEXT,
    ema_state TEXT,
    adx REAL,
    vol_ratio REAL,
    stoch_k REAL,
    bb_squeeze BOOLEAN,
    rsi_divergence TEXT,
    ema_cross_type TEXT,
    ema_cross_bars_ago INTEGER,
    support REAL,
    resistance REAL,
    atr_14 REAL,
    ind_rsi INTEGER,
    ind_macd INTEGER,
    ind_ema INTEGER,
    ind_adx INTEGER,
    ind_vol INTEGER,
    ind_stoch INTEGER,
    ind_obv INTEGER,
    outcome TEXT DEFAULT 'pending',
    price_1d REAL,
    price_3d REAL,
    price_5d REAL,
    price_7d REAL,
    max_gain_pct REAL,
    max_loss_pct REAL,
    outcome_pct REAL,
    outcome_evaluated_at TIMESTAMP,
    source TEXT DEFAULT 'auto',
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_ss_symbol ON signal_snapshots(symbol);
CREATE INDEX IF NOT EXISTS idx_ss_outcome ON signal_snapshots(outcome);
CREATE INDEX IF NOT EXISTS idx_ss_time ON signal_snapshots(signal_time);

CREATE TABLE IF NOT EXISTS indicator_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator_name TEXT UNIQUE NOT NULL,
    total_signals INTEGER DEFAULT 0,
    total_hits INTEGER DEFAULT 0,
    hit_rate REAL DEFAULT 0.5,
    current_weight REAL DEFAULT 1.0,
    base_weight REAL DEFAULT 1.0,
    last_updated TIMESTAMP,
    rolling_hits INTEGER DEFAULT 0,
    rolling_total INTEGER DEFAULT 0,
    rolling_hit_rate REAL DEFAULT 0.5
);

CREATE TABLE IF NOT EXISTS indicator_regime_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator_name TEXT NOT NULL,
    regime TEXT NOT NULL,
    total_signals INTEGER DEFAULT 0,
    total_hits INTEGER DEFAULT 0,
    smoothed_rate REAL DEFAULT 0.5,
    last_updated TIMESTAMP,
    UNIQUE(indicator_name, regime)
);

CREATE TABLE IF NOT EXISTS brain_weekly_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL,
    week_end TEXT NOT NULL,
    total_signals INTEGER,
    total_evaluated INTEGER,
    hits INTEGER,
    misses INTEGER,
    hit_rate REAL,
    avg_gain_on_hits REAL,
    avg_loss_on_misses REAL,
    best_indicator TEXT,
    best_indicator_rate REAL,
    worst_indicator TEXT,
    worst_indicator_rate REAL,
    weight_adjustments TEXT,
    market_summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_schema():
    with _conn() as c:
        c.executescript(_SCHEMA_SQL)
    # Seed indicator_performance rows
    with _conn() as c:
        for ind in INDICATORS:
            c.execute(
                "INSERT OR IGNORE INTO indicator_performance (indicator_name, total_signals, total_hits, hit_rate, current_weight, base_weight) VALUES (?,0,0,0.5,1.0,1.0)",
                (ind,),
            )
    logger.info("Trading brain schema initialized")


# ═══════════════════════════════════════════════════
# 1. SNAPSHOT SIGNALS
# ═══════════════════════════════════════════════════

def snapshot_signals(signals: list = None):
    """Snapshot current signals from signal_engine. Dedup within 24h per symbol."""
    if signals is None:
        try:
            from signal_engine import build_signals
            result = build_signals()
            signals = result.get("all_signals", [])
        except Exception as e:
            logger.warning("Cannot get signals for snapshot: %s", e)
            return 0

    if not signals:
        return 0

    # UTC with the column format (space, seconds), like the insert below.
    # The old local isoformat() cutoff made this window 21h, not 24h, and
    # its T separator sorted after the space on same-day comparisons.
    cutoff = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    count = 0

    with _conn() as c:
        for sig in signals:
            if (sig.get("confluence_score") or 0) < 50:
                continue  # only track meaningful signals

            sym = sig.get("symbol", "")
            if not sym:
                continue

            # Dedup: skip if pending snapshot exists within 24h
            existing = c.execute(
                "SELECT id FROM signal_snapshots WHERE symbol=? AND outcome='pending' AND signal_time>?",
                (sym, cutoff),
            ).fetchone()
            if existing:
                continue

            ema_cross = sig.get("ema_cross") or {}
            pivots = sig.get("pivots") or {}
            # Phase 7: S/R distance calculations
            _price = sig.get("price") or 0
            _s_levels = [v for v in [pivots.get("s1", 0), pivots.get("s2", 0), sig.get("support", 0)] if v and v > 0 and v < _price]
            _r_levels = [v for v in [pivots.get("r1", 0), pivots.get("r2", 0), sig.get("resistance", 0)] if v and v > _price]
            _nearest_s = max(_s_levels) if _s_levels else 0
            _nearest_r = min(_r_levels) if _r_levels else 0
            _dist_support = round(((_price - _nearest_s) / _price) * 100, 2) if _nearest_s > 0 and _price > 0 else 0
            _dist_resist = round(((_nearest_r - _price) / _price) * 100, 2) if _nearest_r > 0 and _price > 0 else 0
            _near_support = 1 if (_nearest_s > 0 and sig.get("atr_14") and (_price - _nearest_s) < sig["atr_14"]) else 0

            c.execute(
                """INSERT INTO signal_snapshots
                (symbol, signal_time, trade_state, verdict, verdict_key, confluence_score,
                 price_at_signal, rsi_14, macd_state, macd_momentum, ema_state,
                 adx, vol_ratio, stoch_k, bb_squeeze, rsi_divergence,
                 ema_cross_type, ema_cross_bars_ago, support, resistance, atr_14,
                 ind_rsi, ind_macd, ind_ema, ind_adx, ind_vol, ind_stoch,
                 daily_pp, daily_s1, daily_s2, daily_r1, daily_r2,
                 pdh, pdl, distance_to_support_pct, distance_to_resistance_pct,
                 near_support, daily_sma20, daily_trend)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    sym,
                    # UTC on purpose, same clock and format as brain_backfill's
                    # candle stamps. CURRENT_TIMESTAMP filled the same value
                    # implicitly; explicit here so the column's clock is stated
                    # in code, not in a schema default nobody reads.
                    datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    sig.get("trade_state"),
                    sig.get("verdict"),
                    sig.get("verdict_key"),
                    sig.get("confluence_score", 0),
                    _price,
                    sig.get("rsi_14"),
                    sig.get("macd_state"),
                    sig.get("macd_momentum"),
                    sig.get("ema_state"),
                    sig.get("adx"),
                    sig.get("vol_ratio"),
                    sig.get("stoch_k"),
                    1 if sig.get("bb_squeeze") else 0,
                    sig.get("rsi_divergence"),
                    ema_cross.get("type"),
                    ema_cross.get("bars_ago"),
                    sig.get("support"),
                    sig.get("resistance"),
                    sig.get("atr_14"),
                    # Individual indicator votes
                    1 if (sig.get("rsi_14") or 0) > 50 else 0,
                    1 if sig.get("macd_state") == "bullish" else 0,
                    1 if sig.get("ema_state") == "bullish" else 0,
                    1 if (sig.get("adx") or 0) > 25 else 0,
                    1 if (sig.get("vol_ratio") or 0) > 1.0 else 0,
                    1 if (sig.get("stoch_k") or 0) > 50 else 0,
                    # Phase 7: S/R tracking columns
                    pivots.get("pp", 0),
                    pivots.get("s1", 0),
                    pivots.get("s2", 0),
                    pivots.get("r1", 0),
                    pivots.get("r2", 0),
                    0,  # pdh (populated when daily_bars has prev day data)
                    0,  # pdl
                    _dist_support,
                    _dist_resist,
                    _near_support,
                    sig.get("daily_sma20", 0),
                    sig.get("daily_trend", "UNKNOWN"),
                ),
            )
            count += 1

    if count:
        logger.info("Snapshotted %d signals", count)
    return count


# ═══════════════════════════════════════════════════
# 2. EVALUATE PENDING SIGNALS
# ═══════════════════════════════════════════════════

def evaluate_pending_signals():
    """Evaluate signals that are old enough (>= 7 days). Called daily after market close."""
    cutoff = (datetime.utcnow() - timedelta(days=DEFAULT_EVAL_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

    with _conn() as c:
        pending = c.execute(
            "SELECT * FROM signal_snapshots WHERE outcome='pending' AND signal_time<=?",
            (cutoff,),
        ).fetchall()

    if not pending:
        return 0

    # Get current prices
    prices = _get_current_prices()
    evaluated = 0

    for row in pending:
        sym = row["symbol"]
        price_at = row["price_at_signal"]
        if not price_at or price_at <= 0:
            continue

        current = prices.get(sym)
        if current is None:
            continue

        change_pct = ((current - price_at) / price_at) * 100
        atr = row["atr_14"] or price_at * 0.03  # fallback 3%
        atr_pct = (atr / price_at) * 100

        # Determine outcome
        hit_threshold = max(atr_pct * 0.5, DEFAULT_HIT_PCT)
        verdict_key = row["verdict_key"] or ""

        if verdict_key in ("buy", "watch"):
            if change_pct >= hit_threshold:
                outcome = "hit"
            elif change_pct <= -hit_threshold:
                outcome = "miss"
            else:
                outcome = "expired"
        elif verdict_key == "avoid":
            if change_pct <= -hit_threshold:
                outcome = "hit"  # correctly predicted weakness
            elif change_pct >= hit_threshold:
                outcome = "miss"
            else:
                outcome = "expired"
        else:
            outcome = "expired"

        with _conn() as c:
            c.execute(
                """UPDATE signal_snapshots SET
                   outcome=?, price_7d=?, outcome_pct=?,
                   max_gain_pct=?, max_loss_pct=?,
                   outcome_evaluated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (
                    outcome,
                    current,
                    round(change_pct, 2),
                    round(max(change_pct, 0), 2),
                    round(min(change_pct, 0), 2),
                    row["id"],
                ),
            )
        evaluated += 1

    if evaluated:
        logger.info("Evaluated %d signals (%d pending were ready)", evaluated, len(pending))
        update_indicator_performance()

    return evaluated


def _get_current_prices() -> dict:
    """Get current prices from radar daily context or bridge cache."""
    prices = {}
    try:
        from stock_radar import _db as _radar_db
        conn = _radar_db()
        rows = conn.execute(
            "SELECT symbol, price, updated_at FROM stock_radar_daily ORDER BY updated_at DESC",
        ).fetchall()
        conn.close()
        for r in rows:
            if r["symbol"] not in prices and r["price"]:
                prices[r["symbol"]] = float(r["price"])
    except Exception as e:
        logger.debug("Radar prices unavailable: %s", e)

    # Fallback: bridge cache
    try:
        from bridge_client import get_bridge_client
        client = get_bridge_client()
        for key, entry in client._cache.items():
            if key.startswith("analysis:"):
                sym = key.split(":")[-1]
                if sym not in prices:
                    data = entry.get("data", {})
                    if data.get("price"):
                        prices[sym] = data["price"]
    except Exception:
        pass

    return prices


# ═══════════════════════════════════════════════════
# HELPER: Bayesian Beta-Binomial smoothed hit rate
# ═══════════════════════════════════════════════════

def _bayesian_hit_rate(hits, total, alpha=5, beta=5):
    """Bayesian smoothed hit rate. Prior = Beta(5,5) = 50% with moderate confidence."""
    return (hits + alpha) / (total + alpha + beta)


def _compute_decay_weight(signal_time_str, half_life_days=90):
    """Recent signals weighted more. Half-life = 90 days (signal from 90d ago = 0.5x weight)."""
    import math
    try:
        sig_time = datetime.fromisoformat(signal_time_str)
        age_days = (datetime.now() - sig_time).days
        return math.exp(-0.693 * age_days / half_life_days)
    except Exception:
        return 0.5


# ═══════════════════════════════════════════════════
# 3. UPDATE INDICATOR PERFORMANCE
# ═══════════════════════════════════════════════════

def update_indicator_performance():
    """Recalculate hit rates and rolling stats for each indicator."""
    with _conn() as c:
        evaluated = c.execute(
            "SELECT * FROM signal_snapshots WHERE outcome IN ('hit','miss') ORDER BY signal_time DESC"
        ).fetchall()

    if not evaluated:
        return

    for ind in INDICATORS:
        col = f"ind_{ind}"
        total           = 0
        hits            = 0
        rolling_total   = 0
        rolling_hits    = 0
        weighted_total  = 0.0
        weighted_hits   = 0.0

        for i, row in enumerate(evaluated):
            vote   = row[col]
            is_hit = row["outcome"] == "hit"
            correct = (vote == 1 and is_hit) or (vote == 0 and not is_hit)

            # Recency decay: recent signals count more
            decay = _compute_decay_weight(row["signal_time"])

            total += 1
            if correct:
                hits += 1

            weighted_total += decay
            if correct:
                weighted_hits += decay

            if i < ROLLING_WINDOW:
                rolling_total += 1
                if correct:
                    rolling_hits += 1

        # Use decay-weighted Bayesian rate as hit_rate; pure Bayesian for rolling
        hit_rate   = _bayesian_hit_rate(weighted_hits, weighted_total)
        rolling_hr = _bayesian_hit_rate(rolling_hits, rolling_total)

        with _conn() as c:
            c.execute(
                """UPDATE indicator_performance SET
                   total_signals=?, total_hits=?, hit_rate=?,
                   rolling_hits=?, rolling_total=?, rolling_hit_rate=?,
                   last_updated=CURRENT_TIMESTAMP
                   WHERE indicator_name=?""",
                (total, hits, round(hit_rate, 4), rolling_hits, rolling_total, round(rolling_hr, 4), ind),
            )

    logger.info("Updated indicator performance for %d indicators", len(INDICATORS))


# ═══════════════════════════════════════════════════
# 4. ADJUST WEIGHTS
# ═══════════════════════════════════════════════════

def adjust_weights() -> dict:
    """Adjust indicator weights based on rolling hit rates. Called weekly."""
    adjustments = {}

    with _conn() as c:
        rows = c.execute("SELECT * FROM indicator_performance").fetchall()

    for row in rows:
        ind = row["indicator_name"]
        if row["rolling_total"] < MIN_SIGNALS_FOR_ADJUST:
            adjustments[ind] = {"old": row["current_weight"], "new": row["current_weight"], "reason": "insufficient_data"}
            continue

        base = row["base_weight"] or 1.0
        rolling_hr = row["rolling_hit_rate"] or 0.5
        new_weight = base * (0.5 + rolling_hr)
        new_weight = max(WEIGHT_MIN, min(WEIGHT_MAX, round(new_weight, 3)))
        old_weight = row["current_weight"]

        with _conn() as c2:
            c2.execute(
                "UPDATE indicator_performance SET current_weight=?, last_updated=CURRENT_TIMESTAMP WHERE indicator_name=?",
                (new_weight, ind),
            )

        adjustments[ind] = {"old": old_weight, "new": new_weight, "hit_rate": rolling_hr}

    logger.info("Weight adjustment: %s", {k: f"{v.get('old',1):.2f}->{v.get('new',1):.2f}" for k, v in adjustments.items()})
    return adjustments


# ═══════════════════════════════════════════════════
# 5. REGIME-AWARE STATS
# ═══════════════════════════════════════════════════

def update_regime_stats():
    """Update indicator performance per market regime."""
    conn = _conn()
    evaluated = conn.execute(
        "SELECT * FROM signal_snapshots WHERE outcome IN ('hit','miss') ORDER BY signal_time DESC"
    ).fetchall()
    conn.close()

    if not evaluated:
        return

    from collections import defaultdict
    stats = defaultdict(lambda: {"hits": 0, "total": 0})

    for row in evaluated:
        adx    = row["adx"] or 0
        regime = "trending" if adx >= 25 else "ranging" if adx <= 20 else "transition"

        for ind in INDICATORS:
            col    = f"ind_{ind}"
            vote   = row[col]
            is_hit = row["outcome"] == "hit"
            correct = (vote == 1 and is_hit) or (vote == 0 and not is_hit)

            key = (ind, regime)
            stats[key]["total"] += 1
            if correct:
                stats[key]["hits"] += 1

    conn = _conn()
    for (ind, regime), val in stats.items():
        smoothed = _bayesian_hit_rate(val["hits"], val["total"])
        conn.execute(
            """INSERT OR REPLACE INTO indicator_regime_stats
               (indicator_name, regime, total_signals, total_hits, smoothed_rate, last_updated)
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (ind, regime, val["total"], val["hits"], round(smoothed, 4)),
        )
    conn.commit()
    conn.close()
    logger.info("Regime stats updated for %d indicator-regime pairs", len(stats))


def _get_regime_weights(regime):
    """Get weights tuned for a specific regime."""
    conn = _conn()
    rows = conn.execute(
        "SELECT indicator_name, smoothed_rate FROM indicator_regime_stats WHERE regime=?",
        (regime,),
    ).fetchall()
    conn.close()
    if len(rows) < len(INDICATORS):
        return None  # not enough data for this regime
    weights = {}
    for r in rows:
        weights[r["indicator_name"]] = round(0.5 + r["smoothed_rate"], 3)
    return weights


# ═══════════════════════════════════════════════════
# 6. ADJUSTED CONFLUENCE (used by signal_engine)
# ═══════════════════════════════════════════════════

def get_adjusted_confluence(signal_data: dict) -> dict:
    """Calculate weighted confluence. Uses regime-aware weights if available,
    fallback to global weights, fallback to simple."""
    adx    = signal_data.get("adx") or 0
    regime = "trending" if adx >= 25 else "ranging" if adx <= 20 else "transition"

    try:
        # Try regime-specific weights first
        weights = _get_regime_weights(regime)
        if not weights:
            weights = get_indicator_weights()  # fallback to global
    except Exception:
        return _fallback_confluence(signal_data)

    votes = {
        "rsi": 1 if (signal_data.get("rsi_14") or 0) > 50 else 0,
        "macd": 1 if signal_data.get("macd_state") == "bullish" else 0,
        "ema": 1 if signal_data.get("ema_state") == "bullish" else 0,
        "adx": 1 if (signal_data.get("adx") or 0) > 25 else 0,
        "vol": 1 if (signal_data.get("vol_ratio") or 0) > 1.0 else 0,
        "stoch": 1 if (signal_data.get("stoch_k") or 0) > 50 else 0,
    }

    # `weights.get(ind, 1.0)` until 2026-08-17: an indicator the brain had
    # never learned a weight for was given FULL weight - the loudest vote in
    # the room going to the one thing with no evidence behind it. And the
    # score came back stamped brain_weighted=True either way, so a blend of
    # learned and invented weights was indistinguishable from a fully learned
    # one. That matters directly for C-27, whose whole question is what the
    # weights were fitted on.
    #
    # Absence now EXCLUDES: an indicator with no learned weight leaves both
    # sides of the ratio. All six carry weights today, so this changes no
    # number now - it changes what happens the first time one does not.
    present = [ind for ind in INDICATORS if weights.get(ind) is not None]
    weighted_bullish = sum(votes[ind] * weights[ind] for ind in present)
    weighted_total = sum(weights[ind] for ind in present)

    if weighted_total <= 0:
        return _fallback_confluence(signal_data)

    score = int(round((weighted_bullish / weighted_total) * 100))
    bullish = sum(1 for v in votes.values() if v == 1)
    bearish = len(votes) - bullish

    if score >= 70:
        direction = "strong_bullish"
    elif score >= 55:
        direction = "bullish"
    elif score <= 30:
        direction = "strong_bearish"
    elif score <= 45:
        direction = "bearish"
    else:
        direction = "neutral"

    raw_score = int(round((bullish / len(votes)) * 100)) if len(votes) > 0 else 0

    return {
        "score":        score,
        "direction":    direction,
        "bullish":      bullish,
        "bearish":      bearish,
        "total":        len(votes),
        "brain_weighted": True,
        # The basis travels with the score (C-27): which indicators actually
        # carried a learned weight, and which were left out for lacking one.
        "weights_used": present,
        "weights_missing": [i for i in INDICATORS if i not in present],
        "regime":       regime,
        "raw_score":    raw_score,
        "brain_delta":  score - raw_score,
    }


def _fallback_confluence(signal_data: dict) -> dict:
    """Original simple confluence from signal_engine."""
    signals = signal_data.get("signals") or {}
    conf = signals.get("confluence")
    if isinstance(conf, dict):
        return conf
    return {"score": 0, "direction": "unknown", "bullish": 0, "bearish": 0, "total": 0}


def get_indicator_weights() -> dict:
    """Return current weights as {name: weight}."""
    with _conn() as c:
        rows = c.execute("SELECT indicator_name, current_weight FROM indicator_performance").fetchall()
    return {r["indicator_name"]: r["current_weight"] for r in rows}


def get_optimal_thresholds() -> dict:
    """Calculate optimal thresholds from historical backfill data.
    Returns thresholds for trade state assignment and verdict decisions.
    Falls back to defaults if insufficient data."""
    DEFAULTS = {
        "ready_min_score":  60,
        "ready_min_vol":    1.2,
        "setup_min_score":  40,
        "avoid_max_score":  30,
        "watch_min_score":  50,
    }

    conn = _conn()
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM signal_snapshots WHERE outcome IN ('hit','miss')"
        ).fetchone()[0]

        if total < 100:
            return {**DEFAULTS, "source": "defaults", "data_points": total}

        rows = conn.execute("""
            SELECT confluence_score,
                   COUNT(*) as total,
                   SUM(CASE WHEN outcome='hit' THEN 1 ELSE 0 END) as hits
            FROM signal_snapshots
            WHERE outcome IN ('hit','miss')
            GROUP BY confluence_score
            ORDER BY confluence_score
        """).fetchall()

        score_hits = [(r["confluence_score"], r["hits"], r["total"]) for r in rows]

        # Cumulative from high to low: find where cumulative hit rate crosses thresholds
        cum_hits  = 0
        cum_total = 0
        ready_threshold = DEFAULTS["ready_min_score"]
        setup_threshold = DEFAULTS["setup_min_score"]

        for score, hits, tot in sorted(score_hits, reverse=True):
            cum_hits  += hits
            cum_total += tot
            rate = cum_hits / cum_total if cum_total > 0 else 0

            if rate >= 0.55 and score < ready_threshold:
                ready_threshold = max(score, 35)
            if rate >= 0.45 and score < setup_threshold:
                setup_threshold = max(score, 25)

        # Avoid = cumulative from low where hit rate stays bad
        avoid_threshold = DEFAULTS["avoid_max_score"]
        cum_hits_low  = 0
        cum_total_low = 0
        for score, hits, tot in sorted(score_hits):
            cum_hits_low  += hits
            cum_total_low += tot
            rate = cum_hits_low / cum_total_low if cum_total_low > 0 else 0
            if rate < 0.35:
                avoid_threshold = max(score + 5, 20)

        return {
            "ready_min_score": ready_threshold,
            "ready_min_vol":   1.2,
            "setup_min_score": setup_threshold,
            "avoid_max_score": avoid_threshold,
            "watch_min_score": int((ready_threshold + setup_threshold) / 2),
            "source":          "brain_learned",
            "data_points":     total,
        }

    except Exception as e:
        logger.warning(f"get_optimal_thresholds failed: {e}")
        return {**DEFAULTS, "source": "defaults_error"}
    finally:
        conn.close()


# ═══════════════════════════════════════════════════
# 6. WEEKLY REPORT
# ═══════════════════════════════════════════════════

def generate_weekly_report() -> dict:
    """Generate weekly performance report. Called Friday 14:00 KWT."""
    # UTC date: signal_time is UTC, and a local date boundary shifted
    # the week window by 3h at each edge
    today = datetime.utcnow().date()
    week_start = (today - timedelta(days=7)).isoformat()
    week_end = today.isoformat()

    with _conn() as c:
        week_signals = c.execute(
            "SELECT * FROM signal_snapshots WHERE signal_time>=? AND signal_time<?",
            (week_start, week_end),
        ).fetchall()

        evaluated = [s for s in week_signals if s["outcome"] in ("hit", "miss", "expired")]
        hits = [s for s in evaluated if s["outcome"] == "hit"]
        misses = [s for s in evaluated if s["outcome"] == "miss"]

    total = len(week_signals)
    total_eval = len(evaluated)
    hit_count = len(hits)
    miss_count = len(misses)
    hit_rate = hit_count / total_eval if total_eval > 0 else 0

    avg_gain = sum(s["outcome_pct"] or 0 for s in hits) / len(hits) if hits else 0
    avg_loss = sum(s["outcome_pct"] or 0 for s in misses) / len(misses) if misses else 0

    # Best/worst indicator
    with _conn() as c:
        ind_rows = c.execute("SELECT * FROM indicator_performance ORDER BY rolling_hit_rate DESC").fetchall()

    best = ind_rows[0] if ind_rows else None
    worst = ind_rows[-1] if ind_rows else None

    # Weight adjustments
    adjustments = adjust_weights()

    report = {
        "week_start": week_start,
        "week_end": week_end,
        "total_signals": total,
        "total_evaluated": total_eval,
        "hits": hit_count,
        "misses": miss_count,
        "hit_rate": round(hit_rate, 3),
        "avg_gain_on_hits": round(avg_gain, 2),
        "avg_loss_on_misses": round(avg_loss, 2),
        "best_indicator": best["indicator_name"] if best else None,
        "best_indicator_rate": best["rolling_hit_rate"] if best else None,
        "worst_indicator": worst["indicator_name"] if worst else None,
        "worst_indicator_rate": worst["rolling_hit_rate"] if worst else None,
        "weight_adjustments": adjustments,
    }

    # Save to DB
    with _conn() as c:
        c.execute(
            """INSERT INTO brain_weekly_reports
            (week_start, week_end, total_signals, total_evaluated, hits, misses, hit_rate,
             avg_gain_on_hits, avg_loss_on_misses, best_indicator, best_indicator_rate,
             worst_indicator, worst_indicator_rate, weight_adjustments)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                week_start, week_end, total, total_eval, hit_count, miss_count,
                round(hit_rate, 3), round(avg_gain, 2), round(avg_loss, 2),
                report["best_indicator"], report["best_indicator_rate"],
                report["worst_indicator"], report["worst_indicator_rate"],
                json.dumps(adjustments),
            ),
        )

    logger.info("Weekly report: %d signals, %d evaluated, %.0f%% hit rate", total, total_eval, hit_rate * 100)
    return report


def format_weekly_tg(report: dict) -> str:
    """Format weekly report as Telegram message."""
    adj = report.get("weight_adjustments", {})
    adj_lines = []
    for ind, v in adj.items():
        if isinstance(v, dict) and "old" in v and "new" in v:
            arrow = "\u25b2" if v["new"] > v["old"] else ("\u25bc" if v["new"] < v["old"] else "=")
            adj_lines.append(f"  {ind.upper()}: {v['old']:.2f} \u2192 {v['new']:.2f} {arrow}")

    return (
        f"\U0001f9e0 \u062a\u0642\u0631\u064a\u0631 \u0639\u0642\u0644 \u0627\u0644\u062a\u062f\u0627\u0648\u0644\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4ca \u0625\u0634\u0627\u0631\u0627\u062a: {report['total_signals']} | \u062a\u0642\u064a\u064a\u0645: {report['total_evaluated']}\n"
        f"\u2705 \u0635\u062d\u064a\u062d\u0629: {report['hits']} ({report['hit_rate']*100:.0f}%) | \u274c \u062e\u0627\u0637\u0626\u0629: {report['misses']}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4c8 \u0623\u0641\u0636\u0644: {(report.get('best_indicator') or '?').upper()} ({(report.get('best_indicator_rate') or 0)*100:.0f}%)\n"
        f"\U0001f4c9 \u0623\u0633\u0648\u0623: {(report.get('worst_indicator') or '?').upper()} ({(report.get('worst_indicator_rate') or 0)*100:.0f}%)\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\u2696\ufe0f \u062a\u0639\u062f\u064a\u0644 \u0627\u0644\u0623\u0648\u0632\u0627\u0646:\n" + "\n".join(adj_lines) + "\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4b0 \u0645\u062a\u0648\u0633\u0637 \u0631\u0628\u062d \u0627\u0644\u0635\u062d\u064a\u062d\u0629: {report['avg_gain_on_hits']:+.1f}%\n"
        f"\U0001f4c9 \u0645\u062a\u0648\u0633\u0637 \u062e\u0633\u0627\u0631\u0629 \u0627\u0644\u062e\u0627\u0637\u0626\u0629: {report['avg_loss_on_misses']:.1f}%"
    )


# ═══════════════════════════════════════════════════
# 7. DASHBOARD DATA
# ═══════════════════════════════════════════════════

def get_brain_stats() -> dict:
    """Return brain stats for /dashboard/brain endpoint."""
    with _conn() as c:
        total = c.execute("SELECT COUNT(*) FROM signal_snapshots").fetchone()[0]
        evaluated = c.execute("SELECT COUNT(*) FROM signal_snapshots WHERE outcome IN ('hit','miss','expired')").fetchone()[0]
        hits = c.execute("SELECT COUNT(*) FROM signal_snapshots WHERE outcome='hit'").fetchone()[0]
        pending = c.execute("SELECT COUNT(*) FROM signal_snapshots WHERE outcome='pending'").fetchone()[0]

        ind_rows = c.execute("SELECT * FROM indicator_performance ORDER BY rolling_hit_rate DESC").fetchall()

        recent = c.execute(
            "SELECT symbol, signal_time, verdict, outcome, outcome_pct FROM signal_snapshots WHERE outcome IN ('hit','miss') ORDER BY outcome_evaluated_at DESC LIMIT 10"
        ).fetchall()

        last_report = c.execute(
            "SELECT * FROM brain_weekly_reports ORDER BY created_at DESC LIMIT 1"
        ).fetchone()

    overall_hr = hits / evaluated if evaluated > 0 else 0

    weights = {}
    for r in ind_rows:
        weights[r["indicator_name"]] = {
            "weight": r["current_weight"],
            "hit_rate": r["rolling_hit_rate"],
            "signals": r["rolling_total"],
        }

    recent_evals = []
    for r in recent:
        recent_evals.append({
            "symbol": r["symbol"],
            "signal_time": r["signal_time"],
            "verdict": r["verdict"],
            "outcome": r["outcome"],
            "pct": r["outcome_pct"],
        })

    weekly = None
    if last_report:
        weekly = {
            "hit_rate": last_report["hit_rate"],
            "best_indicator": last_report["best_indicator"],
            "worst_indicator": last_report["worst_indicator"],
            "week_end": last_report["week_end"],
        }

    # Regime stats per indicator
    regime_stats = {}
    try:
        with _conn() as c:
            rrows = c.execute(
                "SELECT * FROM indicator_regime_stats ORDER BY indicator_name, regime"
            ).fetchall()
        for r in rrows:
            ind = r["indicator_name"]
            if ind not in regime_stats:
                regime_stats[ind] = {}
            regime_stats[ind][r["regime"]] = {
                "hits":  r["total_hits"],
                "total": r["total_signals"],
                "rate":  r["smoothed_rate"],
            }
    except Exception:
        pass

    return {
        "brain_active":       True,
        "total_tracked":      total,
        "total_evaluated":    evaluated,
        "overall_hit_rate":   round(overall_hr, 3),
        "pending_count":      pending,
        "indicator_weights":  weights,
        "recent_evaluations": recent_evals,
        "weekly_summary":     weekly,
        "regime_stats":       regime_stats,
        "backfill_count":     _get_backfill_count(),
        "learning_mode":      "bayesian_regime_aware",
    }


def _get_backfill_count():
    """Count historical backfill snapshots."""
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT COUNT(*) as cnt FROM signal_snapshots WHERE source='historical_backfill'"
            ).fetchone()
        return row["cnt"] if row else 0
    except Exception:
        return 0
