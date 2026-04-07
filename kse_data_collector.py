"""
kse_data_collector.py — KSE Daily Data Collector & Decision Audit
Phase 4 of Master Plan V10

1. Collects daily OHLCV bars for all KSE stocks via Bridge API
2. Stores in daily_bars table for independent historical data
3. Logs collection runs in data_fetch_runs
4. Provides decision_audit table for tracking ENTER outcomes
5. Scheduled daily at 2 PM Kuwait (after market close)
"""

import os
import json
import sqlite3
import logging
import time
from datetime import datetime, date, timedelta

logger = logging.getLogger("kse_data_collector")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")

BRIDGE_URL = "http://192.168.111.159:8059"
BATCH_SIZE = 5
BATCH_TIMEOUT = 90


# ═══════════════════════════════════════════════════
# DB HELPERS
# ═══════════════════════════════════════════════════

def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_collector_schema():
    """Create tables for data collection and decision audit."""
    with _conn() as c:
        c.executescript("""
            -- Daily OHLCV bars
            CREATE TABLE IF NOT EXISTS daily_bars (
                symbol TEXT NOT NULL,
                trading_date DATE NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                value_kwd REAL,
                source TEXT DEFAULT 'bridge',
                fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_final BOOLEAN DEFAULT 1,
                UNIQUE(symbol, trading_date)
            );
            CREATE INDEX IF NOT EXISTS idx_db_symbol ON daily_bars(symbol);
            CREATE INDEX IF NOT EXISTS idx_db_date ON daily_bars(trading_date);

            -- Data fetch run log
            CREATE TABLE IF NOT EXISTS data_fetch_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date DATE NOT NULL,
                source TEXT DEFAULT 'bridge',
                status TEXT NOT NULL,
                symbols_fetched INTEGER DEFAULT 0,
                symbols_expected INTEGER DEFAULT 0,
                duration_sec REAL,
                error_msg TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            -- Decision audit trail
            CREATE TABLE IF NOT EXISTS decision_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                decision_time DATETIME NOT NULL,
                market_date DATE NOT NULL,
                smart_decision TEXT NOT NULL,
                chosen_plan_source TEXT,
                entry_price REAL,
                stop_price REAL,
                target_1 REAL,
                target_2 REAL,
                rr_ratio REAL,
                confidence REAL,
                data_quality INTEGER,
                data_freshness TEXT,
                sr_status TEXT,
                strategy_id TEXT,
                strategy_ev REAL,
                risk_flags TEXT,
                sector TEXT,
                outcome TEXT DEFAULT 'pending',
                outcome_date DATE,
                actual_gain_pct REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_da_symbol ON decision_audit(symbol, market_date);
            CREATE INDEX IF NOT EXISTS idx_da_decision ON decision_audit(smart_decision);
            CREATE INDEX IF NOT EXISTS idx_da_outcome ON decision_audit(outcome);
        """)
    logger.info("collector schema initialized")


# ═══════════════════════════════════════════════════
# DATA COLLECTION
# ═══════════════════════════════════════════════════

def _get_watchlist_symbols() -> list:
    """Get all tracked symbols."""
    try:
        from stock_radar import get_watchlist
        wl = get_watchlist()
        return [w["symbol"] for w in wl]
    except Exception:
        pass
    # Fallback: from DB
    try:
        with _conn() as c:
            rows = c.execute("SELECT DISTINCT symbol FROM stock_radar_daily ORDER BY symbol").fetchall()
            return [r["symbol"] for r in rows]
    except Exception:
        return []


def _fetch_bridge_bars(symbols: list) -> dict:
    """Fetch 1D bars from Bridge API. Returns {symbol: {open,high,low,close,volume}}."""
    import requests as _req

    results = {}
    for i in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[i:i + BATCH_SIZE]
        try:
            r = _req.get(
                f"{BRIDGE_URL}/multi-analysis",
                params={"symbols": ",".join(batch), "exchange": "KSE", "interval": "1D", "bars": 5},
                timeout=BATCH_TIMEOUT,
            )
            if r.status_code == 200:
                data = r.json()
                for item in data.get("results", []):
                    sym_raw = item.get("symbol", "")
                    sym = sym_raw.split(":")[-1] if ":" in sym_raw else sym_raw
                    q = item.get("quote", {})
                    results[sym] = {
                        "open": float(q.get("open") or 0),
                        "high": float(q.get("high") or 0),
                        "low": float(q.get("low") or 0),
                        "close": float(item.get("price") or q.get("price") or q.get("close") or 0),
                        "volume": int(q.get("volume") or 0),
                    }
        except Exception as e:
            logger.warning("Bridge batch %s: %s", batch[:3], e)
    return results


def collect_daily_bars() -> dict:
    """
    Main collection function. Fetches all symbols, stores in daily_bars.
    Returns summary dict.
    """
    init_collector_schema()
    symbols = _get_watchlist_symbols()
    if not symbols:
        return {"status": "failed", "error": "no symbols"}

    today = date.today().isoformat()
    t0 = time.time()
    expected = len(symbols)

    # Fetch from Bridge
    bars = _fetch_bridge_bars(symbols)
    duration = round(time.time() - t0, 1)

    if not bars:
        _log_run(today, "bridge", "failed", 0, expected, duration, "bridge returned no data")
        return {"status": "failed", "error": "bridge_no_data", "duration_sec": duration}

    # Store in daily_bars
    fetched = 0
    with _conn() as c:
        for sym, bar in bars.items():
            if bar.get("close", 0) <= 0:
                continue
            try:
                # Calculate approximate value in KWD
                value_kwd = (bar["close"] * bar["volume"]) / 1000.0 if bar["volume"] > 0 else 0
                c.execute(
                    """INSERT OR REPLACE INTO daily_bars
                       (symbol, trading_date, open, high, low, close, volume, value_kwd, source, is_final)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'bridge', 1)""",
                    (sym, today, bar["open"], bar["high"], bar["low"], bar["close"],
                     bar["volume"], round(value_kwd, 1)),
                )
                fetched += 1
            except Exception as e:
                logger.debug("daily_bars insert %s: %s", sym, e)

    _log_run(today, "bridge", "success", fetched, expected, duration, None)

    summary = {
        "status": "success",
        "date": today,
        "symbols_fetched": fetched,
        "symbols_expected": expected,
        "coverage_pct": round(fetched / expected * 100, 1) if expected > 0 else 0,
        "duration_sec": duration,
    }
    logger.info("Daily collection: %d/%d symbols in %.1fs", fetched, expected, duration)
    return summary


def _log_run(run_date, source, status, fetched, expected, duration, error):
    """Log a data fetch run."""
    try:
        with _conn() as c:
            c.execute(
                """INSERT INTO data_fetch_runs
                   (run_date, source, status, symbols_fetched, symbols_expected, duration_sec, error_msg)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_date, source, status, fetched, expected, duration, error),
            )
    except Exception as e:
        logger.warning("Failed to log run: %s", e)


def collect_and_refresh() -> dict:
    """Collect daily bars, then trigger indicator refresh."""
    # 1. Collect bars
    result = collect_daily_bars()

    # 2. Trigger indicator refresh if collection succeeded
    if result.get("status") == "success":
        try:
            from stock_radar import refresh_daily_snapshot
            refresh_result = refresh_daily_snapshot()
            result["refresh"] = refresh_result
            logger.info("Post-collection refresh: %s", refresh_result)
        except Exception as e:
            logger.warning("Post-collection refresh failed: %s", e)
            result["refresh_error"] = str(e)

    return result


# ═══════════════════════════════════════════════════
# DECISION AUDIT
# ═══════════════════════════════════════════════════

def log_decision(opp: dict):
    """Log an ENTER decision to decision_audit table."""
    init_collector_schema()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = date.today().isoformat()

    plan = opp.get("chosen_plan") or {}
    sm = opp.get("strategy_match") or {}

    # Collect risk flags
    risk_flags = []
    if opp.get("risk_flag"):
        risk_flags.append(opp["risk_flag"])
    if opp.get("fallback_levels"):
        risk_flags.append("fallback_sr")
    if opp.get("data_freshness") in ("stale_old", "missing"):
        risk_flags.append("stale_data")

    try:
        with _conn() as c:
            # Check if already logged today for this symbol
            existing = c.execute(
                "SELECT id FROM decision_audit WHERE symbol=? AND market_date=? AND smart_decision=?",
                (opp.get("symbol", ""), today, opp.get("smart_decision", "")),
            ).fetchone()
            if existing:
                return  # Already logged today

            c.execute(
                """INSERT INTO decision_audit
                   (symbol, decision_time, market_date, smart_decision,
                    chosen_plan_source, entry_price, stop_price, target_1, target_2,
                    rr_ratio, confidence, data_quality, data_freshness, sr_status,
                    strategy_id, strategy_ev, risk_flags, sector)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    opp.get("symbol", ""),
                    now,
                    today,
                    opp.get("smart_decision", ""),
                    plan.get("source", ""),
                    plan.get("entry"),
                    plan.get("stop"),
                    plan.get("target1"),
                    plan.get("target2"),
                    plan.get("rr"),
                    opp.get("confidence"),
                    opp.get("data_quality"),
                    opp.get("data_freshness"),
                    opp.get("sr_status"),
                    sm.get("strategy_id"),
                    sm.get("ev"),
                    json.dumps(risk_flags) if risk_flags else None,
                    opp.get("sector"),
                ),
            )
        logger.info("Decision audit: %s %s", opp.get("symbol"), opp.get("smart_decision"))
    except Exception as e:
        logger.warning("Decision audit log failed: %s", e)


# ═══════════════════════════════════════════════════
# DATA HEALTH
# ═══════════════════════════════════════════════════

def get_data_health() -> dict:
    """Get data health summary for API endpoint."""
    init_collector_schema()
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    with _conn() as c:
        # Last fetch run
        last_run = c.execute(
            "SELECT * FROM data_fetch_runs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()

        # Bars collected today
        today_bars = c.execute(
            "SELECT COUNT(*) as cnt FROM daily_bars WHERE trading_date=?", (today,)
        ).fetchone()

        # Bars collected yesterday (in case today hasn't run yet)
        yesterday_bars = c.execute(
            "SELECT COUNT(*) as cnt FROM daily_bars WHERE trading_date=?", (yesterday,)
        ).fetchone()

        # Total unique symbols in daily_bars
        total_symbols = c.execute(
            "SELECT COUNT(DISTINCT symbol) as cnt FROM daily_bars"
        ).fetchone()

        # Oldest bar date
        oldest = c.execute(
            "SELECT MIN(trading_date) as d FROM daily_bars"
        ).fetchone()

        # Radar freshness
        stale_count = 0
        fresh_count = 0
        try:
            radar_rows = c.execute(
                "SELECT symbol, updated_at FROM stock_radar_daily"
            ).fetchall()
            now = datetime.utcnow()
            for r in radar_rows:
                if r["updated_at"]:
                    try:
                        updated = datetime.strptime(r["updated_at"][:19], "%Y-%m-%d %H:%M:%S")
                        age_hours = (now - updated).total_seconds() / 3600
                        if age_hours <= 26:
                            fresh_count += 1
                        else:
                            stale_count += 1
                    except (ValueError, TypeError):
                        stale_count += 1
                else:
                    stale_count += 1
        except Exception:
            pass

        # Recent decisions
        recent_decisions = c.execute(
            """SELECT smart_decision, COUNT(*) as cnt
               FROM decision_audit WHERE market_date >= ?
               GROUP BY smart_decision""",
            ((date.today() - timedelta(days=7)).isoformat(),)
        ).fetchall()

    return {
        "last_fetch_run": dict(last_run) if last_run else None,
        "daily_bars_today": today_bars["cnt"] if today_bars else 0,
        "daily_bars_yesterday": yesterday_bars["cnt"] if yesterday_bars else 0,
        "total_symbols_in_bars": total_symbols["cnt"] if total_symbols else 0,
        "oldest_bar_date": oldest["d"] if oldest else None,
        "radar_fresh": fresh_count,
        "radar_stale": stale_count,
        "radar_total": fresh_count + stale_count,
        "recent_decisions": {r["smart_decision"]: r["cnt"] for r in recent_decisions},
    }


# ═══════════════════════════════════════════════════
# TELEGRAM NOTIFICATION
# ═════════════════════════════════════════════════��═

def _send_collection_alert(result: dict) -> bool:
    """Send Telegram alert with collection results."""
    import requests as _req

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN") or _read_file("~/.telegram_bot_token")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or _read_file("~/.telegram_chat_id")
    if not bot_token or not chat_id:
        return False

    status = result.get("status", "unknown")
    if status == "success":
        emoji = "\u2705"
        text = (
            f"{emoji} <b>\u062c\u0645\u0639 \u0628\u064a\u0627\u0646\u0627\u062a \u064a\u0648\u0645\u064a</b>\n\n"
            f"\U0001f4ca \u0623\u0633\u0647\u0645: {result.get('symbols_fetched', 0)}/{result.get('symbols_expected', 0)}\n"
            f"\U0001f3af \u062a\u063a\u0637\u064a\u0629: {result.get('coverage_pct', 0)}%\n"
            f"\u23f1 \u0645\u062f\u0629: {result.get('duration_sec', 0)}s"
        )
    else:
        emoji = "\u274c"
        text = (
            f"{emoji} <b>\u0641\u0634\u0644 \u062c\u0645\u0639 \u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a</b>\n\n"
            f"\u26a0\ufe0f {result.get('error', 'unknown error')}"
        )

    try:
        r = _req.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        return r.status_code == 200
    except Exception:
        return False


def _read_file(path: str) -> str:
    expanded = os.path.expanduser(path)
    try:
        with open(expanded, "r") as f:
            return f.read().strip()
    except Exception:
        return ""


# ═══════════════════════════════════════════════════
# DAILY SCHEDULER
# ═══════════════════════════════════════════════════

async def daily_collection_scheduler():
    """
    Async scheduler: runs collect_and_refresh() + position monitor daily at 2 PM Kuwait.
    Designed to be started as asyncio.create_task() from server.py.
    """
    import asyncio
    _log = logging.getLogger("daily_collection_scheduler")
    _log.info("Daily collection scheduler started")
    await asyncio.sleep(60)  # let startup complete

    while True:
        try:
            now = datetime.now()
            # Target: 1:30 PM KWT (after market close at 1:00 PM)
            # Pi runs in UTC, 1:30 PM KWT = 10:30 UTC
            target = now.replace(hour=10, minute=30, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)

            wait_secs = (target - now).total_seconds()
            _log.info("Next daily collection in %.1f hours", wait_secs / 3600)
            await asyncio.sleep(wait_secs)

            # Skip Fri(4) and Sat(5) — KSE closed
            kwt_now = datetime.utcnow() + timedelta(hours=3)
            if kwt_now.weekday() in (4, 5):
                _log.info("Weekend (KSE closed) — skipping collection")
                await asyncio.sleep(3600)
                continue

            _log.info("Starting daily collection...")

            # Run collection in executor (sync → async)
            import asyncio as _aio
            loop = _aio.get_event_loop()
            result = await loop.run_in_executor(None, collect_and_refresh)

            _log.info("Daily collection result: %s", result.get("status"))
            _send_collection_alert(result)

            # Also run position monitor
            try:
                from position_engine import run_daily_monitor
                monitor_result = await loop.run_in_executor(None, run_daily_monitor)
                _log.info("Position monitor: %d alerts", monitor_result.get("alerts_generated", 0))
            except Exception as e:
                _log.warning("Position monitor failed: %s", e)

            # Wait at least 23 hours before next run
            await asyncio.sleep(23 * 3600)

        except Exception as e:
            _log.error("Daily collection scheduler error: %s", e, exc_info=True)
            await asyncio.sleep(3600)  # retry in 1 hour


# ═══════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    init_collector_schema()
    print("Schema OK")

    result = collect_and_refresh()
    print(json.dumps(result, ensure_ascii=False, indent=2))

    health = get_data_health()
    print("\nData health:")
    print(json.dumps(health, ensure_ascii=False, indent=2, default=str))
