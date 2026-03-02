"""
life_stocks.py - Professional Kuwait Stock Exchange Portfolio Manager
Dynamic portfolio from DB, live prices, trade history, watchlist, alerts
"""
import sqlite3
import json
import logging
import re
import asyncio
from datetime import datetime, date, timedelta
from typing import Optional

import httpx

logger = logging.getLogger("life_stocks")

DB_PATH = "/home/pi/master_ai/data/audit.db"

# Boursa Kuwait tickers - expandable
KNOWN_TICKERS = {
    "CLEANING": "شركة أسواق المزادات الدولية",
    "SENERGY": "الطاقة المتحدة",
    "INOVEST": "إينوفست",
    "ZAIN": "زين",
    "KFH": "بيت التمويل الكويتي",
    "NBK": "بنك الكويت الوطني",
    "AGILITY": "أجيليتي",
    "HUMANSOFT": "هيومن سوفت",
    "BOURSA": "بورصة الكويت",
    "STC": "الاتصالات الكويتية",
    "BOUBYAN": "بنك بوبيان",
    "GBK": "بنك الخليج",
    "ABK": "البنك الأهلي الكويتي",
    "MABANEE": "مبانى",
    "MEZZAN": "مزان القابضة",
    "ALIMTIAZ": "الامتياز للاستثمار",
    "NOOR": "نور للاستثمار المالي",
    "IFA": "المجموعة المالية الدولية",
    "KIPCO": "كيبكو",
    "AAYAN": "أعيان للإجارة",
    "QURAIN": "القرين القابضة",
    "SALHIA": "الصالحية العقارية",
    "TAMDEEN": "التمدين العقارية",
    "BPCC": "الكابلات الكويتية",
}

# Arabic aliases for tickers
TICKER_ALIASES = {
    "كلينج": "CLEANING", "تنظيف": "CLEANING", "مزادات": "CLEANING",
    "سنرجي": "SENERGY", "طاقة": "SENERGY",
    "اينوفست": "INOVEST", "انوفست": "INOVEST",
    "زين": "ZAIN",
    "بيتك": "KFH", "التمويل": "KFH",
    "الوطني": "NBK",
    "اجيليتي": "AGILITY",
    "هيومن": "HUMANSOFT",
    "بورصة": "BOURSA",
    "اتصالات": "STC", "stc": "STC",
    "بوبيان": "BOUBYAN",
    "الخليج": "GBK",
    "الأهلي": "ABK", "الاهلي": "ABK",
    "مبانى": "MABANEE", "مباني": "MABANEE",
    "مزان": "MEZZAN",
    "الامتياز": "ALIMTIAZ", "امتياز": "ALIMTIAZ",
    "نور": "NOOR",
    "كيبكو": "KIPCO",
    "أعيان": "AAYAN", "اعيان": "AAYAN",
    "القرين": "QURAIN", "قرين": "QURAIN",
    "الصالحية": "SALHIA", "صالحية": "SALHIA",
    "التمدين": "TAMDEEN", "تمدين": "TAMDEEN",
}


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def resolve_ticker(text: str) -> Optional[str]:
    """Resolve Arabic or English ticker name to standard ticker."""
    t = text.strip().upper()
    if t in KNOWN_TICKERS:
        return t
    t_lower = text.strip().lower()
    if t_lower in TICKER_ALIASES:
        return TICKER_ALIASES[t_lower]
    # Fuzzy match
    for alias, ticker in TICKER_ALIASES.items():
        if alias in t_lower or t_lower in alias:
            return ticker
    return t if len(t) <= 12 else None


# ═══════════════════════════════════════════
# Portfolio Management
# ═══════════════════════════════════════════

def portfolio_add(ticker: str, shares: int, price: float,
                  target: float = None, stop: float = None,
                  notes: str = "", buy_date: str = None) -> str:
    """Add a position to portfolio."""
    ticker = resolve_ticker(ticker) or ticker.upper()
    db = _db()
    db.execute(
        """INSERT INTO portfolio (ticker, shares, buy_price, buy_date,
           target_price, stop_price, notes, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'active')""",
        (ticker, shares, price, buy_date or date.today().isoformat(),
         target, stop, notes)
    )
    db.commit()
    total = shares * price
    name = KNOWN_TICKERS.get(ticker, ticker)
    msg = f"✅ تم إضافة {name} ({ticker})\n"
    msg += f"📊 {shares} سهم × {price} = {total:,.0f} د.ك"
    if target:
        msg += f"\n🎯 هدف: {target}"
    if stop:
        msg += f"\n🛑 وقف: {stop}"
    return msg


def portfolio_sell(ticker: str, shares: int, price: float, notes: str = "") -> str:
    """Record a sell and update portfolio."""
    ticker = resolve_ticker(ticker) or ticker.upper()
    db = _db()

    # Find active position
    pos = db.execute(
        "SELECT * FROM portfolio WHERE ticker=? AND status='active' ORDER BY created_at DESC LIMIT 1",
        (ticker,)
    ).fetchone()

    # Record trade
    total = shares * price
    db.execute(
        "INSERT INTO trades (ticker, action, shares, price, total, trade_date, notes) VALUES (?,?,?,?,?,?,?)",
        (ticker, "sell", shares, price, total, date.today().isoformat(), notes)
    )

    pnl_msg = ""
    if pos:
        buy_total = pos["shares"] * pos["buy_price"]
        sell_total = shares * price
        pnl = sell_total - (shares * pos["buy_price"])
        pnl_pct = (price / pos["buy_price"] - 1) * 100
        remaining = pos["shares"] - shares

        if remaining <= 0:
            db.execute("UPDATE portfolio SET status='closed' WHERE id=?", (pos["id"],))
            pnl_msg = f"\n📦 الصفقة مقفلة"
        else:
            db.execute("UPDATE portfolio SET shares=? WHERE id=?", (remaining, pos["id"]))
            pnl_msg = f"\n📦 متبقي: {remaining} سهم"

        arrow = "🟢" if pnl >= 0 else "🔴"
        pnl_msg += f"\n{arrow} الربح/الخسارة: {pnl:+,.1f} د.ك ({pnl_pct:+.1f}%)"

    db.commit()
    name = KNOWN_TICKERS.get(ticker, ticker)
    return f"💰 بيع {name} ({ticker})\n📊 {shares} سهم × {price} = {total:,.0f} د.ك{pnl_msg}"


def portfolio_list() -> str:
    """List all active positions."""
    db = _db()
    rows = db.execute(
        "SELECT * FROM portfolio WHERE status='active' ORDER BY ticker"
    ).fetchall()

    if not rows:
        return "📂 المحفظة فاضية"

    total_invested = 0
    msg = "📊 **محفظتك**\n\n"
    for r in rows:
        name = KNOWN_TICKERS.get(r["ticker"], r["ticker"])
        invested = r["shares"] * r["buy_price"]
        total_invested += invested
        msg += f"• **{name}** ({r['ticker']})\n"
        msg += f"  {r['shares']} سهم × {r['buy_price']} = {invested:,.0f} د.ك\n"
        if r["target_price"]:
            msg += f"  🎯 {r['target_price']}"
        if r["stop_price"]:
            msg += f" | 🛑 {r['stop_price']}"
        if r["target_price"] or r["stop_price"]:
            msg += "\n"
        if r["notes"]:
            msg += f"  📝 {r['notes']}\n"
        msg += "\n"

    msg += f"💼 إجمالي المستثمر: {total_invested:,.0f} د.ك"
    return msg


def portfolio_update(ticker: str, target: float = None, stop: float = None,
                     notes: str = None) -> str:
    """Update target/stop/notes for a position."""
    ticker = resolve_ticker(ticker) or ticker.upper()
    db = _db()
    pos = db.execute(
        "SELECT * FROM portfolio WHERE ticker=? AND status='active' LIMIT 1",
        (ticker,)
    ).fetchone()
    if not pos:
        return f"❌ ما لقيت {ticker} بالمحفظة"

    updates = []
    params = []
    if target is not None:
        updates.append("target_price=?")
        params.append(target)
    if stop is not None:
        updates.append("stop_price=?")
        params.append(stop)
    if notes is not None:
        updates.append("notes=?")
        params.append(notes)
    if not updates:
        return "❌ شنو تبي تعدل؟"

    updates.append("updated_at=CURRENT_TIMESTAMP")
    params.append(pos["id"])
    db.execute(f"UPDATE portfolio SET {','.join(updates)} WHERE id=?", params)
    db.commit()
    return f"✅ تم تحديث {KNOWN_TICKERS.get(ticker, ticker)}"


def portfolio_remove(ticker: str) -> str:
    """Remove/close a position without recording a sell."""
    ticker = resolve_ticker(ticker) or ticker.upper()
    db = _db()
    r = db.execute(
        "UPDATE portfolio SET status='closed' WHERE ticker=? AND status='active'",
        (ticker,)
    )
    db.commit()
    if r.rowcount:
        return f"✅ شلت {KNOWN_TICKERS.get(ticker, ticker)} من المحفظة"
    return f"❌ ما لقيت {ticker}"


# ═══════════════════════════════════════════
# Watchlist
# ═══════════════════════════════════════════

def watchlist_add(ticker: str, above: float = None, below: float = None,
                  notes: str = "") -> str:
    """Add ticker to watchlist."""
    ticker = resolve_ticker(ticker) or ticker.upper()
    db = _db()
    try:
        db.execute(
            "INSERT INTO watchlist (ticker, alert_above, alert_below, notes) VALUES (?,?,?,?)",
            (ticker, above, below, notes)
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.execute(
            "UPDATE watchlist SET alert_above=?, alert_below=?, notes=? WHERE ticker=?",
            (above, below, notes, ticker)
        )
        db.commit()
    name = KNOWN_TICKERS.get(ticker, ticker)
    msg = f"👁 تمت مراقبة {name}"
    if above:
        msg += f" | فوق {above}"
    if below:
        msg += f" | تحت {below}"
    return msg


def watchlist_remove(ticker: str) -> str:
    ticker = resolve_ticker(ticker) or ticker.upper()
    db = _db()
    db.execute("DELETE FROM watchlist WHERE ticker=?", (ticker,))
    db.commit()
    return f"✅ شلت {ticker} من المراقبة"


def watchlist_list() -> str:
    db = _db()
    rows = db.execute("SELECT * FROM watchlist ORDER BY ticker").fetchall()
    if not rows:
        return "👁 قائمة المراقبة فاضية"
    msg = "👁 **قائمة المراقبة**\n\n"
    for r in rows:
        name = KNOWN_TICKERS.get(r["ticker"], r["ticker"])
        msg += f"• {name} ({r['ticker']})"
        if r["alert_above"]:
            msg += f" | ⬆ {r['alert_above']}"
        if r["alert_below"]:
            msg += f" | ⬇ {r['alert_below']}"
        if r["notes"]:
            msg += f" — {r['notes']}"
        msg += "\n"
    return msg


# ═══════════════════════════════════════════
# Trade History
# ═══════════════════════════════════════════

def trade_history(ticker: str = None, limit: int = 10) -> str:
    db = _db()
    if ticker:
        ticker = resolve_ticker(ticker) or ticker.upper()
        rows = db.execute(
            "SELECT * FROM trades WHERE ticker=? ORDER BY created_at DESC LIMIT ?",
            (ticker, limit)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()

    if not rows:
        return "📜 ما فيه صفقات مسجلة"

    msg = "📜 **سجل الصفقات**\n\n"
    for r in rows:
        icon = "🟢" if r["action"] == "buy" else "🔴"
        action_ar = "شراء" if r["action"] == "buy" else "بيع"
        msg += f"{icon} {r['trade_date']} | {action_ar} {r['ticker']} | "
        msg += f"{r['shares']} × {r['price']} = {r['total']:,.0f} د.ك\n"
    return msg


# ═══════════════════════════════════════════
# Price Fetching
# ═══════════════════════════════════════════

async def fetch_price(ticker: str) -> dict:
    """Fetch live price from multiple sources."""
    ticker = resolve_ticker(ticker) or ticker.upper()
    # Try Google Finance
    try:
        url = f"https://www.google.com/finance/quote/{ticker}:KUW"
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            text = resp.text
            # Extract price from page
            match = re.search(r'data-last-price="([\d.]+)"', text)
            if match:
                price = float(match.group(1))
                # Try to get change
                change_match = re.search(r'data-change="([-\d.]+)"', text)
                pct_match = re.search(r'data-pct-change="([-\d.]+)"', text)
                return {
                    "ticker": ticker,
                    "price": price,
                    "change": float(change_match.group(1)) if change_match else 0,
                    "change_pct": float(pct_match.group(1)) if pct_match else 0,
                    "source": "google",
                }
    except Exception as e:
        logger.warning(f"Google Finance failed for {ticker}: {e}")

    # Fallback: Investing.com or MarketWatch
    return {"ticker": ticker, "price": None, "error": "price unavailable"}


async def fetch_price_display(ticker: str) -> str:
    """Format price for display."""
    data = await fetch_price(ticker)
    name = KNOWN_TICKERS.get(data["ticker"], data["ticker"])
    if data.get("price"):
        arrow = "🟢 ▲" if data.get("change", 0) >= 0 else "🔴 ▼"
        msg = f"💹 {name} ({data['ticker']})\n"
        msg += f"السعر: {data['price']}\n"
        if data.get("change"):
            msg += f"التغيير: {arrow} {data['change']:+.3f} ({data['change_pct']:+.2f}%)"
        return msg
    return f"❌ ما قدرت أجيب سعر {name}"


# ═══════════════════════════════════════════
# Smart Portfolio Summary
# ═══════════════════════════════════════════

async def portfolio_summary() -> str:
    """Portfolio with live prices and P&L."""
    db = _db()
    rows = db.execute(
        "SELECT * FROM portfolio WHERE status='active' ORDER BY ticker"
    ).fetchall()
    if not rows:
        return "📂 المحفظة فاضية — استخدم: شريت [سهم] [عدد] بـ [سعر]"

    msg = "📊 **ملخص المحفظة**\n\n"
    total_invested = 0
    total_current = 0

    for r in rows:
        name = KNOWN_TICKERS.get(r["ticker"], r["ticker"])
        invested = r["shares"] * r["buy_price"]
        total_invested += invested

        price_data = await fetch_price(r["ticker"])
        current_price = price_data.get("price")

        if current_price:
            current_val = r["shares"] * current_price
            total_current += current_val
            pnl = current_val - invested
            pnl_pct = (current_price / r["buy_price"] - 1) * 100
            arrow = "🟢" if pnl >= 0 else "🔴"
            msg += f"{arrow} **{name}** ({r['ticker']})\n"
            msg += f"  {r['shares']} × {current_price} = {current_val:,.0f} د.ك\n"
            msg += f"  الشراء: {r['buy_price']} | PnL: {pnl:+,.0f} ({pnl_pct:+.1f}%)\n"
        else:
            total_current += invested
            msg += f"⚪ **{name}** ({r['ticker']})\n"
            msg += f"  {r['shares']} × {r['buy_price']} = {invested:,.0f} د.ك\n"
            msg += f"  ⚠️ السعر غير متوفر\n"

        if r["target_price"]:
            msg += f"  🎯 {r['target_price']}"
        if r["stop_price"]:
            msg += f" | 🛑 {r['stop_price']}"
        if r["target_price"] or r["stop_price"]:
            msg += "\n"
        msg += "\n"

    total_pnl = total_current - total_invested
    total_pct = (total_current / total_invested - 1) * 100 if total_invested else 0
    arrow = "🟢" if total_pnl >= 0 else "🔴"
    msg += f"━━━━━━━━━━━━━━━\n"
    msg += f"💼 المستثمر: {total_invested:,.0f} د.ك\n"
    msg += f"💰 الحالي: {total_current:,.0f} د.ك\n"
    msg += f"{arrow} الإجمالي: {total_pnl:+,.0f} ({total_pct:+.1f}%)"
    return msg


# ═══════════════════════════════════════════
# Arabic NLP - Parse stock commands
# ═══════════════════════════════════════════

def parse_stock_command(text: str) -> dict:
    """Parse natural Arabic stock commands.

    Examples:
        شريت ZAIN 500 سهم بـ 190
        بعت كلينج 1000 بـ 115
        راقب NBK فوق 960
        شيل INOVEST من المحفظة
        هدف CLEANING 200
        وقف SENERGY 100
    """
    text = text.strip()

    # Buy: شريت TICKER SHARES بـ PRICE
    m = re.search(
        r'(?:شريت|اشتريت|شراء|buy)\s+(\S+)\s+(\d+)\s*(?:سهم)?\s*(?:بـ?|@|بسعر)\s*([\d.]+)',
        text, re.IGNORECASE
    )
    if m:
        return {"action": "buy", "ticker": m.group(1), "shares": int(m.group(2)),
                "price": float(m.group(3))}

    # Sell: بعت TICKER SHARES بـ PRICE
    m = re.search(
        r'(?:بعت|بيع|sell)\s+(\S+)\s+(\d+)\s*(?:سهم)?\s*(?:بـ?|@|بسعر)\s*([\d.]+)',
        text, re.IGNORECASE
    )
    if m:
        return {"action": "sell", "ticker": m.group(1), "shares": int(m.group(2)),
                "price": float(m.group(3))}

    # Watch: راقب TICKER فوق/تحت PRICE
    m = re.search(
        r'(?:راقب|تابع|watch)\s+(\S+)\s*(?:فوق|above)?\s*([\d.]*)\s*(?:تحت|below)?\s*([\d.]*)',
        text, re.IGNORECASE
    )
    if m and (m.group(2) or m.group(3)):
        return {"action": "watch", "ticker": m.group(1),
                "above": float(m.group(2)) if m.group(2) else None,
                "below": float(m.group(3)) if m.group(3) else None}

    # Remove: شيل TICKER
    m = re.search(r'(?:شيل|احذف|remove)\s+(\S+)\s*(?:من\s*المحفظة)?', text, re.IGNORECASE)
    if m:
        return {"action": "remove", "ticker": m.group(1)}

    # Target: هدف TICKER PRICE
    m = re.search(r'(?:هدف|target)\s+(\S+)\s+([\d.]+)', text, re.IGNORECASE)
    if m:
        return {"action": "set_target", "ticker": m.group(1), "price": float(m.group(2))}

    # Stop: وقف TICKER PRICE
    m = re.search(r'(?:وقف|ستوب|stop)\s+(\S+)\s+([\d.]+)', text, re.IGNORECASE)
    if m:
        return {"action": "set_stop", "ticker": m.group(1), "price": float(m.group(2))}

    # Price: سعر TICKER or كم TICKER
    m = re.search(r'(?:سعر|كم|price)\s+(\S+)', text, re.IGNORECASE)
    if m:
        return {"action": "price", "ticker": m.group(1)}

    return {"action": "unknown"}


async def handle_stock_command(text: str) -> str:
    """Main entry point for stock-related commands."""
    cmd = parse_stock_command(text)
    action = cmd.get("action", "unknown")

    if action == "buy":
        result = portfolio_add(cmd["ticker"], cmd["shares"], cmd["price"])
        # Also record trade
        ticker = resolve_ticker(cmd["ticker"]) or cmd["ticker"].upper()
        db = _db()
        total = cmd["shares"] * cmd["price"]
        db.execute(
            "INSERT INTO trades (ticker, action, shares, price, total, trade_date) VALUES (?,?,?,?,?,?)",
            (ticker, "buy", cmd["shares"], cmd["price"], total, date.today().isoformat())
        )
        db.commit()
        return result

    elif action == "sell":
        return portfolio_sell(cmd["ticker"], cmd["shares"], cmd["price"])

    elif action == "watch":
        return watchlist_add(cmd["ticker"], cmd.get("above"), cmd.get("below"))

    elif action == "remove":
        return portfolio_remove(cmd["ticker"])

    elif action == "set_target":
        return portfolio_update(cmd["ticker"], target=cmd["price"])

    elif action == "set_stop":
        return portfolio_update(cmd["ticker"], stop=cmd["price"])

    elif action == "price":
        return await fetch_price_display(cmd["ticker"])

    # If no specific command, show portfolio
    return await portfolio_summary()


# ═══════════════════════════════════════════
# Seed current positions from memory
# ═══════════════════════════════════════════

def seed_portfolio():
    """Seed portfolio with known positions if empty."""
    db = _db()
    count = db.execute("SELECT COUNT(*) FROM portfolio WHERE status='active'").fetchone()[0]
    if count == 0:
        portfolio_add("CLEANING", 1000, 153, target=200, stop=100,
                      notes="institutional accumulation delta+61M", buy_date="2025-01-01")
        portfolio_add("SENERGY", 1000, 111, target=180, stop=100,
                      notes="خير عالمية، باترن الخرافي", buy_date="2025-01-01")
        logger.info("Portfolio seeded with 2 initial positions")


# Auto-seed on import
try:
    seed_portfolio()
except Exception as e:
    logger.warning(f"Seed failed: {e}")
