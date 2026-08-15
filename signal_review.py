"""
Signal Review Engine — Daily ENTER decision evaluation
Compares ENTER signals from decision_audit against next-day price data,
classifies results, analyzes root cause, and sends Telegram summary.

Scheduler: 2:00 PM KWT daily (30min after data collection)
"""

import sqlite3
import logging
import os
import asyncio
from datetime import datetime, date, timedelta
from typing import Optional
from collections import Counter

logger = logging.getLogger("signal_review")
# Explicit INFO: the root logger sits at WARNING (server.py), which silently
# dropped this module's liveness lines — "scheduler started", "review
# complete" — for months. A loop whose heartbeat is invisible reads as dead.
logger.setLevel(logging.INFO)

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _read_file(path: str) -> str:
    expanded = os.path.expanduser(path)
    try:
        with open(expanded, "r") as f:
            return f.read().strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
#  Schema
# ---------------------------------------------------------------------------

def init_review_schema():
    """Create signal_reviews table if not exists."""
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS signal_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_date DATE NOT NULL,
                market_date DATE NOT NULL,
                symbol TEXT NOT NULL,
                smart_decision TEXT NOT NULL,
                chosen_plan_source TEXT,
                strategy_id TEXT,

                -- prices
                entry_price REAL,
                stop_price REAL,
                target_1 REAL,
                target_2 REAL,
                next_day_open REAL,
                next_day_high REAL,
                next_day_low REAL,
                next_day_close REAL,
                next_day_volume INTEGER,

                -- result
                result TEXT NOT NULL DEFAULT 'pending',
                pnl_pct REAL,
                max_favorable REAL,
                max_adverse REAL,
                hit_target_1 BOOLEAN DEFAULT 0,
                hit_stop BOOLEAN DEFAULT 0,

                -- analysis
                error_type TEXT,
                reason_ar TEXT,
                lesson_ar TEXT,

                -- indicators at signal time
                confidence REAL,
                data_quality INTEGER,
                rr_ratio REAL,
                risk_flags TEXT,
                sector TEXT,

                -- tracking
                decision_audit_id INTEGER,
                days_tracked INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

                UNIQUE(market_date, symbol)
            );

            CREATE INDEX IF NOT EXISTS idx_sr_review_date ON signal_reviews(review_date);
            CREATE INDEX IF NOT EXISTS idx_sr_result ON signal_reviews(result);
            CREATE INDEX IF NOT EXISTS idx_sr_symbol ON signal_reviews(symbol);
        """)
        # E-1: 'live' = graded on the first session after market_date,
        # 'backfill' = graded later from history, 'ungraded' = no_data rows
        # (nothing measured yet), 'legacy' = graded by the pre-E-1 loop on
        # bridge bars (Mar-Apr 2026). Never NULL — NULL would read as
        # "unknown provenance" and C-27 must be able to trust this field.
        try:
            c.execute("ALTER TABLE signal_reviews ADD COLUMN graded_mode TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
    logger.info("signal_reviews schema initialized")


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _last_trading_day(ref_date=None):
    """Return last KSE trading day BEFORE today (or before ref_date) — i.e. yesterday's session."""
    d = ref_date or date.today()
    if isinstance(d, str):
        d = datetime.strptime(d, "%Y-%m-%d").date()
    # Go back one day first (we want YESTERDAY's signals, not today's)
    d -= timedelta(days=1)
    # Skip Fri(4) and Sat(5)
    while d.weekday() in (4, 5):
        d -= timedelta(days=1)
    return d.isoformat()


def _get_pending_decisions(market_date: str) -> list:
    """Get all ENTER decisions for a given market date."""
    with _conn() as c:
        rows = c.execute("""
            SELECT id, symbol, smart_decision, chosen_plan_source, strategy_id,
                   entry_price, stop_price, target_1, target_2, rr_ratio,
                   confidence, data_quality, risk_flags, sector, strategy_ev
            FROM decision_audit
            WHERE market_date = ? AND smart_decision = 'ENTER'
            ORDER BY confidence DESC
        """, (market_date,)).fetchall()
    return [dict(r) for r in rows]


def _get_next_day_bars(symbol: str, after_date: str) -> Optional[dict]:
    """Get first trading day bars after the given date for a symbol."""
    with _conn() as c:
        row = c.execute("""
            SELECT trading_date, open, high, low, close, volume
            FROM daily_bars
            WHERE symbol = ? AND trading_date > ?
            ORDER BY trading_date ASC
            LIMIT 1
        """, (symbol, after_date)).fetchone()
    return dict(row) if row else None


def _get_avg_volume(symbol: str, before_date: str, days: int = 20) -> float:
    """Average volume over last N trading days before a date."""
    with _conn() as c:
        row = c.execute("""
            SELECT AVG(volume) as avg_vol FROM (
                SELECT volume FROM daily_bars
                WHERE symbol = ? AND trading_date < ?
                ORDER BY trading_date DESC
                LIMIT ?
            )
        """, (symbol, before_date, days)).fetchone()
    return float(row["avg_vol"]) if row and row["avg_vol"] else 0


def _get_strategy_stats(strategy_id: str) -> Optional[dict]:
    """Get strategy performance stats from mined_strategies."""
    with _conn() as c:
        row = c.execute("""
            SELECT profitable_rate, sample_size, ev, stop_pct, target_1_pct
            FROM mined_strategies
            WHERE strategy_id = ?
        """, (strategy_id,)).fetchone()
    return dict(row) if row else None


def _check_market_drop(trading_date: str) -> bool:
    """Check if more than 70% of stocks closed below open on this date."""
    with _conn() as c:
        row = c.execute("""
            SELECT
                COUNT(CASE WHEN close < open THEN 1 END) as down_count,
                COUNT(*) as total
            FROM daily_bars
            WHERE trading_date = ? AND volume > 0
        """, (trading_date,)).fetchone()
    if not row or row["total"] < 10:
        return False
    return (row["down_count"] / row["total"]) > 0.70


# ---------------------------------------------------------------------------
#  Classification & Analysis
# ---------------------------------------------------------------------------

def _classify_result(decision: dict, bar: dict) -> dict:
    """Classify signal outcome based on next-day price action."""
    entry = decision.get("entry_price") or 0
    stop = decision.get("stop_price")
    t1 = decision.get("target_1")
    t2 = decision.get("target_2")
    high = bar["high"] or 0
    low = bar["low"] or 0
    close = bar["close"] or 0

    if not entry or entry == 0:
        return {"result": "no_data", "pnl_pct": 0, "max_favorable": 0,
                "max_adverse": 0, "hit_target_1": False, "hit_stop": False}

    pnl_pct = ((close - entry) / entry) * 100
    max_favorable = ((high - entry) / entry) * 100
    max_adverse = ((entry - low) / entry) * 100

    hit_t1 = high >= t1 if t1 else False
    hit_stop = low <= stop if stop else False

    if hit_t1:
        result = "success"
    elif hit_stop:
        result = "fail"
    elif pnl_pct > 0:
        result = "partial"
    elif pnl_pct <= -3.0:
        result = "fail"
    else:
        result = "ongoing"

    return {
        "result": result,
        "pnl_pct": round(pnl_pct, 2),
        "max_favorable": round(max_favorable, 2),
        "max_adverse": round(max_adverse, 2),
        "hit_target_1": hit_t1,
        "hit_stop": hit_stop,
    }


def _analyze_reason(decision: dict, bar: dict, result: str) -> dict:
    """Analyze root cause of signal outcome."""
    error_type = "none"
    reason_ar = ""
    lesson_ar = ""

    if result == "success":
        reason_ar = "\u0627\u0644\u0625\u0634\u0627\u0631\u0629 \u0646\u062c\u062d\u062a \u2014 \u0648\u0635\u0644 \u0627\u0644\u0647\u062f\u0641 \u0627\u0644\u0623\u0648\u0644"
        t2 = decision.get("target_2")
        if t2 and bar["high"] >= t2:
            reason_ar = "\u0627\u0644\u0625\u0634\u0627\u0631\u0629 \u0646\u062c\u062d\u062a \u2014 \u0648\u0635\u0644 \u0627\u0644\u0647\u062f\u0641 \u0627\u0644\u062b\u0627\u0646\u064a!"
        lesson_ar = "\u0646\u0645\u0637 \u0646\u0627\u062c\u062d \u2014 \u064a\u0633\u062a\u062d\u0642 \u0627\u0644\u062a\u0643\u0631\u0627\u0631"

    elif result == "fail":
        # 1. Weak volume
        avg_vol = _get_avg_volume(decision["symbol"], bar["trading_date"], 20)
        vol_ratio = bar["volume"] / avg_vol if avg_vol > 0 else 0

        if avg_vol > 0 and vol_ratio < 0.8:
            error_type = "volume"
            reason_ar = f"\u0627\u0644\u062d\u062c\u0645 \u0636\u0639\u064a\u0641 ({vol_ratio:.1f}x) \u2014 \u0645\u0627 \u0623\u0643\u0651\u062f \u0627\u0644\u062d\u0631\u0643\u0629"
            lesson_ar = "\u0644\u0627 \u062a\u062f\u062e\u0644 \u0628\u062f\u0648\u0646 \u062a\u0623\u0643\u064a\u062f \u0627\u0644\u062d\u062c\u0645 (> 1.0x \u0627\u0644\u0645\u062a\u0648\u0633\u0637)"

        # 2. Stop too tight
        elif decision.get("stop_price") and decision.get("entry_price"):
            stop_dist = abs(decision["entry_price"] - decision["stop_price"]) / decision["entry_price"] * 100
            if stop_dist < 1.5:
                error_type = "stop"
                reason_ar = f"\u0627\u0644\u0633\u062a\u0648\u0628 \u0642\u0631\u064a\u0628 \u062c\u062f\u0627\u064b ({stop_dist:.1f}%) \u2014 \u0636\u0631\u0628\u0647 \u0628\u062a\u0630\u0628\u0630\u0628 \u0639\u0627\u062f\u064a"
                lesson_ar = "\u0648\u0633\u0651\u0639 \u0627\u0644\u0633\u062a\u0648\u0628 \u2014 \u0627\u0633\u062a\u062e\u062f\u0645 ATR \u0628\u062f\u0644 \u0646\u0633\u0628\u0629 \u062b\u0627\u0628\u062a\u0629"

        # 3. Entry in wrong zone
        elif bar.get("high") and decision.get("entry_price"):
            day_range = bar["high"] - bar["low"]
            if day_range > 0:
                entry_position = (decision["entry_price"] - bar["low"]) / day_range
                if entry_position > 0.8:
                    error_type = "zone"
                    reason_ar = "\u0627\u0644\u062f\u062e\u0648\u0644 \u0643\u0627\u0646 \u0628\u0645\u0646\u0637\u0642\u0629 \u0645\u0631\u062a\u0641\u0639\u0629 \u2014 \u0642\u0631\u064a\u0628 \u0645\u0646 \u0627\u0644\u0645\u0642\u0627\u0648\u0645\u0629"
                    lesson_ar = "\u0627\u0646\u062a\u0638\u0631 pullback \u0642\u0628\u0644 \u0627\u0644\u062f\u062e\u0648\u0644"

        # 4. Weak pattern
        if not error_type or error_type == "none":
            strat_id = decision.get("strategy_id")
            if strat_id:
                strat = _get_strategy_stats(strat_id)
                if strat and strat.get("profitable_rate", 0) < 0.55:
                    error_type = "pattern"
                    rate = strat["profitable_rate"] * 100
                    reason_ar = f"\u0646\u0645\u0637 \u0636\u0639\u064a\u0641 \u2014 \u0646\u0633\u0628\u0629 \u0627\u0644\u0646\u062c\u0627\u062d {rate:.0f}% \u0641\u0642\u0637"
                    lesson_ar = "\u062a\u062c\u0646\u0628 \u0627\u0644\u0627\u0633\u062a\u0631\u0627\u062a\u064a\u062c\u064a\u0627\u062a \u0628\u0646\u0633\u0628\u0629 \u0646\u062c\u0627\u062d \u0623\u0642\u0644 \u0645\u0646 55%"

        # 5. Market-wide drop
        if not error_type or error_type == "none":
            if _check_market_drop(bar["trading_date"]):
                error_type = "market"
                reason_ar = "\u0627\u0644\u0633\u0648\u0642 \u0643\u0643\u0644 \u0646\u0632\u0644 \u2014 \u0636\u063a\u0637 \u0628\u064a\u0639 \u0639\u0627\u0645"
                lesson_ar = "\u0631\u0627\u0642\u0628 \u0627\u0644\u0645\u0624\u0634\u0631 \u0627\u0644\u0639\u0627\u0645 \u0642\u0628\u0644 \u0627\u0644\u062f\u062e\u0648\u0644"

        # 6. General trend reversal
        if not error_type or error_type == "none":
            error_type = "trend"
            reason_ar = "\u0627\u0644\u0627\u062a\u062c\u0627\u0647 \u0639\u0643\u0633 \u2014 \u0627\u0644\u062d\u0631\u0643\u0629 \u0644\u0645 \u062a\u0633\u062a\u0645\u0631"
            lesson_ar = "\u062a\u0623\u0643\u062f \u0645\u0646 \u0627\u0644\u0627\u062a\u062c\u0627\u0647 \u0627\u0644\u0639\u0627\u0645 (ADX + EMA) \u0642\u0628\u0644 \u0627\u0644\u062f\u062e\u0648\u0644"

    elif result == "partial":
        entry = decision.get("entry_price", 0)
        if entry:
            pnl = ((bar["close"] - entry) / entry) * 100
            reason_ar = f"\u062a\u062d\u0631\u0643 \u0628\u0627\u0644\u0627\u062a\u062c\u0627\u0647 \u0627\u0644\u0635\u062d\u064a\u062d (+{pnl:.1f}%) \u0644\u0643\u0646 \u0645\u0627 \u0648\u0635\u0644 \u0627\u0644\u0647\u062f\u0641"
        else:
            reason_ar = "\u062a\u062d\u0631\u0643 \u0628\u0627\u0644\u0627\u062a\u062c\u0627\u0647 \u0627\u0644\u0635\u062d\u064a\u062d \u0644\u0643\u0646 \u0645\u0627 \u0648\u0635\u0644 \u0627\u0644\u0647\u062f\u0641"
        lesson_ar = "\u062e\u0630 \u0623\u0631\u0628\u0627\u062d \u062c\u0632\u0626\u064a\u0629 \u0639\u0646\u062f \u0645\u0633\u062a\u0648\u0649 \u0645\u0646\u0627\u0633\u0628"

    elif result == "ongoing":
        reason_ar = "\u0627\u0644\u0625\u0634\u0627\u0631\u0629 \u0644\u0633\u0647 \u0645\u0633\u062a\u0645\u0631\u0629 \u2014 \u0645\u0627 \u0648\u0635\u0644 \u0647\u062f\u0641 \u0648\u0644\u0627 \u0633\u062a\u0648\u0628"
        lesson_ar = "\u0631\u0627\u0642\u0628 \u0648\u062d\u062f\u062f \u0646\u0642\u0637\u0629 \u062e\u0631\u0648\u062c \u0648\u0627\u0636\u062d\u0629"

    return {
        "error_type": error_type,
        "reason_ar": reason_ar,
        "lesson_ar": lesson_ar,
    }


# ---------------------------------------------------------------------------
#  Main review function
# ---------------------------------------------------------------------------

def review_signals(target_date: str = None) -> dict:
    """Review ENTER decisions for a given trading day against next-day bars."""
    init_review_schema()

    if not target_date:
        target_date = _last_trading_day()
    # E-4: review_date is a UTC calendar date (runs at ~14:20 KWT = ~11:20
    # UTC, so it matches the local session date; existing rows needed no
    # conversion — see _tools/mixed_clock_census.md). Compared against
    # daily_bars.trading_date, which is also a UTC-derived session date.
    review_date = datetime.utcnow().date().isoformat()

    decisions = _get_pending_decisions(target_date)
    if not decisions:
        return {"status": "no_decisions", "date": target_date}

    all_reviews = []

    with _conn() as c:
        for dec in decisions:
            bar = _get_next_day_bars(dec["symbol"], target_date)

            if bar is None:
                # No next-day data yet
                review = {
                    "symbol": dec["symbol"],
                    "result": "no_data",
                    "pnl_pct": None,
                    "error_type": None,
                    "reason_ar": "\u0628\u064a\u0627\u0646\u0627\u062a \u0627\u0644\u064a\u0648\u0645 \u0627\u0644\u062a\u0627\u0644\u064a \u0645\u0648 \u0645\u062a\u0648\u0641\u0631\u0629",
                    "lesson_ar": "",
                }
                c.execute("""
                    INSERT OR REPLACE INTO signal_reviews
                    (review_date, market_date, symbol, smart_decision,
                     chosen_plan_source, strategy_id,
                     entry_price, stop_price, target_1, target_2,
                     result, confidence, data_quality, rr_ratio,
                     risk_flags, sector, decision_audit_id, reason_ar,
                     graded_mode, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'ungraded',CURRENT_TIMESTAMP)
                """, (review_date, target_date, dec["symbol"],
                      dec["smart_decision"], dec.get("chosen_plan_source"),
                      dec.get("strategy_id"), dec.get("entry_price"),
                      dec.get("stop_price"), dec.get("target_1"),
                      dec.get("target_2"), "no_data",
                      dec.get("confidence"), dec.get("data_quality"),
                      dec.get("rr_ratio"), dec.get("risk_flags"),
                      dec.get("sector"), dec["id"],
                      "\u0628\u064a\u0627\u0646\u0627\u062a \u0627\u0644\u064a\u0648\u0645 \u0627\u0644\u062a\u0627\u0644\u064a \u0645\u0648 \u0645\u062a\u0648\u0641\u0631\u0629"))
                all_reviews.append(review)
                continue

            classification = _classify_result(dec, bar)
            analysis = _analyze_reason(dec, bar, classification["result"])

            # E-1: live = graded on the very session the bar belongs to;
            # anything later is a backfill and must say so (C-27 reads this).
            graded_mode = "live" if bar["trading_date"] == review_date else "backfill"

            review = {
                "symbol": dec["symbol"],
                **classification,
                **analysis,
                "graded_mode": graded_mode,
            }

            c.execute("""
                INSERT OR REPLACE INTO signal_reviews
                (review_date, market_date, symbol, smart_decision,
                 chosen_plan_source, strategy_id,
                 entry_price, stop_price, target_1, target_2,
                 next_day_open, next_day_high, next_day_low, next_day_close,
                 next_day_volume,
                 result, pnl_pct, max_favorable, max_adverse,
                 hit_target_1, hit_stop,
                 error_type, reason_ar, lesson_ar,
                 confidence, data_quality, rr_ratio, risk_flags, sector,
                 decision_audit_id, graded_mode, days_tracked, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,CURRENT_TIMESTAMP)
            """, (review_date, target_date, dec["symbol"],
                  dec["smart_decision"], dec.get("chosen_plan_source"),
                  dec.get("strategy_id"), dec.get("entry_price"),
                  dec.get("stop_price"), dec.get("target_1"),
                  dec.get("target_2"),
                  bar["open"], bar["high"], bar["low"], bar["close"],
                  bar["volume"],
                  classification["result"], classification["pnl_pct"],
                  classification["max_favorable"], classification["max_adverse"],
                  classification["hit_target_1"], classification["hit_stop"],
                  analysis["error_type"], analysis["reason_ar"],
                  analysis["lesson_ar"],
                  dec.get("confidence"), dec.get("data_quality"),
                  dec.get("rr_ratio"), dec.get("risk_flags"),
                  dec.get("sector"), dec["id"], graded_mode))

            # Update decision_audit outcome
            c.execute("""
                UPDATE decision_audit
                SET outcome = ?, outcome_date = ?, actual_gain_pct = ?
                WHERE id = ?
            """, (classification["result"], review_date,
                  classification["pnl_pct"], dec["id"]))

            all_reviews.append(review)

    # Aggregate stats
    results = {}
    for r in all_reviews:
        res = r.get("result", "unknown")
        results[res] = results.get(res, 0) + 1

    error_counts = Counter(
        r["error_type"] for r in all_reviews
        if r.get("result") == "fail" and r.get("error_type")
    )
    top_error = error_counts.most_common(1)[0] if error_counts else None

    return {
        "status": "ok",
        "review_date": review_date,
        "market_date": target_date,
        "total_reviewed": len(decisions),
        "results": results,
        "top_error": top_error,
        "reviews": all_reviews,
    }


# ---------------------------------------------------------------------------
#  Dashboard helper
# ---------------------------------------------------------------------------

def review_liveness() -> dict:
    """E-1: loop liveness — a review loop that dies silently for 114 days
    must never be able to do that again. sessions_since_last_review counts
    daily_bars sessions strictly after the last review_date."""
    with _conn() as c:
        last = c.execute("SELECT MAX(review_date) FROM signal_reviews").fetchone()[0]
        if last:
            sessions = c.execute(
                "SELECT COUNT(DISTINCT trading_date) FROM daily_bars WHERE trading_date > ?",
                (last,)).fetchone()[0]
        else:
            sessions = None
    return {"last_review_date": last, "sessions_since_last_review": sessions}


def lifetime_stats() -> dict:
    """E-6: the loop's whole-of-life record for /dashboard/reviews.
    Counts come straight from signal_reviews with no bucket filtered out —
    no_data and ungraded are part of the record, not omissions."""
    with _conn() as c:
        results = {r[0]: r[1] for r in c.execute(
            "SELECT result, COUNT(*) FROM signal_reviews GROUP BY result")}
        # All four declared modes always present — an empty bucket is a 0
        # the page must be able to show, not an absent key.
        modes = {"live": 0, "backfill": 0, "legacy": 0, "ungraded": 0}
        for r in c.execute(
                "SELECT graded_mode, COUNT(*) FROM signal_reviews GROUP BY graded_mode"):
            modes[r[0] if r[0] is not None else "unknown"] = r[1]
        hits = c.execute(
            "SELECT COALESCE(SUM(hit_target_1),0), COALESCE(SUM(hit_stop),0), "
            "MIN(review_date) FROM signal_reviews").fetchone()
    graded_total = sum(results.values())
    resolved_total = graded_total - results.get("no_data", 0) - results.get("pending", 0)
    return {
        "graded_total": graded_total,
        "resolved_total": resolved_total,
        "results": results,
        "hit_target_1": hits[0],
        "hit_stop": hits[1],
        "by_graded_mode": modes,
        "first_review_date": hits[2],
        **review_liveness(),
    }


def get_reviews_for_dashboard(date_str: str = None) -> dict:
    """Return reviews formatted for dashboard HTML page."""
    init_review_schema()

    if not date_str:
        with _conn() as c:
            row = c.execute(
                "SELECT MAX(market_date) FROM signal_reviews WHERE result NOT IN ('no_data', 'pending')"
            ).fetchone()
            date_str = row[0] if row and row[0] else None

    if not date_str:
        return {"reviews": [], "summary": {}, "date": None,
                "lifetime": lifetime_stats(), **review_liveness()}

    with _conn() as c:
        rows = c.execute("""
            SELECT * FROM signal_reviews
            WHERE market_date = ?
            ORDER BY
                CASE result
                    WHEN 'success' THEN 1
                    WHEN 'partial' THEN 2
                    WHEN 'ongoing' THEN 3
                    WHEN 'fail' THEN 4
                    WHEN 'no_data' THEN 5
                END,
                pnl_pct DESC
        """, (date_str,)).fetchall()

    reviews = [dict(r) for r in rows]

    results = {}
    for r in reviews:
        res = r.get("result", "unknown")
        results[res] = results.get(res, 0) + 1

    total = len(reviews)
    success = results.get("success", 0)
    rate = round(success / total * 100) if total > 0 else 0

    errors = Counter(
        r["error_type"] for r in reviews
        if r.get("result") == "fail" and r.get("error_type")
    )
    top_error = errors.most_common(1)[0] if errors else None

    sorted_pnl = sorted(
        [r for r in reviews if r.get("pnl_pct") is not None],
        key=lambda x: x["pnl_pct"],
    )
    best = sorted_pnl[-1] if sorted_pnl else None
    worst = sorted_pnl[0] if sorted_pnl else None

    return {
        "date": date_str,
        "total": total,
        "success_rate": rate,
        "results": results,
        "top_error": {
            "type": top_error[0] if top_error else None,
            "count": top_error[1] if top_error else 0,
        },
        "best": {"symbol": best["symbol"], "pnl": best["pnl_pct"]} if best else None,
        "worst": {"symbol": worst["symbol"], "pnl": worst["pnl_pct"]} if worst else None,
        "reviews": reviews,
        "lifetime": lifetime_stats(),
        **review_liveness(),
    }


# ---------------------------------------------------------------------------
#  Bulk review of all pending decisions
# ---------------------------------------------------------------------------

def review_all_pending() -> list:
    """Review ALL pending decision_audit entries that have next-day bars available."""
    init_review_schema()
    with _conn() as c:
        dates = c.execute("""
            SELECT DISTINCT market_date FROM decision_audit
            WHERE outcome = 'pending'
            ORDER BY market_date
        """).fetchall()

    results = []
    for row in dates:
        md = row[0]
        summary = review_signals(md)
        results.append(summary)
    return results


# ---------------------------------------------------------------------------
#  Telegram notification
# ---------------------------------------------------------------------------

_ERROR_LABELS = {
    "volume": "\u062f\u062e\u0648\u0644 \u0628\u062f\u0648\u0646 \u062a\u0623\u0643\u064a\u062f \u062d\u062c\u0645",
    "trend": "\u0627\u0644\u0627\u062a\u062c\u0627\u0647 \u0639\u0643\u0633",
    "zone": "\u062f\u062e\u0648\u0644 \u0628\u0645\u0646\u0637\u0642\u0629 \u063a\u0644\u0637",
    "stop": "\u0633\u062a\u0648\u0628 \u0642\u0631\u064a\u0628",
    "market": "\u0627\u0644\u0633\u0648\u0642 \u0643\u0643\u0644 \u0646\u0632\u0644",
    "pattern": "\u0646\u0645\u0637 \u0636\u0639\u064a\u0641",
}


def _send_review_telegram(summary: dict) -> bool:
    """Send daily review summary via Telegram."""
    import requests as _req

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN") or _read_file("~/.telegram_bot_token")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("ADMIN_TELEGRAM_ID") or _read_file("~/.telegram_chat_id")
    if not bot_token or not chat_id:
        logger.warning("Telegram credentials not found")
        return False

    res = summary.get("results", {})
    total = summary.get("total_reviewed", 0)
    success = res.get("success", 0)
    partial = res.get("partial", 0)
    fail = res.get("fail", 0)
    ongoing = res.get("ongoing", 0)
    success_rate = round(success / total * 100) if total > 0 else 0

    top_err = summary.get("top_error")
    top_err_ar = _ERROR_LABELS.get(top_err[0], top_err[0]) if top_err else "\u0644\u0627 \u064a\u0648\u062c\u062f"

    # Best and worst
    reviews = summary.get("reviews", [])
    with_pnl = [r for r in reviews if r.get("pnl_pct") is not None]
    sorted_pnl = sorted(with_pnl, key=lambda x: x["pnl_pct"])
    best = sorted_pnl[-1] if sorted_pnl else None
    worst = sorted_pnl[0] if sorted_pnl else None

    best_line = f"\u2014 \u0623\u0641\u0636\u0644 \u0625\u0634\u0627\u0631\u0629: {best['symbol']} (+{best['pnl_pct']}%)" if best else ""
    worst_line = f"\u2014 \u0623\u0633\u0648\u0623 \u0625\u0634\u0627\u0631\u0629: {worst['symbol']} ({worst['pnl_pct']}%)" if worst else ""

    text = (
        f"\U0001f4ca <b>\u062a\u0642\u064a\u064a\u0645 \u0625\u0634\u0627\u0631\u0627\u062a {summary.get('market_date', '')}</b>\n\n"
        f"\u2705 \u0646\u062c\u0627\u062d: {success}\n"
        f"\u26a0\ufe0f \u062c\u0632\u0626\u064a: {partial}\n"
        f"\u274c \u0641\u0634\u0644: {fail}\n"
        f"\u23f3 \u0645\u0633\u062a\u0645\u0631: {ongoing}\n\n"
        f"\U0001f4c8 \u0646\u0633\u0628\u0629 \u0627\u0644\u0646\u062c\u0627\u062d: {success_rate}%\n"
        f"\U0001f4a1 \u0623\u0643\u0628\u0631 \u062e\u0637\u0623: {top_err_ar}\n\n"
        f"{best_line}\n{worst_line}"
    ).strip()

    try:
        r = _req.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        logger.error("Telegram send failed: %s", e)
        return False


# ---------------------------------------------------------------------------
#  Scheduler
# ---------------------------------------------------------------------------

async def review_scheduler():
    """Async fallback scheduler: 2:45 PM KWT (11:45 UTC), i.e. AFTER the
    14:00 close-backfill cron and the 14:20 daily_signal_review cron.
    Primary path is _tools/daily_signal_review.py; this only catches the
    case where the server is up but cron did not run. At 11:00 UTC it used
    to race the close job and grade against yesterday's bars → no_data."""
    _log = logging.getLogger("review_scheduler")
    _log.setLevel(logging.INFO)  # same reason as signal_review above
    _log.info("Signal review scheduler started")
    await asyncio.sleep(60)  # let startup complete

    while True:
        try:
            now = datetime.utcnow()
            # Target: 2:45 PM KWT = 11:45 UTC
            target = now.replace(hour=11, minute=45, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)

            # Skip Friday(4) and Saturday(5) in KWT time
            kwt_target = target + timedelta(hours=3)
            while kwt_target.weekday() in (4, 5):
                target += timedelta(days=1)
                kwt_target = target + timedelta(hours=3)

            wait_secs = (target - now).total_seconds()
            _log.info("Next signal review in %.1f hours", wait_secs / 3600)
            await asyncio.sleep(wait_secs)

            # Fallback only: skip when the 14:20 cron already reviewed today.
            # E-4: review_date is a UTC date, so compare against a UTC date.
            if review_liveness().get("last_review_date") == datetime.utcnow().date().isoformat():
                _log.info("Signal review already ran today (cron) — fallback skipped")
                await asyncio.sleep(23 * 3600)
                continue

            _log.info("Starting signal review...")
            loop = asyncio.get_event_loop()
            summary = await loop.run_in_executor(None, review_signals)

            if summary.get("status") == "ok":
                _send_review_telegram(summary)
                _log.info("Signal review complete: %s", summary["results"])
            else:
                _log.info("No decisions to review: %s", summary)

            # Wait at least 23 hours before next run
            await asyncio.sleep(23 * 3600)

        except Exception as e:
            _log.error("Signal review scheduler error: %s", e, exc_info=True)
            await asyncio.sleep(3600)
