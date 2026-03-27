"""
tradingview_bridge.py - TradingView Integration Bridge (Phase 6)
Tables in life.db: tv_watchlists, tv_alert_events, tv_signal_stats, tv_config
TG commands: /tv_watchlist, /tv_add, /tv_remove, /tv_last, /tv_summary, /tv_test, /tv_stats
LLM tools: tv_watchlist_add, tv_watchlist_list, tv_last_signal, tv_signal_summary
Webhook: POST /tradingview/webhook
"""

import os
import sqlite3
import json
import logging
import re
from datetime import datetime, date, timedelta, timezone

logger = logging.getLogger("tradingview_bridge")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")

# ══════════════════════════════════════════════════════════
# SCHEMA
# ══════════════════════════════════════════════════════════
_SCHEMA = """
CREATE TABLE IF NOT EXISTS tv_watchlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    market TEXT,
    label TEXT,
    strategy_name TEXT,
    notes TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tv_wl_ticker ON tv_watchlists(ticker);
CREATE INDEX IF NOT EXISTS idx_tv_wl_active ON tv_watchlists(is_active);

CREATE TABLE IF NOT EXISTS tv_alert_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    market TEXT,
    exchange TEXT,
    interval TEXT,
    signal TEXT NOT NULL,
    strategy_name TEXT,
    price REAL,
    volume REAL,
    event_time TEXT,
    received_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    evaluation_score REAL,
    evaluation_label TEXT,
    context_note TEXT,
    telegram_sent INTEGER NOT NULL DEFAULT 0,
    telegram_sent_at TEXT,
    processed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tv_ae_ticker ON tv_alert_events(ticker);
CREATE INDEX IF NOT EXISTS idx_tv_ae_received ON tv_alert_events(received_at);
CREATE INDEX IF NOT EXISTS idx_tv_ae_signal ON tv_alert_events(signal);
CREATE INDEX IF NOT EXISTS idx_tv_ae_strategy ON tv_alert_events(strategy_name);

CREATE TABLE IF NOT EXISTS tv_signal_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    strategy_name TEXT,
    signal_type TEXT,
    count_total INTEGER NOT NULL DEFAULT 0,
    last_seen_at TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tv_ss_ticker ON tv_signal_stats(ticker);

CREATE TABLE IF NOT EXISTS tv_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_DEFAULT_CONFIG = {
    "tv_webhook_secret": "CHANGE_ME_PLEASE",
    "tv_default_market": "KSE",
    "tv_alerts_enabled": "true",
    "tv_daily_summary_enabled": "true",
}

# ══════════════════════════════════════════════════════════
# DB HELPERS
# ══════════════════════════════════════════════════════════
def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c

def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def init_tradingview_domain():
    db = _conn()
    db.executescript(_SCHEMA)
    now = _now()
    for k, v in _DEFAULT_CONFIG.items():
        db.execute(
            "INSERT OR IGNORE INTO tv_config (key, value, updated_at) VALUES (?,?,?)",
            (k, v, now)
        )
    db.commit()
    db.close()
    logger.info("tradingview_bridge: schema + config ready")

def _get_config(key):
    db = _conn()
    row = db.execute("SELECT value FROM tv_config WHERE key=?", (key,)).fetchone()
    db.close()
    return row["value"] if row else None

def _set_config(key, value):
    db = _conn()
    db.execute(
        "INSERT OR REPLACE INTO tv_config (key, value, updated_at) VALUES (?,?,?)",
        (key, value, _now())
    )
    db.commit()
    db.close()

# ══════════════════════════════════════════════════════════
# TICKER NORMALIZATION
# ══════════════════════════════════════════════════════════
_TICKER_ALIASES = {
    "KFH": "KSE:KFH", "NBK": "KSE:NBK", "ZAIN": "KSE:ZAIN",
    "BOURSA": "KSE:BOURSA", "AGILITY": "KSE:AGILITY", "STC": "KSE:STC",
    "CLEANING": "KSE:CLEANING", "SENERGY": "KSE:SENERGY", "INOVEST": "KSE:INOVEST",
    "HUMANSOFT": "KSE:HUMANSOFT", "BOUBYAN": "KSE:BOUBYAN", "GBK": "KSE:GBK",
    "ABK": "KSE:ABK", "CBK": "KSE:CBK", "KIB": "KSE:KIB",
}

def normalize_ticker(raw):
    """Normalize ticker: 'kfh' -> 'KSE:KFH', 'KSE:KFH' stays."""
    if not raw:
        return ""
    raw = raw.strip().upper()
    if ":" in raw:
        return raw
    if raw in _TICKER_ALIASES:
        return _TICKER_ALIASES[raw]
    default_market = _get_config("tv_default_market") or "KSE"
    return f"{default_market}:{raw}"

# ══════════════════════════════════════════════════════════
# SECRET VERIFICATION
# ══════════════════════════════════════════════════════════
def verify_tv_secret(payload):
    """Verify webhook secret from payload."""
    expected = _get_config("tv_webhook_secret")
    if not expected or expected == "CHANGE_ME_PLEASE":
        logger.warning("tv_webhook_secret not configured!")
        return False
    incoming = payload.get("secret", "")
    return incoming == expected

# ══════════════════════════════════════════════════════════
# SIGNAL EVALUATION (rule-based)
# ══════════════════════════════════════════════════════════
_STRONG_SIGNALS = {"breakout", "reversal", "golden_cross", "death_cross", "divergence"}
_MEDIUM_SIGNALS = {"crossover", "trend_change", "volume_spike", "support", "resistance"}
_STRONG_INTERVALS = {"1D", "4H", "1W", "D", "W"}
_MEDIUM_INTERVALS = {"1H", "2H", "H"}

def evaluate_signal_strength(payload):
    """Rule-based signal evaluation. Returns dict with score, label, reasons."""
    score = 0.0
    reasons = []

    # Interval scoring
    interval = (payload.get("interval") or "").upper()
    if interval in _STRONG_INTERVALS:
        score += 0.25
        reasons.append("\u0641\u0631\u064a\u0645 \u064a\u0648\u0645\u064a/\u0623\u0633\u0628\u0648\u0639\u064a")
    elif interval in _MEDIUM_INTERVALS:
        score += 0.15
        reasons.append("\u0641\u0631\u064a\u0645 \u0633\u0627\u0639\u0629")
    else:
        score += 0.05
        reasons.append("\u0641\u0631\u064a\u0645 \u0635\u063a\u064a\u0631")

    # Signal type scoring
    signal = (payload.get("signal") or "").lower()
    if signal in _STRONG_SIGNALS:
        score += 0.25
        reasons.append(f"\u0625\u0634\u0627\u0631\u0629 \u0642\u0648\u064a\u0629: {signal}")
    elif signal in _MEDIUM_SIGNALS:
        score += 0.15
        reasons.append(f"\u0625\u0634\u0627\u0631\u0629 \u0645\u062a\u0648\u0633\u0637\u0629: {signal}")
    else:
        score += 0.05
        reasons.append(f"\u0625\u0634\u0627\u0631\u0629: {signal}")

    # Volume presence
    vol = payload.get("volume")
    if vol and float(vol) > 0:
        score += 0.10
        reasons.append("\u062d\u062c\u0645 \u0645\u062a\u0648\u0641\u0631")

    # Strategy known
    strategy = payload.get("strategy") or payload.get("strategy_name") or ""
    if strategy:
        score += 0.10
        reasons.append(f"\u0627\u0633\u062a\u0631\u0627\u062a\u064a\u062c\u064a\u0629: {strategy}")

    # In watchlist?
    ticker = normalize_ticker(payload.get("ticker", ""))
    if ticker:
        db = _conn()
        wl = db.execute(
            "SELECT 1 FROM tv_watchlists WHERE ticker=? AND is_active=1", (ticker,)
        ).fetchone()
        db.close()
        if wl:
            score += 0.15
            reasons.append("\u0627\u0644\u0633\u0647\u0645 \u0641\u064a \u0627\u0644\u0648\u0627\u062a\u0634 \u0644\u064a\u0633\u062a")

    # Price presence
    if payload.get("price"):
        score += 0.05
        reasons.append("\u0633\u0639\u0631 \u0645\u062a\u0648\u0641\u0631")

    # Clamp
    score = min(score, 1.0)

    # Label
    if score >= 0.7:
        label = "strong_watch"
    elif score >= 0.45:
        label = "moderate_watch"
    elif score >= 0.25:
        label = "weak_watch"
    else:
        label = "info_only"

    return {"score": round(score, 2), "label": label, "reasons": reasons}


# ══════════════════════════════════════════════════════════
# KUWAIT CONTEXT
# ══════════════════════════════════════════════════════════
def build_kuwait_context_note(ticker="", signal=""):
    """Build a short context note about KSE market characteristics."""
    notes = []
    ticker_upper = (ticker or "").upper()
    if "KSE" in ticker_upper or not ticker_upper:
        notes.append(
            "\u0645\u0644\u0627\u062d\u0638\u0629: \u0633\u0648\u0642 \u0627\u0644\u0643\u0648\u064a\u062a "
            "\u0645\u0646\u062e\u0641\u0636 \u0627\u0644\u0633\u064a\u0648\u0644\u0629\u060c "
            "\u0627\u0646\u062a\u0628\u0647 \u0644\u0644\u0627\u062e\u062a\u0631\u0627\u0642\u0627\u062a "
            "\u0627\u0644\u0643\u0627\u0630\u0628\u0629."
        )
    signal_lower = (signal or "").lower()
    if signal_lower in ("breakout", "reversal"):
        notes.append(
            "\u0627\u0644\u0625\u0634\u0627\u0631\u0629 \u0644\u0644\u0645\u062a\u0627\u0628\u0639\u0629 "
            "\u0648\u0627\u0644\u062a\u062d\u0644\u064a\u0644 \u0641\u0642\u0637\u060c "
            "\u0644\u064a\u0633\u062a \u062a\u0648\u0635\u064a\u0629 \u0634\u0631\u0627\u0621/\u0628\u064a\u0639."
        )
    return " ".join(notes) if notes else ""


# ══════════════════════════════════════════════════════════
# SAVE ALERT
# ══════════════════════════════════════════════════════════
def save_tv_alert(payload):
    """Parse, evaluate, save alert. Returns (saved_id, row_dict)."""
    now = _now()
    ticker = normalize_ticker(payload.get("ticker", ""))
    market = payload.get("market") or payload.get("exchange") or ""
    exchange = payload.get("exchange") or payload.get("market") or ""
    interval = payload.get("interval") or ""
    signal = payload.get("signal") or "unknown"
    strategy = payload.get("strategy") or payload.get("strategy_name") or ""
    # Get real price from stock_radar_daily (non-blocking DB lookup)
    price = None
    _sym_bare = ticker.split(":")[-1] if ":" in ticker else ticker
    try:
        import sqlite3 as _sq
        _rdb = _sq.connect(os.path.join(os.path.dirname(__file__), "data", "life.db"), timeout=5)
        _rrow = _rdb.execute(
            "SELECT price FROM stock_radar_daily WHERE symbol=? ORDER BY rowid DESC LIMIT 1",
            (_sym_bare,)
        ).fetchone()
        _rdb.close()
        if _rrow and _rrow[0]:
            price = round(float(_rrow[0]), 1)
            logger.info(f"TV alert price for {ticker}: using radar price {price} fils")
        else:
            logger.warning(f"TV alert price for {ticker}: no radar data, falling back to webhook")
    except Exception as _e:
        logger.warning(f"TV alert price lookup failed for {ticker}: {_e}")
    # Fallback to webhook price if radar lookup failed
    if price is None:
        try:
            price = float(payload.get("price")) if payload.get("price") else None
            if price is not None:
                from tv_data import _normalize_price_to_fils
                price = _normalize_price_to_fils(price, ticker)
                logger.info(f"TV alert price for {ticker}: using webhook price {price} fils (fallback)")
        except (ValueError, TypeError):
            pass
    volume = None
    try:
        volume = float(payload.get("volume")) if payload.get("volume") else None
    except (ValueError, TypeError):
        pass
    event_time = payload.get("time") or payload.get("event_time") or now

    # Evaluate
    evaluation = evaluate_signal_strength(payload)
    context_note = build_kuwait_context_note(ticker, signal)

    db = _conn()
    cur = db.execute(
        "INSERT INTO tv_alert_events "
        "(ticker,market,exchange,interval,signal,strategy_name,price,volume,"
        "event_time,received_at,payload_json,evaluation_score,evaluation_label,"
        "context_note,processed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ticker, market, exchange, interval, signal, strategy, price, volume,
         event_time, now, json.dumps(payload, ensure_ascii=False),
         evaluation["score"], evaluation["label"], context_note, now)
    )
    saved_id = cur.lastrowid
    db.commit()

    # Update stats
    _update_stats(db, ticker, strategy, signal, now)
    db.close()

    row = {
        "id": saved_id, "ticker": ticker, "market": market, "exchange": exchange,
        "interval": interval, "signal": signal, "strategy_name": strategy,
        "price": price, "volume": volume, "event_time": event_time,
        "evaluation_score": evaluation["score"], "evaluation_label": evaluation["label"],
        "evaluation_reasons": evaluation["reasons"], "context_note": context_note,
    }
    logger.info(f"TV alert saved #{saved_id}: {ticker} {signal} [{evaluation['label']}]")
    return saved_id, row


def _update_stats(db, ticker, strategy, signal, now):
    """Increment signal stats."""
    row = db.execute(
        "SELECT id, count_total FROM tv_signal_stats "
        "WHERE ticker=? AND strategy_name=? AND signal_type=?",
        (ticker, strategy or "", signal)
    ).fetchone()
    if row:
        db.execute(
            "UPDATE tv_signal_stats SET count_total=?, last_seen_at=?, updated_at=? WHERE id=?",
            (row["count_total"] + 1, now, now, row["id"])
        )
    else:
        db.execute(
            "INSERT INTO tv_signal_stats (ticker,strategy_name,signal_type,count_total,last_seen_at,updated_at) "
            "VALUES (?,?,?,1,?,?)",
            (ticker, strategy or "", signal, now, now)
        )
    db.commit()


# ══════════════════════════════════════════════════════════
# TELEGRAM ALERT FORMAT
# ══════════════════════════════════════════════════════════
def render_tv_alert_message(row):
    """Build Telegram alert message from saved row — enriched with smart analysis."""
    label_ar = {
        "strong_watch": "\U0001f7e2 \u0645\u0631\u0627\u0642\u0628\u0629 \u0642\u0648\u064a\u0629",
        "moderate_watch": "\U0001f7e1 \u0645\u0631\u0627\u0642\u0628\u0629 \u0645\u062a\u0648\u0633\u0637\u0629",
        "weak_watch": "\U0001f7e0 \u0645\u0631\u0627\u0642\u0628\u0629 \u0636\u0639\u064a\u0641\u0629",
        "info_only": "\u2139\ufe0f \u0645\u0639\u0644\u0648\u0645\u0629 \u0641\u0642\u0637",
    }
    lines = []
    ticker = row.get("ticker", "?")
    signal = row.get("signal", "?")
    lines.append(f"\U0001f4e1 *{ticker}* \u2014 {signal.upper()}")
    if row.get("price"):
        lines.append(f"\u0627\u0644\u0633\u0639\u0631: {row['price']}")
    if row.get("interval"):
        lines.append(f"\u0627\u0644\u0641\u0631\u064a\u0645: {row['interval']}")
    if row.get("strategy_name"):
        lines.append(f"\u0627\u0644\u0625\u0633\u062a\u0631\u0627\u062a\u064a\u062c\u064a\u0629: {row['strategy_name']}")
    if row.get("volume"):
        lines.append(f"\u0627\u0644\u062d\u062c\u0645: {row['volume']:,.0f}")
    label = row.get("evaluation_label", "info_only")
    score = row.get("evaluation_score", 0)
    lines.append(f"\u0627\u0644\u062a\u0642\u064a\u064a\u0645: {label_ar.get(label, label)} ({score:.0%})")
    # Smart advisor enrichment
    try:
        from stock_radar import check_symbol
        analysis = check_symbol(ticker)
        if analysis and not analysis.get("error"):
            lines.append("")
            lines.append("\U0001f9e0 \u062a\u062d\u0644\u064a\u0644 \u0630\u0643\u064a:")
            rsi = analysis.get("rsi")
            if rsi:
                rz = "\u062a\u0634\u0628\u0639 \u0634\u0631\u0627\u0626\u064a" if rsi >= 70 else "\u062a\u0634\u0628\u0639 \u0628\u064a\u0639\u064a" if rsi <= 30 else "\u0645\u062d\u0627\u064a\u062f"
                lines.append(f"  RSI(14): {rsi} ({rz})")
            vwap = analysis.get("vwap")
            if vwap:
                vp = "\u0641\u0648\u0642" if analysis.get("price", 0) > vwap else "\u062a\u062d\u062a"
                lines.append(f"  VWAP: {vwap} ({vp})")
            ef = analysis.get("ema_fast")
            es = analysis.get("ema_slow")
            if ef and es:
                lines.append(f"  EMA9: {ef} | EMA21: {es}")
            sup = analysis.get("support")
            res = analysis.get("resistance")
            if sup and res:
                lines.append(f"  \u0627\u0644\u062f\u0639\u0645: {sup} | \u0627\u0644\u0645\u0642\u0627\u0648\u0645\u0629: {res}")
            vr = analysis.get("vol_ratio", 0)
            if vr:
                lines.append(f"  \u0627\u0644\u062d\u062c\u0645: x{vr:.1f} \u0645\u0646 \u0627\u0644\u0645\u062a\u0648\u0633\u0637")
            verdict = analysis.get("verdict")
            if verdict:
                lines.append(f"  {verdict}")
    except Exception as e:
        logger.debug(f"Smart enrichment skip: {e}")
    if row.get("context_note"):
        lines.append(f"\n{row['context_note']}")
    return chr(10).join(lines)


# ══════════════════════════════════════════════════════════
# WATCHLIST CRUD
# ══════════════════════════════════════════════════════════
def add_watchlist_item(ticker, strategy_name=None, label=None, notes=None, market=None):
    ticker = normalize_ticker(ticker)
    now = _now()
    db = _conn()
    existing = db.execute(
        "SELECT id FROM tv_watchlists WHERE ticker=? AND is_active=1", (ticker,)
    ).fetchone()
    if existing:
        db.close()
        return f"\u26a0\ufe0f {ticker} \u0645\u0648\u062c\u0648\u062f \u0628\u0627\u0644\u0641\u0639\u0644 \u0641\u064a \u0627\u0644\u0648\u0627\u062a\u0634 \u0644\u064a\u0633\u062a"
    db.execute(
        "INSERT INTO tv_watchlists (ticker,market,label,strategy_name,notes,is_active,created_at,updated_at) "
        "VALUES (?,?,?,?,?,1,?,?)",
        (ticker, market or "", label or "", strategy_name or "", notes or "", now, now)
    )
    db.commit()
    db.close()
    return f"\u2705 {ticker} \u0627\u0646\u0636\u0627\u0641 \u0644\u0644\u0648\u0627\u062a\u0634 \u0644\u064a\u0633\u062a"

def remove_watchlist_item(ticker):
    ticker = normalize_ticker(ticker)
    db = _conn()
    cur = db.execute(
        "UPDATE tv_watchlists SET is_active=0, updated_at=? WHERE ticker=? AND is_active=1",
        (_now(), ticker)
    )
    db.commit()
    db.close()
    if cur.rowcount > 0:
        return f"\u2705 {ticker} \u0627\u0646\u0634\u0627\u0644 \u0645\u0646 \u0627\u0644\u0648\u0627\u062a\u0634 \u0644\u064a\u0633\u062a"
    return f"\u26a0\ufe0f {ticker} \u0645\u0648 \u0645\u0648\u062c\u0648\u062f \u0641\u064a \u0627\u0644\u0648\u0627\u062a\u0634 \u0644\u064a\u0633\u062a"

def sync_tv_from_radar():
    """Sync TV watchlist from radar watchlist. Returns summary string."""
    now = _now()
    db = _conn()
    # Get radar symbols from stock_radar_watchlist
    try:
        radar_rows = db.execute(
            "SELECT symbol FROM stock_radar_watchlist WHERE is_active=1"
        ).fetchall()
    except Exception:
        db.close()
        return "\u274c stock_radar_watchlist table not found"
    radar_symbols = [r[0] for r in radar_rows]
    if not radar_symbols:
        db.close()
        return "\u26a0\ufe0f radar watchlist is empty"
    # Deactivate all current TV watchlist items
    db.execute("UPDATE tv_watchlists SET is_active=0, updated_at=?", (now,))
    # Insert/reactivate radar symbols
    added = 0
    for sym in radar_symbols:
        existing = db.execute(
            "SELECT id FROM tv_watchlists WHERE ticker=?", (sym,)
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE tv_watchlists SET is_active=1, updated_at=? WHERE id=?",
                (now, existing[0])
            )
        else:
            db.execute(
                "INSERT INTO tv_watchlists (ticker,market,label,strategy_name,notes,is_active,created_at,updated_at) "
                "VALUES (?,?,?,?,?,1,?,?)",
                (sym, "KSE", "", "Radar EMA9/21", "auto-synced from radar", now, now)
            )
        added += 1
    db.commit()
    db.close()
    return f"\u2705 \u062a\u0645 \u0645\u0632\u0627\u0645\u0646\u0629 {added} \u0633\u0647\u0645 \u0645\u0646 \u0627\u0644\u0631\u0627\u062f\u0627\u0631 \u0625\u0644\u0649 TV watchlist"


def list_watchlist_items(active_only=True):
    db = _conn()
    q = "SELECT * FROM tv_watchlists"
    if active_only:
        q += " WHERE is_active=1"
    q += " ORDER BY ticker"
    rows = db.execute(q).fetchall()
    db.close()
    return [dict(r) for r in rows]

def format_watchlist_tg(items):
    if not items:
        return "\U0001f4cb \u0627\u0644\u0648\u0627\u062a\u0634 \u0644\u064a\u0633\u062a \u0641\u0627\u0636\u064a\u0629"
    lines = [f"\U0001f4cb \u0627\u0644\u0648\u0627\u062a\u0634 \u0644\u064a\u0633\u062a ({len(items)})"]
    for w in items:
        strat = f" [{w.get('strategy_name')}]" if w.get("strategy_name") else ""
        label = f" - {w.get('label')}" if w.get("label") else ""
        lines.append(f"  \u2022 {w['ticker']}{strat}{label}")
    return chr(10).join(lines)


# ══════════════════════════════════════════════════════════
# QUERY FUNCTIONS
# ══════════════════════════════════════════════════════════
def get_last_signal_for_ticker(ticker):
    ticker = normalize_ticker(ticker)
    db = _conn()
    row = db.execute(
        "SELECT * FROM tv_alert_events WHERE ticker=? ORDER BY received_at DESC LIMIT 1",
        (ticker,)
    ).fetchone()
    db.close()
    return dict(row) if row else None

def format_last_signal_tg(row):
    if not row:
        return "\u26a0\ufe0f \u0644\u0627 \u0625\u0634\u0627\u0631\u0627\u062a \u0645\u0633\u062c\u0644\u0629"
    return render_tv_alert_message(row)

def get_signal_summary(period="day", ticker=None):
    """Get signal summary for period. period: day|week|month."""
    days_map = {"day": 1, "today": 1, "week": 7, "month": 30}
    days = days_map.get(period, 1)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db = _conn()
    q = "SELECT * FROM tv_alert_events WHERE received_at >= ?"
    params = [since]
    if ticker:
        ticker = normalize_ticker(ticker)
        q += " AND ticker = ?"
        params.append(ticker)
    q += " ORDER BY received_at DESC"
    rows = db.execute(q, params).fetchall()
    db.close()
    return [dict(r) for r in rows]

def format_summary_tg(rows, period="day"):
    period_ar = {"day": "\u0627\u0644\u064a\u0648\u0645", "today": "\u0627\u0644\u064a\u0648\u0645",
                 "week": "\u0627\u0644\u0623\u0633\u0628\u0648\u0639", "month": "\u0627\u0644\u0634\u0647\u0631"}
    if not rows:
        return f"\U0001f4ca \u0644\u0627 \u0625\u0634\u0627\u0631\u0627\u062a {period_ar.get(period, period)}"

    lines = [f"\U0001f4ca \u0645\u0644\u062e\u0635 \u0625\u0634\u0627\u0631\u0627\u062a {period_ar.get(period, period)} ({len(rows)})"]
    # Group by ticker
    by_ticker = {}
    for r in rows:
        t = r.get("ticker", "?")
        by_ticker.setdefault(t, []).append(r)
    for t, signals in sorted(by_ticker.items()):
        sig_types = set(s.get("signal", "?") for s in signals)
        labels = set(s.get("evaluation_label", "?") for s in signals)
        lines.append(f"  {t}: {len(signals)} \u0625\u0634\u0627\u0631\u0629 ({', '.join(sig_types)})")
    return chr(10).join(lines)


def get_stats_summary():
    """Overall TV signal stats."""
    db = _conn()
    total_signals = db.execute("SELECT COUNT(*) as c FROM tv_alert_events").fetchone()["c"]
    today = date.today().isoformat()
    today_count = db.execute(
        "SELECT COUNT(*) as c FROM tv_alert_events WHERE received_at >= ?",
        (today + "T00:00:00Z",)
    ).fetchone()["c"]
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    week_count = db.execute(
        "SELECT COUNT(*) as c FROM tv_alert_events WHERE received_at >= ?",
        (week_ago + "T00:00:00Z",)
    ).fetchone()["c"]
    top_ticker = db.execute(
        "SELECT ticker, COUNT(*) as c FROM tv_alert_events GROUP BY ticker ORDER BY c DESC LIMIT 1"
    ).fetchone()
    top_strategy = db.execute(
        "SELECT strategy_name, COUNT(*) as c FROM tv_alert_events WHERE strategy_name != '' "
        "GROUP BY strategy_name ORDER BY c DESC LIMIT 1"
    ).fetchone()
    wl_count = db.execute("SELECT COUNT(*) as c FROM tv_watchlists WHERE is_active=1").fetchone()["c"]
    db.close()

    lines = ["\U0001f4ca \u0625\u062d\u0635\u0627\u0626\u064a\u0627\u062a TradingView"]
    lines.append(f"\u0627\u0644\u0625\u0634\u0627\u0631\u0627\u062a: {total_signals} \u0625\u062c\u0645\u0627\u0644\u064a | {today_count} \u0627\u0644\u064a\u0648\u0645 | {week_count} \u0647\u0627\u0644\u0623\u0633\u0628\u0648\u0639")
    if top_ticker:
        lines.append(f"\u0623\u0643\u062b\u0631 \u0633\u0647\u0645: {top_ticker['ticker']} ({top_ticker['c']})")
    if top_strategy:
        lines.append(f"\u0623\u0643\u062b\u0631 \u0627\u0633\u062a\u0631\u0627\u062a\u064a\u062c\u064a\u0629: {top_strategy['strategy_name']} ({top_strategy['c']})")
    lines.append(f"\u0627\u0644\u0648\u0627\u062a\u0634 \u0644\u064a\u0633\u062a: {wl_count} \u0633\u0647\u0645")
    return chr(10).join(lines)


# ══════════════════════════════════════════════════════════
# TEST HELPER
# ══════════════════════════════════════════════════════════
def generate_test_payload():
    """Generate a test payload for /tv_test."""
    return {
        "secret": _get_config("tv_webhook_secret") or "test",
        "ticker": "KSE:KFH",
        "exchange": "KSE",
        "interval": "1D",
        "price": 813,
        "volume": 1245000,
        "signal": "breakout",
        "strategy": "Kuwait_Breakout_v1",
        "time": _now()
    }


# ══════════════════════════════════════════════════════════
# WEBHOOK HANDLER
# ══════════════════════════════════════════════════════════
def handle_webhook(payload):
    """Main webhook handler. Returns (status_code, response_dict)."""
    if not payload or not isinstance(payload, dict):
        return 400, {"ok": False, "error": "invalid payload"}

    if not verify_tv_secret(payload):
        logger.warning(f"TV webhook: bad secret from payload")
        return 403, {"ok": False, "error": "invalid secret"}

    enabled = _get_config("tv_alerts_enabled")
    if enabled and enabled.lower() == "false":
        return 200, {"ok": True, "message": "alerts disabled"}

    try:
        saved_id, row = save_tv_alert(payload)
        tg_message = render_tv_alert_message(row)
        return 200, {
            "ok": True,
            "saved_id": saved_id,
            "evaluation": row.get("evaluation_label"),
            "tg_message": tg_message
        }
    except Exception as e:
        logger.error(f"TV webhook error: {e}")
        return 500, {"ok": False, "error": str(e)}


def mark_telegram_sent(alert_id):
    """Mark alert as sent via Telegram."""
    db = _conn()
    db.execute(
        "UPDATE tv_alert_events SET telegram_sent=1, telegram_sent_at=? WHERE id=?",
        (_now(), alert_id)
    )
    db.commit()
    db.close()


# ══════════════════════════════════════════════════════════
# TG COMMAND HANDLERS
# ══════════════════════════════════════════════════════════
def handle_tv_watchlist():
    """/tv_watchlist"""
    items = list_watchlist_items()
    return format_watchlist_tg(items)

def handle_tv_add(args_text):
    """/tv_add KSE:KFH breakout"""
    if not args_text or not args_text.strip():
        return ("\u0627\u0644\u0627\u0633\u062a\u062e\u062f\u0627\u0645:\n"
                "/tv_add KFH breakout\n"
                "/tv_add KSE:NBK volume\n"
                "/tv_add CLEANING")
    parts = args_text.strip().split()
    ticker = parts[0]
    strategy = parts[1] if len(parts) > 1 else None
    label = parts[2] if len(parts) > 2 else None
    return add_watchlist_item(ticker, strategy_name=strategy, label=label)

def handle_tv_remove(args_text):
    """/tv_remove KFH"""
    if not args_text or not args_text.strip():
        return "\u0627\u0644\u0627\u0633\u062a\u062e\u062f\u0627\u0645: /tv_remove KFH"
    return remove_watchlist_item(args_text.strip())

def handle_tv_last(args_text):
    """/tv_last KFH"""
    if not args_text or not args_text.strip():
        return "\u0627\u0644\u0627\u0633\u062a\u062e\u062f\u0627\u0645: /tv_last KFH"
    row = get_last_signal_for_ticker(args_text.strip())
    return format_last_signal_tg(row)

def handle_tv_summary(args_text=None):
    """/tv_summary [day|week]"""
    period = "day"
    if args_text and args_text.strip().lower() in ("week", "month"):
        period = args_text.strip().lower()
    rows = get_signal_summary(period)
    return format_summary_tg(rows, period)

def handle_tv_test():
    """/tv_test — inject test signal"""
    payload = generate_test_payload()
    payload["signal"] = "test_signal"
    payload["strategy"] = "test_strategy"
    # Skip secret check for test
    try:
        saved_id, row = save_tv_alert(payload)
        msg = render_tv_alert_message(row)
        return f"\u2705 \u062a\u0645 \u062d\u0641\u0638 \u0625\u0634\u0627\u0631\u0629 \u062a\u062c\u0631\u064a\u0628\u064a\u0629 #{saved_id}\n\n{msg}"
    except Exception as e:
        return f"\u274c \u062e\u0637\u0623: {e}"

def handle_tv_stats():
    """/tv_stats"""
    return get_stats_summary()


# ══════════════════════════════════════════════════════════
# QUICK QUERY HANDLERS
# ══════════════════════════════════════════════════════════
def quick_tv_watchlist():
    return handle_tv_watchlist()

def quick_tv_last(ticker):
    row = get_last_signal_for_ticker(ticker)
    return format_last_signal_tg(row)

def quick_tv_summary_today():
    rows = get_signal_summary("day")
    return format_summary_tg(rows, "day")

def quick_tv_summary_week():
    rows = get_signal_summary("week")
    return format_summary_tg(rows, "week")


# ══════════════════════════════════════════════════════════
# LLM TOOL HANDLERS
# ══════════════════════════════════════════════════════════
def llm_tool_tv_watchlist_add(ticker, strategy_name=None, label=None, notes=None):
    result = add_watchlist_item(ticker, strategy_name, label, notes)
    return {"ok": True, "text": result}

def llm_tool_tv_watchlist_list(active_only=True):
    items = list_watchlist_items(active_only)
    return {"ok": True, "text": format_watchlist_tg(items), "count": len(items)}

def llm_tool_tv_last_signal(ticker):
    row = get_last_signal_for_ticker(ticker)
    if not row:
        return {"ok": True, "text": f"\u0644\u0627 \u0625\u0634\u0627\u0631\u0627\u062a \u0645\u0633\u062c\u0644\u0629 \u0644\u0640 {ticker}"}
    return {"ok": True, "text": render_tv_alert_message(row), "data": {
        "ticker": row.get("ticker"), "signal": row.get("signal"),
        "price": row.get("price"), "interval": row.get("interval"),
        "evaluation_label": row.get("evaluation_label"),
        "received_at": row.get("received_at")
    }}

def llm_tool_tv_signal_summary(period="day", ticker=None):
    rows = get_signal_summary(period, ticker)
    return {"ok": True, "text": format_summary_tg(rows, period), "count": len(rows)}


# ══════════════════════════════════════════════════════════
# HOUSEKEEPING
# ══════════════════════════════════════════════════════════
def run_tv_housekeeping():
    """Clean old data (90+ days). Call from nightly cron."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db = _conn()
    cur = db.execute("DELETE FROM tv_alert_events WHERE received_at < ?", (cutoff,))
    deleted = cur.rowcount
    db.commit()
    db.close()
    if deleted > 0:
        logger.info(f"TV housekeeping: deleted {deleted} old alerts")
    return deleted


def get_morning_tv_text():
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db = _conn()
    cnt = db.execute("SELECT COUNT(*) as c FROM tv_alert_events WHERE received_at>=?", (since,)).fetchone()["c"]
    strong = db.execute("SELECT COUNT(*) as c FROM tv_alert_events WHERE received_at>=? AND evaluation_label='strong_watch'", (since,)).fetchone()["c"]
    db.close()
    if cnt == 0:
        return ""
    parts = [f"{cnt} إشارة"]
    if strong > 0:
        parts.append(f"{strong} قوية")
    return f"📡 TradingView: {' | '.join(parts)}"
