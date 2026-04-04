"""
paper_trading.py — Paper Trading Engine for V2 Phase 2.
Simulates real trading with slippage and commission tracking.
"""
import logging
import sqlite3
from datetime import datetime, timedelta

logger = logging.getLogger("paper_trading")
_LIFE_DB = "data/life.db"

# KSE realistic constants
ESTIMATED_SLIPPAGE_PCT = 0.15   # 0.15% slippage
BROKER_COMMISSION_PCT = 0.125   # 0.125% each way (0.25% round trip)


def _conn():
    c = sqlite3.connect(_LIFE_DB, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def open_paper_trade(signal: dict) -> dict:
    """Open a paper trade from a signal."""
    entry_price = signal.get("price", 0)
    stop_loss = signal.get("swing_stop", 0)
    target = signal.get("swing_target", 0)
    symbol = signal.get("symbol", "")

    if not entry_price or not symbol:
        return {"error": "missing price or symbol"}

    # Calculate position size from risk engine
    shares = 0
    try:
        from risk_engine import calculate_position_size
        if entry_price and stop_loss and entry_price > stop_loss:
            sizing = calculate_position_size(entry_price, stop_loss)
            shares = sizing.get("shares", 0)
    except Exception:
        shares = int(200 / entry_price) if entry_price > 0 else 0  # fallback: 200 KWD

    slippage = entry_price * (ESTIMATED_SLIPPAGE_PCT / 100)
    actual_entry = round(entry_price + slippage, 3)
    commission = round(actual_entry * shares * (BROKER_COMMISSION_PCT / 100), 3)

    now = datetime.now().isoformat()
    c = _conn()
    c.execute("""INSERT INTO paper_trades
        (symbol, direction, signal_price, actual_entry, entry_slippage, shares,
         stop_loss, target, entry_commission, status,
         regime_at_entry, confluence_at_entry, adx_at_entry, volume_at_entry, opened_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (symbol, "long", entry_price, actual_entry, round(slippage, 4), shares,
         stop_loss, target, commission, "open",
         signal.get("market_regime", "UNKNOWN"),
         signal.get("swing_confluence_pct", 0),
         signal.get("adx", 0), signal.get("vol_ratio", 0), now))
    trade_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.commit()
    c.close()

    logger.info(f"Paper trade opened: {symbol} {shares} shares @ {actual_entry}")
    return {
        "id": trade_id, "symbol": symbol, "shares": shares,
        "signal_price": entry_price, "actual_entry": actual_entry,
        "slippage_fils": round(slippage * 1000, 1),
        "commission_kwd": commission, "stop_loss": stop_loss, "target": target,
    }


def close_paper_trade(trade_id: int, exit_price: float, exit_reason: str) -> dict:
    """Close an open paper trade."""
    c = _conn()
    trade = c.execute("SELECT * FROM paper_trades WHERE id=? AND status='open'", (trade_id,)).fetchone()
    if not trade:
        c.close()
        return {"error": f"trade {trade_id} not found or already closed"}

    trade = dict(trade)
    slippage = exit_price * (ESTIMATED_SLIPPAGE_PCT / 100)
    actual_exit = round(exit_price - slippage, 3)
    commission = round(actual_exit * trade["shares"] * (BROKER_COMMISSION_PCT / 100), 3)
    pnl_gross = round((actual_exit - trade["actual_entry"]) * trade["shares"], 3)
    pnl_net = round(pnl_gross - trade["entry_commission"] - commission, 3)

    opened = datetime.fromisoformat(trade["opened_at"]) if trade["opened_at"] else datetime.now()
    holding_days = (datetime.now() - opened).days

    now = datetime.now().isoformat()
    c.execute("""UPDATE paper_trades SET
        status='closed', exit_price=?, exit_slippage=?, exit_commission=?,
        exit_reason=?, pnl_gross=?, pnl_net=?, holding_days=?, closed_at=?
        WHERE id=?""",
        (actual_exit, round(slippage, 4), commission,
         exit_reason, pnl_gross, pnl_net, holding_days, now, trade_id))
    c.commit()
    c.close()

    logger.info(f"Paper trade closed: #{trade_id} {trade['symbol']} PnL={pnl_net}")
    return {
        "id": trade_id, "symbol": trade["symbol"],
        "exit_price": actual_exit, "exit_reason": exit_reason,
        "pnl_gross": pnl_gross, "pnl_net": pnl_net,
        "holding_days": holding_days,
        "total_commission": round(trade["entry_commission"] + commission, 3),
        "total_slippage_fils": round((trade["entry_slippage"] + slippage) * 1000, 1),
    }


def check_paper_exits():
    """Daily check: close paper trades that hit stop or target."""
    c = _conn()
    open_trades = c.execute("SELECT * FROM paper_trades WHERE status='open'").fetchall()
    closed = []
    for t in open_trades:
        t = dict(t)
        symbol = t["symbol"]
        # Get current price from radar daily
        row = c.execute(
            "SELECT price FROM stock_radar_daily WHERE symbol=?", (symbol,)).fetchone()
        if not row:
            continue
        current_price = row[0]
        if not current_price:
            continue

        # Check stop
        if t["stop_loss"] and current_price <= t["stop_loss"]:
            result = close_paper_trade(t["id"], current_price, "stop_hit")
            closed.append(result)
        # Check target
        elif t["target"] and current_price >= t["target"]:
            result = close_paper_trade(t["id"], current_price, "target_hit")
            closed.append(result)
    c.close()
    return closed


def get_paper_trading_stats() -> dict:
    """Full paper trading dashboard data."""
    c = _conn()

    open_trades = [dict(r) for r in c.execute(
        "SELECT * FROM paper_trades WHERE status='open' ORDER BY opened_at DESC").fetchall()]
    closed_trades = [dict(r) for r in c.execute(
        "SELECT * FROM paper_trades WHERE status='closed' ORDER BY closed_at DESC LIMIT 50").fetchall()]

    # Stats
    wins = [t for t in closed_trades if (t.get("pnl_net") or 0) > 0]
    losses = [t for t in closed_trades if (t.get("pnl_net") or 0) <= 0]
    total_closed = len(closed_trades)
    win_rate = (len(wins) / total_closed * 100) if total_closed > 0 else 0
    avg_win = sum(t["pnl_net"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl_net"] for t in losses) / len(losses) if losses else 0
    total_pnl = sum(t.get("pnl_net", 0) for t in closed_trades)
    total_slippage = sum((t.get("entry_slippage", 0) + (t.get("exit_slippage") or 0))
                         for t in closed_trades) * 1000  # in fils
    total_commission = sum((t.get("entry_commission", 0) + (t.get("exit_commission") or 0))
                           for t in closed_trades)

    # Account tracking
    try:
        from risk_engine import _get_risk_config
        capital = _get_risk_config()["account_capital"]
    except Exception:
        capital = 10000

    account_current = capital + total_pnl

    c.close()
    return {
        "mode": "paper",
        "account_start": capital,
        "account_current": round(account_current, 3),
        "total_return_pct": round((total_pnl / capital) * 100, 2) if capital else 0,
        "total_trades": len(open_trades) + total_closed,
        "open_trades": len(open_trades),
        "closed_trades": total_closed,
        "win_rate": round(win_rate, 1),
        "avg_win_kwd": round(avg_win, 3),
        "avg_loss_kwd": round(avg_loss, 3),
        "total_pnl_kwd": round(total_pnl, 3),
        "total_slippage_fils": round(total_slippage, 1),
        "total_commission_kwd": round(total_commission, 3),
        "open_positions": open_trades,
        "recent_closed": closed_trades[:20],
    }
