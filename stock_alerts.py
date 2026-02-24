#!/home/pi/master_ai/venv/bin/python3
"""
Stock Alert System for Master AI v4.0
Receives TradingView webhook alerts and announces via Alexa
Also supports manual price checks via API
"""
import os, json, logging, requests
from datetime import datetime

HA_URL = "http://localhost:8123"
HA_TOKEN = os.environ.get("HA_TOKEN", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI1ZDVlZWRkMzk0MjY0MDk2OTY0YThlNjYyZDU0NTYzYiIsImlhdCI6MTc3MTI1NDI4NywiZXhwIjoyMDg2NjE0Mjg3fQ.Ws_86k8u0abSGfBZMYxKVSxzO8r6kX2yyIXPicjyFd0")
ALERT_LOG = "/home/pi/master_ai/data/stock_alerts.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("stock_alerts")

# Portfolio tracking
PORTFOLIO = {
    "CLEANING": {"buy_price": 153, "shares": 0, "target": 200, "stop": 100},
    "SENERGY": {"buy_price": 111, "shares": 0, "target": 180, "stop": 100},
    "INOVEST": {"buy_price": 0, "shares": 0, "target": 0, "stop": 0},
}

def announce_alexa(message, entity="media_player.my_room_alexa"):
    """Send TTS announcement via Alexa."""
    headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "entity_id": entity,
        "message": message
    }
    try:
        r = requests.post(f"{HA_URL}/api/services/notify/alexa_media_my_room_alexa",
                         json=payload, headers=headers, timeout=10)
        if r.status_code not in (200, 201):
            # Try alternate method
            r = requests.post(f"{HA_URL}/api/services/tts/speak",
                            json={"entity_id": entity, "message": message, "media_player_entity_id": entity},
                            headers=headers, timeout=10)
        log.info(f"Alexa announce: {message[:50]}... status={r.status_code}")
        return r.status_code in (200, 201)
    except Exception as e:
        log.error(f"Alexa announce failed: {e}")
        return False

def update_ha_sensor(ticker, price, change_pct=0, signal="", volume=0):
    """Update HA sensor for stock."""
    headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
    entity = f"sensor.stock_{ticker.lower()}"
    portfolio = PORTFOLIO.get(ticker, {})
    pnl = ((price - portfolio.get("buy_price", 0)) / portfolio.get("buy_price", 1) * 100) if portfolio.get("buy_price") else 0
    
    payload = {
        "state": str(price),
        "attributes": {
            "friendly_name": f"Stock: {ticker}",
            "icon": "mdi:chart-line",
            "unit_of_measurement": "fils",
            "change_pct": round(change_pct, 2),
            "signal": signal,
            "volume": volume,
            "buy_price": portfolio.get("buy_price", 0),
            "pnl_pct": round(pnl, 2),
            "target": portfolio.get("target", 0),
            "stop_loss": portfolio.get("stop", 0),
            "last_update": datetime.now().isoformat(),
        }
    }
    requests.post(f"{HA_URL}/api/states/{entity}", json=payload, headers=headers, timeout=10)

def save_alert(alert_data):
    """Save alert to log file."""
    alerts = []
    if os.path.exists(ALERT_LOG):
        with open(ALERT_LOG) as f:
            alerts = json.load(f)
    alerts.append({**alert_data, "timestamp": datetime.now().isoformat()})
    alerts = alerts[-500:]  # Keep last 500
    with open(ALERT_LOG, "w") as f:
        json.dump(alerts, f, indent=2)

def process_webhook(data):
    """Process TradingView webhook alert.
    
    Expected format from TradingView:
    {
        "ticker": "CLEANING",
        "price": 108,
        "action": "BUY" | "SELL" | "ALERT",
        "signal": "SSA+VWAP cross",
        "timeframe": "1D",
        "volume": 150000,
        "strategy": "CLEANING_V3"
    }
    """
    ticker = data.get("ticker", "UNKNOWN")
    price = float(data.get("price", 0))
    action = data.get("action", "ALERT")
    signal = data.get("signal", "")
    volume = data.get("volume", 0)
    strategy = data.get("strategy", "")
    
    # Update HA sensor
    update_ha_sensor(ticker, price, signal=signal, volume=volume)
    
    # Build announcement
    portfolio = PORTFOLIO.get(ticker, {})
    pnl = ((price - portfolio.get("buy_price", 0)) / portfolio.get("buy_price", 1) * 100) if portfolio.get("buy_price") else 0
    
    if action == "BUY":
        msg = f"تنبيه شراء! {ticker} عند {price} فلس. إشارة: {signal}"
    elif action == "SELL":
        msg = f"تنبيه بيع! {ticker} عند {price} فلس. الربح {pnl:.1f} بالمية"
    elif action == "STOP":
        msg = f"تحذير ستوب لوس! {ticker} وصل {price} فلس"
    elif action == "TARGET":
        msg = f"مبروك! {ticker} وصل الهدف عند {price} فلس. الربح {pnl:.1f} بالمية"
    else:
        msg = f"تنبيه {ticker} عند {price} فلس. {signal}"
    
    # Announce
    announce_alexa(msg)
    
    # Save
    save_alert({"ticker": ticker, "price": price, "action": action, "signal": signal, "message": msg})
    
    log.info(f"Alert: {action} {ticker} @ {price} | {signal}")
    return {"status": "ok", "message": msg, "pnl_pct": round(pnl, 2)}

