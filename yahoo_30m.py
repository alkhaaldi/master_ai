"""30m layer rebuilt on Yahoo, replacing the retired TradingView bridge.

The bridge was retired 2026-08-16 and build_signals_30m has returned an
empty list with layer_state='offline' ever since. G-1 measured Yahoo serving
30m for .KW, so the layer was never dead data - it was unbuilt. This module
builds it.

Two hard rules carried over from the note the retirement left behind:

  * Daily data is NEVER substituted for a missing 30m reading. A symbol with
    no usable 30m bars is dropped with a reason, not relabelled.
  * Absence produces a reason, not a number - the same contract indicators.py
    keeps, so a hole in the grid stays visible instead of scoring as zero.

Reads are cache-only. yahoo_gate throttles to one request every 2s, and the
watchlist is 132 symbols, so fetching inside a request would make
/dashboard/signals-30m take four minutes. _tools/collect_30m.py does the
fetching on cron; this module only reads what that left behind.
"""
import logging
import time

logger = logging.getLogger("yahoo_30m")

# One 30m bar per half hour; a bar older than this is from a previous cycle.
DEFAULT_MAX_AGE_S = 2400  # 40 minutes

# After the close the newest 30m bar that can exist is the closing one, so a
# session-length freshness window would blank the layer every evening and
# call it "stale" when nothing is actually wrong. Overnight the last session
# stays readable; `stale` on each row still says the bar is not live.
CLOSED_MAX_AGE_S = 20 * 3600

# Volume ratio needs a baseline; below this many bars there is no baseline.
_VOL_BASELINE_BARS = 20


def _vol_ratio(bars):
    """Last bar's volume against the mean of the prior _VOL_BASELINE_BARS.

    Returns None rather than 1.0 when there is no baseline: 1.0 is a real
    reading ("volume is exactly average") and would cast a vote in
    get_adjusted_confluence, so inventing it would put an invented vote in
    the score.
    """
    vols = [b.get("volume") for b in bars if b.get("volume") is not None]
    if len(vols) < _VOL_BASELINE_BARS + 1:
        return None
    baseline = sum(vols[-(_VOL_BASELINE_BARS + 1):-1]) / float(_VOL_BASELINE_BARS)
    if baseline <= 0:
        return None
    return round(vols[-1] / baseline, 3)


def _radar_prices(db_path="data/life.db"):
    """{SYMBOL: price} from stock_radar_daily, in one query.

    One read for the whole watchlist instead of a per-symbol lookup, so the
    price stays the platform's single number without costing a round trip
    each time.
    """
    import sqlite3
    try:
        c = sqlite3.connect(db_path, timeout=5)
        try:
            rows = c.execute(
                "SELECT symbol, price FROM stock_radar_daily "
                "WHERE price IS NOT NULL AND price > 0").fetchall()
        finally:
            c.close()
        return {r[0].upper(): r[1] for r in rows}
    except Exception as e:
        logger.debug("radar price map unavailable: %r", e)
        return {}


def symbol_data(symbol, max_age_s=DEFAULT_MAX_AGE_S, now_utc_ts=None,
                price_hint=None):
    """Bridge-shaped 30m payload for one symbol, or (None, reason).

    The returned dict carries each reading twice on purpose. Scoring reads
    flat keys (get_adjusted_confluence wants rsi_14 / macd_state / ema_state
    / adx / vol_ratio / stoch_k); the signal row reads nested ones
    (bd['ema']['stack'], bd['macd']['state'], bd['signals'][...]). The bridge
    payload carried both, so both are reproduced here rather than editing
    every reader.
    """
    import yahoo_gate
    import indicators as _I

    symbol = symbol.upper().strip()
    if now_utc_ts is None:
        now_utc_ts = int(time.time())

    try:
        bars = yahoo_gate.cached_bars(symbol, "30m", max_age_s)
    except Exception as e:
        return None, "cache read failed: %r" % (e,)
    if not bars:
        return None, "no 30m bars in cache newer than %ds" % max_age_s

    ind = _I.compute_all(bars, "30m", now_utc_ts)

    # Everything bar-derived below uses COMPLETE bars only - the same set
    # compute_all scores. The forming bar carries volume 0 and an off-grid
    # stamp, so mixing it in produced vol_ratio 0.0 on every symbol: a
    # real-looking reading ("no volume traded") standing in for "not a bar
    # yet", and it votes in get_adjusted_confluence either way.
    complete, _dropped, _drop_reason = _I.drop_incomplete(bars, "30m", now_utc_ts)
    if not complete:
        return None, "every 30m bar is still forming: %s" % (_drop_reason or "",)

    closes = [b.get("close") for b in complete if b.get("close") is not None]
    if not closes:
        return None, "30m bars present but every close is null"

    last_close = closes[-1]
    prev = closes[-2] if len(closes) > 1 else None
    change_pct = round((last_close - prev) / prev * 100, 4) if prev else 0.0

    # Price is the one stock_radar_daily already carries - the same number
    # radar and positions render, maintained by intraday_refresh every 15
    # minutes in session. price_source.get_price() would be the more direct
    # door but it fetches: measured 7-9s per symbol, so 132 symbols is ~20
    # minutes inside an HTTP handler. Reading the materialised row keeps one
    # price per symbol across the platform without paying for it per call.
    if price_hint is not None:
        price, price_src = price_hint, "stock_radar_daily"
    else:
        price, price_src = last_close, "30m_close"

    stamps = [b.get("ts") for b in complete if b.get("ts")]
    bar_age_s = (now_utc_ts - max(stamps)) if stamps else None
    is_stale = bar_age_s is None or bar_age_s > DEFAULT_MAX_AGE_S

    def val(key):
        return (ind.get(key) or {}).get("value")

    rsi_v = val("rsi")
    macd_v = val("macd") or {}
    ema9 = val("ema_9")
    ema21 = val("ema_21")
    adx_v = val("adx")
    stoch_v = val("stoch_k")
    atr_v = val("atr")
    sr_v = val("sr") or {}
    div_v = val("rsi_divergence")

    if ema9 is not None and ema21 is not None:
        ema_state = "bullish" if ema9 > ema21 else "bearish" if ema9 < ema21 else "flat"
    else:
        ema_state = ""

    macd_state = macd_v.get("cross", "") if macd_v else ""
    hist = macd_v.get("histogram") if macd_v else None
    macd_momentum = ("rising" if hist > 0 else "falling") if hist is not None else ""

    vr = _vol_ratio(complete)

    bd = {
        # --- flat: what get_adjusted_confluence votes on ---
        "rsi_14": rsi_v,
        "macd_state": macd_state,
        "ema_state": ema_state,
        "adx": adx_v,
        "vol_ratio": vr,
        "stoch_k": stoch_v,
        # --- shared ---
        "price": price,
        "price_source": price_src,
        "close_30m": last_close,
        "change_pct": change_pct,
        "atr_14": atr_v,
        "source": "yahoo_30m",
        "stale": is_stale,
        "bar_age_s": bar_age_s,
        # --- nested: what the signal row renders ---
        "ema": {"stack": ema_state, "ema9": ema9, "ema21": ema21},
        "macd": {"state": macd_state,
                 "histogram": hist,
                 "above_zero": macd_v.get("above_zero") if macd_v else None},
        "signals": {"macd_momentum": macd_momentum,
                    "rsi_divergence": div_v,
                    "ema_cross": macd_v.get("cross") if macd_v else None},
        "support": [sr_v.get("support")] if sr_v.get("support") is not None else [],
        "resistance": [sr_v.get("resistance")] if sr_v.get("resistance") is not None else [],
        # bb (Bollinger squeeze) and stoch %D have no indicators.py
        # implementation. They stay absent rather than being faked - the
        # signal row already treats a missing key as unknown.
        "bb": {},
        "stoch_rsi": {"k": stoch_v, "d": None},
        # --- evidence, so a thin symbol can be told from a rich one ---
        "coverage_pct": ind.get("coverage_pct"),
        "bars_complete": ind.get("bars_complete"),
        "bars_used": len(bars),
        "indicator_reasons": {k: (ind.get(k) or {}).get("reason")
                              for k in ("rsi", "macd", "ema_9", "ema_21", "adx",
                                        "stoch_k", "atr", "sr")
                              if (ind.get(k) or {}).get("reason")},
    }
    return bd, None


def collect(symbols, max_age_s=None, market_open=False):
    """Bridge-data-shaped dict over many symbols, cache-only.

    Shape matches _get_bridge_data_30m_safe so the existing 30m signal
    builder can consume it unchanged. The freshness window follows the
    session: tight while the market is open, overnight-wide once it closes.
    """
    if max_age_s is None:
        max_age_s = DEFAULT_MAX_AGE_S if market_open else CLOSED_MAX_AGE_S
    now_utc_ts = int(time.time())
    prices = _radar_prices()
    out = {}
    skipped = {}
    for sym in symbols:
        try:
            bd, reason = symbol_data(sym, max_age_s=max_age_s,
                                     now_utc_ts=now_utc_ts,
                                     price_hint=prices.get(sym.upper()))
        except Exception as e:
            logger.debug("30m build failed for %s: %r", sym, e)
            skipped[sym.upper()] = "build failed: %r" % (e,)
            continue
        if bd is None:
            skipped[sym.upper()] = reason
            continue
        out[sym.upper()] = bd

    return {
        "bridge_online": False,
        "source": "yahoo",
        "symbols_count": len(out),
        "symbols": out,
        "skipped": skipped,
        "skipped_count": len(skipped),
        "max_age_s": max_age_s,
    }
