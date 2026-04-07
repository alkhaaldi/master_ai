import subprocess, sys, json

# First get actual data to send to ChatGPT
import urllib.request

# Get ema-live data
try:
    r = urllib.request.urlopen('http://localhost:9000/dashboard/ema-live', timeout=30)
    live = json.loads(r.read())
    live_summary = f"ema-live returns: {live['bullish_count']} bullish, {live['bearish_count']} bearish, {live.get('touching_count',0)} touching, total_checked={live['total_checked']}, bridge_online={live['bridge_online']}"
    sample_bull = json.dumps(live['bullish'][:3], indent=2) if live['bullish'] else "[]"
    sample_bear = json.dumps(live['bearish'][:3], indent=2) if live['bearish'] else "[]"
except Exception as e:
    live_summary = f"ema-live FAILED: {e}"
    sample_bull = "[]"
    sample_bear = "[]"

# Get Bridge raw response for one stock to compare
try:
    from bridge_client import BridgeClient, BRIDGE_BASE_URL
    import asyncio
    async def test():
        c = BridgeClient(BRIDGE_BASE_URL)
        try:
            result = await c.get_multi_analysis_30m(["ZAIN","NBK","HUMANSOFT","CLEANING","EQUIPMENT"])
            return result
        finally:
            await c.close()
    bridge_raw = asyncio.run(test())
    bridge_sample = {}
    for sym, data in list(bridge_raw.get("symbols", {}).items())[:2]:
        bridge_sample[sym] = {
            "price": data.get("price"),
            "ema9": data.get("ema9"),
            "ema20": data.get("ema20"),
            "ema21": data.get("ema21"),
            "ema_9": data.get("ema_9"),
            "ema_20": data.get("ema_20"),
            "ema_21": data.get("ema_21"),
            "indicators": {k:v for k,v in (data.get("indicators") or {}).items() if "ema" in k.lower()},
            "all_keys": list(data.keys())[:20],
        }
    bridge_info = json.dumps(bridge_sample, indent=2)
except Exception as e:
    bridge_info = f"Bridge test FAILED: {e}"

question = f"""I have a KSE stock EMA 9/21 scalper system. The user reports that many stocks shown as "bullish" (EMA9 > EMA21) or "bearish" on the scalper page do NOT match what he sees on TradingView charts for the 30-minute timeframe.

SYSTEM ARCHITECTURE:
1. Bridge API (Windows PC, port 8059) fetches data from TradingView WebSocket
2. bridge_client.py (RPi) calls Bridge and parses the response
3. /dashboard/ema-live endpoint calls bridge_client.get_multi_analysis_30m() for 128 stocks
4. The endpoint compares ema9 vs ema21 to classify bullish/bearish

CURRENT DATA FROM /dashboard/ema-live:
{live_summary}

SAMPLE BULLISH STOCKS:
{sample_bull}

SAMPLE BEARISH STOCKS:
{sample_bear}

RAW BRIDGE RESPONSE FOR SAMPLE STOCKS (showing EMA-related fields):
{bridge_info}

KEY QUESTIONS:
1. The Bridge API was computing EMA(20) until today when we changed it to EMA(21). But bridge_client.py reads field "ema21" or "ema_21" or "ema20" or "ema_20". Could there be a field name mismatch where the endpoint reads the WRONG field?

2. The ema-live endpoint in server.py parses the bridge response like this:
   ema9 = float(ind.get("ema9") or ind.get("ema_9") or 0)
   ema21 = float(ind.get("ema21") or ind.get("ema_21") or ind.get("ema20") or ind.get("ema_20") or 0)
   But the bridge_client returns data in a NESTED structure. The field names depend on how bridge_client formats its response.

3. Is the issue that ema-live endpoint is reading the wrong fields from bridge_client response? What is the actual response structure from get_multi_analysis_30m()?

4. Or is the problem that Bridge API uses cached/stale data outside market hours?

Please analyze the raw bridge response structure above and tell me exactly which field names contain the EMA values, and whether the ema-live endpoint is reading them correctly."""

print(question)
