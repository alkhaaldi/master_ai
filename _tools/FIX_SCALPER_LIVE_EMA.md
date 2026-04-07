# FIX: Scalper Page — Real-Time EMA State
# Date: 2026-03-31
# Problem: ema-active reads from stock_radar_state.last_signal which only stores CROSS events.
#          68/128 stocks have no signal. Old signals (Mar 15-18) show as "currently bullish".
#          User checked TradingView and confirms data doesn't match reality.
#
# Solution: New endpoint that reads LIVE EMA9/EMA21 from Bridge API for ALL 128 stocks.
# Executor: Claude Code on RPi

## The Problem in Detail

1. `stock_radar_state.last_signal` = the LAST cross event, NOT current position
2. A stock showing "bullish_cross" from March 18 may have crossed bearish on March 19
   but the radar missed it (service was restarting, or stock wasn't in watchlist then)
3. 68 out of 128 stocks have ZERO signal recorded
4. After service restart, `_prev_ema` dict is empty → first poll cycle never detects cross

## The Fix — New Endpoint: GET /dashboard/ema-live

This endpoint should:
1. Call Bridge API `get_multi_analysis_30m()` for all 128 KSE stocks
2. For each stock, compare `ema_9` vs `ema_21` (or `ema_20` fallback)
3. Return the CURRENT position (not cross history):
   - `above`: EMA9 > EMA21 (bullish position)
   - `below`: EMA9 < EMA21 (bearish position)
   - `touching`: |EMA9 - EMA21| < 0.1% (about to cross)

### Implementation in server.py or dashboard_api.py:

```python
@app.get("/dashboard/ema-live")
async def dashboard_ema_live():
    """Live EMA 9/21 state for ALL 128 KSE stocks from Bridge API."""
    from bridge_client import BridgeClient, BRIDGE_BASE_URL
    from tv_data import KSE_STOCKS
    import asyncio

    symbols = list(KSE_STOCKS.keys())

    try:
        client = BridgeClient(BRIDGE_BASE_URL)
        try:
            data = await client.get_multi_analysis_30m(symbols)
        finally:
            await client.close()
    except Exception as e:
        return {"error": str(e), "bridge_online": False}

    bridge_symbols = data.get("symbols", {})

    bullish = []
    bearish = []
    touching = []

    for sym, bd in bridge_symbols.items():
        ind = bd if isinstance(bd, dict) else {}
        ema9 = float(ind.get("ema9") or ind.get("ema_9") or 0)
        ema21 = float(ind.get("ema21") or ind.get("ema_21") or ind.get("ema20") or ind.get("ema_20") or 0)
        price = float(bd.get("price") or 0)
        rsi = bd.get("rsi_14") or (ind.get("indicators") or {}).get("rsi_14")
        vol_ratio = bd.get("vol_ratio") or (ind.get("indicators") or {}).get("vol_ratio")

        if not ema9 or not ema21:
            continue

        gap_pct = abs(ema9 - ema21) / ema21 * 100

        entry = {
            "symbol": sym,
            "name_ar": KSE_STOCKS.get(sym, sym),
            "price": price,
            "ema9": round(ema9, 3),
            "ema21": round(ema21, 3),
            "gap_pct": round(gap_pct, 3),
            "rsi": rsi,
            "vol_ratio": vol_ratio,
        }

        if gap_pct < 0.1:
            entry["status"] = "touching"
            touching.append(entry)
        elif ema9 > ema21:
            entry["status"] = "above"
            bullish.append(entry)
        else:
            entry["status"] = "below"
            bearish.append(entry)

    # Sort by gap_pct (closest to cross first for touching, furthest for bull/bear)
    bullish.sort(key=lambda x: x["gap_pct"])
    bearish.sort(key=lambda x: x["gap_pct"])
    touching.sort(key=lambda x: x["gap_pct"])

    from datetime import datetime
    return {
        "bridge_online": data.get("bridge_online", False),
        "total_checked": len(bridge_symbols),
        "bullish_count": len(bullish),
        "bearish_count": len(bearish),
        "touching_count": len(touching),
        "bullish": bullish,
        "bearish": bearish,
        "touching": touching,
        "timestamp": datetime.utcnow().isoformat(),
    }
```

### IMPORTANT NOTES for Claude Code:
- Bridge API is on Windows PC at 192.168.111.158:8059
- bridge_client.py already has `get_multi_analysis_30m()` method
- The response format from bridge_client may nest indicators differently
  → check the actual response structure before parsing
- This endpoint will be SLOW (~30-60 seconds for 128 stocks) during market hours
  → consider caching for 2-3 minutes
- During off-hours, Bridge may timeout → handle gracefully
- Add "/dashboard/ema-live" to OPEN_PATHS

### After adding the endpoint:
1. python3 -c "import ast; ast.parse(open('server.py').read()); print('OK')"
2. python3 -c "import server; print('IMPORT OK')"  (or quick_check.py)
3. sudo systemctl restart master-ai.service
4. curl localhost:9000/dashboard/ema-live
5. git add server.py && git commit -m "ema-live: real-time EMA state from Bridge"

### Phase 2 (claude.ai does after):
Update scalper.html to:
- Tab "صاعدة حالياً" reads from /dashboard/ema-live (bullish[])
- Tab "قريبة من التقاطع" reads from /dashboard/ema-live (touching[])
- Keep "الكل" tab reading from /dashboard/ema-crosses (history)
