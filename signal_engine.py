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
from datetime import datetime, timedelta

logger = logging.getLogger("signal_engine")

# ═══════════════════════════════════════════════════
# Trading V2 — Feature Flags (Phase 8)
# All flags consolidated here. Toggle to switch modes.
# ═══════════════════════════════════════════════════
SWING_MODE = True           # True = daily swing logic (V2)
SCALPING_MODE = True        # True = 30m scalping logic (V1, runs alongside swing for 30m)
WHITELIST_MODE = False      # suspended 2026-08-15 (C-27): list basis is broken hit/miss
DAILY_TREND_FILTER = True   # True = block buys when daily trend DOWN/SIDEWAYS
SWING_CONFLUENCE = True     # True = VOL+ADX only, False = old RSI+MACD+all
MARKET_REGIME_FILTER = True  # True = block buys when KWSE index is bearish/choppy
LIQUIDITY_FILTER = True      # True = filter illiquid stocks / wide spread
RISK_ENGINE = True           # True = position sizing + portfolio heat
PRE_TRADE_CHECKLIST = True   # True = pre-trade checklist gate
PAPER_TRADING = True         # True = paper trading mode
EQUITY_TRACKER = True        # True = equity curve + drawdown tracking


def get_trading_flags() -> dict:
    """Return current feature flags for API responses."""
    return {
        "swing_mode": SWING_MODE,
        "scalping_mode": SCALPING_MODE,
        "whitelist_mode": WHITELIST_MODE,
        "daily_trend_filter": DAILY_TREND_FILTER,
        "swing_confluence": SWING_CONFLUENCE,
        "mode": "swing" if SWING_MODE else ("scalping" if SCALPING_MODE else "default"),
        "market_regime_filter": MARKET_REGIME_FILTER,
        "liquidity_filter": LIQUIDITY_FILTER,
        "risk_engine": RISK_ENGINE,
        "pre_trade_checklist": PRE_TRADE_CHECKLIST,
        "paper_trading": PAPER_TRADING,
        "equity_tracker": EQUITY_TRACKER,
    }


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



# ═══════════════════════════════════════════════════

# ═══════════════════════════════════════════════════

# ═══════════════════════════════════════════════════
# Trading V2 Phase 2: Pre-Trade Checklist (ITEM 6)
# ═══════════════════════════════════════════════════
def pre_trade_checklist(sig: dict, regime: dict, liquidity: dict) -> dict:
    """
    Run comprehensive pre-trade gate. ALL checks must pass for 'ادخل'.
    """
    # Try to get risk status (lazy import to avoid circular)
    risk_ok = True
    sector_ok = True
    positions_ok = True
    try:
        from risk_engine import check_can_open
        rc = check_can_open(sig.get("symbol", ""),
                           sig.get("price", 0), sig.get("swing_stop", 0))
        risk_ok = rc.get("can_open", True)
        sector_ok = rc.get("checks", {}).get("sector", {}).get("ok", True)
        positions_ok = rc.get("checks", {}).get("max_positions", {}).get("ok", True)
    except Exception:
        pass

    checks = [
        {"name": "market_regime", "label": "\u0627\u062a\u062c\u0627\u0647 \u0627\u0644\u0633\u0648\u0642",
         "passed": regime.get("allow_buy", True)},
        {"name": "daily_trend", "label": "\u0627\u062a\u062c\u0627\u0647 \u0627\u0644\u0633\u0647\u0645 (SMA20)",
         "passed": sig.get("daily_trend") == "UP"},
        {"name": "adx_valid", "label": "ADX > 25",
         "passed": (sig.get("adx") or 0) >= 25},
        {"name": "volume_valid", "label": "\u062d\u062c\u0645 1-3x",
         "passed": 1 <= (sig.get("vol_ratio") or 0) <= 3},
        {"name": "liquidity_ok", "label": "\u0633\u064a\u0648\u0644\u0629 \u0643\u0627\u0641\u064a\u0629",
         "passed": liquidity.get("passed", True)},
        {"name": "risk_ok", "label": "\u0645\u062e\u0627\u0637\u0631\u0629 \u0636\u0645\u0646 \u0627\u0644\u062d\u062f",
         "passed": risk_ok},
        {"name": "max_positions", "label": "\u0645\u0631\u0627\u0643\u0632 < \u0627\u0644\u062d\u062f",
         "passed": positions_ok},
        {"name": "sector_ok", "label": "\u0642\u0637\u0627\u0639 \u063a\u064a\u0631 \u0645\u0643\u0631\u0631",
         "passed": sector_ok},
        {"name": "rr_valid", "label": "R:R > 1.5",
         "passed": (sig.get("swing_rr") or 0) >= 1.5},
    ]
    all_passed = all(c["passed"] for c in checks)
    return {
        "all_passed": all_passed,
        "passed_count": sum(1 for c in checks if c["passed"]),
        "total_checks": len(checks),
        "checks": checks,
        "verdict": "\u0627\u062f\u062e\u0644" if all_passed else "\u0644\u0627 \u062a\u062f\u062e\u0644",
        "failed": [c["label"] for c in checks if not c["passed"]],
    }

# Trading V2 Phase 2: Liquidity & Spread Filter (KSE)
# ═══════════════════════════════════════════════════
MIN_AVG_DAILY_VALUE_KWD = 50000   # 20-day avg traded value
MIN_AVG_DAILY_VOLUME = 100000     # 20-day avg volume
MAX_SPREAD_PCT = 1.5              # max bid-ask spread %

def check_liquidity(symbol: str) -> dict:
    """Liquidity from the stored median census: liq_vol x snapshot price,
    against the risk_engine floor, with the per-position cap attached.

    Replaces a 20-session MEAN (the census proved block trades lie to a
    mean) that also compared fils x shares against a threshold labelled
    KWD - a 1000x unit slip that made the 50,000 threshold behave as 50.
    Store-only on purpose: this runs 132 times per scan, and a network
    price per symbol here would rebuild C-10. The risk_engine gate still
    prices actual entries live.
    """
    result = {"passed": True, "liq_value_kwd": None, "state": "missing",
              "as_of": None, "reasons": [],
              # legacy keys kept for shape compatibility; the mean is dead
              "avg_daily_volume": None, "avg_daily_value_kwd": None,
              "spread_pct": 0}
    try:
        from risk_engine import RiskEngine
        conn = _sqlite3.connect(_LIFE_DB, timeout=3)
        conn.row_factory = _sqlite3.Row
        row = conn.execute(
            "SELECT price, liq_vol, captured_at, updated_at"
            " FROM stock_radar_daily WHERE symbol=?",
            (symbol.upper(),)).fetchone()
        conn.close()
        if not row or row["price"] is None or row["liq_vol"] is None:
            result["reasons"].append("liquidity unknown - not gated")
            return result
        v = row["price"] * row["liq_vol"] / 1000.0
        result.update(liq_value_kwd=round(v, 1), state="stored",
                      as_of=str(row["captured_at"] or row["updated_at"]))
        if v < RiskEngine.LIQUIDITY_FLOOR_KWD:
            result["passed"] = False
            result["reasons"].append(
                "median session %d KWD < floor %d"
                % (v, RiskEngine.LIQUIDITY_FLOOR_KWD))
        else:
            result["max_position_kwd"] = round(
                v * RiskEngine.MAX_POSITION_LIQ_SHARE
                * RiskEngine.MAX_POSITION_EXIT_SESSIONS)
    except Exception as e:
        import logging
        logging.getLogger("signal_engine").debug(f"check_liquidity error for {symbol}: {e}")
    return result

# Trading V2 Phase 2: Market Regime Filter (KWSE Index)
# ═══════════════════════════════════════════════════
_regime_cache = {"data": None, "ts": 0}

def check_market_regime() -> dict:
    """
    Determine overall market regime from KWSE index.
    Uses SMA 50 + ADX from daily_bars (index row) or stock_radar_daily.
    Cached 15 min (doesn't change intraday).
    """
    import time as _t
    now = _t.time()
    if _regime_cache["data"] and (now - _regime_cache["ts"]) < 900:
        return _regime_cache["data"]

    result = {"regime": "UNKNOWN", "allow_buy": True, "reason": "insufficient data",
              "index_close": None, "index_sma50": None, "index_adx": None}
    try:
        import sqlite3 as _sq
        conn = _sq.connect("data/life.db", timeout=3)
        # Try daily_bars for KWSE index
        rows = conn.execute(
            "SELECT close FROM daily_bars WHERE symbol='KWSE' ORDER BY trading_date ASC"
        ).fetchall()
        if not rows or len(rows) < 50:
            # Fallback: compute regime from whitelist stock trends
            # trend holds Arabic labels, so trend='UP' matched nothing and
            # up_pct was 0 forever - a BEARISH regime manufactured from a
            # vocabulary mismatch. daily_ema_cross is bullish/bearish and is
            # refreshed by the daily_bars backfill.
            row = conn.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN daily_ema_cross='bullish' THEN 1 ELSE 0 END) as up_count,
                       AVG(adx) as avg_adx
                FROM stock_radar_daily
            """).fetchone()
            conn.close()
            if row and row[0] and row[0] > 0:
                total, up_count, avg_adx = row[0], row[1] or 0, row[2] or 0
                up_pct = (up_count / total) * 100
                if up_pct >= 60 and avg_adx >= 20:
                    regime, allow = "BULLISH", True
                elif up_pct >= 40:
                    regime, allow = "NEUTRAL", True
                elif up_pct < 40 and avg_adx >= 20:
                    regime, allow = "BEARISH", False
                else:
                    regime, allow = "CHOPPY", False
                result = {"regime": regime, "allow_buy": allow,
                          "index_close": None, "index_sma50": None,
                          "index_adx": round(avg_adx, 1),
                          "up_pct": round(up_pct, 1),
                          "reason": f"{up_pct:.0f}% stocks bullish (EMA9>EMA21), ADX={avg_adx:.0f}"}
            _regime_cache["data"] = result
            _regime_cache["ts"] = now
            return result

        closes = [r[0] for r in rows]
        sma50 = sum(closes[-50:]) / 50
        current = closes[-1]
        above_sma = current > sma50

        # Try to get ADX from bridge analysis or radar
        adx = 0
        try:
            row2 = conn.execute(
                "SELECT adx FROM stock_radar_daily WHERE symbol='KWSE' LIMIT 1"
            ).fetchone()
            if row2 and row2[0]:
                adx = row2[0]
        except Exception:
            pass
        conn.close()

        trending = adx > 20
        if above_sma and trending:
            regime, allow = "BULLISH", True
        elif above_sma and not trending:
            regime, allow = "NEUTRAL", True
        elif not above_sma and trending:
            regime, allow = "BEARISH", False
        else:
            regime, allow = "CHOPPY", False

        result = {"regime": regime, "allow_buy": allow,
                  "index_close": round(current, 2), "index_sma50": round(sma50, 2),
                  "index_adx": round(adx, 1),
                  "above_sma50": above_sma,
                  "reason": f"Index {'above' if above_sma else 'below'} SMA50, ADX={adx:.0f}"}
    except Exception as e:
        import logging
        logging.getLogger("signal_engine").warning(f"check_market_regime error: {e}")

    _regime_cache["data"] = result
    _regime_cache["ts"] = now
    return result


def _save_regime_snapshot(regime_data: dict):
    """Persist daily regime to DB for history."""
    try:
        import sqlite3 as _sq
        from datetime import datetime as _dt
        today = _dt.now().strftime("%Y-%m-%d")
        conn = _sq.connect("data/life.db", timeout=3)
        conn.execute("""INSERT OR REPLACE INTO market_regime
            (date, regime, allow_buy, index_close, index_sma50, index_adx)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (today, regime_data.get("regime"), 1 if regime_data.get("allow_buy") else 0,
             regime_data.get("index_close"), regime_data.get("index_sma50"),
             regime_data.get("index_adx")))
        conn.commit()
        conn.close()
    except Exception:
        pass


def _name_ar(symbol, trade=None) -> str:
    """The Arabic company name for a symbol.

    Both call sites used to ask the TRADE record for it. That works for an
    open position and cannot work for an opportunity, which has no trade -
    `(trade or {}).get("name_ar", "")` returned "" for all 18 of them, every
    time, by construction rather than by accident. Meanwhile tv_data.KSE_STOCKS
    has mapped all 132 symbols to their Arabic names the whole time, and
    dashboard_api has been using it two files away.

    Order: the trade's own name first, because a position may carry a name
    the map does not; the map second. Empty last, and empty on purpose - the
    card shows the symbol already, so repeating it as the company name would
    be noise dressed as data.
    """
    if trade:
        own = (trade.get("name_ar") or "").strip()
        if own:
            return own
    try:
        from tv_data import KSE_STOCKS
    except Exception:
        return ""
    return (KSE_STOCKS.get(str(symbol).upper()) or "").strip()


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
        # V2 feature flags (Phase 8)
        "flags": get_trading_flags(),
        "market_regime": check_market_regime(),
        # D-6: suspended list stays off the wire - a populated array
        # will be treated as authoritative by the next consumer (C-27)
        "whitelist": [],
        "whitelist_suspended_reason": "C-27: hit-rate basis was measured with broken evaluation windows",
    }

    # 1. Get open trades from journal
    open_trades = _get_open_trades_safe()
    open_syms = {t["symbol"].upper(): t for t in open_trades if t.get("symbol")}

    # 2. Get bridge multi-analysis (already cached, fast)
    bridge_data = _get_bridge_data_safe()
    result["bridge_online"] = bridge_data.get("bridge_online", False)
    result["bridge_cached_count"] = bridge_data.get("symbols_count", 0)
    bridge_symbols = bridge_data.get("symbols", {})
    # C-10 shape: the loop walks the stored snapshot (stock_radar_daily,
    # dated rows) and the hand-started bridge only enriches it. Before this,
    # a dashboard read produced zero signals whenever the bridge was off -
    # which is most of the time, by user decision.
    universe = _get_snapshot_symbols()
    universe.update(bridge_symbols)

    # 3. Get radar watchlist for discovery context
    radar_syms = _get_radar_watchlist_safe()

    # 4. Build signal for each bridge-enriched symbol
    signals = []
    _skipped_blacklist = 0
    for sym, bd in universe.items():
        sym_upper = sym.upper()

        # Phase 3: Whitelist/Blacklist filter
        if not should_trade(sym_upper):
            _skipped_blacklist += 1
            continue

        trade = open_syms.get(sym_upper)
        radar_entry = radar_syms.get(sym_upper)

        state = _assign_trade_state(sym_upper, bd, radar_entry, trade)
        if state is None:
            continue

        verdict_key = _compute_verdict(bd, state)
        verdict = _VERDICT_MAP.get(verdict_key, verdict_key)
        confluence = _extract_confluence(bd)

        # Phase 2: Daily trend filter
        daily_trend = get_daily_trend(sym_upper)
        if DAILY_TREND_FILTER and not daily_trend["allow_buy"] and state not in ("entered", "manage"):
            verdict_key = "avoid"
            verdict = _VERDICT_MAP.get("avoid", "avoid")

        # Phase 2 ITEM 3: Market regime filter
        regime = result.get("market_regime", {})
        if MARKET_REGIME_FILTER and not regime.get("allow_buy", True) and state not in ("entered", "manage"):
            verdict_key = "avoid"
            verdict = _VERDICT_MAP.get("avoid", "avoid")

        sig = {
            "symbol": sym_upper,
            "name_ar": _name_ar(sym_upper, trade),
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
            "timeframe": "1D",
            "valid_until": now.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%dT%H:%M:%S"),
            "daily_trend": daily_trend.get("trend", "UNKNOWN"),
            "daily_sma20": daily_trend.get("sma20", 0),
            "daily_trend_allow_buy": daily_trend.get("allow_buy", False),
            "source": bd.get("source", ""),
            "stale": bd.get("stale", False),
            "market_regime": regime.get("regime", "UNKNOWN"),
            "regime_allow_buy": regime.get("allow_buy", True),
            "liquidity": check_liquidity(sym_upper) if LIQUIDITY_FILTER else {"passed": True, "reasons": []},
            "sector": _get_stock_sector(sym_upper),
            "sector_ar": _get_sector_name_ar(_get_stock_sector(sym_upper)),
            "checklist": None,  # computed below after sig is built
        }

        # Phase 2 ITEM 6: Compute checklist now that sig is built
        if PRE_TRADE_CHECKLIST:
            sig["checklist"] = pre_trade_checklist(sig, regime, sig.get("liquidity", {}))

        # Phase 4: Pivots + ATR stops
        pivots = _get_pivots_for_symbol(sym_upper)
        sig["pivots"] = pivots
        price = sig["price"]
        atr = sig.get("atr_14") or 0
        if price and atr:
            stop_data = calculate_swing_stop(price, atr, sig.get("support"))
            target_data = calculate_swing_target(price, pivots, atr)
            sig["swing_stop"] = stop_data.get("stop_loss")
            sig["swing_stop_pct"] = stop_data.get("risk_pct")
            sig["swing_stop_type"] = stop_data.get("stop_type")
            sig["swing_target"] = target_data.get("target")
            sig["swing_target_pct"] = target_data.get("reward_pct")
            sig["swing_target_type"] = target_data.get("target_type")
            risk = stop_data.get("risk_pct", 0)
            reward = target_data.get("reward_pct", 0)
            sig["swing_rr"] = round(reward / risk, 2) if risk > 0 else 0

        # Phase 5: Swing confluence
        if SWING_MODE:
            sc = swing_confluence(sym_upper, sig, daily_trend)
            sig["swing_confluence_pct"] = sc["confluence_pct"]
            sig["swing_action"] = sc["action"]
            sig["swing_factors"] = sc["factors"]
            sig["swing_blockers"] = sc.get("blockers", [])
            sig["swing_reason"] = sc.get("reason")

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
    result["filtered_out"] = _skipped_blacklist

    # 8. Open positions with live P&L. current comes from the one price
    # path (bridge -> yahoo -> db); state says "manage" only when that price
    # is a live market price, so the old fallback - current silently set to
    # entry and dressed as a quote - cannot happen again.
    for sym, trade in open_syms.items():
        entry_price = trade.get("entry_price", 0)
        current_price, price_state, price_as_of = None, "missing", None
        if sym in bridge_symbols and bridge_symbols[sym].get("price"):
            current_price = bridge_symbols[sym]["price"]
            price_state, price_as_of = "live", None
        else:
            try:
                from journal_engine import get_fresh_price
                _q = get_fresh_price(sym)
                if _q.get("price"):
                    current_price = float(_q["price"])
                    price_state = _q.get("state")
                    price_as_of = _q.get("as_of")
            except Exception as _qe:
                logger.warning("open position price lookup failed for %s: %r", sym, _qe)
        if current_price is None:
            # no source anywhere: keep the old entry-as-current shape so the
            # row is not dropped, but the state says exactly what it is
            current_price = entry_price
        pnl_pct = ((current_price / entry_price) - 1) * 100 if entry_price else 0
        qty = trade.get("quantity", 0)
        pnl_kwd = ((current_price - entry_price) * qty) / 1000 if entry_price else 0

        state = "manage" if price_state == "live" else "entered"

        result["open_positions"].append({
            "symbol": sym,
            "name_ar": _name_ar(sym, trade),
            "entry": entry_price,
            "current": current_price,
            "pnl_pct": round(pnl_pct, 2),
            "pnl_kwd": round(pnl_kwd, 3),
            "state": state,
            "price_state": price_state,
            "price_as_of": price_as_of,
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

def _get_snapshot_symbols() -> dict:
    """bd-shaped entries from stock_radar_daily - the stored, dated snapshot.

    Only fields the snapshot really has are mapped; signals/confluence stay
    empty rather than fabricated, so a snapshot-only symbol can reach
    discovery/avoid but never a manufactured buy. Rows older than 3 days
    are flagged stale.
    """
    out = {}
    try:
        conn = _sqlite3.connect(_LIFE_DB, timeout=3)
        conn.row_factory = _sqlite3.Row
        rows = conn.execute(
            "SELECT symbol, price, change_pct, rsi, adx, atr, stoch_k,"
            " vol_ratio, support, resistance, macd_cross, daily_ema_cross,"
            " confluence_score, confluence_direction,"
            " captured_at, updated_at FROM stock_radar_daily").fetchall()
        conn.close()
    except Exception as e:
        logger.debug("snapshot universe unavailable: %r", e)
        return out
    from datetime import datetime as _dtu
    for r in rows:
        as_of = r["captured_at"] or r["updated_at"]
        age_days = None
        if as_of:
            try:
                d = _dtu.fromisoformat(str(as_of))
                if d.tzinfo:
                    d = d.replace(tzinfo=None)
                age_days = (_dtu.utcnow() - d).days
            except (ValueError, TypeError):
                pass
        out[str(r["symbol"]).upper()] = {
            "price": r["price"] or 0,
            "change_pct": r["change_pct"] or 0,
            "rsi_14": r["rsi"],
            "adx": r["adx"],
            "atr_14": r["atr"],
            "vol_ratio": r["vol_ratio"],
            "support": [r["support"]] if r["support"] else [],
            "resistance": [r["resistance"]] if r["resistance"] else [],
            "macd": {"state": r["macd_cross"] or ""},
            "ema": {"stack": r["daily_ema_cross"] or ""},
            "stoch_rsi": {"k": r["stoch_k"]},
            "bb": {},
            "signals": ({"confluence": {"score": r["confluence_score"],
                                        "direction": r["confluence_direction"] or "unknown"}}
                        if r["confluence_score"] is not None else {}),
            "source": "radar_daily",
            "stale": age_days is None or age_days > 3,
            "as_of": str(as_of) if as_of else None,
        }
    return out


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


# ═══════════════════════════════════════════════════
# Trading V2 — Phase 2: Daily Trend Filter (SMA 20)
# ═══════════════════════════════════════════════════

import os as _os
import sqlite3 as _sqlite3

_LIFE_DB = _os.path.join(_os.path.dirname(__file__), "data", "life.db")

# (DAILY_TREND_FILTER flag at top of file)


def get_daily_trend(symbol: str, sma_period: int = 20) -> dict:
    """
    Daily trend filter — only buy when price is above SMA 20.

    Data priority:
    1. daily_bars table (real OHLCV history, needs >= sma_period bars)
    2. Bridge EMA 21 as proxy (bridge_data from last fetch)
    3. stock_radar_daily EMA data as fallback

    Returns: trend (UP/DOWN/SIDEWAYS), sma20, price_vs_sma_pct, allow_buy
    """
    # --- Source 1: daily_bars table ---
    try:
        conn = _sqlite3.connect(_LIFE_DB, timeout=5)
        conn.row_factory = _sqlite3.Row
        rows = conn.execute(
            "SELECT close FROM daily_bars WHERE symbol=? ORDER BY trading_date ASC",
            (symbol.upper(),),
        ).fetchall()
        conn.close()
        closes = [float(r["close"]) for r in rows if r["close"]]
        if len(closes) >= sma_period:
            sma = sum(closes[-sma_period:]) / sma_period
            price = closes[-1]
            dist_pct = ((price - sma) / sma) * 100 if sma > 0 else 0
            return _trend_result(price, sma, dist_pct)
    except Exception as e:
        logger.debug("daily_bars lookup failed for %s: %s", symbol, e)

    # --- Source 2: stock_radar_daily (EMA 21 as proxy) ---
    try:
        conn = _sqlite3.connect(_LIFE_DB, timeout=5)
        conn.row_factory = _sqlite3.Row
        row = conn.execute(
            "SELECT price, daily_ema21 FROM stock_radar_daily WHERE symbol=? ORDER BY rowid DESC LIMIT 1",
            (symbol.upper(),),
        ).fetchone()
        conn.close()
        if row and row["price"] and row["daily_ema21"]:
            price = float(row["price"])
            ema21 = float(row["daily_ema21"])
            if ema21 > 0:
                dist_pct = ((price - ema21) / ema21) * 100
                return _trend_result(price, ema21, dist_pct)
    except Exception as e:
        logger.debug("radar_daily trend lookup failed for %s: %s", symbol, e)

    return {"trend": "UNKNOWN", "sma20": 0, "price_vs_sma_pct": 0, "allow_buy": False}


def _trend_result(price: float, sma: float, dist_pct: float) -> dict:
    """Classify trend from price vs SMA distance."""
    if dist_pct > 0.5:
        trend, allow = "UP", True
    elif dist_pct < -0.5:
        trend, allow = "DOWN", False
    else:
        trend, allow = "SIDEWAYS", False
    return {
        "trend": trend,
        "sma20": round(sma, 3),
        "price_vs_sma_pct": round(dist_pct, 2),
        "allow_buy": allow,
    }


# ═══════════════════════════════════════════════════
# Trading V2 — Phase 3: Whitelist / Blacklist
# ═══════════════════════════════════════════════════

# (WHITELIST_MODE flag at top of file)

# Top 10 by hit rate from Brain analysis (66,937 signals)
WHITELIST = {
    "INOVEST",    # 41.2% hit, avg gain 3.9%
    "URC",        # 38.6% hit, avg gain 3.54%
    "ACICO",      # 38.2% hit, avg gain 6.53%
    "AAYANRE",    # 36.5% hit, avg gain 2.88%
    "OOREDOO",    # 36.2% hit, avg gain 3.10%
    "ALFTAQA",    # 35.9% hit, avg gain 3.18%
    "NINV",       # 35.6% hit, avg gain 2.05%
    "MUBARRAD",   # 33.6% hit, avg gain 2.76%
    "NRE",        # 33.5% hit, avg gain 1.96%
    "RASIYAT",    # 32.2% hit, avg gain 2.09%
}

# Bottom 10 by hit rate — almost guaranteed losers
BLACKLIST = {
    "KFH",          # 2.8% hit
    "GINS",         # 4.5% hit, avg loss 12.86%!
    "KHOT",         # 5.2% hit
    "MUNTAZAHAT",   # 5.8% hit
    "PCEM",         # 6.4% hit
    "INJAZZAT",     # 6.9% hit
    "BOUBYAN",      # 8.4% hit
    "TAHSSILAT",    # 8.6% hit
    "GBK",          # 9.0% hit
    "PAPER",        # 9.4% hit
}



# Sector helpers (ITEM 7)
_STOCK_SECTORS = {
    "INOVEST": "financial_services", "URC": "industrial", "ACICO": "industrial",
    "AAYANRE": "real_estate", "OOREDOO": "telecom", "ALFTAQA": "financial_services",
    "NINV": "financial_services", "MUBARRAD": "industrial",
    "NRE": "real_estate", "RASIYAT": "real_estate",
}
_SECTOR_AR = {
    "financial_services": "\u062e\u062f\u0645\u0627\u062a \u0645\u0627\u0644\u064a\u0629",
    "industrial": "\u0635\u0646\u0627\u0639\u064a", "real_estate": "\u0639\u0642\u0627\u0631\u064a",
    "telecom": "\u0627\u062a\u0635\u0627\u0644\u0627\u062a", "unknown": "\u063a\u064a\u0631 \u0645\u062d\u062f\u062f",
}

def _get_stock_sector(symbol: str) -> str:
    return _STOCK_SECTORS.get(symbol.upper(), "unknown")

def _get_sector_name_ar(sector: str) -> str:
    return _SECTOR_AR.get(sector, sector)

def should_trade(symbol: str) -> bool:
    """Both lists suspended 2026-08-15, by user decision (Section C, C-27):
    their hit rates were computed with the evaluation windows fixed only
    yesterday - KFH sat blacklisted at 2.8 percent while being among the
    most liquid names, and the one profitable open position was on neither
    list. Liquidity is the filter now: the risk_engine floor and the
    per-position cap. The lists stay defined below for the record and for
    C-27 to re-derive from re-evaluated outcomes.
    """
    return True


# ═══════════════════════════════════════════════════
# Trading V2 — Phase 4: ATR Stops + Daily Pivots
# ═══════════════════════════════════════════════════

def calculate_daily_pivots(prev_high: float, prev_low: float,
                           prev_close: float) -> dict:
    """Standard Daily Pivot Points from yesterday's OHLC."""
    if not prev_high or not prev_low or not prev_close:
        return {"pp": 0, "s1": 0, "s2": 0, "r1": 0, "r2": 0}
    pp = (prev_high + prev_low + prev_close) / 3
    return {
        "pp": round(pp, 3),
        "s1": round((2 * pp) - prev_high, 3),
        "s2": round(pp - (prev_high - prev_low), 3),
        "r1": round((2 * pp) - prev_low, 3),
        "r2": round(pp + (prev_high - prev_low), 3),
    }


def calculate_swing_stop(entry_price: float, atr_14: float,
                         support_level: float = None) -> dict:
    """
    Swing Trading stop — ATR-based with support awareness.
    Priority: support - 1×ATR > 2×ATR below entry > 3% max.
    """
    if not entry_price or entry_price <= 0 or not atr_14 or atr_14 <= 0:
        return {"stop_loss": 0, "risk_pct": 0, "stop_type": "error", "atr_14": 0}

    atr_stop = entry_price - (2.0 * atr_14)
    sr_stop = (support_level - (1.0 * atr_14)) if support_level and 0 < support_level < entry_price else atr_stop
    max_stop = entry_price * 0.97  # 3% max protection

    stop = max(min(atr_stop, sr_stop), max_stop)
    risk_pct = abs(entry_price - stop) / entry_price * 100

    if stop == sr_stop and sr_stop != atr_stop:
        stype = "support_atr"
    elif stop == max_stop and max_stop > atr_stop:
        stype = "max_3pct"
    else:
        stype = "atr_2x"

    return {
        "stop_loss": round(stop, 3),
        "risk_pct": round(risk_pct, 2),
        "stop_type": stype,
        "atr_14": round(atr_14, 4),
    }


def calculate_swing_target(entry_price: float, daily_levels: dict,
                           atr_14: float) -> dict:
    """Dynamic target at nearest resistance above entry."""
    if not entry_price or entry_price <= 0:
        return {"target": 0, "reward_pct": 0, "target_type": "error"}

    # Find nearest resistance above entry (+0.5% minimum)
    resistance = []
    for key in ("r1", "pdh", "pp", "r2"):
        val = daily_levels.get(key, 0)
        if val and val > entry_price * 1.005:
            resistance.append((key, val))
    resistance.sort(key=lambda x: x[1])

    if resistance:
        t_key, t_price = resistance[0]
    else:
        t_price = entry_price + (3.0 * (atr_14 or entry_price * 0.01))
        t_key = "atr_3x"

    reward_pct = (t_price - entry_price) / entry_price * 100 if entry_price > 0 else 0
    return {
        "target": round(t_price, 3),
        "reward_pct": round(reward_pct, 2),
        "target_type": t_key,
    }


def _get_pivots_for_symbol(symbol: str) -> dict:
    """Load yesterday's OHLC from daily_bars and compute pivots."""
    try:
        conn = _sqlite3.connect(_LIFE_DB, timeout=5)
        conn.row_factory = _sqlite3.Row
        rows = conn.execute(
            "SELECT high, low, close FROM daily_bars WHERE symbol=? ORDER BY trading_date DESC LIMIT 2",
            (symbol.upper(),),
        ).fetchall()
        conn.close()
        if len(rows) >= 2:
            prev = rows[1]  # yesterday (rows[0] is today)
            return calculate_daily_pivots(
                float(prev["high"]), float(prev["low"]), float(prev["close"]))
    except Exception as e:
        logger.debug("Pivots lookup failed for %s: %s", symbol, e)
    return {"pp": 0, "s1": 0, "s2": 0, "r1": 0, "r2": 0}


# ═══════════════════════════════════════════════════
# Trading V2 — Phase 5: Swing Confluence (simplified)
# ═══════════════════════════════════════════════════

# (SWING_MODE flag at top of file)


def swing_confluence(symbol: str, sig: dict, daily_trend: dict) -> dict:
    """
    Simplified confluence for Swing Trading.
    Uses ONLY: Daily Trend + Volume + ADX + RSI filter + near-support bonus.
    RSI/MACD/Stoch/EMA crossovers EXCLUDED (low hit rates from Brain data).
    """
    score = 0
    factors = []
    blockers = []

    # 1. Daily Trend (mandatory)
    trend = daily_trend.get("trend", "UNKNOWN")
    if trend != "UP":
        return {
            "confluence_pct": 0, "action": "NO_ENTRY",
            "reason": f"Daily trend = {trend}",
            "factors": [], "blockers": [f"TREND:{trend}"],
        }
    score += 30
    factors.append("TREND:UP")

    # 2. Volume 1-3x (mandatory range from Brain data)
    vol = sig.get("vol_ratio") or 0
    if 1.0 <= vol <= 3.0:
        score += 25
        factors.append(f"VOL:{vol:.1f}x")
    elif vol > 3.0:
        score += 15  # high volume is OK but less predictable
        factors.append(f"VOL:{vol:.1f}x(high)")
    else:
        blockers.append(f"VOL:{vol:.1f}x(low)")

    # 3. ADX >= 25 (mandatory)
    adx = sig.get("adx") or 0
    if adx >= 25:
        score += 25
        factors.append(f"ADX:{adx:.0f}")
        if adx >= 40:
            score += 5
            factors.append("ADX:STRONG")
    else:
        blockers.append(f"ADX:{adx:.0f}(<25)")

    # 4. RSI < 50 filter (not as a signal — just avoid overbought).
    # `or 50` sent an unmeasured stock down the else-branch and posted a
    # fabricated "RSI:50(>50)" blocker against it. None propagates now:
    # no score either way, and the gap is stated as itself.
    rsi = sig.get("rsi_14")
    rsi_measured = rsi is not None
    if not rsi_measured:
        blockers.append("RSI:unmeasured")
    elif rsi < 30:
        score += 15
        factors.append(f"RSI:{rsi:.0f}(oversold)")
    elif rsi < 50:
        score += 10
        factors.append(f"RSI:{rsi:.0f}(<50)")
    else:
        blockers.append(f"RSI:{rsi:.0f}(>50)")

    # 5. Near support bonus
    support = sig.get("support") or 0
    price = sig.get("price") or 0
    atr = sig.get("atr_14") or 0
    if support and price and atr and (price - support) < atr:
        score += 10
        factors.append("NEAR_SUPPORT")

    # Decision
    if blockers and score < 55:
        action = "NO_ENTRY"
        reason = " + ".join(blockers)
    elif score >= 80:
        action = "STRONG_BUY"
        reason = "All conditions met"
    elif score >= 60:
        action = "BUY"
        reason = "Core conditions met"
    elif score >= 40:
        action = "WATCH"
        reason = "Partial match"
    else:
        action = "NO_ENTRY"
        reason = " + ".join(blockers) if blockers else "Score too low"

    return {
        "confluence_pct": min(score, 100),
        "action": action,
        "reason": reason,
        "factors": factors,
        "blockers": blockers,
    }


# --- Phase 3: Scalping Mode ---
# (SCALPING_MODE flag at top of file)

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
    # Snapshot entries carry the declared-weight score computed at the
    # 14:00 run. The brain's learned weights never touch them - their
    # training basis is the suspect hit/miss sample (C-27).
    if bridge.get("source") == "radar_daily":
        conf = (bridge.get("signals") or {}).get("confluence")
        if isinstance(conf, dict) and conf.get("score") is not None:
            return conf
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
    """RETIRED 2026-08-16 (G-4). Returns the empty shape without touching the
    network. Kept as a function because six call sites read its contract;
    deleting it would be a contract break, and the snapshot universe
    (C-10 shape) is the real source now.
    """
    return {"bridge_online": False, "bridge_status": "retired",
            "symbols_count": 0, "symbols": {}}


def _get_bridge_data_safe_retired_impl() -> dict:
    """Get bridge multi-analysis for candidate symbols (5-min module-level cache).
    Fire-and-forget: triggers background fetch, always returns stale immediately."""
    global _bridge_cache, _bridge_cache_ts
    now = _time.time()
    if _bridge_cache.get("daily") and (now - _bridge_cache_ts.get("daily", 0)) < _BRIDGE_DAILY_TTL:
        return _bridge_cache["daily"]
    # The bridge is started by hand. If its breaker is already open there is
    # nothing to gain from fanning out 128 symbols that will each be refused;
    # back off and serve what we have.
    try:
        from bridge_client import circuit_stats
        if any(c.get("open") for c in circuit_stats().values()):
            return _bridge_cache.get("daily") or {"bridge_online": False, "symbols_count": 0, "symbols": {}}
    except Exception as _e:
        logger.debug("circuit check unavailable (%r) - continuing", _e)
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
            # stamp on failure as well: without this the timestamp stays 0,
            # the TTL test never passes, and every sensor poll starts another
            # full fan-out
            _bridge_cache_ts["daily"] = _time.time()
            logger.warning("Bridge daily fetch failed: %r", e)
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
    # The bridge is started by hand. If its breaker is already open there is
    # nothing to gain from fanning out 128 symbols that will each be refused;
    # back off and serve what we have.
    try:
        from bridge_client import circuit_stats
        if any(c.get("open") for c in circuit_stats().values()):
            return _bridge_cache.get("30m") or {"bridge_online": False, "symbols_count": 0, "symbols": {}}
    except Exception as _e:
        logger.debug("circuit check unavailable (%r) - continuing", _e)
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
            # stamp on failure too - see the daily twin above
            _bridge_cache_ts["30m"] = _time.time()
            logger.warning("Bridge 30m fetch failed: %r", e)
        finally:
            _bridge_30m_lock.release()

    _thr.Thread(target=_fetch_background, daemon=True).start()
    return _bridge_cache.get("30m") or {"bridge_online": False, "symbols_count": 0, "symbols": {}}


def build_signals_30m() -> dict:
    """30m signals. The Bridge supplied this layer; it is retired (G-4).

    The layer is NOT dead - G-1 measured Yahoo serving 30m for .KW: 41
    bars over 5 sessions, tier-1 names 100% populated, thin names 65-93%.
    So it is rebuildable locally through yahoo_gate + indicators.py, and
    the coverage floor already knows what to do with the thin ones.

    Until that is built, this returns an EMPTY list with layer_state and
    layer_reason saying why. The one thing it must never do is let a
    caller quietly substitute daily data - that relabelling is the exact
    disease this phase removed everywhere else.
    """
    now = datetime.now()
    result = {
        "timeframe": "30m",
        "market_open": _is_market_open_safe(),
        "bridge_online": False,
        "layer_state": "offline",
        "layer_reason": ("the 30m layer was fed by the TradingView bridge, "
                         "retired 2026-08-16. Yahoo does serve 30m for .KW "
                         "(G-1), so this is rebuildable locally - it is not "
                         "dead data, it is unbuilt. Do NOT substitute daily "
                         "signals here."),
        "layer_rebuildable": True,
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "signals": [],
        "thresholds": _get_thresholds(),
        "flags": get_trading_flags(),
    }
    return result


def _build_signals_30m_bridge_era() -> dict:
    now = datetime.now()
    result = {
        "timeframe": "30m",
        "market_open": _is_market_open_safe(),
        "bridge_online": False,
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "signals": [],
        "thresholds": _get_thresholds(),
        "flags": get_trading_flags(),
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
            "valid_until": (now + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S"),
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
