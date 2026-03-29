"""
position_engine.py — Position Monitoring & Alert Engine
Phase 2 of Master Plan V10

Monitors open positions daily and sends Telegram alerts for:
- Stop loss hit
- Target 1 / Target 2 hit
- Gap below stop (price dropped >3% below stop)
- Stale position (no movement for 7+ days)
- Automatic breakeven stop when target 1 is hit
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger("position_engine")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")


# ═══════════════════════════════════════════════════
# DB HELPERS
# ═══════════════════════════════════════════════════

def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_position_schema():
    """Create position_alerts table + migrate journal_trades columns."""
    with _conn() as c:
        # New table: position_alerts
        c.executescript("""
            CREATE TABLE IF NOT EXISTS position_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                alert_data TEXT,
                sent_via TEXT DEFAULT 'telegram',
                sent_at DATETIME,
                acknowledged BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_pa_trade ON position_alerts(trade_id);
            CREATE INDEX IF NOT EXISTS idx_pa_symbol ON position_alerts(symbol);
            CREATE INDEX IF NOT EXISTS idx_pa_type ON position_alerts(alert_type);
        """)

        # Migrate trades table — add new columns if missing
        cols = [r[1] for r in c.execute("PRAGMA table_info(trades)").fetchall()]
        migrations = {
            "target_1":          "REAL",
            "target_2":          "REAL",
            "target_1_hit":      "BOOLEAN DEFAULT 0",
            "target_2_hit":      "BOOLEAN DEFAULT 0",
            "target_1_hit_date": "DATE",
            "target_2_hit_date": "DATE",
            "stop_hit":          "BOOLEAN DEFAULT 0",
            "stop_hit_date":     "DATE",
            "trailing_stop":     "REAL",
            "original_stop":     "REAL",
            "strategy_tag":      "TEXT",
            "sector":            "TEXT",
            "data_quality_at_entry": "INTEGER",
            "last_monitored":    "DATETIME",
        }
        for col, col_type in migrations.items():
            if col not in cols:
                try:
                    c.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_type}")
                    logger.info("Added column trades.%s", col)
                except Exception as e:
                    logger.debug("Column %s may already exist: %s", col, e)

    logger.info("position_engine schema initialized")


# ═══════════════════════════════════════════════════
# PRICE FETCHING
# ═══════════════════════════════════════════════════

def _get_latest_price(symbol: str) -> dict:
    """Get latest price with source info. Returns {"price": float|None, "source": str}."""
    from journal_engine import get_fresh_price
    return get_fresh_price(symbol)


# ═══════════════════════════════════════════════════
# ALERT PERSISTENCE
# ═══════════════════════════════════════════════════

def _save_alert(trade_id: int, symbol: str, alert: dict):
    """Save alert to position_alerts table."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        c.execute(
            """INSERT INTO position_alerts
               (trade_id, symbol, alert_type, alert_data, sent_via, sent_at)
               VALUES (?, ?, ?, ?, 'telegram', ?)""",
            (trade_id, symbol, alert["type"], json.dumps(alert, ensure_ascii=False), now),
        )


def _was_alert_sent_today(trade_id: int, alert_type: str) -> bool:
    """Check if this alert type was already sent today for this trade."""
    today = date.today().isoformat()
    with _conn() as c:
        row = c.execute(
            """SELECT COUNT(*) as cnt FROM position_alerts
               WHERE trade_id=? AND alert_type=? AND DATE(sent_at)=?""",
            (trade_id, alert_type, today),
        ).fetchone()
    return (row["cnt"] or 0) > 0


def _mark_target_hit(trade_id: int, target: int):
    """Mark target 1 or 2 as hit."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    col_hit = f"target_{target}_hit"
    col_date = f"target_{target}_hit_date"
    with _conn() as c:
        c.execute(
            f"UPDATE trades SET {col_hit}=1, {col_date}=?, updated_at=? WHERE id=?",
            (date.today().isoformat(), now, trade_id),
        )


def _mark_stop_hit(trade_id: int):
    """Mark stop as hit."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        c.execute(
            "UPDATE trades SET stop_hit=1, stop_hit_date=?, updated_at=? WHERE id=?",
            (date.today().isoformat(), now, trade_id),
        )


def _update_trailing_stop(trade_id: int, new_stop: float):
    """Update trailing stop level."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        c.execute(
            "UPDATE trades SET trailing_stop=?, updated_at=? WHERE id=?",
            (round(new_stop, 3), now, trade_id),
        )


def _mark_monitored(trade_id: int):
    """Update last_monitored timestamp."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        c.execute(
            "UPDATE trades SET last_monitored=? WHERE id=?", (now, trade_id)
        )


def _update_position_pnl(trade_id: int, current_price: float):
    """Update the current P&L fields (using pnl_fils/pnl_pct on open trades)."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        row = c.execute(
            "SELECT entry_price, quantity, direction FROM trades WHERE id=?",
            (trade_id,),
        ).fetchone()
        if not row:
            return
        entry = float(row["entry_price"] or 0)
        qty = int(row["quantity"] or 0)
        direction = row["direction"] or "long"
        if entry <= 0:
            return
        if direction == "long":
            pnl_pct = ((current_price - entry) / entry) * 100
            pnl_fils = (current_price - entry) * qty if qty else (current_price - entry)
        else:
            pnl_pct = ((entry - current_price) / entry) * 100
            pnl_fils = (entry - current_price) * qty if qty else (entry - current_price)
        c.execute(
            "UPDATE trades SET pnl_fils=?, pnl_pct=?, updated_at=? WHERE id=?",
            (round(pnl_fils, 2), round(pnl_pct, 2), now, trade_id),
        )


# ═══════════════════════════════════════════════════
# TELEGRAM ALERTS
# ═══════════════════════════════════════════════════

def _read_file(path: str) -> str:
    """Read single-line file content."""
    expanded = os.path.expanduser(path)
    try:
        with open(expanded, "r") as f:
            return f.read().strip()
    except Exception:
        return ""


def send_position_alert(alert: dict) -> bool:
    """Send a position alert via Telegram."""
    import requests as _req

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN") or _read_file("~/.telegram_bot_token")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or _read_file("~/.telegram_chat_id")
    if not bot_token or not chat_id:
        logger.warning("Telegram credentials not configured — skipping alert")
        return False

    urgency_emoji = {
        "critical": "\U0001f6a8",
        "high": "\U0001f3af",
        "low": "\u23f0",
        "info": "\u2139\ufe0f",
    }
    emoji = urgency_emoji.get(alert.get("urgency", ""), "\U0001f4ca")

    msg = f"{emoji} <b>تنبيه مراكز</b>\n\n"
    msg += alert.get("msg_ar", "") + "\n"
    if alert.get("action_ar"):
        msg += f"\n\u2705 <b>الإجراء:</b> {alert['action_ar']}"

    try:
        r = _req.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        logger.warning("Position alert Telegram send failed: %s", e)
        return False


# ═══════════════════════════════════════════════════
# POSITION ENGINE — MAIN CLASS
# ═══════════════════════════════════════════════════

class PositionEngine:
    """
    Monitors open positions and generates alerts.
    Run daily after market close (2 PM Kuwait) or on-demand.
    """

    def daily_monitor(self) -> dict:
        """
        Full daily scan of all open positions.
        Returns summary dict with alerts generated.
        """
        from journal_engine import get_open_trades

        open_trades = get_open_trades()
        today_date = date.today()
        all_alerts = []
        positions_checked = 0
        errors = 0

        for trade in open_trades:
            trade_id = trade["id"]
            sym = trade.get("symbol", "").upper()
            if not sym:
                continue

            try:
                price_info = _get_latest_price(sym)
                price = price_info.get("price")
                if not price:
                    logger.debug("No price for %s — skipping", sym)
                    continue

                price = float(price)
                entry_price = float(trade.get("entry_price", 0) or 0)
                if entry_price <= 0:
                    continue

                # Effective stop: trailing_stop > stop_loss > None
                stop = float(trade.get("trailing_stop") or trade.get("stop_loss") or 0)

                # Target levels
                t1 = float(trade.get("target_1") or trade.get("take_profit") or 0)
                t2 = float(trade.get("target_2") or 0)
                t1_hit = bool(trade.get("target_1_hit"))
                t2_hit = bool(trade.get("target_2_hit"))

                alerts = []

                # ── 1. Stop hit ──────────────────────────────
                if stop > 0 and price <= stop and not trade.get("stop_hit"):
                    if not _was_alert_sent_today(trade_id, "stop_hit"):
                        alerts.append({
                            "type": "stop_hit",
                            "msg_ar": f"\u26d4 {sym} ضرب الستوب! السعر {price} \u2264 الستوب {stop}",
                            "action_ar": "بيع فوراً",
                            "urgency": "critical",
                        })
                        _mark_stop_hit(trade_id)

                # ── 2. Gap below stop (>3% below) ────────────
                if stop > 0 and price < stop * 0.97 and not trade.get("stop_hit"):
                    if not _was_alert_sent_today(trade_id, "gap_below_stop"):
                        alerts.append({
                            "type": "gap_below_stop",
                            "msg_ar": f"\U0001f534 {sym} قفز تحت الستوب! السعر {price} بعيد عن الستوب {stop}",
                            "action_ar": "راجع المركز فوراً — gap down",
                            "urgency": "critical",
                        })
                        _mark_stop_hit(trade_id)

                # ── 3. Target 1 hit ──────────────────────────
                if t1 > 0 and not t1_hit and price >= t1:
                    if not _was_alert_sent_today(trade_id, "target_1_hit"):
                        alerts.append({
                            "type": "target_1_hit",
                            "msg_ar": f"\U0001f3af {sym} وصل الهدف الأول! السعر {price} \u2265 الهدف {t1}",
                            "action_ar": "بيع نص أو رفع الستوب لسعر الدخول",
                            "urgency": "high",
                        })
                        _mark_target_hit(trade_id, target=1)

                        # Auto-breakeven: raise stop to entry price
                        trailing = float(trade.get("trailing_stop") or 0)
                        if trailing < entry_price:
                            _update_trailing_stop(trade_id, entry_price)
                            alerts.append({
                                "type": "breakeven_set",
                                "msg_ar": f"\U0001f512 {sym} الستوب ارتفع لسعر الدخول {entry_price}",
                                "urgency": "info",
                            })

                # ── 4. Target 2 hit ──────────────────────────
                if t2 > 0 and not t2_hit and price >= t2:
                    if not _was_alert_sent_today(trade_id, "target_2_hit"):
                        alerts.append({
                            "type": "target_2_hit",
                            "msg_ar": f"\U0001f3c6 {sym} وصل الهدف الثاني! السعر {price} \u2265 الهدف {t2}",
                            "action_ar": "بيع الباقي أو trailing stop",
                            "urgency": "high",
                        })
                        _mark_target_hit(trade_id, target=2)

                # ── 5. Stale position (7+ days, <2% move) ───
                entry_date_str = trade.get("entry_date", "")
                if entry_date_str:
                    try:
                        entry_dt = datetime.strptime(entry_date_str[:10], "%Y-%m-%d").date()
                        days_held = (today_date - entry_dt).days
                        move_pct = abs(price - entry_price) / entry_price if entry_price > 0 else 0
                        if days_held >= 7 and move_pct < 0.02:
                            if not _was_alert_sent_today(trade_id, "stale_position"):
                                alerts.append({
                                    "type": "stale_position",
                                    "msg_ar": f"\u23f0 {sym} ما تحرّك {days_held} يوم — راجع المركز",
                                    "urgency": "low",
                                })
                    except (ValueError, TypeError):
                        pass

                # ── Send & save alerts ────────────────────────
                for alert in alerts:
                    _save_alert(trade_id, sym, alert)
                    send_position_alert(alert)
                    all_alerts.append({"symbol": sym, **alert})

                # Update P&L and last_monitored
                _update_position_pnl(trade_id, price)
                _mark_monitored(trade_id)
                positions_checked += 1

            except Exception as e:
                logger.error("Error monitoring %s: %s", sym, e, exc_info=True)
                errors += 1

        summary = {
            "monitored_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "positions_checked": positions_checked,
            "total_open": len(open_trades),
            "alerts_generated": len(all_alerts),
            "errors": errors,
            "alerts": all_alerts,
        }

        logger.info(
            "daily_monitor: checked %d positions, %d alerts, %d errors",
            positions_checked, len(all_alerts), errors,
        )
        return summary

    def get_portfolio_summary(self) -> dict:
        """Portfolio summary for dashboard — positions + P&L + alerts."""
        from journal_engine import get_open_trades, calculate_real_pnl

        trades = get_open_trades()
        positions = []
        total_invested = 0
        total_current = 0
        today_date = date.today()

        for t in trades:
            sym = t.get("symbol", "").upper()
            entry = float(t.get("entry_price", 0) or 0)
            qty = int(t.get("quantity", 0) or 0)
            if entry <= 0:
                continue

            price_info = _get_latest_price(sym)
            current = float(price_info.get("price") or 0) if price_info.get("price") else None
            price_source = price_info.get("source", "none")
            price_stale = price_info.get("stale", True)

            # Days held
            days_held = 0
            entry_date_str = t.get("entry_date", "")
            if entry_date_str:
                try:
                    entry_dt = datetime.strptime(entry_date_str[:10], "%Y-%m-%d").date()
                    days_held = (today_date - entry_dt).days
                except (ValueError, TypeError):
                    pass

            # P&L
            pnl_pct = 0
            pnl_kwd = 0
            if current and current > 0 and entry > 0:
                if qty > 0:
                    pnl_data = calculate_real_pnl(entry, current, qty)
                    pnl_pct = pnl_data["pnl_pct"]
                    pnl_kwd = pnl_data["net_pnl_kwd"]
                else:
                    pnl_pct = ((current - entry) / entry) * 100

                total_invested += entry * qty if qty else entry
                total_current += current * qty if qty else current

            # Effective stop
            stop = float(t.get("trailing_stop") or t.get("stop_loss") or 0)
            t1 = float(t.get("target_1") or t.get("take_profit") or 0)
            t2 = float(t.get("target_2") or 0)

            positions.append({
                "id": t["id"],
                "symbol": sym,
                "name_ar": t.get("name_ar", ""),
                "entry": entry,
                "current": current,
                "price_source": price_source,
                "price_stale": price_stale,
                "quantity": qty,
                "pnl_pct": round(pnl_pct, 2),
                "pnl_kwd": round(pnl_kwd, 3),
                "stop": stop if stop > 0 else None,
                "trailing_stop": float(t.get("trailing_stop") or 0) or None,
                "original_stop": float(t.get("original_stop") or t.get("stop_loss") or 0) or None,
                "target_1": t1 if t1 > 0 else None,
                "target_1_hit": bool(t.get("target_1_hit")),
                "target_2": t2 if t2 > 0 else None,
                "target_2_hit": bool(t.get("target_2_hit")),
                "stop_hit": bool(t.get("stop_hit")),
                "days_held": days_held,
                "sector": t.get("sector", ""),
                "strategy": t.get("strategy", ""),
                "strategy_tag": t.get("strategy_tag", ""),
                "last_monitored": t.get("last_monitored"),
            })

        # Sort: biggest P&L first
        positions.sort(key=lambda p: p["pnl_pct"], reverse=True)

        total_pnl = total_current - total_invested if total_invested > 0 else 0
        total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0

        return {
            "total_positions": len(positions),
            "total_invested_kwd": round(total_invested / 1000, 3),
            "total_current_kwd": round(total_current / 1000, 3),
            "total_pnl_kwd": round(total_pnl / 1000, 3),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "positions": positions,
        }

    def get_active_alerts(self, days: int = 7) -> list:
        """Get recent unacknowledged alerts."""
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        with _conn() as c:
            rows = c.execute(
                """SELECT * FROM position_alerts
                   WHERE acknowledged=0 AND DATE(created_at) >= ?
                   ORDER BY created_at DESC LIMIT 50""",
                (cutoff,),
            ).fetchall()
        return [dict(r) for r in rows]

    def acknowledge_alert(self, alert_id: int) -> bool:
        """Mark an alert as acknowledged."""
        with _conn() as c:
            c.execute(
                "UPDATE position_alerts SET acknowledged=1 WHERE id=?",
                (alert_id,),
            )
        return True

    def get_last_monitor_time(self) -> str:
        """Get the most recent last_monitored time across all positions."""
        with _conn() as c:
            row = c.execute(
                "SELECT MAX(last_monitored) as lm FROM trades WHERE status='open'"
            ).fetchone()
        return row["lm"] if row and row["lm"] else ""


# ═══════════════════════════════════════════════════
# CONVENIENCE — standalone run
# ═══════════════════════════════════════════════════

def run_daily_monitor() -> dict:
    """Convenience function to run daily monitor."""
    init_position_schema()
    engine = PositionEngine()
    return engine.daily_monitor()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    init_position_schema()
    engine = PositionEngine()
    result = engine.daily_monitor()
    print(json.dumps(result, ensure_ascii=False, indent=2))
