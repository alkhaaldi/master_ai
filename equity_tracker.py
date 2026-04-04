"""
equity_tracker.py -- Equity Curve + Drawdown Tracker for V2 Phase 2.
Takes daily snapshots of portfolio value, tracks peak and drawdown.
"""
import logging
import sqlite3
from datetime import datetime

logger = logging.getLogger("equity_tracker")
_LIFE_DB = "data/life.db"


def _conn():
    c = sqlite3.connect(_LIFE_DB, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def take_daily_snapshot():
    """Take a daily equity snapshot. Run once per day (e.g. 1:00 PM)."""
    try:
        from risk_engine import _get_risk_config
        capital = _get_risk_config()["account_capital"]
    except Exception:
        capital = 10000

    c = _conn()
    today = datetime.now().strftime("%Y-%m-%d")

    # Count paper trades
    open_count = c.execute("SELECT COUNT(*) FROM paper_trades WHERE status='open'").fetchone()[0]

    # Closed stats
    wins = c.execute("SELECT COUNT(*) FROM paper_trades WHERE status='closed' AND pnl_net > 0").fetchone()[0]
    losses = c.execute("SELECT COUNT(*) FROM paper_trades WHERE status='closed' AND pnl_net <= 0").fetchone()[0]
    total_closed_pnl = c.execute("SELECT COALESCE(SUM(pnl_net), 0) FROM paper_trades WHERE status='closed'").fetchone()[0]

    # Open positions value (unrealized)
    open_rows = c.execute("""
        SELECT p.symbol, p.actual_entry, p.shares,
               COALESCE(r.price, p.actual_entry) as current_price
        FROM paper_trades p
        LEFT JOIN stock_radar_daily r ON r.symbol = p.symbol
        WHERE p.status='open'
    """).fetchall()

    open_value = 0
    unrealized_pnl = 0
    for r in open_rows:
        pos_val = r["current_price"] * r["shares"]
        open_value += pos_val
        unrealized_pnl += (r["current_price"] - r["actual_entry"]) * r["shares"]

    total_equity = capital + total_closed_pnl + unrealized_pnl
    daily_pnl = unrealized_pnl  # simplified: just unrealized change

    # Get previous peak
    prev = c.execute("SELECT MAX(peak_equity) FROM equity_snapshots").fetchone()
    prev_peak = prev[0] if prev and prev[0] else capital
    peak = max(prev_peak, total_equity)
    drawdown_pct = ((peak - total_equity) / peak * 100) if peak > 0 else 0

    c.execute("""INSERT OR REPLACE INTO equity_snapshots
        (date, cash_kwd, open_positions_value, total_equity, daily_pnl,
         peak_equity, drawdown_pct, open_count, win_count_total, loss_count_total)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
    try:
        from risk_engine import _get_risk_config
        capital = _get_risk_config()["account_capital"]
    except Exception:
        capital = 10000

    c = _conn()

    # Get all snapshots for curve
    snapshots = [dict(r) for r in c.execute(
        "SELECT date, total_equity, drawdown_pct, daily_pnl, open_count FROM equity_snapshots ORDER BY date ASC"
    ).fetchall()]

    # Latest stats
    latest = c.execute("SELECT * FROM equity_snapshots ORDER BY date DESC LIMIT 1").fetchone()
    latest = dict(latest) if latest else {}

    # Paper trade stats
    stats_row = c.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN pnl_net > 0 THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN pnl_net <= 0 THEN 1 ELSE 0 END) as losses,
               COALESCE(AVG(CASE WHEN pnl_net > 0 THEN pnl_net END), 0) as avg_win,
               COALESCE(AVG(CASE WHEN pnl_net <= 0 THEN pnl_net END), 0) as avg_loss,
               COALESCE(AVG(holding_days), 0) as avg_holding
        FROM paper_trades WHERE status='closed'
    """).fetchone()
    stats = dict(stats_row) if stats_row else {}

    total_closed = stats.get("total", 0)
    win_rate = (stats.get("wins", 0) / total_closed * 100) if total_closed > 0 else 0
    avg_win = stats.get("avg_win", 0)
    avg_loss = stats.get("avg_loss", 0)
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
