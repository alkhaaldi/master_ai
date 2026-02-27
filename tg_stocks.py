"""Phase C1: Stock Portfolio Tracker for Telegram.

Commands:
- /stocks — Show portfolio with last known prices
- /price TICKER — Show info about a ticker
- /update_stock TICKER PRICE — Manually update price

Prices are stored locally since Boursa Kuwait blocks API access.
Update via /update_stock or send prices from TradingView alerts.
"""
import json, logging, os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("tg_stocks")

DATA_FILE = Path("/home/pi/master_ai/data/stock_portfolio.json")

# Default portfolio
_DEFAULT = {
    "CLEANING": {"buy": 153, "last": 105, "updated": "2026-02-27", "note": "\u062a\u062c\u0645\u064a\u0639 \u0645\u0624\u0633\u0633\u064a \u03b4+61M"},
    "SENERGY": {"buy": 111, "last": 111, "updated": "2026-02-27", "note": "\u0647\u062f\u0641 140-180"},
}


def _load() -> dict:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text())
        except:
            pass
    return dict(_DEFAULT)


def _save(data: dict):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def _pnl_emoji(pct: float) -> str:
    if pct > 5: return "\U0001f680"
    if pct > 0: return "\u2705"
    if pct > -5: return "\u26a0\ufe0f"
    return "\U0001f534"


async def get_portfolio() -> str:
    portfolio = _load()
    if not portfolio:
        return "\u0627\u0644\u0645\u062d\u0641\u0638\u0629 \u0641\u0627\u0636\u064a\u0629"
    
    lines = ["\U0001f4c8 \u0627\u0644\u0645\u062d\u0641\u0638\u0629:\n"]
    
    for ticker, info in portfolio.items():
        buy = info.get("buy", 0)
        last = info.get("last", 0)
        pnl = ((last - buy) / buy * 100) if buy > 0 and last > 0 else 0
        emoji = _pnl_emoji(pnl)
        
        lines.append(f"{emoji} {ticker}")
        lines.append(f"   \u0627\u0644\u0633\u0639\u0631: {last} | \u0627\u0644\u0634\u0631\u0627\u0621: {buy} | {pnl:+.1f}%")
        note = info.get("note", "")
        if note:
            lines.append(f"   \U0001f4dd {note}")
        lines.append(f"   \U0001f4c5 {info.get('updated', '?')}")
        lines.append("")
    
    lines.append("\u062a\u062d\u062f\u064a\u062b: /update_stock TICKER PRICE")
    return "\n".join(lines)


async def get_price(ticker: str) -> str:
    portfolio = _load()
    ticker = ticker.upper().strip()
    if ticker in portfolio:
        info = portfolio[ticker]
        buy = info.get("buy", 0)
        last = info.get("last", 0)
        pnl = ((last - buy) / buy * 100) if buy > 0 and last > 0 else 0
        return (
            f"\U0001f4ca {ticker}\n\n"
            f"\u0622\u062e\u0631 \u0633\u0639\u0631: {last}\n"
            f"\u0633\u0639\u0631 \u0627\u0644\u0634\u0631\u0627\u0621: {buy}\n"
            f"\u0627\u0644\u0631\u0628\u062d: {pnl:+.1f}%\n"
            f"\U0001f4dd {info.get('note', '')}\n"
            f"\u0622\u062e\u0631 \u062a\u062d\u062f\u064a\u062b: {info.get('updated', '?')}"
        )
    return f"\u26a0\ufe0f {ticker} \u0645\u0648 \u0628\u0627\u0644\u0645\u062d\u0641\u0638\u0629\n\u0623\u0636\u0641\u0647: /update_stock {ticker} PRICE"


def update_stock(ticker: str, price: float, note: str = None) -> str:
    portfolio = _load()
    ticker = ticker.upper().strip()
    today = datetime.now().strftime("%Y-%m-%d")
    
    if ticker in portfolio:
        portfolio[ticker]["last"] = price
        portfolio[ticker]["updated"] = today
        if note:
            portfolio[ticker]["note"] = note
    else:
        portfolio[ticker] = {"buy": price, "last": price, "updated": today, "note": note or ""}
    
    _save(portfolio)
    buy = portfolio[ticker]["buy"]
    pnl = ((price - buy) / buy * 100) if buy > 0 else 0
    return f"\u2705 {ticker} \u062a\u062d\u062f\u062b: {price} ({pnl:+.1f}%)"
