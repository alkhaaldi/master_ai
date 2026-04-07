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

BRIDGE_BASE_URL = "http://192.168.111.159:8059"
DEFAULT_EXCHANGE = "KSE"

# Cache TTLs (seconds)
CACHE_TTL_QUOTE = 30
CACHE_TTL_ANALYSIS = 120
CACHE_TTL_OHLCV = 300

# Circuit breaker
MAX_FAILURES = 15
COOLDOWN_SECONDS = 60


class BridgeClient:
    def __init__(self, base_url: str = BRIDGE_BASE_URL, health_hub=None):
        self.base_url = base_url.rstrip("/")
        self._cache: dict[str, dict] = {}  # key -> {data, ts}
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._online = False
        self._last_success = None
        self._client: Optional[httpx.AsyncClient] = None
        self._health_hub = health_hub

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(connect=2.0, read=60.0, write=3.0, pool=2.0),
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
            if self._health_hub:
                self._health_hub.mark_up("bridge", details={"circuit_reset": True})
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
            if self._health_hub:
                self._health_hub.mark_up("bridge", details={"cached_symbols": len(self._cache)})
            return data
        except Exception as e:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count == MAX_FAILURES:
                self._online = False
                logger.warning("Bridge offline after %d failures: %s", MAX_FAILURES, e)
                if self._health_hub:
                    self._health_hub.mark_down("bridge", reason=f"offline after {MAX_FAILURES} failures: {e}")
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
        """Get daily analysis for multiple symbols via concurrent individual /analysis calls."""
        results = {}
        errors = []
        # Serve from cache first
        to_fetch = []
        for sym in symbols:
            if not force:
                cached = self._cache_get(f"analysis:{exchange}:{sym}", CACHE_TTL_ANALYSIS)
                if cached:
                    results[sym] = {**cached, "source": "cache", "stale": False}
                    continue
            to_fetch.append(sym)

        # Fetch uncached symbols concurrently in batches of 5
        BATCH_SIZE = 5
        for i in range(0, len(to_fetch), BATCH_SIZE):
            batch = to_fetch[i:i + BATCH_SIZE]
            tasks = [
                self._request("/analysis", {"symbol": sym, "exchange": exchange, "interval": "1D", "bars": 300})
                for sym in batch
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for sym, data in zip(batch, responses):
                if isinstance(data, Exception) or data is None:
                    stale = self._cache_get_stale(f"analysis:{exchange}:{sym}")
                    if stale:
                        results[sym] = {**stale, "source": "cache", "stale": True}
                    else:
                        errors.append(sym)
                else:
                    normalized = self._normalize_analysis(data)
                    self._cache_set(f"analysis:{exchange}:{sym}", normalized)
                    results[sym] = {**normalized, "source": "live", "stale": False}

        return {
            "bridge_online": self._online,
            "symbols_count": len(results),
            "symbols": results,
            "errors": errors,
            "asof": self._last_success,
        }

    async def get_analysis_30m(self, symbol: str, exchange: str = DEFAULT_EXCHANGE, force: bool = False) -> dict:
        """Get 30m analysis for a symbol."""
        cache_key = f"analysis_30m:{exchange}:{symbol}"
        if not force:
            cached = self._cache_get(cache_key, 60)  # 60s cache for 30m data
            if cached:
                return {**cached, "source": "cache", "stale": False}

        data = await self._request("/analysis", {
            "symbol": symbol, "exchange": exchange,
            "interval": "30", "bars": 60
        })
        if data:
            normalized = self._normalize_analysis(data)
            normalized["timeframe"] = "30m"
            self._cache_set(cache_key, normalized)
            return {**normalized, "source": "live", "stale": False}

        stale = self._cache_get_stale(cache_key)
        if stale:
            return {**stale, "source": "cache", "stale": True}
        return {"symbol": symbol, "exchange": exchange, "source": "none", "stale": True, "error": "bridge_unreachable"}

    async def get_multi_analysis_30m(self, symbols: list[str], exchange: str = DEFAULT_EXCHANGE) -> dict:
        """Get 30m analysis for multiple symbols via concurrent individual calls."""
        results = {}
        errors = []

        # Serve from cache first (60s TTL)
        to_fetch = []
        for sym in symbols:
            cached = self._cache_get(f"analysis_30m:{exchange}:{sym}", 60)
            if cached:
                results[sym] = {**cached, "source": "cache", "stale": False}
            else:
                to_fetch.append(sym)

        # Fetch uncached symbols concurrently in batches of 5
        BATCH_SIZE = 5
        for i in range(0, len(to_fetch), BATCH_SIZE):
            batch = to_fetch[i:i + BATCH_SIZE]
            tasks = [
                self._request("/analysis", {"symbol": sym, "exchange": exchange, "interval": "30", "bars": 60})
                for sym in batch
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for sym, data in zip(batch, responses):
                if isinstance(data, Exception) or data is None:
                    stale = self._cache_get_stale(f"analysis_30m:{exchange}:{sym}")
                    if stale:
                        results[sym] = {**stale, "source": "cache", "stale": True}
                    else:
                        errors.append(sym)
                else:
                    normalized = self._normalize_analysis(data)
                    normalized["timeframe"] = "30m"
                    self._cache_set(f"analysis_30m:{exchange}:{sym}", normalized)
                    results[sym] = {**normalized, "source": "live", "stale": False}

        return {
            "bridge_online": self._online,
            "symbols_count": len(results),
            "symbols": results,
            "errors": errors,
            "timeframe": "30m",
        }

    async def get_multi_analysis_30m_bulk(self, symbols: list[str], exchange: str = DEFAULT_EXCHANGE, batch_size: int = 25, delay: float = 1.0) -> dict:
        """Get 30m analysis for many symbols via Bridge /multi-analysis (single WebSocket per batch).

        Unlike get_multi_analysis_30m which opens one HTTP request per symbol,
        this uses /multi-analysis which fetches all symbols in a batch over a
        single TradingView WebSocket — avoids HTTP 429 rate limits.
        """
        results = {}
        errors = []

        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            syms_param = ",".join(batch)
            data = await self._request("/multi-analysis", {
                "symbols": syms_param, "exchange": exchange,
                "interval": "30", "bars": 60,
            })
            if data is None:
                errors.extend(batch)
                continue

            for item in data.get("results", []):
                raw_sym = item.get("symbol", "")
                sym = raw_sym.split(":")[-1] if ":" in raw_sym else raw_sym
                normalized = self._normalize_analysis(item)
                normalized["timeframe"] = "30m"
                self._cache_set(f"analysis_30m:{exchange}:{sym}", normalized)
                results[sym] = {**normalized, "source": "live", "stale": False}

            for err in data.get("errors", []):
                err_sym = err.get("symbol", "")
                errors.append(err_sym.split(":")[-1] if ":" in err_sym else err_sym)

            # Delay between batches to be gentle on TradingView
            if i + batch_size < len(symbols):
                await asyncio.sleep(delay)

        return {
            "bridge_online": self._online,
            "symbols_count": len(results),
            "symbols": results,
            "errors": errors,
            "timeframe": "30m",
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
        ema21 = ind.get("ema_21") or ind.get("ema_20") or 0
        ema50 = ind.get("ema_50", 0)
        ema200 = ind.get("ema_200", 0)

        # Determine EMA stack
        if ema9 > ema21 > ema50 > ema200:
            ema_stack = "bullish"
        elif ema9 < ema21 < ema50 < ema200:
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

        # Pro indicators (graceful — None if Bridge hasn't been upgraded yet)
        atr_14 = ind.get("atr_14")
        adx_val = ind.get("adx")
        bb_squeeze = ind.get("bb_squeeze")
        bb_bandwidth = ind.get("bb_bandwidth")
        vol_ratio = ind.get("vol_ratio")
        stoch_k = ind.get("stoch_k")
        stoch_d = ind.get("stoch_d")

        # Signals dict (computed by Bridge compute_signals)
        raw_signals = raw.get("signals", {})

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
                "ema21": round(ema21, 2),
                "ema20": round(ema21, 2),  # backward compat
                "ema50": round(ema50, 2),
                "ema200": round(ema200, 2),
                "stack": ema_stack,
                "above_ema21": price > ema21 if ema21 else None,
                "above_ema20": price > ema21 if ema21 else None,  # backward compat
                "above_ema50": price > ema50 if ema50 else None,
                "above_ema200": price > ema200 if ema200 else None,
            },
            "atr_14": round(atr_14, 2) if atr_14 is not None else None,
            "adx": round(adx_val, 1) if adx_val is not None else None,
            "bb": {
                "squeeze": bb_squeeze,
                "bandwidth": round(bb_bandwidth, 2) if bb_bandwidth is not None else None,
            },
            "stoch_rsi": {
                "k": round(stoch_k, 1) if stoch_k is not None else None,
                "d": round(stoch_d, 1) if stoch_d is not None else None,
            },
            "vol_ratio": round(vol_ratio, 2) if vol_ratio is not None else None,
            "signals": {
                "rsi_divergence": raw_signals.get("rsi_divergence"),
                "macd_momentum": raw_signals.get("macd_momentum"),
                "ema_cross": raw_signals.get("ema_cross"),
                "confluence": raw_signals.get("confluence"),
            },
            "support": raw.get("support", [])[:3],
            "resistance": raw.get("resistance", [])[:3],
        }


# --- Module-level singleton ---
_bridge_client: Optional[BridgeClient] = None


def get_bridge_client(health_hub=None) -> BridgeClient:
    global _bridge_client
    if _bridge_client is None:
        _bridge_client = BridgeClient(health_hub=health_hub)
    elif health_hub and not _bridge_client._health_hub:
        _bridge_client._health_hub = health_hub
    return _bridge_client


async def init_bridge_client(health_hub=None):
    """Called during server lifespan startup."""
    client = get_bridge_client(health_hub=health_hub)
    status = await client.health()
    logger.info("Bridge client initialized: %s", status.get("status", "unknown"))
    return client
