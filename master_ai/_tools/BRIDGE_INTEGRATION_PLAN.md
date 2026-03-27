# Bridge Integration Plan — Claude Code Instructions
# Date: 2026-03-25
# Task: Integrate TradingView Bridge API (Windows PC) with Master AI (RPi)

## CONTEXT
- TradingView Bridge API runs on Windows PC at http://192.168.111.156:8059
- Master AI runs on RPi at /var/lib/homeassistant/share/master_ai/
- Bridge provides: /health, /quote, /analysis, /ohlcv, /multi-analysis
- Each /analysis response is ~75KB (300 bars + indicators + S/R)
- Master AI already has stock_radar.py (128 stocks via tv_data.py websocket)
- Architecture decision: Bridge COMPLEMENTS radar, does NOT replace it

## ARCHITECTURE
- Radar (tv_data.py) = broad 128-stock scanner, always-on, lightweight
- Bridge (bridge_client.py) = deep technical analysis enrichment, selective, 10-15 symbols
- RPi-side cache with stale fallback when Bridge offline
- Compact dashboard endpoints (normalized data, not raw 75KB blobs)
- HA sensors stay summary-only (16KB limit)

## PHASE 1: Create bridge_client.py

### File: bridge_client.py (new file in master_ai root)
### Dependencies: httpx (already available or pip install)

```python
"""
TradingView Bridge API client for Master AI.
Fetches live technical analysis from Windows PC Bridge over LAN.
"""
import asyncio
import time
import logging
from typing import Optional

import httpx

logger = logging.getLogger("bridge_client")

BRIDGE_BASE_URL = "http://192.168.111.156:8059"
DEFAULT_EXCHANGE = "KSE"

# Cache TTLs (seconds)
CACHE_TTL_QUOTE = 30
CACHE_TTL_ANALYSIS = 120
CACHE_TTL_OHLCV = 300

# Circuit breaker
MAX_FAILURES = 3
COOLDOWN_SECONDS = 60


class BridgeClient:
    def __init__(self, base_url: str = BRIDGE_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._cache: dict[str, dict] = {}  # key -> {data, ts}
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._online = False
        self._last_success = None
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(connect=1.5, read=5.0, write=3.0, pool=2.0),
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
            )
        return self._client

    def _cache_get(self, key: str, ttl: int) -> Optional[dict]:
        entry = self._cache.get(key)
        if entry and (time.time() - entry["ts"]) < ttl:
            return entry["data"]
        return None

    def _cache_set(self, key: str, data: dict):
        self._cache[key] = {"data": data, "ts": time.time()}

    def _cache_get_stale(self, key: str) -> Optional[dict]:
        """Return stale cache for offline fallback."""
        entry = self._cache.get(key)
        if entry:
            return entry["data"]
        return None

    def _is_circuit_open(self) -> bool:
        if self._failure_count >= MAX_FAILURES:
            if (time.time() - self._last_failure_time) < COOLDOWN_SECONDS:
                return True
            # Cooldown expired, allow retry
            self._failure_count = 0
        return False

    async def _request(self, path: str, params: dict = None) -> Optional[dict]:
        if self._is_circuit_open():
            logger.debug("Bridge circuit breaker open, skipping request")
            return None

        try:
            client = await self._get_client()
            resp = await client.get(path, params=params or {})
            resp.raise_for_status()
            data = resp.json()
            self._failure_count = 0
            self._online = True
            self._last_success = time.time()
            return data
        except Exception as e:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count == MAX_FAILURES:
                self._online = False
                logger.warning("Bridge offline after %d failures: %s", MAX_FAILURES, e)
            else:
                logger.debug("Bridge request failed (%d/%d): %s", self._failure_count, MAX_FAILURES, e)
            return None

    # --- Public API ---

    async def health(self) -> dict:
        data = await self._request("/health")
        return data or {"status": "offline"}

    async def get_quote(self, symbol: str, exchange: str = DEFAULT_EXCHANGE, force: bool = False) -> dict:
        cache_key = f"quote:{exchange}:{symbol}"
        if not force:
            cached = self._cache_get(cache_key, CACHE_TTL_QUOTE)
            if cached:
                return {**cached, "source": "cache", "stale": False}

        data = await self._request("/quote", {"symbol": symbol, "exchange": exchange})
        if data:
            normalized = self._normalize_quote(data)
            self._cache_set(cache_key, normalized)
            return {**normalized, "source": "live", "stale": False}

        # Stale fallback
        stale = self._cache_get_stale(cache_key)
        if stale:
            return {**stale, "source": "cache", "stale": True}
        return {"symbol": symbol, "exchange": exchange, "source": "none", "stale": True, "error": "bridge_unreachable"}

    async def get_analysis(self, symbol: str, exchange: str = DEFAULT_EXCHANGE, force: bool = False) -> dict:
        cache_key = f"analysis:{exchange}:{symbol}"
        if not force:
            cached = self._cache_get(cache_key, CACHE_TTL_ANALYSIS)
            if cached:
                return {**cached, "source": "cache", "stale": False}

        data = await self._request("/analysis", {"symbol": symbol, "exchange": exchange, "interval": "1D", "bars": 300})
        if data:
            normalized = self._normalize_analysis(data)
            self._cache_set(cache_key, normalized)
            return {**normalized, "source": "live", "stale": False}

        stale = self._cache_get_stale(cache_key)
        if stale:
            return {**stale, "source": "cache", "stale": True}
        return {"symbol": symbol, "exchange": exchange, "source": "none", "stale": True, "error": "bridge_unreachable"}

    async def get_multi_analysis(self, symbols: list[str], exchange: str = DEFAULT_EXCHANGE, force: bool = False) -> dict:
        results = {}
        errors = []
        # Check cache first, only fetch uncached
        to_fetch = []
        for sym in symbols:
            if not force:
                cached = self._cache_get(f"analysis:{exchange}:{sym}", CACHE_TTL_ANALYSIS)
                if cached:
                    results[sym] = {**cached, "source": "cache", "stale": False}
                    continue
            to_fetch.append(sym)

        if to_fetch:
            data = await self._request("/multi-analysis", {
                "symbols": ",".join(to_fetch),
                "exchange": exchange,
                "interval": "1D",
                "bars": 300,
            })
            if data and "results" in data:
                for item in data["results"]:
                    sym = item.get("symbol", "").split(":")[-1]
                    normalized = self._normalize_analysis(item)
                    self._cache_set(f"analysis:{exchange}:{sym}", normalized)
                    results[sym] = {**normalized, "source": "live", "stale": False}
            else:
                # Fallback to stale cache for unfetched
                for sym in to_fetch:
                    stale = self._cache_get_stale(f"analysis:{exchange}:{sym}")
                    if stale:
                        results[sym] = {**stale, "source": "cache", "stale": True}
                    else:
                        errors.append(sym)

        return {
            "bridge_online": self._online,
            "symbols_count": len(results),
            "symbols": results,
            "errors": errors,
            "asof": self._last_success,
        }

    def get_status(self) -> dict:
        return {
            "online": self._online,
            "last_success": self._last_success,
            "failure_count": self._failure_count,
            "circuit_open": self._is_circuit_open(),
            "cached_symbols": len(self._cache),
            "base_url": self.base_url,
        }

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # --- Normalization ---

    def _normalize_quote(self, raw: dict) -> dict:
        q = raw.get("quote", raw)
        return {
            "symbol": q.get("symbol", "").split(":")[-1],
            "exchange": q.get("exchange", DEFAULT_EXCHANGE),
            "price": q.get("price") or q.get("lp"),
            "open": q.get("open") or q.get("open_price"),
            "high": q.get("high") or q.get("high_price"),
            "low": q.get("low") or q.get("low_price"),
            "prev_close": q.get("prev_close") or q.get("prev_close_price"),
            "change": q.get("change") or q.get("ch"),
            "change_pct": q.get("change_percent") or q.get("chp"),
            "volume": q.get("volume"),
            "description": q.get("description", ""),
        }

    def _normalize_analysis(self, raw: dict) -> dict:
        ind = raw.get("indicators", {})
        q = raw.get("quote", {})
        symbol_raw = raw.get("symbol", "")
        symbol = symbol_raw.split(":")[-1] if ":" in symbol_raw else symbol_raw

        price = raw.get("price") or q.get("price", 0)
        ema9 = ind.get("ema_9", 0)
        ema20 = ind.get("ema_20", 0)
        ema50 = ind.get("ema_50", 0)
        ema200 = ind.get("ema_200", 0)

        # Determine EMA stack
        if ema9 > ema20 > ema50 > ema200:
            ema_stack = "bullish"
        elif ema9 < ema20 < ema50 < ema200:
            ema_stack = "bearish"
        else:
            ema_stack = "mixed"

        # MACD state
        macd_val = ind.get("macd", 0)
        macd_sig = ind.get("macd_signal", 0)
        macd_hist = ind.get("macd_hist", 0)
        if macd_hist > 0:
            macd_state = "bullish"
        elif macd_hist < 0:
            macd_state = "bearish"
        else:
            macd_state = "neutral"

        return {
            "symbol": symbol,
            "exchange": raw.get("symbol", "").split(":")[0] if ":" in raw.get("symbol", "") else DEFAULT_EXCHANGE,
            "price": price,
            "change_pct": q.get("change_percent") or q.get("chp", 0),
            "volume": q.get("volume", 0),
            "rsi_14": round(ind.get("rsi_14", 0) or 0, 2),
            "macd": {
                "macd": round(macd_val, 4),
                "signal": round(macd_sig, 4),
                "hist": round(macd_hist, 4),
                "state": macd_state,
            },
            "ema": {
                "ema9": round(ema9, 2),
                "ema20": round(ema20, 2),
                "ema50": round(ema50, 2),
                "ema200": round(ema200, 2),
                "stack": ema_stack,
                "above_ema20": price > ema20 if ema20 else None,
                "above_ema50": price > ema50 if ema50 else None,
                "above_ema200": price > ema200 if ema200 else None,
            },
            "support": raw.get("support", [])[:3],
            "resistance": raw.get("resistance", [])[:3],
        }


# --- Module-level singleton ---
_bridge_client: Optional[BridgeClient] = None


def get_bridge_client() -> BridgeClient:
    global _bridge_client
    if _bridge_client is None:
        _bridge_client = BridgeClient()
    return _bridge_client


async def init_bridge_client():
    """Called during server lifespan startup."""
    client = get_bridge_client()
    status = await client.health()
    logger.info("Bridge client initialized: %s", status.get("status", "unknown"))
    return client
```

## PHASE 2: Add dashboard endpoints in dashboard_api.py

### Add these endpoints to dashboard_api.py:

```python
# --- Bridge Endpoints ---

@router.get("/dashboard/bridge")
async def dashboard_bridge(
    symbols: str = None,
    mode: str = "auto",  # auto|watchlist|top|portfolio
    force_refresh: bool = False,
):
    """Compact bridge analysis for dashboard. Auto-selects symbols if none specified."""
    from bridge_client import get_bridge_client
    client = get_bridge_client()
    
    if not symbols:
        # Auto-select: portfolio + watchlist + top radar
        selected = _get_bridge_candidates(mode)
    else:
        selected = [s.strip() for s in symbols.split(",") if s.strip()]

    if not selected:
        return {"status": "ok", "bridge_online": client._online, "symbols_count": 0, "symbols": {}}

    # Cap at 15 symbols
    selected = selected[:15]
    result = await client.get_multi_analysis(selected, force=force_refresh)
    return {"status": "ok", **result}


@router.get("/dashboard/bridge/{symbol}")
async def dashboard_bridge_symbol(
    symbol: str,
    exchange: str = "KSE",
    force_refresh: bool = False,
):
    """Detailed single-symbol bridge analysis."""
    from bridge_client import get_bridge_client
    client = get_bridge_client()
    analysis = await client.get_analysis(symbol, exchange, force=force_refresh)
    return {"status": "ok", **analysis}


def _get_bridge_candidates(mode: str = "auto") -> list[str]:
    """Select symbols for bridge enrichment from radar + portfolio + watchlist."""
    candidates = set()
    
    # 1. Portfolio open positions
    try:
        from journal_engine import get_open_trades
        trades = get_open_trades()
        for t in trades:
            if t.get("symbol"):
                candidates.add(t["symbol"].upper())
    except Exception:
        pass

    # 2. Radar watchlist
    try:
        from stock_radar import get_watchlist_symbols
        wl = get_watchlist_symbols()
        for s in wl[:10]:
            candidates.add(s.upper())
    except Exception:
        pass

    # 3. Top radar signals
    try:
        from stock_radar import get_top_radar_symbols
        top = get_top_radar_symbols(limit=5, direction="bullish")
        for s in top:
            candidates.add(s.upper())
        top_bear = get_top_radar_symbols(limit=3, direction="bearish")
        for s in top_bear:
            candidates.add(s.upper())
    except Exception:
        pass

    return list(candidates)[:15]
```

## PHASE 3: Wire into server.py lifespan

In server.py lifespan, add:
```python
# After other init calls
from bridge_client import init_bridge_client
await init_bridge_client()
```

## PHASE 4: HA Sensor (optional new sensor)

In configuration.yaml, add or extend:
```yaml
  - platform: rest
    name: Master AI Bridge
    resource: http://192.168.109.123:9000/dashboard/bridge
    headers:
      X-API-Key: !secret master_ai_key
    scan_interval: 180
    value_template: "{{ value_json.bridge_online | default('unknown') }}"
    json_attributes:
      - symbols_count
      - symbols
      - errors
      - asof
```

Or just extend the existing radar sensor attributes with bridge_online and bridge_enriched_count.

## EXECUTION ORDER FOR CLAUDE CODE

1. Install httpx on RPi: `pip install httpx`
2. Create bridge_client.py via patch system
3. Add /dashboard/bridge endpoints to dashboard_api.py via patch
4. Wire init_bridge_client in server.py lifespan via patch
5. Run quick_check.py
6. Run smoke_test.py
7. Test: curl http://localhost:9000/dashboard/bridge
8. Git commit
9. Optionally add HA sensor

## IMPORTANT NOTES
- Bridge PC IP: 192.168.111.156 (confirmed via ipconfig)
- RPi IP: 192.168.109.123
- Both on same /22 subnet (192.168.108.0/22)
- Bridge has no API key (internal LAN only)
- Use apply_text_patch.py for ALL Python file edits
- Run quick_check + smoke_test after every change
- Git commit before restart
