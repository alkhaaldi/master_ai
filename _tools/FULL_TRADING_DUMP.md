# Master AI — Full Trading System Dump
# Generated for Gemini Pro review
# Files from: /home/pi/master_ai/

================================================================================
# SECTION 1: PYTHON TRADING LOGIC
================================================================================


############################################################
# FILE: signal_engine.py (748 lines)
############################################################

```python
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


# --- Phase 3: Scalping Mode ---
SCALPING_MODE = True  # Feature flag — True=scalping logic for 30m, False=original

SCALPING_WEIGHTS = {
    "volume_surge": 1.15,   # 65% hit rate from Brain data
    "adx_strong":   1.13,   # 63% hit rate
    "stoch_signal": 1.05,   # 55% hit rate
    "vwap_aligned": 1.20,   # mandatory — price must be above VWAP
}
_SCALP_MAX = sum(SCALPING_WEIGHTS.values())  # 4.53


def scalping_confluence(sig: dict) -> dict:
    """
    Compute scalping-specific confluence.
    Uses ONLY Volume + ADX + Stoch + VWAP.
    RSI/MACD/EMA crossover excluded (low hit rates from Brain analysis).

    Args: sig dict with vol_ratio, adx, stoch_k, stoch_d, price_vs_vwap
    Returns: {confluence_pct, action, factors, reason}
    """
    score = 0.0
    factors = []

    # Mandatory: VWAP
    if sig.get("price_vs_vwap") != "above":
        return {
            "confluence_pct": 0, "action": "NO_ENTRY",
            "factors": [], "reason": "Price below VWAP",
        }
    score += SCALPING_WEIGHTS["vwap_aligned"]
    factors.append("VWAP\u2713")

    # Volume Surge (>= 3x average)
    vol = sig.get("vol_ratio") or 0
    if vol >= 3.0:
        score += SCALPING_WEIGHTS["volume_surge"]
        factors.append(f"VOL:{vol:.1f}x")

    # ADX >= 25 (trending)
    adx = sig.get("adx") or 0
    if adx >= 25:
        score += SCALPING_WEIGHTS["adx_strong"]
        factors.append(f"ADX:{adx:.0f}")

    # Stochastic: K > D and not overbought
    stoch_k = sig.get("stoch_k") or 0
    stoch_d = sig.get("stoch_d") or 0
    if stoch_k > stoch_d and stoch_k < 80:
        score += SCALPING_WEIGHTS["stoch_signal"]
        factors.append(f"STOCH:{stoch_k:.0f}")

    confluence_pct = round((score / _SCALP_MAX) * 100, 1) if _SCALP_MAX > 0 else 0

    if confluence_pct >= 75:
        action = "STRONG_BUY"
    elif confluence_pct >= 50:
        action = "BUY"
    else:
        action = "WATCH"

    return {
        "confluence_pct": confluence_pct,
        "action": action,
        "factors": factors,
        "reason": None,
    }


# --- Phase 4: Scalping Exit Rules ---

def calculate_scalping_stop(entry_price: float, candle_low: float, ema21: float) -> dict:
    """
    Scalping stop loss — tightest of:
    1. Current candle low
    2. EMA 21
    3. 0.5% max below entry
    """
    if not entry_price or entry_price <= 0:
        return {"stop_loss": 0, "target": 0, "risk_pct": 0, "reward_pct": 0,
                "risk_reward": 0, "stop_type": "error"}

    max_stop = entry_price * 0.995  # 0.5% max

    valid_stops = [s for s in [candle_low, ema21, max_stop]
                   if s and s > 0 and s < entry_price]

    stop = max(valid_stops) if valid_stops else max_stop
    risk = abs(entry_price - stop)
    risk_pct = (risk / entry_price * 100) if entry_price > 0 else 0
    target = entry_price + risk * 1.5  # 1.5R reward

    if stop == candle_low:
        stype = "candle_low"
    elif stop == ema21:
        stype = "ema21"
    else:
        stype = "max_0.5pct"

    return {
        "stop_loss": round(stop, 3),
        "target": round(target, 3),
        "risk_pct": round(risk_pct, 2),
        "reward_pct": round(risk_pct * 1.5, 2),
        "risk_reward": 1.5,
        "stop_type": stype,
    }


def check_scalping_exit(bars_since_entry: int, current_pnl_pct: float,
                        current_close: float, ema9: float) -> dict:
    """
    Exit rules for scalping:
    1. 3 bars with no profit → TIMEOUT
    2. Close below EMA 9 → TREND BREAK
    """
    exit_signal = False
    exit_reason = None

    if bars_since_entry >= 3 and current_pnl_pct <= 0:
        exit_signal = True
        exit_reason = "TIMEOUT_3BARS"
    elif ema9 and current_close < ema9:
        exit_signal = True
        exit_reason = "BELOW_EMA9"

    return {
        "should_exit": exit_signal,
        "exit_reason": exit_reason,
        "bars_held": bars_since_entry,
        "current_pnl_pct": round(current_pnl_pct, 2),
    }


# --- Phase 2: VWAP + PDH/PDL for scalping ---

def calculate_vwap(high: list, low: list, close: list, volume: list) -> dict:
    """
    VWAP = cumulative(TypicalPrice * Volume) / cumulative(Volume)
    TypicalPrice = (High + Low + Close) / 3
    Resets daily (caller provides intraday bars).
    """
    if not high or len(high) < 2:
        return {"vwap": 0, "vwap_distance_pct": 0, "price_vs_vwap": "unknown"}

    # Align arrays to shortest length
    min_len = min(len(high), len(low), len(close), len(volume))
    if min_len < 2:
        return {"vwap": 0, "vwap_distance_pct": 0, "price_vs_vwap": "unknown"}
    high = high[-min_len:]
    low = low[-min_len:]
    close = close[-min_len:]
    volume = volume[-min_len:]

    cum_tp_vol = 0
    cum_vol = 0
    vwap_val = 0
    for h, l, c, v in zip(high, low, close, volume):
        tp = (h + l + c) / 3
        cum_tp_vol += tp * v
        cum_vol += v
        if cum_vol > 0:
            vwap_val = cum_tp_vol / cum_vol

    current_price = close[-1]
    distance_pct = ((current_price - vwap_val) / vwap_val * 100) if vwap_val > 0 else 0

    return {
        "vwap": round(vwap_val, 3),
        "vwap_distance_pct": round(distance_pct, 2),
        "price_vs_vwap": "above" if current_price > vwap_val else "below",
    }


def calculate_pdh_pdl(daily_bars: list) -> dict:
    """
    Previous Day High/Low — key scalping levels.
    daily_bars: list of dicts with high, low, open, close (newest last).
    Needs at least 2 bars.
    """
    if not daily_bars or len(daily_bars) < 2:
        return {"pdh": 0, "pdl": 0, "daily_open": 0}
    prev_day = daily_bars[-2]
    today = daily_bars[-1]
    return {
        "pdh": prev_day.get("high", 0),
        "pdl": prev_day.get("low", 0),
        "daily_open": today.get("open", today.get("close", 0)),
    }


def _get_vwap_for_symbol(sym: str, bridge_data: dict) -> dict:
    """Extract VWAP from bridge bars data if available, else return empty."""
    try:
        bars = bridge_data.get("bars") or bridge_data.get("candles") or []
        if not bars or len(bars) < 5:
            return {"vwap": 0, "vwap_distance_pct": 0, "price_vs_vwap": "unknown"}
        high = [b.get("high", b.get("h", 0)) for b in bars]
        low = [b.get("low", b.get("l", 0)) for b in bars]
        close = [b.get("close", b.get("c", 0)) for b in bars]
        volume = [b.get("volume", b.get("v", 0)) for b in bars]
        return calculate_vwap(high, low, close, volume)
    except Exception as e:
        logger.debug("VWAP calc failed for %s: %s", sym, e)
        return {"vwap": 0, "vwap_distance_pct": 0, "price_vs_vwap": "unknown"}


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

        # Data alignment guard: skip symbols with missing critical fields
        _price = bd.get("price", 0)
        _vol = bd.get("vol_ratio")
        if not _price or _price <= 0:
            logger.debug("Skipping %s: missing price", sym_upper)
            continue

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
            "stoch_d": (bd.get("stoch_rsi") or {}).get("d"),
            "rsi_divergence": (bd.get("signals") or {}).get("rsi_divergence"),
            "ema_cross": (bd.get("signals") or {}).get("ema_cross"),
            "ema9": (bd.get("ema") or {}).get("ema9", 0),
            "ema21": (bd.get("ema") or {}).get("ema21", 0),
            "confluence_detail": confluence,
            "timeframe": "30m",
            "source": bd.get("source", ""),
            "stale": bd.get("stale", False),
        }

        # Phase 2: VWAP enrichment for scalping
        vwap_data = _get_vwap_for_symbol(sym_upper, bd)
        sig["vwap"] = vwap_data.get("vwap", 0)
        sig["vwap_distance_pct"] = vwap_data.get("vwap_distance_pct", 0)
        sig["price_vs_vwap"] = vwap_data.get("price_vs_vwap", "unknown")
        sig["scalping_vwap_ok"] = vwap_data.get("price_vs_vwap") == "above"

        # Phase 3: Scalping confluence (replaces default for 30m)
        if SCALPING_MODE:
            sc = scalping_confluence(sig)
            sig["scalp_confluence_pct"] = sc["confluence_pct"]
            sig["scalp_action"] = sc["action"]
            sig["scalp_factors"] = sc["factors"]
            sig["scalp_reason"] = sc.get("reason")

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

```


############################################################
# FILE: stock_radar.py (1444 lines)
############################################################

```python
"""
stock_radar.py - EMA Crossover Radar for KSE stocks.
Background poller: checks EMA9/21 on 30m candles, sends Telegram alerts.
Phase: Trading Advisor Phase 2 — Radar.

Tables in life.db:
  stock_radar_watchlist  — symbols to monitor
  stock_radar_state      — last signal per symbol (dedup)
  stock_radar_events     — signal log

TG commands: /radar, /radar_add, /radar_remove, /radar_check, /radar_last
"""
import os
import json
import time
import sqlite3
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Integration: Tier2/3 modules
try:
    from coalesced_executor import CoalescedExecutor
    _radar_coalesced = CoalescedExecutor("radar_refresh")
except ImportError:
    _radar_coalesced = None
try:
    from processing_cursor import ProcessingCursor
    _signal_cursor = ProcessingCursor("radar_last_signal_id", cursor_type="id")
except ImportError:
    _signal_cursor = None

logger = logging.getLogger("stock_radar")

DATA_DIR = Path(__file__).parent / "data"
LIFE_DB = DATA_DIR / "life.db"
CONFIG_FILE = DATA_DIR / "ema_radar.json"

DEFAULT_CONFIG = {
    "enabled": True,
    "timeframe": "30m",
    "fast_ema": 9,
    "slow_ema": 21,
    "poll_seconds": 90,
    "cooldown_minutes": 45,
    "symbols": ["ALL"],
}


def _get_config():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return DEFAULT_CONFIG


def _save_config(cfg):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))


def _db():
    conn = sqlite3.connect(str(LIFE_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ═══ DB Schema ═══

def init_radar_db():
    conn = _db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS stock_radar_watchlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        exchange TEXT NOT NULL DEFAULT 'KSE',
        timeframe TEXT NOT NULL DEFAULT '30m',
        fast_len INTEGER NOT NULL DEFAULT 9,
        slow_len INTEGER NOT NULL DEFAULT 21,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, exchange, timeframe, fast_len, slow_len)
    );
    CREATE TABLE IF NOT EXISTS stock_radar_state (
        symbol TEXT NOT NULL,
        exchange TEXT NOT NULL DEFAULT 'KSE',
        timeframe TEXT NOT NULL,
        fast_len INTEGER NOT NULL,
        slow_len INTEGER NOT NULL,
        last_signal TEXT,
        last_signal_candle_time TEXT,
        last_alert_time TEXT,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(symbol, exchange, timeframe, fast_len, slow_len)
    );
    CREATE TABLE IF NOT EXISTS stock_radar_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        exchange TEXT NOT NULL DEFAULT 'KSE',
        timeframe TEXT NOT NULL,
        signal_type TEXT NOT NULL,
        price REAL,
        candle_time TEXT,
        ema_fast REAL,
        ema_slow REAL,
        source TEXT NOT NULL DEFAULT 'local_radar',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # Daily Context Layer table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_radar_daily (
            symbol TEXT NOT NULL, exchange TEXT NOT NULL DEFAULT 'KSE',
            price REAL, trend TEXT, rsi REAL, support REAL, resistance REAL,
            score INTEGER, score_class TEXT, verdict TEXT,
            volume INTEGER, vol_ratio REAL, change_pct REAL,
            source_timeframe TEXT NOT NULL DEFAULT '1D',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(symbol, exchange))
    """)
    # Add MACD + confluence columns (ALTER TABLE, safe if already exists)
    for col_sql in [
        "ALTER TABLE stock_radar_daily ADD COLUMN macd REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN macd_signal REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN macd_histogram REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN macd_cross TEXT DEFAULT 'none'",
        "ALTER TABLE stock_radar_daily ADD COLUMN daily_ema9 REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN daily_ema21 REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN daily_ema_cross TEXT DEFAULT 'none'",
        "ALTER TABLE stock_radar_daily ADD COLUMN confluence_score INTEGER DEFAULT 0",
        "ALTER TABLE stock_radar_daily ADD COLUMN confluence_direction TEXT DEFAULT 'neutral'",
        "ALTER TABLE stock_radar_daily ADD COLUMN avg_volume INTEGER",
        "ALTER TABLE stock_radar_daily ADD COLUMN volume_spike BOOLEAN DEFAULT 0",
        "ALTER TABLE stock_radar_daily ADD COLUMN macd_above_zero BOOLEAN DEFAULT 0",
        "ALTER TABLE stock_radar_daily ADD COLUMN stoch_k REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN adx REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN rsi_divergence TEXT",
        "ALTER TABLE stock_radar_daily ADD COLUMN atr REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN ema_fast REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN ema_slow REAL",
        "ALTER TABLE stock_radar_daily ADD COLUMN bb_squeeze BOOLEAN DEFAULT 0",
        "ALTER TABLE stock_radar_daily ADD COLUMN bb_bandwidth REAL",
    ]:
        try:
            conn.execute(col_sql)
        except Exception:
            pass  # column already exists
    # Add EMA persistence columns to stock_radar_state (survives restart)
    for col_sql in [
        "ALTER TABLE stock_radar_state ADD COLUMN prev_ema_fast REAL",
        "ALTER TABLE stock_radar_state ADD COLUMN prev_ema_slow REAL",
    ]:
        try:
            conn.execute(col_sql)
        except Exception:
            pass
    # Add enriched columns to stock_radar_events (safe if already exists)
    for col_sql in [
        "ALTER TABLE stock_radar_events ADD COLUMN rsi REAL",
        "ALTER TABLE stock_radar_events ADD COLUMN vwap REAL",
        "ALTER TABLE stock_radar_events ADD COLUMN volume INTEGER DEFAULT 0",
        "ALTER TABLE stock_radar_events ADD COLUMN score INTEGER DEFAULT 0",
        "ALTER TABLE stock_radar_events ADD COLUMN score_class TEXT",
        "ALTER TABLE stock_radar_events ADD COLUMN verdict TEXT",
        "ALTER TABLE stock_radar_events ADD COLUMN support REAL",
        "ALTER TABLE stock_radar_events ADD COLUMN resistance REAL",
        "ALTER TABLE stock_radar_events ADD COLUMN vol_ratio REAL",
    ]:
        try:
            conn.execute(col_sql)
        except Exception:
            pass
    conn.commit()
    conn.close()
    logger.info("Radar DB tables ready")


# ═══ Watchlist Management ═══

def add_to_watchlist(symbol, timeframe="30m", fast=9, slow=21):
    from tv_data import resolve_symbol, KSE_STOCKS
    ticker = resolve_symbol(symbol)
    name_ar = KSE_STOCKS.get(ticker, ticker)
    conn = _db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO stock_radar_watchlist (symbol, exchange, timeframe, fast_len, slow_len) VALUES (?,?,?,?,?)",
            (ticker, "KSE", timeframe, fast, slow))
        conn.commit()
        return {"ok": True, "ticker": ticker, "name_ar": name_ar}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


def remove_from_watchlist(symbol):
    from tv_data import resolve_symbol
    ticker = resolve_symbol(symbol)
    conn = _db()
    conn.execute("DELETE FROM stock_radar_watchlist WHERE symbol=?", (ticker,))
    conn.commit()
    n = conn.total_changes
    conn.close()
    return {"ok": True, "ticker": ticker, "removed": n > 0}


def get_watchlist():
    conn = _db()
    rows = conn.execute(
        "SELECT symbol, timeframe, fast_len, slow_len, is_active FROM stock_radar_watchlist WHERE is_active=1"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_events(limit=10):
    conn = _db()
    rows = conn.execute(
        "SELECT * FROM stock_radar_events ORDER BY created_at DESC LIMIT ?",
        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══ EMA Computation ═══

def _compute_ema(closes, period):
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for p in closes[period:]:
        ema = p * k + ema * (1 - k)
    return round(ema, 3)


# ═══ MACD Computation ═══

def _compute_macd(closes, fast=12, slow=26, signal=9):
    """Calculate MACD, Signal, Histogram. Returns dict or None."""
    if len(closes) < slow + signal:
        return None
    # Build MACD line series from slow onward
    macd_line = []
    for i in range(slow, len(closes) + 1):
        ef = _compute_ema(closes[:i], fast)
        es = _compute_ema(closes[:i], slow)
        if ef is not None and es is not None:
            macd_line.append(ef - es)
    if len(macd_line) < signal:
        return None
    signal_line = _compute_ema(macd_line, signal)
    if signal_line is None:
        return None
    macd_current = macd_line[-1]
    histogram = macd_current - signal_line
    # MACD cross detection
    cross = "none"
    if len(macd_line) >= 2:
        prev_signal = _compute_ema(macd_line[:-1], signal)
        if prev_signal is not None:
            prev_hist = macd_line[-2] - prev_signal
            if prev_hist <= 0 and histogram > 0:
                cross = "bullish"
            elif prev_hist >= 0 and histogram < 0:
                cross = "bearish"
    return {
        "macd": round(macd_current, 3),
        "signal": round(signal_line, 3),
        "histogram": round(histogram, 3),
        "cross": cross,
        "above_zero": macd_current > 0,
    }


# ═══ Multi-TF Confluence ═══

def _detect_market_regime(adx):
    """Detect market regime from ADX value."""
    if adx is None:
        return "unknown"
    if adx >= 25:
        return "trending"
    elif adx <= 20:
        return "ranging"
    return "transition"


def _compute_confluence(signal_30m, daily_data):
    """Multi-timeframe confluence scoring. Uses brain weights if available."""
    try:
        from trading_brain import get_indicator_weights
        weights = get_indicator_weights()
        if weights and any(w != 1.0 for w in weights.values()):
            return _compute_confluence_weighted(signal_30m, daily_data, weights)
    except Exception:
        pass
    return _compute_confluence_fixed(signal_30m, daily_data)


def _compute_confluence_weighted(signal_30m, daily_data, weights):
    """Weighted confluence using brain's adaptive weights."""
    result = _compute_confluence_fixed(signal_30m, daily_data)
    score = result["confluence_score"]

    # Apply brain weights to score components
    ema_w = weights.get("ema", 1.0)
    macd_w = weights.get("macd", 1.0)
    rsi_w = weights.get("rsi", 1.0)
    vol_w = weights.get("vol", 1.0)

    # Recompute with weights
    weighted_score = 0
    ema_cross_30m = signal_30m.get("ema_cross", "none") if signal_30m else "none"
    if ema_cross_30m in ("bullish", "bearish"):
        weighted_score += (25 if ema_cross_30m == "bullish" else -25) * ema_w
    daily_ema_cross = daily_data.get("daily_ema_cross", "none")
    if daily_ema_cross in ("bullish", "bearish"):
        weighted_score += (30 if daily_ema_cross == "bullish" else -30) * ema_w
    macd_cross = daily_data.get("macd_cross", "none")
    if macd_cross in ("bullish", "bearish"):
        weighted_score += (20 if macd_cross == "bullish" else -20) * macd_w
    if daily_data.get("macd_above_zero"):
        weighted_score += 10 * macd_w
    elif daily_data.get("macd_above_zero") is False:
        weighted_score -= 10 * macd_w
    vol_ratio = daily_data.get("vol_ratio", 1)
    if vol_ratio >= 3:
        weighted_score += 15 * vol_w
    elif vol_ratio >= 2:
        weighted_score += 10 * vol_w
    rsi = daily_data.get("rsi", 50)
    if rsi and 40 <= rsi <= 60:
        weighted_score += 5 * rsi_w
    elif rsi and rsi > 70:
        weighted_score -= 10 * rsi_w
    elif rsi and rsi < 30:
        weighted_score += 15 * rsi_w

    weighted_score = int(round(weighted_score))
    direction = "bullish" if weighted_score > 0 else "bearish" if weighted_score < 0 else "neutral"
    strength = "strong" if abs(weighted_score) >= 60 else "moderate" if abs(weighted_score) >= 30 else "weak"

    result["confluence_score"] = weighted_score
    result["direction"] = direction
    result["strength"] = strength
    result["brain_weighted"] = True
    return result


def _compute_confluence_fixed(signal_30m, daily_data):
    """Multi-timeframe confluence scoring (fixed weights). Higher abs = stronger signal."""
    score = 0
    reasons = []

    # 30m EMA cross
    ema_cross_30m = signal_30m.get("ema_cross", "none") if signal_30m else "none"
    if ema_cross_30m == "bullish":
        score += 25
        reasons.append("30m EMA \u0635\u0627\u0639\u062f")
    elif ema_cross_30m == "bearish":
        score -= 25
        reasons.append("30m EMA \u0647\u0627\u0628\u0637")

    # Daily EMA cross
    daily_ema_cross = daily_data.get("daily_ema_cross", "none")
    if daily_ema_cross == "bullish":
        score += 30
        reasons.append("Daily EMA \u0635\u0627\u0639\u062f")
    elif daily_ema_cross == "bearish":
        score -= 30
        reasons.append("Daily EMA \u0647\u0627\u0628\u0637")

    # MACD daily
    macd_cross = daily_data.get("macd_cross", "none")
    if macd_cross == "bullish":
        score += 20
        reasons.append("MACD \u062a\u0642\u0627\u0637\u0639 \u0635\u0627\u0639\u062f")
    elif macd_cross == "bearish":
        score -= 20
        reasons.append("MACD \u062a\u0642\u0627\u0637\u0639 \u0647\u0627\u0628\u0637")

    # MACD above/below zero
    if daily_data.get("macd_above_zero"):
        score += 10
        reasons.append("MACD \u0641\u0648\u0642 \u0627\u0644\u0635\u0641\u0631")
    elif daily_data.get("macd_above_zero") is False:
        score -= 10

    # Volume spike
    vol_ratio = daily_data.get("vol_ratio", 1)
    if vol_ratio >= 3:
        score += 15
        reasons.append(f"\u062d\u062c\u0645 \u00d7{vol_ratio:.1f} (spike)")
    elif vol_ratio >= 2:
        score += 10
        reasons.append(f"\u062d\u062c\u0645 \u00d7{vol_ratio:.1f}")

    # RSI
    rsi = daily_data.get("rsi", 50)
    if rsi and 40 <= rsi <= 60:
        score += 5
    elif rsi and rsi > 70:
        score -= 10
        reasons.append("RSI \u062a\u0634\u0628\u0639 \u0634\u0631\u0627\u0626\u064a")
    elif rsi and rsi < 30:
        score += 15
        reasons.append("RSI \u062a\u0634\u0628\u0639 \u0628\u064a\u0639\u064a \u2014 \u0641\u0631\u0635\u0629")

    # Regime adjustment
    adx = daily_data.get("adx")
    regime = _detect_market_regime(adx)
    if regime == "ranging":
        score = int(score * 0.7) if abs(score) > 20 else score
        reasons.append("\u0633\u0648\u0642 \u0639\u0631\u0636\u064a (ADX<20)")
    elif regime == "trending" and abs(score) > 30:
        score = int(score * 1.15)
        reasons.append("\u0633\u0648\u0642 \u0627\u062a\u062c\u0627\u0647\u064a (ADX>25)")

    direction = "bullish" if score > 0 else "bearish" if score < 0 else "neutral"
    strength = "strong" if abs(score) >= 60 else "moderate" if abs(score) >= 30 else "weak"
    strength_ar = "\u0642\u0648\u064a" if strength == "strong" else "\u0645\u062a\u0648\u0633\u0637" if strength == "moderate" else "\u0636\u0639\u064a\u0641"

    return {
        "confluence_score": score,
        "direction": direction,
        "strength": strength,
        "strength_ar": strength_ar,
        "regime": regime,
        "reasons": reasons,
    }


# ═══ Cross Detection ═══

def _detect_cross(closes, fast_len, slow_len):
    """Detect EMA cross on last 2 CLOSED candles only."""
    if len(closes) < max(fast_len, slow_len) + 2:
        return None, None, None
    # Use closes[:-1] = all closed candles (exclude current open candle)
    closed = closes[:-1]
    # Current (last closed)
    curr_fast = _compute_ema(closed, fast_len)
    curr_slow = _compute_ema(closed, slow_len)
    # Previous (second-to-last closed)
    prev_closed = closed[:-1]
    prev_fast = _compute_ema(prev_closed, fast_len)
    prev_slow = _compute_ema(prev_closed, slow_len)
    if None in (curr_fast, curr_slow, prev_fast, prev_slow):
        return None, curr_fast, curr_slow
    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return "bullish_cross", curr_fast, curr_slow
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return "bearish_cross", curr_fast, curr_slow
    return None, curr_fast, curr_slow


def _should_alert(symbol, signal_type, candle_time, cooldown_min=45):
    """Check if we should send alert (dedup + cooldown)."""
    conn = _db()
    row = conn.execute(
        "SELECT last_signal, last_signal_candle_time, last_alert_time FROM stock_radar_state WHERE symbol=? AND timeframe='30m'",
        (symbol,)).fetchone()
    conn.close()
    if not row:
        return True
    # Same signal on same candle = already sent
    if row["last_signal"] == signal_type and row["last_signal_candle_time"] == candle_time:
        return False
    # Cooldown check
    if row["last_alert_time"]:
        try:
            last = datetime.fromisoformat(row["last_alert_time"])
            if datetime.utcnow() - last < timedelta(minutes=cooldown_min):
                return False
        except Exception:
            pass
    return True


def _record_signal(symbol, signal_type, candle_time, price, ema_fast, ema_slow, enriched=None):
    """Record signal in state + events tables with enriched data."""
    now = datetime.utcnow().isoformat()
    conn = _db()
    conn.execute("""
        INSERT OR REPLACE INTO stock_radar_state
        (symbol, exchange, timeframe, fast_len, slow_len, last_signal, last_signal_candle_time, last_alert_time, updated_at)
        VALUES (?, 'KSE', '30m', 9, 21, ?, ?, ?, ?)
    """, (symbol, signal_type, candle_time, now, now))
    # Base insert
    rsi = enriched.get("rsi") if enriched else None
    vwap = enriched.get("vwap") if enriched else None
    volume = enriched.get("volume", 0) if enriched else 0
    score = enriched.get("score", 0) if enriched else 0
    score_class = enriched.get("score_class", "") if enriched else ""
    verdict = enriched.get("verdict", "") if enriched else ""
    support = enriched.get("support") if enriched else None
    resistance = enriched.get("resistance") if enriched else None
    vol_ratio = enriched.get("vol_ratio", 0) if enriched else 0
    conn.execute("""
        INSERT INTO stock_radar_events
        (symbol, exchange, timeframe, signal_type, price, candle_time, ema_fast, ema_slow, source,
         rsi, vwap, volume, score, score_class, verdict, support, resistance, vol_ratio)
        VALUES (?, 'KSE', '30m', ?, ?, ?, ?, ?, 'local_radar', ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (symbol, signal_type, price, candle_time, ema_fast, ema_slow,
          rsi, vwap, volume, score, score_class, verdict, support, resistance, vol_ratio))
    conn.commit()
    conn.close()


# ═══ Alert Formatting ═══

def _format_alert(symbol, signal_type, price, ema_fast, ema_slow, candle_time, enriched=None):
    from tv_data import KSE_STOCKS
    name_ar = KSE_STOCKS.get(symbol, symbol)
    if signal_type == "bullish_cross":
        emoji = "\U0001f7e2"
        signal_ar = "\u062a\u0642\u0627\u0637\u0639 \u0635\u0627\u0639\u062f EMA9 \u0641\u0648\u0642 EMA21"
    else:
        emoji = "\U0001f534"
        signal_ar = "\u062a\u0642\u0627\u0637\u0639 \u0647\u0627\u0628\u0637 EMA9 \u062a\u062d\u062a EMA21"
    lines = [
        f"\U0001f4e1 \u0631\u0627\u062f\u0627\u0631 EMA 30m",
        "",
        f"\u0627\u0644\u0633\u0647\u0645: {name_ar} ({symbol})",
        f"\u0627\u0644\u0625\u0634\u0627\u0631\u0629: {emoji} {signal_ar}",
    ]
    if enriched:
        cp = enriched.get("change_pct", 0)
        arrow = "\u2b06\ufe0f" if cp >= 0 else "\u2b07\ufe0f"
        lines.append(f"\u0627\u0644\u0633\u0639\u0631: {price} \u0641\u0644\u0633 {arrow} {cp:+.2f}%")
        rsi = enriched.get("rsi")
        if rsi:
            rz = "\u062a\u0634\u0628\u0639 \u0634\u0631\u0627\u0626\u064a" if rsi >= 70 else "\u062a\u0634\u0628\u0639 \u0628\u064a\u0639\u064a" if rsi <= 30 else "\u0645\u062d\u0627\u064a\u062f"
            lines.append(f"RSI(14): {rsi} ({rz})")
        vwap = enriched.get("vwap")
        if vwap:
            vp = "\u0641\u0648\u0642" if price > vwap else "\u062a\u062d\u062a"
            lines.append(f"VWAP: {vwap} (\u0627\u0644\u0633\u0639\u0631 {vp})")
        lines.append(f"EMA9: {ema_fast} | EMA21: {ema_slow}")
        sup = enriched.get("support")
        res = enriched.get("resistance")
        if sup and res:
            lines.append(f"\u0627\u0644\u062f\u0639\u0645: {sup} | \u0627\u0644\u0645\u0642\u0627\u0648\u0645\u0629: {res}")
        vr = enriched.get("vol_ratio", 0)
        vol = enriched.get("volume", 0)
        if vol:
            lines.append(f"\u0627\u0644\u062d\u062c\u0645: {vol:,} (x{vr:.1f} \u0645\u0646 \u0627\u0644\u0645\u062a\u0648\u0633\u0637)")
        verdict = enriched.get("verdict", "")
        sc = enriched.get("score", 0)
        sc_cls = enriched.get("score_class", "")
        if verdict or sc:
            lines.append("")
            if sc:
                lines.append(f"Score: {sc}/100 (Class {sc_cls})")
            if verdict:
                lines.append(f"\u0627\u0644\u062d\u0643\u0645: {verdict}")
    else:
        lines.append(f"\u0627\u0644\u0633\u0639\u0631: {price} \u0641\u0644\u0633")
        lines.append(f"EMA9: {ema_fast} | EMA21: {ema_slow}")
    return chr(10).join(lines)


# ═══ Smart Verdict ═══

def _smart_verdict(signal, rsi, vwap, price, vol_sig, ema_f, ema_s):
    """One-line Arabic verdict based on combined indicators."""
    vol_type = vol_sig.get("signal", "normal") if vol_sig else "normal"
    if signal == "bullish_cross":
        if rsi and rsi > 65 and vol_type in ("high_volume", "extreme_volume"):
            return "\U0001f525 \u0627\u062e\u062a\u0631\u0627\u0642 \u0645\u062d\u062a\u0645\u0644"
        if rsi and rsi < 35:
            return "\U0001f7e2 \u0627\u0631\u062a\u062f\u0627\u062f \u0645\u0646 \u0642\u0627\u0639 \u2014 \u0645\u062a\u0627\u0628\u0639\u0629"
        return "\U0001f7e2 \u0632\u062e\u0645 \u0635\u0627\u0639\u062f \u2014 \u0645\u062a\u0627\u0628\u0639\u0629"
    if signal == "bearish_cross":
        if rsi and rsi < 30:
            return "\U0001f534 \u0632\u062e\u0645 \u0636\u0639\u064a\u0641 + \u062a\u0634\u0628\u0639 \u0628\u064a\u0639\u064a"
        if vol_type in ("high_volume", "extreme_volume"):
            return "\u26A0\uFE0F \u062d\u0630\u0631 \u2014 \u0636\u063a\u0637 \u0628\u064a\u0639\u064a \u0628\u062d\u062c\u0645"
        return "\U0001f534 \u0632\u062e\u0645 \u0636\u0639\u064a\u0641 \u2014 \u062d\u0630\u0631"
    return ""


# ═══ Signal Score (0-100) ═══

def _compute_score(signal, rsi, vwap, price, vol_sig, ema_f, ema_s, sr):
    """Compute numeric score 0-100 for signal quality using Brain weights."""
    if not signal:
        return 0, "D"

    # Try brain weights
    try:
        from trading_brain import get_indicator_weights
        weights = get_indicator_weights()
    except Exception:
        weights = {}

    w_ema = weights.get("ema", 1.0)
    w_rsi = weights.get("rsi", 1.0)
    w_vol = weights.get("vol", 1.0)
    w_macd = weights.get("macd", 1.0)
    w_adx = weights.get("adx", 1.0)

    score = 0
    vol_ratio = vol_sig.get("ratio", 0) if vol_sig else 0
    is_bull = signal == "bullish_cross"

    # EMA cross base (weighted)
    score += int(25 * w_ema)

    # RSI alignment (weighted)
    if rsi:
        if is_bull:
            if 40 <= rsi <= 65: score += int(15 * w_rsi)
            elif rsi < 35: score += int(10 * w_rsi)
            elif rsi > 75: score -= int(10 * w_rsi)
        else:
            if 35 <= rsi <= 60: score += int(15 * w_rsi)
            elif rsi > 65: score += int(10 * w_rsi)
            elif rsi < 25: score -= int(10 * w_rsi)

    # VWAP alignment (weighted by macd as proxy)
    if vwap and price:
        if is_bull and price > vwap: score += int(15 * w_macd)
        elif not is_bull and price < vwap: score += int(15 * w_macd)
        elif is_bull and price < vwap * 0.97: score += int(5 * w_macd)

    # Volume confirmation (weighted)
    if vol_ratio >= 2.5: score += int(20 * w_vol)
    elif vol_ratio >= 1.5: score += int(15 * w_vol)
    elif vol_ratio >= 1.0: score += int(5 * w_vol)
    elif vol_ratio < 0.3: score -= int(15 * w_vol)

    # S/R proximity (weighted by adx)
    if sr and price:
        res1 = sr.get("resistance_1", 0)
        sup1 = sr.get("support_1", 0)
        if is_bull and res1 and price > res1 * 0.98: score -= int(10 * w_adx)
        if not is_bull and sup1 and price < sup1 * 1.02: score -= int(10 * w_adx)

    # Trend confirmation (EMA gap)
    if ema_f and ema_s:
        gap_pct = abs(ema_f - ema_s) / ema_s * 100 if ema_s else 0
        if gap_pct > 1.5: score += int(10 * w_ema)
        elif gap_pct > 0.5: score += int(5 * w_ema)

    score = max(0, min(100, score))
    if score >= 75: cls = "A"
    elif score >= 50: cls = "B"
    elif score >= 30: cls = "C"
    else: cls = "D"
    return score, cls


# ═══ Single Symbol Check ═══

# In-memory EMA history for cross detection (survives across poll cycles)
_prev_ema: dict = {}  # {ticker: (prev_fast, prev_slow)}


def _load_prev_ema():
    """Load previous EMA values from DB (survives restart)."""
    global _prev_ema
    try:
        conn = _db()
        rows = conn.execute(
            "SELECT symbol, prev_ema_fast, prev_ema_slow FROM stock_radar_state "
            "WHERE timeframe='30m' AND prev_ema_fast IS NOT NULL"
        ).fetchall()
        conn.close()
        for r in rows:
            _prev_ema[r["symbol"]] = (float(r["prev_ema_fast"]), float(r["prev_ema_slow"]))
        logger.info(f"Loaded {len(_prev_ema)} prev EMA states from DB")
    except Exception as e:
        logger.warning(f"Failed to load prev EMA: {e}")


def _fetch_bridge_30m(ticker: str) -> dict:
    """Fetch 30m analysis for one symbol from Bridge API (sync)."""
    import requests as _req
    r = _req.get(
        "http://192.168.111.158:8059/analysis",
        params={"symbol": ticker, "exchange": "KSE", "interval": "30", "bars": 60},
        timeout=8,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Bridge HTTP {r.status_code}")
    return r.json()


def check_symbol(symbol, fast=9, slow=21):
    """Check one symbol for EMA cross via Bridge API (30m). No tvDatafeed dependency."""
    from tv_data import resolve_symbol, KSE_STOCKS
    ticker = resolve_symbol(symbol)
    try:
        raw = _fetch_bridge_30m(ticker)
        ind = raw.get("indicators", {})
        q   = raw.get("quote", {})

        price      = float(raw.get("price") or q.get("price") or 0)
        change_pct = round(float(q.get("change_percent") or q.get("chp") or 0), 2)
        change     = round(price * change_pct / 100, 3)
        volume     = int(q.get("volume") or 0)
        rsi        = round(float(ind.get("rsi_14") or 0), 2)
        vol_ratio  = round(float(ind.get("vol_ratio") or 0), 2)
        vwap       = ind.get("vwap") or price

        ema_f = float(ind.get("ema_9") or ind.get("ema9") or 0)
        ema_s = float(ind.get("ema_21") or ind.get("ema_20") or 0)

        # EMA cross: compare current vs previous (stored from last poll cycle)
        prev_f, prev_s = _prev_ema.get(ticker, (None, None))
        _prev_ema[ticker] = (ema_f, ema_s)

        signal = None
        if prev_f and prev_s and ema_f and ema_s:
            if prev_f <= prev_s and ema_f > ema_s:
                signal = "bullish_cross"
            elif prev_f >= prev_s and ema_f < ema_s:
                signal = "bearish_cross"

        candle_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M")

        # Fix 6: S/R from top-level arrays in Bridge response
        _sup_arr = raw.get("support", []) if isinstance(raw, dict) else []
        _res_arr = raw.get("resistance", []) if isinstance(raw, dict) else []
        _sup = _sup_arr[0] if _sup_arr else (ind.get("support_1") or ind.get("pivot_low"))
        _res = _res_arr[0] if _res_arr else (ind.get("resistance_1") or ind.get("pivot_high"))
        sr = {"support_1": _sup, "resistance_1": _res} if (_sup or _res) else None

        vol_sig = {
            "signal": "high_volume" if vol_ratio >= 1.5 else "normal",
            "ratio": vol_ratio,
            "avg_volume": 0,
        }
        verdict    = _smart_verdict(signal, rsi, vwap, price, vol_sig, ema_f, ema_s)
        score, score_class = _compute_score(signal, rsi, vwap, price, vol_sig, ema_f, ema_s, sr)

        # Persist EMA state for restart survival
        try:
            conn = _db()
            conn.execute("""
                INSERT OR REPLACE INTO stock_radar_state
                (symbol, exchange, timeframe, fast_len, slow_len, prev_ema_fast, prev_ema_slow, updated_at)
                VALUES (?, 'KSE', '30m', 9, 21, ?, ?, ?)
            """, (ticker, ema_f, ema_s, datetime.utcnow().isoformat()))
            conn.commit()
            conn.close()
        except Exception:
            pass

        return {
            "ticker":      ticker,
            "name_ar":     KSE_STOCKS.get(ticker, ticker),
            "price":       price,
            "change":      change,
            "change_pct":  change_pct,
            "ema_fast":    ema_f,
            "ema_slow":    ema_s,
            "signal":      signal,
            "candle_time": candle_time,
            "rsi":         rsi,
            "vwap":        vwap,
            "support":     _sup,
            "resistance":  _res,
            "volume":      volume,
            "vol_avg":     0,
            "vol_ratio":   vol_ratio,
            "vol_signal":  vol_sig["signal"],
            "verdict":     verdict,
            "score":       score,
            "score_class": score_class,
        }
    except Exception as e:
        logger.error(f"check_symbol({ticker}): {e}")
        return {"ticker": ticker, "error": str(e)}


# ═══ Background Radar Loop ═══

async def radar_loop(send_fn):
    """Main radar loop. send_fn(text) sends Telegram message."""
    init_radar_db()
    _load_prev_ema()
    _radar_running = True
    _radar_cycle_count = 0
    logger.info("Stock radar loop started")
    await asyncio.sleep(60)  # wait for system startup
    while True:
        try:
            # Feature flag check (DB-backed, no restart needed)
            try:
                from feature_flags import FeatureFlags
                _ff = FeatureFlags("data/life.db")
                if not _ff.is_enabled("radar_enabled"):
                    logger.info("Radar disabled by feature flag")
                    await asyncio.sleep(300)
                    continue
            except Exception:
                pass
            cfg = _get_config()
            if not cfg.get("enabled", True):
                await asyncio.sleep(300)
                continue
            # Daily Context Layer: refresh once per session
            _do_daily = True
            try:
                from feature_flags import FeatureFlags
                _ff2 = FeatureFlags("data/life.db")
                _do_daily = _ff2.is_enabled("daily_refresh")
            except Exception:
                pass
            if _do_daily and not _daily_snapshot_is_fresh():
                try:
                    logger.info("Refreshing daily snapshot (stale or missing)...")
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, refresh_daily_snapshot)
                except Exception as de:
                    logger.warning(f"Daily snapshot refresh failed (non-fatal): {de}")
            # Only run during KSE market hours (Sun-Thu 9:00-12:40 KWT)
            from tv_data import _is_market_open
            if not _is_market_open():
                await asyncio.sleep(300)
                continue
            # Skip first 15 min after open (9:00-9:15 KWT) — noisy
            kwt_now = datetime.utcnow() + timedelta(hours=3)
            if kwt_now.hour == 9 and kwt_now.minute < 15:
                await asyncio.sleep(60)
                continue
            # Service health: skip cycle if Bridge is down
            try:
                from service_health import get_health_hub
                _hub = get_health_hub()
                if _hub and not _hub.is_up("bridge"):
                    logger.warning("Bridge down (service_health), skipping radar cycle — waiting 300s")
                    await asyncio.sleep(300)
                    continue
            except Exception:
                pass

            watchlist = get_watchlist()
            if not watchlist:
                # Fallback to config symbols — "ALL" means all KSE stocks
                from tv_data import KSE_STOCKS
                syms = cfg.get("symbols", [])
                if syms == ["ALL"] or syms == ["all"]:
                    syms = list(KSE_STOCKS.keys())
                for sym in syms:
                    add_to_watchlist(sym)
                watchlist = get_watchlist()
            cooldown = cfg.get("cooldown_minutes", 45)
            for item in watchlist:
                sym = item["symbol"]
                fast = item.get("fast_len", cfg.get("fast_ema", 9))
                slow = item.get("slow_len", cfg.get("slow_ema", 21))
                try:
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, check_symbol, sym, fast, slow)
                    if result.get("error"):
                        continue
                    signal = result.get("signal")
                    # Skip dead-volume stocks (noise filter)
                    if result.get("vol_ratio", 0) < 0.3:
                        continue
                    if signal and _should_alert(sym, signal, result["candle_time"], cooldown):
                        _record_signal(sym, signal, result["candle_time"],
                                       result["price"], result["ema_fast"], result["ema_slow"],
                                       enriched=result)
                        # Fire after_signal hook (non-blocking)
                        try:
                            from service_health import get_health_hub
                            _hub = get_health_hub()
                            if _hub:
                                _hk = getattr(_hub, '_hooks', None)
                                if _hk:
                                    _hk.fire_sync("after_signal",
                                        symbol=sym, signal_type=signal,
                                        price=result["price"],
                                        score=result.get("score", 0),
                                        timeframe="30m")
                        except Exception:
                            pass
                        msg = _format_alert(sym, signal, result["price"],
                                            result["ema_fast"], result["ema_slow"],
                                            result["candle_time"], enriched=result)
                        try:
                            _sig_meta = {
                                "symbol": sym, "signal": signal,
                                "price": result["price"],
                                "score": result.get("score", 0),
                                "score_class": result.get("score_class", ""),
                                "rsi": result.get("rsi"),
                                "vol_ratio": result.get("vol_ratio", 0),
                                "source": "radar",
                            }
                            # before_trade_alert hook — can block the alert
                            _skip_alert = False
                            try:
                                from service_health import get_health_hub
                                _hub2 = get_health_hub()
                                if _hub2:
                                    _hk2 = getattr(_hub2, '_hooks', None)
                                    if _hk2:
                                        _hr = await _hk2.fire("before_trade_alert",
                                            symbol=sym, action=signal,
                                            confidence=result.get("score", 0))
                                        for _r in (_hr or []):
                                            if isinstance(_r, dict) and _r.get("skip"):
                                                _skip_alert = True
                                                logger.info("Hook blocked alert for %s: %s", sym, _r.get("reason", ""))
                                                break
                            except Exception:
                                pass
                            if _skip_alert:
                                continue
                            await send_fn(msg, _sig_meta)
                            logger.info(f"Radar alert sent: {sym} {signal}")
                            if _signal_cursor:
                                _signal_cursor.set(f"{sym}:{signal}:{result['candle_time']}")
                        except Exception as se:
                            logger.error(f"Radar send error: {se}")
                    await asyncio.sleep(1)  # pace between symbols
                except Exception as e:
                    logger.warning(f"Radar skip {sym}: {e}")
                    continue
            poll = cfg.get("poll_seconds", 90)
            await asyncio.sleep(poll)
            _radar_cycle_count += 1
        except Exception as e:
            logger.error(f"Radar loop error (non-fatal): {e}")
            await asyncio.sleep(120)


# ═══ Telegram Command Handlers ═══

def tg_radar_list():
    wl = get_watchlist()
    if not wl:
        return "\U0001f4e1 \u0631\u0627\u062f\u0627\u0631 \u0627\u0644\u0623\u0633\u0647\u0645 \u0641\u0627\u0631\u063a \u2014 \u0627\u0633\u062a\u062e\u062f\u0645 /radar_add SYMBOL"
    from tv_data import KSE_STOCKS
    cfg = _get_config()
    status = "\U0001f7e2 \u0634\u063a\u0627\u0644" if cfg.get("enabled") else "\U0001f534 \u0645\u0648\u0642\u0641"
    lines = [f"\U0001f4e1 \u0631\u0627\u062f\u0627\u0631 EMA ({status})", ""]
    for w in wl:
        name = KSE_STOCKS.get(w["symbol"], w["symbol"])
        lines.append(f"  \u2022 {name} ({w['symbol']}) EMA{w['fast_len']}/{w['slow_len']} {w['timeframe']}")
    lines.append(f"{chr(10)}\u23F1 \u0641\u062d\u0635 \u0643\u0644 {cfg.get('poll_seconds', 90)} \u062b\u0627\u0646\u064a\u0629")
    return chr(10).join(lines)


def tg_radar_add(args):
    if not args:
        return "\u2753 \u0627\u0633\u062a\u062e\u062f\u0645: /radar_add SYMBOL"
    result = add_to_watchlist(args.strip())
    if result["ok"]:
        return f"\u2705 {result['name_ar']} ({result['ticker']}) \u0627\u0646\u0636\u0627\u0641 \u0644\u0644\u0631\u0627\u062f\u0627\u0631"
    return f"\u274c {result.get('error', 'error')}"


def tg_radar_remove(args):
    if not args:
        return "\u2753 \u0627\u0633\u062a\u062e\u062f\u0645: /radar_remove SYMBOL"
    result = remove_from_watchlist(args.strip())
    return f"\u2705 {result['ticker']} \u0634\u0644\u0646\u0627\u0647 \u0645\u0646 \u0627\u0644\u0631\u0627\u062f\u0627\u0631" if result["removed"] else f"\u26A0\uFE0F {result['ticker']} \u0645\u0648 \u0628\u0627\u0644\u0631\u0627\u062f\u0627\u0631"


def tg_radar_check(args):
    if not args:
        return "\u2753 \u0627\u0633\u062a\u062e\u062f\u0645: /radar_check SYMBOL"
    result = check_symbol(args.strip())
    if result.get("error"):
        return f"\u274c {result['ticker']}: {result['error']}"
    from tv_data import KSE_STOCKS
    name = KSE_STOCKS.get(result["ticker"], result["ticker"])
    sig = result.get("signal")
    if sig == "bullish_cross":
        sig_text = "\U0001f7e2 \u062a\u0642\u0627\u0637\u0639 \u0635\u0627\u0639\u062f"
    elif sig == "bearish_cross":
        sig_text = "\U0001f534 \u062a\u0642\u0627\u0637\u0639 \u0647\u0627\u0628\u0637"
    else:
        sig_text = "\u26AA \u0644\u0627 \u062a\u0642\u0627\u0637\u0639"
    cp = result.get("change_pct", 0)
    arrow = "\u2b06\ufe0f" if cp >= 0 else "\u2b07\ufe0f"
    lines = [
        f"\U0001f4e1 {name} ({result['ticker']})",
        f"\u0627\u0644\u0633\u0639\u0631: {result['price']} \u0641\u0644\u0633 {arrow} {cp:+.2f}%",
        f"EMA9: {result['ema_fast']} | EMA21: {result['ema_slow']}",
    ]
    rsi = result.get("rsi")
    if rsi:
        lines.append(f"RSI(14): {rsi}")
    vwap = result.get("vwap")
    if vwap:
        lines.append(f"VWAP: {vwap}")
    sup = result.get("support")
    res = result.get("resistance")
    if sup and res:
        lines.append(f"\u0627\u0644\u062f\u0639\u0645: {sup} | \u0627\u0644\u0645\u0642\u0627\u0648\u0645\u0629: {res}")
    vr = result.get("vol_ratio", 0)
    vol = result.get("volume", 0)
    if vol:
        lines.append(f"\u0627\u0644\u062d\u062c\u0645: {vol:,} (x{vr:.1f})")
    lines.append(f"\u0627\u0644\u0625\u0634\u0627\u0631\u0629: {sig_text}")
    sc = result.get("score", 0)
    sc_cls = result.get("score_class", "")
    if sc:
        lines.append(f"Score: {sc}/100 (Class {sc_cls})")
    verdict = result.get("verdict")
    if verdict:
        lines.append(f"\u0627\u0644\u062d\u0643\u0645: {verdict}")
    return chr(10).join(lines)


def tg_radar_last(args=""):
    """Show last events — optionally filtered by symbol."""
    from tv_data import KSE_STOCKS, resolve_symbol
    ticker = None
    if args and args.strip():
        ticker = resolve_symbol(args.strip())
    conn = _db()
    if ticker:
        rows = conn.execute(
            "SELECT * FROM stock_radar_events WHERE symbol=? ORDER BY created_at DESC LIMIT 10",
            (ticker,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM stock_radar_events ORDER BY created_at DESC LIMIT 10").fetchall()
    conn.close()
    events = [dict(r) for r in rows]
    if not events:
        extra = f" \u0644\u0640 {ticker}" if ticker else ""
        return f"\U0001f4e1 \u0644\u0627 \u062a\u0648\u062c\u062f \u0625\u0634\u0627\u0631\u0627\u062a \u0633\u0627\u0628\u0642\u0629{extra}"
    title = f"\U0001f4e1 \u0622\u062e\u0631 \u0625\u0634\u0627\u0631\u0627\u062a {ticker}:" if ticker else "\U0001f4e1 \u0622\u062e\u0631 \u0625\u0634\u0627\u0631\u0627\u062a \u0627\u0644\u0631\u0627\u062f\u0627\u0631:"
    lines = [title, ""]
    for e in events:
        name = KSE_STOCKS.get(e["symbol"], e["symbol"])
        emoji = "\U0001f7e2" if "bullish" in e["signal_type"] else "\U0001f534"
        lines.append(f"{emoji} {name} | {e['price']} | EMA {e.get('ema_fast','?')}/{e.get('ema_slow','?')} | {e['created_at'][:16]}")
    return chr(10).join(lines)


def tg_radar_status():
    """Show radar status: enabled, watchlist count, last signal, uptime."""
    cfg = _get_config()
    enabled = cfg.get("enabled", True)
    status = "\U0001f7e2 \u0634\u063a\u0627\u0644" if enabled else "\U0001f534 \u0645\u0648\u0642\u0641"
    poll = cfg.get("poll_seconds", 90)
    cooldown = cfg.get("cooldown_minutes", 45)
    wl = get_watchlist()
    wl_count = len(wl)
    syms = cfg.get("symbols", [])
    if syms == ["ALL"] or syms == ["all"]:
        mode = "\u0643\u0644 \u0627\u0644\u0623\u0633\u0647\u0645"
    else:
        mode = f"{len(syms)} \u0633\u0647\u0645"
    from tv_data import _is_market_open
    market = "\U0001f7e2 \u0645\u0641\u062a\u0648\u062d" if _is_market_open() else "\U0001f534 \u0645\u063a\u0644\u0642"
    conn = _db()
    total_events = conn.execute("SELECT COUNT(*) FROM stock_radar_events").fetchone()[0]
    last_row = conn.execute("SELECT symbol, signal_type, price, created_at FROM stock_radar_events ORDER BY created_at DESC LIMIT 1").fetchone()
    conn.close()
    lines = [
        f"\U0001f4e1 \u062d\u0627\u0644\u0629 \u0627\u0644\u0631\u0627\u062f\u0627\u0631", "",
        f"\u0627\u0644\u062d\u0627\u0644\u0629: {status}",
        f"\u0627\u0644\u0633\u0648\u0642: {market}",
        f"\u0627\u0644\u0645\u0631\u0627\u0642\u0628\u0629: {mode} ({wl_count} \u0641\u064a \u0627\u0644\u0642\u0627\u0626\u0645\u0629)",
        f"\u0627\u0644\u0641\u062d\u0635: \u0643\u0644 {poll} \u062b\u0627\u0646\u064a\u0629",
        f"\u0627\u0644\u062a\u0628\u0631\u064a\u062f: {cooldown} \u062f\u0642\u064a\u0642\u0629",
        f"\u0625\u062c\u0645\u0627\u0644\u064a \u0627\u0644\u0625\u0634\u0627\u0631\u0627\u062a: {total_events}",
    ]
    if last_row:
        from tv_data import KSE_STOCKS
        ln = KSE_STOCKS.get(last_row["symbol"], last_row["symbol"])
        em = "\U0001f7e2" if "bullish" in last_row["signal_type"] else "\U0001f534"
        lines.append(f"\u0622\u062e\u0631 \u0625\u0634\u0627\u0631\u0629: {em} {ln} @ {last_row['price']} ({last_row['created_at'][:16]})")
    return chr(10).join(lines)


def tg_radar_top(n=10):
    """Top N signals from recent radar events, scored and ranked."""
    conn = _db()
    # Get unique latest signal per symbol from recent events (last 24h)
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    rows = conn.execute("""
        SELECT symbol, signal_type, price, ema_fast, ema_slow, created_at,
               MAX(created_at) as latest
        FROM stock_radar_events
        WHERE created_at > ?
        GROUP BY symbol
        ORDER BY created_at DESC
    """, (cutoff,)).fetchall()
    conn.close()
    if not rows:
        return "\U0001f4e1 \u0644\u0627 \u062a\u0648\u062c\u062f \u0625\u0634\u0627\u0631\u0627\u062a \u062e\u0644\u0627\u0644 24 \u0633\u0627\u0639\u0629"
    # Re-check each for live score
    scored = []
    for r in rows:
        try:
            result = check_symbol(r["symbol"])
            if result.get("error"):
                continue
            sc = result.get("score", 0)
            if sc > 0:
                scored.append({
                    "symbol": r["symbol"],
                    "signal": r["signal_type"],
                    "price": result["price"],
                    "score": sc,
                    "score_class": result.get("score_class", "D"),
                    "rsi": result.get("rsi"),
                    "vol_ratio": result.get("vol_ratio", 0),
                    "verdict": result.get("verdict", ""),
                    "time": r["created_at"][:16],
                })
            time.sleep(0.3)
        except Exception:
            continue
    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:n]
    if not top:
        return "\U0001f4e1 \u0644\u0627 \u062a\u0648\u062c\u062f \u0625\u0634\u0627\u0631\u0627\u062a \u0645\u0624\u0647\u0644\u0629"
    from tv_data import KSE_STOCKS
    lines = [f"\U0001f3af \u0623\u0641\u0636\u0644 {len(top)} \u0625\u0634\u0627\u0631\u0627\u062a \u0627\u0644\u0631\u0627\u062f\u0627\u0631:", ""]
    for i, s in enumerate(top, 1):
        name = KSE_STOCKS.get(s["symbol"], s["symbol"])
        em = "\U0001f7e2" if "bullish" in s["signal"] else "\U0001f534"
        rsi_txt = f"RSI:{s['rsi']}" if s.get("rsi") else ""
        lines.append(f"{i}. {em} {name} ({s['symbol']})")
        lines.append(f"   Score: {s['score']}/100 (Class {s['score_class']}) | {s['price']} fils | x{s['vol_ratio']:.1f} vol {rsi_txt}")
        if s.get("verdict"):
            lines.append(f"   {s['verdict']}")
        lines.append("")
    return chr(10).join(lines)


def tg_radar_toggle():
    cfg = _get_config()
    cfg["enabled"] = not cfg.get("enabled", True)
    _save_config(cfg)
    s = "\U0001f7e2 \u0634\u063a\u0627\u0644" if cfg["enabled"] else "\U0001f534 \u0645\u0648\u0642\u0641"
    return f"\U0001f4e1 \u0627\u0644\u0631\u0627\u062f\u0627\u0631 {s}"



# ═══ Daily Context Layer ═══
# Daily snapshot for post-market review
# trend: "صاعد" if EMA9>EMA21 daily, "هابط" if EMA9<EMA21, "محايد" otherwise

_daily_refresh_lock = False


def _fetch_bridge_daily(symbols: list) -> dict:
    """Fetch 1D analysis for all symbols from Bridge API (sync, batched).
    Returns dict: {symbol: normalized_data} or {} on failure."""
    import requests as _req
    BRIDGE = "http://192.168.111.158:8059"
    BATCH = 5   # smaller batches — daily data is slower to fetch
    results = {}
    for i in range(0, len(symbols), BATCH):
        batch = symbols[i:i + BATCH]
        try:
            r = _req.get(
                f"{BRIDGE}/multi-analysis",
                params={"symbols": ",".join(batch), "exchange": "KSE", "interval": "1D", "bars": 60},
                timeout=90,  # daily TradingView fetch is slow — allow 90s per batch
            )
            if r.status_code == 200:
                data = r.json()
                for item in data.get("results", []):
                    sym_raw = item.get("symbol", "")
                    sym = sym_raw.split(":")[-1] if ":" in sym_raw else sym_raw
                    results[sym] = item
        except Exception as e:
            logger.warning(f"Bridge batch {batch[:3]}…: {e}")
    return results


def refresh_daily_snapshot(symbols=None):
    """Compute daily (1D) analysis for watchlist via Bridge API, store in stock_radar_daily."""
    global _daily_refresh_lock
    if _daily_refresh_lock:
        return {"ok": 0, "errors": 0, "msg": "refresh already running"}
    _daily_refresh_lock = True
    try:
        if symbols is None:
            wl = get_watchlist()
            symbols = [w["symbol"] for w in wl]
        if not symbols:
            return {"ok": 0, "errors": 0, "msg": "empty watchlist"}

        # Fetch all symbols from Bridge in bulk (1D candles)
        bridge_data = _fetch_bridge_daily(symbols)
        if not bridge_data:
            logger.warning("daily_snapshot: Bridge returned no data — aborting")
            return {"ok": 0, "errors": len(symbols), "msg": "bridge_no_data"}

        conn = _db()
        ok_count = 0
        err_count = 0
        now = datetime.utcnow().isoformat()

        # Bridge signals provide pre-computed crosses — no need for prev lookups

        for sym in symbols:
            try:
                raw = bridge_data.get(sym)
                if not raw:
                    err_count += 1
                    continue

                ind = raw.get("indicators", {})
                q   = raw.get("quote", {})

                price      = float(raw.get("price") or q.get("price") or 0)
                change_pct = round(float(q.get("change_percent") or q.get("chp") or 0), 2)
                rsi        = round(float(ind.get("rsi_14") or 0), 2)
                volume     = int(q.get("volume") or 0)
                vol_ratio  = round(float(ind.get("vol_ratio") or 0), 2)

                ema9  = ind.get("ema_9") or ind.get("ema9") or 0
                ema21 = ind.get("ema_21") or ind.get("ema_20") or 0

                # === EMA Direction (always set) ===
                if ema9 and ema21:
                    if ema9 > ema21:
                        trend_ar = "صاعد"
                    elif ema9 < ema21:
                        trend_ar = "هابط"
                    else:
                        trend_ar = "محايد"
                else:
                    trend_ar = "محايد"

                # === Bridge pre-computed signals ===
                bridge_signals = raw.get("signals") or {}
                bridge_ema_cross = bridge_signals.get("ema_cross") or {}
                bridge_confluence = bridge_signals.get("confluence") or {}
                bridge_macd_mom = bridge_signals.get("macd_momentum") or ""

                # === EMA Cross from Bridge ===
                if isinstance(bridge_ema_cross, dict) and bridge_ema_cross.get("type"):
                    cross_type = bridge_ema_cross["type"]
                    if cross_type == "golden":
                        daily_ema_cross = "bullish"
                    elif cross_type == "death":
                        daily_ema_cross = "bearish"
                    else:
                        daily_ema_cross = "none"
                else:
                    daily_ema_cross = "bullish" if ema9 and ema21 and ema9 > ema21 else "bearish" if ema9 and ema21 and ema9 < ema21 else "none"

                # === MACD ===
                macd_val  = ind.get("macd") or 0
                macd_sig  = ind.get("macd_signal") or 0
                macd_hist = ind.get("macd_hist") or 0
                macd_cross = "bullish" if macd_hist > 0 else "bearish" if macd_hist < 0 else "none"
                macd_above_zero = bool(macd_val > 0)

                # === Other indicators ===
                stoch_k_val = ind.get("stoch_k")
                adx_val     = ind.get("adx")
                atr_val     = ind.get("atr_14")
                rsi_div_val = bridge_signals.get("rsi_divergence")
                if rsi_div_val == "none" or rsi_div_val == "":
                    rsi_div_val = None

                # S/R from top-level arrays
                sup_arr = raw.get("support", [])
                res_arr = raw.get("resistance", [])
                support    = sup_arr[0] if sup_arr else None
                resistance = res_arr[0] if res_arr else None

                # BB from indicators
                bb_squeeze_val  = bool(ind.get("bb_squeeze") or False)
                bb_bandwidth_val = ind.get("bb_bandwidth")

                # === Volume spike ===
                volume_spike = 1 if vol_ratio >= 2 else 0

                # === Score: use Bridge confluence if available, else compute ===
                bridge_conf_score = bridge_confluence.get("score", 0)
                if bridge_conf_score > 0:
                    score = bridge_conf_score
                else:
                    vol_sig_proxy = {"signal": "high_volume" if vol_ratio >= 1.5 else "normal", "ratio": vol_ratio}
                    conf_result = _compute_confluence(None, {
                        "daily_ema_cross": daily_ema_cross,
                        "macd_cross": macd_cross,
                        "macd_above_zero": macd_above_zero,
                        "vol_ratio": vol_ratio,
                        "rsi": rsi,
                    })
                    score = conf_result.get("confluence_score", 0)

                if score >= 75: score_class = "A"
                elif score >= 50: score_class = "B"
                elif score >= 30: score_class = "C"
                else: score_class = "D"

                # === Confluence for DB ===
                vol_sig_proxy = {"signal": "high_volume" if vol_ratio >= 1.5 else "normal", "ratio": vol_ratio}
                confluence = _compute_confluence(None, {
                    "daily_ema_cross": daily_ema_cross,
                    "macd_cross": macd_cross,
                    "macd_above_zero": macd_above_zero,
                    "vol_ratio": vol_ratio,
                    "rsi": rsi,
                })

                # === Verdict: smart, based on all data ===
                if score >= 70 and daily_ema_cross == "bullish" and vol_ratio >= 1.2:
                    verdict = "\U0001f525 فرصة قوية"
                elif score >= 50 and daily_ema_cross == "bullish":
                    verdict = "\U0001f7e2 صاعد — مراقبة"
                elif score >= 50 and macd_cross == "bullish":
                    verdict = "\U0001f7e2 زخم صاعد"
                elif score >= 40:
                    verdict = "\U0001f7e1 محايد — انتظار"
                elif daily_ema_cross == "bearish" and score < 40:
                    verdict = "\U0001f534 ضغط بيعي"
                elif rsi and rsi < 30:
                    verdict = "\U0001f7e2 تشبع بيعي — فرصة"
                elif rsi and rsi > 70:
                    verdict = "\U0001f534 تشبع شرائي — حذر"
                else:
                    verdict = "\u26AA محايد"

                conn.execute("""
                    INSERT OR REPLACE INTO stock_radar_daily
                    (symbol, exchange, price, trend, rsi, support, resistance,
                     score, score_class, verdict, volume, vol_ratio, change_pct,
                     source_timeframe, updated_at, ema_fast, ema_slow,
                     macd, macd_signal, macd_histogram, macd_cross,
                     daily_ema9, daily_ema21, daily_ema_cross,
                     confluence_score, confluence_direction,
                     avg_volume, volume_spike, macd_above_zero,
                     stoch_k, adx, rsi_divergence, atr,
                     bb_squeeze, bb_bandwidth)
                    VALUES (?, 'KSE', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '1D', ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?)
                """, (sym, price, trend_ar, rsi, support, resistance,
                      score, score_class, verdict, volume, vol_ratio, change_pct, now,
                      ema9, ema21,
                      macd_val, macd_sig, macd_hist, macd_cross,
                      ema9, ema21, daily_ema_cross,
                      confluence["confluence_score"], confluence["direction"],
                      0, 1 if vol_ratio >= 2 else 0, 1 if macd_above_zero else 0,
                      stoch_k_val, adx_val, rsi_div_val, atr_val,
                      bb_squeeze_val, bb_bandwidth_val))
                ok_count += 1
            except Exception as e:
                logger.warning(f"daily_snapshot skip {sym}: {e}")
                err_count += 1
                continue

        conn.commit()
        conn.close()
        logger.info(f"Daily snapshot refreshed: {ok_count} ok, {err_count} errors")

        # Refresh S/R levels for all symbols from daily data
        try:
            from sr_engine import refresh_sr_for_all
            refresh_sr_for_all()
        except Exception as e:
            logger.warning(f"S/R refresh failed (non-critical): {e}")

        # Fire after_daily_refresh hook
        try:
            from service_health import get_health_hub
            _hub = get_health_hub()
            if _hub:
                _hk = getattr(_hub, '_hooks', None)
                if _hk:
                    _hk.fire_sync("after_daily_refresh",
                        ok_count=ok_count, err_count=err_count)
        except Exception:
            pass
        return {"ok": ok_count, "errors": err_count}
    finally:
        _daily_refresh_lock = False


def get_daily_snapshot(top_n=15, min_score=0):
    """Get stored daily snapshot from DB. Read-only, no fetch."""
    conn = _db()
    rows = conn.execute(
        "SELECT * FROM stock_radar_daily WHERE score >= ? ORDER BY score DESC",
        (min_score,)
    ).fetchall()
    conn.close()
    from tv_data import KSE_STOCKS
    results = []
    for r in rows:
        d = dict(r)
        d["name_ar"] = KSE_STOCKS.get(d["symbol"], d["symbol"])
        try:
            updated = datetime.fromisoformat(d["updated_at"])
            age_hours = (datetime.utcnow() - updated).total_seconds() / 3600
            d["data_age_hours"] = round(age_hours, 1)
            d["is_stale"] = age_hours > 18
            d["freshness"] = "fresh" if age_hours < 6 else "aging" if age_hours < 18 else "stale"
        except Exception:
            d["data_age_hours"] = 999
            d["is_stale"] = True
            d["freshness"] = "stale"
        results.append(d)
    if top_n:
        results = results[:top_n]
    return results


def _daily_snapshot_is_fresh():
    """Daily snapshot is fresh if updated after today's market close (12:40 KWT)."""
    conn = _db()
    try:
        row = conn.execute(
            "SELECT MAX(updated_at) as last_update FROM stock_radar_daily"
        ).fetchone()
    except Exception:
        return False
    finally:
        conn.close()
    if not row or not row["last_update"]:
        return False
    try:
        last = datetime.fromisoformat(row["last_update"])
        kwt_now = datetime.utcnow() + timedelta(hours=3)
        kwt_last = last + timedelta(hours=3)
        # Fresh if updated today after market close
        if kwt_last.date() == kwt_now.date() and kwt_last.hour >= 13:
            return True
        # Also fresh within 4 hours (manual refresh fallback)
        if (datetime.utcnow() - last).total_seconds() < 4 * 3600:
            return True
        return False
    except Exception:
        return False

```


############################################################
# FILE: trading_brain.py (886 lines)
############################################################

```python
"""
trading_brain.py — Signal Learning Engine for Master AI.
Tracks signals, evaluates outcomes against market reality,
learns which indicators work best, and adjusts confluence weights.
"""
import os
import time
import json
import sqlite3
import logging
from datetime import datetime, timedelta, date

logger = logging.getLogger("trading_brain")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")

# Indicators tracked by the brain
INDICATORS = ["rsi", "macd", "ema", "adx", "vol", "stoch"]

# Minimum signals before adjusting weights
MIN_SIGNALS_FOR_ADJUST = 30
ROLLING_WINDOW = 50
WEIGHT_MIN = 0.3
WEIGHT_MAX = 2.0

# Outcome thresholds
DEFAULT_HIT_PCT = 3.0   # 3% move = meaningful
DEFAULT_EVAL_DAYS = 7

# Context injection
_ctx = {}


def init_brain_context(**kwargs):
    _ctx.update(kwargs)


# ═══════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS signal_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    signal_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    trade_state TEXT,
    verdict TEXT,
    verdict_key TEXT,
    confluence_score INTEGER,
    price_at_signal REAL,
    rsi_14 REAL,
    macd_state TEXT,
    macd_momentum TEXT,
    ema_state TEXT,
    adx REAL,
    vol_ratio REAL,
    stoch_k REAL,
    bb_squeeze BOOLEAN,
    rsi_divergence TEXT,
    ema_cross_type TEXT,
    ema_cross_bars_ago INTEGER,
    support REAL,
    resistance REAL,
    atr_14 REAL,
    ind_rsi INTEGER,
    ind_macd INTEGER,
    ind_ema INTEGER,
    ind_adx INTEGER,
    ind_vol INTEGER,
    ind_stoch INTEGER,
    ind_obv INTEGER,
    outcome TEXT DEFAULT 'pending',
    price_1d REAL,
    price_3d REAL,
    price_5d REAL,
    price_7d REAL,
    max_gain_pct REAL,
    max_loss_pct REAL,
    outcome_pct REAL,
    outcome_evaluated_at TIMESTAMP,
    source TEXT DEFAULT 'auto',
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_ss_symbol ON signal_snapshots(symbol);
CREATE INDEX IF NOT EXISTS idx_ss_outcome ON signal_snapshots(outcome);
CREATE INDEX IF NOT EXISTS idx_ss_time ON signal_snapshots(signal_time);

CREATE TABLE IF NOT EXISTS indicator_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator_name TEXT UNIQUE NOT NULL,
    total_signals INTEGER DEFAULT 0,
    total_hits INTEGER DEFAULT 0,
    hit_rate REAL DEFAULT 0.5,
    current_weight REAL DEFAULT 1.0,
    base_weight REAL DEFAULT 1.0,
    last_updated TIMESTAMP,
    rolling_hits INTEGER DEFAULT 0,
    rolling_total INTEGER DEFAULT 0,
    rolling_hit_rate REAL DEFAULT 0.5
);

CREATE TABLE IF NOT EXISTS indicator_regime_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator_name TEXT NOT NULL,
    regime TEXT NOT NULL,
    total_signals INTEGER DEFAULT 0,
    total_hits INTEGER DEFAULT 0,
    smoothed_rate REAL DEFAULT 0.5,
    last_updated TIMESTAMP,
    UNIQUE(indicator_name, regime)
);

CREATE TABLE IF NOT EXISTS brain_weekly_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL,
    week_end TEXT NOT NULL,
    total_signals INTEGER,
    total_evaluated INTEGER,
    hits INTEGER,
    misses INTEGER,
    hit_rate REAL,
    avg_gain_on_hits REAL,
    avg_loss_on_misses REAL,
    best_indicator TEXT,
    best_indicator_rate REAL,
    worst_indicator TEXT,
    worst_indicator_rate REAL,
    weight_adjustments TEXT,
    market_summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_schema():
    with _conn() as c:
        c.executescript(_SCHEMA_SQL)
    # Seed indicator_performance rows
    with _conn() as c:
        for ind in INDICATORS:
            c.execute(
                "INSERT OR IGNORE INTO indicator_performance (indicator_name, total_signals, total_hits, hit_rate, current_weight, base_weight) VALUES (?,0,0,0.5,1.0,1.0)",
                (ind,),
            )
    logger.info("Trading brain schema initialized")


# ═══════════════════════════════════════════════════
# 1. SNAPSHOT SIGNALS
# ═══════════════════════════════════════════════════

def snapshot_signals(signals: list = None):
    """Snapshot current signals from signal_engine. Dedup within 24h per symbol."""
    if signals is None:
        try:
            from signal_engine import build_signals
            result = build_signals()
            signals = result.get("all_signals", [])
        except Exception as e:
            logger.warning("Cannot get signals for snapshot: %s", e)
            return 0

    if not signals:
        return 0

    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    count = 0

    with _conn() as c:
        for sig in signals:
            if (sig.get("confluence_score") or 0) < 50:
                continue  # only track meaningful signals

            sym = sig.get("symbol", "")
            if not sym:
                continue

            # Dedup: skip if pending snapshot exists within 24h
            existing = c.execute(
                "SELECT id FROM signal_snapshots WHERE symbol=? AND outcome='pending' AND signal_time>?",
                (sym, cutoff),
            ).fetchone()
            if existing:
                continue

            ema_cross = sig.get("ema_cross") or {}
            c.execute(
                """INSERT INTO signal_snapshots
                (symbol, trade_state, verdict, verdict_key, confluence_score,
                 price_at_signal, rsi_14, macd_state, macd_momentum, ema_state,
                 adx, vol_ratio, stoch_k, bb_squeeze, rsi_divergence,
                 ema_cross_type, ema_cross_bars_ago, support, resistance, atr_14,
                 ind_rsi, ind_macd, ind_ema, ind_adx, ind_vol, ind_stoch)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    sym,
                    sig.get("trade_state"),
                    sig.get("verdict"),
                    sig.get("verdict_key"),
                    sig.get("confluence_score", 0),
                    sig.get("price"),
                    sig.get("rsi_14"),
                    sig.get("macd_state"),
                    sig.get("macd_momentum"),
                    sig.get("ema_state"),
                    sig.get("adx"),
                    sig.get("vol_ratio"),
                    sig.get("stoch_k"),
                    1 if sig.get("bb_squeeze") else 0,
                    sig.get("rsi_divergence"),
                    ema_cross.get("type"),
                    ema_cross.get("bars_ago"),
                    sig.get("support"),
                    sig.get("resistance"),
                    sig.get("atr_14"),
                    # Individual indicator votes (6 indicators, OBV removed)
                    1 if (sig.get("rsi_14") or 0) > 50 else 0,
                    1 if sig.get("macd_state") == "bullish" else 0,
                    1 if sig.get("ema_state") == "bullish" else 0,
                    1 if (sig.get("adx") or 0) > 25 else 0,
                    1 if (sig.get("vol_ratio") or 0) > 1.0 else 0,
                    1 if (sig.get("stoch_k") or 0) > 50 else 0,
                ),
            )
            count += 1

    if count:
        logger.info("Snapshotted %d signals", count)
    return count


# ═══════════════════════════════════════════════════
# 2. EVALUATE PENDING SIGNALS
# ═══════════════════════════════════════════════════

def evaluate_pending_signals():
    """Evaluate signals that are old enough (>= 7 days). Called daily after market close."""
    cutoff = (datetime.now() - timedelta(days=DEFAULT_EVAL_DAYS)).isoformat()

    with _conn() as c:
        pending = c.execute(
            "SELECT * FROM signal_snapshots WHERE outcome='pending' AND signal_time<=?",
            (cutoff,),
        ).fetchall()

    if not pending:
        return 0

    # Get current prices
    prices = _get_current_prices()
    evaluated = 0

    for row in pending:
        sym = row["symbol"]
        price_at = row["price_at_signal"]
        if not price_at or price_at <= 0:
            continue

        current = prices.get(sym)
        if current is None:
            continue

        change_pct = ((current - price_at) / price_at) * 100
        atr = row["atr_14"] or price_at * 0.03  # fallback 3%
        atr_pct = (atr / price_at) * 100

        # Determine outcome
        hit_threshold = max(atr_pct * 0.5, DEFAULT_HIT_PCT)
        verdict_key = row["verdict_key"] or ""

        if verdict_key in ("buy", "watch"):
            if change_pct >= hit_threshold:
                outcome = "hit"
            elif change_pct <= -hit_threshold:
                outcome = "miss"
            else:
                outcome = "expired"
        elif verdict_key == "avoid":
            if change_pct <= -hit_threshold:
                outcome = "hit"  # correctly predicted weakness
            elif change_pct >= hit_threshold:
                outcome = "miss"
            else:
                outcome = "expired"
        else:
            outcome = "expired"

        with _conn() as c:
            c.execute(
                """UPDATE signal_snapshots SET
                   outcome=?, price_7d=?, outcome_pct=?,
                   max_gain_pct=?, max_loss_pct=?,
                   outcome_evaluated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (
                    outcome,
                    current,
                    round(change_pct, 2),
                    round(max(change_pct, 0), 2),
                    round(min(change_pct, 0), 2),
                    row["id"],
                ),
            )
        evaluated += 1

    if evaluated:
        logger.info("Evaluated %d signals (%d pending were ready)", evaluated, len(pending))
        update_indicator_performance()

    return evaluated


def _get_current_prices() -> dict:
    """Get current prices from radar daily context or bridge cache."""
    prices = {}
    try:
        from stock_radar import _db as _radar_db
        conn = _radar_db()
        rows = conn.execute(
            "SELECT symbol, price, updated_at FROM stock_radar_daily ORDER BY updated_at DESC",
        ).fetchall()
        conn.close()
        for r in rows:
            if r["symbol"] not in prices and r["price"]:
                prices[r["symbol"]] = float(r["price"])
    except Exception as e:
        logger.debug("Radar prices unavailable: %s", e)

    # Fallback: bridge cache
    try:
        from bridge_client import get_bridge_client
        client = get_bridge_client()
        for key, entry in client._cache.items():
            if key.startswith("analysis:"):
                sym = key.split(":")[-1]
                if sym not in prices:
                    data = entry.get("data", {})
                    if data.get("price"):
                        prices[sym] = data["price"]
    except Exception:
        pass

    return prices


# ═══════════════════════════════════════════════════
# HELPER: Bayesian Beta-Binomial smoothed hit rate
# ═══════════════════════════════════════════════════

def _bayesian_hit_rate(hits, total, alpha=5, beta=5):
    """Bayesian smoothed hit rate. Prior = Beta(5,5) = 50% with moderate confidence."""
    return (hits + alpha) / (total + alpha + beta)


def _compute_decay_weight(signal_time_str, half_life_days=90):
    """Recent signals weighted more. Half-life = 90 days (signal from 90d ago = 0.5x weight)."""
    import math
    try:
        sig_time = datetime.fromisoformat(signal_time_str)
        age_days = (datetime.now() - sig_time).days
        return math.exp(-0.693 * age_days / half_life_days)
    except Exception:
        return 0.5


# ═══════════════════════════════════════════════════
# 3. UPDATE INDICATOR PERFORMANCE
# ═══════════════════════════════════════════════════

def update_indicator_performance():
    """Recalculate hit rates and rolling stats for each indicator."""
    with _conn() as c:
        evaluated = c.execute(
            "SELECT * FROM signal_snapshots WHERE outcome IN ('hit','miss') ORDER BY signal_time DESC"
        ).fetchall()

    if not evaluated:
        return

    for ind in INDICATORS:
        col = f"ind_{ind}"
        total           = 0
        hits            = 0
        rolling_total   = 0
        rolling_hits    = 0
        weighted_total  = 0.0
        weighted_hits   = 0.0

        for i, row in enumerate(evaluated):
            vote   = row[col]
            is_hit = row["outcome"] == "hit"
            correct = (vote == 1 and is_hit) or (vote == 0 and not is_hit)

            # Recency decay: recent signals count more
            decay = _compute_decay_weight(row["signal_time"])

            total += 1
            if correct:
                hits += 1

            weighted_total += decay
            if correct:
                weighted_hits += decay

            if i < ROLLING_WINDOW:
                rolling_total += 1
                if correct:
                    rolling_hits += 1

        # Use decay-weighted Bayesian rate as hit_rate; pure Bayesian for rolling
        hit_rate   = _bayesian_hit_rate(weighted_hits, weighted_total)
        rolling_hr = _bayesian_hit_rate(rolling_hits, rolling_total)

        with _conn() as c:
            c.execute(
                """UPDATE indicator_performance SET
                   total_signals=?, total_hits=?, hit_rate=?,
                   rolling_hits=?, rolling_total=?, rolling_hit_rate=?,
                   last_updated=CURRENT_TIMESTAMP
                   WHERE indicator_name=?""",
                (total, hits, round(hit_rate, 4), rolling_hits, rolling_total, round(rolling_hr, 4), ind),
            )

    logger.info("Updated indicator performance for %d indicators", len(INDICATORS))


# ═══════════════════════════════════════════════════
# 4. ADJUST WEIGHTS
# ═══════════════════════════════════════════════════

def adjust_weights() -> dict:
    """Adjust indicator weights based on rolling hit rates. Called weekly."""
    adjustments = {}

    with _conn() as c:
        rows = c.execute("SELECT * FROM indicator_performance").fetchall()

    for row in rows:
        ind = row["indicator_name"]
        if row["rolling_total"] < MIN_SIGNALS_FOR_ADJUST:
            adjustments[ind] = {"old": row["current_weight"], "new": row["current_weight"], "reason": "insufficient_data"}
            continue

        base = row["base_weight"] or 1.0
        rolling_hr = row["rolling_hit_rate"] or 0.5
        new_weight = base * (0.5 + rolling_hr)
        new_weight = max(WEIGHT_MIN, min(WEIGHT_MAX, round(new_weight, 3)))
        old_weight = row["current_weight"]

        with _conn() as c2:
            c2.execute(
                "UPDATE indicator_performance SET current_weight=?, last_updated=CURRENT_TIMESTAMP WHERE indicator_name=?",
                (new_weight, ind),
            )

        adjustments[ind] = {"old": old_weight, "new": new_weight, "hit_rate": rolling_hr}

    logger.info("Weight adjustment: %s", {k: f"{v.get('old',1):.2f}->{v.get('new',1):.2f}" for k, v in adjustments.items()})
    return adjustments


# ═══════════════════════════════════════════════════
# 5. REGIME-AWARE STATS
# ═══════════════════════════════════════════════════

def update_regime_stats():
    """Update indicator performance per market regime."""
    conn = _conn()
    evaluated = conn.execute(
        "SELECT * FROM signal_snapshots WHERE outcome IN ('hit','miss') ORDER BY signal_time DESC"
    ).fetchall()
    conn.close()

    if not evaluated:
        return

    from collections import defaultdict
    stats = defaultdict(lambda: {"hits": 0, "total": 0})

    for row in evaluated:
        adx    = row["adx"] or 0
        regime = "trending" if adx >= 25 else "ranging" if adx <= 20 else "transition"

        for ind in INDICATORS:
            col    = f"ind_{ind}"
            vote   = row[col]
            is_hit = row["outcome"] == "hit"
            correct = (vote == 1 and is_hit) or (vote == 0 and not is_hit)

            key = (ind, regime)
            stats[key]["total"] += 1
            if correct:
                stats[key]["hits"] += 1

    conn = _conn()
    for (ind, regime), val in stats.items():
        smoothed = _bayesian_hit_rate(val["hits"], val["total"])
        conn.execute(
            """INSERT OR REPLACE INTO indicator_regime_stats
               (indicator_name, regime, total_signals, total_hits, smoothed_rate, last_updated)
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (ind, regime, val["total"], val["hits"], round(smoothed, 4)),
        )
    conn.commit()
    conn.close()
    logger.info("Regime stats updated for %d indicator-regime pairs", len(stats))


def _get_regime_weights(regime):
    """Get weights tuned for a specific regime."""
    conn = _conn()
    rows = conn.execute(
        "SELECT indicator_name, smoothed_rate FROM indicator_regime_stats WHERE regime=?",
        (regime,),
    ).fetchall()
    conn.close()
    if len(rows) < len(INDICATORS):
        return None  # not enough data for this regime
    weights = {}
    for r in rows:
        weights[r["indicator_name"]] = round(0.5 + r["smoothed_rate"], 3)
    return weights


# ═══════════════════════════════════════════════════
# 6. ADJUSTED CONFLUENCE (used by signal_engine)
# ═══════════════════════════════════════════════════

def get_adjusted_confluence(signal_data: dict) -> dict:
    """Calculate weighted confluence. Uses regime-aware weights if available,
    fallback to global weights, fallback to simple."""
    adx    = signal_data.get("adx") or 0
    regime = "trending" if adx >= 25 else "ranging" if adx <= 20 else "transition"

    try:
        # Try regime-specific weights first
        weights = _get_regime_weights(regime)
        if not weights:
            weights = get_indicator_weights()  # fallback to global
    except Exception:
        return _fallback_confluence(signal_data)

    votes = {
        "rsi": 1 if (signal_data.get("rsi_14") or 0) > 50 else 0,
        "macd": 1 if signal_data.get("macd_state") == "bullish" else 0,
        "ema": 1 if signal_data.get("ema_state") == "bullish" else 0,
        "adx": 1 if (signal_data.get("adx") or 0) > 25 else 0,
        "vol": 1 if (signal_data.get("vol_ratio") or 0) > 1.0 else 0,
        "stoch": 1 if (signal_data.get("stoch_k") or 0) > 50 else 0,
    }

    weighted_bullish = sum(votes[ind] * weights.get(ind, 1.0) for ind in INDICATORS)
    weighted_total = sum(weights.get(ind, 1.0) for ind in INDICATORS)

    if weighted_total <= 0:
        return _fallback_confluence(signal_data)

    score = int(round((weighted_bullish / weighted_total) * 100))
    bullish = sum(1 for v in votes.values() if v == 1)
    bearish = len(votes) - bullish

    if score >= 70:
        direction = "strong_bullish"
    elif score >= 55:
        direction = "bullish"
    elif score <= 30:
        direction = "strong_bearish"
    elif score <= 45:
        direction = "bearish"
    else:
        direction = "neutral"

    raw_score = int(round((bullish / len(votes)) * 100)) if len(votes) > 0 else 0

    return {
        "score":        score,
        "direction":    direction,
        "bullish":      bullish,
        "bearish":      bearish,
        "total":        len(votes),
        "brain_weighted": True,
        "regime":       regime,
        "raw_score":    raw_score,
        "brain_delta":  score - raw_score,
    }


def _fallback_confluence(signal_data: dict) -> dict:
    """Original simple confluence from signal_engine."""
    signals = signal_data.get("signals") or {}
    conf = signals.get("confluence")
    if isinstance(conf, dict):
        return conf
    return {"score": 0, "direction": "unknown", "bullish": 0, "bearish": 0, "total": 0}


def get_indicator_weights() -> dict:
    """Return current weights as {name: weight}."""
    with _conn() as c:
        rows = c.execute("SELECT indicator_name, current_weight FROM indicator_performance").fetchall()
    return {r["indicator_name"]: r["current_weight"] for r in rows}


def get_optimal_thresholds() -> dict:
    """Calculate optimal thresholds from historical backfill data.
    Returns thresholds for trade state assignment and verdict decisions.
    Falls back to defaults if insufficient data."""
    DEFAULTS = {
        "ready_min_score":  60,
        "ready_min_vol":    1.2,
        "setup_min_score":  40,
        "avoid_max_score":  30,
        "watch_min_score":  50,
    }

    conn = _conn()
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM signal_snapshots WHERE outcome IN ('hit','miss')"
        ).fetchone()[0]

        if total < 100:
            return {**DEFAULTS, "source": "defaults", "data_points": total}

        rows = conn.execute("""
            SELECT confluence_score,
                   COUNT(*) as total,
                   SUM(CASE WHEN outcome='hit' THEN 1 ELSE 0 END) as hits
            FROM signal_snapshots
            WHERE outcome IN ('hit','miss')
            GROUP BY confluence_score
            ORDER BY confluence_score
        """).fetchall()

        score_hits = [(r["confluence_score"], r["hits"], r["total"]) for r in rows]

        # Cumulative from high to low: find where cumulative hit rate crosses thresholds
        cum_hits  = 0
        cum_total = 0
        ready_threshold = DEFAULTS["ready_min_score"]
        setup_threshold = DEFAULTS["setup_min_score"]

        for score, hits, tot in sorted(score_hits, reverse=True):
            cum_hits  += hits
            cum_total += tot
            rate = cum_hits / cum_total if cum_total > 0 else 0

            if rate >= 0.55 and score < ready_threshold:
                ready_threshold = max(score, 35)
            if rate >= 0.45 and score < setup_threshold:
                setup_threshold = max(score, 25)

        # Avoid = cumulative from low where hit rate stays bad
        avoid_threshold = DEFAULTS["avoid_max_score"]
        cum_hits_low  = 0
        cum_total_low = 0
        for score, hits, tot in sorted(score_hits):
            cum_hits_low  += hits
            cum_total_low += tot
            rate = cum_hits_low / cum_total_low if cum_total_low > 0 else 0
            if rate < 0.35:
                avoid_threshold = max(score + 5, 20)

        return {
            "ready_min_score": ready_threshold,
            "ready_min_vol":   1.2,
            "setup_min_score": setup_threshold,
            "avoid_max_score": avoid_threshold,
            "watch_min_score": int((ready_threshold + setup_threshold) / 2),
            "source":          "brain_learned",
            "data_points":     total,
        }

    except Exception as e:
        logger.warning(f"get_optimal_thresholds failed: {e}")
        return {**DEFAULTS, "source": "defaults_error"}
    finally:
        conn.close()


# ═══════════════════════════════════════════════════
# 6. WEEKLY REPORT
# ═══════════════════════════════════════════════════

def generate_weekly_report() -> dict:
    """Generate weekly performance report. Called Friday 14:00 KWT."""
    today = date.today()
    week_start = (today - timedelta(days=7)).isoformat()
    week_end = today.isoformat()

    with _conn() as c:
        week_signals = c.execute(
            "SELECT * FROM signal_snapshots WHERE signal_time>=? AND signal_time<?",
            (week_start, week_end),
        ).fetchall()

        evaluated = [s for s in week_signals if s["outcome"] in ("hit", "miss", "expired")]
        hits = [s for s in evaluated if s["outcome"] == "hit"]
        misses = [s for s in evaluated if s["outcome"] == "miss"]

    total = len(week_signals)
    total_eval = len(evaluated)
    hit_count = len(hits)
    miss_count = len(misses)
    hit_rate = hit_count / total_eval if total_eval > 0 else 0

    avg_gain = sum(s["outcome_pct"] or 0 for s in hits) / len(hits) if hits else 0
    avg_loss = sum(s["outcome_pct"] or 0 for s in misses) / len(misses) if misses else 0

    # Best/worst indicator
    with _conn() as c:
        ind_rows = c.execute("SELECT * FROM indicator_performance ORDER BY rolling_hit_rate DESC").fetchall()

    best = ind_rows[0] if ind_rows else None
    worst = ind_rows[-1] if ind_rows else None

    # Weight adjustments
    adjustments = adjust_weights()

    report = {
        "week_start": week_start,
        "week_end": week_end,
        "total_signals": total,
        "total_evaluated": total_eval,
        "hits": hit_count,
        "misses": miss_count,
        "hit_rate": round(hit_rate, 3),
        "avg_gain_on_hits": round(avg_gain, 2),
        "avg_loss_on_misses": round(avg_loss, 2),
        "best_indicator": best["indicator_name"] if best else None,
        "best_indicator_rate": best["rolling_hit_rate"] if best else None,
        "worst_indicator": worst["indicator_name"] if worst else None,
        "worst_indicator_rate": worst["rolling_hit_rate"] if worst else None,
        "weight_adjustments": adjustments,
    }

    # Save to DB
    with _conn() as c:
        c.execute(
            """INSERT INTO brain_weekly_reports
            (week_start, week_end, total_signals, total_evaluated, hits, misses, hit_rate,
             avg_gain_on_hits, avg_loss_on_misses, best_indicator, best_indicator_rate,
             worst_indicator, worst_indicator_rate, weight_adjustments)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                week_start, week_end, total, total_eval, hit_count, miss_count,
                round(hit_rate, 3), round(avg_gain, 2), round(avg_loss, 2),
                report["best_indicator"], report["best_indicator_rate"],
                report["worst_indicator"], report["worst_indicator_rate"],
                json.dumps(adjustments),
            ),
        )

    logger.info("Weekly report: %d signals, %d evaluated, %.0f%% hit rate", total, total_eval, hit_rate * 100)
    return report


def format_weekly_tg(report: dict) -> str:
    """Format weekly report as Telegram message."""
    adj = report.get("weight_adjustments", {})
    adj_lines = []
    for ind, v in adj.items():
        if isinstance(v, dict) and "old" in v and "new" in v:
            arrow = "\u25b2" if v["new"] > v["old"] else ("\u25bc" if v["new"] < v["old"] else "=")
            adj_lines.append(f"  {ind.upper()}: {v['old']:.2f} \u2192 {v['new']:.2f} {arrow}")

    return (
        f"\U0001f9e0 \u062a\u0642\u0631\u064a\u0631 \u0639\u0642\u0644 \u0627\u0644\u062a\u062f\u0627\u0648\u0644\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4ca \u0625\u0634\u0627\u0631\u0627\u062a: {report['total_signals']} | \u062a\u0642\u064a\u064a\u0645: {report['total_evaluated']}\n"
        f"\u2705 \u0635\u062d\u064a\u062d\u0629: {report['hits']} ({report['hit_rate']*100:.0f}%) | \u274c \u062e\u0627\u0637\u0626\u0629: {report['misses']}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4c8 \u0623\u0641\u0636\u0644: {(report.get('best_indicator') or '?').upper()} ({(report.get('best_indicator_rate') or 0)*100:.0f}%)\n"
        f"\U0001f4c9 \u0623\u0633\u0648\u0623: {(report.get('worst_indicator') or '?').upper()} ({(report.get('worst_indicator_rate') or 0)*100:.0f}%)\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\u2696\ufe0f \u062a\u0639\u062f\u064a\u0644 \u0627\u0644\u0623\u0648\u0632\u0627\u0646:\n" + "\n".join(adj_lines) + "\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4b0 \u0645\u062a\u0648\u0633\u0637 \u0631\u0628\u062d \u0627\u0644\u0635\u062d\u064a\u062d\u0629: {report['avg_gain_on_hits']:+.1f}%\n"
        f"\U0001f4c9 \u0645\u062a\u0648\u0633\u0637 \u062e\u0633\u0627\u0631\u0629 \u0627\u0644\u062e\u0627\u0637\u0626\u0629: {report['avg_loss_on_misses']:.1f}%"
    )


# ═══════════════════════════════════════════════════
# 7. DASHBOARD DATA
# ═══════════════════════════════════════════════════

def get_brain_stats() -> dict:
    """Return brain stats for /dashboard/brain endpoint."""
    with _conn() as c:
        total = c.execute("SELECT COUNT(*) FROM signal_snapshots").fetchone()[0]
        evaluated = c.execute("SELECT COUNT(*) FROM signal_snapshots WHERE outcome IN ('hit','miss','expired')").fetchone()[0]
        hits = c.execute("SELECT COUNT(*) FROM signal_snapshots WHERE outcome='hit'").fetchone()[0]
        pending = c.execute("SELECT COUNT(*) FROM signal_snapshots WHERE outcome='pending'").fetchone()[0]

        ind_rows = c.execute("SELECT * FROM indicator_performance ORDER BY rolling_hit_rate DESC").fetchall()

        recent = c.execute(
            "SELECT symbol, signal_time, verdict, outcome, outcome_pct FROM signal_snapshots WHERE outcome IN ('hit','miss') ORDER BY outcome_evaluated_at DESC LIMIT 10"
        ).fetchall()

        last_report = c.execute(
            "SELECT * FROM brain_weekly_reports ORDER BY created_at DESC LIMIT 1"
        ).fetchone()

    overall_hr = hits / evaluated if evaluated > 0 else 0

    weights = {}
    for r in ind_rows:
        weights[r["indicator_name"]] = {
            "weight": r["current_weight"],
            "hit_rate": r["rolling_hit_rate"],
            "signals": r["rolling_total"],
        }

    recent_evals = []
    for r in recent:
        recent_evals.append({
            "symbol": r["symbol"],
            "signal_time": r["signal_time"],
            "verdict": r["verdict"],
            "outcome": r["outcome"],
            "pct": r["outcome_pct"],
        })

    weekly = None
    if last_report:
        weekly = {
            "hit_rate": last_report["hit_rate"],
            "best_indicator": last_report["best_indicator"],
            "worst_indicator": last_report["worst_indicator"],
            "week_end": last_report["week_end"],
        }

    # Regime stats per indicator
    regime_stats = {}
    try:
        with _conn() as c:
            rrows = c.execute(
                "SELECT * FROM indicator_regime_stats ORDER BY indicator_name, regime"
            ).fetchall()
        for r in rrows:
            ind = r["indicator_name"]
            if ind not in regime_stats:
                regime_stats[ind] = {}
            regime_stats[ind][r["regime"]] = {
                "hits":  r["total_hits"],
                "total": r["total_signals"],
                "rate":  r["smoothed_rate"],
            }
    except Exception:
        pass

    return {
        "brain_active":       True,
        "total_tracked":      total,
        "total_evaluated":    evaluated,
        "overall_hit_rate":   round(overall_hr, 3),
        "pending_count":      pending,
        "indicator_weights":  weights,
        "recent_evaluations": recent_evals,
        "weekly_summary":     weekly,
        "regime_stats":       regime_stats,
        "backfill_count":     _get_backfill_count(),
        "learning_mode":      "bayesian_regime_aware",
    }


def _get_backfill_count():
    """Count historical backfill snapshots."""
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT COUNT(*) as cnt FROM signal_snapshots WHERE source='historical_backfill'"
            ).fetchone()
        return row["cnt"] if row else 0
    except Exception:
        return 0

```


############################################################
# FILE: trading_decision_engine.py (160 lines)
############################################################

```python
"""
trading_decision_engine.py — Entry Timing + Trade Plan.
Converts golden opportunities into actionable trade decisions.

Entry statuses:
  enter_now     — الآن هو الوقت المناسب
  wait_pullback — انتظر رجوع للمنطقة
  watch         — راقب، التأكيد ناقص
  missed        — فات القطار
  avoid         — تجنب
"""
import logging

logger = logging.getLogger("decision_engine")

STATUS_AR = {
    "enter_now":     "🟢 ادخل الآن",
    "wait_pullback": "🟡 انتظر pullback",
    "watch":         "⚪ راقب",
    "missed":        "🔴 فات القطار",
    "avoid":         "⛔ تجنب",
}


def _status(key, score, reasons, trade_plan):
    return {
        "entry_status":    key,
        "entry_status_ar": STATUS_AR.get(key, key),
        "entry_score":     score,
        "reasoning_ar":    reasons,
        "trade_plan":      trade_plan,
    }


def compute_entry_status(opp: dict, profile: dict) -> dict:
    """
    Determine entry timing for an opportunity.

    opp: opportunity dict from golden_engine
         (needs: price, support/key_support, resistance/key_resistance, atr_14,
          current_vol, current_stoch, current_rsi, confidence, win_rate, avg_gain_pct)
    profile: stock_profiles row (key_support, key_resistance, etc.)

    Returns dict with entry_status, entry_status_ar, entry_score, reasoning_ar, trade_plan.
    """
    price = float(opp.get("price") or 0)
    if price <= 0:
        return _status("watch", 30, ["لا يوجد سعر حي"], None)

    # S/R levels — prefer profile (from sr_engine), fallback to live opp
    support    = float(profile.get("key_support")    or opp.get("key_support")    or opp.get("support")    or 0)
    resistance = float(profile.get("key_resistance") or opp.get("key_resistance") or opp.get("resistance") or 0)
    atr        = float(opp.get("atr_14") or opp.get("atr") or price * 0.02)

    # ─── Entry zone ────────────────────────────────────────────
    if support > 0:
        entry_low  = max(support * 0.998, price - atr * 0.8)
        entry_high = min(price + atr * 0.2, support + atr * 1.5)
        # Guard: support far below price → zone becomes inverted; fall back
        if entry_high < entry_low:
            entry_low  = price - atr * 0.5
            entry_high = price + atr * 0.2
    else:
        entry_low  = price - atr * 0.5
        entry_high = price + atr * 0.2

    # ─── Stop loss ─────────────────────────────────────────────
    if support > 0 and entry_low > 0 and (entry_low - support) / entry_low < 0.10:
        # Support is close to entry — place stop just below it
        stop = min(support - atr * 0.6, entry_low - atr * 0.5)
    else:
        # Support far away (or absent) — use tight ATR stop from entry zone
        stop = entry_low - atr * 0.5

    # ─── Targets ───────────────────────────────────────────────
    hist_gain = float(opp.get("avg_gain_pct") or 0)
    target_1  = resistance if resistance > price else price * (1 + max(hist_gain, 3) / 100)
    target_2  = price * (1 + max(hist_gain * 1.5, 5) / 100)
    if resistance > price:
        target_2 = max(target_2, resistance * 1.02)

    # ─── R/R ───────────────────────────────────────────────────
    entry_mid = (entry_low + entry_high) / 2
    risk      = entry_mid - stop
    reward    = target_1 - entry_mid
    rr        = round(reward / risk, 2) if risk > 0 else 0

    trade_plan = {
        "entry_zone_low":   round(entry_low, 3),
        "entry_zone_high":  round(entry_high, 3),
        "entry_mid":        round(entry_mid, 3),
        "stop_loss":        round(stop, 3),
        "stop_distance_pct": round((entry_mid - stop) / entry_mid * 100, 1) if entry_mid > 0 else 0,
        "target_1":         round(target_1, 3),
        "target_2":         round(target_2, 3),
        "rr_ratio":         rr,
    }

    # ─── Indicator readings ────────────────────────────────────
    reasons    = []
    in_zone    = entry_low <= price <= entry_high
    vol_ok     = float(opp.get("current_vol") or opp.get("vol_ratio") or 0) >= 1.2
    stoch      = float(opp.get("current_stoch") or opp.get("stoch_k") or 50)
    rsi        = float(opp.get("current_rsi")   or opp.get("rsi_14") or opp.get("rsi") or 50)
    confidence = float(opp.get("confidence") or 0)

    # ─── Decision logic ────────────────────────────────────────

    # ⛔ AVOID — broken support
    if support > 0 and price < support * 0.99:
        reasons.append("السعر كسر الدعم")
        return _status("avoid", 10, reasons, trade_plan)

    # ⛔ AVOID — poor R/R
    if rr < 1.2:
        reasons.append("العائد/المخاطرة ضعيف ({:.1f}x)".format(rr))
        return _status("avoid", 15, reasons, trade_plan)

    # 🟢 ENTER NOW — full confirmation
    if in_zone and vol_ok and rr >= 1.8 and confidence >= 75:
        reasons.append("السعر داخل منطقة الدخول")
        reasons.append("الحجم يؤكد")
        if stoch < 30:
            reasons.append("Stoch متشبع بيعياً — ارتداد متوقع")
        if rsi < 35:
            reasons.append("RSI متشبع بيعياً")
        reasons.append("R/R {:.1f}x ممتاز".format(rr))
        return _status("enter_now", 90, reasons, trade_plan)

    # 🟢 ENTER NOW — relaxed (strong confidence, volume weak)
    if in_zone and rr >= 2.0 and confidence >= 80:
        reasons.append("السعر بمنطقة الدخول")
        if not vol_ok:
            reasons.append("الحجم مقبول — ادخل بحذر")
        reasons.append("Confidence {:.0f} عالي".format(confidence))
        return _status("enter_now", 80, reasons, trade_plan)

    # 🟡 WAIT PULLBACK — price above zone
    if price > entry_high and rr >= 1.5:
        pct_above = (price - entry_high) / entry_high * 100
        reasons.append("السعر فوق منطقة الدخول بـ{:.1f}%".format(pct_above))
        reasons.append("انتظر رجوع لمنطقة {:.0f}-{:.0f}".format(entry_low, entry_high))
        if resistance > 0 and (resistance - price) / price * 100 < 2:
            reasons.append("المقاومة قريبة — لا تطارد")
        return _status("wait_pullback", 65, reasons, trade_plan)

    # 🔴 MISSED — price near target already
    if resistance > 0 and price >= target_1 * 0.95:
        reasons.append("السعر وصل قرب الهدف")
        reasons.append("الحركة تحققت — فات القطار")
        return _status("missed", 20, reasons, trade_plan)

    # ⚪ WATCH
    reasons.append("النمط جيد بس التأكيد ناقص")
    if not vol_ok:
        reasons.append("الحجم ضعيف — انتظر تأكيد")
    if rr < 1.8:
        reasons.append("R/R {:.1f}x متوسط".format(rr))
    return _status("watch", 50, reasons, trade_plan)

```


############################################################
# FILE: golden_engine.py (970 lines)
############################################################

```python
"""
golden_engine.py — Golden Opportunities Engine.
Matches LIVE market data against historical winning patterns.
Produces ranked opportunities with confidence scores, entry decisions, and Telegram alerts.

Endpoint: GET /api/decisions-now
"""
import os
import math
import sqlite3
import logging
import json
from datetime import datetime

logger = logging.getLogger("golden_engine")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    return c


# ═══════════════════════════════════
# ATOM BUILDER — same atoms as personality engine
# ═══════════════════════════════════

def build_live_atoms(live: dict) -> set:
    """Convert live indicator data into atom set."""
    atoms = set()
    rsi        = float(live.get("rsi_14") or live.get("rsi") or 99)
    vol        = float(live.get("vol_ratio") or 0)
    adx        = float(live.get("adx") or 0)
    stoch      = float(live.get("stoch_k") or 99)
    macd_state = str(live.get("macd_state") or live.get("macd_cross") or "").lower()
    ema_state  = str(live.get("ema_state") or live.get("daily_ema_cross") or "").lower()
    bb_squeeze = live.get("bb_squeeze")
    confluence = float(live.get("confluence_score") or 0)
    price      = float(live.get("price") or 0)
    support    = float(live.get("support") or 0)
    resistance = float(live.get("resistance") or 0)
    atr        = float(live.get("atr_14") or live.get("atr") or 0)

    if rsi < 30:           atoms.add("rsi_lt_30")
    if 30 <= rsi < 45:     atoms.add("rsi_30_45")
    if rsi > 70:           atoms.add("rsi_gt_70")

    if "bullish" in macd_state: atoms.add("macd_bullish")
    if "bearish" in macd_state: atoms.add("macd_bearish")

    if "bullish" in ema_state: atoms.add("ema_bullish")
    if "bearish" in ema_state: atoms.add("ema_bearish")

    if adx >= 25: atoms.add("adx_ge_25")
    if adx < 20:  atoms.add("adx_lt_20")

    if vol >= 1.5: atoms.add("vol_ge_1_5")
    if vol >= 2.0: atoms.add("vol_ge_2")

    if stoch < 20: atoms.add("stoch_lt_20")
    if stoch > 80: atoms.add("stoch_gt_80")

    if bb_squeeze: atoms.add("bb_squeeze")

    if confluence >= 70: atoms.add("confluence_ge_70")

    if price > 0 and support > 0:
        dist = (price - support) / support
        if 0 <= dist <= 0.03: atoms.add("near_support")
        if dist < 0:          atoms.add("below_support")

    if price > 0 and resistance > 0:
        dist = (resistance - price) / resistance
        if 0 <= dist <= 0.03:  atoms.add("near_resistance")
        if price > resistance: atoms.add("above_resistance")

    if price > 0 and atr > 0:
        atr_pct = atr / price
        if atr_pct > 0.03:  atoms.add("high_atr")
        if atr_pct < 0.015: atoms.add("low_atr")

    return atoms


# ═══════════════════════════════════
# MATCHING & SCORING
# ═══════════════════════════════════

def match_pattern(live_atoms: set, pattern_atoms_str: str) -> tuple:
    """Match live atoms against pattern atoms. Returns (match_ratio, matched, missing)."""
    pat_atoms = set(a.strip() for a in pattern_atoms_str.split(",") if a.strip())
    if not pat_atoms:
        return 0, [], []
    matched = [a for a in pat_atoms if a in live_atoms]
    missing = [a for a in pat_atoms if a not in live_atoms]
    ratio = len(matched) / len(pat_atoms)
    return ratio, matched, missing


def calc_confidence(pattern: dict, profile: dict, match_ratio: float) -> float:
    """Calculate confidence score 0-100."""
    wr        = float(pattern.get("win_rate") or 0)
    occ       = int(pattern.get("occurrences") or 0)
    avg_gain  = float(pattern.get("avg_gain_pct") or 0)
    pat_score = float(pattern.get("pattern_score") or 0)
    baseline  = float(profile.get("baseline_win_rate") or 0.3)

    match_score  = match_ratio * 100
    excess       = (wr - baseline) * 100
    wr_score     = max(0, min(100, (excess + 10) / 30 * 100))
    sample_score = min(100, math.log1p(occ) / math.log1p(50) * 100)
    ps_norm      = min(100, pat_score)
    gain_score   = min(100, avg_gain / 12 * 100)

    align = 50
    dom           = str(profile.get("dominant_driver") or "").lower()
    pat_atoms_str = str(pattern.get("pattern_atoms") or "").lower()
    if "stoch"  in dom and "stoch" in pat_atoms_str:  align = 90
    elif "volume" in dom and "vol"  in pat_atoms_str: align = 85
    elif "macd"  in dom and "macd" in pat_atoms_str:  align = 80
    elif "rsi"   in dom and "rsi"  in pat_atoms_str:  align = 80
    elif "ema"   in dom and "ema"  in pat_atoms_str:  align = 75

    confidence = (
        0.35 * match_score +
        0.20 * wr_score +
        0.15 * sample_score +
        0.10 * ps_norm +
        0.10 * gain_score +
        0.10 * align
    )
    return round(max(0, min(100, confidence)), 1)


# ═══════════════════════════════════
# STOP LOSS (simple — trading_decision_engine provides full plan)
# ═══════════════════════════════════

def suggest_stop(live: dict) -> dict:
    price   = float(live.get("price") or 0)
    atr     = float(live.get("atr_14") or live.get("atr") or 0)
    support = float(live.get("support") or 0)
    if price <= 0:
        return {"method": "N/A", "stop_price": None, "distance_pct": None}
    if support > 0 and atr > 0:
        stop = support - 0.5 * atr
        return {"method": "support_atr", "stop_price": round(stop, 3),
                "distance_pct": round((price - stop) / price * 100, 1)}
    if atr > 0:
        stop = price - 1.2 * atr
        return {"method": "atr_only", "stop_price": round(stop, 3),
                "distance_pct": round(1.2 * atr / price * 100, 1)}
    return {"method": "N/A", "stop_price": None, "distance_pct": None}


# ═══════════════════════════════════
# SMART TRADE DECISION (Phase 9)
# ═══════════════════════════════════

def recalc_rr(entry, stop, target):
    """Calculate real R/R from raw prices."""
    if not entry or not stop or not target:
        return None
    if entry <= 0 or stop <= 0 or target <= 0:
        return None
    if entry <= stop:    # stop above entry = error
        return None
    if target <= entry:  # target below entry = error
        return None
    risk = entry - stop
    reward = target - entry
    if risk <= 0:
        return None
    return round(reward / risk, 2)


def choose_best_plan(opp):
    """
    Compare Golden Engine plan vs Strategy Mining plan.
    Returns the best one with: entry, stop, target1, target2, rr, source.
    """
    tp = opp.get("trade_plan") or {}
    sm = opp.get("strategy_match") or {}
    price = float(opp.get("price", 0))

    # --- Golden Engine plan ---
    g_entry = tp.get("entry_mid") or price
    g_stop = tp.get("stop_loss", 0)
    g_t1 = tp.get("target_1", 0)
    g_t2 = tp.get("target_2")
    g_rr = recalc_rr(g_entry, g_stop, g_t1)
    g_stop_pct = ((g_entry - g_stop) / g_entry * 100) if g_entry > 0 and g_stop > 0 else 99

    # --- Strategy Mining plan ---
    s_entry = sm.get("entry_price") or price
    s_stop = sm.get("stop_price", 0) or 0
    s_t1 = sm.get("target_1_price", 0) or 0
    s_t2 = sm.get("target_2_price")
    s_rr = recalc_rr(s_entry, s_stop, s_t1) if s_stop > 0 and s_t1 > 0 else None
    s_stop_pct = ((s_entry - s_stop) / s_entry * 100) if s_entry > 0 and s_stop > 0 else 99

    # --- Scoring ---
    g_score = 0.0
    s_score = 0.0

    # R/R (most important)
    if g_rr and g_rr > 0:
        g_score += min(g_rr, 5) * 25
    if s_rr and s_rr > 0:
        s_score += min(s_rr, 5) * 25

    # Stop distance (1-6% ideal, penalize far stops)
    if 1.0 <= g_stop_pct <= 6.0:
        g_score += 15
    elif g_stop_pct > 6.0:
        g_score -= (g_stop_pct - 6) * 3

    if s_stop_pct and 1.0 <= s_stop_pct <= 6.0:
        s_score += 15
    elif s_stop_pct and s_stop_pct > 6.0:
        s_score -= (s_stop_pct - 6) * 3

    # Strategy win rate + EV
    s_wr = sm.get("profitable_rate", 0)
    s_ev = sm.get("ev", 0)
    if s_wr > 0.55:
        s_score += (s_wr - 0.5) * 100
    if s_ev > 3:
        s_score += min(s_ev, 15) * 3

    # Sample size
    s_n = sm.get("sample_size", 0)
    if s_n >= 50:
        s_score += 10
    elif s_n >= 20:
        s_score += 5

    # --- Pick best ---
    if s_score > g_score and s_rr and s_rr > 0 and s_stop > 0:
        return {
            "source": "strategy",
            "entry": round(s_entry, 3),
            "stop": round(s_stop, 3),
            "target1": round(s_t1, 3),
            "target2": round(s_t2, 3) if s_t2 else None,
            "rr": s_rr,
            "stop_pct": round(s_stop_pct, 1),
        }
    elif g_rr and g_rr > 0 and g_stop > 0:
        return {
            "source": "golden",
            "entry": round(g_entry, 3),
            "stop": round(g_stop, 3),
            "target1": round(g_t1, 3),
            "target2": round(g_t2, 3) if g_t2 else None,
            "rr": g_rr,
            "stop_pct": round(g_stop_pct, 1),
        }
    else:
        return None


def final_trade_decision(opp):
    """
    Single ENTER / WAIT / SKIP decision per stock,
    using all available data.
    """
    plan = choose_best_plan(opp)
    price = float(opp.get("price", 0))
    sm = opp.get("strategy_match") or {}

    if plan is None:
        return {
            "action": "SKIP",
            "action_ar": "\u23ed\ufe0f \u062a\u062c\u0627\u0648\u0632",
            "reason_ar": "\u0643\u0644\u0627 \u0627\u0644\u062e\u0637\u062a\u064a\u0646 \u0641\u064a\u0647\u0645 \u0645\u0634\u0627\u0643\u0644",
            "chosen_plan": None,
        }

    rr = plan["rr"]
    stop_pct = plan["stop_pct"]

    win_rate = sm.get("profitable_rate", 0)
    ev = sm.get("ev", 0)
    pattern_confidence = opp.get("confidence", 0)

    # Is price in entry zone? (within 0.3%)
    in_zone = price > 0 and (plan["entry"] * 0.997 <= price <= plan["entry"] * 1.003)

    # === Decision rules ===

    # ENTER: strong R/R + in zone
    if (rr >= 1.5
            and stop_pct <= 6.0
            and (win_rate >= 0.55 or ev >= 3.0 or pattern_confidence >= 85)
            and in_zone):
        return {
            "action": "ENTER",
            "action_ar": "\U0001f7e2 \u0627\u062f\u062e\u0644",
            "reason_ar": f"\u0627\u0644\u0639\u0627\u0626\u062f/\u0627\u0644\u0645\u062e\u0627\u0637\u0631\u0629 {rr:.1f}x \u0645\u0645\u062a\u0627\u0632\u060c \u0627\u0644\u0633\u0639\u0631 \u0628\u0645\u0646\u0637\u0642\u0629 \u0627\u0644\u062f\u062e\u0648\u0644",
            "chosen_plan": plan,
        }

    # ENTER cautious: high WR compensates moderate R/R
    if (rr >= 1.3
            and stop_pct <= 6.0
            and win_rate >= 0.60
            and ev >= 5.0
            and in_zone):
        return {
            "action": "ENTER",
            "action_ar": "\U0001f7e2 \u0627\u062f\u062e\u0644 \u0628\u062d\u0630\u0631",
            "reason_ar": f"\u0646\u0633\u0628\u0629 \u0627\u0644\u0646\u062c\u0627\u062d \u0639\u0627\u0644\u064a\u0629 ({win_rate:.0%}) \u062a\u0639\u0648\u0636 \u0627\u0644\u0639\u0627\u0626\u062f/\u0627\u0644\u0645\u062e\u0627\u0637\u0631\u0629 ({rr:.1f}x)",
            "chosen_plan": plan,
        }

    # WAIT: good plan but price not there yet
    if (rr >= 1.3
            and (win_rate >= 0.55 or ev >= 3.0)
            and not in_zone):
        trigger = round(plan["entry"], 3)
        return {
            "action": "WAIT",
            "action_ar": "\u23f3 \u0627\u0646\u062a\u0638\u0631",
            "reason_ar": f"\u0627\u0644\u0646\u0645\u0637 \u062d\u0644\u0648 \u2014 \u0627\u0646\u062a\u0638\u0631 \u0627\u0644\u0633\u0639\u0631 \u064a\u0648\u0635\u0644 {trigger}",
            "chosen_plan": plan,
        }

    # WAIT: acceptable R/R, needs confirmation
    if (rr >= 1.2
            and (win_rate >= 0.55 or ev >= 3.0)):
        return {
            "action": "WAIT",
            "action_ar": "\u23f3 \u0627\u0646\u062a\u0638\u0631 \u062a\u0623\u0643\u064a\u062f",
            "reason_ar": f"\u0627\u0644\u0646\u0645\u0637 \u062c\u064a\u062f \u0628\u0633 \u0627\u0644\u0639\u0627\u0626\u062f/\u0627\u0644\u0645\u062e\u0627\u0637\u0631\u0629 {rr:.1f}x \u064a\u062d\u062a\u0627\u062c \u062a\u0623\u0643\u064a\u062f",
            "chosen_plan": plan,
        }

    # SKIP: weak everything
    reason = f"\u0627\u0644\u0639\u0627\u0626\u062f/\u0627\u0644\u0645\u062e\u0627\u0637\u0631\u0629 {rr:.1f}x \u0636\u0639\u064a\u0641"
    if stop_pct > 6:
        reason += f" \u0648\u0627\u0644\u0633\u062a\u0648\u0628 \u0628\u0639\u064a\u062f ({stop_pct:.0f}%)"
    return {
        "action": "SKIP",
        "action_ar": "\u23ed\ufe0f \u062a\u062c\u0627\u0648\u0632",
        "reason_ar": reason,
        "chosen_plan": plan,
    }


# ═══════════════════════════════════
# ARABIC LABELS
# ═══════════════════════════════════

ATOM_AR = {
    "rsi_lt_30": "RSI < 30",       "rsi_30_45": "RSI 30-45",   "rsi_gt_70": "RSI > 70",
    "macd_bullish": "MACD صاعد",   "macd_bearish": "MACD هابط",
    "ema_bullish": "EMA صاعد",     "ema_bearish": "EMA هابط",
    "adx_ge_25": "ADX ≥ 25",       "adx_lt_20": "ADX < 20",
    "vol_ge_1_5": "حجم 1.5x",      "vol_ge_2": "حجم 2x",
    "stoch_lt_20": "Stoch < 20",   "stoch_gt_80": "Stoch > 80",
    "bb_squeeze": "BB ضغط",        "confluence_ge_70": "Confluence ≥ 70",
    "near_support": "قرب دعم",     "near_resistance": "قرب مقاومة",
    "above_resistance": "اختراق",  "below_support": "كسر دعم",
    "high_atr": "تذبذب عالي",      "low_atr": "تذبذب منخفض",
}

def atoms_to_ar(atoms_str: str) -> str:
    return " + ".join(ATOM_AR.get(a.strip(), a.strip()) for a in atoms_str.split(",") if a.strip())


# ═══════════════════════════════════
# STRATEGY MINING — LIVE MATCHING
# ═══════════════════════════════════

def build_mining_atoms(live: dict) -> set:
    """
    Build atoms using the SAME discretisation as Phase 2 mining.
    These atoms must match the ones stored in mined_strategies.pattern_atoms.
    """
    atoms = set()

    # RSI (5 bins — matches mining)
    rsi = live.get("rsi_14") or live.get("rsi")
    if rsi is not None:
        rsi = float(rsi)
        if rsi < 30:      atoms.add("rsi_lt_30")
        elif rsi < 45:    atoms.add("rsi_30_45")
        elif rsi < 55:    atoms.add("rsi_45_55")
        elif rsi < 70:    atoms.add("rsi_55_70")
        else:             atoms.add("rsi_gt_70")

    # MACD state
    macd_state = str(live.get("macd_state") or live.get("macd_cross") or "").lower()
    if "bullish" in macd_state:  atoms.add("macd_bullish")
    elif "bearish" in macd_state: atoms.add("macd_bearish")

    # MACD momentum
    macd_mom = str(live.get("macd_momentum") or "").lower()
    if "accel" in macd_mom:   atoms.add("macd_accel")
    elif "decel" in macd_mom: atoms.add("macd_decel")

    # EMA state
    ema_state = str(live.get("ema_state") or live.get("daily_ema_cross") or "").lower()
    if "bullish" in ema_state:  atoms.add("ema_bullish")
    elif "bearish" in ema_state: atoms.add("ema_bearish")

    # ADX (5 bins)
    adx = live.get("adx")
    if adx is not None:
        adx = float(adx)
        if adx < 15:      atoms.add("adx_lt_15")
        elif adx < 20:    atoms.add("adx_15_20")
        elif adx < 25:    atoms.add("adx_20_25")
        elif adx <= 35:   atoms.add("adx_25_35")
        else:             atoms.add("adx_gt_35")

    # Stochastic (5 bins)
    stoch = live.get("stoch_k")
    if stoch is not None:
        stoch = float(stoch)
        if stoch < 20:    atoms.add("stoch_lt_20")
        elif stoch < 40:  atoms.add("stoch_20_40")
        elif stoch < 60:  atoms.add("stoch_40_60")
        elif stoch < 80:  atoms.add("stoch_60_80")
        else:             atoms.add("stoch_gt_80")

    # Volume ratio (4 bins)
    vol = live.get("vol_ratio")
    if vol is not None:
        vol = float(vol)
        if vol < 0.8:     atoms.add("vol_lt_0_8")
        elif vol < 1.2:   atoms.add("vol_0_8_1_2")
        elif vol < 2.0:   atoms.add("vol_1_2_2_0")
        else:             atoms.add("vol_ge_2")

    # ATR % (3 bins)
    atr = live.get("atr_14") or live.get("atr")
    price = live.get("price")
    if atr and price:
        atr, price = float(atr), float(price)
        if price > 0:
            atr_pct = atr / price * 100
            if atr_pct < 1.5:   atoms.add("low_atr")
            elif atr_pct < 3.0: atoms.add("medium_atr")
            else:               atoms.add("high_atr")

    # BB Squeeze
    if live.get("bb_squeeze"):
        atoms.add("bb_squeeze")

    # Trend direction (from regime classifier)
    # ADX + directional votes → trend_up / trend_down
    adx_val = float(live.get("adx") or 0)
    bull_votes = sum([
        1 if "bullish" in str(live.get("ema_state") or live.get("daily_ema_cross") or "").lower() else 0,
        1 if "bullish" in str(live.get("macd_state") or live.get("macd_cross") or "").lower() else 0,
        1 if "accel" in str(live.get("macd_momentum") or "").lower() else 0,
    ])
    bear_votes = sum([
        1 if "bearish" in str(live.get("ema_state") or live.get("daily_ema_cross") or "").lower() else 0,
        1 if "bearish" in str(live.get("macd_state") or live.get("macd_cross") or "").lower() else 0,
        1 if "decel" in str(live.get("macd_momentum") or "").lower() else 0,
    ])
    if adx_val >= 23:
        if bull_votes >= 2:   atoms.add("trend_up")
        elif bear_votes >= 2: atoms.add("trend_down")

    return atoms


def classify_live_regime(live: dict) -> str:
    """Classify regime from live data — same logic as Phase 2.5."""
    adx = float(live.get("adx") or 0)
    if adx >= 23:
        return "trending"
    elif adx <= 18:
        return "ranging"
    else:
        return "transition"


def match_strategies(live: dict, timeframe: str = "1D", top_n: int = 5) -> list:
    """
    Match live signal against mined strategies.

    Args:
        live: dict with keys rsi_14/rsi, adx, stoch_k, vol_ratio, atr_14/atr,
              macd_state, macd_momentum, ema_state, bb_squeeze, price
        timeframe: '1D' or '30m'
        top_n: max strategies to return

    Returns:
        list of matched strategies sorted by final_score, each with:
        - strategy_id, pattern_ar, ev, target, stop, rr, confidence info
    """
    live_atoms = build_mining_atoms(live)
    regime = classify_live_regime(live)

    if not live_atoms:
        return []

    conn = _conn()
    try:
        rows = conn.execute("""
            SELECT * FROM mined_strategies
            WHERE timeframe = ? AND regime = ?
              AND status IN ('production', 'candidate')
            ORDER BY final_score DESC
        """, (timeframe, regime)).fetchall()
    except Exception as e:
        logger.warning("match_strategies query failed: %s", e)
        return []
    finally:
        conn.close()

    matches = []
    for row in rows:
        try:
            pattern_atoms = set(json.loads(row["pattern_atoms"]))
        except Exception:
            continue

        if not pattern_atoms.issubset(live_atoms):
            continue

        price = float(live.get("price") or 0)
        entry_disc = float(row["entry_discount_pct"] or 0)
        target_1 = float(row["target_1_pct"] or 3)
        target_2 = float(row["target_2_pct"] or 5)
        stop_val = float(row["stop_pct"] or -3)

        entry_price = round(price * (1 + entry_disc / 100), 3) if price > 0 else None
        target_1_price = round(price * (1 + target_1 / 100), 3) if price > 0 else None
        target_2_price = round(price * (1 + target_2 / 100), 3) if price > 0 else None
        stop_price = round(price * (1 + stop_val / 100), 3) if price > 0 else None

        matches.append({
            "strategy_id": row["strategy_id"],
            "pattern_ar": row["pattern_ar"],
            "pattern_atoms": row["pattern_atoms"],
            "timeframe": timeframe,
            "regime": regime,
            "final_score": float(row["final_score"] or 0),
            "ev": float(row["ev"] or 0),
            "profitable_rate": float(row["profitable_rate"] or 0),
            "profit_factor": float(row["profit_factor"] or 0),
            "sample_size": int(row["sample_size"] or 0),
            "stability": float(row["stability"] or 0),
            "p_value": float(row["p_value"] or 1),
            # Trade plan — percentages
            "entry_method": row["entry_method"],
            "target_1_pct": target_1,
            "target_2_pct": target_2,
            "stop_pct": stop_val,
            "rr_ratio": float(row["rr_ratio"] or 0),
            "est_hold_days": float(row["est_hold_days"] or 3),
            # Trade plan — absolute prices
            "entry_price": entry_price,
            "target_1_price": target_1_price,
            "target_2_price": target_2_price,
            "stop_price": stop_price,
            "current_price": price,
        })

    matches.sort(key=lambda x: x["final_score"], reverse=True)
    return matches[:top_n]


# ═══════════════════════════════════
# TELEGRAM ALERTS
# ═══════════════════════════════════

def _read_file(path):
    try:
        p = os.path.expanduser(path)
        with open(p) as f:
            return f.read().strip()
    except Exception:
        return None


def _init_alert_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            pattern_key TEXT,
            entry_status TEXT,
            confidence REAL,
            dedup_key TEXT UNIQUE,
            sent_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def should_alert(conn, opp: dict) -> bool:
    """Return True if this opportunity should trigger a Telegram alert."""
    status = opp.get("entry_status", "")
    if status not in ("enter_now", "wait_pullback"):
        return False
    if opp.get("confidence", 0) < 75:
        return False
    dedup = f"{opp['symbol']}:{opp.get('pattern_atoms', '')}:{status}"
    row = conn.execute("SELECT id FROM alert_history WHERE dedup_key=?", (dedup,)).fetchone()
    return row is None


def record_alert(conn, opp: dict):
    """Record a sent alert to prevent duplicates."""
    dedup = f"{opp['symbol']}:{opp.get('pattern_atoms', '')}:{opp.get('entry_status', '')}"
    conn.execute(
        "INSERT OR IGNORE INTO alert_history (symbol, pattern_key, entry_status, confidence, dedup_key) VALUES (?,?,?,?,?)",
        (opp["symbol"], opp.get("pattern_atoms"), opp.get("entry_status"), opp.get("confidence"), dedup)
    )
    conn.commit()


def send_golden_alert(opp: dict) -> bool:
    """Send a Telegram alert for a golden opportunity."""
    import requests as _req
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN") or _read_file("~/.telegram_bot_token")
    chat_id   = os.environ.get("TELEGRAM_CHAT_ID")   or _read_file("~/.telegram_chat_id")
    if not bot_token or not chat_id:
        return False

    tp = opp.get("trade_plan") or {}

    text = (
        f"🚨 <b>فرصة ذهبية — {opp['symbol']}</b>\n\n"
        f"📊 <b>النمط:</b> {opp.get('pattern_ar', '')}\n"
        f"✅ <b>نسبة نجاح:</b> {opp.get('win_rate', 0):.0f}% ({opp.get('occurrences', 0)} مرة)\n"
        f"{opp.get('entry_status_ar', '')}\n\n"
        f"💰 <b>السعر:</b> {opp.get('price', 0)}\n"
        f"🎯 <b>منطقة الدخول:</b> {tp.get('entry_zone_low', '')} - {tp.get('entry_zone_high', '')}\n"
        f"🛑 <b>وقف:</b> {tp.get('stop_loss', '')} ({tp.get('stop_distance_pct', '')}%)\n"
        f"🏁 <b>هدف 1:</b> {tp.get('target_1', '')}\n"
        f"🏁 <b>هدف 2:</b> {tp.get('target_2', '')}\n"
        f"⚖️ <b>R/R:</b> {tp.get('rr_ratio', 0)}x\n\n"
    )
    reasons = opp.get("reasoning_ar", [])
    if reasons:
        text += "<b>السبب:</b>\n"
        text += "\n".join(f"- {r}" for r in reasons[:4])

    try:
        r = _req.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"Telegram alert failed: {e}")
        return False


# ═══════════════════════════════════
# MAIN ENGINE
# ═══════════════════════════════════

MIN_OCCURRENCES = 8
MIN_WIN_RATE    = 0.55
MIN_MATCH_RATIO = 0.75
MIN_CONFIDENCE  = 65


def scan_opportunities(live_data: list) -> dict:
    """
    Main entry point.
    live_data: list of dicts with live indicator data per symbol.
    Returns ranked opportunities enriched with S/R, entry decisions, and trade plans.
    """
    from trading_decision_engine import compute_entry_status

    conn = _conn()
    _init_alert_table(conn)

    # Load profiles (includes sr_json from sr_engine)
    profiles = {}
    for r in conn.execute("SELECT * FROM stock_profiles").fetchall():
        profiles[r["symbol"]] = dict(r)

    # Load qualifying patterns
    patterns_by_sym = {}
    for r in conn.execute(
        "SELECT * FROM symbol_patterns WHERE occurrences >= ? AND win_rate >= ? ORDER BY pattern_score DESC",
        (MIN_OCCURRENCES, MIN_WIN_RATE)
    ).fetchall():
        sym = r["symbol"]
        if sym not in patterns_by_sym:
            patterns_by_sym[sym] = []
        patterns_by_sym[sym].append(dict(r))

    conn.close()

    all_opportunities = []

    # ── Data Integrity Gate ───────────────────────────
    from data_integrity import DataIntegrityGate
    _gate = DataIntegrityGate()

    for live in live_data:
        sym = (live.get("symbol") or "").upper()
        if not sym or sym not in patterns_by_sym:
            continue

        live_atoms   = build_live_atoms(live)
        profile      = profiles.get(sym, {"baseline_win_rate": 0.3})
        sym_patterns = patterns_by_sym.get(sym, [])

        best_opp = None

        for pat in sym_patterns:
            ratio, matched, missing = match_pattern(live_atoms, pat.get("pattern_atoms", ""))
            if ratio < MIN_MATCH_RATIO:
                continue

            confidence = calc_confidence(pat, profile, ratio)
            if confidence < MIN_CONFIDENCE:
                continue

            if confidence >= 80:
                opp_type = "🔥 فرصة ذهبية"
            elif confidence >= 70:
                opp_type = "🟢 مرشح"
            else:
                opp_type = "🟡 مراقبة"

            opp = {
                "symbol":          sym,
                "name_ar":         profile.get("name_ar") or "",
                "personality_ar":  profile.get("personality_ar") or "",
                "opportunity_type": opp_type,
                "confidence":      confidence,
                "price":           float(live.get("price") or 0),
                "change_pct":      float(live.get("change_pct") or 0),
                "pattern_ar":      atoms_to_ar(pat.get("pattern_atoms", "")),
                "pattern_atoms":   pat.get("pattern_atoms", ""),
                "matched_atoms":   ",".join(matched),
                "missing_atoms":   ",".join(missing),
                "match_ratio":     round(ratio, 2),
                "occurrences":     pat.get("occurrences", 0),
                "hits":            pat.get("hits", 0),
                "win_rate":        round(float(pat.get("win_rate", 0)) * 100, 1),
                "avg_gain_pct":    round(float(pat.get("avg_gain_pct", 0)), 1),
                "pattern_score":   pat.get("pattern_score", 0),
                "current_rsi":     float(live.get("rsi_14") or live.get("rsi") or 0),
                "current_vol":     float(live.get("vol_ratio") or 0),
                "current_adx":     float(live.get("adx") or 0),
                "current_stoch":   float(live.get("stoch_k") or 0),
                "live_atoms":      sorted(list(live_atoms)),
                "stop_loss":       suggest_stop(live),
                "dominant_driver": profile.get("dominant_driver", ""),
                "baseline_wr":     round(float(profile.get("baseline_win_rate", 0)) * 100, 1),
            }

            if best_opp is None or confidence > best_opp["confidence"]:
                best_opp = opp

        if best_opp:
            # ── Data Integrity Gate ────────────────────────────
            sr_json_raw = profile.get("sr_json")
            _sr_parsed = None
            if sr_json_raw:
                try:
                    _sr_parsed = json.loads(sr_json_raw) if isinstance(sr_json_raw, str) else sr_json_raw
                except Exception:
                    pass

            integrity = _gate.check(sym, live, _sr_parsed)
            best_opp["data_quality"]   = integrity["quality_score"]
            best_opp["data_freshness"] = integrity["freshness"]
            best_opp["sr_status"]      = integrity["sr_status"]
            best_opp["gate_decision"]  = integrity["gate_decision"]

            # force_skip → don't add to list at all
            if integrity["gate_decision"] == "force_skip":
                logger.debug("Skipping %s — data quality %d (force_skip)", sym, integrity["quality_score"])
                continue

            # ── Phase 3: Enrich with S/R from profile ──────────
            sr_json = sr_json_raw
            if sr_json:
                try:
                    sr_data = json.loads(sr_json) if isinstance(sr_json, str) else sr_json
                    best_opp["key_support"]          = sr_data.get("key_support")
                    best_opp["key_resistance"]        = sr_data.get("key_resistance")
                    best_opp["support_levels"]        = sr_data.get("support_levels", [])
                    best_opp["resistance_levels"]     = sr_data.get("resistance_levels", [])
                    best_opp["support_touches"]       = sr_data.get("key_support_touches", 0)
                    best_opp["resistance_touches"]    = sr_data.get("key_resistance_touches", 0)
                except Exception:
                    pass

            # Fallback: use live data S/R
            if not best_opp.get("key_support"):
                best_opp["key_support"]    = float(live.get("support") or 0) or None
            if not best_opp.get("key_resistance"):
                best_opp["key_resistance"] = float(live.get("resistance") or 0) or None

            # Also attach atr for decision engine
            best_opp["atr_14"] = float(live.get("atr_14") or live.get("atr") or 0)

            # ── ATR-based fallback S/R when levels are missing ──
            best_opp["fallback_levels"] = False
            if not best_opp.get("key_support") or not best_opp.get("key_resistance"):
                fb = integrity.get("fallback_levels")
                if fb:
                    if not best_opp.get("key_support"):
                        best_opp["key_support"] = fb["stop"]
                    if not best_opp.get("key_resistance"):
                        best_opp["key_resistance"] = fb["target1"]
                    best_opp["fallback_levels"] = True
                    logger.debug("%s using ATR fallback S/R: sup=%s res=%s",
                                 sym, best_opp["key_support"], best_opp["key_resistance"])

            # ── Phase 3: Compute entry decision + trade plan ────
            decision = compute_entry_status(best_opp, profile)
            best_opp["entry_status"]    = decision["entry_status"]
            best_opp["entry_status_ar"] = decision["entry_status_ar"]
            best_opp["entry_score"]     = decision["entry_score"]
            best_opp["reasoning_ar"]    = decision["reasoning_ar"]
            best_opp["trade_plan"]      = decision["trade_plan"]

            # ── Phase 8: Match mined strategies ────────────────
            try:
                strat_matches = match_strategies(live, timeframe="1D", top_n=3)
                if strat_matches:
                    best_strat = strat_matches[0]
                    best_opp["strategy_match"] = {
                        "strategy_id": best_strat.get("strategy_id", ""),
                        "pattern_ar": best_strat.get("pattern_ar", ""),
                        "ev": best_strat.get("ev", 0),
                        "profitable_rate": best_strat.get("profitable_rate", 0),
                        "profit_factor": best_strat.get("profit_factor", 0),
                        "final_score": best_strat.get("final_score", 0),
                        "sample_size": best_strat.get("sample_size", 0),
                        "stability": best_strat.get("stability", 0),
                        "total_matches": len(strat_matches),
                        "target_1_pct": best_strat.get("target_1_pct", 0),
                        "target_2_pct": best_strat.get("target_2_pct", 0),
                        "stop_pct": best_strat.get("stop_pct", 0),
                        "rr_ratio": best_strat.get("rr_ratio", 0),
                        "est_hold_days": best_strat.get("est_hold_days", 0),
                        "entry_price": best_strat.get("entry_price"),
                        "target_1_price": best_strat.get("target_1_price"),
                        "target_2_price": best_strat.get("target_2_price"),
                        "stop_price": best_strat.get("stop_price"),
                    }
                    # Boost confidence if strong strategy match
                    strat_ev = best_strat.get("ev", 0)
                    strat_boost = min(strat_ev * 0.25, 5)  # max +5
                    best_opp["confidence"] = min(
                        best_opp["confidence"] + strat_boost, 99.9
                    )
                else:
                    best_opp["strategy_match"] = None
            except Exception as e:
                logger.warning("Strategy match error for %s: %s", sym, e)
                best_opp["strategy_match"] = None

            # ── Phase 9: Smart Trade Decision ────────────────
            try:
                ftd = final_trade_decision(best_opp)
                best_opp["smart_decision"]    = ftd["action"]
                best_opp["smart_decision_ar"] = ftd["action_ar"]
                best_opp["smart_reason_ar"]   = ftd["reason_ar"]
                best_opp["chosen_plan"]       = ftd["chosen_plan"]

                # Override opportunity_type with smart decision
                if ftd["action"] == "ENTER":
                    best_opp["opportunity_type"] = "\U0001f7e2 \u0627\u062f\u062e\u0644"
                elif ftd["action"] == "WAIT":
                    best_opp["opportunity_type"] = "\u23f3 \u0627\u0646\u062a\u0638\u0631"
                elif ftd["action"] == "SKIP":
                    best_opp["opportunity_type"] = "\u23ed\ufe0f \u062a\u062c\u0627\u0648\u0632"

                # Cap confidence based on decision quality
                if ftd["action"] == "SKIP":
                    best_opp["confidence"] = min(best_opp["confidence"], 60)
                elif ftd["action"] == "WAIT":
                    best_opp["confidence"] = min(best_opp["confidence"], 80)
            except Exception as e:
                logger.warning("Smart decision error for %s: %s", sym, e)

            # ── Data Integrity: downgrade ENTER → WAIT if wait_only ──
            if integrity["gate_decision"] == "wait_only":
                if best_opp.get("smart_decision") == "ENTER":
                    best_opp["smart_decision"]    = "WAIT"
                    best_opp["smart_decision_ar"] = "\u23f3 \u0627\u0646\u062a\u0638\u0631"
                    best_opp["smart_reason_ar"]   = "\u0628\u064a\u0627\u0646\u0627\u062a \u063a\u064a\u0631 \u0645\u0643\u062a\u0645\u0644\u0629 \u2014 \u062c\u0648\u062f\u0629 {}/100".format(integrity["quality_score"])
                    best_opp["opportunity_type"]  = "\u23f3 \u0627\u0646\u062a\u0638\u0631"
                    best_opp["confidence"]        = min(best_opp["confidence"], 75)

            all_opportunities.append(best_opp)

    # ── Phase 3 V10: Risk Gate ────────────────────────
    try:
        from risk_engine import RiskEngine
        from journal_engine import get_open_trades
        _risk = RiskEngine()
        _open_pos = get_open_trades()
        all_opportunities = _risk.apply_risk_gate(all_opportunities, _open_pos)
    except Exception as e:
        logger.warning("Risk gate error (skipped): %s", e)
        # Ensure sector is set even if risk gate fails
        try:
            from sector_map import get_sector
            for opp in all_opportunities:
                if not opp.get("sector"):
                    opp["sector"] = get_sector(opp.get("symbol", ""))
        except Exception:
            pass

    # Sort: ENTER first, then WAIT, then SKIP; within each group by confidence
    action_priority = {"ENTER": 0, "WAIT": 1, "SKIP": 2}
    all_opportunities.sort(
        key=lambda x: (
            action_priority.get(x.get("smart_decision", "SKIP"), 2),
            -x.get("confidence", 0),
        )
    )
    for i, opp in enumerate(all_opportunities):
        opp["rank"] = i + 1

    # ── Phase 4: Telegram alerts for new "enter_now" opps ───────
    alert_conn = _conn()
    _init_alert_table(alert_conn)
    alerts_sent = 0
    for opp in all_opportunities:
        if opp.get("entry_status") == "enter_now" and opp.get("confidence", 0) >= 80:
            if should_alert(alert_conn, opp):
                if send_golden_alert(opp):
                    record_alert(alert_conn, opp)
                    alerts_sent += 1
    alert_conn.close()

    # ── Phase 4 V10: Decision Audit — log ENTER decisions ─────
    try:
        from kse_data_collector import log_decision
        for opp in all_opportunities:
            if opp.get("smart_decision") == "ENTER":
                log_decision(opp)
    except Exception as e:
        logger.warning("Decision audit logging failed: %s", e)

    enter_list = [o for o in all_opportunities if o.get("smart_decision") == "ENTER"]
    wait_list  = [o for o in all_opportunities if o.get("smart_decision") == "WAIT"]
    skip_list  = [o for o in all_opportunities if o.get("smart_decision") == "SKIP"]

    return {
        "generated_at":        datetime.utcnow().isoformat(),
        "total_scanned":       len(live_data),
        "total_opportunities": len(all_opportunities),
        "enter_count":         len(enter_list),
        "wait_count":          len(wait_list),
        "skip_count":          len(skip_list),
        "alerts_sent":         alerts_sent,
        # backward compatible
        "golden_count":        len(enter_list),
        "candidate_count":     len(wait_list),
        "watch_count":         len(skip_list),
        "top_10":              all_opportunities[:10],
        "all_opportunities":   all_opportunities,
    }

```


############################################################
# FILE: sr_engine.py (173 lines)
############################################################

```python
"""
sr_engine.py — Support & Resistance Engine.
Computes S/R levels from swing high/low clustering.
Can use Bridge daily bars or fall back to stock_radar_daily.
"""
import os
import sqlite3
import logging
import json
from datetime import datetime

logger = logging.getLogger("sr_engine")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def init_sr_schema():
    """Add sr columns to stock_profiles if not exist."""
    conn = _conn()
    for col in [
        "ALTER TABLE stock_profiles ADD COLUMN sr_json TEXT",
        "ALTER TABLE stock_profiles ADD COLUMN sr_updated_at TEXT",
    ]:
        try:
            conn.execute(col)
        except Exception:
            pass
    conn.commit()
    conn.close()


def find_pivots(bars, left=3, right=3):
    """Find swing highs and swing lows from OHLC bars."""
    highs = []
    lows  = []
    for i in range(left, len(bars) - right):
        h  = bars[i].get("high") or bars[i].get("h") or 0
        lo = bars[i].get("low")  or bars[i].get("l") or 0

        is_high = all(
            h >= (bars[j].get("high") or bars[j].get("h") or 0)
            for j in range(i - left, i + right + 1) if j != i
        )
        is_low = all(
            lo <= (bars[j].get("low") or bars[j].get("l") or 0)
            for j in range(i - left, i + right + 1) if j != i
        )

        if is_high:
            highs.append({"index": i, "price": round(h, 3),  "volume": bars[i].get("volume", 0)})
        if is_low:
            lows.append({"index":  i, "price": round(lo, 3), "volume": bars[i].get("volume", 0)})

    return highs, lows


def cluster_levels(levels, tolerance_pct=1.5):
    """Group nearby price levels into clusters. Returns sorted by score (strength)."""
    if not levels:
        return []
    levels = sorted(levels, key=lambda x: x["price"])
    clusters = []
    current  = [levels[0]]

    for lev in levels[1:]:
        avg  = sum(x["price"] for x in current) / len(current)
        diff = abs(lev["price"] - avg) / avg * 100 if avg > 0 else 999
        if diff <= tolerance_pct:
            current.append(lev)
        else:
            clusters.append(current)
            current = [lev]
    clusters.append(current)

    result = []
    for cl in clusters:
        avg_p   = round(sum(x["price"] for x in cl) / len(cl), 3)
        touches = len(cl)
        latest  = max(x["index"] for x in cl)
        avg_vol = sum(x.get("volume", 0) for x in cl) / max(1, len(cl))
        # Score: more touches + more recent + more volume = stronger level
        score = round(touches * 3 + (latest * 0.1) + (avg_vol / 1_000_000), 2)
        result.append({
            "price":        avg_p,
            "touches":      touches,
            "score":        score,
            "latest_index": latest,
        })
    return sorted(result, key=lambda x: x["score"], reverse=True)


def compute_sr(symbol, bars, current_price):
    """
    Compute support and resistance for a symbol from OHLC bars.
    Returns dict with key_support, key_resistance, and all levels.
    """
    if not bars or len(bars) < 20:
        return {
            "symbol": symbol, "key_support": None, "key_resistance": None,
            "support_levels": [], "resistance_levels": [],
        }

    pivot_highs, pivot_lows = find_pivots(bars, left=3, right=3)
    sup_clusters = cluster_levels(pivot_lows,  tolerance_pct=1.5)
    res_clusters = cluster_levels(pivot_highs, tolerance_pct=1.5)

    # Nearest support below current price
    sups_below = [s for s in sup_clusters if s["price"] < current_price]
    key_sup    = max(sups_below, key=lambda x: x["price"], default=None)

    # Nearest resistance above current price
    res_above = [r for r in res_clusters if r["price"] > current_price]
    key_res   = min(res_above, key=lambda x: x["price"], default=None)

    return {
        "symbol":                  symbol,
        "current_price":           current_price,
        "key_support":             key_sup["price"]   if key_sup else None,
        "key_support_touches":     key_sup["touches"] if key_sup else 0,
        "key_support_score":       key_sup["score"]   if key_sup else 0,
        "key_resistance":          key_res["price"]   if key_res else None,
        "key_resistance_touches":  key_res["touches"] if key_res else 0,
        "key_resistance_score":    key_res["score"]   if key_res else 0,
        "support_levels":          [s["price"] for s in sup_clusters[:5]],
        "resistance_levels":       [r["price"] for r in res_clusters[:5]],
    }


def refresh_sr_for_all(bridge_data=None):
    """
    Refresh S/R for all symbols.
    bridge_data: dict of {symbol: {bars: [...], price: X}} from Bridge API.
    If None, falls back to support/resistance from stock_radar_daily.
    """
    init_sr_schema()
    conn    = _conn()
    updated = 0

    if bridge_data:
        for sym, data in bridge_data.items():
            bars  = data.get("bars", [])
            price = data.get("price", 0)
            if not bars or not price:
                continue
            sr = compute_sr(sym, bars, price)
            conn.execute(
                "UPDATE stock_profiles SET key_support=?, key_resistance=?, sr_json=?, sr_updated_at=? WHERE symbol=?",
                (sr["key_support"], sr["key_resistance"],
                 json.dumps(sr), datetime.utcnow().isoformat(), sym)
            )
            updated += 1
    else:
        # Fallback: use support/resistance from stock_radar_daily
        rows = conn.execute(
            "SELECT symbol, support, resistance, price FROM stock_radar_daily WHERE support IS NOT NULL"
        ).fetchall()
        for r in rows:
            conn.execute(
                "UPDATE stock_profiles SET key_support=?, key_resistance=? WHERE symbol=?",
                (r["support"], r["resistance"], r["symbol"])
            )
            updated += 1

    conn.commit()
    conn.close()
    logger.info(f"S/R refreshed for {updated} symbols")
    return {"updated": updated}

```


############################################################
# FILE: risk_engine.py (182 lines)
############################################################

```python
"""
risk_engine.py — Risk Gate Engine
Phase 3 of Master Plan V10

Prevents over-concentration, over-trading, and low-liquidity entries.
Runs after Smart Trade Decision, before final ranking.
"""

import os
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger("risk_engine")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=5)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


class RiskEngine:
    """
    Risk gate that modifies opportunities based on portfolio constraints.

    Rules:
    1. Max 2 stocks from the same sector can be ENTER
    2. Max 8 total open positions
    3. No duplicate — if stock already in portfolio, no ENTER
    4. Low liquidity stocks (<5000 KWD daily avg) downgraded to WAIT
    """

    MAX_SAME_SECTOR = 2
    MAX_TOTAL_POSITIONS = 8
    MIN_LIQUIDITY_VALUE = 5000  # KWD daily average

    def apply_risk_gate(self, opportunities: list, open_positions: list = None) -> list:
        """
        Apply risk checks to all opportunities.
        Modifies opportunities in-place (downgrades ENTER → WAIT where needed).
        Returns the same list.

        Args:
            opportunities: list of opportunity dicts from scan_opportunities
            open_positions: list of open trade dicts from journal_engine.get_open_trades()
        """
        from sector_map import get_sector

        if open_positions is None:
            open_positions = []

        # ── Build current portfolio state ────────────────
        portfolio_symbols = set()
        sector_count = {}  # sectors already in portfolio
        for pos in open_positions:
            sym = (pos.get("symbol") or "").upper()
            if sym:
                portfolio_symbols.add(sym)
                sec = get_sector(sym)
                sector_count[sec] = sector_count.get(sec, 0) + 1

        total_open = len(open_positions)

        # Track how many new ENTERs per sector we're allowing
        enter_by_sector = {}

        for opp in opportunities:
            sym = (opp.get("symbol") or "").upper()

            # Attach sector to every opportunity
            sec = get_sector(sym)
            opp["sector"] = sec

            # Only check ENTER decisions
            if opp.get("smart_decision") != "ENTER":
                continue

            # ── Check 1: Duplicate position ──────────────
            if sym in portfolio_symbols:
                self._downgrade(opp, "duplicate_position",
                                "عندك مركز مفتوح بنفس السهم")
                continue

            # ── Check 2: Max total positions ─────────────
            new_enters_total = sum(enter_by_sector.values())
            if total_open + new_enters_total >= self.MAX_TOTAL_POSITIONS:
                self._downgrade(opp, "max_positions",
                                f"المحفظة مليانة — {total_open} مركز مفتوح (الحد {self.MAX_TOTAL_POSITIONS})")
                continue

            # ── Check 3: Sector concentration ────────────
            existing_in_sector = sector_count.get(sec, 0)
            new_in_sector = enter_by_sector.get(sec, 0)
            if existing_in_sector + new_in_sector >= self.MAX_SAME_SECTOR:
                self._downgrade(opp, "sector_concentration",
                                f"تركّز بقطاع {sec} — عندك {existing_in_sector} مركز + {new_in_sector} جديد")
                continue

            # ── Check 4: Liquidity ───────────────────────
            avg_value = self._get_avg_daily_value(sym)
            if avg_value is not None and avg_value < self.MIN_LIQUIDITY_VALUE:
                self._downgrade(opp, "low_liquidity",
                                f"سيولة ضعيفة — متوسط التداول {avg_value:,.0f} د.ك/يوم")
                continue

            # ✅ Passed all checks — allow ENTER
            enter_by_sector[sec] = enter_by_sector.get(sec, 0) + 1

        return opportunities

    def _downgrade(self, opp: dict, flag: str, reason_ar: str):
        """Downgrade ENTER → WAIT with risk flag."""
        opp["smart_decision"]    = "WAIT"
        opp["smart_decision_ar"] = "\u23f3 \u0627\u0646\u062a\u0638\u0631"
        opp["smart_reason_ar"]   = reason_ar
        opp["opportunity_type"]  = "\u23f3 \u0627\u0646\u062a\u0638\u0631"
        opp["risk_flag"]         = flag
        opp["confidence"]        = min(opp.get("confidence", 0), 75)
        logger.info("Risk gate: %s downgraded to WAIT (%s): %s",
                     opp.get("symbol"), flag, reason_ar)

    def _get_avg_daily_value(self, symbol: str):
        """
        Get average daily traded value (KWD) for a symbol.
        Uses avg_volume × price from stock_radar_daily.
        Returns KWD value or None if unavailable.
        """
        try:
            with _conn() as c:
                row = c.execute(
                    "SELECT price, avg_volume, volume FROM stock_radar_daily WHERE symbol=? ORDER BY rowid DESC LIMIT 1",
                    (symbol.upper(),),
                ).fetchone()
                if row:
                    price = float(row["price"] or 0)
                    avg_vol = float(row["avg_volume"] or row["volume"] or 0)
                    if price > 0 and avg_vol > 0:
                        # price is in fils (1 KWD = 1000 fils)
                        return (price * avg_vol) / 1000.0  # KWD
        except Exception as e:
            logger.debug("Avg daily value lookup failed for %s: %s", symbol, e)
        return None


def calculate_position_risk(entry_price: float, stop_loss: float, target: float = 0,
                            capital: float = 1000) -> dict:
    """
    Calculate risk/reward and position size for a trade.
    Safe against ZeroDivisionError when entry == stop.
    """
    if not entry_price or entry_price <= 0:
        return {"error": "invalid entry_price", "risk_reward": 0, "position_size": 0}
    if not stop_loss or stop_loss <= 0:
        return {"error": "invalid stop_loss", "risk_reward": 0, "position_size": 0}
    if abs(entry_price - stop_loss) < 0.001:
        return {"error": "entry equals stop loss", "risk_reward": 0, "position_size": 0}

    risk = abs(entry_price - stop_loss)
    risk_pct = (risk / entry_price) * 100
    reward = abs(target - entry_price) if target and target > entry_price else 0
    rr = round(reward / risk, 2) if risk > 0 else 0

    # Position size: risk 1% of capital
    risk_amount = capital * 0.01
    position_size = int(risk_amount / risk) if risk > 0 else 0

    return {
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "target": target,
        "risk_per_share": round(risk, 3),
        "risk_pct": round(risk_pct, 2),
        "reward_per_share": round(reward, 3),
        "risk_reward": rr,
        "position_size": position_size,
        "capital_at_risk": round(risk * position_size, 2),
    }

```


############################################################
# FILE: journal_engine.py (452 lines)
############################################################

```python
"""
journal_engine.py — Trading Journal for Master AI V12
Tables in life.db: trades
"""
import os
import sqlite3
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger("journal")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")

# ═══════════════════════════════════════════════════
# DB SCHEMA
# ═══════════════════════════════════════════════════

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    name_ar TEXT,
    direction TEXT NOT NULL DEFAULT 'long',
    status TEXT NOT NULL DEFAULT 'open',
    entry_price REAL NOT NULL,
    entry_date TEXT NOT NULL,
    entry_reason TEXT,
    entry_signal_id INTEGER,
    quantity INTEGER DEFAULT 0,
    exit_price REAL,
    exit_date TEXT,
    exit_reason TEXT,
    pnl_fils REAL,
    pnl_pct REAL,
    strategy TEXT,
    timeframe TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(entry_date);
"""


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_schema():
    with _conn() as c:
        c.executescript(_SCHEMA_SQL)
        # Migration: add stop_loss/take_profit columns if missing
        cols = [r[1] for r in c.execute("PRAGMA table_info(trades)").fetchall()]
        if "stop_loss" not in cols:
            c.execute("ALTER TABLE trades ADD COLUMN stop_loss REAL")
        if "take_profit" not in cols:
            c.execute("ALTER TABLE trades ADD COLUMN take_profit REAL")
    logger.info("journal schema initialized")

    # Phase 2: Position engine schema (new columns + position_alerts table)
    try:
        from position_engine import init_position_schema
        init_position_schema()
    except Exception as e:
        logger.warning("position_engine schema init skipped: %s", e)


def _row_to_dict(row):
    if row is None:
        return None
    return dict(row)


# ═══════════════════════════════════════════════════
# P&L CALCULATOR — KWD with Broker Fees
# ═══════════════════════════════════════════════════

def calculate_real_pnl(entry_price_fils, current_price_fils, quantity, broker_fee_pct=0.125):
    """Calculate real P&L with broker commission.
    KSE broker fee: ~0.125% per trade (entry + exit = 0.25% total)
    Prices in fils. Returns dict with KWD and fils values.
    """
    entry_total_fils = entry_price_fils * quantity
    current_total_fils = current_price_fils * quantity

    # Broker fees (entry + estimated exit)
    entry_fee_fils = entry_total_fils * (broker_fee_pct / 100)
    exit_fee_fils = current_total_fils * (broker_fee_pct / 100)
    total_fees_fils = entry_fee_fils + exit_fee_fils

    # Net P&L
    gross_pnl_fils = current_total_fils - entry_total_fils
    net_pnl_fils = gross_pnl_fils - total_fees_fils

    # Convert to KWD
    gross_pnl_kwd = gross_pnl_fils / 1000
    net_pnl_kwd = net_pnl_fils / 1000
    entry_total_kwd = entry_total_fils / 1000
    current_total_kwd = current_total_fils / 1000

    # Percentages
    pnl_pct = ((current_price_fils / entry_price_fils) - 1) * 100 if entry_price_fils else 0
    net_pnl_pct = (net_pnl_fils / entry_total_fils) * 100 if entry_total_fils else 0

    return {
        "entry_total_kwd": round(entry_total_kwd, 3),
        "current_total_kwd": round(current_total_kwd, 3),
        "gross_pnl_fils": round(gross_pnl_fils),
        "gross_pnl_kwd": round(gross_pnl_kwd, 3),
        "net_pnl_fils": round(net_pnl_fils),
        "net_pnl_kwd": round(net_pnl_kwd, 3),
        "pnl_pct": round(pnl_pct, 2),
        "net_pnl_pct": round(net_pnl_pct, 2),
        "total_fees_kwd": round(total_fees_fils / 1000, 3),
        "broker_fee_pct": broker_fee_pct,
    }


# ═══════════════════════════════════════════════════
# CORE FUNCTIONS
# ═══════════════════════════════════════════════════

def open_trade(symbol, entry_price, quantity=0, entry_reason="",
               strategy="manual", timeframe="1D", direction="long",
               name_ar="", entry_signal_id=None, stop_loss=None, take_profit=None):
    """Open a new trade. Returns trade_id."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = date.today().isoformat()
    with _conn() as c:
        c.execute("""INSERT INTO trades
            (symbol, name_ar, direction, status, entry_price, entry_date,
             entry_reason, entry_signal_id, quantity, strategy, timeframe,
             stop_loss, take_profit, created_at)
            VALUES (?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol.upper(), name_ar, direction, entry_price, today,
             entry_reason, entry_signal_id, quantity, strategy, timeframe,
             stop_loss, take_profit, now))
        trade_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    logger.info("Opened trade #%d: %s @ %s", trade_id, symbol, entry_price)
    return trade_id


def close_trade(trade_id, exit_price, exit_reason="manual"):
    """Close a trade. Calculates P&L. Returns updated trade dict."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = date.today().isoformat()
    with _conn() as c:
        row = c.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
        if not row:
            return None
        trade = dict(row)
        if trade["status"] != "open":
            return None

        entry = trade["entry_price"]
        qty = trade["quantity"] or 0
        direction = trade["direction"]

        if direction == "long":
            pnl_fils = (exit_price - entry) * qty if qty else (exit_price - entry)
            pnl_pct = ((exit_price - entry) / entry * 100) if entry else 0
        else:
            pnl_fils = (entry - exit_price) * qty if qty else (entry - exit_price)
            pnl_pct = ((entry - exit_price) / entry * 100) if entry else 0

        c.execute("""UPDATE trades SET
            status='closed', exit_price=?, exit_date=?, exit_reason=?,
            pnl_fils=?, pnl_pct=?, updated_at=?
            WHERE id=?""",
            (exit_price, today, exit_reason, round(pnl_fils, 2),
             round(pnl_pct, 2), now, trade_id))

        trade.update({
            "status": "closed", "exit_price": exit_price, "exit_date": today,
            "exit_reason": exit_reason, "pnl_fils": round(pnl_fils, 2),
            "pnl_pct": round(pnl_pct, 2), "updated_at": now,
        })
    logger.info("Closed trade #%d: %s @ %s → %s (%.2f%%)",
                trade_id, trade["symbol"], entry, exit_price, pnl_pct)
    return trade


def cancel_trade(trade_id):
    """Cancel a trade (never executed)."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        row = c.execute("SELECT * FROM trades WHERE id=? AND status='open'", (trade_id,)).fetchone()
        if not row:
            return None
        c.execute("UPDATE trades SET status='cancelled', updated_at=? WHERE id=?", (now, trade_id))
    return True


def get_open_trades():
    """Get all open trades. Returns list of dicts."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM trades WHERE status='open' ORDER BY entry_date DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_trades(limit=20):
    """Get recent trades (all statuses). Returns list of dicts."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_trade(trade_id):
    """Get single trade by ID."""
    with _conn() as c:
        row = c.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
    return dict(row) if row else None


def update_trade_notes(trade_id, notes):
    """Add/update notes on a trade."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        c.execute("UPDATE trades SET notes=?, updated_at=? WHERE id=?",
                  (notes, now, trade_id))
    return True


def update_trade_levels(trade_id, stop_loss=None, take_profit=None):
    """Update stop loss and/or take profit on an open trade."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as c:
        row = c.execute("SELECT id, status FROM trades WHERE id=?", (trade_id,)).fetchone()
        if not row or row["status"] != "open":
            return None
        updates = []
        params = []
        if stop_loss is not None:
            updates.append("stop_loss=?")
            params.append(stop_loss)
        if take_profit is not None:
            updates.append("take_profit=?")
            params.append(take_profit)
        if not updates:
            return None
        updates.append("updated_at=?")
        params.append(now)
        params.append(trade_id)
        c.execute(f"UPDATE trades SET {','.join(updates)} WHERE id=?", params)
    logger.info("Updated trade #%d levels: SL=%s TP=%s", trade_id, stop_loss, take_profit)
    return True


def get_fresh_price(symbol):
    """Get freshest price: bridge cache → stock_radar_daily fallback."""
    import time as _t
    # 1. Try bridge cache
    try:
        from bridge_client import get_bridge_client
        client = get_bridge_client()
        for key, entry in client._cache.items():
            if key.startswith("analysis:") and key.split(":")[-1] == symbol.upper():
                age = _t.time() - entry.get("ts", 0)
                data = entry.get("data", {})
                price = data.get("price")
                if price:
                    return {"price": price, "source": "bridge", "stale": age > 300}
    except Exception:
        pass
    # 1b. Direct Bridge HTTP quote (live)
    try:
        import urllib.request as _urlreq, json as _json
        _quote_url = f"http://192.168.111.158:8059/quote?symbol={symbol.upper()}"
        with _urlreq.urlopen(_quote_url, timeout=5) as _resp:
            _qdata = _json.loads(_resp.read().decode())
        _qprice = _qdata.get("price")
        if _qprice:
            return {"price": float(_qprice), "source": "bridge_live", "stale": False}
    except Exception:
        pass
    # 2. Fallback: stock_radar_daily
    try:
        db = sqlite3.connect(DB_PATH, timeout=3)
        db.row_factory = sqlite3.Row
        row = db.execute(
            "SELECT price FROM stock_radar_daily WHERE symbol=? ORDER BY rowid DESC LIMIT 1",
            (symbol.upper(),)
        ).fetchone()
        db.close()
        if row:
            return {"price": float(row["price"]), "source": "radar_daily", "stale": True}
    except Exception:
        pass
    return {"price": None, "source": "none", "stale": True}


def get_trade_stats(days=30):
    """Get trading statistics for the last N days."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    with _conn() as c:
        all_trades = c.execute(
            "SELECT * FROM trades WHERE entry_date >= ?", (cutoff,)
        ).fetchall()

    trades = [dict(r) for r in all_trades]
    closed = [t for t in trades if t["status"] == "closed"]
    open_t = [t for t in trades if t["status"] == "open"]
    wins = [t for t in closed if (t["pnl_pct"] or 0) > 0]
    losses = [t for t in closed if (t["pnl_pct"] or 0) <= 0]

    total_pnl = sum(t.get("pnl_fils", 0) or 0 for t in closed)
    avg_profit = (sum(t["pnl_pct"] for t in wins) / len(wins)) if wins else 0
    avg_loss = (sum(t["pnl_pct"] for t in losses) / len(losses)) if losses else 0

    best = max(closed, key=lambda t: t.get("pnl_pct", 0)) if closed else None
    worst = min(closed, key=lambda t: t.get("pnl_pct", 0)) if closed else None

    return {
        "days": days,
        "total_trades": len(trades),
        "open_trades": len(open_t),
        "closed_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(closed)) if closed else 0,
        "avg_profit_pct": round(avg_profit, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "total_pnl_fils": round(total_pnl, 2),
        "best_trade": {"symbol": best["symbol"], "pnl_pct": best["pnl_pct"]} if best else None,
        "worst_trade": {"symbol": worst["symbol"], "pnl_pct": worst["pnl_pct"]} if worst else None,
    }


# ═══════════════════════════════════════════════════
# WEEKLY PERFORMANCE REPORT
# ═══════════════════════════════════════════════════

def generate_weekly_report():
    """Generate weekly trading performance report.
    Covers last 7 days of trading activity + radar signal stats.
    Returns dict suitable for Telegram message or dashboard.
    """
    stats_7d = get_trade_stats(days=7)

    # Closed trades this week with KWD P&L
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM trades WHERE exit_date >= ? AND status='closed' ORDER BY exit_date DESC",
            (cutoff,)
        ).fetchall()
    closed_this_week = [dict(r) for r in rows]

    # Calculate KWD totals
    total_net_kwd = 0
    trades_detail = []
    for t in closed_this_week:
        entry = float(t.get("entry_price", 0))
        exit_p = float(t.get("exit_price", 0))
        qty = int(t.get("quantity", 0))
        if entry and exit_p and qty:
            pnl = calculate_real_pnl(entry, exit_p, qty)
            total_net_kwd += pnl["net_pnl_kwd"]
            trades_detail.append({
                "symbol": t["symbol"],
                "name_ar": t.get("name_ar", t["symbol"]),
                "net_pnl_kwd": pnl["net_pnl_kwd"],
                "pnl_pct": pnl["pnl_pct"],
            })

    # Radar signal stats (from stock_radar_events)
    signal_stats = {"total": 0, "bullish": 0, "bearish": 0}
    try:
        import sqlite3 as _sq3
        _conn2 = _sq3.connect(DB_PATH, timeout=5)
        _conn2.row_factory = _sq3.Row
        cutoff_dt = (date.today() - timedelta(days=7)).isoformat()
        sig_rows = _conn2.execute(
            "SELECT signal_type, COUNT(*) as cnt FROM stock_radar_events "
            "WHERE created_at >= ? GROUP BY signal_type", (cutoff_dt,)
        ).fetchall()
        for r in sig_rows:
            cnt = r["cnt"]
            signal_stats["total"] += cnt
            if "bullish" in r["signal_type"]:
                signal_stats["bullish"] += cnt
            elif "bearish" in r["signal_type"]:
                signal_stats["bearish"] += cnt

        # Top stocks by score this week
        top_stocks = _conn2.execute("""
            SELECT symbol, MAX(score) as max_score, COUNT(*) as signals
            FROM stock_radar_events WHERE created_at >= ? AND score > 0
            GROUP BY symbol ORDER BY max_score DESC LIMIT 5
        """, (cutoff_dt,)).fetchall()
        signal_stats["top_stocks"] = [{"symbol": r["symbol"], "max_score": r["max_score"],
                                        "signals": r["signals"]} for r in top_stocks]
        _conn2.close()
    except Exception:
        signal_stats["top_stocks"] = []

    # Date range
    end_date = date.today()
    start_date = end_date - timedelta(days=6)

    return {
        "period": f"{start_date.isoformat()} — {end_date.isoformat()}",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "stats": stats_7d,
        "total_net_kwd": round(total_net_kwd, 3),
        "trades_detail": trades_detail,
        "signal_stats": signal_stats,
        "confirmed_from_signals": stats_7d.get("total_trades", 0),
    }


def format_weekly_report_tg(report):
    """Format weekly report for Telegram message."""
    s = report["stats"]
    ss = report["signal_stats"]
    lines = [
        f"\U0001f4ca \u062a\u0642\u0631\u064a\u0631 \u0627\u0644\u062a\u062f\u0627\u0648\u0644 \u0627\u0644\u0623\u0633\u0628\u0648\u0639\u064a \u2014 {report['period']}",
        "",
        "\U0001f4c8 \u0627\u0644\u0623\u062f\u0627\u0621:",
        f"  \u0635\u0641\u0642\u0627\u062a: {s.get('closed_trades', 0)} ({s.get('wins', 0)} \u0641\u0648\u0632, {s.get('losses', 0)} \u062e\u0633\u0627\u0631\u0629) \u2014 {round(s.get('win_rate', 0) * 100)}% win rate",
        f"  \u0627\u0644\u0631\u0628\u062d \u0627\u0644\u0635\u0627\u0641\u064a: {'+' if report['total_net_kwd'] >= 0 else ''}{report['total_net_kwd']} \u062f.\u0643",
    ]
    # Best/worst
    if s.get("best_trade"):
        lines.append(f"  \u0623\u0641\u0636\u0644 \u0635\u0641\u0642\u0629: {s['best_trade']['symbol']} {'+' if s['best_trade']['pnl_pct'] >= 0 else ''}{s['best_trade']['pnl_pct']}%")
    if s.get("worst_trade"):
        lines.append(f"  \u0623\u0633\u0648\u0623 \u0635\u0641\u0642\u0629: {s['worst_trade']['symbol']} {s['worst_trade']['pnl_pct']}%")
    lines.append("")
    lines.append("\U0001f4e1 \u0627\u0644\u0631\u0627\u062f\u0627\u0631:")
    lines.append(f"  \u0625\u0634\u0627\u0631\u0627\u062a: {ss['total']} ({ss['bullish']} \u0635\u0627\u0639\u062f, {ss['bearish']} \u0647\u0627\u0628\u0637)")
    if ss.get("top_stocks"):
        lines.append("")
        lines.append("\U0001f3c6 \u0623\u0641\u0636\u0644 \u0623\u0633\u0647\u0645 \u0627\u0644\u0623\u0633\u0628\u0648\u0639:")
        for i, ts in enumerate(ss["top_stocks"][:3], 1):
            lines.append(f"  {i}. {ts['symbol']} \u2014 Score {ts['max_score']}, {ts['signals']} \u0625\u0634\u0627\u0631\u0629")
    # Market sentiment
    if ss["total"] > 0:
        bull_pct = round(ss["bullish"] / ss["total"] * 100)
        lines.append("")
        lines.append(f"\U0001f4ca \u0627\u0644\u0633\u0648\u0642 \u0628\u0634\u0643\u0644 \u0639\u0627\u0645: {'صاعد' if bull_pct > 55 else 'هابط' if bull_pct < 45 else 'محايد'} ({bull_pct}% \u0625\u0634\u0627\u0631\u0627\u062a \u0635\u0627\u0639\u062f\u0629)")
    return chr(10).join(lines)

```


############################################################
# FILE: bridge_client.py (440 lines)
############################################################

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

BRIDGE_BASE_URL = "http://192.168.111.158:8059"
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

```


############################################################
# FILE: dashboard_api.py (2762 lines)
############################################################

```python
"""
dashboard_api.py — HA Dashboard API endpoints (FastAPI Router)
Extracted from server.py v8.3.0
"""
import os
import time
import json
import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from collections import deque
from fastapi import APIRouter, Request

from priority_engine import (
    build_priority_engine, build_assistant_surface,
    _pe_get_extended_snapshot, _pe_get_radar_snapshot,
)

logger = logging.getLogger("dashboard_api")

router = APIRouter()

# Server context — populated by server.py at startup via init_dashboard_context()
_ctx = {}

def init_dashboard_context(version, start_time, dashboard_jobs, tg_handle_command_fn,
                           radar_ok, journal_ok, get_open_trades_fn, get_trade_stats_fn):
    """Called by server.py to inject shared state."""
    global _ctx
    _ctx = {
        "version": version,
        "start_time": start_time,
        "dashboard_jobs": dashboard_jobs,
        "tg_handle_command": tg_handle_command_fn,
        "radar_ok": radar_ok,
        "journal_ok": journal_ok,
        "get_open_trades": get_open_trades_fn,
        "get_trade_stats": get_trade_stats_fn,
    }


# ═══════════════════════════════════════════════════
# Room entity helpers
# ═══════════════════════════════════════════════════

_ROOM_ENTITIES = None

def _load_room_entities():
    global _ROOM_ENTITIES
    if _ROOM_ENTITIES is not None:
        return _ROOM_ENTITIES
    import json as _j
    try:
        em = _j.load(open(os.path.join(os.path.dirname(__file__), "entity_map.json")))
    except Exception:
        em = {}
    mapping = {}
    for room, ents in em.items():
        rn = room.split("/")[0].strip()
        lights, climates, covers = [], [], []
        for e in ents:
            eid = e.split("=")[0]
            if eid.startswith("light."):
                lights.append(eid)
            elif eid.startswith("climate."):
                climates.append(eid)
            elif eid.startswith("cover.") and "_inverted" in eid:
                covers.append(eid)
        if lights or climates or covers:
            mapping[rn] = {"lights": lights, "climates": climates, "covers": covers}
    _ROOM_ENTITIES = mapping
    return mapping

def _build_rooms_summary(states):
    if not states:
        return []
    mapping = _load_room_entities()
    state_map = {s["entity_id"]: s for s in states}
    rooms = []
    for rn, ents in mapping.items():
        lo = sum(1 for eid in ents["lights"] if state_map.get(eid, {}).get("state") == "on" and "backlight" not in eid)
        lt = len([eid for eid in ents["lights"] if "backlight" not in eid])
        ac_state = "off"
        ac_temp = None
        ac_target = None
        for eid in ents["climates"]:
            st = state_map.get(eid, {})
            attrs = st.get("attributes", {})
            cur_t = attrs.get("current_temperature")
            if cur_t is not None:
                ac_temp = cur_t
                ac_target = attrs.get("temperature")
            if st.get("state") not in ("off", "unavailable", "unknown", None):
                ac_state = st.get("state", "off")
                break
        co = sum(1 for eid in ents["covers"] if state_map.get(eid, {}).get("state") == "closed")
        ct = len(ents["covers"])
        rooms.append({
            "room": rn,
            "lights_on": lo,
            "lights_total": lt,
            "ac_state": ac_state,
            "ac_temp": ac_temp,
            "ac_target": ac_target,
            "covers_closed": co,
            "covers_total": ct,
        })
    rooms.sort(key=lambda r: (-(r["lights_on"]), r["ac_state"] == "off", r["room"]))
    return rooms


# ═══════════════════════════════════════════════════
# /dashboard — Single call for all sensors
# ═══════════════════════════════════════════════════

def _check_bridge_health():
    """Check if Bridge is available via service_health."""
    try:
        from service_health import get_health_hub
        hub = get_health_hub()
        if hub and not hub.is_up("bridge"):
            svc = hub._services.get("bridge")
            return False, {
                "degraded": True,
                "degraded_reason": f"Bridge offline: {svc.reason if svc else 'unknown'}",
                "data_source": "cache",
            }
    except Exception:
        pass
    return True, {}


@router.get("/dashboard")
async def ha_dashboard():
    """Returns all data needed for HA Master AI dashboard page."""
    import psutil, sqlite3
    data = {}
    data["version"] = _ctx["version"]
    data["uptime"] = round(time.time() - _ctx["start_time"])
    data["api_online"] = True
    try:
        data["cpu"] = psutil.cpu_percent(interval=0.5)
        data["memory"] = psutil.virtual_memory().percent
        data["disk"] = psutil.disk_usage("/").percent
        try:
            data["temperature"] = round(float(open("/sys/class/thermal/thermal_zone0/temp").read().strip()) / 1000, 1)
        except Exception:
            data["temperature"] = 0
    except Exception:
        data["cpu"] = 0; data["memory"] = 0; data["disk"] = 0; data["temperature"] = 0
    data["background_tasks"] = 22
    bridge_up, bridge_degraded = _check_bridge_health()
    if not bridge_up:
        data["degraded_mode"] = "bridge_offline"
        data["degraded_info"] = bridge_degraded
    else:
        data["degraded_mode"] = "normal"
    try:
        from life_work import get_shift
        from datetime import date as _d
        st = get_shift(_d.today())
        data["shift_today"] = st.get("shift", "?") + " " + st.get("emoji", "")
        st2 = get_shift(_d.today() + timedelta(days=1))
        data["shift_tomorrow"] = st2.get("shift", "?") + " " + st2.get("emoji", "")
    except Exception:
        data["shift_today"] = "?"; data["shift_tomorrow"] = "?"
    try:
        from stock_radar import get_watchlist, get_recent_events, _get_config, get_daily_snapshot
        from tv_data import _is_market_open
        cfg = _get_config()
        data["radar_enabled"] = cfg.get("enabled", False)
        data["radar_watch_count"] = len(get_watchlist())
        data["market_open"] = _is_market_open()
        events = get_recent_events(5)
        data["radar_alerts_today"] = len([e for e in events if e.get("created_at","")[:10] == str(_d.today())])
        if events:
            last = events[0]
            data["last_signal_symbol"] = last.get("symbol", "")
            data["last_signal_type"] = last.get("signal_type", "")
            data["last_signal_price"] = last.get("price", 0)
            data["last_signal_time"] = last.get("created_at", "")[:16]
        else:
            data["last_signal_symbol"] = ""; data["last_signal_type"] = ""; data["last_signal_price"] = 0; data["last_signal_time"] = ""
        if events:
            best = events[0]
            data["top_signal"] = f"{best.get('symbol','')} ({best.get('signal_type','').replace('_',' ')}) @ {best.get('price',0)} fils"
        else:
            data["top_signal"] = ""
    except Exception:
        data["radar_enabled"] = False; data["radar_watch_count"] = 0; data["market_open"] = False; data["radar_alerts_today"] = 0
        data["last_signal_symbol"] = ""; data["last_signal_type"] = ""; data["last_signal_price"] = 0; data["last_signal_time"] = ""
        data["top_signal"] = ""
    try:
        conn = sqlite3.connect("data/life.db", timeout=3)
        data["tasks_open"] = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='todo'").fetchone()[0]
        data["tasks_high"] = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='todo' AND priority<=1").fetchone()[0]
        conn.close()
    except Exception:
        data["tasks_open"] = 0; data["tasks_high"] = 0
    try:
        conn = sqlite3.connect("data/life.db", timeout=3)
        today = str(_d.today())
        data["events_today"] = conn.execute("SELECT COUNT(*) FROM calendar_events WHERE start_ts LIKE ? AND status='confirmed'", (today+"%",)).fetchone()[0]
        row = conn.execute("SELECT summary, start_ts FROM calendar_events WHERE start_ts >= ? AND status='confirmed' ORDER BY start_ts LIMIT 1", (datetime.utcnow().isoformat(),)).fetchone()
        data["next_event"] = row[0] if row else ""
        data["next_event_time"] = row[1][:16] if row else ""
        conn.close()
    except Exception:
        data["events_today"] = 0; data["next_event"] = ""; data["next_event_time"] = ""
    try:
        conn = sqlite3.connect("data/life.db", timeout=3)
        today = str(_d.today())
        data["expenses_today"] = conn.execute("SELECT COALESCE(SUM(amount),0) FROM expense_entries WHERE spent_at LIKE ?", (today+"%",)).fetchone()[0]
        conn.close()
    except Exception:
        data["expenses_today"] = 0
    try:
        import glob
        bks = sorted(glob.glob("backups/*.gz"))
        data["last_backup"] = bks[-1].split("/")[-1] if bks else "none"
    except Exception:
        data["last_backup"] = "unknown"
    states = []
    try:
        import aiohttp
        ha_token = ""
        try:
            ha_token = open(os.path.expanduser("~/.ha_token")).read().strip()
        except Exception:
            pass
        if ha_token:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://127.0.0.1:8123/api/states",
                                       headers={"Authorization": f"Bearer {ha_token}"},
                                       timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        states = await resp.json()
                        data["home_lights_on"] = sum(1 for s in states if s["entity_id"].startswith("light.") and s["state"] == "on" and "backlight" not in s["entity_id"])
                        data["home_ac_on"] = sum(1 for s in states if s["entity_id"].startswith("climate.") and s["state"] not in ("off", "unavailable", "unknown"))
                        ci = sum(1 for s in states if s["entity_id"].startswith("cover.") and "_inverted" in s["entity_id"] and s["state"] == "closed")
                        data["home_covers_open"] = ci
                    else:
                        data["home_lights_on"] = -1; data["home_ac_on"] = -1; data["home_covers_open"] = -1
        else:
            data["home_lights_on"] = -1; data["home_ac_on"] = -1; data["home_covers_open"] = -1
    except Exception:
        data["home_lights_on"] = -1; data["home_ac_on"] = -1; data["home_covers_open"] = -1
    try:
        data["rooms_summary"] = _build_rooms_summary(states)
    except Exception as _rs_err:
        logging.getLogger("master_ai").warning("rooms_summary error: %s", _rs_err)
        data["rooms_summary"] = []
    if _ctx["dashboard_jobs"]:
        lj = _ctx["dashboard_jobs"][-1]
        data["last_cmd_command"] = lj.get("command", "")
        data["last_cmd_status"] = lj.get("status", "")
        data["last_cmd_result"] = lj.get("result", "")[:200]
        data["last_cmd_time"] = lj.get("time", "")
    else:
        data["last_cmd_command"] = ""; data["last_cmd_status"] = ""; data["last_cmd_result"] = ""; data["last_cmd_time"] = ""
    # --- Priority Engine ---
    try:
        # A1: Warm inbox cache on cold start so PE sees emails
        if not hasattr(ha_dashboard_extended, "_inbox_cache") or not ha_dashboard_extended._inbox_cache.get("data"):
            try:
                from inbox_engine import fetch_unified_inbox
                import asyncio as _aio
                _inbox_warm = await fetch_unified_inbox(hours=24, limit=15)
                import time as _tw
                ha_dashboard_extended._inbox_cache = {"data": _inbox_warm, "ts": _tw.time()}
            except Exception:
                pass
        pe_ext = _pe_get_extended_snapshot()
        pe_rad = _pe_get_radar_snapshot()
        pe = build_priority_engine(data, pe_ext, pe_rad)
        data["priority_engine"] = pe
        # A1: Assistant Surface Layer
        try:
            data["assistant_surface"] = build_assistant_surface(pe, data)
        except Exception as _as_err:
            logging.getLogger("master_ai").warning("assistant_surface error: %s", _as_err)
            data["assistant_surface"] = {"top_action": {"headline": "", "why_now": ""}, "next_actions": [], "later_today": [], "changes": {}, "meta": {"quiet_mode": True}}
        # A1: ai_insight from assistant surface (action-framed)
        asf_ta = data.get("assistant_surface", {}).get("top_action", {})
        if asf_ta.get("headline"):
            why = asf_ta.get("why_now", "")
            data["ai_insight"] = asf_ta["headline"] + (" \u2014 " + why if why else "")
        elif pe.get("summary_line"):
            data["ai_insight"] = pe["summary_line"]
        else:
            data["ai_insight"] = "\u2705 كل شي تحت السيطرة"
    except Exception as _pe_err:
        logging.getLogger("master_ai").warning("priority_engine in /dashboard error: %s", _pe_err)
        data["priority_engine"] = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "stale": True, "empty_state": True,
            "summary_line": "", "top_priority": None, "priorities": []
        }
        # Fallback to old ai_insight
        parts = []
        if data.get("degraded_mode") not in ("normal", None):
            parts.append("\u26a0 " + str(data["degraded_mode"]))
        sh = data.get("shift_today", "")
        sh2 = data.get("shift_tomorrow", "")
        if sh:
            parts.append(sh + (" \u2192 " + sh2 if sh2 else ""))
        lo = data.get("home_lights_on", -1)
        ao = data.get("home_ac_on", -1)
        if lo >= 0:
            parts.append("\U0001f3e0 " + str(lo) + "\U0001f4a1 " + str(ao) + "\u2744")
        if data.get("top_signal"):
            parts.append("\U0001f4ca " + data["top_signal"])
        if data.get("next_event"):
            parts.append("\U0001f4c5 " + data["next_event"])
        if not parts:
            parts.append("\u2705 كل شي تحت السيطرة")
        data["ai_insight"] = " | ".join(parts[:4])
    return data


# ═══════════════════════════════════════════════════
# /dashboard/cmd — Execute TG command from HA dashboard
# ═══════════════════════════════════════════════════

@router.post("/dashboard/cmd")
async def dashboard_cmd(request: Request):
    """Execute a TG command from HA dashboard. Fire-and-forget with job tracking."""
    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid JSON"}
    cmd = body.get("command", "").strip()
    if not cmd:
        return {"ok": False, "error": "no command"}
    job = {"command": cmd, "status": "running", "result": "", "time": datetime.now().strftime("%H:%M:%S")}
    _ctx["dashboard_jobs"].append(job)
    # Fire-and-forget: return immediately, execute in background
    async def _run_bg():
        try:
            result = await asyncio.wait_for(_ctx["tg_handle_command"](0, cmd), timeout=25)
            job["status"] = "done"
            job["result"] = str(result)[:2000] if result else "done"
        except asyncio.TimeoutError:
            job["status"] = "timeout"
            job["result"] = "قيد التنفيذ — النتيجة بالتلقرام"
        except Exception as ex:
            job["status"] = "error"
            job["result"] = str(ex)[:500]
    asyncio.create_task(_run_bg())
    return {"ok": True, "result": "⏳ جاري التنفيذ..."}


# ═══════════════════════════════════════════════════
# /dashboard/jobs — Last 10 dashboard command results
# ═══════════════════════════════════════════════════

@router.get("/dashboard/jobs")
async def dashboard_jobs_list():
    """Return last 10 dashboard command results."""
    return {"jobs": list(_ctx["dashboard_jobs"])}


# ═══════════════════════════════════════════════════
# /dashboard/radar — Dedicated radar data for HA radar sensor
# ═══════════════════════════════════════════════════

@router.get("/dashboard/radar")
async def ha_dashboard_radar():
    """Dedicated radar data for HA radar sensor -- lightweight, read-only from DB."""
    import sqlite3
    from datetime import date as _d
    data = {}
    bridge_up, bridge_degraded = _check_bridge_health()
    if bridge_degraded:
        data.update(bridge_degraded)
    try:
        from stock_radar import get_watchlist, get_recent_events, _get_config, get_daily_snapshot
        from tv_data import KSE_STOCKS
        cfg = _get_config()
        wl = get_watchlist()
        events = get_recent_events(20)
        today_str = str(_d.today())
        data["radar_enabled"] = cfg.get("enabled", False)
        data["radar_watch_count"] = len(wl)
        # Enrich watchlist with price/change/reason from daily snapshot
        _daily_by_sym = {}
        try:
            _daily_all = get_daily_snapshot(top_n=200, min_score=0)
            _daily_by_sym = {d["symbol"]: d for d in _daily_all}
        except Exception:
            pass
        _enriched_wl = []
        for s in wl[:12]:
            _sym = s["symbol"] if isinstance(s, dict) else s
            _tf = s.get("timeframe", "30m") if isinstance(s, dict) else "30m"
            _dd = _daily_by_sym.get(_sym, {})
            _price = _dd.get("price", 0)
            _chg = _dd.get("change_pct", 0)
            _score = _dd.get("score", 0)
            _trend = _dd.get("trend", "")
            _rsi = _dd.get("rsi") or 50
            _sup = _dd.get("support")
            _res = _dd.get("resistance")
            # Derive watch_reason
            if _score >= 70 and _trend == "\u0635\u0627\u0639\u062f":
                _reason = "\u0632\u062e\u0645 \u0635\u0627\u0639\u062f \u0642\u0648\u064a"
            elif _rsi and _rsi < 30:
                _reason = "RSI \u0645\u0646\u062e\u0641\u0636 — \u0642\u0631\u064a\u0628 \u0645\u0646 \u0627\u0644\u0642\u0627\u0639"
            elif _rsi and _rsi > 70:
                _reason = "RSI \u0645\u0631\u062a\u0641\u0639 — \u062d\u0630\u0631"
            elif _sup and _price and _price > 0 and abs(_price - _sup) / _price < 0.02:
                _reason = "\u0642\u0631\u064a\u0628 \u0645\u0646 \u0627\u0644\u062f\u0639\u0645"
            elif _res and _price and _price > 0 and abs(_price - _res) / _price < 0.02:
                _reason = "\u0642\u0631\u064a\u0628 \u0645\u0646 \u0627\u0644\u0645\u0642\u0627\u0648\u0645\u0629"
            elif _trend == "\u0647\u0627\u0628\u0637":
                _reason = "\u0627\u062a\u062c\u0627\u0647 \u0647\u0627\u0628\u0637"
            elif _score >= 50:
                _reason = "\u062a\u0642\u064a\u064a\u0645 \u0645\u062a\u0648\u0633\u0637"
            else:
                _reason = "\u0645\u0631\u0627\u0642\u0628\u0629"
            _enriched_wl.append({
                "symbol": _sym,
                "name_ar": KSE_STOCKS.get(_sym, str(_sym)),
                "price": _price,
                "change_pct": round(_chg, 2) if _chg else 0,
                "timeframe": _tf,
                "watch_reason": _reason,
            })
        data["radar_watchlist"] = _enriched_wl
        enriched_signals = []
        for e in events[:10]:
            sym = e.get("symbol", "")
            gap = abs(float(e.get("ema_fast", 0)) - float(e.get("ema_slow", 0)))
            sig = {
                "symbol": sym,
                "name_ar": KSE_STOCKS.get(sym, sym),
                "type": e.get("signal_type", ""),
                "signal_type": e.get("signal_type", ""),
                "type_ar": "\u0635\u0627\u0639\u062f" if "bullish" in e.get("signal_type","") else "\u0647\u0627\u0628\u0637",
                "price": e.get("price", 0),
                "time": e.get("created_at", "")[:16],
                "timeframe": e.get("timeframe", "30m"),
                "ema_fast": round(float(e.get("ema_fast", 0)), 2),
                "ema_slow": round(float(e.get("ema_slow", 0)), 2),
                "ema_gap": round(gap, 3),
                "strength": "\u0642\u0648\u064a\u0629" if gap > 0.5 else "\u0645\u062a\u0648\u0633\u0637\u0629" if gap > 0.1 else "\u0636\u0639\u064a\u0641\u0629",
                "rsi": e.get("rsi"),
                "vwap": e.get("vwap"),
                "volume": e.get("volume", 0),
                "score": e.get("score", 0),
                "score_class": e.get("score_class", ""),
                "verdict": e.get("verdict", ""),
                "support": e.get("support"),
                "resistance": e.get("resistance"),
                "vol_ratio": e.get("vol_ratio", 0),
                "enriched_available": e.get("rsi") is not None,
            }
            enriched_signals.append(sig)
        data["radar_recent_signals"] = enriched_signals
        data["radar_alerts_today"] = len([e for e in events if e.get("created_at","")[:10] == today_str])
    except Exception as _e:
        logging.getLogger("master_ai").warning("dashboard/radar signals error: %s", _e)
        data["radar_enabled"] = False; data["radar_watch_count"] = 0
        data["radar_watchlist"] = []; data["radar_recent_signals"] = []; data["radar_alerts_today"] = 0
    try:
        daily = get_daily_snapshot(top_n=10, min_score=0)
        # Collect 30m signal symbols for action derivation
        _sig_syms = set()
        for _sig in data.get("radar_recent_signals", []):
            _sig_syms.add(_sig.get("symbol", ""))
        daily_clean = []
        for d in daily:
            # Derive action from score + trend + RSI + signals + EMA cross
            _score = d.get("score", 0)
            _trend = d.get("trend", "")
            _rsi = d.get("rsi") or 50
            _in_signals = d["symbol"] in _sig_syms
            _ema9 = d.get("ema_fast") or d.get("daily_ema9") or 0
            _ema21 = d.get("ema_slow") or d.get("daily_ema21") or 0
            _ema_bull = _ema9 > _ema21 > 0
            _ema_bear = 0 < _ema9 < _ema21
            if _score >= 70 and _trend == "\u0635\u0627\u0639\u062f" and _rsi < 70 and _ema_bull:
                _action = "buy"
                _action_ar = "\u0634\u0631\u0627\u0621 \u2014 \u0645\u0624\u0643\u062f"
            elif _score >= 70 and _trend == "\u0635\u0627\u0639\u062f" and _rsi < 70 and _ema_bear:
                _action = "watch"
                _action_ar = "\u0645\u0631\u0627\u0642\u0628\u0629 \u2014 EMA \u0645\u062a\u0636\u0627\u0631\u0628"
            elif _score >= 70 and _trend == "\u0635\u0627\u0639\u062f" and _rsi < 70:
                _action = "buy"
                _action_ar = "\u0634\u0631\u0627\u0621"
            elif _score >= 70 and _trend == "\u0635\u0627\u0639\u062f" and _rsi >= 70:
                _action = "watch"
                _action_ar = "\u0645\u0631\u0627\u0642\u0628\u0629 \u2014 RSI \u0645\u0631\u062a\u0641\u0639"
            elif _trend == "\u0647\u0627\u0628\u0637" and _ema_bear:
                _action = "sell"
                _action_ar = "\u0628\u064a\u0639 \u2014 \u0645\u0624\u0643\u062f"
            elif _trend == "\u0647\u0627\u0628\u0637" and _ema_bull:
                _action = "watch"
                _action_ar = "\u0645\u0631\u0627\u0642\u0628\u0629 \u2014 EMA \u0625\u064a\u062c\u0627\u0628\u064a"
            elif _trend == "\u0647\u0627\u0628\u0637" and _rsi < 30:
                _action = "watch"
                _action_ar = "\u0645\u0631\u0627\u0642\u0628\u0629 \u2014 \u0642\u0631\u064a\u0628 \u0645\u0646 \u0627\u0644\u0642\u0627\u0639"
            elif _trend == "\u0647\u0627\u0628\u0637":
                _action = "sell"
                _action_ar = "\u0628\u064a\u0639"
            elif _in_signals and _score >= 50:
                _action = "watch"
                _action_ar = "\u0645\u0631\u0627\u0642\u0628\u0629 \u2014 \u0625\u0634\u0627\u0631\u0629 30m"
            else:
                _action = "hold"
                _action_ar = "\u0627\u0646\u062a\u0638\u0627\u0631"
            # EMA cross derivation
            if _ema9 > 0 and _ema21 > 0:
                _ema_gap = round((_ema9 - _ema21) / _ema21 * 100, 2)
                if abs(_ema_gap) < 0.3:
                    _ema_cross = "neutral"
                elif _ema9 > _ema21:
                    _ema_cross = "bullish"
                else:
                    _ema_cross = "bearish"
            else:
                _ema_gap = 0
                _ema_cross = None  # null in JSON → JS falls through to daily_ema_cross
            # Compute avg_volume from vol_ratio
            _vol = d.get("volume", 0) or 0
            _vr = d.get("vol_ratio", 0) or 0
            _avg_vol = round(_vol / _vr) if _vr > 0 else 0
            # MACD + Confluence from daily snapshot
            _macd = d.get("macd")
            _macd_sig = d.get("macd_signal")
            _macd_hist = d.get("macd_histogram")
            _macd_cross = d.get("macd_cross", "none")
            _macd_above_zero = bool(d.get("macd_above_zero", False))
            _conf_score = d.get("confluence_score", 0)
            _conf_dir = d.get("confluence_direction", "neutral")
            _daily_ema_cross = d.get("daily_ema_cross", "none")
            _vol_spike = bool(d.get("volume_spike", False))
            # Confluence strength
            _conf_str = "\u0642\u0648\u064a" if abs(_conf_score or 0) >= 60 else "\u0645\u062a\u0648\u0633\u0637" if abs(_conf_score or 0) >= 30 else "\u0636\u0639\u064a\u0641"
            daily_clean.append({
                "symbol": d["symbol"],
                "name_ar": d.get("name_ar", d["symbol"]),
                "price": d.get("price", 0),
                "trend": d.get("trend", ""),
                "rsi": d.get("rsi"),
                "support": d.get("support"),
                "resistance": d.get("resistance"),
                "score": d.get("score", 0),
                "score_class": d.get("score_class", ""),
                "verdict": d.get("verdict", ""),
                "volume": _vol,
                "avg_volume": _avg_vol,
                "vol_ratio": round(_vr, 2) if _vr else 0,
                "change_pct": d.get("change_pct", 0),
                "updated_at": d.get("updated_at", ""),
                "data_age_hours": d.get("data_age_hours", 999),
                "is_stale": d.get("is_stale", True),
                "freshness": d.get("freshness", "stale"),
                "source_timeframe": d.get("source_timeframe", "1D"),
                "action": _action,
                "action_ar": _action_ar,
                "ema9": round(_ema9, 2) if _ema9 else None,
                "ema21": round(_ema21, 2) if _ema21 else None,
                "ema_cross": _ema_cross,
                "ema_gap_pct": _ema_gap,
                # MACD data
                "macd": round(_macd, 3) if _macd is not None else None,
                "macd_signal": round(_macd_sig, 3) if _macd_sig is not None else None,
                "macd_histogram": round(_macd_hist, 3) if _macd_hist is not None else None,
                "macd_cross": _macd_cross,
                "macd_above_zero": _macd_above_zero,
                # Daily EMA cross
                "daily_ema_cross": _daily_ema_cross,
                # Volume spike
                "volume_spike": _vol_spike,
                # Confluence
                "confluence": {
                    "score": _conf_score or 0,
                    "direction": _conf_dir,
                    "strength_ar": _conf_str,
                },
                # New indicators
                "stoch_k": d.get("stoch_k"),
                "adx": d.get("adx"),
                "rsi_divergence": d.get("rsi_divergence"),
                "atr": d.get("atr"),
                "bb_squeeze": bool(d.get("bb_squeeze", False)),
                "bb_bandwidth": d.get("bb_bandwidth"),
            })
        data["radar_daily_context"] = daily_clean
        data["daily_context_stale"] = all(d.get("is_stale", True) for d in daily) if daily else True
        if not daily_clean:
            data["daily_context_reason"] = "daily context not initialized yet"
        elif data["daily_context_stale"]:
            data["daily_context_reason"] = "data available but stale"
        else:
            data["daily_context_reason"] = "ok"
    except Exception as _e:
        logging.getLogger("master_ai").warning("dashboard/radar daily context error: %s", _e)
        data["radar_daily_context"] = []
        data["daily_context_stale"] = True
        data["daily_context_reason"] = f"error: {_e}"
    # ── Journal data with live P&L in KWD + broker fees ──
    try:
        if _ctx.get("journal_ok", False):
            _open_trades = _ctx["get_open_trades"]()
            # Enrich with live P&L from daily snapshot (no blocking API calls)
            try:
                import sqlite3 as _sq3
                from journal_engine import calculate_real_pnl
                _rdb = _sq3.connect("data/life.db", timeout=3)
                _rdb.row_factory = _sq3.Row
                for _t in _open_trades:
                    try:
                        from tv_data import resolve_symbol, _normalize_price_to_fils
                        _rsym = resolve_symbol(_t["symbol"])
                        _dr = _rdb.execute(
                            "SELECT price FROM stock_radar_daily WHERE symbol=? ORDER BY rowid DESC LIMIT 1",
                            (_rsym,)
                        ).fetchone()
                        if _dr:
                            _cur = _normalize_price_to_fils(float(_dr["price"]), _rsym)
                            _entry = float(_t.get("entry_price", 0))
                            _qty = int(_t.get("quantity", 0))
                            _t["current_price"] = _cur
                            if _entry and _qty:
                                _t["pnl"] = calculate_real_pnl(_entry, _cur, _qty)
                            else:
                                _t["pnl_pct"] = round((_cur / _entry - 1) * 100, 2) if _entry else 0
                                _t["pnl_fils"] = round((_cur - _entry) * _qty) if _qty else 0
                    except Exception:
                        pass
                _rdb.close()
            except Exception:
                pass
            data["journal_open"] = _open_trades
            data["journal_stats"] = _ctx["get_trade_stats"](days=30)
        else:
            data["journal_open"] = []
            data["journal_stats"] = {}
    except Exception as _je:
        logging.getLogger("master_ai").warning("dashboard/radar journal error: %s", _je)
        data["journal_open"] = []
        data["journal_stats"] = {}
    return data


# ═══════════════════════════════════════════════════
# /dashboard/portfolio — Portfolio + Journal data
# ═══════════════════════════════════════════════════

@router.get("/dashboard/portfolio")
async def ha_dashboard_portfolio():
    """Portfolio data for HA dashboard — open positions, closed trades, stats."""
    data = {}
    bridge_up, bridge_degraded = _check_bridge_health()
    if bridge_degraded:
        data.update(bridge_degraded)

    # Open positions with live P&L in KWD + broker fees
    try:
        if _ctx.get("journal_ok", False):
            from journal_engine import get_open_trades, get_trade_stats, get_recent_trades, calculate_real_pnl, get_fresh_price
            open_trades = get_open_trades()
            # Enrich with current prices + S/R + P&L
            _rdb = None
            try:
                _rdb = sqlite3.connect("data/life.db", timeout=3)
                _rdb.row_factory = sqlite3.Row
            except Exception:
                pass
            for t in open_trades:
                _entry = float(t.get("entry_price", 0) or 0)
                _qty = int(t.get("quantity", 0) or 0)
                _cur = None
                _src = "unknown"
                _stale = True
                sym = t.get("symbol", "").upper()

                # Layer 1: Bridge cache (freshest)
                try:
                    fp = get_fresh_price(sym)
                    if fp.get("price"):
                        _cur = float(fp["price"])
                        _src = fp.get("source", "bridge")
                        _stale = fp.get("stale", False)
                except Exception:
                    pass

                # Layer 2: Radar daily DB (fallback)
                if _cur is None and _rdb:
                    try:
                        from tv_data import resolve_symbol, _normalize_price_to_fils
                        _rsym = resolve_symbol(sym)
                        _dr = _rdb.execute(
                            "SELECT price, support, resistance FROM stock_radar_daily WHERE symbol=? ORDER BY rowid DESC LIMIT 1",
                            (_rsym,)
                        ).fetchone()
                        if _dr and _dr["price"]:
                            _cur = _normalize_price_to_fils(float(_dr["price"]), _rsym)
                            _src = "radar_daily"
                            _stale = True
                            t["support"] = _dr["support"]
                            t["resistance"] = _dr["resistance"]
                    except Exception:
                        pass

                # Set current price + source
                if _cur:
                    t["current_price"] = _cur
                t["quote_source"] = _src
                t["quote_stale"] = _stale

                # ALWAYS compute P&L when we have entry + current price
                if _entry and _cur:
                    t["pnl_pct"] = round((_cur / _entry - 1) * 100, 2)
                    if _qty:
                        t["pnl"] = calculate_real_pnl(_entry, _cur, _qty)
                        t["pnl_fils"] = round((_cur - _entry) * _qty)
                        t["pnl_kwd"] = round((_cur - _entry) * _qty / 1000, 3)
                    else:
                        t["pnl_fils"] = round(_cur - _entry)
                        t["pnl_kwd"] = round((_cur - _entry) / 1000, 3)
                else:
                    t["pnl_pct"] = 0
                    t["pnl_fils"] = 0
                    t["pnl_kwd"] = 0

                # ── S/R from Bridge analysis (if not already set from radar_daily) ──
                if _cur and not t.get("support"):
                    try:
                        import urllib.request as _urlreq, json as _json
                        _aurl = f"http://192.168.111.158:8059/analysis?symbol={sym}&interval=1D"
                        with _urlreq.urlopen(_aurl, timeout=5) as _aresp:
                            _adata = _json.loads(_aresp.read().decode())
                        _abars = _adata.get("bars", [])
                        if _abars and len(_abars) >= 20:
                            from sr_engine import compute_sr
                            _sr = compute_sr(sym, _abars, _cur)
                            if _sr.get("key_support"):
                                t["support"] = _sr["key_support"]
                            if _sr.get("key_resistance"):
                                t["resistance"] = _sr["key_resistance"]
                    except Exception:
                        pass

                # ── Suggested stop loss (if user hasn't set one) ──
                if not t.get("stop_loss") and _entry:
                    _sup = t.get("support")
                    if _sup and _sup < _entry:
                        t["suggested_stop"] = _sup
                    else:
                        t["suggested_stop"] = round(_entry * 0.95, 1)

            if _rdb:
                try:
                    _rdb.close()
                except Exception:
                    pass
            # Enrich with signal_health + alerts from signal_engine
            try:
                from signal_engine import build_signals
                import asyncio as _asyncio
                sig_result = await _asyncio.get_event_loop().run_in_executor(None, build_signals)
                sig_map = {s["symbol"]: s for s in (sig_result.get("all_signals") or [])}
                for t in open_trades:
                    sym = t.get("symbol", "").upper()
                    sig = sig_map.get(sym)
                    if sig:
                        t["signal_health"] = {
                            "confluence_score": sig.get("confluence_score", 0),
                            "verdict": sig.get("verdict", ""),
                            "rsi_14": sig.get("rsi_14"),
                            "macd_momentum": sig.get("macd_momentum", ""),
                            "rsi_divergence": sig.get("rsi_divergence"),
                            "adx": sig.get("adx"),
                        }
                        alerts = []
                        cs = sig.get("confluence_score", 100)
                        if cs < 40:
                            alerts.append({"level": "danger", "message": "\u0628\u064a\u0639 \u2014 confluence \u0636\u0639\u064a\u0641"})
                        if sig.get("rsi_divergence") == "bearish":
                            alerts.append({"level": "warning", "message": "\u0645\u0631\u0627\u062c\u0639\u0629 \u2014 divergence \u0633\u0644\u0628\u064a"})
                        sl = t.get("stop_loss")
                        cp = t.get("current_price", 0)
                        if sl and cp and cp < sl:
                            alerts.append({"level": "danger", "message": "\u0628\u064a\u0639 \u0641\u0648\u0631\u0627\u064b \u2014 \u0648\u0642\u0641 \u0627\u0644\u062e\u0633\u0627\u0631\u0629"})
                        mom = sig.get("macd_momentum", "")
                        if "bearish" in mom and cs < 50:
                            alerts.append({"level": "warning", "message": "\u0645\u0631\u0627\u062c\u0639\u0629 \u2014 momentum \u0633\u0644\u0628\u064a"})
                        t["alerts"] = alerts
                    else:
                        t["signal_health"] = {}
                        t["alerts"] = []
            except Exception:
                for t in open_trades:
                    t["signal_health"] = {}
                    t["alerts"] = []

            # ATR trailing stop suggestions
            try:
                from journal_engine import suggest_trailing_stop
                for t in open_trades:
                    if t.get("id"):
                        ts = suggest_trailing_stop(t["id"])
                        if ts:
                            t["trailing_stop"] = ts["suggested_stop"]
                            t["atr"] = ts["atr"]
                            t["trailing_distance_pct"] = ts["distance_pct"]
            except Exception:
                pass

            data["open_positions"] = open_trades
        else:
            data["open_positions"] = []
    except Exception:
        data["open_positions"] = []

    # Closed trades (recent)
    try:
        from journal_engine import get_recent_trades
        all_trades = get_recent_trades(limit=50)
        data["closed_trades"] = [t for t in all_trades if t.get("status") == "closed"][:20]
    except Exception:
        data["closed_trades"] = []

    # 30-day and 7-day stats
    try:
        from journal_engine import get_trade_stats
        data["stats_30d"] = get_trade_stats(days=30)
        data["stats_7d"] = get_trade_stats(days=7)
    except Exception:
        data["stats_30d"] = {}
        data["stats_7d"] = {}

    # Signal vs trade ratio (7 days)
    try:
        conn = sqlite3.connect("data/life.db", timeout=3)
        signals_7d = conn.execute(
            "SELECT COUNT(*) FROM stock_radar_events WHERE created_at > datetime('now', '-7 days')"
        ).fetchone()[0]
        confirmed_7d = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE created_at > datetime('now', '-7 days')"
        ).fetchone()[0]
        data["signal_vs_trade"] = {
            "signals_7d": signals_7d,
            "confirmed_7d": confirmed_7d,
            "skip_rate": round((1 - confirmed_7d / max(signals_7d, 1)) * 100, 1)
        }
        conn.close()
    except Exception:
        data["signal_vs_trade"] = {}

    return data


# ═══════════════════════════════════════════════════
# /dashboard/journal — Detailed trade journal + monthly stats
# ═══════════════════════════════════════════════════

@router.get("/dashboard/journal")
async def ha_dashboard_journal():
    """Detailed trade journal with P&L in KWD, monthly stats, best/worst trades."""
    data = {}
    try:
        from journal_engine import get_open_trades, get_recent_trades, get_trade_stats, calculate_real_pnl, get_fresh_price
        from tv_data import resolve_symbol, _normalize_price_to_fils

        # ── Open positions with real P&L + S/R ──
        open_trades = get_open_trades()
        total_net_pnl_kwd = 0
        total_gross_pnl_kwd = 0
        total_fees_kwd = 0
        _rdb2 = None
        try:
            _rdb2 = sqlite3.connect("data/life.db", timeout=3)
            _rdb2.row_factory = sqlite3.Row
        except Exception:
            pass
        for t in open_trades:
            _entry = float(t.get("entry_price", 0) or 0)
            _qty = int(t.get("quantity", 0) or 0)
            _cur = None
            sym = t.get("symbol", "").upper()
            # Layer 1: Bridge
            try:
                fp = get_fresh_price(sym)
                if fp.get("price"):
                    _cur = float(fp["price"])
                    t["quote_source"] = fp.get("source", "bridge")
                    t["quote_stale"] = fp.get("stale", False)
            except Exception:
                pass
            # Layer 2: Radar daily
            if _cur is None and _rdb2:
                try:
                    _rsym = resolve_symbol(sym)
                    _dr = _rdb2.execute(
                        "SELECT price, support, resistance FROM stock_radar_daily WHERE symbol=? ORDER BY rowid DESC LIMIT 1",
                        (_rsym,)
                    ).fetchone()
                    if _dr and _dr["price"]:
                        _cur = _normalize_price_to_fils(float(_dr["price"]), _rsym)
                        t["quote_source"] = "radar_daily"
                        t["quote_stale"] = True
                        t["support"] = _dr["support"]
                        t["resistance"] = _dr["resistance"]
                except Exception:
                    pass
            if _cur:
                t["current_price"] = _cur
            # Always compute P&L
            if _entry and _cur:
                t["pnl_pct"] = round((_cur / _entry - 1) * 100, 2)
                if _qty:
                    pnl = calculate_real_pnl(_entry, _cur, _qty)
                    t["pnl"] = pnl
                    t["pnl_kwd"] = pnl["net_pnl_kwd"]
                    t["pnl_fils"] = pnl["net_pnl_fils"]
                    total_net_pnl_kwd += pnl["net_pnl_kwd"]
                    total_gross_pnl_kwd += pnl["gross_pnl_kwd"]
                    total_fees_kwd += pnl["total_fees_kwd"]
                else:
                    t["pnl_fils"] = round(_cur - _entry)
                    t["pnl_kwd"] = round((_cur - _entry) / 1000, 3)
            else:
                t["pnl_pct"] = 0
                t["pnl_fils"] = 0
                t["pnl_kwd"] = 0
        if _rdb2:
            try:
                _rdb2.close()
            except Exception:
                pass
        data["open_positions"] = open_trades

        # ── Closed trades with P&L in KWD ──
        all_trades = get_recent_trades(limit=100)
        closed = [t for t in all_trades if t.get("status") == "closed"]
        for t in closed:
            _entry = float(t.get("entry_price", 0))
            _exit = float(t.get("exit_price", 0))
            _qty = int(t.get("quantity", 0))
            if _entry and _exit and _qty:
                t["pnl"] = calculate_real_pnl(_entry, _exit, _qty)
        data["closed_trades"] = closed[:20]

        # ── Summary stats ──
        stats_30d = get_trade_stats(days=30)
        stats_7d = get_trade_stats(days=7)
        data["stats_30d"] = stats_30d
        data["stats_7d"] = stats_7d

        # ── Total portfolio P&L ──
        data["portfolio_summary"] = {
            "open_count": len(open_trades),
            "total_net_pnl_kwd": round(total_net_pnl_kwd, 3),
            "total_gross_pnl_kwd": round(total_gross_pnl_kwd, 3),
            "total_fees_kwd": round(total_fees_kwd, 3),
        }

        # ── Monthly stats ──
        try:
            conn = sqlite3.connect("data/life.db", timeout=3)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT strftime('%Y-%m', entry_date) as month,
                       COUNT(*) as total,
                       SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN pnl_pct <= 0 THEN 1 ELSE 0 END) as losses,
                       SUM(pnl_fils) as total_pnl_fils,
                       AVG(pnl_pct) as avg_pnl_pct
                FROM trades WHERE status='closed'
                GROUP BY month ORDER BY month DESC LIMIT 6
            """).fetchall()
            data["monthly_stats"] = [{
                "month": r["month"],
                "total": r["total"],
                "wins": r["wins"] or 0,
                "losses": r["losses"] or 0,
                "total_pnl_kwd": round((r["total_pnl_fils"] or 0) / 1000, 3),
                "win_rate": round((r["wins"] or 0) / max(r["total"], 1) * 100, 0),
            } for r in rows]
            conn.close()
        except Exception:
            data["monthly_stats"] = []

        # ── Best/Worst trades ──
        data["best_trade"] = stats_30d.get("best_trade")
        data["worst_trade"] = stats_30d.get("worst_trade")

    except Exception as e:
        logging.getLogger("master_ai").warning("dashboard/journal error: %s", e)
        data = {"open_positions": [], "closed_trades": [], "stats_30d": {},
                "stats_7d": {}, "portfolio_summary": {}, "monthly_stats": [],
                "best_trade": None, "worst_trade": None}

    return data


# ═══════════════════════════════════════════════════
# /dashboard/alerts — Smart trading alerts
# ═══════════════════════════════════════════════════

@router.get("/dashboard/alerts")
async def ha_dashboard_alerts():
    """Smart alerts: volume spikes, S/R proximity, confluence, RSI extremes."""
    data = {"volume_spikes": [], "sr_proximity": [], "confluence_alerts": [], "rsi_extremes": []}
    try:
        from stock_radar import get_daily_snapshot
        from tv_data import KSE_STOCKS
        daily = get_daily_snapshot(top_n=200, min_score=0)
        if not daily:
            return data

        for d in daily:
            sym = d["symbol"]
            name_ar = d.get("name_ar", KSE_STOCKS.get(sym, sym))
            price = d.get("price", 0)
            vr = d.get("vol_ratio", 0) or 0
            vol = d.get("volume", 0) or 0
            avg_vol = d.get("avg_volume") or (round(vol / vr) if vr > 0 else 0)
            rsi = d.get("rsi")
            support = d.get("support")
            resistance = d.get("resistance")
            conf_score = d.get("confluence_score", 0) or 0
            conf_dir = d.get("confluence_direction", "neutral")
            macd_cross = d.get("macd_cross", "none")
            daily_ema_cross = d.get("daily_ema_cross", "none")

            # Volume spikes (>=2x average)
            if vr >= 2:
                data["volume_spikes"].append({
                    "symbol": sym, "name_ar": name_ar, "price": price,
                    "volume": vol, "avg_volume": avg_vol,
                    "vol_ratio": round(vr, 1),
                    "is_spike": vr >= 3,
                })

            # S/R proximity (within 5%)
            if price and price > 0:
                if support and abs(price - support) / price < 0.05:
                    dist_pct = round((price - support) / price * 100, 1)
                    data["sr_proximity"].append({
                        "symbol": sym, "name_ar": name_ar, "price": price,
                        "level": support, "type": "support",
                        "distance_pct": dist_pct,
                    })
                if resistance and abs(price - resistance) / price < 0.05:
                    dist_pct = round((resistance - price) / price * 100, 1)
                    data["sr_proximity"].append({
                        "symbol": sym, "name_ar": name_ar, "price": price,
                        "level": resistance, "type": "resistance",
                        "distance_pct": dist_pct,
                    })

            # Multi-TF Confluence alerts (strong only)
            if abs(conf_score) >= 40:
                data["confluence_alerts"].append({
                    "symbol": sym, "name_ar": name_ar, "price": price,
                    "confluence_score": conf_score,
                    "direction": conf_dir,
                    "macd_cross": macd_cross,
                    "daily_ema_cross": daily_ema_cross,
                })

            # RSI extremes
            if rsi and (rsi > 70 or rsi < 30):
                data["rsi_extremes"].append({
                    "symbol": sym, "name_ar": name_ar, "price": price,
                    "rsi": round(rsi, 1),
                    "type": "overbought" if rsi > 70 else "oversold",
                    "type_ar": "\u062a\u0634\u0628\u0639 \u0634\u0631\u0627\u0626\u064a" if rsi > 70 else "\u062a\u0634\u0628\u0639 \u0628\u064a\u0639\u064a",
                })

        # Sort by relevance
        data["volume_spikes"].sort(key=lambda x: x["vol_ratio"], reverse=True)
        data["sr_proximity"].sort(key=lambda x: abs(x["distance_pct"]))
        data["confluence_alerts"].sort(key=lambda x: abs(x["confluence_score"]), reverse=True)
        data["rsi_extremes"].sort(key=lambda x: abs(x["rsi"] - 50), reverse=True)

    except Exception as e:
        logging.getLogger("master_ai").warning("dashboard/alerts error: %s", e)

    return data


# ═══════════════════════════════════════════════════
# /dashboard/confluence — Smart Confluence Decision Engine
# ═══════════════════════════════════════════════════

@router.get("/dashboard/confluence")
async def ha_dashboard_confluence():
    """Confluence decision engine data — actionable BUY signals + watchlist."""
    data = {
        "scan_active": False, "last_scan": "", "scan_stale": False,
        "stocks_scanned": 0, "actionable_count": 0, "watch_count": 0,
        "actionable": [], "watchlist": [], "market_summary": {},
    }
    try:
        from confluence_engine import get_actionable_signals, get_watchlist_signals, get_confluence_stats, _dedup_items_keep_latest
        stats = get_confluence_stats()

        # Dual mode: discovery + confirmation
        disc_act = get_actionable_signals(limit=5, mode="discovery")
        conf_act = get_actionable_signals(limit=5, mode="confirmation")
        disc_watch = get_watchlist_signals(limit=8, mode="discovery")
        conf_watch = get_watchlist_signals(limit=8, mode="confirmation")

        last_scan = stats.get("last_scan", "")
        scan_stale = False
        if last_scan:
            from datetime import datetime, timedelta
            try:
                ls_dt = datetime.fromisoformat(last_scan)
                scan_stale = (datetime.now() - ls_dt) > timedelta(hours=2)
            except Exception:
                pass

        data["scan_active"] = bool(last_scan and not scan_stale)
        data["last_scan"] = last_scan
        data["scan_stale"] = scan_stale
        data["stocks_scanned"] = stats.get("total_scanned", 0)
        # Backward compatible flat lists (discovery first) — dedup safety net
        all_actionable = _dedup_items_keep_latest(disc_act + conf_act)
        all_watchlist = _dedup_items_keep_latest(disc_watch + conf_watch)
        data["actionable"] = all_actionable
        data["actionable_count"] = len(all_actionable)
        data["watchlist"] = all_watchlist
        data["watch_count"] = len(all_watchlist)
        # Dual mode split
        data["discovery"] = {
            "actionable": disc_act, "actionable_count": len(disc_act),
            "watchlist": disc_watch, "watch_count": len(disc_watch),
        }
        data["confirmation"] = {
            "actionable": conf_act, "actionable_count": len(conf_act),
            "watchlist": conf_watch, "watch_count": len(conf_watch),
        }
        data["market_summary"] = {
            "high_count": stats.get("high_count", 0),
            "medium_count": stats.get("medium_count", 0),
            "low_count": max(0, stats.get("total_scanned", 0) - stats.get("high_count", 0) - stats.get("medium_count", 0)),
            "avg_confluence": stats.get("avg_confluence", 0),
        }
    except Exception as e:
        logging.getLogger("master_ai").warning("dashboard/confluence error: %s", e)

    return data


# ═══════════════════════════════════════════════════
# /dashboard/analysis — Trading analysis + signal stats
# ═══════════════════════════════════════════════════

@router.get("/dashboard/analysis")
async def ha_dashboard_analysis():
    """Trading analysis data for HA dashboard — TV alerts, signal history, stats."""
    data = {}

    try:
        conn = sqlite3.connect("data/life.db", timeout=3)
        conn.row_factory = sqlite3.Row
    except Exception:
        return {"tv_alerts": [], "signal_history": [], "signal_stats": [], "radar_accuracy": {}}

    # TV alert history
    try:
        rows = conn.execute(
            "SELECT ticker, price, signal, strategy_name, evaluation_score, event_time "
            "FROM tv_alert_events ORDER BY id DESC LIMIT 20"
        ).fetchall()
        data["tv_alerts"] = []
        for r in rows:
            _p = r["price"]
            if _p is not None and float(_p) < 10:
                _p = round(float(_p) * 1000, 1)
            data["tv_alerts"].append({
                "ticker": r["ticker"], "price": _p, "signal": r["signal"],
                "strategy": r["strategy_name"], "score": r["evaluation_score"],
                "time": r["event_time"]
            })
    except Exception:
        data["tv_alerts"] = []

    # Signal history (radar events)
    try:
        rows = conn.execute(
            "SELECT symbol, signal_type, price, score, created_at "
            "FROM stock_radar_events ORDER BY created_at DESC LIMIT 30"
        ).fetchall()
        data["signal_history"] = [
            {"symbol": r["symbol"], "type": r["signal_type"], "price": r["price"],
             "score": r["score"], "time": r["created_at"]}
            for r in rows
        ]
    except Exception:
        data["signal_history"] = []

    # Signal stats per ticker (TV)
    try:
        rows = conn.execute(
            "SELECT ticker, strategy_name, signal_type, count_total, last_seen_at "
            "FROM tv_signal_stats ORDER BY count_total DESC LIMIT 20"
        ).fetchall()
        data["signal_stats"] = [
            {"ticker": r["ticker"], "strategy": r["strategy_name"],
             "signal_type": r["signal_type"], "count": r["count_total"], "last_seen": r["last_seen_at"]}
            for r in rows
        ]
    except Exception:
        data["signal_stats"] = []

    # Radar accuracy summary
    try:
        total = conn.execute("SELECT COUNT(*) FROM stock_radar_events").fetchone()[0]
        bullish = conn.execute(
            "SELECT COUNT(*) FROM stock_radar_events WHERE signal_type='bullish_cross'"
        ).fetchone()[0]
        bearish = conn.execute(
            "SELECT COUNT(*) FROM stock_radar_events WHERE signal_type='bearish_cross'"
        ).fetchone()[0]
        avg_score = conn.execute("SELECT AVG(score) FROM stock_radar_events").fetchone()[0]
        data["radar_accuracy"] = {
            "total_signals": total,
            "bullish": bullish,
            "bearish": bearish,
            "avg_score": round(avg_score, 1) if avg_score else 0
        }
    except Exception:
        data["radar_accuracy"] = {}

    # Daily summary — built from today's data
    try:
        from datetime import date as _date
        _today = _date.today().isoformat()
        _sig_today = conn.execute(
            "SELECT COUNT(*) FROM stock_radar_events WHERE date(created_at)=?", (_today,)
        ).fetchone()[0]
        _bull_today = conn.execute(
            "SELECT COUNT(*) FROM stock_radar_events WHERE date(created_at)=? AND signal_type='bullish_cross'",
            (_today,)
        ).fetchone()[0]
        _bear_today = conn.execute(
            "SELECT COUNT(*) FROM stock_radar_events WHERE date(created_at)=? AND signal_type='bearish_cross'",
            (_today,)
        ).fetchone()[0]
        # Today's trades
        _trades_today = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE date(created_at)=?", (_today,)
        ).fetchone()[0]
        data["daily_summary"] = {
            "date": _today,
            "signals_today": _sig_today,
            "bullish_today": _bull_today,
            "bearish_today": _bear_today,
            "trades_today": _trades_today,
        }
    except Exception:
        data["daily_summary"] = None

    conn.close()
    return data


# ═══════════════════════════════════════════════════
# _parse_news_items helper
# ═══════════════════════════════════════════════════

def _parse_news_items(digest: dict) -> list:
    """Parse news category text blobs into structured items array."""
    items = []
    categories = [
        ("urgent", "عاجل", "🔥", 1),
        ("economic", "اقتصاد", "💰", 2),
        ("local", "محلي", "🇰🇼", 3),
        ("tech", "تقنية", "💻", 4),
        ("ai", "ذكاء اصطناعي", "🤖", 5),
        ("gadgets", "أجهزة", "📱", 6),
    ]
    for key, ar, emoji, pri in categories:
        text = digest.get(key, "") or ""
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            clean = line
            for ch in ["🔥", "💰", "🇰🇼", "💻", "🤖", "📱", "⚡", "🛡"]:
                clean = clean.lstrip(ch)
            clean = clean.strip(" \u200f\u200e")
            if not clean:
                continue
            source = ""
            if clean.endswith(")") and "(" in clean:
                idx = clean.rfind("(")
                source = clean[idx+1:-1].strip()
                clean = clean[:idx].strip()
            items.append({
                "category": key,
                "category_ar": ar,
                "emoji": emoji,
                "text": clean,
                "source": source,
                "priority": pri,
            })
    return items


# ═══════════════════════════════════════════════════
# /dashboard/extended — Extended data for HA subviews
# ═══════════════════════════════════════════════════

@router.get("/dashboard/extended")
async def ha_dashboard_extended():
    """Extended data for HA subviews: radar details, tasks list, events, system health."""
    import psutil, subprocess, sqlite3
    from datetime import date as _d
    data = {}

    # -- Radar data moved to /dashboard/radar endpoint --
    # Radar fields are now served by sensor.master_ai_radar
    # via /dashboard/radar -- no longer in /dashboard/extended.

    # ── Tasks List ──
    try:
        conn = sqlite3.connect("data/life.db", timeout=3)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, title, priority, category, due_date, status FROM tasks WHERE status='todo' ORDER BY priority, due_date LIMIT 15").fetchall()
        data["tasks_list"] = [dict(r) for r in rows]
        data["tasks_done_today"] = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='done' AND updated_at LIKE ?", (str(_d.today())+"%",)).fetchone()[0]
        conn.close()
    except Exception:
        data["tasks_list"] = []; data["tasks_done_today"] = 0

    # ── Calendar Events ──
    try:
        conn = sqlite3.connect("data/life.db", timeout=3)
        conn.row_factory = sqlite3.Row
        today_str = str(_d.today())
        tomorrow_str = str(_d.today() + timedelta(days=1))
        rows = conn.execute("SELECT summary, start_ts, end_ts, location FROM calendar_events WHERE (start_ts LIKE ? OR start_ts LIKE ?) AND status='confirmed' ORDER BY start_ts LIMIT 10", (today_str+"%", tomorrow_str+"%")).fetchall()
        data["events_list"] = [dict(r) for r in rows]
        conn.close()
    except Exception:
        data["events_list"] = []

    # ── System Health ──
    try:
        data["cpu"] = psutil.cpu_percent(interval=0.3)
        data["memory_pct"] = psutil.virtual_memory().percent
        data["memory_used_mb"] = round(psutil.virtual_memory().used / 1024 / 1024)
        data["memory_total_mb"] = round(psutil.virtual_memory().total / 1024 / 1024)
        data["disk_pct"] = psutil.disk_usage("/").percent
        data["disk_used_gb"] = round(psutil.disk_usage("/").used / 1024**3, 1)
        data["disk_total_gb"] = round(psutil.disk_usage("/").total / 1024**3, 1)
        try:
            data["temperature"] = round(float(open("/sys/class/thermal/thermal_zone0/temp").read().strip()) / 1000, 1)
        except Exception:
            data["temperature"] = 0
        data["uptime_hours"] = round((time.time() - _ctx["start_time"]) / 3600, 1)
        data["load_avg"] = list(os.getloadavg())
    except Exception:
        data["cpu"] = 0; data["memory_pct"] = 0; data["memory_used_mb"] = 0; data["memory_total_mb"] = 0
        data["disk_pct"] = 0; data["disk_used_gb"] = 0; data["disk_total_gb"] = 0
        data["temperature"] = 0; data["uptime_hours"] = 0; data["load_avg"] = [0,0,0]

    # ── Git Info ──
    try:
        git_log = subprocess.check_output(
            ["git", "log", "--oneline", "-5"], cwd="/var/lib/homeassistant/share/master_ai",
            timeout=5, text=True
        ).strip().split("\n")
        data["git_log"] = git_log
        data["git_branch"] = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd="/var/lib/homeassistant/share/master_ai",
            timeout=3, text=True
        ).strip()
        data["git_commit_count"] = subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"], cwd="/var/lib/homeassistant/share/master_ai",
            timeout=3, text=True
        ).strip()
    except Exception:
        data["git_log"] = []; data["git_branch"] = "?"; data["git_commit_count"] = "?"

    # ── Tool Usage (top 10) ──
    try:
        conn = sqlite3.connect("data/audit.db", timeout=3)
        rows = conn.execute("SELECT COALESCE(route_type,'unknown'), COUNT(*) as cnt FROM audit_log GROUP BY route_type ORDER BY cnt DESC LIMIT 10").fetchall()
        data["tool_usage"] = [{"tool": r[0], "count": r[1]} for r in rows]
        data["total_requests"] = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        conn.close()
    except Exception:
        data["tool_usage"] = []; data["total_requests"] = 0

    # ── Cost (real token tracking from cost_tracker.py) ──
    try:
        from cost_tracker import get_cost_for_kpi
        _ck = get_cost_for_kpi()
        data["cost_today_usd"] = _ck.get("today_usd", 0)
        data["cost_total_usd"] = _ck.get("month_usd", 0)
        data["avg_cost_per_request"] = _ck.get("avg_per_request_usd", 0)
    except Exception:
        data["cost_today_usd"] = 0; data["cost_total_usd"] = 0; data["avg_cost_per_request"] = 0

    # ── Memory Stats ──
    try:
        conn = sqlite3.connect("data/structured_memory.db", timeout=3)
        data["memory_total"] = conn.execute("SELECT COUNT(*) FROM memories WHERE active=1").fetchone()[0]
        rows = conn.execute("SELECT type, COUNT(*) FROM memories WHERE active=1 GROUP BY type").fetchall()
        data["memory_by_type"] = {r[0]: r[1] for r in rows}
        conn.close()
    except Exception:
        data["memory_total"] = 0; data["memory_by_type"] = {}

    # ── Shift Week Schedule ──
    try:
        from life_work import get_shift
        from datetime import date as _d
        week = []
        day_names_ar = ["الإثنين","الثلاثاء","الأربعاء","الخميس","الجمعة","السبت","الأحد"]
        for i in range(7):
            d = _d.today() + timedelta(days=i)
            s = get_shift(d)
            week.append({
                "day": day_names_ar[d.weekday()],
                "date": str(d),
                "shift": s.get("shift","?"),
                "emoji": s.get("emoji","")
            })
        data["shift_week"] = week
    except Exception:
        data["shift_week"] = []

    # ── Anomaly Count (from home_brain) ──
    try:
        conn = sqlite3.connect("data/home_brain.db", timeout=3)
        today_str = str(_d.today())
        data["anomalies_today"] = conn.execute("SELECT COUNT(*) FROM anomaly_log WHERE detected_at LIKE ?", (today_str+"%",)).fetchone()[0]
        conn.close()
    except Exception:
        data["anomalies_today"] = 0

    # ── Email Inbox (last 24h, cached 5min) ──
    try:
        from inbox_engine import fetch_unified_inbox
        import time as _time_mod
        _now = _time_mod.time()
        if not hasattr(ha_dashboard_extended, '_inbox_cache') or (_now - ha_dashboard_extended._inbox_cache.get('ts', 0)) > 300:
            inbox_data = await fetch_unified_inbox(hours=24, limit=15)
            ha_dashboard_extended._inbox_cache = {'data': inbox_data, 'ts': _now}
        else:
            inbox_data = ha_dashboard_extended._inbox_cache['data']
        msgs = inbox_data.get("messages", [])
        email_list = []
        for m in msgs[:10]:
            pri = m.get("_priority", 1)
            pri_label = {4: "\u0639\u0627\u062c\u0644", 3: "\u0645\u0647\u0645", 2: "\u0639\u0627\u062f\u064a", 1: "\u0645\u0646\u062e\u0641\u0636"}.get(pri, "?")
            pri_emoji = {4: "\U0001f6a8", 3: "\U0001f534", 2: "\U0001f7e1", 1: "\U0001f7e2"}.get(pri, "")
            email_list.append({
                "from": (m.get("sender") or m.get("from_name") or m.get("from", ""))[:30],
                "subject": m.get("subject", "(no subject)")[:50],
                "source": m.get("source", ""),
                "source_label": "Gmail" if m.get("source") == "gmail" else "KNPC",
                "priority": pri,
                "priority_label": pri_emoji + " " + pri_label,
                "unread": m.get("unread", False),
                "time": (m.get("date") or m.get("time", ""))[:16],
            })
        data["email_messages"] = email_list
        data["email_total"] = inbox_data.get("total", 0)
        data["email_unread"] = sum(1 for m in msgs if m.get("unread"))
        data["email_critical"] = sum(1 for m in msgs if m.get("_priority") == 4)
        data["email_high"] = sum(1 for m in msgs if m.get("_priority") == 3)
        data["email_errors"] = inbox_data.get("errors", [])
    except Exception as _e:
        logging.getLogger("master_ai").warning("dashboard/extended email error: %s", _e)
        data["email_messages"] = []
        data["email_total"] = 0
        data["email_unread"] = 0
        data["email_critical"] = 0
        data["email_high"] = 0
        data["email_errors"] = [str(_e)]

    # ── News Digest ──
    try:
        from news_engine import get_today_digests, get_latest_digest, CATEGORIES
        digests_today = get_today_digests()
        latest = digests_today[0] if digests_today else get_latest_digest()
        if latest:
            cat_info = CATEGORIES.get(latest.get("category", ""), {})
            # Split summary into category fields to avoid HA truncation
            _raw_summary = latest.get("summary_text", "")
            _lines = [ln.strip() for ln in _raw_summary.split("\n") if ln.strip()]
            _urgent, _economic, _local, _tech, _ai, _gadgets, _other = [], [], [], [], [], [], []
            for _ln in _lines:
                if any(_ln.startswith(p) for p in ["\U0001f525", "\u2694", "\U0001f494", "\u26a0"]):
                    _urgent.append(_ln)
                elif any(_ln.startswith(p) for p in ["\U0001f4b0", "\U0001f4ca", "\U0001f4c8", "\U0001f4c9"]):
                    _economic.append(_ln)
                elif _ln.startswith("\U0001f1f0\U0001f1fc"):
                    _local.append(_ln)
                elif any(_ln.startswith(p) for p in ["\u26a1", "\U0001f6e1", "\U0001f4bb"]):
                    _tech.append(_ln)
                elif _ln.startswith("\U0001f916"):
                    _ai.append(_ln)
                elif _ln.startswith("\U0001f4f1"):
                    _gadgets.append(_ln)
                else:
                    _other.append(_ln)
            data["news_digest"] = {
                "summary": _raw_summary[:500],
                "urgent": "\n".join(_urgent),
                "economic": "\n".join(_economic),
                "local": "\n".join(_local),
                "tech": "\n".join(_tech),
                "ai": "\n".join(_ai),
                "gadgets": "\n".join(_gadgets),
                "other": "\n".join(_other),
                "category": latest.get("category", "mixed"),
                "category_ar": cat_info.get("ar", latest.get("category", "")),
                "category_emoji": cat_info.get("emoji", "\U0001f4f0"),
                "item_count": latest.get("item_count", 0),
                "date": latest.get("digest_date", ""),
                "slot": latest.get("digest_slot", ""),
                "created_at": latest.get("created_at", ""),
            }
            data["news_available"] = True
            data["news_digest"]["news_items"] = _parse_news_items(data["news_digest"])
        else:
            data["news_digest"] = {}
            data["news_available"] = False
            data["news_reason"] = "no digest yet"
    except Exception as _e:
        logging.getLogger("master_ai").warning("dashboard/extended news error: %s", _e)
        data["news_digest"] = {}
        data["news_available"] = False
        data["news_reason"] = str(_e)

    return data


# ═══════════════════════════════════════════════════
# Bridge API endpoints (TradingView Bridge enrichment)
# ═══════════════════════════════════════════════════

@router.get("/dashboard/bridge")
async def dashboard_bridge(
    symbols: str = None,
    mode: str = "auto",
    force_refresh: bool = False,
):
    """Compact bridge analysis for dashboard. Auto-selects symbols if none specified."""
    from bridge_client import get_bridge_client
    client = get_bridge_client()

    if not symbols:
        selected = _get_bridge_candidates(mode)
    else:
        selected = [s.strip() for s in symbols.split(",") if s.strip()]

    if not selected:
        return {"status": "ok", "bridge_online": client._online, "symbols_count": 0, "symbols": {}}

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
    """Select symbols for bridge enrichment from portfolio + watchlist."""
    candidates = set()

    # 1. Portfolio open positions
    try:
        fn = _ctx.get("get_open_trades")
        if fn:
            trades = fn()
            for t in trades:
                if t.get("symbol"):
                    candidates.add(t["symbol"].upper())
    except Exception:
        pass

    # 2. Radar watchlist
    try:
        from stock_radar import get_watchlist
        wl = get_watchlist()
        for item in wl[:10]:
            sym = item.get("symbol", "")
            if sym:
                candidates.add(sym.upper())
    except Exception:
        pass

    return list(candidates)[:15]


# ═══════════════════════════════════════════════════
# Signal Engine endpoint (composite trading signals)
# ═══════════════════════════════════════════════════

@router.get("/dashboard/signals")
def dashboard_signals():
    """Composite trading signals: radar + bridge + journal merged."""
    from signal_engine import build_signals
    return build_signals()


@router.get("/dashboard/signals-30m")
def dashboard_signals_30m():
    """30m signals for all watchlist symbols using Brain weights."""
    from signal_engine import build_signals_30m
    return build_signals_30m()


@router.get("/dashboard/scalper")
def dashboard_scalper():
    """
    Scalper dashboard — hot stocks filtered by VWAP+Volume+ADX+Stoch.
    Phase 5 of Scalping Optimization Plan.
    """
    from datetime import datetime as _dt
    from signal_engine import (
        build_signals_30m, SCALPING_MODE,
        calculate_scalping_stop, check_scalping_exit,
    )

    raw = build_signals_30m()
    all_sigs = raw.get("signals", [])
    bridge_online = raw.get("bridge_online", False)

    # --- Filter: scalping candidates ---
    hot = []
    for s in all_sigs:
        # Must have scalping data
        if not s.get("scalp_action"):
            continue
        # Only BUY or STRONG_BUY
        if s["scalp_action"] not in ("BUY", "STRONG_BUY"):
            continue
        # Must be above VWAP
        if s.get("price_vs_vwap") != "above":
            continue
        # Minimum volume ratio
        if (s.get("vol_ratio") or 0) < 3.0:
            continue
        # Minimum ADX
        if (s.get("adx") or 0) < 25:
            continue

        # Calculate stop/target
        price = s.get("price", 0)
        ema21 = s.get("ema21", 0)
        # Use support as candle_low proxy when no bar data available
        candle_low = s.get("support") or (price * 0.997)
        stop_data = calculate_scalping_stop(price, candle_low, ema21)

        hot.append({
            "symbol": s["symbol"],
            "name_ar": s.get("name_ar", ""),
            "price": price,
            "change_pct": s.get("change_pct", 0),
            "volume_ratio": s.get("vol_ratio"),
            "adx": s.get("adx"),
            "stoch_k": s.get("stoch_k"),
            "stoch_d": s.get("stoch_d"),
            "vwap": s.get("vwap"),
            "vwap_distance_pct": s.get("vwap_distance_pct"),
            "price_vs_vwap": s.get("price_vs_vwap"),
            "confluence_pct": s.get("scalp_confluence_pct", 0),
            "action": s.get("scalp_action"),
            "factors": s.get("scalp_factors", []),
            "stop_loss": stop_data.get("stop_loss"),
            "target": stop_data.get("target"),
            "risk_pct": stop_data.get("risk_pct"),
            "reward_pct": stop_data.get("reward_pct"),
            "risk_reward": stop_data.get("risk_reward"),
            "stop_type": stop_data.get("stop_type"),
            "ema9": s.get("ema9"),
            "ema21": ema21,
        })

    # Sort by confluence descending, take top 10
    hot.sort(key=lambda x: x.get("confluence_pct", 0), reverse=True)
    hot = hot[:10]

    # --- Active scalps: open positions with exit check ---
    active_scalps = []
    try:
        from journal_engine import get_open_trades
        for t in get_open_trades():
            sym = (t.get("symbol") or "").upper()
            entry_p = t.get("entry_price") or t.get("avg_price") or 0
            # Find current price from signals
            cur_sig = next((s for s in all_sigs if s["symbol"] == sym), None)
            if not cur_sig or not entry_p:
                continue
            cur_price = cur_sig.get("price", 0)
            if not cur_price:
                continue
            pnl_pct = ((cur_price - entry_p) / entry_p * 100) if entry_p > 0 else 0
            ema9 = cur_sig.get("ema9", 0)
            bars_held = t.get("bars_held", 0)
            exit_ck = check_scalping_exit(bars_held, pnl_pct, cur_price, ema9)
            active_scalps.append({
                "symbol": sym,
                "entry_price": entry_p,
                "current_price": cur_price,
                "bars_held": bars_held,
                "pnl_pct": round(pnl_pct, 2),
                "stop_loss": t.get("stop_loss"),
                "target": t.get("target_price"),
                "exit_check": exit_ck,
            })
    except Exception:
        pass

    avg_conf = round(sum(h["confluence_pct"] for h in hot) / len(hot), 1) if hot else 0

    return {
        "scalper_active": SCALPING_MODE,
        "scan_time": _dt.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "market_status": "open" if raw.get("market_open") else "closed",
        "bridge_online": bridge_online,
        "hot_stocks": hot,
        "active_scalps": active_scalps,
        "stats": {
            "total_scanned": len(all_sigs),
            "hot_count": len(hot),
            "active_scalps": len(active_scalps),
            "avg_confluence": avg_conf,
        },
        "filters_applied": {
            "min_volume_ratio": 3.0,
            "min_adx": 25,
            "vwap_required": True,
            "scalping_mode": SCALPING_MODE,
        },
    }


# ═══════════════════════════════════════════════════
# Trading Brain endpoint (signal learning stats)
# ═══════════════════════════════════════════════════

@router.get("/dashboard/regime")
async def dashboard_regime():
    """Market regime analysis per symbol."""
    from stock_radar import get_daily_snapshot
    snapshot = get_daily_snapshot(top_n=None, min_score=0)
    regimes = {}
    for s in snapshot:
        adx = s.get("adx")
        if adx and adx >= 25:
            regime = "trending"
        elif adx and adx <= 20:
            regime = "ranging"
        else:
            regime = "transition"
        regimes[s["symbol"]] = {
            "regime": regime,
            "regime_ar": "\u0627\u062a\u062c\u0627\u0647\u064a" if regime == "trending" else "\u0639\u0631\u0636\u064a" if regime == "ranging" else "\u0627\u0646\u062a\u0642\u0627\u0644\u064a",
            "adx": round(adx, 1) if adx else None,
            "atr": s.get("atr"),
            "trend": s.get("trend"),
        }
    trending = sum(1 for r in regimes.values() if r["regime"] == "trending")
    ranging = sum(1 for r in regimes.values() if r["regime"] == "ranging")
    return {
        "regimes": regimes,
        "summary": {
            "trending": trending,
            "ranging": ranging,
            "transition": len(regimes) - trending - ranging,
            "total": len(regimes),
        }
    }


@router.get("/dashboard/brain")
async def dashboard_brain():
    """Trading brain stats: indicator weights, hit rates, recent evaluations."""
    try:
        from trading_brain import get_brain_stats, get_optimal_thresholds
        result = get_brain_stats()
        result["thresholds"] = get_optimal_thresholds()
        return result
    except Exception as e:
        return {"brain_active": False, "error": str(e)}


# ═══════════════════════════════════════════════════
# /dashboard/brain-insights — Phase 5: Trading Learnings
# ═══════════════════════════════════════════════════

def _bi_conn():
    db_path = os.path.join(os.path.dirname(__file__), "data", "life.db")
    c = sqlite3.connect(db_path, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def _rows_to_list(rows):
    return [dict(r) for r in rows] if rows else []


def _build_key_learnings(c):
    """4 cards: best timeframe, top pattern, top indicator proxy, best regime."""
    # 1. Timeframe comparison (from signal_snapshots)
    timeframe_stats = c.execute("""
        SELECT
            source as timeframe,
            COUNT(*) as samples,
            ROUND(100.0 * SUM(CASE WHEN outcome='hit' THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
            ROUND(AVG(CASE WHEN outcome='hit' THEN max_gain_pct ELSE -max_loss_pct END), 2) as avg_return
        FROM signal_snapshots
        WHERE outcome IN ('hit','miss')
        GROUP BY source
        ORDER BY avg_return DESC
    """).fetchall()

    # 2. Top pattern (from mined_strategies)
    top_pattern = c.execute("""
        SELECT
            pattern_atoms, pattern_ar, timeframe, regime,
            ROUND(profitable_rate * 100, 1) as win_pct,
            ROUND(ev, 2) as ev,
            sample_size as samples,
            ROUND(profit_factor, 2) as pf
        FROM mined_strategies
        WHERE sample_size >= 30
        ORDER BY ev DESC
        LIMIT 1
    """).fetchone()

    # 3. Best indicator proxy — which single-atom patterns have highest EV
    best_indicator = c.execute("""
        SELECT
            pattern_atoms as indicator,
            COUNT(*) as strategy_count,
            ROUND(AVG(ev), 2) as avg_ev,
            ROUND(AVG(profitable_rate) * 100, 1) as avg_win_pct
        FROM mined_strategies
        WHERE sample_size >= 30 AND ev > 0
          AND pattern_atoms NOT LIKE '%,%'
        GROUP BY pattern_atoms
        HAVING COUNT(*) >= 2
        ORDER BY avg_ev DESC
        LIMIT 1
    """).fetchone()

    # 4. Best regime context (from signal_outcomes)
    best_context = c.execute("""
        SELECT
            regime_calc as regime,
            regime_dir as direction,
            COUNT(*) as samples,
            ROUND(100.0 * SUM(CASE WHEN outcome_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
            ROUND(AVG(outcome_pct), 2) as avg_return
        FROM signal_outcomes
        WHERE regime_calc IS NOT NULL
        GROUP BY regime_calc, regime_dir
        HAVING COUNT(*) >= 50
        ORDER BY avg_return DESC
        LIMIT 1
    """).fetchone()

    return {
        "timeframe_comparison": _rows_to_list(timeframe_stats),
        "top_pattern": dict(top_pattern) if top_pattern else None,
        "best_indicator": dict(best_indicator) if best_indicator else None,
        "best_context": dict(best_context) if best_context else None,
    }


def _build_edge_map(c):
    """Performance map: timeframe × regime × direction."""
    # By timeframe
    by_timeframe = c.execute("""
        SELECT
            timeframe,
            COUNT(*) as samples,
            ROUND(100.0 * SUM(CASE WHEN outcome_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
            ROUND(AVG(outcome_pct), 2) as avg_return
        FROM signal_outcomes
        GROUP BY timeframe
    """).fetchall()

    # Top 5 contexts
    top_contexts = c.execute("""
        SELECT
            timeframe,
            regime_calc as regime,
            regime_dir as direction,
            COUNT(*) as samples,
            ROUND(100.0 * SUM(CASE WHEN outcome_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
            ROUND(AVG(outcome_pct), 2) as avg_return
        FROM signal_outcomes
        WHERE regime_calc IS NOT NULL
        GROUP BY timeframe, regime_calc, regime_dir
        HAVING COUNT(*) >= 30
        ORDER BY avg_return DESC
        LIMIT 5
    """).fetchall()

    # Worst 5 contexts
    worst_contexts = c.execute("""
        SELECT
            timeframe,
            regime_calc as regime,
            regime_dir as direction,
            COUNT(*) as samples,
            ROUND(100.0 * SUM(CASE WHEN outcome_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
            ROUND(AVG(outcome_pct), 2) as avg_return
        FROM signal_outcomes
        WHERE regime_calc IS NOT NULL
        GROUP BY timeframe, regime_calc, regime_dir
        HAVING COUNT(*) >= 30
        ORDER BY avg_return ASC
        LIMIT 5
    """).fetchall()

    return {
        "by_timeframe": _rows_to_list(by_timeframe),
        "top_contexts": _rows_to_list(top_contexts),
        "worst_contexts": _rows_to_list(worst_contexts),
    }


def _build_top_strategies(c):
    """Best/worst 5 strategies + helpful patterns."""
    best = c.execute("""
        SELECT
            strategy_id, pattern_ar, timeframe, regime,
            sample_size as samples,
            ROUND(profitable_rate * 100, 1) as win_pct,
            ROUND(ev, 2) as ev,
            ROUND(profit_factor, 2) as pf,
            ROUND(stability, 2) as stability
        FROM mined_strategies
        WHERE sample_size >= 30
        ORDER BY ev DESC
        LIMIT 5
    """).fetchall()

    worst = c.execute("""
        SELECT
            strategy_id, pattern_ar, timeframe, regime,
            sample_size as samples,
            ROUND(profitable_rate * 100, 1) as win_pct,
            ROUND(ev, 2) as ev,
            ROUND(profit_factor, 2) as pf,
            ROUND(stability, 2) as stability
        FROM mined_strategies
        WHERE sample_size >= 30
        ORDER BY ev ASC
        LIMIT 5
    """).fetchall()

    # Helpful patterns: multi-atom patterns with high EV
    helpful = c.execute("""
        SELECT
            pattern_atoms, pattern_ar,
            COUNT(*) as strategy_count,
            ROUND(AVG(ev), 2) as avg_ev,
            ROUND(AVG(profitable_rate) * 100, 1) as avg_win_pct
        FROM mined_strategies
        WHERE ev > 3 AND sample_size >= 30
        GROUP BY pattern_atoms
        ORDER BY avg_ev DESC
        LIMIT 10
    """).fetchall()

    return {
        "best_5": _rows_to_list(best),
        "worst_5": _rows_to_list(worst),
        "helpful_patterns": _rows_to_list(helpful),
    }


def _build_decision_scorecard(c):
    """Decision audit performance."""
    # Check if table has data
    cnt = c.execute("SELECT COUNT(*) FROM decision_audit").fetchone()[0]
    if cnt == 0:
        return {"message": "لا توجد بيانات بعد", "total_decisions": 0}

    total = c.execute("""
        SELECT smart_decision, COUNT(*) as count
        FROM decision_audit
        GROUP BY smart_decision
    """).fetchall()

    by_confidence = c.execute("""
        SELECT
            CASE
                WHEN confidence >= 90 THEN '90+'
                WHEN confidence >= 80 THEN '80-89'
                WHEN confidence >= 70 THEN '70-79'
                ELSE '<70'
            END as bucket,
            COUNT(*) as count,
            ROUND(AVG(confidence), 1) as avg_conf,
            ROUND(AVG(data_quality), 1) as avg_quality
        FROM decision_audit
        WHERE smart_decision = 'ENTER'
        GROUP BY bucket
        ORDER BY bucket DESC
    """).fetchall()

    by_quality = c.execute("""
        SELECT
            CASE
                WHEN data_quality >= 80 THEN 'عالية'
                WHEN data_quality >= 60 THEN 'متوسطة'
                ELSE 'ضعيفة'
            END as quality_ar,
            COUNT(*) as count,
            ROUND(AVG(rr_ratio), 2) as avg_rr
        FROM decision_audit
        WHERE smart_decision = 'ENTER'
        GROUP BY quality_ar
    """).fetchall()

    top_used = c.execute("""
        SELECT
            strategy_id,
            COUNT(*) as used_count,
            ROUND(AVG(rr_ratio), 2) as avg_rr,
            ROUND(AVG(confidence), 1) as avg_conf
        FROM decision_audit
        WHERE smart_decision = 'ENTER' AND strategy_id IS NOT NULL AND strategy_id != ''
        GROUP BY strategy_id
        ORDER BY used_count DESC
        LIMIT 5
    """).fetchall()

    # Recent ENTER decisions (last 7 days)
    recent = c.execute("""
        SELECT symbol, market_date, confidence, data_quality, rr_ratio, sector,
               chosen_plan_source, outcome
        FROM decision_audit
        WHERE smart_decision = 'ENTER'
        ORDER BY decision_time DESC
        LIMIT 10
    """).fetchall()

    return {
        "total_decisions": cnt,
        "total_by_decision": _rows_to_list(total),
        "enter_by_confidence": _rows_to_list(by_confidence),
        "enter_by_quality": _rows_to_list(by_quality),
        "top_used_strategies": _rows_to_list(top_used),
        "recent_enters": _rows_to_list(recent),
    }


def _build_action_panel(c):
    """3 lists: do more / avoid / system stats."""
    do_more = c.execute("""
        SELECT timeframe, regime_calc as regime, regime_dir as direction,
            COUNT(*) as samples,
            ROUND(AVG(outcome_pct), 2) as avg_return
        FROM signal_outcomes
        WHERE regime_calc IS NOT NULL
        GROUP BY timeframe, regime_calc, regime_dir
        HAVING COUNT(*) >= 50 AND AVG(outcome_pct) > 2
        ORDER BY avg_return DESC
        LIMIT 3
    """).fetchall()

    avoid = c.execute("""
        SELECT timeframe, regime_calc as regime, regime_dir as direction,
            COUNT(*) as samples,
            ROUND(AVG(outcome_pct), 2) as avg_return
        FROM signal_outcomes
        WHERE regime_calc IS NOT NULL
        GROUP BY timeframe, regime_calc, regime_dir
        HAVING COUNT(*) >= 50 AND AVG(outcome_pct) < 0
        ORDER BY avg_return ASC
        LIMIT 3
    """).fetchall()

    stats = c.execute("""
        SELECT
            (SELECT COUNT(*) FROM mined_strategies) as total_strategies,
            (SELECT COUNT(*) FROM signal_outcomes) as total_signals,
            (SELECT COUNT(DISTINCT symbol) FROM signal_outcomes) as unique_stocks,
            (SELECT COUNT(*) FROM decision_audit) as total_decisions,
            (SELECT COUNT(*) FROM decision_audit WHERE smart_decision='ENTER') as total_enters,
            (SELECT ROUND(AVG(ev), 2) FROM mined_strategies WHERE sample_size >= 30) as avg_strategy_ev
    """).fetchone()

    return {
        "do_more": _rows_to_list(do_more),
        "avoid": _rows_to_list(avoid),
        "system_stats": dict(stats) if stats else {},
    }


@router.get("/dashboard/brain-insights")
async def dashboard_brain_insights():
    """Phase 5: Trading learnings — what the system learned, what works, what doesn't."""
    try:
        c = _bi_conn()
        result = {
            "generated_at": datetime.now().isoformat(),
            "key_learnings": _build_key_learnings(c),
            "edge_map": _build_edge_map(c),
            "top_strategies": _build_top_strategies(c),
            "decision_scorecard": _build_decision_scorecard(c),
            "action_panel": _build_action_panel(c),
        }
        c.close()
        return result
    except Exception as e:
        logger.error("brain-insights error: %s", e, exc_info=True)
        return {"error": str(e)}


@router.get("/dashboard/strategies")
async def dashboard_strategies():
    """Mined strategies from FP-Growth engine — ranked by final_score."""
    import json as _json
    db_path = os.path.join(os.path.dirname(__file__), "data", "life.db")
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Total count
        total = cursor.execute("SELECT COUNT(*) FROM mined_strategies").fetchone()[0]

        # Top 30 strategies
        rows = cursor.execute("""
            SELECT strategy_id, pattern_atoms, pattern_ar,
                   timeframe, regime, sample_size, unique_stocks, unique_months,
                   profitable_rate, hit_rate_3pct, hit_rate_5pct,
                   baseline_profitable, uplift, ev, speed_score,
                   profit_factor, rr_proxy,
                   avg_max_gain, avg_max_loss, avg_outcome, median_outcome,
                   entry_discount_pct, entry_method, target_1_pct, target_2_pct,
                   stop_pct, rr_ratio, est_hold_days,
                   p_value, stability, walk_forward,
                   final_score, rank, status
            FROM mined_strategies
            WHERE status IN ('production', 'candidate')
            ORDER BY final_score DESC
            LIMIT 30
        """).fetchall()

        strategies = []
        for r in rows:
            s = dict(r)
            # Parse JSON fields for frontend
            if s.get("pattern_atoms"):
                try:
                    s["pattern_atoms_list"] = _json.loads(s["pattern_atoms"])
                except Exception:
                    s["pattern_atoms_list"] = []
            if s.get("walk_forward"):
                try:
                    s["walk_forward_parsed"] = _json.loads(s["walk_forward"])
                except Exception:
                    s["walk_forward_parsed"] = []
            strategies.append(s)

        # Summary by segment
        segments = cursor.execute("""
            SELECT timeframe, regime, COUNT(*) as cnt,
                   ROUND(AVG(ev), 2) as avg_ev,
                   ROUND(AVG(profitable_rate), 3) as avg_wr
            FROM mined_strategies
            WHERE status IN ('production', 'candidate')
            GROUP BY timeframe, regime
            ORDER BY AVG(ev) DESC
        """).fetchall()

        conn.close()

        return {
            "total": total,
            "showing": len(strategies),
            "segments": [dict(s) for s in segments],
            "strategies": strategies,
        }
    except Exception as e:
        return {"total": 0, "error": str(e), "strategies": []}


# ═══════════════════════════════════════════════════
# Trade Management API
# ═══════════════════════════════════════════════════

from fastapi import Body

@router.post("/api/trade/open")
async def api_trade_open(data: dict = Body(...)):
    """Open a new trade."""
    try:
        from journal_engine import open_trade
        required = ["symbol", "entry_price", "quantity"]
        for f in required:
            if f not in data:
                return {"success": False, "error": f"Missing field: {f}"}
        trade_id = open_trade(
            symbol=data["symbol"],
            entry_price=float(data["entry_price"]),
            quantity=int(data.get("quantity", 0)),
            entry_reason=data.get("notes", ""),
            strategy=data.get("strategy", "manual"),
            timeframe=data.get("timeframe", "1D"),
            direction=data.get("direction", "long"),
            name_ar=data.get("name_ar", ""),
            stop_loss=float(data["stop_loss"]) if data.get("stop_loss") else None,
            take_profit=float(data["take_profit"]) if data.get("take_profit") else None,
        )
        return {"success": True, "trade_id": trade_id, "message": "Trade opened"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/trade/close")
async def api_trade_close(data: dict = Body(...)):
    """Close an existing trade."""
    try:
        from journal_engine import close_trade
        trade_id = data.get("trade_id")
        exit_price = data.get("exit_price")
        if not trade_id or exit_price is None:
            return {"success": False, "error": "Missing trade_id or exit_price"}
        result = close_trade(int(trade_id), float(exit_price), data.get("reason", "manual"))
        if result is None:
            return {"success": False, "error": "Trade not found or already closed"}
        return {"success": True, "trade": result, "message": "Trade closed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/trade/update")
async def api_trade_update(data: dict = Body(...)):
    """Update stop loss / take profit on a trade."""
    try:
        from journal_engine import update_trade_levels
        trade_id = data.get("trade_id")
        if not trade_id:
            return {"success": False, "error": "Missing trade_id"}
        sl = float(data["stop_loss"]) if data.get("stop_loss") is not None else None
        tp = float(data["take_profit"]) if data.get("take_profit") is not None else None
        result = update_trade_levels(int(trade_id), stop_loss=sl, take_profit=tp)
        if result is None:
            return {"success": False, "error": "Trade not found or not open"}
        return {"success": True, "message": "Trade updated"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════
# /api/data-health — Data collection health status
# ═══════════════════════════════════════════════════

@router.get("/api/data-health")
async def api_data_health():
    """Data health: last collection, freshness, coverage."""
    try:
        from kse_data_collector import get_data_health
        return get_data_health()
    except Exception as e:
        logger.error("data-health error: %s", e, exc_info=True)
        return {"error": str(e)}


@router.get("/api/data-freshness")
async def api_data_freshness():
    """Data freshness: last update, age, bridge status, per-stock staleness."""
    try:
        db_path = os.path.join(os.path.dirname(__file__), "data", "life.db")
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row

        # Last radar update
        row = conn.execute(
            "SELECT MAX(updated_at) as last_update FROM stock_radar_daily"
        ).fetchone()
        last_update = row["last_update"] if row else None

        age_hours = 999
        is_stale = True
        freshness = "stale"
        if last_update:
            try:
                from datetime import datetime as _dt
                updated = _dt.fromisoformat(last_update)
                age_hours = round((_dt.utcnow() - updated).total_seconds() / 3600, 1)
                is_stale = age_hours > 18
                freshness = "fresh" if age_hours < 6 else "aging" if age_hours < 18 else "stale"
            except Exception:
                pass

        # Total and stale counts
        total_row = conn.execute("SELECT COUNT(*) as cnt FROM stock_radar_daily").fetchone()
        total = total_row["cnt"] if total_row else 0

        stale_count = 0
        fresh_count = 0
        aging_count = 0
        rows = conn.execute("SELECT updated_at FROM stock_radar_daily").fetchall()
        for r in rows:
            if r["updated_at"]:
                try:
                    from datetime import datetime as _dt
                    u = _dt.fromisoformat(r["updated_at"])
                    h = (_dt.utcnow() - u).total_seconds() / 3600
                    if h < 6:
                        fresh_count += 1
                    elif h < 18:
                        aging_count += 1
                    else:
                        stale_count += 1
                except Exception:
                    stale_count += 1
            else:
                stale_count += 1
        conn.close()

        # Bridge connectivity
        bridge_online = False
        try:
            import urllib.request as _ur
            with _ur.urlopen("http://192.168.111.158:8059/health", timeout=3) as resp:
                if resp.status == 200:
                    bridge_online = True
        except Exception:
            pass

        return {
            "last_radar_update": last_update,
            "age_hours": age_hours,
            "is_stale": is_stale,
            "freshness": freshness,
            "bridge_online": bridge_online,
            "total_stocks": total,
            "fresh_count": fresh_count,
            "aging_count": aging_count,
            "stale_count": stale_count,
        }
    except Exception as e:
        logger.error("data-freshness error: %s", e)
        return {"error": str(e)}


@router.post("/api/collect-now")
async def api_collect_now():
    """Trigger manual data collection (on-demand)."""
    try:
        from kse_data_collector import collect_and_refresh
        result = collect_and_refresh()
        return {"success": True, "result": result}
    except Exception as e:
        logger.error("collect-now error: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════
# /api/portfolio-status — Position Engine Summary + Alerts
# ═══════════════════════════════════════════════════

@router.get("/api/portfolio-status")
async def api_portfolio_status():
    """Portfolio status with position monitoring alerts."""
    try:
        from position_engine import PositionEngine, init_position_schema
        init_position_schema()
        engine = PositionEngine()

        summary = engine.get_portfolio_summary()
        active_alerts = engine.get_active_alerts(days=7)
        last_monitored = engine.get_last_monitor_time()

        # Parse alert_data JSON for each alert
        for a in active_alerts:
            if a.get("alert_data"):
                try:
                    a["alert_data"] = json.loads(a["alert_data"])
                except Exception:
                    pass

        return {
            "portfolio": summary,
            "active_alerts": active_alerts,
            "last_monitored": last_monitored,
        }
    except Exception as e:
        logger.error("portfolio-status error: %s", e, exc_info=True)
        return {"error": str(e), "portfolio": None, "active_alerts": []}


@router.post("/api/portfolio-monitor")
async def api_portfolio_monitor():
    """Trigger daily position monitoring scan (on-demand)."""
    try:
        from position_engine import run_daily_monitor
        result = run_daily_monitor()
        return {"success": True, "result": result}
    except Exception as e:
        logger.error("portfolio-monitor error: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/api/portfolio-alert-ack")
async def api_portfolio_alert_ack(request: Request):
    """Acknowledge a position alert."""
    try:
        body = await request.json()
        alert_id = body.get("alert_id")
        if not alert_id:
            return {"success": False, "error": "alert_id required"}
        from position_engine import PositionEngine
        engine = PositionEngine()
        engine.acknowledge_alert(int(alert_id))
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/symbols")
async def api_symbols():
    """List all tracked stock symbols."""
    try:
        import sqlite3 as _sql
        db = _sql.connect("data/life.db", timeout=3)
        db.row_factory = _sql.Row
        rows = db.execute(
            "SELECT DISTINCT symbol, name_ar FROM stock_radar_daily ORDER BY symbol"
        ).fetchall()
        db.close()
        return {"symbols": [{"symbol": r["symbol"], "name_ar": r["name_ar"] or ""} for r in rows]}
    except Exception:
        # Fallback: try watchlist
        try:
            from stock_radar import get_watchlist
            wl = get_watchlist()
            return {"symbols": [{"symbol": w["symbol"], "name_ar": ""} for w in wl]}
        except Exception:
            return {"symbols": []}


# ═══════════════════════════════════════════════════
# TIER 3 DASHBOARD ENDPOINTS
# ═══════════════════════════════════════════════════

_DB = os.path.join(os.path.dirname(__file__), "data", "audit.db")


@router.get("/api/memory-extraction/stats")
async def api_memory_extraction_stats():
    """Enhancement 1: Auto-learning card stats."""
    try:
        conn = sqlite3.connect(_DB, timeout=3)
        conn.row_factory = sqlite3.Row

        # Total active observations
        total = conn.execute("SELECT COUNT(*) as c FROM memory WHERE active=1").fetchone()["c"]

        # By scope
        scope_rows = conn.execute(
            "SELECT COALESCE(scope,'global') as s, COUNT(*) as c FROM memory WHERE active=1 GROUP BY s"
        ).fetchall()
        by_scope = {r["s"]: r["c"] for r in scope_rows}

        # Extracted today (auto_extract source)
        today = datetime.now().strftime("%Y-%m-%d")
        today_count = conn.execute(
            "SELECT COUNT(*) as c FROM memory WHERE source='auto_extract' AND created_at LIKE ?",
            (today + "%",)
        ).fetchone()["c"]

        # This week
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        week_count = conn.execute(
            "SELECT COUNT(*) as c FROM memory WHERE source='auto_extract' AND created_at >= ?",
            (week_ago,)
        ).fetchone()["c"]

        # Last extraction
        last_row = conn.execute(
            "SELECT created_at, category FROM memory WHERE source='auto_extract' ORDER BY id DESC LIMIT 5"
        ).fetchall()

        last_at = last_row[0]["created_at"] if last_row else None
        last_topics = list(set(r["category"] for r in last_row)) if last_row else []

        conn.close()
        return {
            "today_extracted": today_count,
            "week_extracted": week_count,
            "last_extraction_at": last_at,
            "last_topics": last_topics,
            "total_observations": total,
            "by_scope": by_scope,
        }
    except Exception as e:
        return {"error": str(e), "today_extracted": 0, "week_extracted": 0,
                "total_observations": 0, "by_scope": {}}


@router.get("/api/intent-analytics")
async def api_intent_analytics():
    """Enhancement 2: Intent routing analytics."""
    try:
        conn = sqlite3.connect(_DB, timeout=3)
        conn.row_factory = sqlite3.Row

        today = datetime.now().strftime("%Y-%m-%d")

        # Today totals
        total = conn.execute(
            "SELECT COUNT(*) as c FROM intent_audit WHERE created_at LIKE ?",
            (today + "%",)
        ).fetchone()["c"]

        success = conn.execute(
            "SELECT COUNT(*) as c FROM intent_audit WHERE created_at LIKE ? AND final_state='responded'",
            (today + "%",)
        ).fetchone()["c"]

        failed = conn.execute(
            "SELECT COUNT(*) as c FROM intent_audit WHERE created_at LIKE ? AND final_state='failed'",
            (today + "%",)
        ).fetchone()["c"]

        # Avg duration
        avg_row = conn.execute(
            "SELECT AVG(duration_ms) as avg FROM intent_audit WHERE created_at LIKE ?",
            (today + "%",)
        ).fetchone()
        avg_ms = int(avg_row["avg"] or 0)

        # Top intents
        top = conn.execute(
            "SELECT intent, COUNT(*) as c FROM intent_audit "
            "WHERE created_at LIKE ? AND intent IS NOT NULL "
            "GROUP BY intent ORDER BY c DESC LIMIT 10",
            (today + "%",)
        ).fetchall()

        # Recent 5
        recent = conn.execute(
            "SELECT created_at as timestamp, intent, final_state as state, "
            "duration_ms, transitions FROM intent_audit "
            "ORDER BY id DESC LIMIT 5"
        ).fetchall()

        conn.close()
        return {
            "today_total": total,
            "today_success": success,
            "today_failed": failed,
            "avg_duration_ms": avg_ms,
            "top_intents": [{"intent": r["intent"], "count": r["c"]} for r in top],
            "recent": [dict(r) for r in recent],
        }
    except Exception as e:
        return {"error": str(e), "today_total": 0, "today_success": 0,
                "today_failed": 0, "avg_duration_ms": 0, "top_intents": [], "recent": []}


@router.get("/api/brain/stats")
async def api_brain_stats():
    """Enhancement 3: Brain observations statistics."""
    try:
        conn = sqlite3.connect(_DB, timeout=3)
        conn.row_factory = sqlite3.Row

        total = conn.execute("SELECT COUNT(*) as c FROM memory WHERE active=1").fetchone()["c"]

        # By scope
        scope_rows = conn.execute(
            "SELECT COALESCE(scope,'global') as s, COUNT(*) as c FROM memory WHERE active=1 GROUP BY s"
        ).fetchall()
        by_scope = {r["s"]: r["c"] for r in scope_rows}

        # Recent 24h
        yesterday = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        recent_24h = conn.execute(
            "SELECT COUNT(*) as c FROM memory WHERE active=1 AND COALESCE(updated_at, created_at) >= ?",
            (yesterday,)
        ).fetchone()["c"]

        # Staleness distribution
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        one_day = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        one_week = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

        fresh = conn.execute(
            "SELECT COUNT(*) as c FROM memory WHERE active=1 AND COALESCE(updated_at, created_at) >= ?",
            (one_day,)
        ).fetchone()["c"]
        recent_count = conn.execute(
            "SELECT COUNT(*) as c FROM memory WHERE active=1 AND COALESCE(updated_at, created_at) >= ? AND COALESCE(updated_at, created_at) < ?",
            (one_week, one_day)
        ).fetchone()["c"]
        old = total - fresh - recent_count

        # Oldest
        oldest = conn.execute(
            "SELECT MIN(created_at) as oldest FROM memory WHERE active=1"
        ).fetchone()["oldest"]
        oldest_days = 0
        if oldest:
            try:
                from brain_core import memory_age_days
                oldest_days = memory_age_days(oldest)
            except Exception:
                pass

        conn.close()
        return {
            "total_observations": total,
            "by_scope": by_scope,
            "recent_24h": recent_24h,
            "oldest_observation_days": oldest_days,
            "staleness_distribution": {
                "fresh": fresh,
                "recent": recent_count,
                "old": max(old, 0),
            },
        }
    except Exception as e:
        return {"error": str(e), "total_observations": 0, "by_scope": {},
                "recent_24h": 0, "staleness_distribution": {}}


# Context health counters (in-memory, reset on restart)
_context_layer_stats = {
    "trim": {"fires": 0, "last": None},
    "compress": {"fires": 0, "last": None},
    "summarize": {"fires": 0, "last": None},
    "emergency": {"fires": 0, "last": None},
}
_context_tokens_current = 0


def record_context_layer(layer_name: str):
    """Called by context_manager.py when a layer fires."""
    if layer_name in _context_layer_stats:
        _context_layer_stats[layer_name]["fires"] += 1
        _context_layer_stats[layer_name]["last"] = datetime.now().isoformat()


def set_context_tokens(tokens: int):
    """Update current token estimate."""
    global _context_tokens_current
    _context_tokens_current = tokens


@router.get("/api/context-health")
async def api_context_health():
    """Enhancement 4: Context management health."""
    today = datetime.now().strftime("%Y-%m-%d")
    compactions = sum(
        s["fires"] for s in _context_layer_stats.values()
        if s["last"] and s["last"].startswith(today)
    )
    active = "idle"
    if _context_layer_stats["emergency"]["fires"] > 0:
        active = "emergency"
    elif _context_layer_stats["summarize"]["fires"] > 0:
        active = "summarize"
    elif _context_layer_stats["compress"]["fires"] > 0:
        active = "compress"
    elif _context_layer_stats["trim"]["fires"] > 0:
        active = "trim"

    return {
        "current_tokens_estimate": _context_tokens_current,
        "max_tokens": 180000,
        "active_layer": active,
        "compactions_today": compactions,
        "layer_stats": _context_layer_stats,
    }


# Radar progress (in-memory, updated by parallel_coordinator)
_radar_progress = {
    "status": "idle",
    "total_stocks": 0,
    "completed": 0,
    "workers": 0,
    "elapsed_ms": 0,
    "last_completed": None,
}


def update_radar_progress(**kwargs):
    """Called during radar refresh to update progress."""
    _radar_progress.update(kwargs)


@router.get("/api/radar/progress")
async def api_radar_progress():
    """Enhancement 5: Radar parallel refresh progress."""
    return _radar_progress


@router.get("/api/latency-stats")
async def api_latency_stats():
    """Enhancement 6: Response latency breakdown."""
    try:
        conn = sqlite3.connect(_DB, timeout=3)
        conn.row_factory = sqlite3.Row

        today = datetime.now().strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT duration_ms FROM intent_audit WHERE created_at LIKE ? AND duration_ms IS NOT NULL",
            (today + "%",)
        ).fetchall()
        conn.close()

        if not rows:
            return {"avg_total_ms": 0, "samples": 0}

        durations = [r["duration_ms"] for r in rows]
        avg_total = sum(durations) // len(durations)

        # Rough breakdown estimate (real tracking requires instrumented code)
        return {
            "avg_total_ms": avg_total,
            "avg_intent_ms": min(avg_total // 10, 200),
            "avg_memory_ms": min(avg_total // 8, 300),
            "avg_llm_ms": max(avg_total - 400, 0),
            "prefetch_savings_ms": min(avg_total // 5, 500),
            "samples": len(durations),
        }
    except Exception as e:
        return {"error": str(e), "avg_total_ms": 0, "samples": 0}


@router.get("/api/skills")
async def api_skills():
    """List all available skills from skills/ directory (#20 Tier3)."""
    try:
        from skill_loader import SkillLoader
        loader = SkillLoader()
        return {"skills": loader.list_skills(), "count": len(loader.list_skills())}
    except Exception as e:
        return {"skills": [], "count": 0, "error": str(e)}

```


================================================================================
# SECTION 2: DASHBOARD HTML (trading pages)
================================================================================


############################################################
# FILE: www/trading/scalper.html (686 lines)
############################################################

```html
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>&#x0645;&#x0636;&#x0627;&#x0631;&#x0628; &#x0633;&#x0631;&#x064A;&#x0639; | Master AI</title>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --navy: #0a1628;
    --navy-light: #111d35;
    --navy-mid: #162544;
    --gold: #d4a841;
    --gold-dim: #a88832;
    --green: #00c853;
    --green-dim: #1b5e20;
    --red: #ff1744;
    --red-dim: #7f0000;
    --cyan: #26c6da;
    --white: #e8eaf0;
    --gray: #6b7b99;
    --orange: #ff9100;
    --card-bg: rgba(17, 29, 53, 0.85);
    --border: rgba(212, 168, 65, 0.15);
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: 'Tajawal', sans-serif;
    background: var(--navy);
    color: var(--white);
    min-height: 100vh;
    overflow-x: hidden;
  }
  .mono { font-family: 'IBM Plex Mono', monospace; }

  /* ===== NAV BAR ===== */
  .nav {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    background: var(--navy-light);
    border-bottom: 1px solid var(--border);
    overflow-x: auto;
    white-space: nowrap;
  }
  .nav a {
    color: var(--gray);
    text-decoration: none;
    font-size: 13px;
    padding: 4px 10px;
    border-radius: 4px;
    transition: all 0.2s;
  }
  .nav a:hover { color: var(--gold); background: rgba(212,168,65,0.08); }
  .nav a.active { color: var(--gold); background: rgba(212,168,65,0.15); font-weight: 700; }

  /* ===== PULSE BAR ===== */
  .pulse-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 20px;
    background: linear-gradient(135deg, var(--navy-mid), var(--navy-light));
    border-bottom: 2px solid var(--gold-dim);
  }
  .pulse-title {
    font-size: 22px;
    font-weight: 800;
    color: var(--gold);
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .pulse-title .icon { font-size: 26px; }
  .pulse-stats {
    display: flex;
    gap: 24px;
    align-items: center;
  }
  .pulse-stat {
    text-align: center;
  }
  .pulse-stat .val {
    font-size: 24px;
    font-weight: 800;
    color: var(--gold);
  }
  .pulse-stat .lbl {
    font-size: 11px;
    color: var(--gray);
    margin-top: 2px;
  }
  .pulse-dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    background: var(--green);
    animation: blink 1.5s infinite;
    margin-left: 8px;
  }
  .pulse-dot.offline { background: var(--red); }
  @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }

  /* ===== FILTERS ===== */
  .filters-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 20px;
    background: var(--navy-light);
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
  }
  .filter-chip {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 5px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 500;
    border: 1px solid var(--border);
    color: var(--cyan);
    background: rgba(38,198,218,0.06);
  }
  .filter-chip .fv { color: var(--gold); font-weight: 700; }
  .refresh-info {
    margin-right: auto;
    font-size: 11px;
    color: var(--gray);
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .countdown {
    color: var(--gold);
    font-weight: 600;
  }

  /* ===== SCANNER TABLE ===== */
  .scanner-wrap {
    padding: 12px 16px;
  }
  .section-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
  }
  .section-title {
    font-size: 15px;
    font-weight: 700;
    color: var(--gold);
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .badge {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
    font-weight: 700;
  }
  .badge-hot { background: rgba(255,23,68,0.2); color: var(--red); }
  .badge-ok  { background: rgba(0,200,83,0.2); color: var(--green); }
  .badge-watch { background: rgba(255,145,0,0.2); color: var(--orange); }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  thead th {
    padding: 8px 6px;
    text-align: center;
    font-weight: 600;
    font-size: 11px;
    color: var(--gray);
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    background: var(--navy);
    z-index: 2;
  }
  tbody td {
    padding: 10px 6px;
    text-align: center;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    transition: background 0.15s;
  }
  tbody tr:hover { background: rgba(212,168,65,0.05); }
  tbody tr.strong-buy { border-right: 3px solid var(--green); }
  tbody tr.buy { border-right: 3px solid var(--cyan); }

  .sym-cell {
    text-align: right;
    font-weight: 700;
    font-size: 14px;
    color: var(--white);
    padding-right: 12px !important;
  }
  .price-up { color: var(--green); }
  .price-dn { color: var(--red); }
  .price-flat { color: var(--gray); }

  .vwap-above {
    background: rgba(0,200,83,0.12);
    color: var(--green);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
  }
  .vwap-below {
    background: rgba(255,23,68,0.12);
    color: var(--red);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
  }

  .conf-bar-wrap {
    width: 60px;
    height: 6px;
    background: rgba(255,255,255,0.08);
    border-radius: 3px;
    overflow: hidden;
    display: inline-block;
    vertical-align: middle;
    margin-left: 6px;
  }
  .conf-bar {
    height: 100%;
    border-radius: 3px;
    transition: width 0.5s;
  }
  .conf-high { background: var(--green); }
  .conf-mid { background: var(--gold); }
  .conf-low { background: var(--orange); }

  .factors-cell {
    display: flex;
    gap: 3px;
    justify-content: center;
    flex-wrap: wrap;
  }
  .factor-tag {
    font-size: 10px;
    padding: 1px 5px;
    border-radius: 3px;
    font-weight: 600;
    white-space: nowrap;
  }
  .factor-tag.vwap  { background: rgba(0,200,83,0.2); color: var(--green); }
  .factor-tag.vol   { background: rgba(38,198,218,0.2); color: var(--cyan); }
  .factor-tag.adx   { background: rgba(212,168,65,0.2); color: var(--gold); }
  .factor-tag.stoch { background: rgba(156,39,176,0.2); color: #ce93d8; }

  .action-strong { color: var(--green); font-weight: 800; font-size: 12px; }
  .action-buy { color: var(--cyan); font-weight: 700; font-size: 12px; }
  .action-watch { color: var(--orange); font-weight: 600; font-size: 12px; }

  .sl-tp {
    font-size: 11px;
    line-height: 1.6;
  }
  .sl-val { color: var(--red); }
  .tp-val { color: var(--green); }
  .rr-val { color: var(--gold); font-weight: 600; }

  /* ===== ACTIVE SCALPS ===== */
  .active-scalps {
    padding: 12px 16px;
  }
  .scalp-cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 10px;
  }
  .scalp-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px;
    position: relative;
    overflow: hidden;
  }
  .scalp-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 100%; height: 3px;
  }
  .scalp-card.profit::before { background: var(--green); }
  .scalp-card.loss::before { background: var(--red); }
  .scalp-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
  }
  .scalp-sym {
    font-size: 16px;
    font-weight: 800;
    color: var(--white);
  }
  .scalp-pnl {
    font-size: 18px;
    font-weight: 800;
  }
  .scalp-pnl.pos { color: var(--green); }
  .scalp-pnl.neg { color: var(--red); }
  .scalp-details {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
    font-size: 12px;
    color: var(--gray);
  }
  .scalp-details .val { color: var(--white); font-weight: 600; }
  .bars-indicator {
    display: flex;
    gap: 3px;
    margin-top: 8px;
  }
  .bar-dot {
    width: 20px;
    height: 5px;
    border-radius: 2px;
    background: rgba(255,255,255,0.1);
  }
  .bar-dot.used { background: var(--gold); }
  .bar-dot.danger { background: var(--red); animation: blink 0.8s infinite; }
  .exit-warning {
    margin-top: 8px;
    font-size: 11px;
    color: var(--red);
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 4px;
  }

  /* ===== DEGRADED MODE ===== */
  .degraded-banner {
    padding: 8px 20px;
    background: rgba(255,145,0,0.15);
    border-bottom: 1px solid rgba(255,145,0,0.3);
    color: var(--orange);
    font-size: 12px;
    font-weight: 600;
    text-align: center;
    display: none;
  }
  .degraded-banner.show { display: block; }

  /* ===== FOOTER ===== */
  .footer {
    padding: 10px 20px;
    text-align: center;
    font-size: 11px;
    color: var(--gray);
    border-top: 1px solid var(--border);
    margin-top: 20px;
  }

  /* ===== NO DATA ===== */
  .empty-state {
    text-align: center;
    padding: 40px 20px;
    color: var(--gray);
  }
  .empty-state .icon { font-size: 48px; margin-bottom: 12px; }
  .empty-state .msg { font-size: 16px; font-weight: 600; }
  .empty-state .sub { font-size: 13px; margin-top: 6px; }

  /* ===== RESPONSIVE ===== */
  @media (max-width: 768px) {
    .pulse-bar { flex-direction: column; gap: 10px; }
    .pulse-stats { gap: 16px; }
    .filters-bar { gap: 8px; }
    table { font-size: 12px; }
    thead th, tbody td { padding: 6px 3px; }
    .conf-bar-wrap { width: 40px; }
    .scalp-cards { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>

<!-- NAV -->
<nav class="nav">
  <a href="home.html">&#x0627;&#x0644;&#x0631;&#x0626;&#x064A;&#x0633;&#x064A;&#x0629;</a>
  <a href="radar.html">&#x0631;&#x0627;&#x062F;&#x0627;&#x0631;</a>
  <a href="signals.html">&#x0625;&#x0634;&#x0627;&#x0631;&#x0627;&#x062A;</a>
  <a href="scalper.html" class="active">&#x0645;&#x0636;&#x0627;&#x0631;&#x0628;</a>
  <a href="brain.html">&#x0627;&#x0644;&#x062F;&#x0645;&#x0627;&#x063A;</a>
  <a href="positions.html">&#x0645;&#x0631;&#x0627;&#x0643;&#x0632;</a>
  <a href="journal.html">&#x064A;&#x0648;&#x0645;&#x064A;&#x0629;</a>
  <a href="news.html">&#x0623;&#x062E;&#x0628;&#x0627;&#x0631;</a>
  <a href="system.html">&#x0627;&#x0644;&#x0646;&#x0638;&#x0627;&#x0645;</a>
</nav>

<!-- DEGRADED -->
<div class="degraded-banner" id="degradedBanner">
  &#x26A0;&#xFE0F; Bridge &#x063A;&#x064A;&#x0631; &#x0645;&#x062A;&#x0635;&#x0644; &mdash; &#x0627;&#x0644;&#x0628;&#x064A;&#x0627;&#x0646;&#x0627;&#x062A; &#x0642;&#x062F; &#x062A;&#x0643;&#x0648;&#x0646; &#x0642;&#x062F;&#x064A;&#x0645;&#x0629;
</div>

<!-- PULSE BAR -->
<div class="pulse-bar">
  <div class="pulse-title">
    <span class="icon">&#x26A1;</span>
    <span>&#x0645;&#x0636;&#x0627;&#x0631;&#x0628; &#x0633;&#x0631;&#x064A;&#x0639; 30m</span>
    <span class="pulse-dot" id="statusDot"></span>
  </div>
  <div class="pulse-stats">
    <div class="pulse-stat">
      <div class="val" id="hotCount">-</div>
      <div class="lbl">&#x0641;&#x0631;&#x0635;&#x0629; &#x062D;&#x0627;&#x0631;&#x0629;</div>
    </div>
    <div class="pulse-stat">
      <div class="val" id="activeCount">-</div>
      <div class="lbl">&#x0645;&#x0636;&#x0627;&#x0631;&#x0628;&#x0629; &#x0646;&#x0634;&#x0637;&#x0629;</div>
    </div>
    <div class="pulse-stat">
      <div class="val" id="avgConf">-</div>
      <div class="lbl">&#x0645;&#x062A;&#x0648;&#x0633;&#x0637; Confluence</div>
    </div>
    <div class="pulse-stat">
      <div class="val mono" id="scannedCount">-</div>
      <div class="lbl">&#x0645;&#x0646; 128</div>
    </div>
  </div>
</div>

<!-- FILTERS -->
<div class="filters-bar">
  <div class="filter-chip">Vol <span class="fv">&ge;3x</span></div>
  <div class="filter-chip">ADX <span class="fv">&ge;25</span></div>
  <div class="filter-chip">VWAP <span class="fv">&#x0641;&#x0648;&#x0642;</span></div>
  <div class="filter-chip">Stoch <span class="fv">K&gt;D</span></div>
  <div class="refresh-info">
    <span>&#x062A;&#x062D;&#x062F;&#x064A;&#x062B; &#x0643;&#x0644;</span>
    <span class="countdown mono" id="countdown">30</span>
    <span>&#x062B;&#x0627;&#x0646;&#x064A;&#x0629;</span>
  </div>
</div>

<!-- ACTIVE SCALPS -->
<div class="active-scalps" id="activeScalpsSection" style="display:none">
  <div class="section-head">
    <div class="section-title">
      &#x1F3AF; &#x0645;&#x0636;&#x0627;&#x0631;&#x0628;&#x0627;&#x062A; &#x0646;&#x0634;&#x0637;&#x0629;
    </div>
  </div>
  <div class="scalp-cards" id="scalpCards"></div>
</div>

<!-- HOT SCANNER -->
<div class="scanner-wrap">
  <div class="section-head">
    <div class="section-title">
      &#x1F525; &#x0641;&#x0631;&#x0635; &#x062D;&#x0627;&#x0631;&#x0629;
      <span class="badge badge-hot" id="hotBadge">0</span>
    </div>
  </div>
  <div id="scannerContent">
    <table>
      <thead>
        <tr>
          <th>&#x0627;&#x0644;&#x0633;&#x0647;&#x0645;</th>
          <th>&#x0627;&#x0644;&#x0633;&#x0639;&#x0631;</th>
          <th>&#x0627;&#x0644;&#x062A;&#x063A;&#x064A;&#x0631;</th>
          <th>Vol</th>
          <th>ADX</th>
          <th>VWAP</th>
          <th>Confluence</th>
          <th>&#x0627;&#x0644;&#x0639;&#x0648;&#x0627;&#x0645;&#x0644;</th>
          <th>&#x0627;&#x0644;&#x0642;&#x0631;&#x0627;&#x0631;</th>
          <th>SL / TP</th>
        </tr>
      </thead>
      <tbody id="hotTableBody">
      </tbody>
    </table>
    <div class="empty-state" id="emptyState" style="display:none">
      <div class="icon">&#x1F50D;</div>
      <div class="msg">&#x0644;&#x0627; &#x062A;&#x0648;&#x062C;&#x062F; &#x0641;&#x0631;&#x0635; &#x062D;&#x0627;&#x0644;&#x064A;&#x0627;&#x064B;</div>
      <div class="sub">&#x064A;&#x062A;&#x0645; &#x0627;&#x0644;&#x0641;&#x062D;&#x0635; &#x0643;&#x0644; 30 &#x062B;&#x0627;&#x0646;&#x064A;&#x0629; &#x2014; &#x0627;&#x0646;&#x062A;&#x0638;&#x0631; &#x0627;&#x0644;&#x062D;&#x0631;&#x0643;&#x0629;</div>
    </div>
  </div>
</div>

<!-- FOOTER -->
<div class="footer">
  <span>Master AI Scalper</span>
  &bull;
  <span>&#x0627;&#x0644;&#x0645;&#x0635;&#x062F;&#x0631;: Bridge 30m</span>
  &bull;
  <span>&#x0622;&#x062E;&#x0631; &#x062A;&#x062D;&#x062F;&#x064A;&#x062B;: <span class="mono" id="lastUpdate">--</span></span>
</div>

<script>
const API_BASE = '';  // same origin (FastAPI serves this page)
const API_KEY_META = document.querySelector('meta[name="api-key"]');
const REFRESH_INTERVAL = 30; // seconds

let countdown = REFRESH_INTERVAL;
let countdownEl = document.getElementById('countdown');

// ===== FETCH DATA =====
async function fetchScalperData() {
  try {
    const headers = { 'Accept': 'application/json' };
    // API key from cookie or meta (FastAPI handles auth for served pages)
    const res = await fetch(`${API_BASE}/dashboard/scalper`, { headers });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderData(data);
  } catch (err) {
    console.error('Fetch error:', err);
    showDegraded(true);
  }
}

// ===== RENDER =====
function renderData(data) {
  // Degraded check
  const bridgeOk = data.scalper_active !== false;
  showDegraded(!bridgeOk);
  document.getElementById('statusDot').className = bridgeOk ? 'pulse-dot' : 'pulse-dot offline';

  // Pulse stats
  const stats = data.stats || {};
  document.getElementById('hotCount').textContent = stats.hot_count || 0;
  document.getElementById('activeCount').textContent = stats.active_scalps || 0;
  document.getElementById('avgConf').textContent = stats.avg_confluence ? stats.avg_confluence + '%' : '-';
  document.getElementById('scannedCount').textContent = stats.total_scanned || 0;
  document.getElementById('lastUpdate').textContent = formatTime(data.scan_time);

  // Hot stocks
  renderHotStocks(data.hot_stocks || []);

  // Active scalps
  renderActiveScalps(data.active_scalps || []);
}

function renderHotStocks(stocks) {
  const tbody = document.getElementById('hotTableBody');
  const empty = document.getElementById('emptyState');
  const badge = document.getElementById('hotBadge');

  badge.textContent = stocks.length;

  if (stocks.length === 0) {
    tbody.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  tbody.innerHTML = stocks.map(s => {
    const chgClass = s.change_pct > 0 ? 'price-up' : s.change_pct < 0 ? 'price-dn' : 'price-flat';
    const chgSign = s.change_pct > 0 ? '+' : '';
    const vwapClass = s.price_vs_vwap === 'above' ? 'vwap-above' : 'vwap-below';
    const vwapText = s.price_vs_vwap === 'above' ? '\u2191 ' + s.vwap_distance_pct + '%' : '\u2193 ' + Math.abs(s.vwap_distance_pct) + '%';

    const confPct = s.confluence_pct || 0;
    const confClass = confPct >= 75 ? 'conf-high' : confPct >= 50 ? 'conf-mid' : 'conf-low';

    const actionClass = s.action === 'STRONG_BUY' ? 'action-strong' : s.action === 'BUY' ? 'action-buy' : 'action-watch';
    const actionText = s.action === 'STRONG_BUY' ? '\u0634\u0631\u0627\u0621 \u0642\u0648\u064A' : s.action === 'BUY' ? '\u0634\u0631\u0627\u0621' : '\u0645\u0631\u0627\u0642\u0628\u0629';

    const factors = (s.factors || []).map(f => {
      let cls = 'vol';
      if (f.includes('VWAP')) cls = 'vwap';
      else if (f.includes('ADX')) cls = 'adx';
      else if (f.includes('STOCH')) cls = 'stoch';
      return `<span class="factor-tag ${cls}">${f}</span>`;
    }).join('');

    const rowClass = s.action === 'STRONG_BUY' ? 'strong-buy' : s.action === 'BUY' ? 'buy' : '';

    return `<tr class="${rowClass}">
      <td class="sym-cell">${s.symbol}</td>
      <td class="mono">${s.price}</td>
      <td class="${chgClass} mono">${chgSign}${s.change_pct}%</td>
      <td class="mono" style="color:var(--cyan)">${s.volume_ratio}x</td>
      <td class="mono">${s.adx}</td>
      <td><span class="${vwapClass}">${vwapText}</span></td>
      <td>
        <span class="mono">${confPct}%</span>
        <div class="conf-bar-wrap"><div class="conf-bar ${confClass}" style="width:${confPct}%"></div></div>
      </td>
      <td><div class="factors-cell">${factors}</div></td>
      <td class="${actionClass}">${actionText}</td>
      <td class="sl-tp mono">
        <span class="sl-val">SL ${s.stop_loss}</span><br>
        <span class="tp-val">TP ${s.target}</span><br>
        <span class="rr-val">${s.risk_reward || 1.5}R</span>
      </td>
    </tr>`;
  }).join('');
}

function renderActiveScalps(scalps) {
  const section = document.getElementById('activeScalpsSection');
  const container = document.getElementById('scalpCards');

  if (scalps.length === 0) {
    section.style.display = 'none';
    return;
  }
  section.style.display = 'block';

  container.innerHTML = scalps.map(s => {
    const pnlClass = s.pnl_pct >= 0 ? 'pos' : 'neg';
    const cardClass = s.pnl_pct >= 0 ? 'profit' : 'loss';
    const pnlSign = s.pnl_pct >= 0 ? '+' : '';
    const barsHeld = s.bars_held || 0;
    const exitCheck = s.exit_check || {};

    // Bar dots (max 5 shown)
    let barDots = '';
    for (let i = 0; i < 5; i++) {
      if (i < barsHeld) {
        barDots += `<div class="bar-dot ${barsHeld >= 3 && s.pnl_pct <= 0 ? 'danger' : 'used'}"></div>`;
      } else {
        barDots += '<div class="bar-dot"></div>';
      }
    }

    let exitWarn = '';
    if (exitCheck.should_exit) {
      const reason = exitCheck.exit_reason === 'TIMEOUT_3BARS' ? '\u23F0 3 \u0634\u0645\u0648\u0639 \u0628\u062F\u0648\u0646 \u0631\u0628\u062D' :
                     exitCheck.exit_reason === 'BELOW_EMA9' ? '\u26A0 \u062A\u062D\u062A EMA9' : exitCheck.exit_reason;
      exitWarn = `<div class="exit-warning">\u26D4 ${reason} \u2014 \u0627\u062E\u0631\u062C!</div>`;
    }

    return `<div class="scalp-card ${cardClass}">
      <div class="scalp-header">
        <div class="scalp-sym">${s.symbol}</div>
        <div class="scalp-pnl ${pnlClass}">${pnlSign}${s.pnl_pct}%</div>
      </div>
      <div class="scalp-details">
        <div>\u062F\u062E\u0648\u0644: <span class="val mono">${s.entry_price}</span></div>
        <div>\u062D\u0627\u0644\u064A: <span class="val mono">${s.current_price}</span></div>
        <div>SL: <span class="val mono" style="color:var(--red)">${s.stop_loss}</span></div>
        <div>TP: <span class="val mono" style="color:var(--green)">${s.target}</span></div>
      </div>
      <div class="bars-indicator">${barDots}</div>
      ${exitWarn}
    </div>`;
  }).join('');
}

// ===== HELPERS =====
function showDegraded(show) {
  document.getElementById('degradedBanner').className = show ? 'degraded-banner show' : 'degraded-banner';
}

function formatTime(ts) {
  if (!ts) return '--';
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch { return '--'; }
}

// ===== COUNTDOWN + AUTO REFRESH =====
function tick() {
  countdown--;
  if (countdown <= 0) {
    countdown = REFRESH_INTERVAL;
    fetchScalperData();
  }
  countdownEl.textContent = countdown;
}

// Init
fetchScalperData();
setInterval(tick, 1000);
</script>
</body>
</html>
```


############################################################
# FILE: www/trading/radar.html (774 lines)
############################################################

```html
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>غرفة العمليات — KSE</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Noto+Kufi+Arabic:wght@400;500;600;700&family=Tajawal:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>
:root{
  --navy-900:#070D17;--navy-800:#0C1525;--navy-700:#111E32;
  --navy-600:#162840;--navy-500:#1C334F;--navy-400:#24405F;
  --gold:#C6974B;--gold-bright:#D4A95C;--gold-dim:#9E7A3D;
  --gold-bg:rgba(198,151,75,.06);--gold-br:rgba(198,151,75,.25);
  --green:#4CAF82;--green-bright:#5BC492;--green-bg:rgba(76,175,130,.08);--green-br:rgba(76,175,130,.3);
  --red:#D94452;--red-bright:#E5606C;--red-bg:rgba(217,68,82,.08);--red-br:rgba(217,68,82,.3);
  --amber:#E8A838;--amber-bg:rgba(232,168,56,.08);--amber-br:rgba(232,168,56,.3);
  --cyan:#38BDF8;--cyan-bg:rgba(56,189,248,.08);--cyan-br:rgba(56,189,248,.3);
  --text:#E8ECF0;--text-2:#A0ADBC;--text-3:#6B7D90;--text-4:#405060;
  --card:#0E1929;--card-hover:#132137;--card-border:#1A2E45;
  --f:'Tajawal','Noto Kufi Arabic',sans-serif;
  --fd:'Noto Kufi Arabic','Tajawal',sans-serif;
  --fm:'IBM Plex Mono','Consolas',monospace;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{
  font-family:var(--f);font-variant-numeric:tabular-nums;
  background:var(--navy-900);color:var(--text);
  min-height:100vh;line-height:1.6;-webkit-font-smoothing:antialiased;
}
.ltr{direction:ltr;unicode-bidi:isolate}
a{color:var(--gold);text-decoration:none}
a:hover{color:var(--gold-bright)}

/* ===== TOPBAR ===== */
.topbar{
  position:sticky;top:0;z-index:100;
  background:rgba(7,13,23,.92);backdrop-filter:blur(16px);
  border-bottom:1px solid var(--card-border);
  padding:0 1.25rem;height:56px;
  display:flex;align-items:center;justify-content:space-between;gap:.75rem;
}
.topbar-brand{display:flex;align-items:center;gap:.75rem;flex-shrink:0}
.brand-mark{
  background:linear-gradient(135deg,var(--gold),var(--gold-dim));
  color:var(--navy-900);font-family:var(--fm);font-weight:700;
  font-size:.85rem;padding:.25rem .6rem;border-radius:4px;letter-spacing:.5px;
}
.topbar-title{font-family:var(--fd);font-weight:700;font-size:1rem;color:var(--text)}
.topbar-tag{
  font-size:.65rem;background:var(--navy-600);color:var(--text-3);
  padding:2px 8px;border-radius:10px;white-space:nowrap;
}
.topbar-center{display:flex;align-items:center;gap:.5rem;flex-shrink:0}
.status-chip{
  display:flex;align-items:center;gap:.35rem;
  font-size:.75rem;padding:.25rem .65rem;border-radius:20px;
  border:1px solid var(--card-border);background:var(--navy-800);
  color:var(--text-2);white-space:nowrap;
}
.status-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.status-dot.on{background:var(--green);box-shadow:0 0 6px var(--green)}
.status-dot.off{background:var(--red);box-shadow:0 0 6px var(--red)}
.topbar-right{display:flex;align-items:center;gap:.75rem;flex-shrink:0}
.clock{font-family:var(--fm);font-size:.85rem;color:var(--gold);direction:ltr;unicode-bidi:isolate;white-space:nowrap}
.btn-refresh{
  background:none;border:1px solid var(--card-border);color:var(--text-2);
  width:34px;height:34px;border-radius:8px;cursor:pointer;
  display:flex;align-items:center;justify-content:center;
  transition:all .2s;
}
.btn-refresh:hover{border-color:var(--gold-br);color:var(--gold)}
.btn-refresh.spinning svg{animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.nav-links{display:flex;gap:.15rem}
.nav-link{
  font-size:.75rem;padding:.3rem .6rem;border-radius:6px;color:var(--text-3);
  transition:all .2s;
}
.nav-link:hover{color:var(--text);background:var(--navy-700)}
.nav-link.active{color:var(--gold);background:var(--gold-bg);border:1px solid var(--gold-br)}

/* ===== TICKER STRIP ===== */
.ticker-strip{
  background:var(--navy-800);border-bottom:1px solid var(--card-border);
  overflow:hidden;position:relative;height:38px;
}
.ticker-track{
  display:flex;align-items:center;height:100%;gap:2rem;
  animation:scroll-rtl 40s linear infinite;white-space:nowrap;
  padding:0 1rem;
}
.ticker-strip:hover .ticker-track{animation-play-state:paused}
@keyframes scroll-rtl{
  0%{transform:translateX(0)}
  100%{transform:translateX(50%)}
}
.ticker-item{
  display:flex;align-items:center;gap:.5rem;font-size:.8rem;flex-shrink:0;
}
.ticker-sym{font-family:var(--fm);font-weight:600;color:var(--text)}
.ticker-price{font-family:var(--fm);color:var(--text-2)}
.ticker-chg{font-family:var(--fm);font-size:.75rem;padding:1px 6px;border-radius:4px}
.ticker-chg.up{color:var(--green);background:var(--green-bg)}
.ticker-chg.dn{color:var(--red);background:var(--red-bg)}
.ticker-chg.flat{color:var(--text-3);background:var(--navy-700)}

/* ===== FILTER BAR ===== */
.filter-bar{
  display:flex;align-items:center;gap:.5rem;padding:.75rem 1.25rem;
  background:var(--navy-800);border-bottom:1px solid var(--card-border);
  overflow-x:auto;-webkit-overflow-scrolling:touch;
}
.filter-chip{
  font-family:var(--f);font-size:.8rem;padding:.35rem .85rem;border-radius:20px;
  border:1px solid var(--card-border);background:var(--navy-700);color:var(--text-2);
  cursor:pointer;white-space:nowrap;transition:all .2s;display:flex;align-items:center;gap:.35rem;
}
.filter-chip:hover{border-color:var(--gold-br);color:var(--text)}
.filter-chip.active{background:var(--gold-bg);border-color:var(--gold-br);color:var(--gold)}
.filter-count{
  font-family:var(--fm);font-size:.7rem;background:var(--navy-600);
  padding:0 .4rem;border-radius:8px;min-width:20px;text-align:center;
}
.filter-chip.active .filter-count{background:rgba(198,151,75,.15)}

/* ===== MAIN CONTENT ===== */
.main{max-width:1440px;margin:0 auto;padding:1rem 1.25rem 2rem}

/* ===== HERO DECISION CARD ===== */
.hero-card{
  background:var(--card);border:1px solid var(--card-border);border-radius:12px;
  padding:1.25rem 1.5rem;margin-bottom:1.25rem;position:relative;
  border-right:4px solid var(--gold);
}
.hero-label{
  font-size:.7rem;color:var(--text-3);margin-bottom:.75rem;
  text-transform:uppercase;letter-spacing:.5px;font-family:var(--fd);
}
.hero-top{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:.75rem;margin-bottom:.75rem}
.hero-ident{display:flex;flex-direction:column;gap:.15rem}
.hero-sym{font-family:var(--fm);font-size:1.5rem;font-weight:700;color:var(--text)}
.hero-name{font-size:.9rem;color:var(--text-2);font-family:var(--fd)}
.hero-price-block{text-align:left;direction:ltr;unicode-bidi:isolate}
.hero-price{font-family:var(--fm);font-size:1.5rem;font-weight:700;color:var(--text)}
.hero-chg{font-family:var(--fm);font-size:.95rem;font-weight:600}
.hero-chg.up{color:var(--green)}
.hero-chg.dn{color:var(--red)}
.hero-chg.flat{color:var(--text-3)}
.hero-badges{display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:1rem}
.pill{
  font-size:.75rem;font-weight:600;padding:.25rem .75rem;border-radius:20px;
  display:inline-flex;align-items:center;gap:.25rem;
}
.pill-buy{background:var(--green-bg);color:var(--green);border:1px solid var(--green-br)}
.pill-watch{background:var(--amber-bg);color:var(--amber);border:1px solid var(--amber-br)}
.pill-review{background:var(--cyan-bg);color:var(--cyan);border:1px solid var(--cyan-br)}
.pill-avoid{background:var(--red-bg);color:var(--red);border:1px solid var(--red-br)}
.pill-neutral{background:var(--navy-700);color:var(--text-3);border:1px solid var(--card-border)}
.pill-hold{background:rgba(168,85,247,.08);color:#A855F7;border:1px solid rgba(168,85,247,.3)}
.state-tag{
  font-size:.7rem;padding:.2rem .6rem;border-radius:4px;font-family:var(--fm);
}
.st-manage{background:var(--green-bg);color:var(--green);border:1px solid var(--green-br)}
.st-entered{background:var(--cyan-bg);color:var(--cyan);border:1px solid var(--cyan-br)}
.st-ready{background:var(--gold-bg);color:var(--gold);border:1px solid var(--gold-br)}
.st-setup{background:var(--amber-bg);color:var(--amber);border:1px solid var(--amber-br)}
.st-discovery{background:var(--navy-700);color:var(--text-3);border:1px solid var(--card-border)}

.hero-metrics{
  display:grid;grid-template-columns:repeat(4,1fr);gap:.6rem;margin-bottom:1rem;
}
.metric-box{
  background:var(--navy-800);border:1px solid var(--card-border);border-radius:8px;
  padding:.6rem .75rem;
}
.metric-label{font-size:.65rem;color:var(--text-3);margin-bottom:.25rem;font-family:var(--fd)}
.metric-val{font-family:var(--fm);font-size:.9rem;font-weight:600;color:var(--text)}

.hero-levels{
  display:flex;gap:1.5rem;flex-wrap:wrap;padding-top:.75rem;
  border-top:1px solid var(--card-border);
}
.level-item{display:flex;align-items:center;gap:.4rem;font-size:.8rem}
.level-dot{width:8px;height:8px;border-radius:50%}
.level-dot.support{background:var(--green)}
.level-dot.resistance{background:var(--red)}
.level-dot.atr{background:var(--cyan)}
.level-label{color:var(--text-3)}
.level-val{font-family:var(--fm);font-weight:600}

/* ===== TABLE ===== */
.section-title{
  font-family:var(--fd);font-size:1rem;font-weight:700;color:var(--text);
  margin-bottom:.75rem;display:flex;align-items:center;gap:.5rem;
}
.section-title .count{
  font-family:var(--fm);font-size:.75rem;color:var(--gold);
  background:var(--gold-bg);border:1px solid var(--gold-br);
  padding:1px 8px;border-radius:10px;
}
.table-wrap{
  overflow-x:auto;-webkit-overflow-scrolling:touch;
  border:1px solid var(--card-border);border-radius:10px;
  margin-bottom:1.5rem;background:var(--card);
}
table{width:100%;border-collapse:collapse;min-width:900px}
thead th{
  font-family:var(--fd);font-size:.72rem;font-weight:600;
  color:var(--text-3);padding:.65rem .7rem;
  background:var(--navy-800);border-bottom:1px solid var(--card-border);
  text-align:right;white-space:nowrap;position:sticky;top:0;
}
tbody td{
  font-size:.8rem;padding:.55rem .7rem;
  border-bottom:1px solid rgba(26,46,69,.5);white-space:nowrap;
}
tbody tr{transition:background .15s}
tbody tr:hover{background:var(--card-hover)}
tbody tr:last-child td{border-bottom:none}
.cell-sym{font-family:var(--fm);font-weight:600;color:var(--text)}
.cell-name{font-size:.72rem;color:var(--text-3);display:block}
.cell-mono{font-family:var(--fm)}
.confluence-cell{display:flex;align-items:center;gap:.4rem}
.conf-bar{width:48px;height:6px;border-radius:3px;background:var(--navy-600);overflow:hidden;flex-shrink:0}
.conf-fill{height:100%;border-radius:3px;transition:width .4s}
.mini-pill{
  font-size:.68rem;padding:1px 6px;border-radius:10px;font-weight:600;
}

/* ===== OPEN POSITIONS ===== */
.positions-grid{
  display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));
  gap:.75rem;margin-bottom:1.5rem;
}
.pos-card{
  background:var(--card);border:1px solid var(--card-border);border-radius:10px;
  padding:.85rem 1rem;transition:all .2s;
}
.pos-card:hover{border-color:var(--gold-br);background:var(--card-hover)}
.pos-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:.5rem}
.pos-sym{font-family:var(--fm);font-weight:700;font-size:.95rem}
.pos-state{font-size:.65rem;padding:2px 6px;border-radius:4px;font-family:var(--fm)}
.pos-row{display:flex;justify-content:space-between;font-size:.78rem;margin-bottom:.25rem}
.pos-label{color:var(--text-3)}
.pos-val{font-family:var(--fm);font-weight:500}
.pos-pnl{font-family:var(--fm);font-weight:700;font-size:.95rem;text-align:left;direction:ltr;unicode-bidi:isolate}
.pos-pnl.up{color:var(--green)}
.pos-pnl.dn{color:var(--red)}

/* ===== FOOTER ===== */
.footer{
  text-align:center;padding:1.5rem 1rem;
  border-top:1px solid var(--card-border);color:var(--text-4);font-size:.72rem;
}
.footer-time{color:var(--text-3);margin-top:.35rem;font-family:var(--fm);font-size:.7rem}

/* ===== LOADING / ERROR ===== */
.state-overlay{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  padding:4rem 1rem;gap:1rem;
}
.spinner{
  width:40px;height:40px;border:3px solid var(--navy-600);
  border-top-color:var(--gold);border-radius:50%;animation:spin .8s linear infinite;
}
.state-text{color:var(--text-3);font-size:.9rem}
.btn-retry{
  font-family:var(--f);background:var(--gold-bg);border:1px solid var(--gold-br);
  color:var(--gold);padding:.5rem 1.5rem;border-radius:8px;cursor:pointer;
  font-size:.85rem;transition:all .2s;
}
.btn-retry:hover{background:rgba(198,151,75,.15)}
.empty-state{color:var(--text-3);text-align:center;padding:2rem;font-size:.85rem}

/* ===== RESPONSIVE ===== */
@media(max-width:1024px){
  .hero-metrics{grid-template-columns:repeat(2,1fr)}
}
@media(max-width:768px){
  .topbar{padding:0 .75rem;gap:.4rem}
  .topbar-title{font-size:.85rem}
  .topbar-tag,.nav-links{display:none}
  .topbar-center{gap:.3rem}
  .status-chip{font-size:.68rem;padding:.2rem .5rem}
  .main{padding:.75rem}
  .hero-card{padding:1rem}
  .hero-sym{font-size:1.15rem}
  .hero-price{font-size:1.15rem}
  .hero-metrics{grid-template-columns:repeat(2,1fr);gap:.4rem}
  .metric-box{padding:.45rem .55rem}
  .metric-val{font-size:.8rem}
  .hero-levels{gap:.75rem}
  .filter-bar{padding:.6rem .75rem;gap:.35rem}
  .positions-grid{grid-template-columns:1fr}
}
@media(max-width:480px){
  .hero-metrics{grid-template-columns:1fr 1fr}
  .hero-top{flex-direction:column}
  .hero-price-block{text-align:right}
}
</style>
<link rel="stylesheet" href="indicator-tooltips.css">
</head>
<body>

<!-- TOPBAR -->
<header class="topbar">
  <div class="topbar-brand">
    <span class="brand-mark">KSE</span>
    <span class="topbar-title">منصة التداول</span>
    <span class="topbar-tag">Master AI</span>
  </div>
  <div class="topbar-center">
    <span class="status-chip" id="chip-market">
      <span class="status-dot off" id="dot-market"></span>
      <span id="lbl-market">السوق مغلق</span>
    </span>
    <span class="status-chip" id="chip-bridge">
      <span class="status-dot off" id="dot-bridge"></span>
      <span id="lbl-bridge">الربط غير متصل</span>
    </span>
  </div>
  <div class="topbar-right">
    <span class="clock" id="clock">--:--:--</span>
    <button class="btn-refresh" id="btn-refresh" title="تحديث">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>
    </button>
    <nav class="nav-links">
      <a href="decisions" class="nav-link">القرارات</a>
      <a href="positions" class="nav-link">المراكز</a>
      <a href="radar" class="nav-link active">الرادار</a>
      <a href="journal" class="nav-link">السجل</a>
      <a href="strategies" class="nav-link">الاستراتيجيات</a>
      <a href="brain" class="nav-link">العقل</a>
    </nav>
  </div>
</header>

<!-- TICKER STRIP -->
<div class="ticker-strip">
  <div class="ticker-track" id="ticker-track"></div>
</div>

<!-- FILTER BAR -->
<div class="filter-bar" id="filter-bar">
  <button class="filter-chip active" data-filter="all">الكل <span class="filter-count" id="fc-all">0</span></button>
  <button class="filter-chip" data-filter="manage">إدارة <span class="filter-count" id="fc-manage">0</span></button>
  <button class="filter-chip" data-filter="entered">داخل <span class="filter-count" id="fc-entered">0</span></button>
  <button class="filter-chip" data-filter="ready">جاهز <span class="filter-count" id="fc-ready">0</span></button>
  <button class="filter-chip" data-filter="setup">تحضير <span class="filter-count" id="fc-setup">0</span></button>
  <button class="filter-chip" data-filter="discovery">استكشاف <span class="filter-count" id="fc-discovery">0</span></button>
</div>

<!-- MAIN CONTENT -->
<main class="main" id="main-content">
  <div class="state-overlay" id="loading-state">
    <div class="spinner"></div>
    <div class="state-text">جاري تحميل البيانات...</div>
  </div>
  <div class="state-overlay" id="error-state" style="display:none">
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--red)" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
    <div class="state-text">فشل تحميل البيانات</div>
    <button class="btn-retry" id="btn-retry">إعادة المحاولة</button>
  </div>
  <div id="data-content" style="display:none">
    <!-- HERO -->
    <div id="hero-section"></div>
    <!-- TABLE -->
    <div id="table-section"></div>
    <!-- POSITIONS -->
    <div id="positions-section"></div>
  </div>
</main>

<!-- FOOTER -->
<footer class="footer">
  <div>هذه المنصة للأغراض التعليمية فقط ولا تُعد نصيحة استثمارية. جميع القرارات على مسؤولية المستخدم.</div>
  <div class="footer-time" id="footer-time">آخر تحديث: --</div>
</footer>

<script>
(function(){
"use strict";

/* ===== State ===== */
let allSignals = [];
let activeFilter = 'all';
let refreshTimer = null;

/* ===== Helpers ===== */
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const ltr = v => `<span class="ltr">${v}</span>`;
const fmtNum = (n,d=2) => n!=null ? Number(n).toFixed(d) : '—';
const fmtPct = n => n!=null ? (n>=0?'+':'')+Number(n).toFixed(2)+'%' : '—';
const pctDir = n => n>0?'up':n<0?'dn':'flat';

function confColor(s){
  if(s==null) return 'var(--text-3)';
  if(s>=71) return 'var(--green)';
  if(s>=50) return 'var(--gold)';
  if(s>=40) return 'var(--amber)';
  return 'var(--red)';
}
function confTier(s){
  if(s==null) return '';
  if(s>=71) return 'tier-s';
  if(s>=50) return 'tier-m';
  if(s>=40) return 'tier-n';
  return 'tier-w';
}

function verdictPill(key,label){
  const map = {
    'شراء':'pill-buy','buy':'pill-buy',
    'مراقبة':'pill-watch','watch':'pill-watch',
    'مراجعة':'pill-review','review':'pill-review',
    'تجنب':'pill-avoid','avoid':'pill-avoid',
    'حياد':'pill-neutral','neutral':'pill-neutral',
    'ابقاء':'pill-hold','hold':'pill-hold'
  };
  const cls = map[(key||'').toLowerCase()] || map[(label||'').toLowerCase()] || 'pill-neutral';
  return `<span class="pill ${cls}">${label||key||'—'}</span>`;
}

function stateTag(st){
  const map = {manage:'st-manage',entered:'st-entered',ready:'st-ready',setup:'st-setup',discovery:'st-discovery'};
  const labels = {manage:'إدارة',entered:'داخل',ready:'جاهز',setup:'تحضير',discovery:'استكشاف'};
  const cls = map[st]||'st-discovery';
  return `<span class="state-tag ${cls}">${labels[st]||st||'—'}</span>`;
}

function emaText(st){
  if(!st) return {t:'—',c:'var(--text-3)'};
  const s = st.toLowerCase();
  if(s==='bullish') return {t:'▲ صاعد',c:'var(--green)'};
  if(s==='bearish') return {t:'▼ هابط',c:'var(--red)'};
  return {t:'— مختلط',c:'var(--text-3)'};
}

function momentumText(m){
  if(!m) return {t:'—',c:'var(--text-3)'};
  const s = m.toLowerCase().replace(/ /g,'_');
  if(s==='accelerating_bullish') return {t:'▲▲ تسارع',c:'var(--green)'};
  if(s==='decelerating_bullish') return {t:'▲ تباطؤ',c:'var(--green-bright)'};
  if(s==='accelerating_bearish') return {t:'▼▼ تسارع',c:'var(--red)'};
  if(s==='decelerating_bearish') return {t:'▼ تباطؤ',c:'var(--red-bright)'};
  return {t:'—',c:'var(--text-3)'};
}

/* ===== Clock ===== */
function updateClock(){
  const now = new Date();
  const kw = new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Kuwait',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(now);
  $('#clock').textContent = kw;
}
setInterval(updateClock,1000);
updateClock();

/* ===== Filters ===== */
$('#filter-bar').addEventListener('click',e=>{
  const chip = e.target.closest('.filter-chip');
  if(!chip) return;
  $$('.filter-chip').forEach(c=>c.classList.remove('active'));
  chip.classList.add('active');
  activeFilter = chip.dataset.filter;
  renderTable();
});

/* ===== Refresh ===== */
$('#btn-refresh').addEventListener('click',()=>fetchData());
$('#btn-retry').addEventListener('click',()=>fetchData());

/* ===== Fetch ===== */
async function fetchData(){
  const btn = $('#btn-refresh');
  btn.classList.add('spinning');
  try{
    const r = await fetch('/dashboard/signals');
    if(!r.ok) throw new Error(r.status);
    const d = await r.json();
    processData(d);
    /* Brain badge */
    try{
      var dc=d.decision_card||{};var cd=dc.confluence_detail||{};
      if(cd.brain_weighted){
        var regime=cd.regime||'';
        var regimeAr=regime==='trending'?'\u0627\u062a\u062c\u0627\u0647\u064a':regime==='ranging'?'\u0639\u0631\u0636\u064a':'\u0627\u0646\u062a\u0642\u0627\u0644\u064a';
        var el=document.getElementById('brain-radar-badge');
        if(!el){el=document.createElement('div');el.id='brain-radar-badge';el.style.cssText='text-align:center;padding:4px 0 8px';
          var main=document.querySelector('.main')||document.body;
          var first=main.firstElementChild;if(first)main.insertBefore(el,first.nextSibling);else main.appendChild(el);}
        el.innerHTML='<span style="display:inline-flex;align-items:center;gap:5px;background:rgba(198,151,75,0.08);border:1px solid rgba(198,151,75,0.25);color:#C6974B;font-size:11px;padding:3px 12px;border-radius:12px;font-weight:600">\u{1F9E0} \u0623\u0648\u0632\u0627\u0646 \u0630\u0643\u064a\u0629 (Brain) \u2022 \u0646\u0638\u0627\u0645: '+regimeAr+'</span>';
      }
    }catch(e){}
    showContent();
  }catch(e){
    console.error('Fetch error:',e);
    showError();
  }finally{
    btn.classList.remove('spinning');
    scheduleRefresh();
  }
}

function scheduleRefresh(){
  if(refreshTimer) clearTimeout(refreshTimer);
  refreshTimer = setTimeout(fetchData,120000);
}

function showContent(){
  $('#loading-state').style.display='none';
  $('#error-state').style.display='none';
  $('#data-content').style.display='block';
}
function showError(){
  $('#loading-state').style.display='none';
  $('#error-state').style.display='flex';
  $('#data-content').style.display='none';
}

/* ===== Process ===== */
function processData(d){
  // Status chips
  const mo = d.market_open;
  const bo = d.bridge_online;
  $('#dot-market').className = 'status-dot '+(mo?'on':'off');
  $('#lbl-market').textContent = mo?'السوق مفتوح':'السوق مغلق';
  $('#dot-bridge').className = 'status-dot '+(bo?'on':'off');
  const bc = d.bridge_cached_count!=null ? ` (${d.bridge_cached_count})` : '';
  $('#lbl-bridge').textContent = (bo?'الربط متصل':'الربط غير متصل') + bc;

  // Signal counts
  const sc = d.signal_counts || {};
  const total = (sc.discovery||0)+(sc.setup||0)+(sc.ready||0)+(sc.entered||0)+(sc.manage||0);
  $('#fc-all').textContent = total;
  $('#fc-manage').textContent = sc.manage||0;
  $('#fc-entered').textContent = sc.entered||0;
  $('#fc-ready').textContent = sc.ready||0;
  $('#fc-setup').textContent = sc.setup||0;
  $('#fc-discovery').textContent = sc.discovery||0;

  // Merge all signals
  allSignals = d.all_signals || [];

  // Ticker strip
  renderTicker(d.opportunities || d.all_signals || []);

  // Hero card
  renderHero(d.decision_card);

  // Table
  renderTable();

  // Positions
  renderPositions(d.open_positions || []);

  // Footer
  const ts = d.timestamp ? new Date(d.timestamp).toLocaleString('ar-KW',{timeZone:'Asia/Kuwait'}) : new Date().toLocaleString('ar-KW',{timeZone:'Asia/Kuwait'});
  $('#footer-time').textContent = 'آخر تحديث: ' + ts;
}

/* ===== Ticker ===== */
function renderTicker(list){
  const top = list.slice(0,8);
  if(!top.length){$('#ticker-track').innerHTML='';return;}
  const items = top.map(s=>{
    const dir = pctDir(s.change_pct);
    return `<div class="ticker-item">
      <span class="ticker-sym">${s.symbol||''}</span>
      <span class="ticker-price">${ltr(fmtNum(s.price,3))}</span>
      <span class="ticker-chg ${dir}">${ltr(fmtPct(s.change_pct))}</span>
    </div>`;
  }).join('');
  // Duplicate for seamless scroll
  $('#ticker-track').innerHTML = items + items;
}

/* ===== Hero ===== */
function renderHero(card){
  const sec = $('#hero-section');
  if(!card){sec.innerHTML='';return;}
  const dir = pctDir(card.change_pct);
  const cc = confColor(card.confluence_score);
  const ema = emaText(card.ema_state);
  const mom = momentumText(card.macd_momentum);
  sec.innerHTML = `
  <div class="hero-card" style="border-right-color:${cc}">
    <div class="hero-label">🎯 القرار الأفضل</div>
    <div class="hero-top">
      <div class="hero-ident">
        <div class="hero-sym">${ltr(card.symbol||'')}</div>
        <div class="hero-name">${card.name_ar||''}</div>
      </div>
      <div class="hero-price-block">
        <div class="hero-price">${ltr(fmtNum(card.price,3))}</div>
        <div class="hero-chg ${dir}">${ltr(fmtPct(card.change_pct))}</div>
      </div>
    </div>
    <div class="hero-badges">
      ${verdictPill(card.verdict_key, card.verdict)}
      ${stateTag(card.trade_state)}
    </div>
    <div class="hero-metrics">
      <div class="metric-box">
        <div class="metric-label">Confluence</div>
        <div class="metric-val" style="color:${cc}">${ltr(card.confluence_score!=null?card.confluence_score:'—')}</div>
      </div>
      <div class="metric-box">
        <div class="metric-label">RSI</div>
        <div class="metric-val">${ltr(fmtNum(card.rsi_14,1))}</div>
      </div>
      <div class="metric-box">
        <div class="metric-label">EMA</div>
        <div class="metric-val" style="color:${ema.c}">${ema.t}</div>
      </div>
      <div class="metric-box">
        <div class="metric-label">MACD</div>
        <div class="metric-val" style="color:${mom.c}">${mom.t}</div>
      </div>
      <div class="metric-box">
        <div class="metric-label">ADX</div>
        <div class="metric-val">${ltr(fmtNum(card.adx,1))}</div>
      </div>
      <div class="metric-box">
        <div class="metric-label">Vol Ratio</div>
        <div class="metric-val">${ltr(fmtNum(card.vol_ratio,2))}</div>
      </div>
      <div class="metric-box">
        <div class="metric-label">Stoch K</div>
        <div class="metric-val">${ltr(fmtNum(card.stoch_k,1))}</div>
      </div>
      <div class="metric-box">
        <div class="metric-label">BB Squeeze</div>
        <div class="metric-val">${card.bb_squeeze===true?'<span style="color:var(--amber)">⬤ ضغط</span>':'<span style="color:var(--text-3)">—</span>'}</div>
      </div>
    </div>
    <div class="hero-levels">
      <div class="level-item"><span class="level-dot support"></span><span class="level-label">الدعم</span><span class="level-val">${ltr(fmtNum(card.support,3))}</span></div>
      <div class="level-item"><span class="level-dot resistance"></span><span class="level-label">المقاومة</span><span class="level-val">${ltr(fmtNum(card.resistance,3))}</span></div>
      <div class="level-item"><span class="level-dot atr"></span><span class="level-label">ATR</span><span class="level-val">${ltr(fmtNum(card.atr_14,3))}</span></div>
    </div>
  </div>`;
}

/* ===== Table ===== */
function renderTable(){
  const sec = $('#table-section');
  let list = allSignals;
  if(activeFilter!=='all'){
    list = list.filter(s=>(s.trade_state||'').toLowerCase()===activeFilter);
  }
  const rows = list.slice(0,15);
  if(!rows.length){
    sec.innerHTML = `<div class="section-title">أهم الفرص</div><div class="empty-state">لا توجد إشارات${activeFilter!=='all'?' لهذا الفلتر':''}</div>`;
    return;
  }
  let html = `<div class="section-title">أهم الفرص <span class="count">${ltr(rows.length)}</span></div>`;
  html += `<div class="table-wrap"><table>
    <thead><tr>
      <th>السهم</th><th>الحالة</th><th>السعر</th><th>التغير%</th>
      <th>Confluence</th><th>القرار</th><th>EMA</th><th>RSI</th>
      <th>Momentum</th><th>ADX</th><th>النظام</th><th>Vol</th>
    </tr></thead><tbody>`;
  rows.forEach(s=>{
    const dir = pctDir(s.change_pct);
    const cc = confColor(s.confluence_score);
    const ema = emaText(s.ema_state);
    const mom = momentumText(s.macd_momentum);
    const confW = s.confluence_score!=null ? Math.min(s.confluence_score,100) : 0;
    html += `<tr>
      <td style="cursor:pointer" onclick="showPersonality('${s.symbol||''}')" title="&#1588;&#1582;&#1589;&#1610;&#1577; &#1575;&#1604;&#1587;&#1607;&#1605;"><span class="cell-sym">${ltr(s.symbol||'')}</span><span class="cell-name">${s.name_ar||''}</span></td>
      <td>${stateTag(s.trade_state)}</td>
      <td class="cell-mono">${ltr(fmtNum(s.price,3))}</td>
      <td class="cell-mono" style="color:var(--${dir==='up'?'green':dir==='dn'?'red':'text-3'})">${ltr(fmtPct(s.change_pct))}</td>
      <td><div class="confluence-cell"><span class="cell-mono" style="color:${cc}">${ltr(s.confluence_score!=null?s.confluence_score:'—')}</span><div class="conf-bar"><div class="conf-fill" style="width:${confW}%;background:${cc}"></div></div></div></td>
      <td>${verdictPill(s.verdict_key, s.verdict)}</td>
      <td style="color:${ema.c}">${ema.t}</td>
      <td class="cell-mono">${ltr(fmtNum(s.rsi_14,1))}</td>
      <td style="color:${mom.c}">${mom.t}</td>
      <td class="cell-mono">${ltr(fmtNum(s.adx,1))}</td>
      <td style="font-size:.72rem;white-space:nowrap">${(s.adx||0)>=25?'<span style="color:var(--green)">\u{1F7E2} \u0627\u062A\u062C\u0627\u0647\u064A</span>':(s.adx||0)<=20?'<span style="color:var(--red)">\u{1F534} \u0639\u0631\u0636\u064A</span>':'<span style="color:var(--amber)">\u{1F7E1} \u0627\u0646\u062A\u0642\u0627\u0644\u064A</span>'}</td>
      <td class="cell-mono">${ltr(fmtNum(s.vol_ratio,2))}</td>
    </tr>`;
  });
  html += '</tbody></table></div>';
  sec.innerHTML = html;
}

/* ===== Positions ===== */
function renderPositions(list){
  const sec = $('#positions-section');
  if(!list.length){sec.innerHTML='';return;}
  let html = `<div class="section-title">المراكز المفتوحة <span class="count">${ltr(list.length)}</span></div>`;
  html += '<div class="positions-grid">';
  list.forEach(p=>{
    const pDir = p.pnl_pct>=0?'up':'dn';
    const stMap = {manage:'st-manage',entered:'st-entered',ready:'st-ready',setup:'st-setup',discovery:'st-discovery'};
    const stCls = stMap[p.state]||'st-discovery';
    const stLabels = {manage:'إدارة',entered:'داخل',ready:'جاهز',setup:'تحضير',discovery:'استكشاف'};
    html += `<div class="pos-card">
      <div class="pos-top">
        <span class="pos-sym">${ltr(p.symbol||'')}</span>
        <span class="pos-state ${stCls}">${stLabels[p.state]||p.state||''}</span>
      </div>
      <div class="pos-row"><span class="pos-label">الدخول</span><span class="pos-val">${ltr(fmtNum(p.entry,3))}</span></div>
      <div class="pos-row"><span class="pos-label">الحالي</span><span class="pos-val">${ltr(fmtNum(p.current,3))}</span></div>
      <div class="pos-row"><span class="pos-label">الربح/الخسارة</span>
        <span class="pos-pnl ${pDir}">${ltr(fmtPct(p.pnl_pct))} &nbsp; ${ltr(fmtNum(p.pnl_kwd,1))} KWD</span>
      </div>
    </div>`;
  });
  html += '</div>';
  sec.innerHTML = html;
}

/* ===== Init ===== */
fetchData();

})();
</script>
<!-- PERSONALITY POPUP -->
<div id="personalityPopup" style="display:none;position:fixed;inset:0;z-index:500;background:rgba(7,13,23,.85);backdrop-filter:blur(8px);align-items:center;justify-content:center;padding:1rem" onclick="if(event.target===this)closePersonality()">
  <div style="background:var(--navy-800);border:1px solid var(--gold-br);border-radius:16px;max-width:680px;width:100%;max-height:85vh;overflow-y:auto;padding:1.25rem;position:relative">
    <button onclick="closePersonality()" style="position:absolute;top:.75rem;left:.75rem;background:none;border:none;color:var(--text-3);font-size:1.2rem;cursor:pointer">&times;</button>
    <div id="personalityContent"></div>
    <div style="text-align:center;margin-top:1rem"><a id="personalityLink" href="#" style="font-size:.75rem;color:var(--gold)">&#1601;&#1578;&#1581; &#1575;&#1604;&#1589;&#1601;&#1581;&#1577; &#1575;&#1604;&#1603;&#1575;&#1605;&#1604;&#1577; &#8594;</a></div>
  </div>
</div>
<script>
function closePersonality(){document.getElementById('personalityPopup').style.display='none'}
async function showPersonality(sym){
  var popup=document.getElementById('personalityPopup');
  var content=document.getElementById('personalityContent');
  var link=document.getElementById('personalityLink');
  popup.style.display='flex';
  content.innerHTML='<div style="text-align:center;padding:2rem;color:var(--text-3)">&#1580;&#1575;&#1585;&#1610; &#1575;&#1604;&#1578;&#1581;&#1605;&#1610;&#1604;...</div>';
  link.href='personality?symbol='+sym;
  try{
    var r=await fetch('/api/stocks/symbol/'+sym);
    if(!r.ok)throw new Error(r.status);
    var d=await r.json();var p=d.profile||{};var pats=d.top_patterns||[];var notes=d.notes||'';
    var h='<div style="text-align:center;margin-bottom:1rem">';
    h+='<div style="font-family:var(--fm);font-size:1.3rem;font-weight:700;color:var(--gold)">'+sym+'</div>';
    h+='<div style="font-size:.8rem;color:var(--text-2);margin-top:.25rem">'+(p.personality_ar||'')+'</div>';
    h+='<div style="margin-top:.5rem;display:flex;justify-content:center;gap:1.5rem">';
    h+='<span style="font-family:var(--fm);color:var(--green);font-weight:700">'+((p.baseline_win_rate||0)*100).toFixed(1)+'%</span>';
    h+='<span style="font-family:var(--fm);color:var(--cyan)">'+((p.reward_risk_ratio||0)).toFixed(1)+'x R/R</span>';
    h+='<span style="font-family:var(--fm);color:var(--amber)">'+(p.signals_count||0)+' sig</span>';
    h+='</div></div>';
    h+='<div style="font-size:.75rem;color:var(--text-3);margin-bottom:.5rem">Driver: <span style="color:var(--cyan);font-weight:700">'+(p.dominant_driver||'-')+'</span></div>';
    if(pats.length>0){
      h+='<div style="font-size:.78rem;font-weight:600;color:var(--gold);margin:.75rem 0 .4rem">\u{1F3C6} Top 3:</div>';
      pats.slice(0,3).forEach(function(pt){
        var wc=pt.win_rate>=0.6?'var(--green)':pt.win_rate>=0.4?'var(--amber)':'var(--red)';
        h+='<div style="background:var(--navy-900);border-radius:8px;padding:.5rem .75rem;margin-bottom:.4rem;font-size:.78rem">';
        h+='<span style="color:var(--cyan)">'+pt.pattern_ar+'</span>';
        h+=' <span style="font-family:var(--fm);color:'+wc+';font-weight:600">'+pt.hits+'/'+pt.occurrences+' ('+(pt.win_rate*100).toFixed(0)+'%)</span>';
        h+=' <span style="font-family:var(--fm);color:var(--green)">+'+((pt.avg_gain_pct||0)).toFixed(1)+'%</span>';
        h+='</div>';
      });
    }
    content.innerHTML=h;
  }catch(e){content.innerHTML='<div style="color:var(--red);text-align:center">Error: '+e.message+'</div>'}
}
window.showPersonality=showPersonality;
</script>
<script src="indicator-tooltips.js"></script>
</body>
</html>

```


############################################################
# FILE: www/trading/signals.html (1067 lines)
############################################################

```html
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>مصفوفة التحليل — KSE</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Noto+Kufi+Arabic:wght@400;500;600;700&family=Tajawal:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>
:root{
  --navy-900:#070D17;--navy-800:#0C1525;--navy-700:#111E32;
  --navy-600:#162840;--navy-500:#1C334F;--navy-400:#24405F;
  --gold:#C6974B;--gold-bright:#D4A95C;--gold-dim:#9E7A3D;
  --gold-bg:rgba(198,151,75,.06);--gold-br:rgba(198,151,75,.25);
  --green:#4CAF82;--green-bright:#5BC492;--green-bg:rgba(76,175,130,.08);--green-br:rgba(76,175,130,.3);
  --red:#D94452;--red-bright:#E5606C;--red-bg:rgba(217,68,82,.08);--red-br:rgba(217,68,82,.3);
  --amber:#E8A838;--amber-bg:rgba(232,168,56,.08);--amber-br:rgba(232,168,56,.3);
  --cyan:#38BDF8;--cyan-bg:rgba(56,189,248,.08);--cyan-br:rgba(56,189,248,.3);
  --text:#E8ECF0;--text-2:#A0ADBC;--text-3:#6B7D90;--text-4:#405060;
  --card:#0E1929;--card-hover:#132137;--card-border:#1A2E45;
  --f:'Tajawal','Noto Kufi Arabic',sans-serif;
  --fd:'Noto Kufi Arabic','Tajawal',sans-serif;
  --fm:'IBM Plex Mono','Consolas',monospace;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{
  font-family:var(--f);font-variant-numeric:tabular-nums;
  background:var(--navy-900);color:var(--text);
  min-height:100vh;line-height:1.6;-webkit-font-smoothing:antialiased;
}
.ltr{direction:ltr;unicode-bidi:isolate}
a{color:var(--gold);text-decoration:none}
a:hover{color:var(--gold-bright)}

/* ===== TOPBAR ===== */
.topbar{
  position:sticky;top:0;z-index:100;
  background:rgba(7,13,23,.92);backdrop-filter:blur(16px);
  border-bottom:1px solid var(--card-border);
  padding:0 1.25rem;height:56px;
  display:flex;align-items:center;justify-content:space-between;gap:.75rem;
}
.topbar-brand{display:flex;align-items:center;gap:.75rem;flex-shrink:0}
.brand-mark{
  background:linear-gradient(135deg,var(--gold),var(--gold-dim));
  color:var(--navy-900);font-family:var(--fm);font-weight:700;
  font-size:.85rem;padding:.25rem .6rem;border-radius:4px;letter-spacing:.5px;
}
.topbar-title{font-family:var(--fd);font-weight:700;font-size:1rem;color:var(--text)}
.topbar-tag{
  font-size:.65rem;background:var(--navy-600);color:var(--text-3);
  padding:2px 8px;border-radius:10px;white-space:nowrap;
}
.topbar-center{display:flex;align-items:center;gap:.5rem;flex-shrink:0}
.status-chip{
  display:flex;align-items:center;gap:.35rem;
  font-size:.75rem;padding:.25rem .65rem;border-radius:20px;
  border:1px solid var(--card-border);background:var(--navy-800);
  color:var(--text-2);white-space:nowrap;
}
.status-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.status-dot.on{background:var(--green);box-shadow:0 0 6px var(--green)}
.status-dot.off{background:var(--red);box-shadow:0 0 6px var(--red)}
.topbar-right{display:flex;align-items:center;gap:.75rem;flex-shrink:0}
.clock{font-family:var(--fm);font-size:.85rem;color:var(--gold);direction:ltr;unicode-bidi:isolate;white-space:nowrap}
.btn-refresh{
  background:none;border:1px solid var(--card-border);color:var(--text-2);
  width:34px;height:34px;border-radius:8px;cursor:pointer;
  display:flex;align-items:center;justify-content:center;transition:all .2s;
}
.btn-refresh:hover{border-color:var(--gold-br);color:var(--gold)}
.btn-refresh.spinning svg{animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.nav-links{display:flex;gap:.15rem}
.nav-link{
  font-size:.75rem;padding:.3rem .6rem;border-radius:6px;color:var(--text-3);transition:all .2s;
}
.nav-link:hover{color:var(--text);background:var(--navy-700)}
.nav-link.active{color:var(--gold);background:var(--gold-bg);border:1px solid var(--gold-br)}

/* ===== PULSE BAR ===== */
.pulse-bar{
  background:var(--navy-800);border-bottom:1px solid var(--card-border);
  padding:.85rem 1.25rem;display:flex;align-items:center;gap:1.25rem;
  overflow-x:auto;-webkit-overflow-scrolling:touch;
}
.pulse-stat{display:flex;flex-direction:column;align-items:center;gap:.15rem;min-width:70px}
.pulse-val{font-family:var(--fm);font-size:1.35rem;font-weight:700;color:var(--text)}
.pulse-label{font-size:.68rem;color:var(--text-3);white-space:nowrap}
.pulse-divider{width:1px;height:36px;background:var(--card-border);flex-shrink:0}
.pulse-chips{display:flex;align-items:center;gap:.4rem;flex-wrap:wrap}
.pulse-chip{
  font-size:.72rem;padding:.25rem .65rem;border-radius:14px;
  font-family:var(--fm);font-weight:600;display:flex;align-items:center;gap:.3rem;
  white-space:nowrap;
}
.pc-manage{background:var(--green-bg);color:var(--green);border:1px solid var(--green-br)}
.pc-entered{background:var(--cyan-bg);color:var(--cyan);border:1px solid var(--cyan-br)}
.pc-ready{background:var(--gold-bg);color:var(--gold);border:1px solid var(--gold-br)}
.pc-setup{background:var(--amber-bg);color:var(--amber);border:1px solid var(--amber-br)}
.pc-discovery{background:var(--navy-700);color:var(--text-3);border:1px solid var(--card-border)}

/* ===== FILTER CONTROLS ===== */
.filter-bar{
  display:flex;align-items:center;gap:.5rem;padding:.75rem 1.25rem;
  background:var(--navy-800);border-bottom:1px solid var(--card-border);
  overflow-x:auto;-webkit-overflow-scrolling:touch;flex-wrap:wrap;
}
.filter-search{
  font-family:var(--f);font-size:.82rem;
  background:var(--navy-700);border:1px solid var(--card-border);
  color:var(--text);padding:.4rem .75rem;border-radius:8px;
  outline:none;min-width:160px;transition:border-color .2s;
}
.filter-search:focus{border-color:var(--gold-br)}
.filter-search::placeholder{color:var(--text-4)}
.filter-select{
  font-family:var(--f);font-size:.78rem;
  background:var(--navy-700);border:1px solid var(--card-border);
  color:var(--text-2);padding:.4rem .65rem;border-radius:8px;
  outline:none;cursor:pointer;-webkit-appearance:none;appearance:none;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236B7D90' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:left .5rem center;padding-left:1.5rem;
}
.filter-select:focus{border-color:var(--gold-br)}
.filter-label{font-size:.7rem;color:var(--text-3);white-space:nowrap}

/* ===== MAIN ===== */
.main{max-width:100%;margin:0 auto;padding:.75rem 1rem 2rem}

/* ===== PILLS & TAGS ===== */
.pill{
  font-size:.68rem;font-weight:600;padding:.15rem .55rem;border-radius:14px;
  display:inline-flex;align-items:center;gap:.2rem;white-space:nowrap;
}
.pill-buy{background:var(--green-bg);color:var(--green);border:1px solid var(--green-br)}
.pill-watch{background:var(--amber-bg);color:var(--amber);border:1px solid var(--amber-br)}
.pill-review{background:var(--cyan-bg);color:var(--cyan);border:1px solid var(--cyan-br)}
.pill-avoid{background:var(--red-bg);color:var(--red);border:1px solid var(--red-br)}
.pill-neutral{background:var(--navy-700);color:var(--text-3);border:1px solid var(--card-border)}
.pill-hold{background:rgba(168,85,247,.08);color:#A855F7;border:1px solid rgba(168,85,247,.3)}
.state-tag{
  font-size:.65rem;padding:.15rem .5rem;border-radius:4px;font-family:var(--fm);
  display:inline-block;white-space:nowrap;
}
.st-manage{background:var(--green-bg);color:var(--green);border:1px solid var(--green-br)}
.st-entered{background:var(--cyan-bg);color:var(--cyan);border:1px solid var(--cyan-br)}
.st-ready{background:var(--gold-bg);color:var(--gold);border:1px solid var(--gold-br)}
.st-setup{background:var(--amber-bg);color:var(--amber);border:1px solid var(--amber-br)}
.st-discovery{background:var(--navy-700);color:var(--text-3);border:1px solid var(--card-border)}

/* ===== TABLE ===== */
.table-wrap{
  overflow-x:auto;-webkit-overflow-scrolling:touch;
  border:1px solid var(--card-border);border-radius:10px;
  background:var(--card);
}
table{width:100%;border-collapse:collapse;min-width:1600px}
thead th{
  font-family:var(--fd);font-size:.68rem;font-weight:600;
  color:var(--text-3);padding:.6rem .55rem;
  background:var(--navy-800);border-bottom:1px solid var(--card-border);
  text-align:right;white-space:nowrap;position:sticky;top:0;
  cursor:pointer;user-select:none;transition:color .15s;
}
thead th:hover{color:var(--gold)}
thead th.sorted{color:var(--gold)}
thead th .sort-arrow{font-size:.6rem;margin-right:.2rem;opacity:.5}
thead th.sorted .sort-arrow{opacity:1}
tbody td{
  font-size:.75rem;padding:.5rem .55rem;
  border-bottom:1px solid rgba(26,46,69,.4);white-space:nowrap;
}
tbody tr{transition:background .15s}
tbody tr:hover{background:var(--card-hover)}
tbody tr:last-child td{border-bottom:none}
tbody tr.row-tier-s{background:rgba(76,175,130,.03)}
tbody tr.row-tier-m{background:rgba(198,151,75,.03)}
tbody tr.row-tier-n{background:rgba(232,168,56,.02)}
tbody tr.row-tier-w{background:rgba(217,68,82,.02)}
tbody tr.row-tier-s:hover{background:rgba(76,175,130,.07)}
tbody tr.row-tier-m:hover{background:rgba(198,151,75,.07)}
tbody tr.row-tier-n:hover{background:rgba(232,168,56,.05)}
tbody tr.row-tier-w:hover{background:rgba(217,68,82,.05)}
.cell-sym{font-family:var(--fm);font-weight:600;font-size:.78rem;color:var(--text)}
.cell-name{font-size:.65rem;color:var(--text-3);display:block;max-width:100px;overflow:hidden;text-overflow:ellipsis}
.cell-mono{font-family:var(--fm)}
.confluence-cell{display:flex;align-items:center;gap:.35rem}
.conf-bar{width:44px;height:5px;border-radius:3px;background:var(--navy-600);overflow:hidden;flex-shrink:0}
.conf-fill{height:100%;border-radius:3px;transition:width .4s}
.bb-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--amber);box-shadow:0 0 5px var(--amber)}
.bb-off{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--navy-600)}
.rsi-div-arrow{font-size:.8rem;font-weight:700}
.ema-cross-tag{font-size:.65rem;padding:1px 5px;border-radius:4px;font-family:var(--fm)}
.ema-golden{background:var(--gold-bg);color:var(--gold);border:1px solid var(--gold-br)}
.ema-death{background:var(--red-bg);color:var(--red);border:1px solid var(--red-br)}
.ema-cross-none{color:var(--text-4)}

/* ===== BRIDGE DIAGNOSTICS ===== */
/* ═══ INDICATOR LEGEND ═══ */
.legend-wrap{max-width:1440px;margin:0 auto;padding:0 24px}
.legend-toggle{
  width:100%;padding:12px 18px;background:var(--navy-800);border:1px solid var(--card-border);
  border-radius:10px;color:var(--gold-dim);font-family:var(--fd);font-size:.8rem;font-weight:700;
  cursor:pointer;text-align:right;direction:rtl;display:flex;justify-content:space-between;align-items:center;
  transition:.2s;
}
.legend-toggle:hover{border-color:var(--gold-br);color:var(--gold)}
.legend-toggle.open{border-radius:10px 10px 0 0;border-bottom:none;color:var(--gold)}
.legend-arrow{transition:transform .2s;font-size:.7rem}
.legend-toggle.open .legend-arrow{transform:rotate(180deg)}
.legend-body{
  display:none;background:var(--card);border:1px solid var(--card-border);border-top:none;
  border-radius:0 0 10px 10px;padding:16px 18px;direction:rtl;
}
.legend-body.open{display:block}
.legend-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px 24px}
.legend-item{margin-bottom:4px}
.legend-title{font-family:var(--fd);font-size:.75rem;font-weight:700;color:var(--gold);margin-bottom:6px;letter-spacing:.2px}
.legend-row{font-size:.7rem;color:var(--text-2);line-height:1.8;display:flex;align-items:center;gap:6px}
.legend-row .pill{font-size:.58rem;padding:2px 6px}
.legend-row .bb-dot{flex-shrink:0}
@media(max-width:768px){.legend-grid{grid-template-columns:1fr}.legend-wrap{padding:0 14px}}

.bridge-diag{
  display:flex;align-items:center;gap:1rem;padding:.6rem 1.25rem;
  background:var(--navy-800);border-top:1px solid var(--card-border);
  font-size:.7rem;color:var(--text-3);flex-wrap:wrap;
}
.bridge-diag .bd-item{display:flex;align-items:center;gap:.3rem}
.bridge-diag .bd-label{color:var(--text-4)}
.bridge-diag .bd-val{font-family:var(--fm);color:var(--text-3)}

/* ===== FOOTER ===== */
.footer{
  text-align:center;padding:1.5rem 1rem;
  border-top:1px solid var(--card-border);color:var(--text-4);font-size:.72rem;
}
.footer-time{color:var(--text-3);margin-top:.35rem;font-family:var(--fm);font-size:.7rem}

/* ===== LOADING / ERROR ===== */
.state-overlay{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  padding:4rem 1rem;gap:1rem;
}
.spinner{
  width:40px;height:40px;border:3px solid var(--navy-600);
  border-top-color:var(--gold);border-radius:50%;animation:spin .8s linear infinite;
}
.state-text{color:var(--text-3);font-size:.9rem}
.btn-retry{
  font-family:var(--f);background:var(--gold-bg);border:1px solid var(--gold-br);
  color:var(--gold);padding:.5rem 1.5rem;border-radius:8px;cursor:pointer;
  font-size:.85rem;transition:all .2s;
}
.btn-retry:hover{background:rgba(198,151,75,.15)}
.empty-state{color:var(--text-3);text-align:center;padding:2rem;font-size:.85rem}
.results-count{
  font-size:.72rem;color:var(--text-3);padding:.35rem 0;
  font-family:var(--fm);
}

/* ===== RESPONSIVE ===== */
@media(max-width:1024px){
  .pulse-bar{gap:.75rem;padding:.7rem 1rem}
  .pulse-val{font-size:1.1rem}
}
@media(max-width:768px){
  .topbar{padding:0 .75rem;gap:.4rem}
  .topbar-title{font-size:.85rem}
  .topbar-tag,.nav-links{display:none}
  .topbar-center{gap:.3rem}
  .status-chip{font-size:.68rem;padding:.2rem .5rem}
  .main{padding:.5rem}
  .pulse-bar{padding:.6rem .75rem;gap:.5rem}
  .pulse-val{font-size:1rem}
  .pulse-stat{min-width:55px}
  .filter-bar{padding:.5rem .75rem;gap:.35rem}
  .filter-search{min-width:120px;font-size:.78rem}
}
@media(max-width:480px){
  .pulse-chips{display:none}
  .filter-bar{flex-direction:column;align-items:stretch}
  .filter-search,.filter-select{width:100%}
}
</style>
<link rel="stylesheet" href="indicator-tooltips.css">
</head>
<body>

<!-- TOPBAR -->
<header class="topbar">
  <div class="topbar-brand">
    <span class="brand-mark">KSE</span>
    <span class="topbar-title">مصفوفة التحليل</span>
    <span class="topbar-tag">Master AI</span>
  </div>
  <div class="topbar-center">
    <span class="status-chip" id="chip-market">
      <span class="status-dot off" id="dot-market"></span>
      <span id="lbl-market">السوق مغلق</span>
    </span>
    <span class="status-chip" id="chip-bridge">
      <span class="status-dot off" id="dot-bridge"></span>
      <span id="lbl-bridge">الربط غير متصل</span>
    </span>
  </div>
  <div class="topbar-right">
    <span class="clock" id="clock">--:--:--</span>
    <button class="btn-refresh" id="btn-refresh" title="تحديث">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>
    </button>
    <nav class="nav-links">
      <a href="radar.html" class="nav-link">الرادار</a>
      <a href="signals.html" class="nav-link active">الإشارات</a>
      <a href="positions.html" class="nav-link">المراكز</a>
      <a href="journal.html" class="nav-link">السجل</a>
    </nav>
  </div>
</header>

<!-- SIGNAL PULSE BAR -->
<div class="pulse-bar" id="pulse-bar">
  <div class="pulse-stat">
    <span class="pulse-val" id="p-total">--</span>
    <span class="pulse-label">إجمالي الإشارات</span>
  </div>
  <div class="pulse-divider"></div>
  <div class="pulse-stat">
    <span class="pulse-val" id="p-avg-conf" style="color:var(--gold)">--</span>
    <span class="pulse-label">متوسط Confluence</span>
  </div>
  <div class="pulse-divider"></div>
  <div class="pulse-chips" id="p-chips"></div>
</div>

<!-- TIMEFRAME TABS -->
<div id="tf-tabs" style="display:flex;justify-content:center;gap:6px;padding:8px 12px">
  <button id="tab-30m" class="tf-tab active" onclick="switchTF('30m')" style="padding:6px 20px;border-radius:8px;border:1px solid rgba(52,211,153,0.3);background:rgba(52,211,153,0.08);color:#34D399;font-family:inherit;font-size:13px;font-weight:700;cursor:pointer;transition:.2s">&#x26A1; &#x0628;&#x064A;&#x0627;&#x0646;&#x0627;&#x062A; &#x062D;&#x064A;&#x0629; (30m)</button>
  <button id="tab-1d" class="tf-tab" onclick="switchTF('1d')" style="padding:6px 20px;border-radius:8px;border:1px solid rgba(198,151,75,0.25);background:transparent;color:#6B7280;font-family:inherit;font-size:13px;font-weight:700;cursor:pointer;transition:.2s">&#x1F4C5; &#x0627;&#x0644;&#x062A;&#x062D;&#x0644;&#x064A;&#x0644; &#x0627;&#x0644;&#x064A;&#x0648;&#x0645;&#x064A; (1D)</button>
</div>
<div id="data-source-info" style="text-align:center;font-size:11px;color:#6B7280;padding:0 12px 6px;direction:rtl"></div>
<div id="brain-status-bar" style="display:none;text-align:center;padding:0 12px 8px">
  <span id="brain-badge" style="display:inline-flex;align-items:center;gap:5px;background:rgba(198,151,75,0.08);border:1px solid rgba(198,151,75,0.25);color:#C6974B;font-size:11px;padding:3px 12px;border-radius:12px;font-weight:600">
    &#x1F9E0; <span id="brain-badge-text"></span>
  </span>
</div>

<!-- FILTER CONTROLS -->
<div class="filter-bar" id="filter-bar">
  <input type="text" class="filter-search" id="f-search" placeholder="بحث بالرمز...">
  <span class="filter-label">الحالة:</span>
  <select class="filter-select" id="f-state">
    <option value="all">الكل</option>
    <option value="manage">إدارة</option>
    <option value="entered">داخل</option>
    <option value="ready">جاهز</option>
    <option value="setup">تحضير</option>
    <option value="discovery">استكشاف</option>
  </select>
  <span class="filter-label">أقل Confluence:</span>
  <select class="filter-select" id="f-conf">
    <option value="0">الكل</option>
    <option value="30">30+</option>
    <option value="40">40+</option>
    <option value="50">50+</option>
    <option value="60">60+</option>
    <option value="70">70+</option>
  </select>
  <span class="filter-label">الترتيب:</span>
  <select class="filter-select" id="f-sort">
    <option value="confluence">Confluence</option>
    <option value="rsi">RSI</option>
    <option value="adx">ADX</option>
    <option value="change">%التغير</option>
  </select>
</div>

<!-- MAIN CONTENT -->
<main class="main" id="main-content">
  <div class="state-overlay" id="loading-state">
    <div class="spinner"></div>
    <div class="state-text">جاري تحميل البيانات...</div>
  </div>
  <div class="state-overlay" id="error-state" style="display:none">
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--red)" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
    <div class="state-text">فشل تحميل البيانات</div>
    <button class="btn-retry" id="btn-retry">إعادة المحاولة</button>
  </div>
  <div id="data-content" style="display:none">
    <div class="results-count" id="results-count"></div>
    <div id="table-section"></div>
  </div>
</main>

<!-- INDICATOR LEGEND (collapsible) -->
<div class="legend-wrap" id="legend-wrap">
  <button class="legend-toggle" id="legend-toggle" onclick="document.getElementById('legend-body').classList.toggle('open');this.classList.toggle('open')">
    دليل المؤشرات <span class="legend-arrow">▼</span>
  </button>
  <div class="legend-body" id="legend-body">
    <div class="legend-grid">

      <div class="legend-item">
        <div class="legend-title">Confluence (التوافق 0-100)</div>
        <div class="legend-row"><span style="color:var(--green)">🟢 71+</span> إشارات قوية متفقة على الصعود</div>
        <div class="legend-row"><span style="color:var(--gold)">🟡 50-70</span> أغلب المؤشرات إيجابية</div>
        <div class="legend-row"><span style="color:var(--amber)">🟠 40-49</span> محايد / متضارب</div>
        <div class="legend-row"><span style="color:var(--red)">🔴 أقل من 40</span> أغلب المؤشرات سلبية</div>
      </div>

      <div class="legend-item">
        <div class="legend-title">الحالة (Trade State)</div>
        <div class="legend-row"><span class="pill st-setup">تحضير</span> المؤشرات تتحسن، قبل نقطة الدخول</div>
        <div class="legend-row"><span class="pill st-manage">إدارة</span> مركز مفتوح قيد المتابعة</div>
        <div class="legend-row"><span class="pill st-discovery">استكشاف</span> الرادار اكتشفه مبكراً</div>
      </div>

      <div class="legend-item">
        <div class="legend-title">القرار (Verdict)</div>
        <div class="legend-row"><span class="pill pill-watch">مراقبة</span> راقب بدون دخول</div>
        <div class="legend-row"><span class="pill pill-review">مراجعة</span> راجع مركزك</div>
        <div class="legend-row"><span class="pill pill-avoid">تجنب</span> لا تدخل</div>
      </div>

      <div class="legend-item">
        <div class="legend-title">EMA (المتوسطات المتحركة)</div>
        <div class="legend-row"><span style="color:var(--green);font-weight:700">▲ صاعد</span> السعر فوق المتوسطات (ترند صاعد)</div>
        <div class="legend-row"><span style="color:var(--red);font-weight:700">▼ هابط</span> السعر تحت المتوسطات</div>
      </div>

      <div class="legend-item">
        <div class="legend-title">RSI (القوة النسبية 0-100)</div>
        <div class="legend-row"><span style="color:var(--red)">فوق 70</span> overbought — احتمال تصحيح</div>
        <div class="legend-row"><span style="color:var(--text-2)">30-70</span> منطقة طبيعية</div>
        <div class="legend-row"><span style="color:var(--green)">تحت 30</span> oversold — احتمال ارتداد</div>
      </div>

      <div class="legend-item">
        <div class="legend-title">Momentum (زخم MACD)</div>
        <div class="legend-row"><span style="color:var(--green);font-weight:700">▲▲ تسارع</span> زخم صاعد يزيد (أقوى شراء)</div>
        <div class="legend-row"><span style="color:var(--green);opacity:.6">▲ تباطؤ</span> صاعد يضعف (حذر)</div>
        <div class="legend-row"><span style="color:var(--red);font-weight:700">▼▼ تسارع</span> زخم هابط يزيد (أقوى بيع)</div>
        <div class="legend-row"><span style="color:var(--red);opacity:.6">▼ تباطؤ</span> هابط يخف (ممكن ارتداد)</div>
      </div>

      <div class="legend-item">
        <div class="legend-title">ADX (قوة الترند)</div>
        <div class="legend-row"><span style="font-weight:700;color:var(--text)">فوق 25</span> ترند واضح</div>
        <div class="legend-row"><span style="color:var(--text-3)">تحت 20</span> السوق sideways</div>
      </div>

      <div class="legend-item">
        <div class="legend-title">Vol (نسبة الحجم)</div>
        <div class="legend-row"><span style="color:var(--gold);font-weight:700">فوق 1.5×</span> حجم عالي يدعم الحركة</div>
        <div class="legend-row"><span style="color:var(--text-3)">تحت 0.5×</span> حجم ضعيف (حركة مشكوك فيها)</div>
      </div>

      <div class="legend-item">
        <div class="legend-title">BB Sq (Bollinger Squeeze)</div>
        <div class="legend-row"><span class="bb-dot"></span> ضغط — حركة قوية قريبة</div>
        <div class="legend-row"><span style="color:var(--text-4)">—</span> لا ضغط</div>
      </div>

      <div class="legend-item">
        <div class="legend-title">RSI Div (Divergence)</div>
        <div class="legend-row"><span style="color:var(--green)">▲</span> divergence صاعد (إشارة ارتداد)</div>
        <div class="legend-row"><span style="color:var(--red)">▼</span> divergence هابط (إشارة تصحيح)</div>
      </div>

      <div class="legend-item">
        <div class="legend-title">EMA Cross (تقاطع)</div>
        <div class="legend-row"><span style="color:var(--green)">★ رقم</span> Golden Cross قبل N بار (إيجابي)</div>
      </div>

      <div class="legend-item">
        <div class="legend-title">ATR (متوسط المدى اليومي)</div>
        <div class="legend-row">كم يتحرك السهم يومياً — وقف الخسارة = دخول - 2×ATR</div>
      </div>

    </div>
  </div>
</div>

<!-- BRIDGE DIAGNOSTICS -->
<div class="bridge-diag" id="bridge-diag">
  <div class="bd-item"><span class="bd-label">حالة الربط:</span><span class="bd-val" id="bd-status">--</span></div>
  <div class="bd-item"><span class="bd-label">البيانات المخزنة:</span><span class="bd-val ltr" id="bd-cached">--</span></div>
  <div class="bd-item"><span class="bd-label">آخر تحديث:</span><span class="bd-val ltr" id="bd-time">--</span></div>
</div>

<!-- FOOTER -->
<footer class="footer">
  <div>هذه المنصة للأغراض التعليمية فقط ولا تُعد نصيحة استثمارية. جميع القرارات على مسؤولية المستخدم.</div>
  <div class="footer-time" id="footer-time">آخر تحديث: --</div>
</footer>

<script>
(function(){
"use strict";

/* ===== State ===== */
let allSignals = [];
let liveSignals = [];
let dailySignals = [];
let activeTF = '30m';
let refreshTimer = null;
let sortCol = 'confluence';
let sortAsc = false;
let colSortState = {};

/* ===== Helpers ===== */
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const ltr = v => `<span class="ltr">${v}</span>`;
const fmtNum = (n,d=2) => n!=null ? Number(n).toFixed(d) : '\u2014';
const fmtPct = n => n!=null ? (n>=0?'+':'')+Number(n).toFixed(2)+'%' : '\u2014';
const pctDir = n => n>0?'up':n<0?'dn':'flat';

function confColor(s){
  if(s==null) return 'var(--text-3)';
  if(s>=71) return 'var(--green)';
  if(s>=50) return 'var(--gold)';
  if(s>=40) return 'var(--amber)';
  return 'var(--red)';
}
function confTier(s){
  if(s==null) return '';
  if(s>=71) return 'tier-s';
  if(s>=50) return 'tier-m';
  if(s>=40) return 'tier-n';
  return 'tier-w';
}

function verdictPill(key,label){
  const map = {
    'شراء':'pill-buy','buy':'pill-buy',
    'مراقبة':'pill-watch','watch':'pill-watch',
    'مراجعة':'pill-review','review':'pill-review',
    'تجنب':'pill-avoid','avoid':'pill-avoid',
    'حياد':'pill-neutral','neutral':'pill-neutral',
    'ابقاء':'pill-hold','hold':'pill-hold'
  };
  const cls = map[(key||'').toLowerCase()] || map[(label||'').toLowerCase()] || 'pill-neutral';
  return `<span class="pill ${cls}">${label||key||'\u2014'}</span>`;
}

function stateTag(st){
  const map = {manage:'st-manage',entered:'st-entered',ready:'st-ready',setup:'st-setup',discovery:'st-discovery'};
  const labels = {manage:'\u0625\u062F\u0627\u0631\u0629',entered:'\u062F\u0627\u062E\u0644',ready:'\u062C\u0627\u0647\u0632',setup:'\u062A\u062D\u0636\u064A\u0631',discovery:'\u0627\u0633\u062A\u0643\u0634\u0627\u0641'};
  const cls = map[st]||'st-discovery';
  return `<span class="state-tag ${cls}">${labels[st]||st||'\u2014'}</span>`;
}

function emaText(st){
  if(!st) return {t:'\u2014',c:'var(--text-3)'};
  const s = st.toLowerCase();
  if(s==='bullish') return {t:'\u25B2 \u0635\u0627\u0639\u062F',c:'var(--green)'};
  if(s==='bearish') return {t:'\u25BC \u0647\u0627\u0628\u0637',c:'var(--red)'};
  return {t:'\u2014 \u0645\u062E\u062A\u0644\u0637',c:'var(--text-3)'};
}

function momentumText(m){
  if(!m) return {t:'\u2014',c:'var(--text-3)'};
  const s = m.toLowerCase().replace(/ /g,'_');
  if(s==='accelerating_bullish') return {t:'\u25B2\u25B2 \u062A\u0633\u0627\u0631\u0639',c:'var(--green)'};
  if(s==='decelerating_bullish') return {t:'\u25B2 \u062A\u0628\u0627\u0637\u0624',c:'var(--green-bright)'};
  if(s==='accelerating_bearish') return {t:'\u25BC\u25BC \u062A\u0633\u0627\u0631\u0639',c:'var(--red)'};
  if(s==='decelerating_bearish') return {t:'\u25BC \u062A\u0628\u0627\u0637\u0624',c:'var(--red-bright)'};
  return {t:'\u2014',c:'var(--text-3)'};
}

function rsiColor(v){
  if(v==null) return 'var(--text-2)';
  if(v>70) return 'var(--red)';
  if(v<30) return 'var(--green)';
  return 'var(--text-2)';
}

function bbSqueezeHtml(v){
  if(v===true || v==='true' || v===1) return '<span class="bb-dot" title="BB Squeeze Active"></span>';
  return '<span class="bb-off"></span>';
}

function rsiDivHtml(v){
  if(!v) return '<span style="color:var(--text-4)">\u2014</span>';
  const s = String(v).toLowerCase();
  if(s==='bullish'||s==='bull') return '<span class="rsi-div-arrow" style="color:var(--green)">\u25B2</span>';
  if(s==='bearish'||s==='bear') return '<span class="rsi-div-arrow" style="color:var(--red)">\u25BC</span>';
  return '<span style="color:var(--text-4)">\u2014</span>';
}

function emaCrossHtml(ec){
  if(!ec||!ec.type) return '<span class="ema-cross-none">\u2014</span>';
  const t = ec.type.toLowerCase();
  const bars = ec.bars_ago!=null ? ec.bars_ago : '';
  if(t==='golden'||t==='golden_cross'){
    return `<span class="ema-cross-tag ema-golden">\u2606 ${bars}</span>`;
  }
  if(t==='death'||t==='death_cross'){
    return `<span class="ema-cross-tag ema-death">\u2620 ${bars}</span>`;
  }
  return '<span class="ema-cross-none">\u2014</span>';
}

/* ===== Clock ===== */
function updateClock(){
  const now = new Date();
  const kw = new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Kuwait',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(now);
  $('#clock').textContent = kw;
}
setInterval(updateClock,1000);
updateClock();

/* ===== Filters ===== */
$('#f-search').addEventListener('input',()=>renderTable());
$('#f-state').addEventListener('change',()=>renderTable());
$('#f-conf').addEventListener('change',()=>renderTable());
$('#f-sort').addEventListener('change',()=>{
  sortCol = $('#f-sort').value;
  sortAsc = false;
  colSortState = {};
  renderTable();
});

/* ===== Refresh ===== */
$('#btn-refresh').addEventListener('click',()=>fetchData());
$('#btn-retry').addEventListener('click',()=>fetchData());

/* ===== Tab Switching ===== */
function switchTF(tf){
  activeTF = tf;
  const tab30 = $('#tab-30m');
  const tab1d = $('#tab-1d');
  if(tf==='30m'){
    tab30.style.background='rgba(52,211,153,0.08)';tab30.style.borderColor='rgba(52,211,153,0.3)';tab30.style.color='#34D399';
    tab1d.style.background='transparent';tab1d.style.borderColor='rgba(198,151,75,0.25)';tab1d.style.color='#6B7280';
    allSignals = liveSignals;
    $('#data-source-info').textContent = liveSignals.length ? '\u26A1 '+liveSignals.length+' \u0625\u0634\u0627\u0631\u0629 \u0645\u0646 Bridge (30 \u062F\u0642\u064A\u0642\u0629)' : '\u0644\u0627 \u0628\u064A\u0627\u0646\u0627\u062A \u062D\u064A\u0629 \u2014 Bridge \u063A\u064A\u0631 \u0645\u062A\u0635\u0644 \u0623\u0648 \u0627\u0644\u0633\u0648\u0642 \u0645\u063A\u0644\u0642';
  } else {
    tab1d.style.background='rgba(198,151,75,0.08)';tab1d.style.borderColor='rgba(198,151,75,0.3)';tab1d.style.color='#C6974B';
    tab30.style.background='transparent';tab30.style.borderColor='rgba(52,211,153,0.25)';tab30.style.color='#6B7280';
    allSignals = dailySignals;
    const age = dailySignals[0] && dailySignals[0].data_age_hours ? Math.round(dailySignals[0].data_age_hours)+'h' : '';
    $('#data-source-info').textContent = dailySignals.length ? '\u{1F4C5} '+dailySignals.length+' \u0633\u0647\u0645 \u0645\u0646 \u0627\u0644\u062A\u062D\u0644\u064A\u0644 \u0627\u0644\u064A\u0648\u0645\u064A (1D) \u2014 \u0639\u0645\u0631 \u0627\u0644\u0628\u064A\u0627\u0646\u0627\u062A: '+age+' \u2014 StochK, ADX, RSI Div, ATR \u063A\u064A\u0631 \u0645\u062A\u0648\u0641\u0631\u0629 \u0641\u064A \u0627\u0644\u064A\u0648\u0645\u064A' : '\u0644\u0627 \u0628\u064A\u0627\u0646\u0627\u062A \u064A\u0648\u0645\u064A\u0629 \u0645\u062D\u0641\u0648\u0638\u0629';
  }
  renderTable();
  /* Update pulse bar */
  const total = allSignals.length;
  const avgConf = total > 0 ? (allSignals.reduce((s,x)=>s+(x.confluence_score||0),0)/total).toFixed(1) : '--';
  $('#p-total').textContent = total;
  $('#p-avg-conf').textContent = avgConf;
}
window.switchTF = switchTF;

/* ===== Fetch ===== */
async function fetchData(){
  const btn = $('#btn-refresh');
  btn.classList.add('spinning');
  try{
    const [r1, r2, r30m] = await Promise.all([
      fetch('/dashboard/signals').then(r=>r.ok?r.json():null).catch(()=>null),
      fetch('/dashboard/radar').then(r=>r.ok?r.json():null).catch(()=>null),
      fetch('/dashboard/signals-30m').then(r=>r.ok?r.json():null).catch(()=>null)
    ]);
    const d = r1 || {};
    /* === Store both data sources === */
    /* 30m: use dedicated 30m endpoint (real 30m data, brain-weighted, all 128 symbols) */
    liveSignals = (r30m && r30m.signals && r30m.signals.length > 0) ? r30m.signals : (d.all_signals || []);
    
    /* Build daily signals from radar_daily_context */
    const dailyCtx = r2 && r2.radar_daily_context && r2.radar_daily_context.length > 0 ? r2.radar_daily_context : [];
    dailySignals = dailyCtx.map(w=>{
      /* Merge: use live price if available, daily indicators otherwise */
      const liveMatch = liveSignals.find(s=>s.symbol===w.symbol);
      const price = liveMatch ? liveMatch.price : w.price;
      const change = liveMatch ? liveMatch.change_pct : w.change_pct;
      /* Map MACD cross to momentum label */
      let macdMom = null;
      if(w.macd_histogram!=null && w.macd!=null){
        if(w.macd_histogram>0 && w.macd>0) macdMom = 'accelerating_bullish';
        else if(w.macd_histogram>0 && w.macd<0) macdMom = 'decelerating_bearish';
        else if(w.macd_histogram<0 && w.macd<0) macdMom = 'accelerating_bearish';
        else if(w.macd_histogram<0 && w.macd>0) macdMom = 'decelerating_bullish';
      }
      return {
        symbol: w.symbol, name_ar: w.name_ar || '', price: price,
        change_pct: change,
        confluence_score: w.confluence ? w.confluence.score : (w.score || null),
        verdict: w.verdict || null, verdict_key: w.action || null,
        trade_state: w.trade_state || 'discovery',
        rsi_14: w.rsi || null,
        ema_state: (w.ema_cross && w.ema_cross !== 'unknown' && w.ema_cross !== 'none') ? w.ema_cross : (w.daily_ema_cross && w.daily_ema_cross !== 'none' ? w.daily_ema_cross : null),
        macd_momentum: macdMom || w.macd_cross || null,
        adx: w.adx || null,
        stoch_k: w.stoch_k || null,
        vol_ratio: w.vol_ratio || null,
        support: w.support || null, resistance: w.resistance || null,
        atr_14: w.atr || null,
        bb_squeeze: w.volume_spike ? true : null,
        rsi_divergence: w.rsi_divergence || null,
        ema_cross: (()=>{
          const ec = w.ema_cross || w.daily_ema_cross || null;
          if(!ec || ec==='none' || ec==='unknown') return null;
          const type = ec==='bullish'?'golden': ec==='bearish'?'death': null;
          if(!type) return null;
          const barsRaw = (w.signals||{}).ema_cross;
          const bars_ago = (barsRaw!=null && !isNaN(Number(barsRaw))) ? Number(barsRaw) : null;
          return {type, bars_ago};
        })(),
        timeframe: '1D', data_age_hours: w.data_age_hours || null,
        _from_daily: true, _price_is_live: !!liveMatch
      };
    });
    
    /* Set active tab data */
    if(activeTF==='30m'){
      allSignals = liveSignals;
    } else {
      allSignals = dailySignals;
    }
    d.all_signals = allSignals;
    
    /* Update tab badges */
    $('#tab-30m').textContent = '\u26A1 \u062D\u064A\u0629 (30m) [' + liveSignals.length + ']';
    $('#tab-1d').textContent = '\u{1F4C5} \u064A\u0648\u0645\u064A (1D) [' + dailySignals.length + ']';
    
    /* Update info line */
    if(activeTF==='30m'){
      const is30m = r30m && r30m.signals && r30m.signals.length > 0;
      $('#data-source-info').textContent = liveSignals.length ? '\u26A1 '+liveSignals.length+' \u0633\u0647\u0645 (30m '+(is30m?'\u0641\u0639\u0644\u064A':'fallback 1D')+') \u2014 Brain-weighted' : '\u0644\u0627 \u0628\u064A\u0627\u0646\u0627\u062A \u062D\u064A\u0629';
    } else {
      const age = dailySignals[0] && dailySignals[0].data_age_hours ? Math.round(dailySignals[0].data_age_hours)+'h' : '';
      $('#data-source-info').textContent = dailySignals.length ? '\u{1F4C5} '+dailySignals.length+' \u0633\u0647\u0645 (1D) \u2014 \u0639\u0645\u0631: '+age+' \u2014 Brain-weighted' : '\u0644\u0627 \u0628\u064A\u0627\u0646\u0627\u062A \u064A\u0648\u0645\u064A\u0629';
    }
    
    processData(d);
    /* Brain status badge */
    try{
      var brainSrc = activeTF==='30m' && r30m ? r30m : d;
      var dc = (activeTF==='30m' && r30m && r30m.signals && r30m.signals[0]) ? r30m.signals[0] : (d.decision_card||{});
      var cd = dc.confluence_detail||{};
      var brainBar = document.getElementById('brain-status-bar');
      var brainText = document.getElementById('brain-badge-text');
      if(cd.brain_weighted){
        var regime = cd.regime||'';
        var regimeAr = regime==='trending'?'\u0627\u062a\u062c\u0627\u0647\u064a':regime==='ranging'?'\u0639\u0631\u0636\u064a':regime==='transition'?'\u0627\u0646\u062a\u0642\u0627\u0644\u064a':'';
        var tfLabel = activeTF==='30m'?'30m':'1D';
        brainText.textContent='\u0623\u0648\u0632\u0627\u0646 \u0630\u0643\u064a\u0629 (Brain) \u2022 '+tfLabel+' \u2022 \u0646\u0638\u0627\u0645: '+regimeAr;
        brainBar.style.display='';
      }else{
        brainBar.style.display='none';
      }
    }catch(e){}
    showContent();
  }catch(e){
    console.error('Fetch error:',e);
    showError();
  }finally{
    btn.classList.remove('spinning');
    scheduleRefresh();
  }
}

function scheduleRefresh(){
  if(refreshTimer) clearTimeout(refreshTimer);
  refreshTimer = setTimeout(fetchData,120000);
}

function showContent(){
  $('#loading-state').style.display='none';
  $('#error-state').style.display='none';
  $('#data-content').style.display='block';
}
function showError(){
  $('#loading-state').style.display='none';
  $('#error-state').style.display='flex';
  $('#data-content').style.display='none';
}

/* ===== Process ===== */
function processData(d){
  /* Status chips */
  const mo = d.market_open;
  const bo = d.bridge_online;
  $('#dot-market').className = 'status-dot '+(mo?'on':'off');
  $('#lbl-market').textContent = mo?'\u0627\u0644\u0633\u0648\u0642 \u0645\u0641\u062A\u0648\u062D':'\u0627\u0644\u0633\u0648\u0642 \u0645\u063A\u0644\u0642';
  $('#dot-bridge').className = 'status-dot '+(bo?'on':'off');
  const bc = d.bridge_cached_count!=null ? ` (${d.bridge_cached_count})` : '';
  $('#lbl-bridge').textContent = (bo?'\u0627\u0644\u0631\u0628\u0637 \u0645\u062A\u0635\u0644':'\u0627\u0644\u0631\u0628\u0637 \u063A\u064A\u0631 \u0645\u062A\u0635\u0644') + bc;

  /* Signals */
  allSignals = d.all_signals || [];

  /* Signal counts */
  const sc = d.signal_counts || {};
  const total = allSignals.length;
  const avgConf = total > 0
    ? (allSignals.reduce((s,x)=>s+(x.confluence_score||0),0)/total).toFixed(1)
    : '--';

  /* Pulse bar */
  $('#p-total').textContent = total;
  $('#p-avg-conf').textContent = avgConf;
  $('#p-chips').innerHTML = [
    {k:'manage',l:'\u0625\u062F\u0627\u0631\u0629',c:'pc-manage',v:sc.manage||0},
    {k:'entered',l:'\u062F\u0627\u062E\u0644',c:'pc-entered',v:sc.entered||0},
    {k:'ready',l:'\u062C\u0627\u0647\u0632',c:'pc-ready',v:sc.ready||0},
    {k:'setup',l:'\u062A\u062D\u0636\u064A\u0631',c:'pc-setup',v:sc.setup||0},
    {k:'discovery',l:'\u0627\u0633\u062A\u0643\u0634\u0627\u0641',c:'pc-discovery',v:sc.discovery||0}
  ].map(x=>`<span class="pulse-chip ${x.c}">${x.l} <span class="ltr">${x.v}</span></span>`).join('');

  /* Bridge diagnostics */
  $('#bd-status').textContent = bo ? '\u0645\u062A\u0635\u0644' : '\u063A\u064A\u0631 \u0645\u062A\u0635\u0644';
  $('#bd-status').style.color = bo ? 'var(--green)' : 'var(--red)';
  $('#bd-cached').textContent = d.bridge_cached_count!=null ? d.bridge_cached_count : '--';
  const ts = d.timestamp ? new Date(d.timestamp).toLocaleString('ar-KW',{timeZone:'Asia/Kuwait'}) : new Date().toLocaleString('ar-KW',{timeZone:'Asia/Kuwait'});
  $('#bd-time').textContent = ts;
  $('#footer-time').textContent = '\u0622\u062E\u0631 \u062A\u062D\u062F\u064A\u062B: ' + ts;

  /* Render table */
  renderTable();
}

/* ===== Get Sorted & Filtered List ===== */
function getFilteredList(){
  let list = [...allSignals];
  /* Search filter */
  const q = ($('#f-search').value||'').trim().toLowerCase();
  if(q){
    list = list.filter(s =>
      (s.symbol||'').toLowerCase().includes(q) ||
      (s.name_ar||'').includes(q)
    );
  }
  /* State filter */
  const st = $('#f-state').value;
  if(st!=='all'){
    list = list.filter(s=>(s.trade_state||'').toLowerCase()===st);
  }
  /* Confluence min */
  const minConf = parseInt($('#f-conf').value)||0;
  if(minConf>0){
    list = list.filter(s=>(s.confluence_score||0)>=minConf);
  }
  /* Determine active sort */
  let activeSortCol = sortCol;
  let activeSortAsc = sortAsc;
  const colKeys = Object.keys(colSortState);
  if(colKeys.length>0){
    activeSortCol = colKeys[0];
    activeSortAsc = colSortState[colKeys[0]];
  }
  /* Sort */
  const sortMap = {
    confluence: s=>s.confluence_score||0,
    rsi: s=>s.rsi_14||0,
    adx: s=>s.adx||0,
    change: s=>s.change_pct||0,
    price: s=>s.price||0,
    stoch_k: s=>s.stoch_k||0,
    vol: s=>s.vol_ratio||0,
    atr: s=>s.atr_14||0,
    symbol: s=>(s.symbol||'').toLowerCase(),
  };
  const fn = sortMap[activeSortCol]||sortMap.confluence;
  list.sort((a,b)=>{
    const va = fn(a), vb = fn(b);
    if(va<vb) return activeSortAsc?-1:1;
    if(va>vb) return activeSortAsc?1:-1;
    return 0;
  });
  return list;
}

/* ===== Column Header Click Sort ===== */
function handleColSort(col){
  if(colSortState[col]!=null){
    colSortState[col] = !colSortState[col];
  } else {
    colSortState = {};
    colSortState[col] = false; /* default descending */
  }
  sortCol = col;
  sortAsc = colSortState[col];
  renderTable();
}

/* ===== Render Table ===== */
function renderTable(){
  const sec = $('#table-section');
  const list = getFilteredList();
  $('#results-count').textContent = list.length + ' \u0625\u0634\u0627\u0631\u0629';

  if(!list.length){
    sec.innerHTML = '<div class="empty-state">\u0644\u0627 \u062A\u0648\u062C\u062F \u0625\u0634\u0627\u0631\u0627\u062A \u0645\u0637\u0627\u0628\u0642\u0629</div>';
    return;
  }

  const cols = [
    {key:'symbol',label:'\u0627\u0644\u0633\u0647\u0645'},
    {key:'state',label:'\u0627\u0644\u062D\u0627\u0644\u0629'},
    {key:'price',label:'\u0627\u0644\u0633\u0639\u0631'},
    {key:'change',label:'%\u0627\u0644\u062A\u063A\u064A\u0631'},
    {key:'confluence',label:'Confluence',tip:'Confluence'},
    {key:'verdict',label:'\u0627\u0644\u0642\u0631\u0627\u0631'},
    {key:'ema',label:'EMA',tip:'EMA'},
    {key:'rsi',label:'RSI',tip:'RSI'},
    {key:'stoch_k',label:'StochK',tip:'Stoch'},
    {key:'momentum',label:'Momentum',tip:'MACD'},
    {key:'adx',label:'ADX',tip:'ADX'},
    {key:'regime',label:'\u0627\u0644\u0646\u0638\u0627\u0645',tip:'Regime'},
    {key:'vol',label:'Vol',tip:'Vol'},
    {key:'bb',label:'BB Sq',tip:'BB'},
    {key:'rsi_div',label:'RSI Div',tip:'RSI'},
    {key:'ema_cross',label:'EMA Cross',tip:'EMA'},
    {key:'support',label:'\u0627\u0644\u062F\u0639\u0645',tip:'S/R'},
    {key:'resistance',label:'\u0627\u0644\u0645\u0642\u0627\u0648\u0645\u0629',tip:'S/R'},
    {key:'atr',label:'ATR',tip:'ATR'}
  ];
  const sortable = ['symbol','price','change','confluence','rsi','stoch_k','adx','vol','atr'];

  let html = '<div class="table-wrap"><table><thead><tr>';
  cols.forEach(c=>{
    const isSortable = sortable.includes(c.key);
    const isSorted = sortCol===c.key;
    const arrow = isSorted ? (sortAsc ? '\u25B2' : '\u25BC') : '';
    const tipAttr = c.tip ? ` data-tip="${c.tip}"` : '';
    if(isSortable){
      html += `<th class="${isSorted?'sorted':''}" data-sort="${c.key}"${tipAttr}><span class="sort-arrow">${arrow}</span>${c.label}</th>`;
    } else {
      html += `<th${tipAttr}>${c.label}</th>`;
    }
  });
  html += '</tr></thead><tbody>';

  list.forEach(s=>{
    const dir = pctDir(s.change_pct);
    const cc = confColor(s.confluence_score);
    const tier = confTier(s.confluence_score);
    const ema = emaText(s.ema_state);
    const mom = momentumText(s.macd_momentum);
    const confW = s.confluence_score!=null ? Math.min(s.confluence_score,100) : 0;
    const rsiC = rsiColor(s.rsi_14);
    const adxBold = (s.adx||0)>25 ? 'font-weight:700' : '';
    const volBold = (s.vol_ratio||0)>1.5 ? 'font-weight:700;color:var(--gold)' : '';

    html += `<tr class="row-${tier}">`;
    /* Symbol — clickable for personality */
    html += `<td style="cursor:pointer" onclick="showPersonality('${s.symbol||''}')"><span class="cell-sym">${ltr(s.symbol||'')}</span><span class="cell-name">${s.name_ar||''}</span></td>`;
    /* State */
    html += `<td>${stateTag(s.trade_state)}</td>`;
    /* Price */
    html += `<td class="cell-mono">${ltr(fmtNum(s.price,3))}</td>`;
    /* Change */
    html += `<td class="cell-mono" style="color:var(--${dir==='up'?'green':dir==='dn'?'red':'text-3'})">${ltr(fmtPct(s.change_pct))}</td>`;
    /* Confluence */
    const bDelta = s.confluence_detail && s.confluence_detail.brain_delta ? s.confluence_detail.brain_delta : null;
    const deltaHtml = bDelta!==null && bDelta!==0 ? '<span style="font-size:.65rem;color:'+(bDelta>0?'var(--green)':'var(--red)')+'"> '+(bDelta>0?'+':'')+bDelta+'</span>' : '';
    html += `<td><div class="confluence-cell"><span class="cell-mono" style="color:${cc};font-weight:700">${ltr(s.confluence_score!=null?s.confluence_score:'\u2014')}</span>${deltaHtml}<div class="conf-bar"><div class="conf-fill" style="width:${confW}%;background:${cc}"></div></div></div></td>`;
    /* Verdict */
    html += `<td>${verdictPill(s.verdict_key, s.verdict)}</td>`;
    /* EMA */
    html += `<td style="color:${ema.c};font-size:.72rem">${ema.t}</td>`;
    /* RSI */
    html += `<td class="cell-mono" style="color:${rsiC}">${ltr(fmtNum(s.rsi_14,1))}</td>`;
    /* StochK */
    html += `<td class="cell-mono">${ltr(fmtNum(s.stoch_k,1))}</td>`;
    /* Momentum */
    html += `<td style="color:${mom.c};font-size:.72rem">${mom.t}</td>`;
    /* ADX */
    html += `<td class="cell-mono" style="${adxBold}">${ltr(fmtNum(s.adx,1))}</td>`;
    /* Regime */
    const adxV=s.adx||0;
    const regT=adxV>=25?'\u0627\u062A\u062C\u0627\u0647\u064A':adxV<=20?'\u0639\u0631\u0636\u064A':'\u0627\u0646\u062A\u0642\u0627\u0644\u064A';
    const regC=adxV>=25?'var(--green)':adxV<=20?'var(--red)':'var(--amber)';
    const regE=adxV>=25?'\u{1F7E2}':adxV<=20?'\u{1F534}':'\u{1F7E1}';
    html += `<td style="font-size:.72rem;color:${regC};white-space:nowrap">${regE} ${regT}</td>`;
    /* Vol */
    html += `<td class="cell-mono" style="${volBold}">${ltr(fmtNum(s.vol_ratio,2))}</td>`;
    /* BB Squeeze */
    html += `<td style="text-align:center">${bbSqueezeHtml(s.bb_squeeze)}</td>`;
    /* RSI Divergence */
    html += `<td style="text-align:center">${rsiDivHtml(s.rsi_divergence)}</td>`;
    /* EMA Cross */
    html += `<td>${emaCrossHtml(s.ema_cross)}</td>`;
    /* Support */
    html += `<td class="cell-mono">${ltr(fmtNum(s.support,3))}</td>`;
    /* Resistance */
    html += `<td class="cell-mono">${ltr(fmtNum(s.resistance,3))}</td>`;
    /* ATR */
    html += `<td class="cell-mono">${ltr(fmtNum(s.atr_14,3))}</td>`;
    html += '</tr>';
  });

  html += '</tbody></table></div>';
  sec.innerHTML = html;

  /* Attach column sort click handlers */
  sec.querySelectorAll('th[data-sort]').forEach(th=>{
    th.addEventListener('click',()=>handleColSort(th.dataset.sort));
  });
}

/* ===== Init ===== */
fetchData();

})();
</script>
<!-- PERSONALITY POPUP -->
<div id="personalityPopup" style="display:none;position:fixed;inset:0;z-index:500;background:rgba(7,13,23,.85);backdrop-filter:blur(8px);align-items:center;justify-content:center;padding:1rem" onclick="if(event.target===this)closePersonality()">
  <div style="background:var(--navy-800);border:1px solid var(--gold-br);border-radius:16px;max-width:680px;width:100%;max-height:85vh;overflow-y:auto;padding:1.25rem;position:relative">
    <button onclick="closePersonality()" style="position:absolute;top:.75rem;left:.75rem;background:none;border:none;color:var(--text-3);font-size:1.2rem;cursor:pointer">&times;</button>
    <div id="personalityContent" style="font-size:.85rem"></div>
    <div style="text-align:center;margin-top:1rem"><a id="personalityLink" href="#" style="font-size:.75rem;color:var(--gold)">&#1601;&#1578;&#1581; &#1575;&#1604;&#1589;&#1601;&#1581;&#1577; &#1575;&#1604;&#1603;&#1575;&#1605;&#1604;&#1577; &#8594;</a></div>
  </div>
</div>
<script>
function closePersonality(){document.getElementById('personalityPopup').style.display='none'}
async function showPersonality(sym){
  var popup=document.getElementById('personalityPopup');
  var content=document.getElementById('personalityContent');
  var link=document.getElementById('personalityLink');
  popup.style.display='flex';
  content.innerHTML='<div style="text-align:center;padding:2rem;color:var(--text-3)"><div class="spinner" style="margin:0 auto 1rem;width:30px;height:30px;border:2px solid var(--navy-600);border-top-color:var(--gold);border-radius:50%;animation:spin .8s linear infinite"></div>&#1580;&#1575;&#1585;&#1610; &#1575;&#1604;&#1578;&#1581;&#1605;&#1610;&#1604;...</div>';
  link.href='personality?symbol='+sym;
  try{
    var r=await fetch('/api/stocks/symbol/'+sym);
    if(!r.ok)throw new Error(r.status);
    var d=await r.json();var p=d.profile||{};var pats=d.top_patterns||[];var notes=d.notes||'';
    var h='<div style="text-align:center;margin-bottom:1rem">';
    h+='<div style="font-family:var(--fm);font-size:1.3rem;font-weight:700;color:var(--gold)">'+sym+'</div>';
    h+='<div style="font-size:.8rem;color:var(--text-2);margin-top:.25rem">'+(p.personality_ar||'')+'</div>';
    h+='<div style="margin-top:.5rem;display:flex;justify-content:center;gap:1.5rem">';
    h+='<span style="font-family:var(--fm);color:var(--green);font-weight:700">'+((p.baseline_win_rate||0)*100).toFixed(1)+'% &#1606;&#1580;&#1575;&#1581;</span>';
    h+='<span style="font-family:var(--fm);color:var(--cyan)">'+((p.reward_risk_ratio||0)).toFixed(1)+'x R/R</span>';
    h+='<span style="font-family:var(--fm);color:var(--amber)">'+(p.signals_count||0)+' &#1573;&#1588;&#1575;&#1585;&#1577;</span>';
    h+='</div></div>';
    h+='<div style="font-size:.75rem;color:var(--text-3);margin-bottom:.5rem">&#1571;&#1602;&#1608;&#1609; &#1605;&#1572;&#1588;&#1585;: <span style="color:var(--cyan);font-weight:700">'+(p.dominant_driver||'-')+'</span></div>';
    if(pats.length>0){
      h+='<div style="font-size:.78rem;font-weight:600;color:var(--gold);margin:.75rem 0 .4rem">\u{1F3C6} &#1571;&#1601;&#1590;&#1604; 3 &#1571;&#1606;&#1605;&#1575;&#1591;:</div>';
      pats.slice(0,3).forEach(function(pt,i){
        var wc=pt.win_rate>=0.6?'var(--green)':pt.win_rate>=0.4?'var(--amber)':'var(--red)';
        h+='<div style="background:var(--navy-900);border-radius:8px;padding:.5rem .75rem;margin-bottom:.4rem;font-size:.78rem">';
        h+='<span style="color:var(--cyan)">'+pt.pattern_ar+'</span>';
        h+=' <span style="font-family:var(--fm);color:'+wc+';font-weight:600">'+pt.hits+'/'+pt.occurrences+' ('+(pt.win_rate*100).toFixed(0)+'%)</span>';
        h+=' <span style="font-family:var(--fm);color:var(--green);font-size:.72rem">+'+((pt.avg_gain_pct||0)).toFixed(1)+'%</span>';
        h+='</div>';
      });
    }
    if(notes){
      var lines=notes.split('|').slice(0,5).map(function(l){return l.trim()}).filter(function(l){return l});
      h+='<div style="margin-top:.75rem;font-size:.75rem;color:var(--text-2);line-height:1.9;border-top:1px solid var(--card-border);padding-top:.75rem">';
      lines.forEach(function(l){h+='<div>'+l+'</div>'});
      h+='</div>';
    }
    content.innerHTML=h;
  }catch(e){content.innerHTML='<div style="color:var(--red);text-align:center;padding:2rem">&#1582;&#1591;&#1571;: '+e.message+'</div>'}
}
window.showPersonality=showPersonality;
</script>
<script src="indicator-tooltips.js"></script>
</body>
</html>

```


############################################################
# FILE: www/trading/positions.html (1087 lines)
############################################################

```html
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>إدارة المراكز — KSE</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Noto+Kufi+Arabic:wght@400;500;600;700&family=Tajawal:wght@400;500;700;800&display=swap" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/@mdi/font@7/css/materialdesignicons.min.css" rel="stylesheet">
<style>
:root{
  --navy-900:#070D17;--navy-800:#0C1525;--navy-700:#111E32;
  --navy-600:#162840;--navy-500:#1C334F;--navy-400:#24405F;
  --gold:#C6974B;--gold-bright:#D4A95C;--gold-dim:#9E7A3D;
  --gold-bg:rgba(198,151,75,.06);--gold-br:rgba(198,151,75,.25);
  --green:#4CAF82;--green-bright:#5BC492;--green-bg:rgba(76,175,130,.08);--green-br:rgba(76,175,130,.3);
  --red:#D94452;--red-bright:#E5606C;--red-bg:rgba(217,68,82,.08);--red-br:rgba(217,68,82,.3);
  --amber:#E8A838;--amber-bg:rgba(232,168,56,.08);--amber-br:rgba(232,168,56,.3);
  --cyan:#38BDF8;--cyan-bg:rgba(56,189,248,.08);--cyan-br:rgba(56,189,248,.3);
  --text:#E8ECF0;--text-2:#A0ADBC;--text-3:#6B7D90;--text-4:#405060;
  --card:#0E1929;--card-hover:#132137;--card-border:#1A2E45;
  --f:'Tajawal','Noto Kufi Arabic',sans-serif;
  --fd:'Noto Kufi Arabic','Tajawal',sans-serif;
  --fm:'IBM Plex Mono','Consolas',monospace;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{
  font-family:var(--f);font-variant-numeric:tabular-nums;
  background:var(--navy-900);color:var(--text);
  min-height:100vh;line-height:1.6;-webkit-font-smoothing:antialiased;
}
.ltr{direction:ltr;unicode-bidi:isolate}
a{color:var(--gold);text-decoration:none}
a:hover{color:var(--gold-bright)}

/* ===== TOPBAR ===== */
.topbar{
  position:sticky;top:0;z-index:100;
  background:rgba(7,13,23,.92);backdrop-filter:blur(16px);
  border-bottom:1px solid var(--card-border);
  padding:0 1.25rem;height:56px;
  display:flex;align-items:center;justify-content:space-between;gap:.75rem;
}
.topbar-brand{display:flex;align-items:center;gap:.75rem;flex-shrink:0}
.brand-mark{
  background:linear-gradient(135deg,var(--gold),var(--gold-dim));
  color:var(--navy-900);font-family:var(--fm);font-weight:700;
  font-size:.85rem;padding:.25rem .6rem;border-radius:4px;letter-spacing:.5px;
}
.topbar-title{font-family:var(--fd);font-weight:700;font-size:1rem;color:var(--text)}
.topbar-tag{
  font-size:.65rem;background:var(--navy-600);color:var(--text-3);
  padding:2px 8px;border-radius:10px;white-space:nowrap;
}
.topbar-center{display:flex;align-items:center;gap:.5rem;flex-shrink:0}
.topbar-right{display:flex;align-items:center;gap:.75rem;flex-shrink:0}
.clock{font-family:var(--fm);font-size:.85rem;color:var(--gold);direction:ltr;unicode-bidi:isolate;white-space:nowrap}
.btn-refresh{
  background:none;border:1px solid var(--card-border);color:var(--text-2);
  width:34px;height:34px;border-radius:8px;cursor:pointer;
  display:flex;align-items:center;justify-content:center;transition:all .2s;
}
.btn-refresh:hover{border-color:var(--gold-br);color:var(--gold)}
.btn-refresh.spinning svg{animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes stopFlash{0%,100%{opacity:1}50%{opacity:.6}}
.nav-links{display:flex;gap:.15rem}
.nav-link{
  font-size:.75rem;padding:.3rem .6rem;border-radius:6px;color:var(--text-3);transition:all .2s;
}
.nav-link:hover{color:var(--text);background:var(--navy-700)}
.nav-link.active{color:var(--gold);background:var(--gold-bg);border:1px solid var(--gold-br)}

/* ===== MAIN CONTENT ===== */
.main{padding:1.25rem;max-width:1400px;margin:0 auto}

/* ===== SECTION TITLE ===== */
.section-title{
  font-family:var(--fd);font-weight:700;font-size:1.05rem;color:var(--text);
  margin-bottom:1rem;display:flex;align-items:center;gap:.5rem;
}
.section-title .mdi{font-size:1.2rem;color:var(--gold)}

/* ===== PORTFOLIO PULSE BAR — 4 stat cards ===== */
.pulse-grid{
  display:grid;grid-template-columns:repeat(4,1fr);gap:.75rem;margin-bottom:1.5rem;
}
.pulse-card{
  background:var(--navy-800);border:1px solid var(--card-border);border-radius:10px;
  padding:1rem 1.1rem;display:flex;align-items:center;gap:.85rem;transition:background .2s;
}
.pulse-card:hover{background:var(--navy-700)}
.pulse-icon{
  width:44px;height:44px;border-radius:10px;display:flex;align-items:center;justify-content:center;
  font-size:1.3rem;flex-shrink:0;
}
.pulse-icon.gold{background:var(--gold-bg);color:var(--gold);border:1px solid var(--gold-br)}
.pulse-icon.green{background:var(--green-bg);color:var(--green);border:1px solid var(--green-br)}
.pulse-icon.red{background:var(--red-bg);color:var(--red);border:1px solid var(--red-br)}
.pulse-icon.amber{background:var(--amber-bg);color:var(--amber);border:1px solid var(--amber-br)}
.pulse-icon.cyan{background:var(--cyan-bg);color:var(--cyan);border:1px solid var(--cyan-br)}
.pulse-info{display:flex;flex-direction:column;gap:.1rem;min-width:0}
.pulse-val{font-family:var(--fm);font-size:1.8rem;font-weight:700;color:var(--text);line-height:1.1}
.pulse-label{font-size:.72rem;color:var(--text-3);white-space:nowrap}

/* ===== POSITION CARDS ===== */
.positions-list{display:flex;flex-direction:column;gap:.75rem;margin-bottom:1.75rem}
.pos-card{
  background:var(--card);border:1px solid var(--card-border);border-radius:12px;
  border-right:4px solid var(--card-border);padding:1.1rem 1.25rem;
  transition:background .2s;
}
.pos-card:hover{background:var(--card-hover)}
.pos-card.profit{border-right-color:var(--green)}
.pos-card.loss{border-right-color:var(--red)}
.pos-card.danger-border{border:1px solid var(--red);border-right:4px solid var(--red)}

.pos-header{
  display:flex;align-items:center;gap:.75rem;margin-bottom:.85rem;flex-wrap:wrap;
}
.pos-symbol{font-family:var(--fm);font-size:1.25rem;font-weight:700;color:var(--text)}
.pos-name{font-size:.85rem;color:var(--text-2)}
.pos-dir{
  font-size:.65rem;font-weight:600;padding:.2rem .55rem;border-radius:6px;
  text-transform:uppercase;letter-spacing:.5px;
}
.pos-dir.long{background:var(--green-bg);color:var(--green);border:1px solid var(--green-br)}
.pos-dir.short{background:var(--red-bg);color:var(--red);border:1px solid var(--red-br)}
.pos-status{
  font-size:.6rem;padding:.15rem .45rem;border-radius:4px;margin-right:auto;
  background:var(--navy-700);color:var(--text-3);border:1px solid var(--card-border);
}

.pos-metrics{
  display:grid;grid-template-columns:repeat(6,1fr);gap:.6rem .75rem;margin-bottom:.85rem;
}
.pos-metric{display:flex;flex-direction:column;gap:.15rem}
.pos-metric-label{
  font-size:.58rem;text-transform:uppercase;letter-spacing:.8px;color:var(--text-3);
}
.pos-metric-val{font-family:var(--fm);font-size:1rem;font-weight:600;color:var(--text)}
.pos-metric-val.big{font-size:1.3rem;font-weight:700}
.pos-metric-val.green{color:var(--green)}
.pos-metric-val.red{color:var(--red)}

.pos-reason{
  font-size:.78rem;color:var(--text-2);padding:.6rem .75rem;
  background:var(--navy-800);border-radius:8px;border:1px solid var(--card-border);
  line-height:1.5;
}
.pos-reason-label{font-size:.6rem;color:var(--text-3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:.25rem}

/* ===== CLOSED TRADES ===== */
.closed-card{
  background:var(--card);border:1px solid var(--card-border);border-radius:12px;
  border-right:4px solid var(--card-border);padding:.85rem 1.1rem;
  transition:background .2s;opacity:.85;
}
.closed-card:hover{background:var(--card-hover);opacity:1}
.closed-card.profit{border-right-color:var(--green)}
.closed-card.loss{border-right-color:var(--red)}
.closed-header{display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;margin-bottom:.6rem}
.closed-metrics{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:.5rem .65rem}

/* ===== SIGNAL VS TRADE ===== */
.signal-grid{
  display:grid;grid-template-columns:repeat(3,1fr);gap:.75rem;margin-bottom:1.75rem;
}

/* ===== STATS COMPARISON ===== */
.stats-compare{
  display:grid;grid-template-columns:repeat(2,1fr);gap:1rem;margin-bottom:1.75rem;
}
.stats-panel{
  background:var(--card);border:1px solid var(--card-border);border-radius:12px;
  padding:1.1rem 1.25rem;
}
.stats-panel-title{
  font-family:var(--fd);font-weight:700;font-size:.9rem;color:var(--gold);
  margin-bottom:.85rem;display:flex;align-items:center;gap:.4rem;
}
.stats-rows{display:flex;flex-direction:column;gap:.45rem}
.stats-row{
  display:flex;justify-content:space-between;align-items:center;
  padding:.35rem 0;border-bottom:1px solid rgba(26,46,69,.4);
}
.stats-row:last-child{border-bottom:none}
.stats-row-label{font-size:.78rem;color:var(--text-2)}
.stats-row-val{font-family:var(--fm);font-size:.9rem;font-weight:600;color:var(--text)}

/* ===== EMPTY / LOADING / ERROR ===== */
.loading-wrap{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  padding:4rem 1rem;gap:1rem;
}
.spinner{
  width:40px;height:40px;border:3px solid var(--card-border);
  border-top-color:var(--gold);border-radius:50%;animation:spin .8s linear infinite;
}
.loading-text{font-size:.85rem;color:var(--text-3)}
.error-wrap{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  padding:3rem 1rem;gap:.75rem;
}
.error-icon{font-size:2.5rem;color:var(--red)}
.error-msg{font-size:.85rem;color:var(--text-2);text-align:center}
.btn-retry{
  font-family:var(--f);font-size:.8rem;padding:.45rem 1.2rem;border-radius:8px;
  background:var(--gold-bg);color:var(--gold);border:1px solid var(--gold-br);
  cursor:pointer;transition:all .2s;
}
.btn-retry:hover{background:var(--gold);color:var(--navy-900)}

.empty-state{
  text-align:center;padding:3rem 1rem;color:var(--text-3);font-size:.9rem;
}
.empty-state .mdi{font-size:2.5rem;display:block;margin-bottom:.5rem;color:var(--text-4)}

/* ===== FOOTER ===== */
.footer{
  text-align:center;padding:1.5rem 1rem;color:var(--text-4);font-size:.7rem;
  border-top:1px solid var(--card-border);margin-top:1rem;
}
.footer-ts{font-family:var(--fm);color:var(--text-3);margin-top:.25rem}

/* ===== ADD TRADE BUTTON ===== */
.btn-add-trade{
  background:var(--gold);color:var(--navy-900);font-family:var(--f);
  font-weight:700;font-size:.88rem;border:none;border-radius:8px;
  padding:10px 24px;cursor:pointer;transition:all .2s;
  display:inline-flex;align-items:center;gap:.4rem;
}
.btn-add-trade:hover{background:var(--gold-bright);transform:translateY(-1px)}
.btn-add-trade:active{transform:translateY(0)}
.action-bar{display:flex;align-items:center;gap:.75rem;margin-bottom:1.25rem}

/* ===== MODAL ===== */
.modal-overlay{
  position:fixed;inset:0;background:rgba(0,0,0,0.7);
  display:flex;align-items:center;justify-content:center;
  z-index:1000;opacity:0;visibility:hidden;transition:all .25s;
}
.modal-overlay.open{opacity:1;visibility:visible}
.modal{
  background:var(--navy-800);border:1px solid var(--gold-br);
  border-radius:14px;padding:24px;max-width:500px;width:90%;
  direction:rtl;transform:scale(.95);transition:transform .25s;
}
.modal-overlay.open .modal{transform:scale(1)}
.modal h3{color:var(--gold);font-family:var(--fd);margin-bottom:16px;font-size:1.05rem}

/* ===== FORM INPUTS ===== */
.form-group{margin-bottom:14px}
.form-group label{
  font-size:.72rem;color:var(--text-3);font-weight:600;
  margin-bottom:4px;display:block;
}
.form-group input,
.form-group select,
.form-group textarea{
  background:var(--navy-700);border:1px solid var(--card-border);
  color:var(--text);padding:10px 14px;border-radius:8px;
  font-family:var(--f);font-size:.85rem;width:100%;direction:rtl;
}
.form-group input:focus,
.form-group textarea:focus{
  border-color:var(--gold);outline:none;
  box-shadow:0 0 0 2px rgba(198,151,75,0.2);
}
.form-group textarea{resize:vertical;min-height:60px}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.form-actions{display:flex;gap:10px;margin-top:18px;justify-content:flex-start}
.btn-modal-primary{
  background:var(--gold);color:var(--navy-900);font-family:var(--f);
  font-weight:700;font-size:.82rem;border:none;border-radius:8px;
  padding:10px 24px;cursor:pointer;transition:all .2s;
}
.btn-modal-primary:hover{background:var(--gold-bright)}
.btn-modal-primary:disabled{opacity:.5;cursor:not-allowed}
.btn-modal-danger{
  background:var(--red);color:#fff;font-family:var(--f);
  font-weight:700;font-size:.82rem;border:none;border-radius:8px;
  padding:10px 24px;cursor:pointer;transition:all .2s;
}
.btn-modal-danger:hover{background:var(--red-bright)}
.btn-modal-danger:disabled{opacity:.5;cursor:not-allowed}
.btn-modal-cancel{
  background:var(--navy-700);color:var(--text-2);font-family:var(--f);
  font-weight:600;font-size:.82rem;border:1px solid var(--card-border);
  border-radius:8px;padding:10px 20px;cursor:pointer;transition:all .2s;
}
.btn-modal-cancel:hover{background:var(--navy-600);color:var(--text)}
.form-msg{
  font-size:.78rem;padding:8px 12px;border-radius:8px;margin-top:10px;
  display:none;
}
.form-msg.success{display:block;background:var(--green-bg);color:var(--green);border:1px solid var(--green-br)}
.form-msg.error{display:block;background:var(--red-bg);color:var(--red);border:1px solid var(--red-br)}

/* ===== POSITION ACTION BUTTONS ===== */
.pos-actions{
  display:flex;gap:8px;margin-top:.75rem;padding-top:.65rem;
  border-top:1px solid var(--card-border);
}
.btn-pos-close{
  font-family:var(--f);font-size:.72rem;font-weight:600;padding:6px 16px;
  border-radius:6px;cursor:pointer;transition:all .2s;border:none;
  background:var(--red-bg);color:var(--red);border:1px solid var(--red-br);
}
.btn-pos-close:hover{background:var(--red);color:#fff}
.btn-pos-edit{
  font-family:var(--f);font-size:.72rem;font-weight:600;padding:6px 16px;
  border-radius:6px;cursor:pointer;transition:all .2s;border:none;
  background:var(--amber-bg);color:var(--amber);border:1px solid var(--amber-br);
}
.btn-pos-edit:hover{background:var(--amber);color:var(--navy-900)}

/* ===== INLINE EDIT ===== */
.inline-edit{
  display:none;margin-top:.65rem;padding:.75rem;
  background:var(--navy-800);border-radius:8px;border:1px solid var(--card-border);
}
.inline-edit.open{display:block}
.inline-edit-row{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap}
.inline-edit-field{display:flex;flex-direction:column;gap:3px;flex:1;min-width:120px}
.inline-edit-field label{font-size:.65rem;color:var(--text-3);font-weight:600}
.inline-edit-field input{
  background:var(--navy-700);border:1px solid var(--card-border);
  color:var(--text);padding:7px 10px;border-radius:6px;
  font-family:var(--fm);font-size:.82rem;width:100%;direction:ltr;
}
.inline-edit-field input:focus{border-color:var(--gold);outline:none;box-shadow:0 0 0 2px rgba(198,151,75,0.2)}
.btn-inline-save{
  font-family:var(--f);font-size:.72rem;font-weight:600;padding:7px 16px;
  border-radius:6px;cursor:pointer;background:var(--gold);color:var(--navy-900);
  border:none;transition:all .2s;white-space:nowrap;
}
.btn-inline-save:hover{background:var(--gold-bright)}
.btn-inline-cancel{
  font-family:var(--f);font-size:.72rem;font-weight:600;padding:7px 14px;
  border-radius:6px;cursor:pointer;background:var(--navy-700);color:var(--text-2);
  border:1px solid var(--card-border);transition:all .2s;white-space:nowrap;
}
.btn-inline-cancel:hover{background:var(--navy-600)}
.inline-msg{font-size:.7rem;margin-top:6px;color:var(--green)}

/* ===== ALERT BADGES ===== */
.alert-badges{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:.6rem}
.alert-badge{
  font-size:.65rem;font-weight:600;padding:3px 10px;border-radius:6px;
  display:inline-flex;align-items:center;gap:4px;
}
.alert-badge.danger{background:var(--red-bg);color:var(--red);border:1px solid var(--red-br)}
.alert-badge.warning{background:var(--amber-bg);color:var(--amber);border:1px solid var(--amber-br)}
.alert-badge .mdi{font-size:.8rem}

/* ===== SIGNAL HEALTH STRIP ===== */
.signal-health-strip{
  display:flex;gap:.75rem;flex-wrap:wrap;margin-top:.65rem;padding:.6rem .75rem;
  background:var(--navy-800);border-radius:8px;border:1px solid var(--card-border);
}
.sh-item{display:flex;flex-direction:column;gap:2px;min-width:80px}
.sh-item-label{font-size:.55rem;color:var(--text-3);text-transform:uppercase;letter-spacing:.5px}
.sh-item-val{font-family:var(--fm);font-size:.85rem;font-weight:600}

/* ===== SL/TP DISPLAY ===== */
.sl-tp-row{
  display:flex;gap:1rem;flex-wrap:wrap;margin-top:.5rem;
}
.sl-tp-item{
  display:flex;align-items:center;gap:6px;font-size:.78rem;
}
.sl-tp-label{font-size:.6rem;font-weight:600;text-transform:uppercase;letter-spacing:.5px}
.sl-tp-val{font-family:var(--fm);font-weight:600}
.sl-tp-pct{font-size:.68rem;font-family:var(--fm);opacity:.7}

/* ===== RESPONSIVE ===== */
@media(max-width:1024px){
  .pulse-grid{grid-template-columns:repeat(2,1fr)}
  .pos-metrics{grid-template-columns:repeat(3,1fr)}
  .stats-compare{grid-template-columns:1fr}
}
@media(max-width:768px){
  .topbar-tag,.nav-links{display:none}
  .main{padding:.85rem}
  .pulse-grid{grid-template-columns:repeat(2,1fr);gap:.5rem}
  .pulse-card{padding:.75rem .85rem}
  .pulse-val{font-size:1.4rem}
  .pulse-icon{width:38px;height:38px;font-size:1.1rem}
  .signal-grid{grid-template-columns:1fr}
  .pos-metrics{grid-template-columns:repeat(2,1fr)}
  .pos-card{padding:.85rem 1rem}
  .closed-metrics{grid-template-columns:repeat(2,1fr)}
  .form-row{grid-template-columns:1fr}
}
@media(max-width:480px){
  .pulse-grid{grid-template-columns:1fr}
  .pos-metrics{grid-template-columns:repeat(2,1fr)}
  .topbar{padding:0 .75rem;height:48px}
  .brand-mark{font-size:.75rem;padding:.2rem .45rem}
  .topbar-title{font-size:.85rem}
  .clock{font-size:.75rem}
  .modal{padding:18px;width:95%}
}
</style>
<link rel="stylesheet" href="indicator-tooltips.css">
</head>
<body>

<!-- ===== TOPBAR ===== -->
<header class="topbar">
  <div class="topbar-brand">
    <span class="brand-mark">KSE</span>
    <span class="topbar-title">إدارة المراكز</span>
    <span class="topbar-tag">Master AI</span>
  </div>
  <div class="topbar-center">
    <nav class="nav-links">
      <a href="decisions" class="nav-link">القرارات</a>
      <a href="positions" class="nav-link active">المراكز</a>
      <a href="radar" class="nav-link">الرادار</a>
      <a href="journal" class="nav-link">السجل</a>
      <a href="strategies" class="nav-link">الاستراتيجيات</a>
      <a href="brain" class="nav-link">العقل</a>
      <a href="system" class="nav-link">النظام</a>
    </nav>
  </div>
  <div class="topbar-right">
    <span class="clock ltr" id="clock">--:--:--</span>
    <button class="btn-refresh" id="btnRefresh" title="تحديث">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>
    </button>
  </div>
</header>

<!-- ===== ADD TRADE MODAL ===== -->
<div class="modal-overlay" id="addTradeOverlay">
  <div class="modal">
    <h3><span class="mdi mdi-plus-circle-outline"></span> إضافة صفقة جديدة</h3>
    <form id="addTradeForm" autocomplete="off">
      <div class="form-group">
        <label for="at_symbol">الرمز</label>
        <input type="text" id="at_symbol" name="symbol" list="symbolsList" required placeholder="اختر أو اكتب الرمز...">
        <datalist id="symbolsList"></datalist>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label for="at_entry">سعر الدخول</label>
          <input type="number" id="at_entry" name="entry_price" step="any" required placeholder="0.000">
        </div>
        <div class="form-group">
          <label for="at_qty">الكمية</label>
          <input type="number" id="at_qty" name="quantity" min="1" required placeholder="0">
        </div>
      </div>
      <div class="form-group">
        <label for="at_strategy">الاستراتيجية</label>
        <input type="text" id="at_strategy" name="strategy" value="manual" placeholder="manual">
      </div>
      <div class="form-row">
        <div class="form-group">
          <label for="at_sl">وقف الخسارة</label>
          <input type="number" id="at_sl" name="stop_loss" step="any" placeholder="اختياري">
        </div>
        <div class="form-group">
          <label for="at_tp">جني الأرباح</label>
          <input type="number" id="at_tp" name="take_profit" step="any" placeholder="اختياري">
        </div>
      </div>
      <div class="form-group">
        <label for="at_notes">ملاحظات</label>
        <textarea id="at_notes" name="notes" rows="2" placeholder="ملاحظات اختيارية..."></textarea>
      </div>
      <div class="form-actions">
        <button type="submit" class="btn-modal-primary" id="at_submit">حفظ</button>
        <button type="button" class="btn-modal-cancel" onclick="closeAddTrade()">إلغاء</button>
      </div>
      <div class="form-msg" id="at_msg"></div>
    </form>
  </div>
</div>

<!-- ===== CLOSE TRADE MODAL ===== -->
<div class="modal-overlay" id="closeTradeOverlay">
  <div class="modal">
    <h3><span class="mdi mdi-close-circle-outline"></span> إغلاق الصفقة</h3>
    <form id="closeTradeForm" autocomplete="off">
      <input type="hidden" id="ct_trade_id" name="trade_id">
      <div class="form-group">
        <label>الرمز</label>
        <div id="ct_symbol_display" style="font-family:var(--fm);font-size:1rem;color:var(--gold);font-weight:700;margin-bottom:4px"></div>
      </div>
      <div class="form-group">
        <label for="ct_exit">سعر الخروج</label>
        <input type="number" id="ct_exit" name="exit_price" step="any" required placeholder="0.000">
      </div>
      <div class="form-group">
        <label for="ct_reason">السبب</label>
        <input type="text" id="ct_reason" name="reason" placeholder="سبب الإغلاق...">
      </div>
      <div class="form-actions">
        <button type="submit" class="btn-modal-danger" id="ct_submit">إغلاق الصفقة</button>
        <button type="button" class="btn-modal-cancel" onclick="closeCloseModal()">إلغاء</button>
      </div>
      <div class="form-msg" id="ct_msg"></div>
    </form>
  </div>
</div>

<!-- ===== MAIN ===== -->
<main class="main" id="app">
  <div class="loading-wrap" id="loading">
    <div class="spinner"></div>
    <div class="loading-text">جارٍ تحميل المحفظة...</div>
  </div>
  <div class="error-wrap" id="errorState" style="display:none">
    <div class="error-icon"><span class="mdi mdi-alert-circle-outline"></span></div>
    <div class="error-msg" id="errorMsg">تعذّر تحميل البيانات</div>
    <button class="btn-retry" onclick="loadData()">إعادة المحاولة</button>
  </div>
  <div id="content" style="display:none"></div>
</main>

<script>
(function(){
'use strict';

const API_URL = '/dashboard/portfolio';
const REFRESH_MS = 120000;
let refreshTimer = null;
let _lastData = null;

/* ===== Auth ===== */
function getApiKey(){
  const p = new URLSearchParams(window.location.search);
  return p.get('key') || '';
}
function authHeaders(){
  const k = getApiKey();
  return {'X-API-Key':k, 'Authorization':'Bearer '+k, 'Accept':'application/json'};
}

/* ===== Clock ===== */
function tickClock(){
  const d = new Date();
  document.getElementById('clock').textContent =
    d.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
}
setInterval(tickClock,1000);
tickClock();

/* ===== Helpers ===== */
function n(v,dec){
  if(v==null) return '\u2014';
  const num = Number(v);
  if(isNaN(num)) return '\u2014';
  return num.toLocaleString('en-US',{minimumFractionDigits:dec||0,maximumFractionDigits:dec||0});
}
function n3(v){return n(v,3)}
function pct(v){
  if(v==null) return '\u2014';
  return Number(v).toFixed(2)+'%';
}
function pnlClass(v){return Number(v)>=0?'green':'red'}
function pnlSign(v){return Number(v)>=0?'+':''}
function daysHeld(dateStr){
  if(!dateStr) return '\u2014';
  const d = new Date(dateStr);
  const now = new Date();
  return Math.max(0,Math.floor((now-d)/(86400000)));
}
function esc(s){
  if(!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

/* ===== Symbols datalist ===== */
(async function loadSymbols(){
  try{
    const r = await fetch('/api/symbols');
    if(!r.ok) return;
    const d = await r.json();
    const dl = document.getElementById('symbolsList');
    (d.symbols||[]).forEach(s=>{
      const opt = document.createElement('option');
      opt.value = s.symbol;
      opt.textContent = s.name_ar||s.symbol;
      dl.appendChild(opt);
    });
  }catch(e){console.warn('Could not load symbols:', e)}
})();

/* ===== Modal Helpers ===== */
function openAddTrade(){
  document.getElementById('addTradeForm').reset();
  document.getElementById('at_strategy').value = 'manual';
  hideMsg('at_msg');
  document.getElementById('addTradeOverlay').classList.add('open');
}
function closeAddTrade(){
  document.getElementById('addTradeOverlay').classList.remove('open');
}
function openCloseModal(tradeId, symbol, currentPrice){
  document.getElementById('ct_trade_id').value = tradeId;
  document.getElementById('ct_symbol_display').textContent = symbol;
  document.getElementById('ct_exit').value = currentPrice || '';
  document.getElementById('ct_reason').value = '';
  hideMsg('ct_msg');
  document.getElementById('closeTradeOverlay').classList.add('open');
}
function closeCloseModal(){
  document.getElementById('closeTradeOverlay').classList.remove('open');
}
function showMsg(id, text, type){
  const el = document.getElementById(id);
  el.textContent = text;
  el.className = 'form-msg '+type;
}
function hideMsg(id){
  const el = document.getElementById(id);
  el.textContent = '';
  el.className = 'form-msg';
}

/* Close modals on overlay click */
document.getElementById('addTradeOverlay').addEventListener('click', function(e){
  if(e.target===this) closeAddTrade();
});
document.getElementById('closeTradeOverlay').addEventListener('click', function(e){
  if(e.target===this) closeCloseModal();
});

/* ===== Add Trade Submit ===== */
document.getElementById('addTradeForm').addEventListener('submit', async function(e){
  e.preventDefault();
  const btn = document.getElementById('at_submit');
  btn.disabled = true;
  hideMsg('at_msg');
  try{
    const body = {
      symbol: document.getElementById('at_symbol').value.trim(),
      entry_price: parseFloat(document.getElementById('at_entry').value),
      quantity: parseInt(document.getElementById('at_qty').value),
      strategy: document.getElementById('at_strategy').value.trim() || 'manual'
    };
    const sl = document.getElementById('at_sl').value;
    const tp = document.getElementById('at_tp').value;
    const notes = document.getElementById('at_notes').value.trim();
    if(sl) body.stop_loss = parseFloat(sl);
    if(tp) body.take_profit = parseFloat(tp);
    if(notes) body.notes = notes;

    const res = await fetch('/api/trade/open', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if(!res.ok) throw new Error(data.error || data.message || 'HTTP '+res.status);
    showMsg('at_msg', 'تم فتح الصفقة بنجاح', 'success');
    setTimeout(()=>{
      closeAddTrade();
      loadData();
    }, 800);
  }catch(err){
    showMsg('at_msg', 'خطأ: '+err.message, 'error');
  }finally{
    btn.disabled = false;
  }
});

/* ===== Close Trade Submit ===== */
document.getElementById('closeTradeForm').addEventListener('submit', async function(e){
  e.preventDefault();
  const btn = document.getElementById('ct_submit');
  btn.disabled = true;
  hideMsg('ct_msg');
  try{
    const body = {
      trade_id: document.getElementById('ct_trade_id').value,
      exit_price: parseFloat(document.getElementById('ct_exit').value),
      reason: document.getElementById('ct_reason').value.trim()
    };
    const res = await fetch('/api/trade/close', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if(!res.ok) throw new Error(data.error || data.message || 'HTTP '+res.status);
    showMsg('ct_msg', 'تم إغلاق الصفقة بنجاح', 'success');
    setTimeout(()=>{
      closeCloseModal();
      loadData();
    }, 800);
  }catch(err){
    showMsg('ct_msg', 'خطأ: '+err.message, 'error');
  }finally{
    btn.disabled = false;
  }
});

/* ===== Inline Edit SL/TP ===== */
function toggleInlineEdit(tradeId){
  const el = document.getElementById('ie_'+tradeId);
  if(!el) return;
  el.classList.toggle('open');
}
async function saveInlineEdit(tradeId){
  const slEl = document.getElementById('ie_sl_'+tradeId);
  const tpEl = document.getElementById('ie_tp_'+tradeId);
  const msgEl = document.getElementById('ie_msg_'+tradeId);
  if(!slEl||!tpEl) return;
  const body = {trade_id: tradeId};
  if(slEl.value) body.stop_loss = parseFloat(slEl.value);
  if(tpEl.value) body.take_profit = parseFloat(tpEl.value);
  try{
    const res = await fetch('/api/trade/update', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if(!res.ok) throw new Error(data.error || data.message || 'HTTP '+res.status);
    if(msgEl){ msgEl.textContent = 'تم التحديث'; msgEl.style.color = 'var(--green)'; }
    setTimeout(()=>loadData(), 600);
  }catch(err){
    if(msgEl){ msgEl.textContent = 'خطأ: '+err.message; msgEl.style.color = 'var(--red)'; }
  }
}

/* ===== Expose to global ===== */
window.openAddTrade = openAddTrade;
window.closeAddTrade = closeAddTrade;
window.openCloseModal = openCloseModal;
window.closeCloseModal = closeCloseModal;
window.toggleInlineEdit = toggleInlineEdit;
window.saveInlineEdit = saveInlineEdit;

/* ===== Render ===== */
function render(data){
  _lastData = data;
  const el = document.getElementById('content');
  const op = data.open_positions || [];
  const ct = data.closed_trades || [];
  const s30 = data.stats_30d || {};
  const s7 = data.stats_7d || {};
  const svt = data.signal_vs_trade || {};

  /* aggregate stats for pulse bar */
  let totalNetPnl = 0, totalFees = 0;
  op.forEach(p=>{
    if(p.pnl){
      totalNetPnl += Number(p.pnl.net_pnl_kwd)||0;
      totalFees += Number(p.pnl.total_fees_kwd)||0;
    }
  });

  let html = '';

  /* ===== PULSE BAR ===== */
  html += '<div class="section-title"><span class="mdi mdi-chart-box-outline"></span> نبض المحفظة</div>';
  html += '<div class="pulse-grid">';
  html += pulseCard('mdi-briefcase-outline','gold', op.length, 'مراكز مفتوحة');
  html += pulseCard('mdi-cash-multiple', totalNetPnl>=0?'green':'red',
    '<span class="ltr">'+pnlSign(totalNetPnl)+n3(totalNetPnl)+'</span>', 'صافي الربح/الخسارة KWD', totalNetPnl>=0?'green':'red');
  html += pulseCard('mdi-receipt-text-outline','amber',
    '<span class="ltr">'+n3(totalFees)+'</span>', 'إجمالي الرسوم KWD');
  html += pulseCard('mdi-trophy-outline','cyan',
    '<span class="ltr">'+(s30.win_rate!=null? pct(s30.win_rate):'\u2014')+'</span>', 'معدل الفوز 30 يوم');
  html += '</div>';

  /* ===== ADD TRADE BUTTON ===== */
  html += '<div class="action-bar">';
  html += '<button class="btn-add-trade" onclick="openAddTrade()"><span class="mdi mdi-plus-thick"></span> إضافة صفقة</button>';
  html += '</div>';

  /* ===== OPEN POSITIONS ===== */
  html += '<div class="section-title"><span class="mdi mdi-swap-vertical-bold"></span> المراكز المفتوحة <span style="font-size:.72rem;color:var(--text-3);font-weight:400;margin-right:.4rem">('+op.length+')</span></div>';
  if(op.length===0){
    html += '<div class="empty-state"><span class="mdi mdi-package-variant"></span>لا توجد مراكز مفتوحة حالياً</div>';
  } else {
    html += '<div class="positions-list">';
    op.forEach(p=>{
      const pnl = p.pnl || {};
      const profitable = Number(pnl.net_pnl_kwd)>=0;
      const cls = profitable?'profit':'loss';
      const dir = (p.direction||'').toLowerCase();
      const dirAr = dir==='long'?'شراء':'بيع';
      const dirCls = dir==='long'?'long':'short';
      const tradeId = p.trade_id || p.id || '';
      const alerts = p.alerts || [];
      const sh = p.signal_health || {};
      const dangerBorder = (sh.confluence_score!=null && sh.confluence_score < 40) ? ' danger-border' : '';

      html += '<div class="pos-card '+cls+dangerBorder+'">';

      /* Alert badges */
      if(alerts.length > 0){
        html += '<div class="alert-badges">';
        alerts.forEach(a=>{
          const lvl = (a.level||'warning').toLowerCase();
          const badgeCls = lvl==='danger'?'danger':'warning';
          const icon = lvl==='danger'?'mdi-alert-octagon':'mdi-alert';
          html += '<span class="alert-badge '+badgeCls+'"><span class="mdi '+icon+'"></span>'+esc(a.message||a.msg||a.text||'')+'</span>';
        });
        html += '</div>';
      }

      html += '<div class="pos-header">';
      html += '<span class="pos-symbol ltr">'+esc(p.symbol)+'</span>';
      html += '<span class="pos-name">'+esc(p.name_ar)+'</span>';
      html += '<span class="pos-dir '+dirCls+'">'+dirAr+'</span>';
      if(p.status) html += '<span class="pos-status">'+esc(p.status)+'</span>';
      html += '</div>';

      html += '<div class="pos-metrics">';
      html += metric('سعر الدخول','<span class="ltr">'+n3(p.entry_price)+'</span>');
      html += metric('السعر الحالي','<span class="ltr">'+n3(p.current_price)+'</span>');
      html += metric('نسبة الربح','<span class="ltr '+pnlClass(pnl.pnl_pct)+'">'+pnlSign(pnl.pnl_pct)+pct(pnl.pnl_pct)+'</span>','big '+pnlClass(pnl.pnl_pct));
      html += metric('صافي PnL','<span class="ltr">'+pnlSign(pnl.net_pnl_kwd)+n3(pnl.net_pnl_kwd)+' KWD</span>','big '+pnlClass(pnl.net_pnl_kwd));
      html += metric('إجمالي PnL','<span class="ltr">'+pnlSign(pnl.gross_pnl_kwd)+n3(pnl.gross_pnl_kwd)+' KWD</span>');
      html += metric('الرسوم','<span class="ltr">'+n3(pnl.total_fees_kwd)+' KWD</span>');
      html += metric('الكمية','<span class="ltr">'+n(p.quantity)+'</span>');
      html += metric('أيام الاحتفاظ','<span class="ltr">'+daysHeld(p.entry_date)+'</span>');
      html += metric('الاستراتيجية', esc(p.entry_reason||p.strategy||'\u2014'));
      html += metric('الدعم','<span class="ltr">'+n3(p.support)+'</span>');
      html += metric('المقاومة','<span class="ltr">'+n3(p.resistance)+'</span>');
      html += metric('تاريخ الدخول','<span class="ltr">'+(p.entry_date||'\u2014')+'</span>');
      html += '</div>';

      /* SL / TP display */
      const curP = Number(p.current_price)||0;
      const slVal = p.stop_loss!=null ? Number(p.stop_loss) : null;
      const tpVal = p.take_profit!=null ? Number(p.take_profit) : null;
      if(slVal || tpVal){
        html += '<div class="sl-tp-row">';
        if(slVal){
          const slPct = curP>0 ? (((slVal-curP)/curP)*100).toFixed(2) : '\u2014';
          html += '<div class="sl-tp-item">';
          html += '<span class="sl-tp-label" style="color:var(--red)"><span class="mdi mdi-shield-alert-outline"></span> SL</span>';
          html += '<span class="sl-tp-val ltr" style="color:var(--red)">'+n3(slVal)+'</span>';
          html += '<span class="sl-tp-pct ltr" style="color:var(--red)">('+slPct+'%)</span>';
          html += '</div>';
        }
        if(tpVal){
          const tpPct = curP>0 ? (((tpVal-curP)/curP)*100).toFixed(2) : '\u2014';
          html += '<div class="sl-tp-item">';
          html += '<span class="sl-tp-label" style="color:var(--green)"><span class="mdi mdi-trophy-outline"></span> TP</span>';
          html += '<span class="sl-tp-val ltr" style="color:var(--green)">'+n3(tpVal)+'</span>';
          html += '<span class="sl-tp-pct ltr" style="color:var(--green)">(+'+( curP>0 ? (((tpVal-curP)/curP)*100).toFixed(2) : '\u2014')+'%)</span>';
          html += '</div>';
        }
        html += '</div>';
      }

      /* Stop Hit Alert */
      if(p.stop_hit){
        html += '<div style="background:var(--red-bg);border:1px solid var(--red-br);border-radius:8px;padding:.65rem 1rem;margin-top:.5rem;display:flex;align-items:center;gap:.5rem;animation:stopFlash 1.5s ease infinite">';
        html += '<span style="font-size:1.1rem">\u26A0\uFE0F</span>';
        html += '<span style="color:var(--red-bright);font-weight:700;font-size:.85rem">\u0648\u0635\u0644 \u0627\u0644\u0633\u062A\u0648\u0628! \u0627\u0644\u0633\u0639\u0631 '+n3(curP)+' \u2264 SL '+n3(slVal)+'</span>';
        html += '</div>';
      }

      /* ATR Trailing Stop Suggestion */
      if(p.trailing_stop && !p.stop_hit){
        const trDist = p.trailing_distance_pct||0;
        const trColor = trDist>3?'var(--green)':trDist>1.5?'var(--amber)':'var(--red)';
        html += '<div style="background:var(--cyan-bg);border:1px solid var(--cyan-br);border-radius:8px;padding:.55rem 1rem;margin-top:.4rem;font-size:.8rem;display:flex;align-items:center;gap:.5rem">';
        html += '<span style="font-size:.9rem">\u{1F6E1}\uFE0F</span>';
        html += '<span style="color:var(--cyan)">Trailing Stop (ATR\u00D72): </span>';
        html += '<span class="ltr" style="font-family:var(--fm);font-weight:600;color:'+trColor+'">'+n3(p.trailing_stop)+'</span>';
        html += '<span class="ltr" style="font-family:var(--fm);font-size:.75rem;color:var(--text-3)">(-'+trDist+'%)</span>';
        if(p.atr) html += '<span class="ltr" style="font-family:var(--fm);font-size:.72rem;color:var(--text-4);margin-right:auto">ATR: '+n3(p.atr)+'</span>';
        html += '</div>';
      }

      /* Signal health strip */
      if(sh && (sh.confluence_score!=null || sh.rsi!=null || sh.macd_momentum!=null)){
        html += '<div class="signal-health-strip">';
        if(sh.confluence_score!=null){
          const cColor = sh.confluence_score>=60?'var(--green)':sh.confluence_score>=40?'var(--amber)':'var(--red)';
          html += '<div class="sh-item"><span class="sh-item-label">CONFLUENCE</span><span class="sh-item-val ltr" style="color:'+cColor+'">'+sh.confluence_score+'</span></div>';
        }
        if(sh.rsi!=null){
          const rColor = sh.rsi>70?'var(--red)':sh.rsi<30?'var(--green)':'var(--text)';
          html += '<div class="sh-item"><span class="sh-item-label">RSI</span><span class="sh-item-val ltr" style="color:'+rColor+'">'+Number(sh.rsi).toFixed(1)+'</span></div>';
        }
        if(sh.macd_momentum!=null){
          const mColor = sh.macd_momentum>=0?'var(--green)':'var(--red)';
          html += '<div class="sh-item"><span class="sh-item-label">MACD</span><span class="sh-item-val ltr" style="color:'+mColor+'">'+(sh.macd_momentum>=0?'+':'')+Number(sh.macd_momentum).toFixed(3)+'</span></div>';
        }
        if(sh.trend) html += '<div class="sh-item"><span class="sh-item-label">TREND</span><span class="sh-item-val">'+esc(sh.trend)+'</span></div>';
        if(sh.volume_signal) html += '<div class="sh-item"><span class="sh-item-label">VOLUME</span><span class="sh-item-val">'+esc(sh.volume_signal)+'</span></div>';
        html += '</div>';
      }

      if(p.entry_reason){
        html += '<div class="pos-reason"><div class="pos-reason-label">سبب الدخول</div>'+esc(p.entry_reason)+'</div>';
      }

      /* Action buttons */
      html += '<div class="pos-actions">';
      html += '<button class="btn-pos-close" onclick="openCloseModal(\''+esc(tradeId)+'\',\''+esc(p.symbol)+'\','+(p.current_price||'')+')"><span class="mdi mdi-close-thick"></span> إغلاق</button>';
      html += '<button class="btn-pos-edit" onclick="toggleInlineEdit(\''+esc(tradeId)+'\')"><span class="mdi mdi-pencil-outline"></span> تعديل</button>';
      html += '</div>';

      /* Inline edit for SL/TP */
      html += '<div class="inline-edit" id="ie_'+esc(tradeId)+'">';
      html += '<div class="inline-edit-row">';
      html += '<div class="inline-edit-field"><label>وقف الخسارة</label><input type="number" step="any" id="ie_sl_'+esc(tradeId)+'" value="'+(slVal||'')+'" placeholder="SL"></div>';
      html += '<div class="inline-edit-field"><label>جني الأرباح</label><input type="number" step="any" id="ie_tp_'+esc(tradeId)+'" value="'+(tpVal||'')+'" placeholder="TP"></div>';
      html += '<button class="btn-inline-save" onclick="saveInlineEdit(\''+esc(tradeId)+'\')">حفظ</button>';
      html += '<button class="btn-inline-cancel" onclick="toggleInlineEdit(\''+esc(tradeId)+'\')">إلغاء</button>';
      html += '</div>';
      html += '<div class="inline-msg" id="ie_msg_'+esc(tradeId)+'"></div>';
      html += '</div>';

      html += '</div>';
    });
    html += '</div>';
  }

  /* ===== CLOSED TRADES ===== */
  if(ct.length>0){
    html += '<div class="section-title"><span class="mdi mdi-history"></span> الصفقات المغلقة <span style="font-size:.72rem;color:var(--text-3);font-weight:400;margin-right:.4rem">('+ct.length+')</span></div>';
    html += '<div class="positions-list">';
    ct.forEach(t=>{
      const pnl = t.pnl || {};
      const profitable = Number(pnl.net_pnl_kwd)>=0;
      const cls = profitable?'profit':'loss';
      const dir = (t.direction||'').toLowerCase();
      const dirAr = dir==='long'?'شراء':'بيع';
      const dirCls = dir==='long'?'long':'short';
      html += '<div class="closed-card '+cls+'">';
      html += '<div class="closed-header">';
      html += '<span class="pos-symbol ltr">'+esc(t.symbol)+'</span>';
      html += '<span class="pos-name">'+esc(t.name_ar)+'</span>';
      html += '<span class="pos-dir '+dirCls+'">'+dirAr+'</span>';
      html += '</div>';
      html += '<div class="closed-metrics">';
      html += metric('دخول','<span class="ltr">'+n3(t.entry_price)+'</span>');
      html += metric('خروج','<span class="ltr">'+n3(t.exit_price)+'</span>');
      html += metric('نسبة','<span class="ltr '+pnlClass(pnl.net_pnl_pct)+'">'+pnlSign(pnl.net_pnl_pct)+pct(pnl.net_pnl_pct)+'</span>');
      html += metric('صافي','<span class="ltr '+pnlClass(pnl.net_pnl_kwd)+'">'+pnlSign(pnl.net_pnl_kwd)+n3(pnl.net_pnl_kwd)+' KWD</span>');
      html += metric('تاريخ الدخول','<span class="ltr">'+(t.entry_date||'\u2014')+'</span>');
      html += metric('تاريخ الخروج','<span class="ltr">'+(t.exit_date||'\u2014')+'</span>');
      if(t.exit_reason) html += metric('سبب الخروج', esc(t.exit_reason));
      html += '</div>';
      html += '</div>';
    });
    html += '</div>';
  }

  /* ===== SIGNAL VS TRADE ===== */
  html += '<div class="section-title"><span class="mdi mdi-signal-variant"></span> الإشارات مقابل التداول</div>';
  html += '<div class="signal-grid">';
  html += pulseCard('mdi-bell-ring-outline','cyan',
    '<span class="ltr">'+(svt.signals_7d!=null?svt.signals_7d:'\u2014')+'</span>', 'إشارات آخر 7 أيام');
  html += pulseCard('mdi-check-decagram-outline','green',
    '<span class="ltr">'+(svt.confirmed_7d!=null?svt.confirmed_7d:'\u2014')+'</span>', 'صفقات مؤكدة');
  html += pulseCard('mdi-skip-next-circle-outline','amber',
    '<span class="ltr">'+(svt.skip_rate!=null?pct(svt.skip_rate):'\u2014')+'</span>', 'معدل التجاوز');
  html += '</div>';

  /* ===== STATS COMPARISON ===== */
  html += '<div class="section-title"><span class="mdi mdi-chart-bar"></span> مقارنة الأداء</div>';
  html += '<div class="stats-compare">';
  html += statsPanel('آخر 7 أيام','mdi-calendar-week', s7);
  html += statsPanel('آخر 30 يوم','mdi-calendar-month', s30);
  html += '</div>';

  /* ===== FOOTER ===== */
  html += '<footer class="footer">';
  html += 'البيانات للاطلاع فقط ولا تُعدّ نصيحة استثمارية — بورصة الكويت';
  html += '<div class="footer-ts ltr">'+new Date().toLocaleString('en-GB')+'</div>';
  html += '</footer>';

  el.innerHTML = html;
}

function pulseCard(icon, colorCls, value, label, valColor){
  return '<div class="pulse-card">'
    +'<div class="pulse-icon '+colorCls+'"><span class="mdi '+icon+'"></span></div>'
    +'<div class="pulse-info">'
    +'<div class="pulse-val'+(valColor?' '+valColor:'')+'">'+value+'</div>'
    +'<div class="pulse-label">'+label+'</div>'
    +'</div></div>';
}

function metric(label, value, extraCls){
  return '<div class="pos-metric">'
    +'<div class="pos-metric-label">'+label+'</div>'
    +'<div class="pos-metric-val'+(extraCls?' '+extraCls:'')+'">'+value+'</div>'
    +'</div>';
}

function statsPanel(title, icon, s){
  let html = '<div class="stats-panel">';
  html += '<div class="stats-panel-title"><span class="mdi '+icon+'"></span> '+title+'</div>';
  html += '<div class="stats-rows">';
  html += sRow('إجمالي الصفقات', s.total_trades);
  html += sRow('صفقات رابحة', s.wins, 'green');
  html += sRow('صفقات خاسرة', s.losses, 'red');
  html += sRow('معدل الفوز', s.win_rate!=null?pct(s.win_rate):'\u2014', 'cyan');
  html += sRow('متوسط الربح', s.avg_profit_pct!=null?pct(s.avg_profit_pct):'\u2014', 'green');
  html += sRow('متوسط الخسارة', s.avg_loss_pct!=null?pct(s.avg_loss_pct):'\u2014', 'red');
  html += sRow('إجمالي PnL (فلس)', s.total_pnl_fils!=null?'<span class="ltr">'+n(s.total_pnl_fils)+'</span>':'\u2014',
    s.total_pnl_fils>=0?'green':'red');
  html += '</div></div>';
  return html;
}

function sRow(label, value, color){
  const v = value!=null?value:'\u2014';
  return '<div class="stats-row">'
    +'<span class="stats-row-label">'+label+'</span>'
    +'<span class="stats-row-val ltr'+(color?' style="color:var(--'+color+')"':'')+'">'+v+'</span>'
    +'</div>';
}

/* ===== Data Loading ===== */
function showLoading(){
  document.getElementById('loading').style.display='';
  document.getElementById('errorState').style.display='none';
  document.getElementById('content').style.display='none';
}
function showError(msg){
  document.getElementById('loading').style.display='none';
  document.getElementById('errorState').style.display='';
  document.getElementById('content').style.display='none';
  document.getElementById('errorMsg').textContent = msg||'تعذّر تحميل البيانات';
}
function showContent(){
  document.getElementById('loading').style.display='none';
  document.getElementById('errorState').style.display='none';
  document.getElementById('content').style.display='';
}

async function loadData(){
  showLoading();
  const btn = document.getElementById('btnRefresh');
  btn.classList.add('spinning');
  try{
    const res = await fetch(API_URL, {headers: authHeaders()});
    if(!res.ok) throw new Error('HTTP '+res.status);
    const data = await res.json();
    render(data);
    showContent();
  }catch(e){
    console.error('Portfolio fetch error:', e);
    showError('تعذّر تحميل البيانات: '+e.message);
  }finally{
    btn.classList.remove('spinning');
  }
}

/* ===== Init ===== */
window.loadData = loadData;
loadData();
refreshTimer = setInterval(loadData, REFRESH_MS);

/* ===== Refresh button ===== */
document.getElementById('btnRefresh').addEventListener('click', function(){
  clearInterval(refreshTimer);
  loadData();
  refreshTimer = setInterval(loadData, REFRESH_MS);
});

/* ===== Keyboard: Escape closes modals ===== */
document.addEventListener('keydown', function(e){
  if(e.key==='Escape'){
    closeAddTrade();
    closeCloseModal();
  }
});

})();
</script>
<script src="indicator-tooltips.js"></script>
</body>
</html>

```


############################################################
# FILE: www/trading/brain.html (318 lines)
############################################################

```html
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>عقل النظام — KSE</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Noto+Kufi+Arabic:wght@400;500;600;700;800&family=Tajawal:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>
:root{--n9:#070D17;--n8:#0C1525;--n7:#111E32;--n6:#162840;--n5:#1C334F;--gold:#C6974B;--gold-b:#D4A95C;--gold-bg:rgba(198,151,75,.06);--gold-br:rgba(198,151,75,.25);--grn:#4CAF82;--grn-bg:rgba(76,175,130,.08);--grn-br:rgba(76,175,130,.3);--red:#D94452;--red-bg:rgba(217,68,82,.08);--red-br:rgba(217,68,82,.3);--amb:#E8A838;--amb-bg:rgba(232,168,56,.08);--amb-br:rgba(232,168,56,.3);--cyn:#38BDF8;--cyn-bg:rgba(56,189,248,.08);--cyn-br:rgba(56,189,248,.3);--t:#E8ECF0;--t2:#A0ADBC;--t3:#6B7D90;--t4:#405060;--card:#0E1929;--card-h:#132137;--cb:#1A2E45;--f:'Tajawal','Noto Kufi Arabic',sans-serif;--fd:'Noto Kufi Arabic','Tajawal',sans-serif;--fm:'IBM Plex Mono',monospace}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--f);background:var(--n9);color:var(--t);min-height:100vh;-webkit-font-smoothing:antialiased}
.ltr{direction:ltr;unicode-bidi:isolate}
</style>
</head>
<body>
<style>
.topbar{position:sticky;top:0;z-index:100;background:rgba(7,13,23,.92);backdrop-filter:blur(16px);border-bottom:1px solid var(--cb);padding:0 1.25rem;height:56px;display:flex;align-items:center;justify-content:space-between}
.brand{display:flex;align-items:center;gap:.75rem}
.brand-m{background:linear-gradient(135deg,var(--gold),#9E7A3D);color:var(--n9);font-family:var(--fm);font-weight:700;font-size:.85rem;padding:.25rem .6rem;border-radius:4px}
.brand-t{font-family:var(--fd);font-weight:700;font-size:1rem}
.nav{display:flex;gap:.15rem}
.nav a{font-size:.75rem;padding:.3rem .6rem;border-radius:6px;color:var(--t3);text-decoration:none;transition:.2s}
.nav a:hover{color:var(--t);background:var(--n7)}
.nav a.on{color:var(--gold);background:var(--gold-bg);border:1px solid var(--gold-br)}
.clock{font-family:var(--fm);font-size:.85rem;color:var(--gold);direction:ltr}
.main{padding:1.25rem;max-width:1200px;margin:0 auto}
</style>
<style>
/* SECTIONS */
.section{background:var(--card);border:1px solid var(--cb);border-radius:12px;margin-bottom:1rem;overflow:hidden}
.section-head{padding:.85rem 1.15rem;border-bottom:1px solid var(--cb);display:flex;justify-content:space-between;align-items:center}
.section-title{font-family:var(--fd);font-size:.95rem;font-weight:700;color:var(--t)}
.section-badge{font-family:var(--fm);font-size:.65rem;padding:2px 8px;border-radius:10px;background:var(--gold-bg);color:var(--gold);border:1px solid var(--gold-br)}
.section-body{padding:1rem 1.15rem}
/* INSIGHT CARDS */
.insights{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:.75rem;margin-bottom:1rem}
.insight{background:var(--n8);border:1px solid var(--cb);border-radius:10px;padding:.85rem;transition:border-color .2s}
.insight:hover{border-color:var(--gold-br)}
.insight-icon{font-size:1.5rem;margin-bottom:.3rem}
.insight-label{font-size:.68rem;color:var(--t3);margin-bottom:.25rem}
.insight-value{font-family:var(--fm);font-size:1.1rem;font-weight:700;margin-bottom:.15rem}
.insight-sub{font-size:.72rem;color:var(--t2);line-height:1.5}
/* COMPARISON BAR */
.comp-row{display:flex;gap:.75rem;margin-bottom:.6rem;align-items:center}
.comp-label{font-size:.75rem;color:var(--t2);min-width:60px;text-align:left}
.comp-bar-wrap{flex:1;height:24px;background:var(--n7);border-radius:6px;overflow:hidden;position:relative}
.comp-bar{height:100%;border-radius:6px;display:flex;align-items:center;justify-content:flex-end;padding:0 8px;font-family:var(--fm);font-size:.65rem;font-weight:600;color:#fff;transition:width .6s}
.comp-val{font-family:var(--fm);font-size:.78rem;font-weight:700;min-width:55px;text-align:left}
/* TABLE */
.st{width:100%;border-collapse:collapse}
.st th{font-size:.65rem;color:var(--t3);font-weight:500;text-align:right;padding:.6rem .75rem;border-bottom:1px solid var(--cb);background:var(--n8)}
.st td{padding:.55rem .75rem;border-bottom:1px solid rgba(26,46,69,.5);font-size:.78rem}
.st tr:hover{background:var(--card-h)}
/* ACTION PANEL */
.action-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:.75rem}
.action-card{border-radius:10px;padding:.85rem;border:1px solid}
.action-card.do-more{background:var(--grn-bg);border-color:var(--grn-br)}
.action-card.avoid{background:var(--red-bg);border-color:var(--red-br)}
.action-card.watch{background:var(--amb-bg);border-color:var(--amb-br)}
.action-card h3{font-family:var(--fd);font-size:.85rem;font-weight:700;margin-bottom:.5rem}
.action-card ul{list-style:none;font-size:.75rem;color:var(--t2);line-height:1.8}
.action-card li::before{content:'• ';color:var(--t3)}
/* LOADING */
.loading{display:flex;align-items:center;justify-content:center;padding:4rem;gap:1rem}
.spinner{width:36px;height:36px;border:3px solid var(--n6);border-top-color:var(--gold);border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.footer{text-align:center;padding:1.5rem;font-size:.65rem;color:var(--t4);border-top:1px solid var(--cb);margin-top:2rem}
@media(max-width:768px){.insights{grid-template-columns:1fr}.action-cards{grid-template-columns:1fr}.nav{display:none}}
</style>

<header class="topbar">
  <div class="brand"><span class="brand-m">KSE</span><span class="brand-t">&#1593;&#1602;&#1604; &#1575;&#1604;&#1606;&#1592;&#1575;&#1605;</span></div>
  <nav class="nav">
    <a href="decisions">&#1575;&#1604;&#1602;&#1585;&#1575;&#1585;&#1575;&#1578;</a>
    <a href="positions">&#1575;&#1604;&#1605;&#1585;&#1575;&#1603;&#1586;</a>
    <a href="radar">&#1575;&#1604;&#1585;&#1575;&#1583;&#1575;&#1585;</a>
    <a href="journal">&#1575;&#1604;&#1587;&#1580;&#1604;</a>
    <a href="strategies">&#1575;&#1604;&#1575;&#1587;&#1578;&#1585;&#1575;&#1578;&#1610;&#1580;&#1610;&#1575;&#1578;</a>
    <a href="brain" class="on">&#1575;&#1604;&#1593;&#1602;&#1604;</a>
  </nav>
  <span class="clock" id="ck"></span>
</header>

<main class="main">
  <div class="loading" id="loadState"><div class="spinner"></div><span style="color:var(--t3)">&#1580;&#1575;&#1585;&#1610; &#1578;&#1581;&#1604;&#1610;&#1604; &#1575;&#1604;&#1576;&#1610;&#1575;&#1606;&#1575;&#1578;...</span></div>
  <div id="content" style="display:none">

    <!-- SECTION 1: KEY LEARNINGS -->
    <div class="insights" id="insightCards"></div>

    <!-- SECTION 2: EDGE MAP -->
    <div class="section" id="edgeSection">
      <div class="section-head"><span class="section-title">&#1608;&#1610;&#1606; &#1575;&#1604;&#1601;&#1585;&#1589;&#1577; &#1575;&#1604;&#1581;&#1602;&#1610;&#1602;&#1610;&#1577;&#1567;</span><span class="section-badge" id="tfBadge"></span></div>
      <div class="section-body">
        <div id="tfBars"></div>
        <div style="margin-top:1rem">
          <div style="font-size:.78rem;font-weight:600;color:var(--gold);margin-bottom:.5rem">&#1571;&#1601;&#1590;&#1604; &#1637; &#1576;&#1610;&#1574;&#1575;&#1578;</div>
          <table class="st" id="topCtxTable"><thead><tr><th>&#1575;&#1604;&#1601;&#1585;&#1610;&#1605;</th><th>&#1575;&#1604;&#1606;&#1592;&#1575;&#1605;</th><th>&#1575;&#1604;&#1575;&#1578;&#1580;&#1575;&#1607;</th><th>&#1593;&#1610;&#1606;&#1575;&#1578;</th><th>&#1606;&#1587;&#1576;&#1577; &#1606;&#1580;&#1575;&#1581;</th><th>&#1605;&#1578;&#1608;&#1587;&#1591; &#1593;&#1575;&#1574;&#1583;</th></tr></thead><tbody></tbody></table>
        </div>
      </div>
    </div>

    <!-- SECTION 3: TOP STRATEGIES -->
    <div class="section">
      <div class="section-head"><span class="section-title">&#1588;&#1606;&#1608; &#1610;&#1606;&#1601;&#1593; &#1608;&#1588;&#1606;&#1608; &#1601;&#1575;&#1588;&#1604;&#1567;</span></div>
      <div class="section-body">
        <div style="font-size:.78rem;font-weight:600;color:var(--grn);margin-bottom:.5rem">&#128640; &#1571;&#1601;&#1590;&#1604; &#1637; &#1575;&#1587;&#1578;&#1585;&#1575;&#1578;&#1610;&#1580;&#1610;&#1575;&#1578;</div>
        <table class="st" id="bestTable"><thead><tr><th>&#1575;&#1604;&#1606;&#1605;&#1591;</th><th>&#1575;&#1604;&#1606;&#1592;&#1575;&#1605;</th><th>&#1593;&#1610;&#1606;&#1575;&#1578;</th><th>&#1606;&#1580;&#1575;&#1581;</th><th>EV</th><th>PF</th></tr></thead><tbody></tbody></table>
        <div style="font-size:.78rem;font-weight:600;color:var(--red);margin:1rem 0 .5rem">&#9940; &#1571;&#1587;&#1608;&#1571; &#1637; &#1575;&#1587;&#1578;&#1585;&#1575;&#1578;&#1610;&#1580;&#1610;&#1575;&#1578;</div>
        <table class="st" id="worstTable"><thead><tr><th>&#1575;&#1604;&#1606;&#1605;&#1591;</th><th>&#1575;&#1604;&#1606;&#1592;&#1575;&#1605;</th><th>&#1593;&#1610;&#1606;&#1575;&#1578;</th><th>&#1606;&#1580;&#1575;&#1581;</th><th>EV</th><th>PF</th></tr></thead><tbody></tbody></table>
      </div>
    </div>

    <!-- SECTION 4: DECISION SCORECARD -->
    <div class="section">
      <div class="section-head"><span class="section-title">&#1571;&#1583;&#1575;&#1569; &#1605;&#1581;&#1585;&#1603; &#1575;&#1604;&#1602;&#1585;&#1575;&#1585;&#1575;&#1578;</span><span class="section-badge" id="decBadge"></span></div>
      <div class="section-body" id="scorecardBody"></div>
    </div>

    <!-- SECTION 5: ACTION PANEL -->
    <div class="action-cards" id="actionPanel"></div>

  </div>
</main>
<footer class="footer">&#1578;&#1581;&#1604;&#1610;&#1604; &#1605;&#1576;&#1606;&#1610; &#1593;&#1604;&#1609; &#1576;&#1610;&#1575;&#1606;&#1575;&#1578; &#1578;&#1575;&#1585;&#1610;&#1582;&#1610;&#1577; &#8212; &#1604;&#1575; &#1610;&#1605;&#1579;&#1604; &#1606;&#1589;&#1610;&#1581;&#1577; &#1575;&#1587;&#1578;&#1579;&#1605;&#1575;&#1585;&#1610;&#1577;</footer>

<script>
(function(){
const ck=document.getElementById('ck');
function tick(){ck.textContent=new Date().toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}
tick();setInterval(tick,1000);
const L=s=>'<span class="ltr">'+s+'</span>';

const regimeAr={'trending':'\u0627\u062A\u062C\u0627\u0647','ranging':'\u062A\u0630\u0628\u0630\u0628','transition':'\u0627\u0646\u062A\u0642\u0627\u0644'};
const dirAr={'up':'\u0635\u0627\u0639\u062F','down':'\u0647\u0627\u0628\u0637','neutral':'\u0645\u062D\u0627\u064A\u062F'};
const tfAr={'1D':'\u064A\u0648\u0645\u064A','30m':'30 \u062F\u0642\u064A\u0642\u0629','historical_backfill':'\u064A\u0648\u0645\u064A','historical_backfill_30m':'30 \u062F\u0642\u064A\u0642\u0629'};

async function loadData(){
  try{
    const r=await fetch('/dashboard/brain-insights');
    if(!r.ok)throw new Error('HTTP '+r.status);
    const d=await r.json();
    render(d);
    document.getElementById('loadState').style.display='none';
    document.getElementById('content').style.display='';
  }catch(e){
    document.getElementById('loadState').innerHTML='<span style="color:var(--red)">\u274C '+e.message+'</span>';
  }
}

function render(d){
  const kl=d.key_learnings||{};
  const em=d.edge_map||{};
  const ts=d.top_strategies||{};
  const sc=d.decision_scorecard||{};
  const ap=d.action_panel||{};
  const stats=ap.system_stats||{};

  // === SECTION 1: KEY LEARNINGS ===
  const tf=kl.timeframe_comparison||[];
  const tf1d=tf.find(t=>t.timeframe.includes('1') || t.timeframe==='1D')||{};
  const tf30=tf.find(t=>t.timeframe.includes('30'))||{};
  const topP=kl.top_pattern||{};
  const bestCtx=kl.best_context||{};

  let cards='';
  // Card 1: Timeframe
  cards+='<div class="insight" style="border-color:var(--grn-br)">'
    +'<div class="insight-icon">\u{1F4C8}</div>'
    +'<div class="insight-label">\u0623\u0641\u0636\u0644 \u0641\u0631\u064A\u0645</div>'
    +'<div class="insight-value" style="color:var(--grn)">\u0627\u0644\u064A\u0648\u0645\u064A</div>'
    +'<div class="insight-sub">\u0646\u0633\u0628\u0629 \u0646\u062C\u0627\u062D '+L((tf1d.win_rate||0).toFixed(0)+'%')+' \u0645\u0642\u0627\u0628\u0644 '+L((tf30.win_rate||0).toFixed(0)+'%')+' \u0644\u0640 30 \u062F\u0642\u064A\u0642\u0629<br>\u0645\u062A\u0648\u0633\u0637 \u0639\u0627\u0626\u062F '+L((tf1d.avg_return||0).toFixed(1)+'%')+' \u0645\u0642\u0627\u0628\u0644 '+L((tf30.avg_return||0).toFixed(1)+'%')+'</div>'
    +'</div>';
  // Card 2: Top Pattern
  if(topP.ev){
    cards+='<div class="insight" style="border-color:var(--gold-br)">'
      +'<div class="insight-icon">\u{1F3AF}</div>'
      +'<div class="insight-label">\u0623\u0642\u0648\u0649 \u0646\u0645\u0637 \u0645\u0643\u062A\u0634\u0641</div>'
      +'<div class="insight-value" style="color:var(--gold)">EV '+L(topP.ev.toFixed(1))+'</div>'
      +'<div class="insight-sub">'+topP.pattern_ar+'<br>\u0646\u062C\u0627\u062D '+L(topP.win_pct.toFixed(0)+'%')+' \u2022 PF '+L(topP.pf.toFixed(1))+' \u2022 '+L(topP.samples)+' \u0639\u064A\u0646\u0629</div>'
      +'</div>';
  }
  // Card 3: Best Context
  if(bestCtx.regime){
    cards+='<div class="insight" style="border-color:var(--cyn-br)">'
      +'<div class="insight-icon">\u{1F30D}</div>'
      +'<div class="insight-label">\u0623\u0641\u0636\u0644 \u0628\u064A\u0626\u0629</div>'
      +'<div class="insight-value" style="color:var(--cyn)">'+(regimeAr[bestCtx.regime]||bestCtx.regime)+' / '+(dirAr[bestCtx.direction]||bestCtx.direction)+'</div>'
      +'<div class="insight-sub">\u0646\u062C\u0627\u062D '+L(bestCtx.win_rate.toFixed(0)+'%')+' \u2022 '+L(bestCtx.samples)+' \u0639\u064A\u0646\u0629</div>'
      +'</div>';
  }
  // Card 4: System Stats
  cards+='<div class="insight" style="border-color:var(--cb)">'
    +'<div class="insight-icon">\u{1F9E0}</div>'
    +'<div class="insight-label">\u0627\u0644\u0646\u0638\u0627\u0645 \u062A\u0639\u0644\u0651\u0645 \u0645\u0646</div>'
    +'<div class="insight-value" style="color:var(--t)">'+L((stats.total_signals||0).toLocaleString())+' \u0625\u0634\u0627\u0631\u0629</div>'
    +'<div class="insight-sub">'+L(stats.total_strategies||0)+' \u0627\u0633\u062A\u0631\u0627\u062A\u064A\u062C\u064A\u0629 \u2022 '+L(stats.unique_stocks||0)+' \u0633\u0647\u0645 \u2022 \u0645\u062A\u0648\u0633\u0637 EV '+L((stats.avg_strategy_ev||0).toFixed(1))+'</div>'
    +'</div>';
  document.getElementById('insightCards').innerHTML=cards;

  // === SECTION 2: EDGE MAP ===
  const byTf=em.by_timeframe||[];
  const maxRet=Math.max(...byTf.map(t=>Math.abs(t.avg_return)),1);
  document.getElementById('tfBadge').textContent=byTf.length+' \u0641\u0631\u064A\u0645';
  let bars='';
  byTf.forEach(function(t){
    const w=Math.abs(t.avg_return)/maxRet*100;
    const c=t.avg_return>0?'var(--grn)':'var(--red)';
    bars+='<div class="comp-row">'
      +'<span class="comp-label">'+(tfAr[t.timeframe]||t.timeframe)+'</span>'
      +'<div class="comp-bar-wrap"><div class="comp-bar" style="width:'+Math.max(w,5)+'%;background:'+c+'">'+L(t.win_rate.toFixed(0)+'%')+'</div></div>'
      +'<span class="comp-val" style="color:'+c+'">'+L((t.avg_return>=0?'+':'')+t.avg_return.toFixed(2)+'%')+'</span>'
      +'</div>';
  });
  document.getElementById('tfBars').innerHTML=bars;

  // Top contexts table
  const topCtx=em.top_contexts||[];
  let ctxRows='';
  topCtx.forEach(function(c){
    const rc=c.avg_return>=0?'var(--grn)':'var(--red)';
    ctxRows+='<tr><td>'+L(tfAr[c.timeframe]||c.timeframe)+'</td><td>'+(regimeAr[c.regime]||c.regime)+'</td><td>'+(dirAr[c.direction]||c.direction)+'</td><td>'+L(c.samples)+'</td><td style="color:var(--grn)">'+L(c.win_rate.toFixed(0)+'%')+'</td><td style="color:'+rc+'">'+L((c.avg_return>=0?'+':'')+c.avg_return.toFixed(2)+'%')+'</td></tr>';
  });
  document.querySelector('#topCtxTable tbody').innerHTML=ctxRows;

  // === SECTION 3: TOP/WORST STRATEGIES ===
  function stratRows(arr,tbody){
    let html='';
    (arr||[]).forEach(function(s){
      const evC=s.ev>5?'var(--grn)':s.ev>1?'var(--amb)':'var(--red)';
      html+='<tr><td style="font-size:.72rem;color:var(--cyn)">'+s.pattern_ar+'</td><td>'+(regimeAr[s.regime]||s.regime)+'</td><td>'+L(s.samples)+'</td><td style="color:var(--grn)">'+L(s.win_pct.toFixed(0)+'%')+'</td><td style="color:'+evC+';font-family:var(--fm);font-weight:700">'+L(s.ev.toFixed(1))+'</td><td>'+L(s.pf.toFixed(1))+'</td></tr>';
    });
    document.querySelector(tbody+' tbody').innerHTML=html;
  }
  stratRows(ts.best_5,'#bestTable');
  stratRows(ts.worst_5,'#worstTable');

  // === SECTION 4: DECISION SCORECARD ===
  let scHtml='';
  const totalDec=sc.total_decisions||0;
  const enters=sc.total_by_decision?.find(d=>d.smart_decision==='ENTER');
  const enterCount=enters?enters.count:0;
  document.getElementById('decBadge').textContent=totalDec+' \u0642\u0631\u0627\u0631';

  // Recent ENTER decisions
  const recent=sc.recent_enters||[];
  if(recent.length){
    scHtml+='<div style="font-size:.78rem;font-weight:600;color:var(--grn);margin-bottom:.5rem">\u0622\u062E\u0631 \u0642\u0631\u0627\u0631\u0627\u062A \u0627\u0644\u062F\u062E\u0648\u0644</div>';
    scHtml+='<table class="st"><thead><tr><th>\u0627\u0644\u0633\u0647\u0645</th><th>\u0627\u0644\u062A\u0627\u0631\u064A\u062E</th><th>\u0627\u0644\u062B\u0642\u0629</th><th>\u062C\u0648\u062F\u0629</th><th>R/R</th><th>\u0627\u0644\u0642\u0637\u0627\u0639</th><th>\u0627\u0644\u0645\u0635\u062F\u0631</th><th>\u0627\u0644\u0646\u062A\u064A\u062C\u0629</th></tr></thead><tbody>';
    recent.forEach(function(r){
      const src=r.chosen_plan_source==='strategy'?'\u0627\u0633\u062A\u0631\u0627\u062A\u064A\u062C\u064A\u0629':'\u062F\u0639\u0645/\u0645\u0642\u0627\u0648\u0645\u0629';
      const outC=r.outcome==='pending'?'var(--amb)':'var(--grn)';
      const outAr=r.outcome==='pending'?'\u0642\u064A\u062F \u0627\u0644\u0645\u062A\u0627\u0628\u0639\u0629':r.outcome;
      scHtml+='<tr><td style="font-family:var(--fm);color:var(--gold)">'+L(r.symbol)+'</td><td>'+L(r.market_date)+'</td><td>'+L(r.confidence.toFixed(0))+'</td><td>'+L(r.data_quality)+'</td><td style="font-family:var(--fm);color:var(--grn)">'+L(r.rr_ratio.toFixed(1)+'x')+'</td><td>'+r.sector+'</td><td>'+src+'</td><td style="color:'+outC+'">'+outAr+'</td></tr>';
    });
    scHtml+='</tbody></table>';
  }

  // Confidence buckets
  const byConf=sc.enter_by_confidence||[];
  if(byConf.length){
    scHtml+='<div style="font-size:.78rem;font-weight:600;color:var(--cyn);margin:1rem 0 .5rem">\u0627\u0644\u062B\u0642\u0629 \u0645\u0642\u0627\u0628\u0644 \u0627\u0644\u062C\u0648\u062F\u0629</div>';
    scHtml+='<div style="display:flex;gap:.5rem;flex-wrap:wrap">';
    byConf.forEach(function(b){
      scHtml+='<div style="background:var(--n8);border-radius:8px;padding:.5rem .75rem;text-align:center;min-width:100px">'
        +'<div style="font-family:var(--fm);font-size:.9rem;font-weight:700;color:var(--cyn)">'+L(b.bucket)+'</div>'
        +'<div style="font-size:.62rem;color:var(--t3)">\u062B\u0642\u0629</div>'
        +'<div style="font-size:.72rem;color:var(--t2);margin-top:.25rem">'+L(b.count)+' \u0642\u0631\u0627\u0631 \u2022 \u062C\u0648\u062F\u0629 '+L(b.avg_quality.toFixed(0))+'</div></div>';
    });
    scHtml+='</div>';
  }
  document.getElementById('scorecardBody').innerHTML=scHtml||'<div style="color:var(--t3);text-align:center;padding:2rem">\u0644\u0627 \u062A\u0648\u062C\u062F \u0642\u0631\u0627\u0631\u0627\u062A \u0645\u0633\u062C\u0651\u0644\u0629 \u0628\u0639\u062F</div>';

  // === SECTION 5: ACTION PANEL ===
  const doMore=ap.do_more||[];
  const avoid=ap.avoid||[];
  let apHtml='';

  // Do More
  apHtml+='<div class="action-card do-more"><h3>\u2705 \u0632\u0650\u062F \u0645\u0646</h3><ul>';
  if(doMore.length){
    doMore.forEach(function(d){
      apHtml+='<li>'+(tfAr[d.timeframe]||d.timeframe)+' / '+(regimeAr[d.regime]||d.regime)+' / '+(dirAr[d.direction]||d.direction)+' \u2014 \u0639\u0627\u0626\u062F '+L((d.avg_return>=0?'+':'')+d.avg_return.toFixed(1)+'%')+' ('+L(d.samples)+' \u0639\u064A\u0646\u0629)</li>';
    });
  } else {
    apHtml+='<li>\u0627\u0644\u0641\u0631\u064A\u0645 \u0627\u0644\u064A\u0648\u0645\u064A \u0641\u064A \u0627\u062A\u062C\u0627\u0647 \u0635\u0627\u0639\u062F \u2014 \u0623\u0641\u0636\u0644 \u0628\u064A\u0626\u0629</li>';
    apHtml+='<li>\u0623\u0646\u0645\u0627\u0637 "\u0627\u0644\u0635\u0639\u0648\u062F \u0627\u0644\u0645\u064F\u062A\u0639\u064E\u0628" (MACD \u0645\u062A\u0628\u0627\u0637\u0626 + RSI \u0639\u0627\u0644\u064A + \u062A\u0630\u0628\u0630\u0628 \u0639\u0627\u0644\u064A)</li>';
    apHtml+='<li>\u0627\u0644\u062D\u062C\u0645 \u0643\u0645\u0624\u0634\u0631 \u062A\u0623\u0643\u064A\u062F\u064A \u2014 \u0623\u0639\u0644\u0649 \u062F\u0642\u0629 \u0628\u064A\u0646 \u0627\u0644\u0645\u0624\u0634\u0631\u0627\u062A</li>';
  }
  apHtml+='</ul></div>';

  // Avoid
  apHtml+='<div class="action-card avoid"><h3>\u26D4 \u062A\u062C\u0646\u0651\u0628</h3><ul>';
  if(avoid.length){
    avoid.forEach(function(a){
      apHtml+='<li>'+(tfAr[a.timeframe]||a.timeframe)+' / '+(regimeAr[a.regime]||a.regime)+' / '+(dirAr[a.direction]||a.direction)+' \u2014 \u0639\u0627\u0626\u062F '+L(a.avg_return.toFixed(1)+'%')+' ('+L(a.samples)+' \u0639\u064A\u0646\u0629)</li>';
    });
  } else {
    apHtml+='<li>\u0625\u0634\u0627\u0631\u0627\u062A 30 \u062F\u0642\u064A\u0642\u0629 \u0628\u062D\u062C\u0645 \u0636\u0639\u064A\u0641</li>';
  }
  apHtml+='</ul></div>';

  // Watch
  apHtml+='<div class="action-card watch"><h3>\u{1F440} \u0631\u0627\u0642\u0628</h3><ul>';
  apHtml+='<li>\u0623\u062F\u0627\u0621 \u0622\u062E\u0631 '+L(totalDec)+' \u0642\u0631\u0627\u0631 \u2014 \u0645\u062A\u0648\u0633\u0637 R/R '+L(((sc.enter_by_quality||[{avg_rr:0}])[0].avg_rr||0).toFixed(1)+'x')+'</li>';
  apHtml+='<li>\u0625\u0630\u0627 \u0646\u0633\u0628\u0629 \u0627\u0644\u0646\u062C\u0627\u062D \u0646\u0632\u0644\u062A \u062A\u062D\u062A 40% \u2014 \u0642\u0644\u0651\u0644 \u062D\u062C\u0645 \u0627\u0644\u0635\u0641\u0642\u0627\u062A</li>';
  apHtml+='</ul></div>';

  document.getElementById('actionPanel').innerHTML=apHtml;
}

loadData();
setInterval(loadData,300000);
})();
</script>
</body>
</html>

```


================================================================================
# SECTION 3: SYSTEM SUMMARY
================================================================================


## Current Architecture:
- 128 KSE stocks monitored
- 30m + 1D timeframes
- Bridge API (TradingView WebSocket) provides live data: RSI, MACD, EMA 9/21/50/200, ATR, ADX, Stoch, BB, OBV, Volume
- VWAP calculated from OHLCV bars (not from Bridge)
- SCALPING_MODE = True (feature flag)
- Confluence: Volume + ADX + Stoch + VWAP (RSI/MACD/Golden removed)
- Exit: 3-bar timeout + EMA9 break + 1.5R target
- Stop: min(candle_low, EMA21, 0.5%)
- Commission: 0.125% per side = 0.25% round trip
- No short selling (LONG ONLY)

## Brain Database Stats (66,937 signals):
- Overall hit rate: 21.0%
- Volume ON: 23.7% hit | OFF: 19.4%
- ADX ON: 22.9% hit | OFF: 19.2%
- RSI ON: 19.7% hit | OFF: 25.8% (RSI HURTS!)
- MACD ON: 20.6% hit | OFF: 23.2% (MACD HURTS!)
- Best combo: VOL+ADX = 25.5% hit, 4.79% avg gain
- Volume sweet spot: 1-3x (NOT 3x+)
- ADX sweet spot: 25-40+ (stronger = better)
- RSI sweet spot: <50 (contrarian)
- Top stocks: INOVEST 41%, URC 38.6%, ACICO 38.2%
- Worst stocks: KFH 2.8%, GINS 4.5%, BOUBYAN 8.4%

## User's Problem:
The user is CONFUSED by the current system:
- Doesn't know if signals are 30m or Daily
- Doesn't know when to enter or exit
- System shows signals but user can't make decisions
- Previous Gemini review said: +0.03% expectancy = NOT PROFITABLE
- Gemini recommended: Daily trend filter + 30m entry timing + wider stops (2%) + bigger targets (4-6%)
