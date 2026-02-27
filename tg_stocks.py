"""Phase C1: Stock Portfolio Tracker for Telegram.

Commands:
- /stocks — Show portfolio summary
- /price TICKER — Get current price for a ticker
"""
import httpx, logging, re
from datetime import datetime

logger = logging.getLogger("tg_stocks")

# Portfolio — update manually or via command
PORTFOLIO = {
    "CLEANING": {"buy_price": 153, "shares": 0, "note": "\u062a\u062c\u0645\u064a\u0639 \u0645\u0624\u0633\u0633\u064a"},
    "SENERGY": {"buy_price": 111, "shares": 0, "note": "\u0647\u062f\u0641 140-180"},
}

# Boursa Kuwait scraper (public page, no API key needed)
BOURSA_URL = "https://www.boursakuwait.com.kw/api/v2/instruments/search?q={ticker}&lang=en"


async def _fetch_price(ticker: str) -> dict:
    """Fetch price from Boursa Kuwait API."""
    ticker = ticker.upper().strip()
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            # Try Boursa Kuwait search API
            resp = await client.get(
                f"https://www.boursakuwait.com.kw/api/v2/instruments/search",
                params={"q": ticker, "lang": "en"},
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list) and len(data) > 0:
                    item = data[0]
                    return {
                        "ticker": item.get("symbol", ticker),
                        "name_ar": item.get("name_ar", ""),
                        "name_en": item.get("name_en", ""),
                        "last": item.get("last", 0),
                        "change": item.get("change", 0),
                        "change_pct": item.get("change_pct", 0),
                        "volume": item.get("volume", 0),
                        "high": item.get("high", 0),
                        "low": item.get("low", 0),
                        "open": item.get("open", 0),
                    }
            
            # Fallback: try direct symbol lookup
            resp2 = await client.get(
                f"https://www.boursakuwait.com.kw/api/v2/instruments/{ticker}/overview",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp2.status_code == 200:
                item = resp2.json()
                return {
                    "ticker": ticker,
                    "name_ar": item.get("name_ar", ""),
                    "name_en": item.get("name_en", ""),
                    "last": item.get("last_price", item.get("last", 0)),
                    "change": item.get("change", 0),
                    "change_pct": item.get("change_percent", 0),
                    "volume": item.get("volume", 0),
                    "high": item.get("high", 0),
                    "low": item.get("low", 0),
                    "open": item.get("open", 0),
                }
    except Exception as e:
        logger.error(f"Price fetch error for {ticker}: {e}")
    return None


def _format_number(n) -> str:
    """Format number with commas."""
    try:
        if isinstance(n, float):
            return f"{n:,.3f}"
        return f"{int(n):,}"
    except:
        return str(n)


def _pnl_emoji(pct: float) -> str:
    if pct > 5: return "\U0001f680"
    if pct > 0: return "\u2705"
    if pct > -5: return "\u26a0\ufe0f"
    return "\U0001f534"


async def get_portfolio() -> str:
    """Get portfolio summary with live prices."""
    lines = ["\U0001f4c8 \u0627\u0644\u0645\u062d\u0641\u0638\u0629:\n"]
    
    for ticker, info in PORTFOLIO.items():
        data = await _fetch_price(ticker)
        if data and data["last"]:
            price = float(data["last"])
            buy = info["buy_price"]
            pnl_pct = ((price - buy) / buy * 100) if buy > 0 else 0
            emoji = _pnl_emoji(pnl_pct)
            change_str = f"+{data['change_pct']}" if float(data.get('change_pct', 0)) >= 0 else str(data['change_pct'])
            
            lines.append(f"{emoji} {ticker}")
            name = data.get('name_ar') or data.get('name_en', '')
            if name:
                lines.append(f"   {name}")
            lines.append(f"   \u0627\u0644\u0633\u0639\u0631: {_format_number(price)} | \u0627\u0644\u062a\u063a\u064a\u064a\u0631: {change_str}%")
            if buy > 0:
                lines.append(f"   \u0627\u0644\u0634\u0631\u0627\u0621: {buy} | \u0627\u0644\u0631\u0628\u062d: {pnl_pct:+.1f}%")
            if info.get("note"):
                lines.append(f"   \U0001f4dd {info['note']}")
            lines.append("")
        else:
            lines.append(f"\u26a0\ufe0f {ticker}: \u0645\u0627 \u0642\u062f\u0631\u062a \u0623\u062c\u064a\u0628 \u0627\u0644\u0633\u0639\u0631\n")
    
    return "\n".join(lines)


async def get_price(ticker: str) -> str:
    """Get price for a specific ticker."""
    data = await _fetch_price(ticker)
    if not data or not data.get("last"):
        return f"\u26a0\ufe0f \u0645\u0627 \u0644\u0642\u064a\u062a {ticker.upper()} \u0628\u0628\u0648\u0631\u0635\u0629 \u0627\u0644\u0643\u0648\u064a\u062a"
    
    price = float(data["last"])
    change_pct = data.get("change_pct", 0)
    change_str = f"+{change_pct}" if float(change_pct) >= 0 else str(change_pct)
    name = data.get("name_ar") or data.get("name_en", ticker.upper())
    vol = _format_number(data.get("volume", 0))
    
    return (
        f"\U0001f4ca {data['ticker']} — {name}\n\n"
        f"\u0627\u0644\u0633\u0639\u0631: {_format_number(price)}\n"
        f"\u0627\u0644\u062a\u063a\u064a\u064a\u0631: {change_str}%\n"
        f"\u0627\u0644\u0623\u0639\u0644\u0649: {_format_number(data.get('high', 0))} | \u0627\u0644\u0623\u062f\u0646\u0649: {_format_number(data.get('low', 0))}\n"
        f"\u0627\u0644\u0627\u0641\u062a\u062a\u0627\u062d: {_format_number(data.get('open', 0))}\n"
        f"\u0627\u0644\u0643\u0645\u064a\u0629: {vol}"
    )
