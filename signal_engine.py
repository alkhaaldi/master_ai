"""
signal_engine.py — Composite trading signal engine for Master AI.
Merges radar + bridge + journal into decision-ready signals with trade state model.

Trade State Model:
  discovery  — radar detected EMA cross, no bridge confirmation yet
  setup      — bridge confirms improving indicators (confluence >40)
  ready      — confluence >60, volume confirms, entry conditions met
  entered    — open position exists in journal
  manage     — tracking stop/target (entered + bridge monitoring)
  closed     — archived in journal
"""
import logging
import time
import time as _time
from datetime import datetime

logger = logging.getLogger("signal_engine")

# --- Context injection (same pattern as dashboard_api) ---
_ctx = {}


def init_signal_context(**kwargs):
    """Called by server.py lifespan to inject shared state."""
    _ctx.update(kwargs)


# --- Brain-learned thresholds cache ---
_cached_thresholds = None
_thresholds_ts     = 0
_THRESHOLDS_TTL    = 300  # refresh every 5 min

# --- Bridge result cache (avoids re-fetching on every request) ---
import threading as _threading
_bridge_cache: dict = {}
_bridge_cache_ts: dict = {}
_bridge_daily_lock = _threading.Lock()  # separate lock for daily fetch
_bridge_30m_lock   = _threading.Lock()  # separate lock for 30m fetch
_BRIDGE_DAILY_TTL = 300  # 5 min cache for daily signals
_BRIDGE_30M_TTL   = 120  # 2 min cache for 30m signals


def _get_thresholds() -> dict:
    """Get brain-learned thresholds with 5-min cache."""
    global _cached_thresholds, _thresholds_ts
    now = _time.time()
    if _cached_thresholds and (now - _thresholds_ts) < _THRESHOLDS_TTL:
        return _cached_thresholds
    try:
        from trading_brain import get_optimal_thresholds
        _cached_thresholds = get_optimal_thresholds()
        _thresholds_ts = now
    except Exception:
        _cached_thresholds = {
            "ready_min_score": 60, "ready_min_vol": 1.2,
            "setup_min_score": 40, "avoid_max_score": 30,
            "watch_min_score": 50, "source": "fallback",
        }
    return _cached_thresholds


# --- Verdict labels (Arabic) ---
_VERDICT_MAP = {
    "buy":     "\u0634\u0631\u0627\u0621",       # شراء
    "watch":   "\u0645\u0631\u0627\u0642\u0628\u0629",     # مراقبة
    "review":  "\u0645\u0631\u0627\u062c\u0639\u0629",     # مراجعة
    "avoid":   "\u062a\u062c\u0646\u0628",       # تجنب
    "neutral": "\u062d\u064a\u0627\u062f",       # حياد
}


def build_signals() -> dict:
    """Main entry: build composite signals from radar + bridge + journal."""
    now = datetime.now()
    result = {
        "market_open": _is_market_open_safe(),
        "bridge_online": False,
        "bridge_cached_count": 0,
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "decision_card": None,
        "opportunities": [],
        "open_positions": [],
        "signal_counts": {"discovery": 0, "setup": 0, "ready": 0, "entered": 0, "manage": 0},
        "thresholds": _get_thresholds(),
    }

    # 1. Get open trades from journal
    open_trades = _get_open_trades_safe()
    open_syms = {t["symbol"].upper(): t for t in open_trades if t.get("symbol")}

    # 2. Get bridge multi-analysis (already cached, fast)
    bridge_data = _get_bridge_data_safe()
    result["bridge_online"] = bridge_data.get("bridge_online", False)
    result["bridge_cached_count"] = bridge_data.get("symbols_count", 0)
    bridge_symbols = bridge_data.get("symbols", {})

    # 3. Get radar watchlist for discovery context
    radar_syms = _get_radar_watchlist_safe()

    # 4. Build signal for each bridge-enriched symbol
    signals = []
    for sym, bd in bridge_symbols.items():
        sym_upper = sym.upper()
        trade = open_syms.get(sym_upper)
        radar_entry = radar_syms.get(sym_upper)

        state = _assign_trade_state(sym_upper, bd, radar_entry, trade)
        if state is None:
            continue

        verdict_key = _compute_verdict(bd, state)
        verdict = _VERDICT_MAP.get(verdict_key, verdict_key)
        confluence = _extract_confluence(bd)

        sig = {
            "symbol": sym_upper,
            "name_ar": (trade or {}).get("name_ar", ""),
            "price": bd.get("price", 0),
            "change_pct": round(bd.get("change_pct", 0) or 0, 2),
            "verdict": verdict,
            "verdict_key": verdict_key,
            "trade_state": state,
            "confluence_score": confluence.get("score", 0),
            "ema_state": (bd.get("ema") or {}).get("stack", ""),
            "rsi_14": bd.get("rsi_14", 0),
            "macd_state": (bd.get("macd") or {}).get("state", ""),
            "macd_momentum": (bd.get("signals") or {}).get("macd_momentum", ""),
            "adx": bd.get("adx"),
            "vol_ratio": bd.get("vol_ratio"),
            "support": (bd.get("support") or [None])[0],
            "resistance": (bd.get("resistance") or [None])[0],
            "atr_14": bd.get("atr_14"),
            "bb_squeeze": (bd.get("bb") or {}).get("squeeze"),
            "stoch_k": (bd.get("stoch_rsi") or {}).get("k"),
            "rsi_divergence": (bd.get("signals") or {}).get("rsi_divergence"),
            "ema_cross": (bd.get("signals") or {}).get("ema_cross"),
            "confluence_detail": confluence,
            "source": bd.get("source", ""),
            "stale": bd.get("stale", False),
        }
        signals.append(sig)

        # Count states
        if state in result["signal_counts"]:
            result["signal_counts"][state] += 1

    # Sort by confluence score descending
    signals.sort(key=lambda s: s.get("confluence_score", 0), reverse=True)

    # 5. Decision card = top signal (highest confluence)
    if signals:
        result["decision_card"] = signals[0]

    # 6. Opportunities = ALL non-entered signals, sorted by confluence
    result["opportunities"] = [
        s for s in signals if s["trade_state"] not in ("entered", "manage")
    ]

    # 7. All signals for Signals page full indicator matrix
    result["all_signals"] = signals

    # 8. Open positions with live P&L
    for sym, trade in open_syms.items():
        bd = bridge_symbols.get(sym, {})
        entry_price = trade.get("entry_price", 0)
        current_price = bd.get("price") or entry_price
        pnl_pct = ((current_price / entry_price) - 1) * 100 if entry_price else 0
        qty = trade.get("quantity", 0)
        pnl_kwd = ((current_price - entry_price) * qty) / 1000 if entry_price else 0

        state = "manage" if sym in bridge_symbols else "entered"

        result["open_positions"].append({
            "symbol": sym,
            "name_ar": trade.get("name_ar", ""),
            "entry": entry_price,
            "current": current_price,
            "pnl_pct": round(pnl_pct, 2),
            "pnl_kwd": round(pnl_kwd, 3),
            "state": state,
            "quantity": qty,
            "entry_date": trade.get("entry_date", ""),
            "id": trade.get("id"),
        })

    # 9. Stop Loss alerts for open positions
    for pos in result["open_positions"]:
        trade_data = open_syms.get(pos["symbol"], {})
        stop = trade_data.get("stop_loss")
        if stop and pos["current"] and float(pos["current"]) <= float(stop):
            pos["stop_hit"] = True
            pos["stop_alert"] = f"\u26a0\ufe0f {pos['symbol']} \u0648\u0635\u0644 \u0627\u0644\u0633\u062a\u0648\u0628 {stop}! \u0627\u0644\u0633\u0639\u0631: {pos['current']}"
        else:
            pos["stop_hit"] = False
            pos["stop_alert"] = None

    return result


# --- Trade State Assignment ---

def _assign_trade_state(symbol: str, bridge: dict, radar: dict, trade: dict) -> str:
    """Assign trade state based on rules."""
    if trade:
        # Open position exists
        if symbol in _get_bridge_symbols_set():
            return "manage"
        return "entered"

    confluence = _extract_confluence(bridge)
    score = confluence.get("score", 0)
    vol   = bridge.get("vol_ratio") or 0

    t = _get_thresholds()  # Brain-learned thresholds

    if score >= t["ready_min_score"] and vol > t["ready_min_vol"]:
        return "ready"
    if score >= t["setup_min_score"]:
        return "setup"
    if radar:
        return "discovery"
    return None


def _compute_verdict(bridge: dict, state: str) -> str:
    """Compute verdict label based on bridge data + state + market regime."""
    confluence = _extract_confluence(bridge)
    score     = confluence.get("score", 0)
    direction = confluence.get("direction", "")
    regime    = confluence.get("regime", "unknown")
    momentum  = (bridge.get("signals") or {}).get("macd_momentum", "")

    t = _get_thresholds()  # Brain-learned thresholds

    # Regime adjustment: ranging market → raise bar (more false signals)
    regime_penalty = 0
    if regime == "ranging":
        regime_penalty = 10
    elif regime == "trending":
        regime_penalty = -5

    adjusted_watch = t["watch_min_score"] + regime_penalty
    adjusted_avoid = t["avoid_max_score"] + regime_penalty

    if state == "ready" and "bullish" in direction:
        if regime == "ranging" and score < 75:
            return "watch"  # ranging market: downgrade ready→watch
        return "buy"
    if state == "setup" and score >= adjusted_watch:
        return "watch"
    if state in ("entered", "manage") and "decelerating" in momentum:
        return "review"
    if score < adjusted_avoid or "strong_bearish" in direction:
        return "avoid"
    if "bearish" in direction and regime == "trending":
        return "avoid"  # bearish in trending market is more meaningful
    return "neutral"


def _extract_confluence(bridge: dict) -> dict:
    """Extract confluence — uses brain's adaptive weights if available, else raw bridge confluence."""
    try:
        from trading_brain import get_adjusted_confluence
        adjusted = get_adjusted_confluence(bridge)
        if adjusted and adjusted.get("score", 0) > 0:
            return adjusted
    except Exception:
        pass
    # Fallback: raw bridge confluence
    signals = bridge.get("signals") or {}
    conf = signals.get("confluence")
    if isinstance(conf, dict):
        return conf
    return {"score": 0, "direction": "unknown", "bullish": 0, "bearish": 0, "total": 0}


# --- Safe data accessors ---

def _is_market_open_safe() -> bool:
    try:
        from tv_data import _is_market_open
        return _is_market_open()
    except Exception:
        return False


def _get_open_trades_safe() -> list:
    try:
        fn = _ctx.get("get_open_trades")
        if fn:
            return fn()
        from journal_engine import get_open_trades
        return get_open_trades()
    except Exception as e:
        logger.debug("Failed to get open trades: %s", e)
        return []


def _get_bridge_data_safe() -> dict:
    """Get bridge multi-analysis for candidate symbols (5-min module-level cache).
    Fire-and-forget: triggers background fetch, always returns stale immediately."""
    global _bridge_cache, _bridge_cache_ts
    now = _time.time()
    if _bridge_cache.get("daily") and (now - _bridge_cache_ts.get("daily", 0)) < _BRIDGE_DAILY_TTL:
        return _bridge_cache["daily"]
    # If another fetch is already running, return stale immediately
    if not _bridge_daily_lock.acquire(blocking=False):
        return _bridge_cache.get("daily") or {"bridge_online": False, "symbols_count": 0, "symbols": {}}
    # Got the lock — start background fetch thread, return stale immediately
    import threading as _thr

    def _fetch_background():
        try:
            from bridge_client import BridgeClient, BRIDGE_BASE_URL
            import asyncio
            candidates = set()
            for t in _get_open_trades_safe():
                if t.get("symbol"):
                    candidates.add(t["symbol"].upper())
            try:
                from stock_radar import get_watchlist
                wl = get_watchlist()
                for item in wl:
                    sym = item.get("symbol", "")
                    if sym:
                        candidates.add(sym.upper())
            except Exception:
                pass
            if not candidates:
                return
            symbols = list(candidates)
            async def _fetch():
                client = BridgeClient(BRIDGE_BASE_URL)
                try:
                    return await client.get_multi_analysis(symbols)
                finally:
                    await client.close()
            result = asyncio.run(_fetch())
            _bridge_cache["daily"] = result
            _bridge_cache_ts["daily"] = _time.time()
            logger.info("Bridge daily cache refreshed: %d symbols", result.get("symbols_count", 0))
        except Exception as e:
            logger.warning("Bridge daily fetch failed: %s", e)
        finally:
            _bridge_daily_lock.release()

    _thr.Thread(target=_fetch_background, daemon=True).start()
    return _bridge_cache.get("daily") or {"bridge_online": False, "symbols_count": 0, "symbols": {}}


def _get_bridge_data_30m_safe() -> dict:
    """Get bridge 30m analysis for all watchlist symbols (2-min module-level cache).
    Fire-and-forget: triggers background fetch, always returns stale immediately."""
    global _bridge_cache, _bridge_cache_ts
    now = _time.time()
    if _bridge_cache.get("30m") and (now - _bridge_cache_ts.get("30m", 0)) < _BRIDGE_30M_TTL:
        return _bridge_cache["30m"]
    if not _bridge_30m_lock.acquire(blocking=False):
        return _bridge_cache.get("30m") or {"bridge_online": False, "symbols_count": 0, "symbols": {}}
    import threading as _thr

    def _fetch_background():
        try:
            from bridge_client import BridgeClient, BRIDGE_BASE_URL
            import asyncio
            candidates = set()
            for t in _get_open_trades_safe():
                if t.get("symbol"):
                    candidates.add(t["symbol"].upper())
            try:
                from stock_radar import get_watchlist
                wl = get_watchlist()
                for item in wl:
                    sym = item.get("symbol", "")
                    if sym:
                        candidates.add(sym.upper())
            except Exception:
                pass
            if not candidates:
                return
            symbols = list(candidates)
            async def _fetch():
                client = BridgeClient(BRIDGE_BASE_URL)
                try:
                    return await client.get_multi_analysis_30m(symbols)
                finally:
                    await client.close()
            result = asyncio.run(_fetch())
            _bridge_cache["30m"] = result
            _bridge_cache_ts["30m"] = _time.time()
            logger.info("Bridge 30m cache refreshed: %d symbols", result.get("symbols_count", 0))
        except Exception as e:
            logger.warning("Bridge 30m fetch failed: %s", e)
        finally:
            _bridge_30m_lock.release()

    _thr.Thread(target=_fetch_background, daemon=True).start()
    return _bridge_cache.get("30m") or {"bridge_online": False, "symbols_count": 0, "symbols": {}}


def build_signals_30m() -> dict:
    """Build 30m signals from Bridge — uses Brain weights."""
    now = datetime.now()
    result = {
        "timeframe": "30m",
        "market_open": _is_market_open_safe(),
        "bridge_online": False,
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "signals": [],
        "thresholds": _get_thresholds(),
    }

    bridge_data = _get_bridge_data_30m_safe()
    result["bridge_online"] = bridge_data.get("bridge_online", False)
    bridge_symbols = bridge_data.get("symbols", {})

    open_trades = _get_open_trades_safe()
    open_syms = {t["symbol"].upper(): t for t in open_trades if t.get("symbol")}

    signals = []
    for sym, bd in bridge_symbols.items():
        sym_upper = sym.upper()
        trade = open_syms.get(sym_upper)

        confluence = _extract_confluence(bd)
        score = confluence.get("score", 0)
        direction = confluence.get("direction", "")
        regime = confluence.get("regime", "unknown")

        t = _get_thresholds()

        if trade:
            state = "manage"
        elif score >= t["ready_min_score"] and (bd.get("vol_ratio") or 0) > t["ready_min_vol"]:
            state = "ready"
        elif score >= t["setup_min_score"]:
            state = "setup"
        else:
            state = "discovery"

        regime_penalty = 10 if regime == "ranging" else -5 if regime == "trending" else 0
        adjusted_watch = t["watch_min_score"] + regime_penalty
        adjusted_avoid = t["avoid_max_score"] + regime_penalty

        if state == "ready" and "bullish" in direction:
            if regime == "ranging" and score < 75:
                verdict_key = "watch"
            else:
                verdict_key = "buy"
        elif state == "setup" and score >= adjusted_watch:
            verdict_key = "watch"
        elif score < adjusted_avoid or "strong_bearish" in direction:
            verdict_key = "avoid"
        elif "bearish" in direction and regime != "ranging":
            verdict_key = "avoid"
        else:
            verdict_key = "neutral"

        verdict = _VERDICT_MAP.get(verdict_key, verdict_key)

        sig = {
            "symbol": sym_upper,
            "name_ar": (trade or {}).get("name_ar", bd.get("description", "")),
            "price": bd.get("price", 0),
            "change_pct": round(bd.get("change_pct", 0) or 0, 2),
            "verdict": verdict,
            "verdict_key": verdict_key,
            "trade_state": state,
            "confluence_score": score,
            "ema_state": (bd.get("ema") or {}).get("stack", ""),
            "rsi_14": bd.get("rsi_14", 0),
            "macd_state": (bd.get("macd") or {}).get("state", ""),
            "macd_momentum": (bd.get("signals") or {}).get("macd_momentum", ""),
            "adx": bd.get("adx"),
            "vol_ratio": bd.get("vol_ratio"),
            "support": (bd.get("support") or [None])[0],
            "resistance": (bd.get("resistance") or [None])[0],
            "atr_14": bd.get("atr_14"),
            "bb_squeeze": (bd.get("bb") or {}).get("squeeze"),
            "stoch_k": (bd.get("stoch_rsi") or {}).get("k"),
            "rsi_divergence": (bd.get("signals") or {}).get("rsi_divergence"),
            "ema_cross": (bd.get("signals") or {}).get("ema_cross"),
            "confluence_detail": confluence,
            "timeframe": "30m",
            "source": bd.get("source", ""),
            "stale": bd.get("stale", False),
        }
        signals.append(sig)

    signals.sort(key=lambda s: s.get("confluence_score", 0), reverse=True)
    result["signals"] = signals
    result["count"] = len(signals)
    return result


def _get_radar_watchlist_safe() -> dict:
    """Get radar watchlist as {SYMBOL: dict}."""
    try:
        from stock_radar import get_watchlist
        wl = get_watchlist()
        return {item["symbol"].upper(): item for item in wl if item.get("symbol")}
    except Exception:
        return {}


def _get_bridge_symbols_set() -> set:
    """Get set of symbols currently in bridge cache."""
    try:
        from bridge_client import get_bridge_client
        client = get_bridge_client()
        return {k.split(":")[-1] for k in client._cache if k.startswith("analysis:")}
    except Exception:
        return set()
