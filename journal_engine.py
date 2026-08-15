"""
journal_engine.py — Trading Journal for Master AI V12
Tables in life.db: trades
"""
import os
import sqlite3
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger("journal")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")

# ═══════════════════════════════════════════════════
# DB SCHEMA
# ═══════════════════════════════════════════════════

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    name_ar TEXT,
    direction TEXT NOT NULL DEFAULT 'long',
    status TEXT NOT NULL DEFAULT 'open',
    entry_price REAL NOT NULL,
    entry_date TEXT NOT NULL,
    entry_reason TEXT,
    entry_signal_id INTEGER,
    quantity INTEGER DEFAULT 0,
    exit_price REAL,
    exit_date TEXT,
    exit_reason TEXT,
    pnl_fils REAL,
    pnl_pct REAL,
    strategy TEXT,
    timeframe TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(entry_date);
"""


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_schema():
    with _conn() as c:
        c.executescript(_SCHEMA_SQL)
        # Migration: add stop_loss/take_profit columns if missing
        cols = [r[1] for r in c.execute("PRAGMA table_info(trades)").fetchall()]
        if "stop_loss" not in cols:
            c.execute("ALTER TABLE trades ADD COLUMN stop_loss REAL")
        if "take_profit" not in cols:
            c.execute("ALTER TABLE trades ADD COLUMN take_profit REAL")
        if "entry_date_precision" not in cols:
            # PHASE2_SECTION_D D-3: exact|approx - a backdated manual entry
            # must never carry a confident date it does not have
            c.execute("ALTER TABLE trades ADD COLUMN entry_date_precision TEXT")
    c.execute("""CREATE TABLE IF NOT EXISTS trade_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_id INTEGER NOT NULL,
        tx_type TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        price REAL NOT NULL,
        pnl_fils REAL,
        pnl_pct REAL,
        fees REAL DEFAULT 0,
        avg_price_after REAL,
        qty_after INTEGER,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (trade_id) REFERENCES trades(id)
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ttx_trade ON trade_transactions(trade_id)")
    logger.info("Journal schema initialized")

    # Phase 2: Position engine schema (new columns + position_alerts table)
    try:
        from position_engine import init_position_schema
        init_position_schema()
    except Exception as e:
        logger.warning("position_engine schema init skipped: %s", e)


def _row_to_dict(row):
    if row is None:
        return None
    return dict(row)


# ═══════════════════════════════════════════════════
# P&L CALCULATOR — KWD with Broker Fees
# ═══════════════════════════════════════════════════

def calculate_real_pnl(entry_price_fils, current_price_fils, quantity, broker_fee_pct=0.125):
    """Calculate real P&L with broker commission.
    KSE broker fee: ~0.125% per trade (entry + exit = 0.25% total)
    Prices in fils. Returns dict with KWD and fils values.
    """
    entry_total_fils = entry_price_fils * quantity
    current_total_fils = current_price_fils * quantity

    # Broker fees (entry + estimated exit)
    entry_fee_fils = entry_total_fils * (broker_fee_pct / 100)
    exit_fee_fils = current_total_fils * (broker_fee_pct / 100)
    total_fees_fils = entry_fee_fils + exit_fee_fils

    # Net P&L
    gross_pnl_fils = current_total_fils - entry_total_fils
    net_pnl_fils = gross_pnl_fils - total_fees_fils

    # Convert to KWD
    gross_pnl_kwd = gross_pnl_fils / 1000
    net_pnl_kwd = net_pnl_fils / 1000
    entry_total_kwd = entry_total_fils / 1000
    current_total_kwd = current_total_fils / 1000

    # Percentages
    pnl_pct = ((current_price_fils / entry_price_fils) - 1) * 100 if entry_price_fils else 0
    net_pnl_pct = (net_pnl_fils / entry_total_fils) * 100 if entry_total_fils else 0

    return {
        "entry_total_kwd": round(entry_total_kwd, 3),
        "current_total_kwd": round(current_total_kwd, 3),
        "gross_pnl_fils": round(gross_pnl_fils),
        "gross_pnl_kwd": round(gross_pnl_kwd, 3),
        "net_pnl_fils": round(net_pnl_fils),
        "net_pnl_kwd": round(net_pnl_kwd, 3),
        "pnl_pct": round(pnl_pct, 2),
        "net_pnl_pct": round(net_pnl_pct, 2),
        "total_fees_kwd": round(total_fees_fils / 1000, 3),
        "broker_fee_pct": broker_fee_pct,
    }


# ═══════════════════════════════════════════════════
# CORE FUNCTIONS
# ═══════════════════════════════════════════════════

def open_trade(symbol, entry_price, quantity=0, entry_reason="",
               strategy="manual", timeframe="1D", direction="long",
               name_ar="", entry_signal_id=None, stop_loss=None, take_profit=None,
               entry_date=None, entry_date_precision=None):
    """Open a new trade. Returns trade_id.

    entry_date is the date of the ACTUAL trade at the broker, not the day
    the row is typed - trades are logged after the fact, and defaulting to
    today forged same-day entries (PHASE2_SECTION_D, D-3). Required, with
    entry_date_precision "exact" or "approx".
    """
    if not entry_date:
        raise ValueError("entry_date required: the trade date, not the typing date (D-3)")
    if entry_date_precision not in ("exact", "approx"):
        raise ValueError("entry_date_precision must be exact or approx (D-3)")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        c.execute("""INSERT INTO trades
            (symbol, name_ar, direction, status, entry_price, entry_date,
             entry_reason, entry_signal_id, quantity, strategy, timeframe,
             stop_loss, take_profit, entry_date_precision, created_at)
            VALUES (?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol.upper(), name_ar, direction, entry_price, str(entry_date)[:10],
             entry_reason, entry_signal_id, quantity, strategy, timeframe,
             stop_loss, take_profit, entry_date_precision, now))
        trade_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    logger.info("Opened trade #%d: %s @ %s", trade_id, symbol, entry_price)
    return trade_id


def close_trade(trade_id, exit_price, exit_reason="manual"):
    """Close a trade. Calculates P&L. Returns updated trade dict."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = date.today().isoformat()
    with _conn() as c:
        row = c.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
        if not row:
            return None
        trade = dict(row)
        if trade["status"] != "open":
            return None

        entry = trade["entry_price"]
        qty = trade["quantity"] or 0
        direction = trade["direction"]

        if direction == "long":
            pnl_fils = (exit_price - entry) * qty if qty else (exit_price - entry)
            pnl_pct = ((exit_price - entry) / entry * 100) if entry else 0
        else:
            pnl_fils = (entry - exit_price) * qty if qty else (entry - exit_price)
            pnl_pct = ((entry - exit_price) / entry * 100) if entry else 0

        c.execute("""UPDATE trades SET
            status='closed', exit_price=?, exit_date=?, exit_reason=?,
            pnl_fils=?, pnl_pct=?, updated_at=?
            WHERE id=?""",
            (exit_price, today, exit_reason, round(pnl_fils, 2),
             round(pnl_pct, 2), now, trade_id))

        trade.update({
            "status": "closed", "exit_price": exit_price, "exit_date": today,
            "exit_reason": exit_reason, "pnl_fils": round(pnl_fils, 2),
            "pnl_pct": round(pnl_pct, 2), "updated_at": now,
        })
    logger.info("Closed trade #%d: %s @ %s → %s (%.2f%%)",
                trade_id, trade["symbol"], entry, exit_price, pnl_pct)
    return trade


def cancel_trade(trade_id):
    """Cancel a trade (never executed)."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        row = c.execute("SELECT * FROM trades WHERE id=? AND status='open'", (trade_id,)).fetchone()
        if not row:
            return None
        c.execute("UPDATE trades SET status='cancelled', updated_at=? WHERE id=?", (now, trade_id))
    return True


def get_open_trades():
    """Get all open trades. Returns list of dicts."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM trades WHERE status='open' ORDER BY entry_date DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_trades(limit=20):
    """Get recent trades (all statuses). Returns list of dicts."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_trade(trade_id):
    """Get single trade by ID."""
    with _conn() as c:
        row = c.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
    return dict(row) if row else None


def update_trade_notes(trade_id, notes):
    """Add/update notes on a trade."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        c.execute("UPDATE trades SET notes=?, updated_at=? WHERE id=?",
                  (notes, now, trade_id))
    return True


def update_trade_levels(trade_id, stop_loss=None, take_profit=None):
    """Update stop loss and/or take profit on an open trade."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        row = c.execute("SELECT id, status FROM trades WHERE id=?", (trade_id,)).fetchone()
        if not row or row["status"] != "open":
            return None
        updates = []
        params = []
        if stop_loss is not None:
            updates.append("stop_loss=?")
            params.append(stop_loss)
        if take_profit is not None:
            updates.append("take_profit=?")
            params.append(take_profit)
        if not updates:
            return None
        updates.append("updated_at=?")
        params.append(now)
        params.append(trade_id)
        c.execute(f"UPDATE trades SET {','.join(updates)} WHERE id=?", params)
    logger.info("Updated trade #%d levels: SL=%s TP=%s", trade_id, stop_loss, take_profit)
    return True


def get_fresh_price(symbol):
    """Freshest dated price via price_source (bridge -> yahoo -> db).

    Contract kept for the four consumers: price / source / stale. state and
    as_of ride along so nobody has to guess what stale means. Gone with the
    old body: a private bridge probe with its own 5s timeout on a dead host
    outside the circuit breaker, and a rowid-DESC read of the frozen
    stock_radar_daily that surfaced April prices as the "fresh" answer.
    """
    from price_source import get_price
    q = get_price(symbol)
    out = {"price": q.get("price"), "source": q.get("source"),
           "stale": q.get("state") != "live",
           "state": q.get("state"), "as_of": q.get("as_of")}
    for k in ("age_days", "captured_mid_session",
              "db_deviation_flag", "db_deviation_pct", "reason"):
        if k in q:
            out[k] = q[k]
    return out


def get_trade_stats(days=30):
    """Get trading statistics for the last N days."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    with _conn() as c:
        all_trades = c.execute(
            "SELECT * FROM trades WHERE entry_date >= ?", (cutoff,)
        ).fetchall()

    trades = [dict(r) for r in all_trades]
    closed = [t for t in trades if t["status"] == "closed"]
    open_t = [t for t in trades if t["status"] == "open"]
    wins = [t for t in closed if (t["pnl_pct"] or 0) > 0]
    losses = [t for t in closed if (t["pnl_pct"] or 0) <= 0]

    total_pnl = sum(t.get("pnl_fils", 0) or 0 for t in closed)
    avg_profit = (sum(t["pnl_pct"] for t in wins) / len(wins)) if wins else 0
    avg_loss = (sum(t["pnl_pct"] for t in losses) / len(losses)) if losses else 0

    best = max(closed, key=lambda t: t.get("pnl_pct", 0)) if closed else None
    worst = min(closed, key=lambda t: t.get("pnl_pct", 0)) if closed else None

    return {
        "days": days,
        "total_trades": len(trades),
        "open_trades": len(open_t),
        "closed_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(closed)) if closed else 0,
        "avg_profit_pct": round(avg_profit, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "total_pnl_fils": round(total_pnl, 2),
        "best_trade": {"symbol": best["symbol"], "pnl_pct": best["pnl_pct"]} if best else None,
        "worst_trade": {"symbol": worst["symbol"], "pnl_pct": worst["pnl_pct"]} if worst else None,
    }


# ═══════════════════════════════════════════════════
# WEEKLY PERFORMANCE REPORT
# ═══════════════════════════════════════════════════



# ═══════════════════════════════════════════════════
# Partial Sell + Add More
# ═══════════════════════════════════════════════════

BROKER_FEE_PCT = 0.125  # 0.125% each way


def partial_sell_trade(trade_id, sell_qty, sell_price, notes=""):
    """
    Sell part of a position.
    - If sell_qty == remaining qty → fully closes the trade
    - Otherwise updates quantity, logs transaction, calculates realized P&L
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = date.today().isoformat()
    with _conn() as c:
        row = c.execute("SELECT * FROM trades WHERE id=? AND status='open'", (trade_id,)).fetchone()
        if not row:
            return {"error": f"Trade {trade_id} not found or not open"}
        trade = dict(row)

        old_qty = int(trade["quantity"] or 0)
        if old_qty <= 0:
            return {"error": "Trade has no quantity to sell"}
        if sell_qty <= 0 or sell_qty > old_qty:
            return {"error": f"Invalid sell_qty={sell_qty}, current={old_qty}"}

        entry = float(trade["entry_price"])
        direction = trade.get("direction", "long")

        # P&L for sold portion
        if direction == "long":
            pnl_fils = round((sell_price - entry) * sell_qty, 2)
            pnl_pct = round((sell_price - entry) / entry * 100, 2) if entry else 0
        else:
            pnl_fils = round((entry - sell_price) * sell_qty, 2)
            pnl_pct = round((entry - sell_price) / entry * 100, 2) if entry else 0

        fees = round(sell_price * sell_qty * BROKER_FEE_PCT / 100, 3)
        pnl_net = round(pnl_fils - fees, 2)
        new_qty = old_qty - sell_qty

        if new_qty == 0:
            # Full close
            c.execute("""UPDATE trades SET
                status='closed', exit_price=?, exit_date=?, exit_reason=?,
                pnl_fils=?, pnl_pct=?, quantity=0, updated_at=?
                WHERE id=?""",
                (sell_price, today, "partial_sell_complete",
                 pnl_net, pnl_pct, now, trade_id))
        else:
            # Partial — keep open with reduced qty
            c.execute("""UPDATE trades SET
                quantity=?, updated_at=?, notes=COALESCE(notes,'') || ?
                WHERE id=?""",
                (new_qty, now,
                 f"\nPartial sell: {sell_qty}@{sell_price} on {today} (PnL: {pnl_net})",
                 trade_id))

        # Log transaction
        c.execute("""INSERT INTO trade_transactions
            (trade_id, tx_type, quantity, price, pnl_fils, pnl_pct, fees,
             avg_price_after, qty_after, notes, created_at)
            VALUES (?, 'partial_sell', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (trade_id, sell_qty, sell_price, pnl_net, pnl_pct, fees,
             entry, new_qty, notes or f"Sold {sell_qty}@{sell_price}", now))

    status = "closed" if new_qty == 0 else "open"
    logger.info("Partial sell #%d: %s %d@%s → remaining %d (PnL: %s)",
                trade_id, trade["symbol"], sell_qty, sell_price, new_qty, pnl_net)
    return {
        "success": True,
        "trade_id": trade_id,
        "symbol": trade["symbol"],
        "sold_qty": sell_qty,
        "sell_price": sell_price,
        "remaining_qty": new_qty,
        "realized_pnl": pnl_net,
        "realized_pnl_pct": pnl_pct,
        "fees": fees,
        "status": status,
        "entry_price": entry,
    }


def add_more_trade(trade_id, add_qty, add_price, notes=""):
    """
    Add more shares to an existing position.
    Recalculates weighted average entry price.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        row = c.execute("SELECT * FROM trades WHERE id=? AND status='open'", (trade_id,)).fetchone()
        if not row:
            return {"error": f"Trade {trade_id} not found or not open"}
        trade = dict(row)

        old_qty = int(trade["quantity"] or 0)
        old_price = float(trade["entry_price"])

        if add_qty <= 0 or add_price <= 0:
            return {"error": "add_qty and add_price must be > 0"}

        # Weighted average
        new_qty = old_qty + add_qty
        new_avg = round((old_qty * old_price + add_qty * add_price) / new_qty, 3)

        fees = round(add_price * add_qty * BROKER_FEE_PCT / 100, 3)

        c.execute("""UPDATE trades SET
            entry_price=?, quantity=?, updated_at=?,
            notes=COALESCE(notes,'') || ?
            WHERE id=?""",
            (new_avg, new_qty, now,
             f"\nAdded {add_qty}@{add_price} on {now[:10]} (avg: {new_avg})",
             trade_id))

        # Log transaction
        c.execute("""INSERT INTO trade_transactions
            (trade_id, tx_type, quantity, price, fees,
             avg_price_after, qty_after, notes, created_at)
            VALUES (?, 'add_more', ?, ?, ?, ?, ?, ?, ?)""",
            (trade_id, add_qty, add_price, fees,
             new_avg, new_qty, notes or f"Added {add_qty}@{add_price}", now))

    logger.info("Add more #%d: %s +%d@%s → total %d @ avg %s",
                trade_id, trade["symbol"], add_qty, add_price, new_qty, new_avg)
    return {
        "success": True,
        "trade_id": trade_id,
        "symbol": trade["symbol"],
        "added_qty": add_qty,
        "add_price": add_price,
        "new_qty": new_qty,
        "old_avg_price": old_price,
        "new_avg_price": new_avg,
        "fees": fees,
    }


def get_trade_transactions(trade_id):
    """Get all transactions for a trade."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM trade_transactions WHERE trade_id=? ORDER BY created_at ASC",
            (trade_id,)).fetchall()
        return [dict(r) for r in rows]

def generate_weekly_report():
    """Generate weekly trading performance report.
    Covers last 7 days of trading activity + radar signal stats.
    Returns dict suitable for Telegram message or dashboard.
    """
    stats_7d = get_trade_stats(days=7)

    # Closed trades this week with KWD P&L
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM trades WHERE exit_date >= ? AND status='closed' ORDER BY exit_date DESC",
            (cutoff,)
        ).fetchall()
    closed_this_week = [dict(r) for r in rows]

    # Calculate KWD totals
    total_net_kwd = 0
    trades_detail = []
    for t in closed_this_week:
        entry = float(t.get("entry_price", 0))
        exit_p = float(t.get("exit_price", 0))
        qty = int(t.get("quantity", 0))
        if entry and exit_p and qty:
            pnl = calculate_real_pnl(entry, exit_p, qty)
            total_net_kwd += pnl["net_pnl_kwd"]
            trades_detail.append({
                "symbol": t["symbol"],
                "name_ar": t.get("name_ar", t["symbol"]),
                "net_pnl_kwd": pnl["net_pnl_kwd"],
                "pnl_pct": pnl["pnl_pct"],
            })

    # Radar signal stats (from stock_radar_events)
    signal_stats = {"total": 0, "bullish": 0, "bearish": 0}
    try:
        import sqlite3 as _sq3
        _conn2 = _sq3.connect(DB_PATH, timeout=5)
        _conn2.row_factory = _sq3.Row
        cutoff_dt = (datetime.utcnow().date() - timedelta(days=7)).isoformat()  # events are stamped UTC
        sig_rows = _conn2.execute(
            "SELECT signal_type, COUNT(*) as cnt FROM stock_radar_events "
            "WHERE created_at >= ? GROUP BY signal_type", (cutoff_dt,)
        ).fetchall()
        for r in sig_rows:
            cnt = r["cnt"]
            signal_stats["total"] += cnt
            if "bullish" in r["signal_type"]:
                signal_stats["bullish"] += cnt
            elif "bearish" in r["signal_type"]:
                signal_stats["bearish"] += cnt

        # Top stocks by score this week
        top_stocks = _conn2.execute("""
            SELECT symbol, MAX(score) as max_score, COUNT(*) as signals
            FROM stock_radar_events WHERE created_at >= ? AND score > 0
            GROUP BY symbol ORDER BY max_score DESC LIMIT 5
        """, (cutoff_dt,)).fetchall()
        signal_stats["top_stocks"] = [{"symbol": r["symbol"], "max_score": r["max_score"],
                                        "signals": r["signals"]} for r in top_stocks]
        _conn2.close()
    except Exception:
        signal_stats["top_stocks"] = []

    # Date range
    end_date = date.today()
    start_date = end_date - timedelta(days=6)

    return {
        "period": f"{start_date.isoformat()} — {end_date.isoformat()}",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "stats": stats_7d,
        "total_net_kwd": round(total_net_kwd, 3),
        "trades_detail": trades_detail,
        "signal_stats": signal_stats,
        "confirmed_from_signals": stats_7d.get("total_trades", 0),
    }


def format_weekly_report_tg(report):
    """Format weekly report for Telegram message."""
    s = report["stats"]
    ss = report["signal_stats"]
    lines = [
        f"\U0001f4ca \u062a\u0642\u0631\u064a\u0631 \u0627\u0644\u062a\u062f\u0627\u0648\u0644 \u0627\u0644\u0623\u0633\u0628\u0648\u0639\u064a \u2014 {report['period']}",
        "",
        "\U0001f4c8 \u0627\u0644\u0623\u062f\u0627\u0621:",
        f"  \u0635\u0641\u0642\u0627\u062a: {s.get('closed_trades', 0)} ({s.get('wins', 0)} \u0641\u0648\u0632, {s.get('losses', 0)} \u062e\u0633\u0627\u0631\u0629) \u2014 {round(s.get('win_rate', 0) * 100)}% win rate",
        f"  \u0627\u0644\u0631\u0628\u062d \u0627\u0644\u0635\u0627\u0641\u064a: {'+' if report['total_net_kwd'] >= 0 else ''}{report['total_net_kwd']} \u062f.\u0643",
    ]
    # Best/worst
    if s.get("best_trade"):
        lines.append(f"  \u0623\u0641\u0636\u0644 \u0635\u0641\u0642\u0629: {s['best_trade']['symbol']} {'+' if s['best_trade']['pnl_pct'] >= 0 else ''}{s['best_trade']['pnl_pct']}%")
    if s.get("worst_trade"):
        lines.append(f"  \u0623\u0633\u0648\u0623 \u0635\u0641\u0642\u0629: {s['worst_trade']['symbol']} {s['worst_trade']['pnl_pct']}%")
    lines.append("")
    lines.append("\U0001f4e1 \u0627\u0644\u0631\u0627\u062f\u0627\u0631:")
    lines.append(f"  \u0625\u0634\u0627\u0631\u0627\u062a: {ss['total']} ({ss['bullish']} \u0635\u0627\u0639\u062f, {ss['bearish']} \u0647\u0627\u0628\u0637)")
    if ss.get("top_stocks"):
        lines.append("")
        lines.append("\U0001f3c6 \u0623\u0641\u0636\u0644 \u0623\u0633\u0647\u0645 \u0627\u0644\u0623\u0633\u0628\u0648\u0639:")
        for i, ts in enumerate(ss["top_stocks"][:3], 1):
            lines.append(f"  {i}. {ts['symbol']} \u2014 Score {ts['max_score']}, {ts['signals']} \u0625\u0634\u0627\u0631\u0629")
    # Market sentiment
    if ss["total"] > 0:
        bull_pct = round(ss["bullish"] / ss["total"] * 100)
        lines.append("")
        lines.append(f"\U0001f4ca \u0627\u0644\u0633\u0648\u0642 \u0628\u0634\u0643\u0644 \u0639\u0627\u0645: {'صاعد' if bull_pct > 55 else 'هابط' if bull_pct < 45 else 'محايد'} ({bull_pct}% \u0625\u0634\u0627\u0631\u0627\u062a \u0635\u0627\u0639\u062f\u0629)")
    return chr(10).join(lines)
