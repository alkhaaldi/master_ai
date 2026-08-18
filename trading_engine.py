"""
trading_engine.py - Trading Journal Lite (Phase 5)
Tables in life.db: trade_journal
TG commands: /trade, /trades, /trade_review
LLM tools: trade_log_entry, trade_get_journal
Quick query: "صفقاتي" / "آخر صفقة"
"""

import os
import sqlite3
import json
import logging
import re
from datetime import datetime, date, timedelta

logger = logging.getLogger("trading_engine")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trade_journal (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT NOT NULL,
    action      TEXT NOT NULL,       -- buy | sell | close
    shares      INTEGER,
    price       REAL,
    strategy    TEXT,                -- CLEANING_V3 | SENERGY_V5 | INOVEST_V5 | manual
    reason      TEXT,                -- entry/exit reason
    emotion     TEXT,                -- calm | fomo | fear | greedy | disciplined
    outcome     TEXT,                -- win | loss | breakeven (set on close/sell)
    pnl         REAL,               -- profit/loss amount (set on close/sell)
    review      TEXT,                -- post-trade review notes
    trade_date  DATE NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_trade_ticker_date ON trade_journal(ticker, trade_date);
CREATE INDEX IF NOT EXISTS idx_trade_action ON trade_journal(action, trade_date);
"""

# ── DB ────────────────────────────────────────────────────
def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c

def init_schema():
    db = _conn()
    db.executescript(_SCHEMA)
    db.commit()
    db.close()
    logger.info("trading_engine: schema ready")

# ── CRUD ──────────────────────────────────────────────────
def log_trade(ticker, action, shares=None, price=None, strategy=None,
              reason=None, emotion=None, outcome=None, pnl=None,
              review=None, trade_date=None):
    """Log a trade entry (buy/sell/close)."""
    ticker = ticker.upper().strip()
    action = action.lower().strip()
    if action not in ("buy", "sell", "close"):
        return "\u26a0\ufe0f action \u0644\u0627\u0632\u0645 buy \u0623\u0648 sell \u0623\u0648 close"
    if trade_date is None:
        trade_date = date.today().isoformat()

    db = _conn()
    db.execute(
        "INSERT INTO trade_journal (ticker,action,shares,price,strategy,reason,emotion,outcome,pnl,review,trade_date) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (ticker, action, shares, price, strategy, reason, emotion, outcome, pnl, review, trade_date)
    )
    db.commit()
    db.close()

    emoji = {"buy": "\U0001f7e2", "sell": "\U0001f534", "close": "\u2b1c"}.get(action, "\u2705")
    price_str = f" @ {price}" if price else ""
    shares_str = f" x{shares}" if shares else ""
    strat_str = f" [{strategy}]" if strategy else ""
    return f"{emoji} {action.upper()} {ticker}{shares_str}{price_str}{strat_str}"


def get_trades(days=30, ticker=None, limit=20):
    """Get recent trades."""
    since = (date.today() - timedelta(days=days)).isoformat()
    db = _conn()
    q = "SELECT * FROM trade_journal WHERE trade_date >= ?"
    params = [since]
    if ticker:
        q += " AND ticker = ?"
        params.append(ticker.upper())
    q += " ORDER BY trade_date DESC, created_at DESC LIMIT ?"
    params.append(limit)
    rows = db.execute(q, params).fetchall()
    db.close()
    return [dict(r) for r in rows]


def add_review(trade_id, review_text, outcome=None, pnl=None):
    """Add post-trade review to an existing trade."""
    db = _conn()
    row = db.execute("SELECT * FROM trade_journal WHERE id=?", (trade_id,)).fetchone()
    if not row:
        db.close()
        return "\u26a0\ufe0f \u0645\u0627 \u0644\u0642\u064a\u062a \u0627\u0644\u0635\u0641\u0642\u0629"

    updates = ["review = ?"]
    params = [review_text]
    if outcome:
        updates.append("outcome = ?")
        params.append(outcome)
    if pnl is not None:
        updates.append("pnl = ?")
        params.append(pnl)
    params.append(trade_id)

    db.execute(f"UPDATE trade_journal SET {', '.join(updates)} WHERE id = ?", params)
    db.commit()
    db.close()
    return f"\u2705 \u062a\u0645 \u062a\u062d\u062f\u064a\u062b \u0645\u0631\u0627\u062c\u0639\u0629 \u0627\u0644\u0635\u0641\u0642\u0629 #{trade_id}"


def get_stats(days=30):
    """Trading stats for period."""
    since = (date.today() - timedelta(days=days)).isoformat()
    db = _conn()
    rows = db.execute(
        "SELECT * FROM trade_journal WHERE trade_date >= ?", (since,)
    ).fetchall()
    db.close()

    if not rows:
        return None

    total = len(rows)
    buys = sum(1 for r in rows if r["action"] == "buy")
    sells = sum(1 for r in rows if r["action"] in ("sell", "close"))
    wins = sum(1 for r in rows if r["outcome"] == "win")
    losses = sum(1 for r in rows if r["outcome"] == "loss")
    total_pnl = sum(r["pnl"] or 0 for r in rows)
    reviewed = sum(1 for r in rows if r["review"])

    return {
        "days": days, "total": total, "buys": buys, "sells": sells,
        "wins": wins, "losses": losses, "total_pnl": total_pnl,
        "win_rate": (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0,
        "reviewed": reviewed,
        "tickers": list(set(r["ticker"] for r in rows)),
        "emotions": _emotion_stats(rows)
    }


def _emotion_stats(rows):
    counts = {}
    for r in rows:
        if r["emotion"]:
            counts[r["emotion"]] = counts.get(r["emotion"], 0) + 1
    return counts


# ── Formatters ────────────────────────────────────────────
def format_trades_tg(trades):
    if not trades:
        return "\U0001f4c8 \u0644\u0627 \u0635\u0641\u0642\u0627\u062a \u0645\u0633\u062c\u0644\u0629"
    lines = [f"\U0001f4c8 \u0622\u062e\u0631 \u0627\u0644\u0635\u0641\u0642\u0627\u062a ({len(trades)})"]
    for t in trades[:10]:
        emoji = {"buy": "\U0001f7e2", "sell": "\U0001f534", "close": "\u2b1c"}.get(t["action"], "\u2705")
        price_str = f"@{t['price']}" if t.get("price") else ""
        outcome_str = ""
        if t.get("outcome"):
            oc = {
                "win": " \u2705",
                "loss": " \u274c",
                "breakeven": " \u27a1\ufe0f"
            }.get(t["outcome"], "")
            outcome_str = oc
        pnl_str = ""
        if t.get("pnl"):
            sign = "+" if t["pnl"] > 0 else ""
            pnl_str = f" ({sign}{t['pnl']:.1f})"
        review_flag = " \U0001f4dd" if t.get("review") else ""
        lines.append(
            f"  {emoji} {t['trade_date']} {t['ticker']} {t['action'].upper()} "
            f"{price_str}{outcome_str}{pnl_str}{review_flag}"
        )
    return chr(10).join(lines)


def format_stats_tg(stats):
    if not stats:
        return "\U0001f4ca \u0644\u0627 \u0625\u062d\u0635\u0627\u0626\u064a\u0627\u062a"
    lines = [
        f"\U0001f4ca \u0625\u062d\u0635\u0627\u0626\u064a\u0627\u062a \u0627\u0644\u062a\u062f\u0627\u0648\u0644 ({stats['days']} \u064a\u0648\u0645)",
        "",
        f"\U0001f4c8 \u0635\u0641\u0642\u0627\u062a: {stats['total']} (\U0001f7e2{stats['buys']} \u0634\u0631\u0627\u0621 / \U0001f534{stats['sells']} \u0628\u064a\u0639)",
        f"\U0001f3af \u0646\u062a\u064a\u062c\u0629: {stats['wins']}W / {stats['losses']}L ({stats['win_rate']:.0f}%)",
        f"\U0001f4b0 P&L: {'+' if stats['total_pnl'] >= 0 else ''}{stats['total_pnl']:.1f} KWD",
        f"\U0001f4dd \u0645\u0631\u0627\u062c\u0639: {stats['reviewed']}/{stats['total']}",
    ]
    if stats["emotions"]:
        emo_str = " | ".join(f"{k}:{v}" for k, v in stats["emotions"].items())
        lines.append(f"\U0001f9e0 \u0645\u0634\u0627\u0639\u0631: {emo_str}")
    if stats["tickers"]:
        lines.append(f"\U0001f4cc \u0623\u0633\u0647\u0645: {', '.join(stats['tickers'][:8])}")
    return chr(10).join(lines)


def format_review_prompt(trade):
    """Generate review prompt for a trade."""
    lines = [
        f"\U0001f50d \u0645\u0631\u0627\u062c\u0639\u0629 \u0635\u0641\u0642\u0629 #{trade['id']}:",
        f"  {trade['ticker']} {trade['action'].upper()} @{trade.get('price','-')}",
        f"  \u0627\u0644\u0627\u0633\u062a\u0631\u0627\u062a\u064a\u062c\u064a\u0629: {trade.get('strategy', '-')}",
        f"  \u0627\u0644\u0633\u0628\u0628: {trade.get('reason', '-')}",
        "",
        "\u0623\u062c\u0628 \u0639\u0644\u0649:",
        "1\ufe0f\u20e3 \u0627\u0644\u0646\u062a\u064a\u062c\u0629: win/loss/breakeven",
        "2\ufe0f\u20e3 P&L: \u0643\u0645 \u0631\u0628\u062d\u062a/\u062e\u0633\u0631\u062a\u061f",
        "3\ufe0f\u20e3 \u0627\u0644\u062f\u0631\u0633: \u0634\u0646\u0648 \u062a\u0639\u0644\u0645\u062a\u061f",
    ]
    return chr(10).join(lines)


# ── Parse ─────────────────────────────────────────────────
def parse_trade_input(text):
    """Parse trade input.
    Examples: 'buy CLEANING 100 @153', 'sell SENERGY 200 @140 ربح'
    """
    text = text.strip()

    # Pattern: action ticker [shares] [@price] [strategy] [reason...]
    m = re.match(
        r'(buy|sell|close|\u0634\u0631\u0627\u0621|\u0628\u064a\u0639)\s+'
        r'(\w+)\s*'
        r'(?:(\d+)\s*)?'
        r'(?:@\s*([\d.]+)\s*)?'
        r'(?:\[(\w+)\]\s*)?'
        r'(.*)?',
        text, re.IGNORECASE
    )
    if not m:
        return None

    action_map = {"\u0634\u0631\u0627\u0621": "buy", "\u0628\u064a\u0639": "sell"}
    action = action_map.get(m.group(1).lower(), m.group(1).lower())
    ticker = m.group(2).upper()
    shares = int(m.group(3)) if m.group(3) else None
    price = float(m.group(4)) if m.group(4) else None
    strategy = m.group(5) if m.group(5) else None
    reason = m.group(6).strip() if m.group(6) and m.group(6).strip() else None

    return {
        "ticker": ticker, "action": action, "shares": shares,
        "price": price, "strategy": strategy, "reason": reason
    }


# ── TG Handlers ───────────────────────────────────────────
def handle_trade_log(args_text):
    """/trade_log buy CLEANING 100 @153 [CLEANING_V3] accumulation zone"""
    if not args_text or not args_text.strip():
        return ("\u0627\u0644\u0627\u0633\u062a\u062e\u062f\u0627\u0645:\n"
                "/trade_log buy CLEANING 100 @153\n"
                "/trade_log sell SENERGY 200 @140\n"
                "/trade_log buy INOVEST 500 @0.120 [INOVEST_V5]")

    parsed = parse_trade_input(args_text)
    if not parsed:
        return "\u26a0\ufe0f \u0645\u0627 \u0641\u0647\u0645\u062a. \u0627\u0644\u0635\u064a\u063a\u0629: /trade_log buy TICKER [shares] [@price] [strategy]"

    return log_trade(**parsed)


def handle_trades_list(args_text=None):
    """/trades [ticker] [days]"""
    ticker = None
    days = 30
    if args_text and args_text.strip():
        parts = args_text.strip().split()
        for p in parts:
            if p.isdigit():
                days = int(p)
            elif p.isalpha():
                ticker = p
    trades = get_trades(days=days, ticker=ticker)
    return format_trades_tg(trades)


def handle_trade_review(args_text=None):
    """/trade_review [id] — show trades needing review, or review prompt for specific trade"""
    if args_text and args_text.strip().isdigit():
        trade_id = int(args_text.strip())
        db = _conn()
        row = db.execute("SELECT * FROM trade_journal WHERE id=?", (trade_id,)).fetchone()
        db.close()
        if not row:
            return f"\u26a0\ufe0f \u0645\u0627 \u0644\u0642\u064a\u062a \u0635\u0641\u0642\u0629 #{trade_id}"
        return format_review_prompt(dict(row))

    # Show unreviewed sells/closes
    db = _conn()
    rows = db.execute(
        "SELECT * FROM trade_journal WHERE action IN ('sell','close') "
        "AND (review IS NULL OR review = '') ORDER BY trade_date DESC LIMIT 5"
    ).fetchall()
    db.close()
    if not rows:
        return "\u2705 \u0643\u0644 \u0627\u0644\u0635\u0641\u0642\u0627\u062a \u0645\u0631\u0627\u062c\u0639\u0629"
    lines = ["\U0001f4cb \u0635\u0641\u0642\u0627\u062a \u0628\u062f\u0648\u0646 \u0645\u0631\u0627\u062c\u0639\u0629:"]
    for r in rows:
        lines.append(f"  #{r['id']} {r['trade_date']} {r['ticker']} {r['action'].upper()} @{r['price'] or '-'}")
    lines.append("")
    lines.append("\u0627\u0633\u062a\u062e\u062f\u0645 /trade_review [id] \u0644\u0644\u0645\u0631\u0627\u062c\u0639\u0629")
    return chr(10).join(lines)


# ── Quick Query Handlers ──────────────────────────────────
def quick_trades_recent():
    trades = get_trades(days=7, limit=5)
    return format_trades_tg(trades)

def quick_trade_stats():
    stats = get_stats(30)
    return format_stats_tg(stats)


# ── LLM Tool Handlers ────────────────────────────────────
def llm_tool_trade_log(ticker, action, shares=None, price=None,
                       strategy=None, reason=None, emotion=None,
                       outcome=None, pnl=None, review=None, trade_date=None):
    """LLM tool: log a trade."""
    result = log_trade(ticker, action, shares, price, strategy,
                       reason, emotion, outcome, pnl, review, trade_date)
    return {"ok": True, "text": result}


def llm_tool_trade_journal(days=30, ticker=None):
    """LLM tool: get trade journal."""
    trades = get_trades(days=days, ticker=ticker)
    if not trades:
        return {"ok": True, "text": "\u0644\u0627 \u0635\u0641\u0642\u0627\u062a \u0645\u0633\u062c\u0644\u0629"}
    text = format_trades_tg(trades)
    stats = get_stats(days)
    if stats:
        text += chr(10) + chr(10) + format_stats_tg(stats)
    return {"ok": True, "text": text}


def get_morning_trading_text():
    from datetime import date, timedelta
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    db = _conn()
    wk = db.execute("SELECT COUNT(*) as c FROM trade_journal WHERE trade_date>=?", (week_ago,)).fetchone()["c"]
    ur = db.execute("SELECT COUNT(*) as c FROM trade_journal WHERE action IN ('sell','close') AND (review IS NULL OR review='')").fetchone()["c"]
    db.close()
    if wk == 0 and ur == 0:
        return ""
    parts = []
    if wk > 0:
        parts.append(f"{wk} صفقة هالأسبوع")
    if ur > 0:
        parts.append(f"{ur} بدون مراجعة")
    return f"📈 التداول: {' | '.join(parts)}"
