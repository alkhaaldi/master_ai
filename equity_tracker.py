"""
equity_tracker.py -- Equity Curve + Drawdown Tracker for V2 Phase 2.
Takes daily snapshots of portfolio value, tracks peak and drawdown.

Source of truth is the `trades` table (the real book), NOT `paper_trades`.
`paper_trades` has been empty since inception; reading it made this whole
dashboard report zeros while 7 real closed trades sat in `trades`.

Units: trades.entry_price / exit_price and trades.pnl_fils are in FILS.
Everything this module returns is in KWD, so every read divides by _FILS.
Trades with trade_kind='void' are excluded to stay consistent with
journal_engine, which reports 7 closed trades out of 9 rows.
"""
import logging
import sqlite3
from datetime import datetime

logger = logging.getLogger("equity_tracker")
_LIFE_DB = "data/life.db"
_FILS = 1000.0

# Shared predicate: the real, non-voided book.
_REAL = "COALESCE(trade_kind,'real') <> 'void'"


def _fee_pct():
    """Broker fee per side, from journal_engine so there is one rate."""
    try:
        from journal_engine import BROKER_FEE_PCT
        return float(BROKER_FEE_PCT)
    except Exception:
        return 0.125


def _net_pnl_sql():
    """P&L in KWD net of broker fees, as a SQL expression.

    trades.pnl_fils is GROSS. journal_engine charges BROKER_FEE_PCT on each
    side, so an equity curve built on pnl_fils reads high by the round trip
    - 82 KWD on SENERGY alone - and would disagree with the same trade's row
    on the journal page directly above the chart.
    """
    f = _fee_pct() / 100.0
    return ("(pnl_fils - (entry_price * quantity"
            " + COALESCE(exit_price, entry_price) * quantity) * %r) / %r"
            % (f, _FILS))


def _conn():
    c = sqlite3.connect(_LIFE_DB, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def _capital():
    try:
        from risk_engine import _get_risk_config
        return _get_risk_config()["account_capital"]
    except Exception:
        return 10000


def _closed_stats(c):
    """Realized stats over the real closed book, in KWD, net of fees."""
    net = _net_pnl_sql()
    row = c.execute(
        "SELECT COUNT(*) as total,"
        " SUM(CASE WHEN {n} > 0 THEN 1 ELSE 0 END) as wins,"
        " SUM(CASE WHEN {n} <= 0 THEN 1 ELSE 0 END) as losses,"
        " COALESCE(AVG(CASE WHEN {n} > 0 THEN {n} END), 0) as avg_win,"
        " COALESCE(AVG(CASE WHEN {n} <= 0 THEN {n} END), 0) as avg_loss,"
        " COALESCE(SUM({n}), 0) as total_pnl,"
        " COALESCE(AVG(julianday(exit_date) - julianday(entry_date)), 0) as avg_holding"
        " FROM trades WHERE status='closed' AND {r}".format(n=net, r=_REAL)
    ).fetchone()
    return dict(row) if row else {}


def _open_exposure(c):
    """Open position count, value and unrealized P&L, in KWD."""
    rows = c.execute(
        "SELECT t.symbol, t.entry_price, t.quantity,"
        " COALESCE(r.price, t.entry_price) as current_price"
        " FROM trades t"
        " LEFT JOIN stock_radar_daily r ON r.symbol = t.symbol"
        " WHERE t.status='open' AND " + _REAL
    ).fetchall()

    fee = _fee_pct() / 100.0
    open_value = 0.0
    unrealized = 0.0
    for r in rows:
        qty = r["quantity"] or 0
        entry, cur = r["entry_price"], r["current_price"]
        open_value += (cur * qty) / _FILS
        # Net of the round trip, matching how journal_engine reports an open
        # position: it charges the entry fee already paid plus the exit fee
        # the position will owe. Gross here would make the same trade read
        # differently on the journal page than in the equity total.
        fees = (entry * qty + cur * qty) * fee
        unrealized += ((cur - entry) * qty - fees) / _FILS
    return len(rows), open_value, unrealized


def backfill_snapshots():
    """Rebuild equity_snapshots from closed-trade history.

    take_daily_snapshot() has never had a caller, so equity_snapshots stayed
    empty and the dashboard curve rendered blank. This reconstructs one point
    per exit date from realized P&L, which is deterministic and replayable.
    Returns the number of rows written.
    """
    capital = _capital()
    c = _conn()

    net = _net_pnl_sql()
    rows = c.execute(
        "SELECT exit_date, SUM({n}) as pnl,"
        " SUM(CASE WHEN {n} > 0 THEN 1 ELSE 0 END) as wins,"
        " SUM(CASE WHEN {n} <= 0 THEN 1 ELSE 0 END) as losses"
        " FROM trades"
        " WHERE status='closed' AND exit_date IS NOT NULL AND {r}"
        " GROUP BY exit_date ORDER BY exit_date ASC".format(n=net, r=_REAL)
    ).fetchall()

    equity = capital
    peak = capital
    cum_w = cum_l = 0
    written = 0
    for r in rows:
        equity += r["pnl"]
        cum_w += r["wins"]
        cum_l += r["losses"]
        peak = max(peak, equity)
        dd = ((peak - equity) / peak * 100) if peak > 0 else 0
        c.execute(
            "INSERT OR REPLACE INTO equity_snapshots"
            " (date, cash_kwd, open_positions_value, total_equity, daily_pnl,"
            "  peak_equity, drawdown_pct, open_count, win_count_total, loss_count_total)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (r["exit_date"], round(equity, 3), 0.0, round(equity, 3),
             round(r["pnl"], 3), round(peak, 3), round(dd, 2), 0, cum_w, cum_l))
        written += 1

    c.commit()
    c.close()
    logger.info(f"Equity backfill: {written} snapshots rebuilt from trades")
    return written


def take_daily_snapshot():
    """Take a daily equity snapshot. Run once per day (e.g. 1:00 PM)."""
    capital = _capital()
    c = _conn()
    today = datetime.now().strftime("%Y-%m-%d")

    stats = _closed_stats(c)
    total_closed_pnl = stats.get("total_pnl", 0) or 0
    wins = stats.get("wins", 0) or 0
    losses = stats.get("losses", 0) or 0

    open_count, open_value, unrealized_pnl = _open_exposure(c)

    total_equity = capital + total_closed_pnl + unrealized_pnl
    daily_pnl = unrealized_pnl  # simplified: just unrealized change

    prev = c.execute("SELECT MAX(peak_equity) FROM equity_snapshots").fetchone()
    prev_peak = prev[0] if prev and prev[0] else capital
    peak = max(prev_peak, total_equity)
    drawdown_pct = ((peak - total_equity) / peak * 100) if peak > 0 else 0

    c.execute(
        "INSERT OR REPLACE INTO equity_snapshots"
        " (date, cash_kwd, open_positions_value, total_equity, daily_pnl,"
        "  peak_equity, drawdown_pct, open_count, win_count_total, loss_count_total)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (today, round(capital + total_closed_pnl, 3), round(open_value, 3),
         round(total_equity, 3), round(daily_pnl, 3),
         round(peak, 3), round(drawdown_pct, 2),
         open_count, wins, losses))
    c.commit()
    c.close()

    logger.info(f"Equity snapshot: {total_equity:.0f} KWD, DD={drawdown_pct:.1f}%")
    return {
        "date": today, "total_equity": round(total_equity, 3),
        "peak": round(peak, 3), "drawdown_pct": round(drawdown_pct, 2),
    }


def get_equity_dashboard() -> dict:
    """Full equity dashboard data with curve."""
    capital = _capital()
    c = _conn()

    snapshots = [dict(r) for r in c.execute(
        "SELECT date, total_equity, drawdown_pct, daily_pnl, open_count"
        " FROM equity_snapshots ORDER BY date ASC"
    ).fetchall()]

    latest = c.execute("SELECT * FROM equity_snapshots ORDER BY date DESC LIMIT 1").fetchone()
    latest = dict(latest) if latest else {}

    stats = _closed_stats(c)

    total_closed = stats.get("total", 0) or 0
    win_rate = (stats.get("wins", 0) / total_closed * 100) if total_closed > 0 else 0
    avg_win = stats.get("avg_win", 0) or 0
    avg_loss = stats.get("avg_loss", 0) or 0
    expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss) if total_closed > 0 else 0

    current_equity = latest.get("total_equity", capital)
    peak_equity = latest.get("peak_equity", capital)
    max_dd = max((s.get("drawdown_pct", 0) for s in snapshots), default=0)

    c.close()
    return {
        "current_equity": round(current_equity, 3),
        "peak_equity": round(peak_equity, 3),
        "drawdown_pct": round(latest.get("drawdown_pct", 0), 2),
        "max_drawdown_pct": round(max_dd, 2),
        "total_return_pct": round(((current_equity - capital) / capital) * 100, 2) if capital else 0,
        "win_rate": round(win_rate, 1),
        "expectancy_kwd": round(expectancy, 3),
        "avg_holding_days": round(stats.get("avg_holding", 0), 1),
        "equity_curve": [{"date": s["date"], "equity": s["total_equity"],
                          "drawdown": s.get("drawdown_pct", 0)}
                         for s in snapshots],
        "total_closed_trades": total_closed,
        "capital": capital,
    }
