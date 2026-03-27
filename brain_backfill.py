"""
brain_backfill.py — Historical backfill for Trading Brain.
Fetches 1yr daily bars from Bridge API, generates signal snapshots,
evaluates outcomes immediately (since future is known), and stores
in signal_snapshots with source='historical_backfill'.
"""
import os
import sys
import json
import time
import sqlite3
import logging
import requests
from datetime import datetime, timedelta

logger = logging.getLogger("brain_backfill")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")
BRIDGE_URL = "http://192.168.111.158:8059"
EVAL_DAYS = 7
MIN_WARMUP = 60  # skip first 60 bars (indicator warm-up)
MIN_CONFLUENCE = 50


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _fetch_daily_bars(symbol, bars=300):
    """Fetch daily bars with indicators from Bridge API."""
    try:
        r = requests.get(
            f"{BRIDGE_URL}/analysis",
            params={"symbol": symbol, "exchange": "KSE", "interval": "1D", "bars": bars},
            timeout=60,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        return data.get("bars", [])
    except Exception as e:
        logger.warning(f"Bridge fetch failed for {symbol}: {e}")
        return None


def _compute_snapshot(bar):
    """Compute indicator votes and confluence from a single bar."""
    rsi       = bar.get("rsi_14") or 0
    macd_hist = bar.get("macd_hist") or 0
    macd_val  = bar.get("macd") or 0
    ema9      = bar.get("ema_9") or 0
    ema20     = bar.get("ema_20") or 0
    ema50     = bar.get("ema_50") or 0
    adx       = bar.get("adx") or 0
    vol_ratio = bar.get("vol_ratio") or 0
    stoch_k   = bar.get("stoch_k") or 0
    bb_squeeze = bar.get("bb_squeeze") or False
    atr       = bar.get("atr_14") or 0

    # Indicator votes (same logic as signal_engine)
    ind_rsi   = 1 if rsi > 50 else 0
    ind_macd  = 1 if macd_hist > 0 else 0
    ind_ema   = 1 if ema9 > ema20 > 0 else 0
    ind_adx   = 1 if adx > 25 else 0
    ind_vol   = 1 if vol_ratio > 1.0 else 0
    ind_stoch = 1 if stoch_k > 50 else 0

    bullish    = ind_rsi + ind_macd + ind_ema + ind_adx + ind_vol + ind_stoch
    confluence = int(round((bullish / 6) * 100))

    # EMA stack state
    if ema9 > ema20 > ema50 > 0:
        ema_state = "bullish"
    elif ema9 < ema20 < ema50 and ema50 > 0:
        ema_state = "bearish"
    else:
        ema_state = "mixed"

    macd_state    = "bullish" if macd_hist > 0 else "bearish"
    macd_momentum = "accelerating" if abs(macd_hist) > abs(macd_val) * 0.1 else "decelerating"

    # Verdict
    if confluence >= 70 and ema_state == "bullish":
        verdict_key = "buy"
        verdict     = "شراء"
    elif confluence >= 50:
        verdict_key = "watch"
        verdict     = "مراقبة"
    elif confluence < 30:
        verdict_key = "avoid"
        verdict     = "تجنب"
    else:
        verdict_key = "neutral"
        verdict     = "حياد"

    # Trade state (simplified for backfill)
    if confluence >= 60 and vol_ratio > 1.2:
        trade_state = "ready"
    elif confluence >= 50:
        trade_state = "setup"
    else:
        trade_state = "discovery"

    # RSI divergence (simplified)
    rsi_divergence = None
    if rsi < 30:
        rsi_divergence = "oversold"
    elif rsi > 70:
        rsi_divergence = "overbought"

    return {
        "confluence":         confluence,
        "trade_state":        trade_state,
        "verdict":            verdict,
        "verdict_key":        verdict_key,
        "rsi_14":             round(rsi, 2) if rsi else None,
        "macd_state":         macd_state,
        "macd_momentum":      macd_momentum,
        "ema_state":          ema_state,
        "adx":                round(adx, 1) if adx else None,
        "vol_ratio":          round(vol_ratio, 2) if vol_ratio else None,
        "stoch_k":            round(stoch_k, 1) if stoch_k else None,
        "bb_squeeze":         1 if bb_squeeze else 0,
        "rsi_divergence":     rsi_divergence,
        "ema_cross_type":     None,
        "ema_cross_bars_ago": None,
        "atr_14":             round(atr, 3) if atr else None,
        "ind_rsi":            ind_rsi,
        "ind_macd":           ind_macd,
        "ind_ema":            ind_ema,
        "ind_adx":            ind_adx,
        "ind_vol":            ind_vol,
        "ind_stoch":          ind_stoch,
        "price":              bar.get("close", 0),
        "support":            None,
        "resistance":         None,
    }


def _evaluate_outcome(bars, idx, snapshot):
    """Evaluate outcome using bars[idx+1:idx+8] (7 days forward)."""
    price_at = snapshot["price"]
    atr      = snapshot["atr_14"] or price_at * 0.03
    if not price_at or price_at <= 0:
        return None

    future = bars[idx + 1: idx + 1 + EVAL_DAYS]
    if len(future) < EVAL_DAYS:
        return None  # not enough future bars

    max_high  = max(b.get("high", 0) for b in future)
    min_low   = min(b.get("low", 999999) for b in future)
    price_7d  = future[-1].get("close", price_at)

    max_gain_pct  = ((max_high - price_at) / price_at) * 100
    max_loss_pct  = ((price_at - min_low) / price_at) * 100
    outcome_pct   = ((price_7d - price_at) / price_at) * 100

    hit_threshold_pct = max((atr * 0.5 / price_at) * 100, 3.0)

    verdict_key = snapshot["verdict_key"]
    if verdict_key in ("buy", "watch"):
        if max_gain_pct >= hit_threshold_pct and max_loss_pct < hit_threshold_pct:
            outcome = "hit"
        elif max_loss_pct >= hit_threshold_pct and max_gain_pct < hit_threshold_pct:
            outcome = "miss"
        elif max_gain_pct >= hit_threshold_pct and max_loss_pct >= hit_threshold_pct:
            outcome = "ambiguous"
        else:
            outcome = "expired"
    elif verdict_key == "avoid":
        if max_loss_pct >= hit_threshold_pct and max_gain_pct < hit_threshold_pct:
            outcome = "hit"
        elif max_gain_pct >= hit_threshold_pct and max_loss_pct < hit_threshold_pct:
            outcome = "miss"
        else:
            outcome = "expired"
    else:
        outcome = "expired"

    return {
        "outcome":      outcome,
        "price_7d":     round(price_7d, 3),
        "outcome_pct":  round(outcome_pct, 2),
        "max_gain_pct": round(max_gain_pct, 2),
        "max_loss_pct": round(max_loss_pct, 2),
    }


def backfill_symbol(symbol, bars=None):
    """Backfill one symbol. Returns {snapshots: N, hits: N, misses: N, ...}"""
    if bars is None:
        bars = _fetch_daily_bars(symbol, 300)
    if not bars or len(bars) < MIN_WARMUP + EVAL_DAYS + 10:
        return {
            "symbol": symbol,
            "error":  "insufficient_bars",
            "count":  len(bars) if bars else 0,
        }

    conn  = _conn()
    stats = {
        "symbol":    symbol,
        "snapshots": 0,
        "hit":       0,
        "miss":      0,
        "expired":   0,
        "ambiguous": 0,
        "skipped":   0,
    }

    for i in range(MIN_WARMUP, len(bars) - EVAL_DAYS):
        bar      = bars[i]
        bar_time = bar.get("time", 0)
        if not bar_time:
            continue

        # Convert epoch to datetime
        signal_time = datetime.utcfromtimestamp(bar_time).strftime("%Y-%m-%d %H:%M:%S")
        signal_date = datetime.utcfromtimestamp(bar_time).strftime("%Y-%m-%d")

        # Dedup check
        existing = conn.execute(
            "SELECT id FROM signal_snapshots WHERE symbol=? AND source='historical_backfill' AND date(signal_time)=?",
            (symbol, signal_date),
        ).fetchone()
        if existing:
            stats["skipped"] += 1
            continue

        # Compute snapshot
        snap = _compute_snapshot(bar)
        if snap["confluence"] < MIN_CONFLUENCE:
            continue

        # Evaluate outcome
        outcome_data = _evaluate_outcome(bars, i, snap)
        if not outcome_data:
            continue

        # Insert
        conn.execute(
            """
            INSERT INTO signal_snapshots
            (symbol, signal_time, trade_state, verdict, verdict_key, confluence_score,
             price_at_signal, rsi_14, macd_state, macd_momentum, ema_state,
             adx, vol_ratio, stoch_k, bb_squeeze, rsi_divergence,
             ema_cross_type, ema_cross_bars_ago, support, resistance, atr_14,
             ind_rsi, ind_macd, ind_ema, ind_adx, ind_vol, ind_stoch,
             outcome, price_7d, outcome_pct, max_gain_pct, max_loss_pct,
             outcome_evaluated_at, source)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,'historical_backfill')
            """,
            (
                symbol, signal_time, snap["trade_state"], snap["verdict"], snap["verdict_key"],
                snap["confluence"], snap["price"], snap["rsi_14"], snap["macd_state"],
                snap["macd_momentum"], snap["ema_state"], snap["adx"], snap["vol_ratio"],
                snap["stoch_k"], snap["bb_squeeze"], snap["rsi_divergence"],
                snap["ema_cross_type"], snap["ema_cross_bars_ago"],
                snap["support"], snap["resistance"], snap["atr_14"],
                snap["ind_rsi"], snap["ind_macd"], snap["ind_ema"],
                snap["ind_adx"], snap["ind_vol"], snap["ind_stoch"],
                outcome_data["outcome"], outcome_data["price_7d"], outcome_data["outcome_pct"],
                outcome_data["max_gain_pct"], outcome_data["max_loss_pct"],
            ),
        )

        stats["snapshots"] += 1
        stats[outcome_data["outcome"]] = stats.get(outcome_data["outcome"], 0) + 1

    conn.commit()
    conn.close()
    return stats


def run_full_backfill():
    """Run backfill for all watchlist symbols."""
    from stock_radar import get_watchlist
    wl      = get_watchlist()
    symbols = [w["symbol"] for w in wl]
    if not symbols:
        logger.warning("Empty watchlist — nothing to backfill")
        return {"total": 0, "symbols": []}

    logger.info(f"Starting backfill for {len(symbols)} symbols...")
    all_stats        = []
    total_snapshots  = 0
    total_hits       = 0

    for idx, sym in enumerate(symbols):
        logger.info(f"[{idx+1}/{len(symbols)}] Backfilling {sym}...")
        stats = backfill_symbol(sym)
        all_stats.append(stats)
        total_snapshots += stats.get("snapshots", 0)
        total_hits      += stats.get("hit", 0)
        time.sleep(0.5)  # pace: avoid hammering Bridge

    logger.info(f"Backfill complete: {total_snapshots} snapshots, {total_hits} hits")

    # After backfill, update indicator performance
    from trading_brain import update_indicator_performance, adjust_weights
    update_indicator_performance()
    adjust_weights()
    logger.info("Indicator performance updated + weights adjusted")

    return {
        "total_symbols":    len(symbols),
        "total_snapshots":  total_snapshots,
        "total_hits":       total_hits,
        "symbols":          all_stats,
    }


def backfill_symbol_30m(symbol, bars=None):
    """Backfill one symbol with 30m data."""
    if bars is None:
        try:
            r = requests.get(
                f"{BRIDGE_URL}/analysis",
                params={"symbol": symbol, "exchange": "KSE", "interval": "30", "bars": 500},
                timeout=60
            )
            if r.status_code != 200:
                return {"symbol": symbol, "error": "bridge_http_" + str(r.status_code)}
            data = r.json()
            bars = data.get("bars", [])
        except Exception as e:
            return {"symbol": symbol, "error": str(e)}

    EVAL_BARS_30M = 14  # ~7 hours of 30m data
    if not bars or len(bars) < MIN_WARMUP + EVAL_BARS_30M + 10:
        return {"symbol": symbol, "error": "insufficient_bars", "count": len(bars) if bars else 0}

    conn = _conn()
    stats = {"symbol": symbol, "timeframe": "30m", "snapshots": 0, "hit": 0, "miss": 0, "expired": 0}

    for i in range(MIN_WARMUP, len(bars) - EVAL_BARS_30M):
        bar = bars[i]
        snap = _compute_snapshot(bar)
        if snap["confluence"] < MIN_CONFLUENCE:
            continue

        bar_time = bar.get("time", 0)
        if not bar_time:
            continue
        signal_time = datetime.utcfromtimestamp(bar_time).strftime("%Y-%m-%d %H:%M:%S")

        future = bars[i+1:i+1+EVAL_BARS_30M]
        if len(future) < EVAL_BARS_30M:
            continue

        price_at = snap["price"]
        atr = snap["atr_14"] or price_at * 0.02
        if not price_at or price_at <= 0:
            continue

        max_high = max(b.get("high", 0) for b in future)
        min_low = min(b.get("low", 999999) for b in future)
        price_end = future[-1].get("close", price_at)

        max_gain_pct = ((max_high - price_at) / price_at) * 100
        max_loss_pct = ((price_at - min_low) / price_at) * 100
        outcome_pct = ((price_end - price_at) / price_at) * 100

        hit_threshold_pct = max((atr * 0.3 / price_at) * 100, 1.5)

        verdict_key = snap["verdict_key"]
        if verdict_key in ("buy", "watch"):
            if max_gain_pct >= hit_threshold_pct and max_loss_pct < hit_threshold_pct:
                outcome = "hit"
            elif max_loss_pct >= hit_threshold_pct and max_gain_pct < hit_threshold_pct:
                outcome = "miss"
            else:
                outcome = "expired"
        else:
            outcome = "expired"

        conn.execute("""
            INSERT INTO signal_snapshots
            (symbol, signal_time, trade_state, verdict, verdict_key, confluence_score,
             price_at_signal, rsi_14, macd_state, macd_momentum, ema_state,
             adx, vol_ratio, stoch_k, bb_squeeze, rsi_divergence,
             ema_cross_type, ema_cross_bars_ago, support, resistance, atr_14,
             ind_rsi, ind_macd, ind_ema, ind_adx, ind_vol, ind_stoch,
             outcome, price_7d, outcome_pct, max_gain_pct, max_loss_pct,
             outcome_evaluated_at, source, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,'historical_backfill_30m','30m backfill')
        """, (
            symbol, signal_time, snap["trade_state"], snap["verdict"], snap["verdict_key"],
            snap["confluence"], snap["price"], snap["rsi_14"], snap["macd_state"],
            snap["macd_momentum"], snap["ema_state"], snap["adx"], snap["vol_ratio"],
            snap["stoch_k"], snap["bb_squeeze"], snap["rsi_divergence"],
            snap["ema_cross_type"], snap["ema_cross_bars_ago"],
            snap["support"], snap["resistance"], snap["atr_14"],
            snap["ind_rsi"], snap["ind_macd"], snap["ind_ema"],
            snap["ind_adx"], snap["ind_vol"], snap["ind_stoch"],
            outcome, round(price_end, 3), round(outcome_pct, 2),
            round(max_gain_pct, 2), round(max_loss_pct, 2),
        ))
        stats["snapshots"] += 1
        stats[outcome] = stats.get(outcome, 0) + 1

    conn.commit()
    conn.close()
    return stats


def run_full_backfill_30m():
    """Run 30m backfill for all watchlist symbols."""
    from stock_radar import get_watchlist
    wl = get_watchlist()
    symbols = [w["symbol"] for w in wl]
    if not symbols:
        logger.warning("Empty watchlist — nothing to 30m backfill")
        return {"total_snapshots": 0, "symbols": []}

    logger.info(f"Starting 30m backfill for {len(symbols)} symbols...")
    all_stats = []
    total = 0

    for idx, sym in enumerate(symbols):
        logger.info(f"[{idx+1}/{len(symbols)}] 30m backfill {sym}...")
        stats = backfill_symbol_30m(sym)
        all_stats.append(stats)
        total += stats.get("snapshots", 0)
        time.sleep(0.5)

    from trading_brain import update_indicator_performance, adjust_weights
    update_indicator_performance()
    adjust_weights()
    logger.info(f"30m backfill complete: {total} snapshots")

    return {"total_symbols": len(symbols), "total_snapshots": total, "symbols": all_stats}


if __name__ == "__main__":
    result = run_full_backfill()
    print(json.dumps(result, default=str, indent=2))
