"""
tg_stocks.py - Kuwait Stock Exchange commands for Telegram
Commands: /stocks (portfolio), /price <ticker> (live price)
Auto: price alerts when target/stop hit
"""
import asyncio
import logging
import httpx
from datetime import datetime, time as dtime

logger = logging.getLogger("tg_stocks")

# Portfolio - update as needed
PORTFOLIO = {
    "CLEANING": {"buy": 153, "target": 200, "stop": 100, "notes": "institutional accumulation"},
    "SENERGY": {"buy": 111, "target": 180, "stop": 100, "notes": "pattern breakout"},
}

# Kuwait Stock Exchange - Boursa Kuwait
# No free API, so we scrape from marketwatch or use investing.com
TICKER_MAP = {
    "CLEANING": "KW:CLEANING",
    "SENERGY": "KW:SENERGY",
    "INOVEST": "KW:INOVEST",
    "ZAIN": "KW:ZAIN",
    "KFH": "KW:KFH",
    "NBK": "KW:NBK",
}

_last_prices = {}
_alert_sent = {}


async def _fetch_price_google(ticker: str) -> dict:
    """Try to get price from Google Finance."""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            # Try Google Finance
            url = f"https://www.google.com/finance/quote/{ticker}"
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            text = resp.text
            
            # Extract price from Google Finance page
            import re
            # Pattern: data-last-price="0.105"
            m = re.search(r'data-last-price="([\d.]+)"', text)
            if m:
                price = float(m.group(1)) * 1000  # Convert to fils
                return {"price": price, "source": "google"}
            
            # Alternative pattern
            m = re.search(r'class="YMlKec fxKbKc">([\d,.]+)', text)
            if m:
                price = float(m.group(1).replace(",", "")) * 1000
                return {"price": price, "source": "google"}
    except Exception as e:
        logger.debug(f"Google fetch failed for {ticker}: {e}")
    return None


async def _fetch_price(ticker: str) -> dict:
    """Get current price for a Kuwait stock ticker."""
    mapped = TICKER_MAP.get(ticker.upper(), f"KW:{ticker.upper()}")
    
    result = await _fetch_price_google(mapped)
    if result:
        return result
    
    return None


def format_portfolio() -> str:
    """Format portfolio status message."""
    lines = ["\U0001f4ca \u0627\u0644\u0645\u062d\u0641\u0638\u0629:\n"]
    for ticker, info in PORTFOLIO.items():
        last = _last_prices.get(ticker)
        if last:
            price = last["price"]
            pnl = ((price - info["buy"]) / info["buy"]) * 100
            icon = "\U0001f7e2" if pnl >= 0 else "\U0001f534"
            lines.append(f"{icon} {ticker}: {price:.0f} (\u0634\u0631\u0627\u0621@{info['buy']}, {pnl:+.1f}%)")
        else:
            lines.append(f"\u26aa {ticker}: \u0634\u0631\u0627\u0621@{info['buy']} (\u0644\u0627 \u0633\u0639\u0631 \u062d\u0627\u0644\u064a)")
        if info.get("notes"):
            lines.append(f"   \u0640 {info['notes']}")
    
    lines.append(f"\n\u23f0 \u0622\u062e\u0631 \u062a\u062d\u062f\u064a\u062b: {datetime.now().strftime('%H:%M')}")
    return "\n".join(lines)


async def cmd_stocks() -> str:
    """Handle /stocks command - refresh prices and show portfolio."""
    for ticker in PORTFOLIO:
        result = await _fetch_price(ticker)
        if result:
            _last_prices[ticker] = result
    
    return format_portfolio()


async def cmd_price(ticker: str) -> str:
    """Handle /price <ticker> command."""
    if not ticker:
        return "\u0627\u0644\u0627\u0633\u062a\u062e\u062f\u0627\u0645: /price CLEANING"
    
    ticker = ticker.upper().strip()
    result = await _fetch_price(ticker)
    
    if result:
        _last_prices[ticker] = result
        price = result["price"]
        
        # Check if in portfolio
        if ticker in PORTFOLIO:
            info = PORTFOLIO[ticker]
            pnl = ((price - info["buy"]) / info["buy"]) * 100
            return f"\U0001f4b0 {ticker}: {price:.0f} \u0641\u0644\u0633\n\u0634\u0631\u0627\u0621: {info['buy']} | \u0627\u0644\u0631\u0628\u062d: {pnl:+.1f}%\n\u0647\u062f\u0641: {info['target']} | \u0648\u0642\u0641: {info['stop']}"
        else:
            return f"\U0001f4b0 {ticker}: {price:.0f} \u0641\u0644\u0633"
    else:
        return f"\u26a0 \u0645\u0627 \u0642\u062f\u0631\u062a \u0623\u062c\u064a\u0628 \u0633\u0639\u0631 {ticker}"


async def stock_alert_loop(send_fn):
    """Background loop: check prices every 15 min during trading hours."""
    logger.info("\U0001f4c8 Stock alert loop started")
    
    while True:
        now = datetime.now()
        # Kuwait trading: Sun-Thu 9:00-12:40
        weekday = now.weekday()  # 0=Mon
        trading = weekday < 4 or weekday == 6  # Sun(6) to Thu(3)
        in_hours = dtime(9, 0) <= now.time() <= dtime(13, 0)
        
        if trading and in_hours:
            for ticker, info in PORTFOLIO.items():
                try:
                    result = await _fetch_price(ticker)
                    if not result:
                        continue
                    
                    price = result["price"]
                    _last_prices[ticker] = result
                    
                    # Check alerts
                    alert_key = f"{ticker}_{now.strftime('%Y%m%d')}"
                    
                    if price >= info["target"] and f"{alert_key}_target" not in _alert_sent:
                        await send_fn(f"\U0001f3af {ticker} \u0648\u0635\u0644 \u0627\u0644\u0647\u062f\u0641! {price:.0f} >= {info['target']}")
                        _alert_sent[f"{alert_key}_target"] = True
                    
                    if price <= info["stop"] and f"{alert_key}_stop" not in _alert_sent:
                        await send_fn(f"\U0001f6a8 {ticker} \u0648\u0635\u0644 \u0627\u0644\u0648\u0642\u0641! {price:.0f} <= {info['stop']}")
                        _alert_sent[f"{alert_key}_stop"] = True
                    
                except Exception as e:
                    logger.debug(f"Stock check error {ticker}: {e}")
        
        await asyncio.sleep(900)  # 15 min
