"""Phase C1: Stock Monitoring for Telegram.

Features:
- /stocks - Show portfolio status
- /price <ticker> - Check a specific stock price
- Background: check prices every 30 min during market hours (Sun-Thu 9:00-13:10 KW time)
- Alert on significant moves (>3% daily change)

Uses boursakuwait.com.kw for price data (no API key needed).
"""
import httpx, logging, asyncio, re
from datetime import datetime

logger = logging.getLogger("tg_stocks")

PORTFOLIO = {
    "CLEANING": {"buy": 153, "target": 200, "stop": 95, "name": "\u0634\u0631\u0643\u0629 \u0627\u0644\u062a\u0646\u0638\u064a\u0641\u0627\u062a"},
    "SENERGY": {"buy": 111, "target": 180, "stop": 95, "name": "\u0633\u064a\u0646\u0631\u062c\u064a"},
}

CHECK_INTERVAL = 1800  # 30 min
ALERT_THRESHOLD = 3.0  # % daily move to alert
_last_prices = {}  # ticker -> last known price


async def _fetch_price(ticker: str) -> dict | None:
    """Fetch stock price from boursakuwait.com.kw search API."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
            # Try the search endpoint
            r = await c.get(f"https://www.boursakuwait.com.kw/api/search?q={ticker}")
            if r.status_code == 200:
                data = r.json()
                if data and isinstance(data, list):
                    for item in data:
                        if item.get("symbol", "").upper() == ticker.upper():
                            return {
                                "symbol": ticker.upper(),
                                "price": float(item.get("last_price", 0)),
                                "change": float(item.get("change_pct", 0)),
                                "volume": int(item.get("volume", 0)),
                                "name": item.get("name_ar", ticker),
                            }
    except Exception as e:
        logger.warning(f"Price fetch error for {ticker}: {e}")
    
    # Fallback: try scraping
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
            r = await c.get(f"https://www.boursakuwait.com.kw/en/company/{ticker}/overview")
            if r.status_code == 200:
                # Extract price from HTML
                match = re.search(r'data-last-price="([\d.]+)"', r.text)
                change = re.search(r'data-change-pct="([\-\d.]+)"', r.text)
                if match:
                    return {
                        "symbol": ticker.upper(),
                        "price": float(match.group(1)),
                        "change": float(change.group(1)) if change else 0,
                        "volume": 0,
                        "name": ticker,
                    }
    except Exception as e:
        logger.warning(f"Scrape error for {ticker}: {e}")
    
    return None


async def get_portfolio_status() -> str:
    """Get full portfolio status."""
    lines = ["\U0001f4ca \u0645\u062d\u0641\u0638\u0629 \u0628\u0648 \u062e\u0644\u064a\u0641\u0629:\n"]
    
    for ticker, info in PORTFOLIO.items():
        data = await _fetch_price(ticker)
        if data:
            price = data["price"]
            pnl = ((price - info["buy"]) / info["buy"]) * 100 if info["buy"] > 0 else 0
            icon = "\U0001f7e2" if pnl >= 0 else "\U0001f534"
            
            line = f"{icon} {ticker} ({info['name']})\n"
            line += f"   \u0627\u0644\u0633\u0639\u0631: {price} | \u0627\u0644\u062a\u063a\u064a\u0631: {data['change']:+.1f}%\n"
            line += f"   \u0627\u0644\u0634\u0631\u0627\u0621: {info['buy']} | \u0627\u0644\u0631\u0628\u062d: {pnl:+.1f}%\n"
            line += f"   \u0627\u0644\u0647\u062f\u0641: {info['target']} | \u0627\u0644\u0648\u0642\u0641: {info['stop']}"
            lines.append(line)
            _last_prices[ticker] = price
        else:
            lines.append(f"\u26a0 {ticker}: \u0645\u0627 \u0642\u062f\u0631\u062a \u0623\u062c\u064a\u0628 \u0627\u0644\u0633\u0639\u0631")
    
    now = datetime.now()
    is_market = now.weekday() < 4 and 9 <= now.hour < 14  # Sun-Thu approx
    status = "\U0001f7e2 \u0627\u0644\u0633\u0648\u0642 \u0645\u0641\u062a\u0648\u062d" if is_market else "\U0001f534 \u0627\u0644\u0633\u0648\u0642 \u0645\u0642\u0641\u0644"
    lines.append(f"\n{status}")
    
    return "\n".join(lines)


async def get_price(ticker: str) -> str:
    """Get single stock price."""
    data = await _fetch_price(ticker)
    if not data:
        return f"\u26a0 \u0645\u0627 \u0644\u0642\u064a\u062a {ticker}"
    
    price = data["price"]
    return f"\U0001f4c8 {ticker}: {price} ({data['change']:+.1f}%) | Vol: {data['volume']:,}"


async def stock_monitor_loop(send_fn):
    """Background loop: check prices during market hours, alert on big moves."""
    logger.info("\U0001f4c8 Stock monitor started")
    
    while True:
        now = datetime.now()
        # Kuwait market: Sun-Thu 9:00-13:10
        is_market_day = now.weekday() in [6, 0, 1, 2, 3]  # Sun=6, Mon-Thu=0-3
        is_market_hour = 9 <= now.hour < 14
        
        if is_market_day and is_market_hour:
            for ticker, info in PORTFOLIO.items():
                data = await _fetch_price(ticker)
                if not data:
                    continue
                
                price = data["price"]
                change = abs(data["change"])
                prev = _last_prices.get(ticker)
                _last_prices[ticker] = price
                
                # Alert conditions
                alerts = []
                if change >= ALERT_THRESHOLD:
                    direction = "\U0001f4c8 \u0627\u0631\u062a\u0641\u0627\u0639" if data["change"] > 0 else "\U0001f4c9 \u0627\u0646\u062e\u0641\u0627\u0636"
                    alerts.append(f"{direction} {ticker} {data['change']:+.1f}% (\u0627\u0644\u0633\u0639\u0631: {price})")
                
                if price >= info["target"] and info["target"] > 0:
                    alerts.append(f"\U0001f3af {ticker} \u0648\u0635\u0644 \u0627\u0644\u0647\u062f\u0641! {price} >= {info['target']}")
                
                if price <= info["stop"] and info["stop"] > 0:
                    alerts.append(f"\U0001f6a8 {ticker} \u0643\u0633\u0631 \u0627\u0644\u0648\u0642\u0641! {price} <= {info['stop']}")
                
                for msg in alerts:
                    try:
                        await send_fn(msg)
                    except Exception as e:
                        logger.error(f"Stock alert send error: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)
