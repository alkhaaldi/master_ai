"""
stock_radar.py - EMA Crossover Radar for KSE stocks.
Background poller: checks EMA9/21 on 30m candles, sends Telegram alerts.
Phase: Trading Advisor Phase 2 — Radar.

Tables in life.db:
  stock_radar_watchlist  — symbols to monitor
  stock_radar_state      — last signal per symbol (dedup)
  stock_radar_events     — signal log

TG commands: /radar, /radar_add, /radar_remove, /radar_check, /radar_last
"""
import os
import json
import time
import sqlite3
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Integration: Tier2/3 modules
try:
    from coalesced_executor import CoalescedExecutor
    _radar_coalesced = CoalescedExecutor("radar_refresh")
except ImportError:
    _radar_coalesced = None
try:
    from processing_cursor import ProcessingCursor
    _signal_cursor = ProcessingCursor("radar_last_signal_id", cursor_type="id")
except ImportError:
    _signal_cursor = None

logger = logging.getLogger("stock_radar")

DATA_DIR = Path(__file__).parent / "data"
LIFE_DB = DATA_DIR / "life.db"
CONFIG_FILE = DATA_DIR / "ema_radar.json"

DEFAULT_CONFIG = {
    "enabled": True,
    "timeframe": "30m",
    "fast_ema": 9,
    "slow_ema": 21,
    "poll_seconds": 90,
    "cooldown_minutes": 45,
    "symbols": ["ALL"],
}


def _get_config():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return DEFAULT_CONFIG


def _save_config(cfg):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))


def _db():
    conn = sqlite3.connect(str(LIFE_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ═══ DB Schema ═══

def init_radar_db():
    conn = _db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS stock_radar_watchlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        exchange TEXT NOT NULL DEFAULT 'KSE',
        timeframe TEXT NOT NULL DEFAULT '30m',
        fast_len INTEGER NOT NULL DEFAULT 9,
        slow_len INTEGER NOT NULL DEFAULT 21,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, exchange, timeframe, fast_len, slow_len)
    );
    CREATE TABLE IF NOT EXISTS stock_radar_state (
        symbol TEXT NOT NULL,
        exchange TEXT NOT NULL DEFAULT 'KSE',
        timeframe TEXT NOT NULL,
        fast_len INTEGER NOT NULL,
        slow_len INTEGER NOT NULL,
        last_signal TEXT,
        last_signal_candle_time TEXT,
        last_alert_time TEXT,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(symbol, exchange, timeframe, fast_len, slow_len)
    );
    CREATE TABLE IF NOT EXISTS stock_radar_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        exchange TEXT NOT NULL DEFAULT 'KSE',
        timeframe TEXT NOT NULL,
        signal_type TEXT NOT NULL,
        price REAL,
        candle_time TEXT,
        ema_fast REAL,
        ema_slow REAL,
        source TEXT NOT NULL DEFAULT 'local_radar',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # Daily Context Layer table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_radar_daily (
            symbol TEXT NOT NULL, exchange TEXT NOT NULL DEFAULT 'KSE',
            price REAL, trend TEXT, rsi REAL, support REAL, resistance REAL,
            score INTEGER, score_class TEXT, verdict TEXT,
            volume INTEGER, vol_ratio REAL, change_pct REAL,
            source_timeframe TEXT NOT NULL DEFAULT '1D',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(symbol, exchange))
    """)
    # Add MACD + confluence columns (ALTER TABLE, safe if already exists)
    for col_sql in [
        "ALTER TABLE stock_radar_daily ADD COLUMN macd REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN macd_signal REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN macd_histogram REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN macd_cross TEXT DEFAULT 'none'",
        "ALTER TABLE stock_radar_daily ADD COLUMN daily_ema9 REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN daily_ema21 REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN daily_ema_cross TEXT DEFAULT 'none'",
        "ALTER TABLE stock_radar_daily ADD COLUMN confluence_score INTEGER DEFAULT 0",
        "ALTER TABLE stock_radar_daily ADD COLUMN confluence_direction TEXT DEFAULT 'neutral'",
        "ALTER TABLE stock_radar_daily ADD COLUMN avg_volume INTEGER",
        "ALTER TABLE stock_radar_daily ADD COLUMN volume_spike BOOLEAN DEFAULT 0",
        "ALTER TABLE stock_radar_daily ADD COLUMN macd_above_zero BOOLEAN DEFAULT 0",
        "ALTER TABLE stock_radar_daily ADD COLUMN stoch_k REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN adx REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN rsi_divergence TEXT",
        "ALTER TABLE stock_radar_daily ADD COLUMN atr REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN ema_fast REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN ema_slow REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN bb_squeeze BOOLEAN DEFAULT 0",
        "ALTER TABLE stock_radar_daily ADD COLUMN bb_bandwidth REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN captured_at TEXT",
        # Real multi-session average volume, from full-day history. The existing
        # `volume` column is a mid-session snapshot - captured_at is 10:40 local
        # on a 09:00-13:00 session - so it understates a day by 2-6x. avg_volume,
        # avg_daily_volume and avg_daily_value are all zero in every row and were
        # never populated. New columns, nothing overwritten.
        "ALTER TABLE stock_radar_daily ADD COLUMN avg_vol_20 REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN avg_vol_60 REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN avg_vol_sessions_20 INTEGER",
        "ALTER TABLE stock_radar_daily ADD COLUMN avg_vol_sessions_60 INTEGER",
        "ALTER TABLE stock_radar_daily ADD COLUMN avg_vol_as_of TEXT",
        "ALTER TABLE stock_radar_daily ADD COLUMN avg_vol_source TEXT",
        # Median, not mean: one block trade lies to a mean and barely moves a
        # median. liq_vol takes the smaller of the two windows because liquidity
        # risk is always on the low side - if the stock has gone quiet lately,
        # that is the number you will actually be trading against.
        "ALTER TABLE stock_radar_daily ADD COLUMN med_vol_20 REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN med_vol_60 REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN liq_vol REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN liq_value_kwd REAL",
        # no DEFAULT on purpose: NULL means "provenance unknown", 0 must only
        # ever mean "verified captured after the close"
        "ALTER TABLE stock_radar_daily ADD COLUMN market_was_open BOOLEAN",
    ]:
        try:
            conn.execute(col_sql)
        except Exception:
            pass  # column already exists
    # Add EMA persistence columns to stock_radar_state (survives restart)
    for col_sql in [
        "ALTER TABLE stock_radar_state ADD COLUMN prev_ema_fast REAL",
        "ALTER TABLE stock_radar_state ADD COLUMN prev_ema_slow REAL",
    ]:
        try:
            conn.execute(col_sql)
        except Exception:
            pass
    # Add enriched columns to stock_radar_events (safe if already exists)
    for col_sql in [
        "ALTER TABLE stock_radar_events ADD COLUMN rsi REAL",
        "ALTER TABLE stock_radar_events ADD COLUMN vwap REAL",
        "ALTER TABLE stock_radar_events ADD COLUMN volume INTEGER DEFAULT 0",
        "ALTER TABLE stock_radar_events ADD COLUMN score INTEGER DEFAULT 0",
        "ALTER TABLE stock_radar_events ADD COLUMN score_class TEXT",
        "ALTER TABLE stock_radar_events ADD COLUMN verdict TEXT",
        "ALTER TABLE stock_radar_events ADD COLUMN support REAL",
        "ALTER TABLE stock_radar_events ADD COLUMN resistance REAL",
        "ALTER TABLE stock_radar_events ADD COLUMN vol_ratio REAL",
    ]:
        try:
            conn.execute(col_sql)
        except Exception:
            pass
    conn.commit()
    conn.close()
    logger.info("Radar DB tables ready")


# ═══ Watchlist Management ═══

def add_to_watchlist(symbol, timeframe="30m", fast=9, slow=21):
    from tv_data import resolve_symbol, KSE_STOCKS
    ticker = resolve_symbol(symbol)
    name_ar = KSE_STOCKS.get(ticker, ticker)
    conn = _db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO stock_radar_watchlist (symbol, exchange, timeframe, fast_len, slow_len) VALUES (?,?,?,?,?)",
            (ticker, "KSE", timeframe, fast, slow))
        conn.commit()
        return {"ok": True, "ticker": ticker, "name_ar": name_ar}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def remove_from_watchlist(symbol):
    from tv_data import resolve_symbol
    ticker = resolve_symbol(symbol)
    conn = _db()
    conn.execute("DELETE FROM stock_radar_watchlist WHERE symbol=?", (ticker,))
    conn.commit()
    n = conn.total_changes
    conn.close()
    return {"ok": True, "ticker": ticker, "removed": n > 0}


UNIVERSE_DEFAULTS = {"exchange": "KSE", "timeframe": "30m",
                     "fast_len": 9, "slow_len": 21, "is_active": 1}


def sync_watchlist_from_universe(dry_run: bool = False) -> dict:
    """Make stock_radar_watchlist match KSE_STOCKS, which is the universe.

    KSE_STOCKS is loaded from data/kse_stocks.csv and is the single definition
    of what exists. The watchlist table is a per-symbol settings row, not a
    second opinion about which symbols there are - but the two had drifted:
    four rows in the csv had lost a newline, so four symbols never reached
    either, and the table kept 128 while the universe was repaired to 132.

    Adds missing symbols with the defaults every existing row already uses.
    Never deletes: a symbol in the table but not the universe is reported and
    left alone, because that is a question about the csv, not an answer.
    """
    from tv_data import KSE_STOCKS
    conn = _db()
    have = {r["symbol"] for r in
            conn.execute("SELECT symbol FROM stock_radar_watchlist").fetchall()}
    universe = set(KSE_STOCKS)
    missing = sorted(universe - have)
    extra = sorted(have - universe)
    if missing and not dry_run:
        conn.executemany(
            "INSERT INTO stock_radar_watchlist "
            "(symbol, exchange, timeframe, fast_len, slow_len, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(s, UNIVERSE_DEFAULTS["exchange"], UNIVERSE_DEFAULTS["timeframe"],
              UNIVERSE_DEFAULTS["fast_len"], UNIVERSE_DEFAULTS["slow_len"],
              UNIVERSE_DEFAULTS["is_active"]) for s in missing])
        conn.commit()
        logger.warning("watchlist synced from universe: added %s", missing)
    if extra:
        logger.warning("in watchlist but not in the universe (left alone): %s", extra)
    total = conn.execute("SELECT COUNT(*) FROM stock_radar_watchlist").fetchone()[0]
    conn.close()
    return {"universe": len(universe), "watchlist": total,
            "added": [] if dry_run else missing, "would_add": missing if dry_run else [],
            "not_in_universe": extra}


def get_watchlist():
    conn = _db()
    rows = conn.execute(
        "SELECT symbol, timeframe, fast_len, slow_len, is_active FROM stock_radar_watchlist WHERE is_active=1"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_events(limit=10):
    conn = _db()
    rows = conn.execute(
        "SELECT * FROM stock_radar_events ORDER BY created_at DESC LIMIT ?",
        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══ EMA Computation ═══

def _compute_ema(closes, period):
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for p in closes[period:]:
        ema = p * k + ema * (1 - k)
    return round(ema, 3)


# ═══ MACD Computation ═══

def _compute_macd(closes, fast=12, slow=26, signal=9):
    """Calculate MACD, Signal, Histogram. Returns dict or None."""
    if len(closes) < slow + signal:
        return None
    # Build MACD line series from slow onward
    macd_line = []
    for i in range(slow, len(closes) + 1):
        ef = _compute_ema(closes[:i], fast)
        es = _compute_ema(closes[:i], slow)
        if ef is not None and es is not None:
            macd_line.append(ef - es)
    if len(macd_line) < signal:
        return None
    signal_line = _compute_ema(macd_line, signal)
    if signal_line is None:
        return None
    macd_current = macd_line[-1]
    histogram = macd_current - signal_line
    # MACD cross detection
    cross = "none"
    if len(macd_line) >= 2:
        prev_signal = _compute_ema(macd_line[:-1], signal)
        if prev_signal is not None:
            prev_hist = macd_line[-2] - prev_signal
            if prev_hist <= 0 and histogram > 0:
                cross = "bullish"
            elif prev_hist >= 0 and histogram < 0:
                cross = "bearish"
    return {
        "macd": round(macd_current, 3),
        "signal": round(signal_line, 3),
        "histogram": round(histogram, 3),
        "cross": cross,
        "above_zero": macd_current > 0,
    }


# ═══ Multi-TF Confluence ═══

def _detect_market_regime(adx):
    """Detect market regime from ADX value."""
    if adx is None:
        return "unknown"
    if adx >= 25:
        return "trending"
    elif adx <= 20:
        return "ranging"
    return "transition"


def _compute_confluence(signal_30m, daily_data):
    """Multi-timeframe confluence scoring. Uses brain weights if available."""
    try:
        from trading_brain import get_indicator_weights
        weights = get_indicator_weights()
        if weights and any(w != 1.0 for w in weights.values()):
            return _compute_confluence_weighted(signal_30m, daily_data, weights)
    except Exception:
        pass
    return _compute_confluence_fixed(signal_30m, daily_data)


def _compute_confluence_weighted(signal_30m, daily_data, weights):
    """Weighted confluence using brain's adaptive weights."""
    result = _compute_confluence_fixed(signal_30m, daily_data)
    score = result["confluence_score"]

    # Apply brain weights to score components
    ema_w = weights.get("ema", 1.0)
    macd_w = weights.get("macd", 1.0)
    rsi_w = weights.get("rsi", 1.0)
    vol_w = weights.get("vol", 1.0)

    # Recompute with weights
    weighted_score = 0
    ema_cross_30m = signal_30m.get("ema_cross", "none") if signal_30m else "none"
    if ema_cross_30m in ("bullish", "bearish"):
        weighted_score += (25 if ema_cross_30m == "bullish" else -25) * ema_w
    daily_ema_cross = daily_data.get("daily_ema_cross", "none")
    if daily_ema_cross in ("bullish", "bearish"):
        weighted_score += (30 if daily_ema_cross == "bullish" else -30) * ema_w
    macd_cross = daily_data.get("macd_cross", "none")
    if macd_cross in ("bullish", "bearish"):
        weighted_score += (20 if macd_cross == "bullish" else -20) * macd_w
    if daily_data.get("macd_above_zero"):
        weighted_score += 10 * macd_w
    elif daily_data.get("macd_above_zero") is False:
        weighted_score -= 10 * macd_w
    vol_ratio = daily_data.get("vol_ratio", 1)
    if vol_ratio >= 3:
        weighted_score += 15 * vol_w
    elif vol_ratio >= 2:
        weighted_score += 10 * vol_w
    rsi = daily_data.get("rsi", 50)
    if rsi and 40 <= rsi <= 60:
        weighted_score += 5 * rsi_w
    elif rsi and rsi > 70:
        weighted_score -= 10 * rsi_w
    elif rsi and rsi < 30:
        weighted_score += 15 * rsi_w

    weighted_score = int(round(weighted_score))
    direction = "bullish" if weighted_score > 0 else "bearish" if weighted_score < 0 else "neutral"
    strength = "strong" if abs(weighted_score) >= 60 else "moderate" if abs(weighted_score) >= 30 else "weak"

    result["confluence_score"] = weighted_score
    result["direction"] = direction
    result["strength"] = strength
    result["brain_weighted"] = True
    return result


def _compute_confluence_fixed(signal_30m, daily_data):
    """Multi-timeframe confluence scoring (fixed weights). Higher abs = stronger signal."""
    score = 0
    reasons = []

    # 30m EMA cross
    ema_cross_30m = signal_30m.get("ema_cross", "none") if signal_30m else "none"
    if ema_cross_30m == "bullish":
        score += 25
        reasons.append("30m EMA \u0635\u0627\u0639\u062f")
    elif ema_cross_30m == "bearish":
        score -= 25
        reasons.append("30m EMA \u0647\u0627\u0628\u0637")

    # Daily EMA cross
    daily_ema_cross = daily_data.get("daily_ema_cross", "none")
    if daily_ema_cross == "bullish":
        score += 30
        reasons.append("Daily EMA \u0635\u0627\u0639\u062f")
    elif daily_ema_cross == "bearish":
        score -= 30
        reasons.append("Daily EMA \u0647\u0627\u0628\u0637")

    # MACD daily
    macd_cross = daily_data.get("macd_cross", "none")
    if macd_cross == "bullish":
        score += 20
        reasons.append("MACD \u062a\u0642\u0627\u0637\u0639 \u0635\u0627\u0639\u062f")
    elif macd_cross == "bearish":
        score -= 20
        reasons.append("MACD \u062a\u0642\u0627\u0637\u0639 \u0647\u0627\u0628\u0637")

    # MACD above/below zero
    if daily_data.get("macd_above_zero"):
        score += 10
        reasons.append("MACD \u0641\u0648\u0642 \u0627\u0644\u0635\u0641\u0631")
    elif daily_data.get("macd_above_zero") is False:
        score -= 10

    # Volume spike
    vol_ratio = daily_data.get("vol_ratio", 1)
    if vol_ratio >= 3:
        score += 15
        reasons.append(f"\u062d\u062c\u0645 \u00d7{vol_ratio:.1f} (spike)")
    elif vol_ratio >= 2:
        score += 10
        reasons.append(f"\u062d\u062c\u0645 \u00d7{vol_ratio:.1f}")

    # RSI
    rsi = daily_data.get("rsi", 50)
    if rsi and 40 <= rsi <= 60:
        score += 5
    elif rsi and rsi > 70:
        score -= 10
        reasons.append("RSI \u062a\u0634\u0628\u0639 \u0634\u0631\u0627\u0626\u064a")
    elif rsi and rsi < 30:
        score += 15
        reasons.append("RSI \u062a\u0634\u0628\u0639 \u0628\u064a\u0639\u064a \u2014 \u0641\u0631\u0635\u0629")

    # Regime adjustment
    adx = daily_data.get("adx")
    regime = _detect_market_regime(adx)
    if regime == "ranging":
        score = int(score * 0.7) if abs(score) > 20 else score
        reasons.append("\u0633\u0648\u0642 \u0639\u0631\u0636\u064a (ADX<20)")
    elif regime == "trending" and abs(score) > 30:
        score = int(score * 1.15)
        reasons.append("\u0633\u0648\u0642 \u0627\u062a\u062c\u0627\u0647\u064a (ADX>25)")

    direction = "bullish" if score > 0 else "bearish" if score < 0 else "neutral"
    strength = "strong" if abs(score) >= 60 else "moderate" if abs(score) >= 30 else "weak"
    strength_ar = "\u0642\u0648\u064a" if strength == "strong" else "\u0645\u062a\u0648\u0633\u0637" if strength == "moderate" else "\u0636\u0639\u064a\u0641"

    return {
        "confluence_score": score,
        "direction": direction,
        "strength": strength,
        "strength_ar": strength_ar,
        "regime": regime,
        "reasons": reasons,
    }


# ═══ Cross Detection ═══

def _detect_cross(closes, fast_len, slow_len):
    """Detect EMA cross on last 2 CLOSED candles only."""
    if len(closes) < max(fast_len, slow_len) + 2:
        return None, None, None
    # Use closes[:-1] = all closed candles (exclude current open candle)
    closed = closes[:-1]
    # Current (last closed)
    curr_fast = _compute_ema(closed, fast_len)
    curr_slow = _compute_ema(closed, slow_len)
    # Previous (second-to-last closed)
    prev_closed = closed[:-1]
    prev_fast = _compute_ema(prev_closed, fast_len)
    prev_slow = _compute_ema(prev_closed, slow_len)
    if None in (curr_fast, curr_slow, prev_fast, prev_slow):
        return None, curr_fast, curr_slow
    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return "bullish_cross", curr_fast, curr_slow
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return "bearish_cross", curr_fast, curr_slow
    return None, curr_fast, curr_slow


def _should_alert(symbol, signal_type, candle_time, cooldown_min=45):
    """Check if we should send alert (dedup + cooldown)."""
    conn = _db()
    row = conn.execute(
        "SELECT last_signal, last_signal_candle_time, last_alert_time FROM stock_radar_state WHERE symbol=? AND timeframe='30m'",
        (symbol,)).fetchone()
    conn.close()
    if not row:
        return True
    # Same signal on same candle = already sent
    if row["last_signal"] == signal_type and row["last_signal_candle_time"] == candle_time:
        return False
    # Cooldown check
    if row["last_alert_time"]:
        try:
            last = datetime.fromisoformat(row["last_alert_time"])
            if datetime.utcnow() - last < timedelta(minutes=cooldown_min):
                return False
        except Exception:
            pass
    return True


def _record_signal(symbol, signal_type, candle_time, price, ema_fast, ema_slow, enriched=None):
    """Record signal in state + events tables with enriched data."""
    now = datetime.utcnow().isoformat()
    conn = _db()
    conn.execute("""
        INSERT OR REPLACE INTO stock_radar_state
        (symbol, exchange, timeframe, fast_len, slow_len, last_signal, last_signal_candle_time, last_alert_time, updated_at)
        VALUES (?, 'KSE', '30m', 9, 21, ?, ?, ?, ?)
    """, (symbol, signal_type, candle_time, now, now))
    # Base insert
    rsi = enriched.get("rsi") if enriched else None
    vwap = enriched.get("vwap") if enriched else None
    volume = enriched.get("volume", 0) if enriched else 0
    score = enriched.get("score", 0) if enriched else 0
    score_class = enriched.get("score_class", "") if enriched else ""
    verdict = enriched.get("verdict", "") if enriched else ""
    support = enriched.get("support") if enriched else None
    resistance = enriched.get("resistance") if enriched else None
    vol_ratio = enriched.get("vol_ratio", 0) if enriched else 0
    conn.execute("""
        INSERT INTO stock_radar_events
        (symbol, exchange, timeframe, signal_type, price, candle_time, ema_fast, ema_slow, source,
         rsi, vwap, volume, score, score_class, verdict, support, resistance, vol_ratio)
        VALUES (?, 'KSE', '30m', ?, ?, ?, ?, ?, 'local_radar', ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (symbol, signal_type, price, candle_time, ema_fast, ema_slow,
          rsi, vwap, volume, score, score_class, verdict, support, resistance, vol_ratio))
    conn.commit()
    conn.close()


# ═══ Alert Formatting ═══

def _format_alert(symbol, signal_type, price, ema_fast, ema_slow, candle_time, enriched=None):
    from tv_data import KSE_STOCKS
    name_ar = KSE_STOCKS.get(symbol, symbol)
    if signal_type == "bullish_cross":
        emoji = "\U0001f7e2"
        signal_ar = "\u062a\u0642\u0627\u0637\u0639 \u0635\u0627\u0639\u062f EMA9 \u0641\u0648\u0642 EMA21"
    else:
        emoji = "\U0001f534"
        signal_ar = "\u062a\u0642\u0627\u0637\u0639 \u0647\u0627\u0628\u0637 EMA9 \u062a\u062d\u062a EMA21"
    lines = [
        f"\U0001f4e1 \u0631\u0627\u062f\u0627\u0631 EMA 30m",
        "",
        f"\u0627\u0644\u0633\u0647\u0645: {name_ar} ({symbol})",
        f"\u0627\u0644\u0625\u0634\u0627\u0631\u0629: {emoji} {signal_ar}",
    ]
    if enriched:
        cp = enriched.get("change_pct", 0)
        arrow = "\u2b06\ufe0f" if cp >= 0 else "\u2b07\ufe0f"
        lines.append(f"\u0627\u0644\u0633\u0639\u0631: {price} \u0641\u0644\u0633 {arrow} {cp:+.2f}%")
        rsi = enriched.get("rsi")
        if rsi:
            rz = "\u062a\u0634\u0628\u0639 \u0634\u0631\u0627\u0626\u064a" if rsi >= 70 else "\u062a\u0634\u0628\u0639 \u0628\u064a\u0639\u064a" if rsi <= 30 else "\u0645\u062d\u0627\u064a\u062f"
            lines.append(f"RSI(14): {rsi} ({rz})")
        vwap = enriched.get("vwap")
        if vwap:
            vp = "\u0641\u0648\u0642" if price > vwap else "\u062a\u062d\u062a"
            lines.append(f"VWAP: {vwap} (\u0627\u0644\u0633\u0639\u0631 {vp})")
        lines.append(f"EMA9: {ema_fast} | EMA21: {ema_slow}")
        sup = enriched.get("support")
        res = enriched.get("resistance")
        if sup and res:
            lines.append(f"\u0627\u0644\u062f\u0639\u0645: {sup} | \u0627\u0644\u0645\u0642\u0627\u0648\u0645\u0629: {res}")
        vr = enriched.get("vol_ratio", 0)
        vol = enriched.get("volume", 0)
        if vol:
            lines.append(f"\u0627\u0644\u062d\u062c\u0645: {vol:,} (x{vr:.1f} \u0645\u0646 \u0627\u0644\u0645\u062a\u0648\u0633\u0637)")
        verdict = enriched.get("verdict", "")
        sc = enriched.get("score", 0)
        sc_cls = enriched.get("score_class", "")
        if verdict or sc:
            lines.append("")
            if sc:
                lines.append(f"Score: {sc}/100 (Class {sc_cls})")
            if verdict:
                lines.append(f"\u0627\u0644\u062d\u0643\u0645: {verdict}")
    else:
        lines.append(f"\u0627\u0644\u0633\u0639\u0631: {price} \u0641\u0644\u0633")
        lines.append(f"EMA9: {ema_fast} | EMA21: {ema_slow}")
    return chr(10).join(lines)


# ═══ Smart Verdict ═══

def _smart_verdict(signal, rsi, vwap, price, vol_sig, ema_f, ema_s):
    """One-line Arabic verdict based on combined indicators."""
    vol_type = vol_sig.get("signal", "normal") if vol_sig else "normal"
    if signal == "bullish_cross":
        if rsi and rsi > 65 and vol_type in ("high_volume", "extreme_volume"):
            return "\U0001f525 \u0627\u062e\u062a\u0631\u0627\u0642 \u0645\u062d\u062a\u0645\u0644"
        if rsi and rsi < 35:
            return "\U0001f7e2 \u0627\u0631\u062a\u062f\u0627\u062f \u0645\u0646 \u0642\u0627\u0639 \u2014 \u0645\u062a\u0627\u0628\u0639\u0629"
        return "\U0001f7e2 \u0632\u062e\u0645 \u0635\u0627\u0639\u062f \u2014 \u0645\u062a\u0627\u0628\u0639\u0629"
    if signal == "bearish_cross":
        if rsi and rsi < 30:
            return "\U0001f534 \u0632\u062e\u0645 \u0636\u0639\u064a\u0641 + \u062a\u0634\u0628\u0639 \u0628\u064a\u0639\u064a"
        if vol_type in ("high_volume", "extreme_volume"):
            return "\u26A0\uFE0F \u062d\u0630\u0631 \u2014 \u0636\u063a\u0637 \u0628\u064a\u0639\u064a \u0628\u062d\u062c\u0645"
        return "\U0001f534 \u0632\u062e\u0645 \u0636\u0639\u064a\u0641 \u2014 \u062d\u0630\u0631"
    return ""


# ═══ Signal Score (0-100) ═══

def _compute_score(signal, rsi, vwap, price, vol_sig, ema_f, ema_s, sr):
    """Compute numeric score 0-100 for signal quality using Brain weights."""
    if not signal:
        return 0, "D"

    # Try brain weights
    try:
        from trading_brain import get_indicator_weights
        weights = get_indicator_weights()
    except Exception:
        weights = {}

    w_ema = weights.get("ema", 1.0)
    w_rsi = weights.get("rsi", 1.0)
    w_vol = weights.get("vol", 1.0)
    w_macd = weights.get("macd", 1.0)
    w_adx = weights.get("adx", 1.0)

    score = 0
    vol_ratio = vol_sig.get("ratio", 0) if vol_sig else 0
    is_bull = signal == "bullish_cross"

    # EMA cross base (weighted)
    score += int(25 * w_ema)

    # RSI alignment (weighted)
    if rsi:
        if is_bull:
            if 40 <= rsi <= 65: score += int(15 * w_rsi)
            elif rsi < 35: score += int(10 * w_rsi)
            elif rsi > 75: score -= int(10 * w_rsi)
        else:
            if 35 <= rsi <= 60: score += int(15 * w_rsi)
            elif rsi > 65: score += int(10 * w_rsi)
            elif rsi < 25: score -= int(10 * w_rsi)

    # VWAP alignment (weighted by macd as proxy)
    if vwap and price:
        if is_bull and price > vwap: score += int(15 * w_macd)
        elif not is_bull and price < vwap: score += int(15 * w_macd)
        elif is_bull and price < vwap * 0.97: score += int(5 * w_macd)

    # Volume confirmation (weighted)
    if vol_ratio >= 2.5: score += int(20 * w_vol)
    elif vol_ratio >= 1.5: score += int(15 * w_vol)
    elif vol_ratio >= 1.0: score += int(5 * w_vol)
    elif vol_ratio < 0.3: score -= int(15 * w_vol)

    # S/R proximity (weighted by adx)
    if sr and price:
        res1 = sr.get("resistance_1", 0)
        sup1 = sr.get("support_1", 0)
        if is_bull and res1 and price > res1 * 0.98: score -= int(10 * w_adx)
        if not is_bull and sup1 and price < sup1 * 1.02: score -= int(10 * w_adx)

    # Trend confirmation (EMA gap)
    if ema_f and ema_s:
        gap_pct = abs(ema_f - ema_s) / ema_s * 100 if ema_s else 0
        if gap_pct > 1.5: score += int(10 * w_ema)
        elif gap_pct > 0.5: score += int(5 * w_ema)

    score = max(0, min(100, score))
    if score >= 75: cls = "A"
    elif score >= 50: cls = "B"
    elif score >= 30: cls = "C"
    else: cls = "D"
    return score, cls


# ═══ Single Symbol Check ═══

# In-memory EMA history for cross detection (survives across poll cycles)
_prev_ema: dict = {}  # {ticker: (prev_fast, prev_slow)}


def _load_prev_ema():
    """Load previous EMA values from DB (survives restart)."""
    global _prev_ema
    try:
        conn = _db()
        rows = conn.execute(
            "SELECT symbol, prev_ema_fast, prev_ema_slow FROM stock_radar_state "
            "WHERE timeframe='30m' AND prev_ema_fast IS NOT NULL"
        ).fetchall()
        conn.close()
        for r in rows:
            _prev_ema[r["symbol"]] = (float(r["prev_ema_fast"]), float(r["prev_ema_slow"]))
        logger.info(f"Loaded {len(_prev_ema)} prev EMA states from DB")
    except Exception as e:
        logger.warning(f"Failed to load prev EMA: {e}")


def _fetch_bridge_30m(ticker: str) -> dict:
    # RETIRED 2026-08-16 (G-4): the bridge dependency is gone. Returning
    # the empty shape rather than calling a host that is not there - a
    # dangling endpoint that times out is a silent failure waiting to be
    # misread as "no signal". The URL below stays as a deprecated marker.
    return {}


def _fetch_bridge_30m_retired(ticker: str) -> dict:
    """Fetch 30m analysis for one symbol from Bridge API (sync)."""
    import requests as _req
    r = _req.get(
        os.getenv("BRIDGE_URL", "http://192.168.111.214:8059") + "/analysis",
        params={"symbol": ticker, "exchange": "KSE", "interval": "30", "bars": 60},
        timeout=8,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Bridge HTTP {r.status_code}")
    return r.json()


def check_symbol(symbol, fast=9, slow=21):
    """Check one symbol for EMA cross via Bridge API (30m). No tvDatafeed dependency."""
    from tv_data import resolve_symbol, KSE_STOCKS
    ticker = resolve_symbol(symbol)
    try:
        raw = _fetch_bridge_30m(ticker)
        ind = raw.get("indicators", {})
        q   = raw.get("quote", {})

        price      = float(raw.get("price") or q.get("price") or 0)
        change_pct = round(float(q.get("change_percent") or q.get("chp") or 0), 2)
        change     = round(price * change_pct / 100, 3)
        volume     = int(q.get("volume") or 0)
        rsi        = round(float(ind.get("rsi_14") or 0), 2)
        vol_ratio  = round(float(ind.get("vol_ratio") or 0), 2)
        vwap       = ind.get("vwap") or price

        ema_f = float(ind.get("ema_9") or ind.get("ema9") or 0)
        ema_s = float(ind.get("ema_21") or ind.get("ema_20") or 0)

        # EMA cross: compare current vs previous (stored from last poll cycle)
        prev_f, prev_s = _prev_ema.get(ticker, (None, None))
        _prev_ema[ticker] = (ema_f, ema_s)

        signal = None
        if prev_f and prev_s and ema_f and ema_s:
            if prev_f <= prev_s and ema_f > ema_s:
                signal = "bullish_cross"
            elif prev_f >= prev_s and ema_f < ema_s:
                signal = "bearish_cross"

        candle_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M")

        # Fix 6: S/R from top-level arrays in Bridge response
        _sup_arr = raw.get("support", []) if isinstance(raw, dict) else []
        _res_arr = raw.get("resistance", []) if isinstance(raw, dict) else []
        _sup = _sup_arr[0] if _sup_arr else (ind.get("support_1") or ind.get("pivot_low"))
        _res = _res_arr[0] if _res_arr else (ind.get("resistance_1") or ind.get("pivot_high"))
        sr = {"support_1": _sup, "resistance_1": _res} if (_sup or _res) else None

        vol_sig = {
            "signal": "high_volume" if vol_ratio >= 1.5 else "normal",
            "ratio": vol_ratio,
            "avg_volume": 0,
        }
        verdict    = _smart_verdict(signal, rsi, vwap, price, vol_sig, ema_f, ema_s)
        score, score_class = _compute_score(signal, rsi, vwap, price, vol_sig, ema_f, ema_s, sr)

        # Persist EMA state for restart survival
        try:
            conn = _db()
            conn.execute("""
                INSERT OR REPLACE INTO stock_radar_state
                (symbol, exchange, timeframe, fast_len, slow_len, prev_ema_fast, prev_ema_slow, updated_at)
                VALUES (?, 'KSE', '30m', 9, 21, ?, ?, ?)
            """, (ticker, ema_f, ema_s, datetime.utcnow().isoformat()))
            conn.commit()
            conn.close()
        except Exception:
            pass

        return {
            "ticker":      ticker,
            "name_ar":     KSE_STOCKS.get(ticker, ticker),
            "price":       price,
            "change":      change,
            "change_pct":  change_pct,
            "ema_fast":    ema_f,
            "ema_slow":    ema_s,
            "signal":      signal,
            "candle_time": candle_time,
            "rsi":         rsi,
            "vwap":        vwap,
            "support":     _sup,
            "resistance":  _res,
            "volume":      volume,
            "vol_avg":     0,
            "vol_ratio":   vol_ratio,
            "vol_signal":  vol_sig["signal"],
            "verdict":     verdict,
            "score":       score,
            "score_class": score_class,
        }
    except Exception as e:
        logger.error(f"check_symbol({ticker}): {e}")
        return {"ticker": ticker, "error": str(e)}


# ═══ Background Radar Loop ═══

async def radar_loop(send_fn):
    """Main radar loop. send_fn(text) sends Telegram message."""
    init_radar_db()
    _load_prev_ema()
    _radar_running = True
    _radar_cycle_count = 0
    logger.info("Stock radar loop started")
    await asyncio.sleep(60)  # wait for system startup
    while True:
        try:
            # Feature flag check (DB-backed, no restart needed)
            try:
                from feature_flags import FeatureFlags
                _ff = FeatureFlags("data/life.db")
                if not _ff.is_enabled("radar_enabled"):
                    logger.info("Radar disabled by feature flag")
                    await asyncio.sleep(300)
                    continue
            except Exception:
                pass
            cfg = _get_config()
            if not cfg.get("enabled", True):
                await asyncio.sleep(300)
                continue
            # Daily Context Layer: refresh once per session
            _do_daily = True
            try:
                from feature_flags import FeatureFlags
                _ff2 = FeatureFlags("data/life.db")
                _do_daily = _ff2.is_enabled("daily_refresh")
            except Exception:
                pass
            if _do_daily and not _daily_snapshot_is_fresh():
                try:
                    logger.info("Refreshing daily snapshot (stale or missing)...")
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, refresh_daily_snapshot)
                except Exception as de:
                    logger.warning(f"Daily snapshot refresh failed (non-fatal): {de}")
            # Only run during KSE market hours (Sun-Thu 9:00-12:40 KWT)
            from tv_data import _is_market_open
            if not _is_market_open():
                await asyncio.sleep(300)
                continue
            # Skip first 15 min after open (9:00-9:15 KWT) — noisy
            kwt_now = datetime.utcnow() + timedelta(hours=3)
            if kwt_now.hour == 9 and kwt_now.minute < 15:
                await asyncio.sleep(60)
                continue
            # Service health: skip cycle if Bridge is down
            try:
                from service_health import get_health_hub
                _hub = get_health_hub()
                if _hub and not _hub.is_up("bridge"):
                    logger.warning("Bridge down (service_health), skipping radar cycle — waiting 300s")
                    await asyncio.sleep(300)
                    continue
            except Exception:
                pass

            watchlist = get_watchlist()
            if not watchlist:
                # Fallback to config symbols — "ALL" means all KSE stocks
                from tv_data import KSE_STOCKS
                syms = cfg.get("symbols", [])
                if syms == ["ALL"] or syms == ["all"]:
                    syms = list(KSE_STOCKS.keys())
                for sym in syms:
                    add_to_watchlist(sym)
                watchlist = get_watchlist()
            cooldown = cfg.get("cooldown_minutes", 45)
            for item in watchlist:
                sym = item["symbol"]
                fast = item.get("fast_len", cfg.get("fast_ema", 9))
                slow = item.get("slow_len", cfg.get("slow_ema", 21))
                try:
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, check_symbol, sym, fast, slow)
                    if result.get("error"):
                        continue
                    signal = result.get("signal")
                    # Skip dead-volume stocks (noise filter)
                    if result.get("vol_ratio", 0) < 0.3:
                        continue
                    if signal and _should_alert(sym, signal, result["candle_time"], cooldown):
                        _record_signal(sym, signal, result["candle_time"],
                                       result["price"], result["ema_fast"], result["ema_slow"],
                                       enriched=result)
                        # Fire after_signal hook (non-blocking)
                        try:
                            from service_health import get_health_hub
                            _hub = get_health_hub()
                            if _hub:
                                _hk = getattr(_hub, '_hooks', None)
                                if _hk:
                                    _hk.fire_sync("after_signal",
                                        symbol=sym, signal_type=signal,
                                        price=result["price"],
                                        score=result.get("score", 0),
                                        timeframe="30m")
                        except Exception:
                            pass
                        msg = _format_alert(sym, signal, result["price"],
                                            result["ema_fast"], result["ema_slow"],
                                            result["candle_time"], enriched=result)
                        try:
                            _sig_meta = {
                                "symbol": sym, "signal": signal,
                                "price": result["price"],
                                "score": result.get("score", 0),
                                "score_class": result.get("score_class", ""),
                                "rsi": result.get("rsi"),
                                "vol_ratio": result.get("vol_ratio", 0),
                                "source": "radar",
                            }
                            # before_trade_alert hook — can block the alert
                            _skip_alert = False
                            try:
                                from service_health import get_health_hub
                                _hub2 = get_health_hub()
                                if _hub2:
                                    _hk2 = getattr(_hub2, '_hooks', None)
                                    if _hk2:
                                        _hr = await _hk2.fire("before_trade_alert",
                                            symbol=sym, action=signal,
                                            confidence=result.get("score", 0))
                                        for _r in (_hr or []):
                                            if isinstance(_r, dict) and _r.get("skip"):
                                                _skip_alert = True
                                                logger.info("Hook blocked alert for %s: %s", sym, _r.get("reason", ""))
                                                break
                            except Exception:
                                pass
                            if _skip_alert:
                                continue
                            await send_fn(msg, _sig_meta)
                            logger.info(f"Radar alert sent: {sym} {signal}")
                            if _signal_cursor:
                                _signal_cursor.set(f"{sym}:{signal}:{result['candle_time']}")
                        except Exception as se:
                            logger.error(f"Radar send error: {se}")
                    await asyncio.sleep(1)  # pace between symbols
                except Exception as e:
                    logger.warning(f"Radar skip {sym}: {e}")
                    continue
            poll = cfg.get("poll_seconds", 90)
            await asyncio.sleep(poll)
            _radar_cycle_count += 1
        except Exception as e:
            logger.error(f"Radar loop error (non-fatal): {e}")
            await asyncio.sleep(120)


# ═══ Telegram Command Handlers ═══

def tg_radar_list():
    wl = get_watchlist()
    if not wl:
        return "\U0001f4e1 \u0631\u0627\u062f\u0627\u0631 \u0627\u0644\u0623\u0633\u0647\u0645 \u0641\u0627\u0631\u063a \u2014 \u0627\u0633\u062a\u062e\u062f\u0645 /radar_add SYMBOL"
    from tv_data import KSE_STOCKS
    cfg = _get_config()
    status = "\U0001f7e2 \u0634\u063a\u0627\u0644" if cfg.get("enabled") else "\U0001f534 \u0645\u0648\u0642\u0641"
    lines = [f"\U0001f4e1 \u0631\u0627\u062f\u0627\u0631 EMA ({status})", ""]
    for w in wl:
        name = KSE_STOCKS.get(w["symbol"], w["symbol"])
        lines.append(f"  \u2022 {name} ({w['symbol']}) EMA{w['fast_len']}/{w['slow_len']} {w['timeframe']}")
    lines.append(f"{chr(10)}\u23F1 \u0641\u062d\u0635 \u0643\u0644 {cfg.get('poll_seconds', 90)} \u062b\u0627\u0646\u064a\u0629")
    return chr(10).join(lines)


def tg_radar_add(args):
    if not args:
        return "\u2753 \u0627\u0633\u062a\u062e\u062f\u0645: /radar_add SYMBOL"
    result = add_to_watchlist(args.strip())
    if result["ok"]:
        return f"\u2705 {result['name_ar']} ({result['ticker']}) \u0627\u0646\u0636\u0627\u0641 \u0644\u0644\u0631\u0627\u062f\u0627\u0631"
    return f"\u274c {result.get('error', 'error')}"


def tg_radar_remove(args):
    if not args:
        return "\u2753 \u0627\u0633\u062a\u062e\u062f\u0645: /radar_remove SYMBOL"
    result = remove_from_watchlist(args.strip())
    return f"\u2705 {result['ticker']} \u0634\u0644\u0646\u0627\u0647 \u0645\u0646 \u0627\u0644\u0631\u0627\u062f\u0627\u0631" if result["removed"] else f"\u26A0\uFE0F {result['ticker']} \u0645\u0648 \u0628\u0627\u0644\u0631\u0627\u062f\u0627\u0631"


def tg_radar_check(args):
    if not args:
        return "\u2753 \u0627\u0633\u062a\u062e\u062f\u0645: /radar_check SYMBOL"
    result = check_symbol(args.strip())
    if result.get("error"):
        return f"\u274c {result['ticker']}: {result['error']}"
    from tv_data import KSE_STOCKS
    name = KSE_STOCKS.get(result["ticker"], result["ticker"])
    sig = result.get("signal")
    if sig == "bullish_cross":
        sig_text = "\U0001f7e2 \u062a\u0642\u0627\u0637\u0639 \u0635\u0627\u0639\u062f"
    elif sig == "bearish_cross":
        sig_text = "\U0001f534 \u062a\u0642\u0627\u0637\u0639 \u0647\u0627\u0628\u0637"
    else:
        sig_text = "\u26AA \u0644\u0627 \u062a\u0642\u0627\u0637\u0639"
    cp = result.get("change_pct", 0)
    arrow = "\u2b06\ufe0f" if cp >= 0 else "\u2b07\ufe0f"
    lines = [
        f"\U0001f4e1 {name} ({result['ticker']})",
        f"\u0627\u0644\u0633\u0639\u0631: {result['price']} \u0641\u0644\u0633 {arrow} {cp:+.2f}%",
        f"EMA9: {result['ema_fast']} | EMA21: {result['ema_slow']}",
    ]
    rsi = result.get("rsi")
    if rsi:
        lines.append(f"RSI(14): {rsi}")
    vwap = result.get("vwap")
    if vwap:
        lines.append(f"VWAP: {vwap}")
    sup = result.get("support")
    res = result.get("resistance")
    if sup and res:
        lines.append(f"\u0627\u0644\u062f\u0639\u0645: {sup} | \u0627\u0644\u0645\u0642\u0627\u0648\u0645\u0629: {res}")
    vr = result.get("vol_ratio", 0)
    vol = result.get("volume", 0)
    if vol:
        lines.append(f"\u0627\u0644\u062d\u062c\u0645: {vol:,} (x{vr:.1f})")
    lines.append(f"\u0627\u0644\u0625\u0634\u0627\u0631\u0629: {sig_text}")
    sc = result.get("score", 0)
    sc_cls = result.get("score_class", "")
    if sc:
        lines.append(f"Score: {sc}/100 (Class {sc_cls})")
    verdict = result.get("verdict")
    if verdict:
        lines.append(f"\u0627\u0644\u062d\u0643\u0645: {verdict}")
    return chr(10).join(lines)


def tg_radar_last(args=""):
    """Show last events — optionally filtered by symbol."""
    from tv_data import KSE_STOCKS, resolve_symbol
    ticker = None
    if args and args.strip():
        ticker = resolve_symbol(args.strip())
    conn = _db()
    if ticker:
        rows = conn.execute(
            "SELECT * FROM stock_radar_events WHERE symbol=? ORDER BY created_at DESC LIMIT 10",
            (ticker,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM stock_radar_events ORDER BY created_at DESC LIMIT 10").fetchall()
    conn.close()
    events = [dict(r) for r in rows]
    if not events:
        extra = f" \u0644\u0640 {ticker}" if ticker else ""
        return f"\U0001f4e1 \u0644\u0627 \u062a\u0648\u062c\u062f \u0625\u0634\u0627\u0631\u0627\u062a \u0633\u0627\u0628\u0642\u0629{extra}"
    title = f"\U0001f4e1 \u0622\u062e\u0631 \u0625\u0634\u0627\u0631\u0627\u062a {ticker}:" if ticker else "\U0001f4e1 \u0622\u062e\u0631 \u0625\u0634\u0627\u0631\u0627\u062a \u0627\u0644\u0631\u0627\u062f\u0627\u0631:"
    lines = [title, ""]
    for e in events:
        name = KSE_STOCKS.get(e["symbol"], e["symbol"])
        emoji = "\U0001f7e2" if "bullish" in e["signal_type"] else "\U0001f534"
        lines.append(f"{emoji} {name} | {e['price']} | EMA {e.get('ema_fast','?')}/{e.get('ema_slow','?')} | {e['created_at'][:16]}")
    return chr(10).join(lines)


def tg_radar_status():
    """Show radar status: enabled, watchlist count, last signal, uptime."""
    cfg = _get_config()
    enabled = cfg.get("enabled", True)
    status = "\U0001f7e2 \u0634\u063a\u0627\u0644" if enabled else "\U0001f534 \u0645\u0648\u0642\u0641"
    poll = cfg.get("poll_seconds", 90)
    cooldown = cfg.get("cooldown_minutes", 45)
    wl = get_watchlist()
    wl_count = len(wl)
    syms = cfg.get("symbols", [])
    if syms == ["ALL"] or syms == ["all"]:
        mode = "\u0643\u0644 \u0627\u0644\u0623\u0633\u0647\u0645"
    else:
        mode = f"{len(syms)} \u0633\u0647\u0645"
    from tv_data import _is_market_open
    market = "\U0001f7e2 \u0645\u0641\u062a\u0648\u062d" if _is_market_open() else "\U0001f534 \u0645\u063a\u0644\u0642"
    conn = _db()
    total_events = conn.execute("SELECT COUNT(*) FROM stock_radar_events").fetchone()[0]
    last_row = conn.execute("SELECT symbol, signal_type, price, created_at FROM stock_radar_events ORDER BY created_at DESC LIMIT 1").fetchone()
    conn.close()
    lines = [
        f"\U0001f4e1 \u062d\u0627\u0644\u0629 \u0627\u0644\u0631\u0627\u062f\u0627\u0631", "",
        f"\u0627\u0644\u062d\u0627\u0644\u0629: {status}",
        f"\u0627\u0644\u0633\u0648\u0642: {market}",
        f"\u0627\u0644\u0645\u0631\u0627\u0642\u0628\u0629: {mode} ({wl_count} \u0641\u064a \u0627\u0644\u0642\u0627\u0626\u0645\u0629)",
        f"\u0627\u0644\u0641\u062d\u0635: \u0643\u0644 {poll} \u062b\u0627\u0646\u064a\u0629",
        f"\u0627\u0644\u062a\u0628\u0631\u064a\u062f: {cooldown} \u062f\u0642\u064a\u0642\u0629",
        f"\u0625\u062c\u0645\u0627\u0644\u064a \u0627\u0644\u0625\u0634\u0627\u0631\u0627\u062a: {total_events}",
    ]
    if last_row:
        from tv_data import KSE_STOCKS
        ln = KSE_STOCKS.get(last_row["symbol"], last_row["symbol"])
        em = "\U0001f7e2" if "bullish" in last_row["signal_type"] else "\U0001f534"
        lines.append(f"\u0622\u062e\u0631 \u0625\u0634\u0627\u0631\u0629: {em} {ln} @ {last_row['price']} ({last_row['created_at'][:16]})")
    return chr(10).join(lines)


def tg_radar_top(n=10):
    """Top N signals from recent radar events, scored and ranked."""
    conn = _db()
    # Get unique latest signal per symbol from recent events (last 24h)
    # column format (space): with a T cutoff, "last 24h" behaved as
    # "since midnight of the cutoff date"
    cutoff = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute("""
        SELECT symbol, signal_type, price, ema_fast, ema_slow, created_at,
               MAX(created_at) as latest
        FROM stock_radar_events
        WHERE created_at > ?
        GROUP BY symbol
        ORDER BY created_at DESC
    """, (cutoff,)).fetchall()
    conn.close()
    if not rows:
        return "\U0001f4e1 \u0644\u0627 \u062a\u0648\u062c\u062f \u0625\u0634\u0627\u0631\u0627\u062a \u062e\u0644\u0627\u0644 24 \u0633\u0627\u0639\u0629"
    # Re-check each for live score
    scored = []
    for r in rows:
        try:
            result = check_symbol(r["symbol"])
            if result.get("error"):
                continue
            sc = result.get("score", 0)
            if sc > 0:
                scored.append({
                    "symbol": r["symbol"],
                    "signal": r["signal_type"],
                    "price": result["price"],
                    "score": sc,
                    "score_class": result.get("score_class", "D"),
                    "rsi": result.get("rsi"),
                    "vol_ratio": result.get("vol_ratio", 0),
                    "verdict": result.get("verdict", ""),
                    "time": r["created_at"][:16],
                })
            time.sleep(0.3)
        except Exception:
            continue
    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:n]
    if not top:
        return "\U0001f4e1 \u0644\u0627 \u062a\u0648\u062c\u062f \u0625\u0634\u0627\u0631\u0627\u062a \u0645\u0624\u0647\u0644\u0629"
    from tv_data import KSE_STOCKS
    lines = [f"\U0001f3af \u0623\u0641\u0636\u0644 {len(top)} \u0625\u0634\u0627\u0631\u0627\u062a \u0627\u0644\u0631\u0627\u062f\u0627\u0631:", ""]
    for i, s in enumerate(top, 1):
        name = KSE_STOCKS.get(s["symbol"], s["symbol"])
        em = "\U0001f7e2" if "bullish" in s["signal"] else "\U0001f534"
        rsi_txt = f"RSI:{s['rsi']}" if s.get("rsi") else ""
        lines.append(f"{i}. {em} {name} ({s['symbol']})")
        lines.append(f"   Score: {s['score']}/100 (Class {s['score_class']}) | {s['price']} fils | x{s['vol_ratio']:.1f} vol {rsi_txt}")
        if s.get("verdict"):
            lines.append(f"   {s['verdict']}")
        lines.append("")
    return chr(10).join(lines)


def tg_radar_toggle():
    cfg = _get_config()
    cfg["enabled"] = not cfg.get("enabled", True)
    _save_config(cfg)
    s = "\U0001f7e2 \u0634\u063a\u0627\u0644" if cfg["enabled"] else "\U0001f534 \u0645\u0648\u0642\u0641"
    return f"\U0001f4e1 \u0627\u0644\u0631\u0627\u062f\u0627\u0631 {s}"



# ═══ Daily Context Layer ═══
# Daily snapshot for post-market review
# trend: "صاعد" if EMA9>EMA21 daily, "هابط" if EMA9<EMA21, "محايد" otherwise

_daily_refresh_lock = False


def _market_open_safe() -> bool:
    """True if KSE is trading.

    On error assume open. Refusing a snapshot is recoverable; recording
    mid-session prices as if they were closing values is not.
    """
    try:
        from tv_data import _is_market_open
        return _is_market_open()
    except Exception as e:
        logger.warning("market-hours check failed (%r) - assuming open", e)
        return True


def _fetch_bridge_daily(symbols: list) -> dict:
    # RETIRED 2026-08-16 (G-4): the bridge dependency is gone. Returning
    # the empty shape rather than calling a host that is not there - a
    # dangling endpoint that times out is a silent failure waiting to be
    # misread as "no signal". The URL below stays as a deprecated marker.
    return {}


def _fetch_bridge_daily_retired(symbols: list) -> dict:
    """Fetch 1D analysis for all symbols from Bridge API (sync, batched).
    Returns dict: {symbol: normalized_data} or {} on failure.

    Probes /health for 2s before starting the batch walk. Without it, an
    unreachable bridge costs one full timeout per batch - 26 batches, six
    and a half minutes, measured 2026-08-14 - and every one of them was
    always going to fail. The probe is the same one stock_analyzer uses.
    """
    import requests as _req
    BRIDGE = os.getenv("BRIDGE_URL", "http://192.168.111.214:8059")
    BATCH = 5   # smaller batches — daily data is slower to fetch
    try:
        _hc = _req.get(f"{BRIDGE}/health", timeout=2)
        if _hc.status_code != 200:
            logger.warning("daily_snapshot: bridge health returned %s - not fetching",
                           _hc.status_code)
            return {}
    except Exception as _he:
        logger.warning("daily_snapshot: bridge unreachable (%r) - not fetching", _he)
        return {}
    results = {}
    for i in range(0, len(symbols), BATCH):
        batch = symbols[i:i + BATCH]
        try:
            r = _req.get(
                f"{BRIDGE}/multi-analysis",
                params={"symbols": ",".join(batch), "exchange": "KSE", "interval": "1D", "bars": 60},
                timeout=75,  # a real daily TradingView fetch is slow; the health
                             # probe above is what keeps a dead bridge cheap, not
                             # a short timeout here
            )
            if r.status_code == 200:
                data = r.json()
                for item in data.get("results", []):
                    sym_raw = item.get("symbol", "")
                    sym = sym_raw.split(":")[-1] if ":" in sym_raw else sym_raw
                    results[sym] = item
        except Exception as e:
            logger.warning(f"Bridge batch {batch[:3]}…: {e}")
    return results


def refresh_daily_snapshot(symbols=None, force=False):
    """Refresh stock_radar_daily. Delegates to the ONE writer (Yahoo).

    Retired as an independent writer 2026-08-16 (OPEN_ITEMS NEXT-4). Two
    writers shared this table - this one (bridge era) and
    _tools/backfill_daily_bars.py (Yahoo) - and only the second wrote
    indicator_source / bars_used / coverage_pct. The damage was worse than
    a missing tag: the old body used INSERT OR REPLACE naming 37 of the
    table's 56 columns, so a single successful run would have silently
    NULLed 19 populated columns - the entire liquidity census (med_vol_20,
    liq_vol, liq_value_kwd, avg_vol_*, 127-132 rows each) and every piece
    of G-2 evidence. It has been inert since the bridge was retired, so
    nothing was lost; the risk was that reviving the bridge would have
    wiped four days of work on the first run.

    The five callers keep working and keep their contract shape - the
    scheduler, kse_data_collector, the manual endpoint, verify_sunday and
    the _tools scripts all still get {ok, errors, msg}.
    """
    global _daily_refresh_lock
    market_open = _market_open_safe()
    if market_open and not force:
        logger.warning("daily_snapshot: KSE still open - refusing (pass force=True)")
        return {"ok": 0, "errors": 0, "msg": "market_open", "market_was_open": True}
    if _daily_refresh_lock:
        return {"ok": 0, "errors": 0, "msg": "refresh already running"}
    _daily_refresh_lock = True
    try:
        import importlib.util, os as _os
        _p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                           "_tools", "backfill_daily_bars.py")
        _spec = importlib.util.spec_from_file_location("_bdb", _p)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _mod.main()
        return {"ok": 1, "errors": 0, "msg": "delegated to backfill_daily_bars (Yahoo)",
                "writer": "backfill_daily_bars", "market_was_open": market_open}
    except Exception as e:
        logger.warning("daily_snapshot delegation failed: %r", e)
        return {"ok": 0, "errors": 1, "msg": "delegation failed: %r" % e}
    finally:
        _daily_refresh_lock = False


def _refresh_daily_snapshot_bridge_era(symbols=None, force=False):
    """The pre-2026-08-16 bridge writer. Unreachable. Kept for the record
    ONLY - do not call it: its INSERT OR REPLACE would NULL 19 columns."""
    global _daily_refresh_lock
    market_open = _market_open_safe()
    if market_open and not force:
        logger.warning("daily_snapshot: KSE still open - refusing (pass force=True to override)")
        return {"ok": 0, "errors": 0, "msg": "market_open", "market_was_open": True}
    if _daily_refresh_lock:
        return {"ok": 0, "errors": 0, "msg": "refresh already running"}
    _daily_refresh_lock = True
    try:
        if symbols is None:
            wl = get_watchlist()
            symbols = [w["symbol"] for w in wl]
        if not symbols:
            return {"ok": 0, "errors": 0, "msg": "empty watchlist"}

        # Fetch all symbols from Bridge in bulk (1D candles)
        bridge_data = _fetch_bridge_daily(symbols)
        if not bridge_data:
            logger.warning("daily_snapshot: Bridge returned no data — aborting")
            return {"ok": 0, "errors": len(symbols), "msg": "bridge_no_data"}

        conn = _db()
        ok_count = 0
        err_count = 0
        now = datetime.utcnow().isoformat()

        # Bridge signals provide pre-computed crosses — no need for prev lookups

        for sym in symbols:
            try:
                raw = bridge_data.get(sym)
                if not raw:
                    err_count += 1
                    continue

                ind = raw.get("indicators", {})
                q   = raw.get("quote", {})

                price      = float(raw.get("price") or q.get("price") or 0)
                change_pct = round(float(q.get("change_percent") or q.get("chp") or 0), 2)
                rsi        = round(float(ind.get("rsi_14") or 0), 2)
                volume     = int(q.get("volume") or 0)
                vol_ratio  = round(float(ind.get("vol_ratio") or 0), 2)

                ema9  = ind.get("ema_9") or ind.get("ema9") or 0
                ema21 = ind.get("ema_21") or ind.get("ema_20") or 0

                # === EMA Direction (always set) ===
                if ema9 and ema21:
                    if ema9 > ema21:
                        trend_ar = "صاعد"
                    elif ema9 < ema21:
                        trend_ar = "هابط"
                    else:
                        trend_ar = "محايد"
                else:
                    trend_ar = "محايد"

                # === Bridge pre-computed signals ===
                bridge_signals = raw.get("signals") or {}
                bridge_ema_cross = bridge_signals.get("ema_cross") or {}
                bridge_confluence = bridge_signals.get("confluence") or {}
                bridge_macd_mom = bridge_signals.get("macd_momentum") or ""

                # === EMA Cross from Bridge ===
                if isinstance(bridge_ema_cross, dict) and bridge_ema_cross.get("type"):
                    cross_type = bridge_ema_cross["type"]
                    if cross_type == "golden":
                        daily_ema_cross = "bullish"
                    elif cross_type == "death":
                        daily_ema_cross = "bearish"
                    else:
                        daily_ema_cross = "none"
                else:
                    daily_ema_cross = "bullish" if ema9 and ema21 and ema9 > ema21 else "bearish" if ema9 and ema21 and ema9 < ema21 else "none"

                # === MACD ===
                macd_val  = ind.get("macd") or 0
                macd_sig  = ind.get("macd_signal") or 0
                macd_hist = ind.get("macd_hist") or 0
                macd_cross = "bullish" if macd_hist > 0 else "bearish" if macd_hist < 0 else "none"
                macd_above_zero = bool(macd_val > 0)

                # === Other indicators ===
                stoch_k_val = ind.get("stoch_k")
                adx_val     = ind.get("adx")
                atr_val     = ind.get("atr_14")
                rsi_div_val = bridge_signals.get("rsi_divergence")
                if rsi_div_val == "none" or rsi_div_val == "":
                    rsi_div_val = None

                # S/R from top-level arrays
                sup_arr = raw.get("support", [])
                res_arr = raw.get("resistance", [])
                support    = sup_arr[0] if sup_arr else None
                resistance = res_arr[0] if res_arr else None

                # BB from indicators
                bb_squeeze_val  = bool(ind.get("bb_squeeze") or False)
                bb_bandwidth_val = ind.get("bb_bandwidth")

                # === Volume spike ===
                volume_spike = 1 if vol_ratio >= 2 else 0

                # === Score: use Bridge confluence if available, else compute ===
                bridge_conf_score = bridge_confluence.get("score", 0)
                if bridge_conf_score > 0:
                    score = bridge_conf_score
                else:
                    vol_sig_proxy = {"signal": "high_volume" if vol_ratio >= 1.5 else "normal", "ratio": vol_ratio}
                    conf_result = _compute_confluence(None, {
                        "daily_ema_cross": daily_ema_cross,
                        "macd_cross": macd_cross,
                        "macd_above_zero": macd_above_zero,
                        "vol_ratio": vol_ratio,
                        "rsi": rsi,
                    })
                    score = conf_result.get("confluence_score", 0)

                if score >= 75: score_class = "A"
                elif score >= 50: score_class = "B"
                elif score >= 30: score_class = "C"
                else: score_class = "D"

                # === Confluence for DB ===
                vol_sig_proxy = {"signal": "high_volume" if vol_ratio >= 1.5 else "normal", "ratio": vol_ratio}
                confluence = _compute_confluence(None, {
                    "daily_ema_cross": daily_ema_cross,
                    "macd_cross": macd_cross,
                    "macd_above_zero": macd_above_zero,
                    "vol_ratio": vol_ratio,
                    "rsi": rsi,
                })

                # === Verdict: smart, based on all data ===
                if score >= 70 and daily_ema_cross == "bullish" and vol_ratio >= 1.2:
                    verdict = "\U0001f525 فرصة قوية"
                elif score >= 50 and daily_ema_cross == "bullish":
                    verdict = "\U0001f7e2 صاعد — مراقبة"
                elif score >= 50 and macd_cross == "bullish":
                    verdict = "\U0001f7e2 زخم صاعد"
                elif score >= 40:
                    verdict = "\U0001f7e1 محايد — انتظار"
                elif daily_ema_cross == "bearish" and score < 40:
                    verdict = "\U0001f534 ضغط بيعي"
                elif rsi and rsi < 30:
                    verdict = "\U0001f7e2 تشبع بيعي — فرصة"
                elif rsi and rsi > 70:
                    verdict = "\U0001f534 تشبع شرائي — حذر"
                else:
                    verdict = "\u26AA محايد"

                conn.execute("""
                    INSERT OR REPLACE INTO stock_radar_daily
                    (symbol, exchange, price, trend, rsi, support, resistance,
                     score, score_class, verdict, volume, vol_ratio, change_pct,
                     source_timeframe, updated_at, ema_fast, ema_slow,
                     macd, macd_signal, macd_histogram, macd_cross,
                     daily_ema9, daily_ema21, daily_ema_cross,
                     confluence_score, confluence_direction,
                     avg_volume, volume_spike, macd_above_zero,
                     stoch_k, adx, rsi_divergence, atr,
                     bb_squeeze, bb_bandwidth, captured_at, market_was_open)
                    VALUES (?, 'KSE', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '1D', ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?)
                """, (sym, price, trend_ar, rsi, support, resistance,
                      score, score_class, verdict, volume, vol_ratio, change_pct, now,
                      ema9, ema21,
                      macd_val, macd_sig, macd_hist, macd_cross,
                      ema9, ema21, daily_ema_cross,
                      confluence["confluence_score"], confluence["direction"],
                      0, 1 if vol_ratio >= 2 else 0, 1 if macd_above_zero else 0,
                      stoch_k_val, adx_val, rsi_div_val, atr_val,
                      bb_squeeze_val, bb_bandwidth_val, now, 1 if market_open else 0))
                ok_count += 1
            except Exception as e:
                logger.warning(f"daily_snapshot skip {sym}: {e}")
                err_count += 1
                continue

        conn.commit()
        conn.close()
        logger.info(f"Daily snapshot refreshed: {ok_count} ok, {err_count} errors")

        # Refresh S/R levels for all symbols from daily data
        try:
            from sr_engine import refresh_sr_for_all
            refresh_sr_for_all()
        except Exception as e:
            logger.warning(f"S/R refresh failed (non-critical): {e}")

        # Fire after_daily_refresh hook
        try:
            from service_health import get_health_hub
            _hub = get_health_hub()
            if _hub:
                _hk = getattr(_hub, '_hooks', None)
                if _hk:
                    _hk.fire_sync("after_daily_refresh",
                        ok_count=ok_count, err_count=err_count)
        except Exception:
            pass
        return {"ok": ok_count, "errors": err_count}
    finally:
        _daily_refresh_lock = False


def get_daily_snapshot(top_n=15, min_score=0):
    """Get stored daily snapshot from DB. Read-only, no fetch."""
    conn = _db()
    rows = conn.execute(
        "SELECT * FROM stock_radar_daily WHERE score >= ? ORDER BY score DESC",
        (min_score,)
    ).fetchall()
    conn.close()
    from tv_data import KSE_STOCKS
    results = []
    for r in rows:
        d = dict(r)
        d["name_ar"] = KSE_STOCKS.get(d["symbol"], d["symbol"])
        try:
            updated = datetime.fromisoformat(d["updated_at"])
            age_hours = (datetime.utcnow() - updated).total_seconds() / 3600
            d["data_age_hours"] = round(age_hours, 1)
            d["is_stale"] = age_hours > 18
            d["freshness"] = "fresh" if age_hours < 6 else "aging" if age_hours < 18 else "stale"
        except Exception:
            d["data_age_hours"] = 999
            d["is_stale"] = True
            d["freshness"] = "stale"
        results.append(d)
    if top_n:
        results = results[:top_n]
    return results


def _daily_snapshot_is_fresh():
    """Daily snapshot is fresh if updated after today's market close (12:40 KWT)."""
    conn = _db()
    try:
        row = conn.execute(
            "SELECT MAX(updated_at) as last_update FROM stock_radar_daily"
        ).fetchone()
    except Exception:
        return False
    finally:
        conn.close()
    if not row or not row["last_update"]:
        return False
    try:
        last = datetime.fromisoformat(row["last_update"])
        kwt_now = datetime.utcnow() + timedelta(hours=3)
        kwt_last = last + timedelta(hours=3)
        # Fresh if updated today after market close
        if kwt_last.date() == kwt_now.date() and kwt_last.hour >= 13:
            return True
        # Also fresh within 4 hours (manual refresh fallback)
        if (datetime.utcnow() - last).total_seconds() < 4 * 3600:
            return True
        return False
    except Exception:
        return False
