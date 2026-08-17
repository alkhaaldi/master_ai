"""Indicators computed locally from OHLCV bars. Pure - no network, no DB.

G-2. Every value returned carries the evidence it was computed from:

    {"value": x|None, "bars_used": n, "coverage_pct": p,
     "params": "...", "reason": str|None}

Three rules this module exists to enforce, all of them scars:

1. **Never compute on a forming bar.** `drop_incomplete()` removes any bar
   that is not provably closed. A close that can still move is not a close,
   and an indicator built on it changes retroactively.
2. **Never compute on a holed grid.** A thin name whose 30m series is 66%
   null does not get an RSI - it gets None and a reason. A number computed
   over a grid with holes is a confident answer to a question the data
   cannot support (G-1 measured 27/41 non-null for URC).
3. **Never substitute a neutral default.** Insufficient bars -> None. No
   `rsi or 50` (F-3, and the inventory ratchet in quick_check).

Parameters are stated in the return so that a value computed with RSI 14
is never silently compared against one computed with RSI 9, and so the
2026-08-16 local/bridge seam stays visible (SCALES.md).
"""
from __future__ import annotations

# KSE: Sun-Thu, 09:00-13:00 Asia/Kuwait (+3, no DST) = 06:00-10:00 UTC
KSE_OPEN_UTC_H = 6
KSE_CLOSE_UTC_H = 10
KSE_TRADING_WEEKDAYS = (6, 0, 1, 2, 3)      # datetime.weekday(): Sun-Thu

# Default coverage floor. Below this share of non-null closes in the window
# an indicator is refused rather than approximated.
MIN_COVERAGE_PCT = 80.0

RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
ATR_PERIOD = 14
ADX_PERIOD = 14
STOCH_PERIOD = 14
SR_LOOKBACK = 20
# RSI divergence: how far back to look for the two pivots, and how many bars
# must sit either side of a turn before it counts as one. Two bars is the
# smallest window that rejects single-bar noise without smoothing away a
# real two-day turn on a market this thin.
RSI_DIV_LOOKBACK = 30
RSI_DIV_PIVOT = 2

INTERVAL_SECONDS = {"30m": 1800, "60m": 3600, "1h": 3600, "1d": 86400}


# ───────────────────────────── bar hygiene ─────────────────────────────

def is_bar_complete(ts, interval, now_utc_ts):
    """Is the bar starting at epoch `ts` provably closed?

    Two independent tests, both must pass:

    - **on the grid**: an intraday bar start is a multiple of its own
      interval. G-1 measured Yahoo's newest 30m stamp at 09:45Z, which is
      NOT on the 30m grid - that element is the forming bar carrying a
      last-update time, not a bar open. Off-grid means forming.
    - **elapsed**: the bar's window has ended in wall-clock terms.

    Daily bars are stamped at the session open (06:00Z, measured in G-1),
    so a daily bar is complete once that session's close has passed.
    """
    step = INTERVAL_SECONDS.get(interval)
    if step is None:
        return False, "unknown interval %r" % interval
    if interval == "1d":
        # complete once the 10:00Z close of its own session has passed
        close_ts = ts - (ts % 86400) + KSE_CLOSE_UTC_H * 3600
        if ts % 3600 != 0:
            return False, "daily stamp off the hour grid"
        return (now_utc_ts >= close_ts,
                None if now_utc_ts >= close_ts else "session still open")
    if ts % step != 0:
        return False, "off-grid stamp (forming bar)"
    if now_utc_ts < ts + step:
        return False, "bar window has not elapsed"
    return True, None


def drop_incomplete(bars, interval, now_utc_ts):
    """Return (complete_bars, dropped_count, reason_of_last_dropped).

    `bars` is a list of dicts with at least `ts` (epoch seconds) and
    `close`. Only trailing bars are examined: a hole in the middle is a
    no-trade window, which is market information, not an unfinished bar.
    """
    if not bars:
        return [], 0, "no bars"
    out = list(bars)
    dropped, reason = 0, None
    while out:
        ok, why = is_bar_complete(out[-1].get("ts"), interval, now_utc_ts)
        if ok:
            break
        out.pop()
        dropped += 1
        reason = why
    return out, dropped, reason


def _closes(bars):
    return [b.get("close") for b in bars]


def coverage(bars):
    """(non_null, total, pct) over the given bars."""
    total = len(bars)
    if not total:
        return 0, 0, 0.0
    nn = sum(1 for b in bars if b.get("close") is not None)
    return nn, total, round(100.0 * nn / total, 1)


def _result(value, bars_used, cov_pct, params, reason=None):
    return {"value": value, "bars_used": bars_used, "coverage_pct": cov_pct,
            "params": params, "reason": reason}


def _prepare(bars, need, params, min_coverage):
    """Shared gate: enough bars AND enough coverage, or None + reason."""
    nn, total, pct = coverage(bars)
    if total < need:
        return None, _result(None, total, pct, params,
                             "need %d bars, have %d" % (need, total))
    if pct < min_coverage:
        return None, _result(None, nn, pct, params,
                             "coverage %.1f%% below the %.1f%% floor - the "
                             "grid has holes, so no value is computed"
                             % (pct, min_coverage))
    series = [c for c in _closes(bars) if c is not None]
    if len(series) < need:
        return None, _result(None, len(series), pct, params,
                             "need %d non-null closes, have %d"
                             % (need, len(series)))
    return series, None


# ───────────────────────────── indicators ──────────────────────────────

def rsi(bars, period=RSI_PERIOD, min_coverage=MIN_COVERAGE_PCT):
    """Wilder RSI. Scale 0-100, continuous. 50 is a real reading."""
    params = "RSI %d (Wilder)" % period
    series, bad = _prepare(bars, period + 1, params, min_coverage)
    if bad:
        return bad
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = series[i] - series[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    ag, al = gains / period, losses / period
    for i in range(period + 1, len(series)):
        d = series[i] - series[i - 1]
        ag = (ag * (period - 1) + max(d, 0.0)) / period
        al = (al * (period - 1) + max(-d, 0.0)) / period
    _, _, pct = coverage(bars)
    if al == 0:
        return _result(100.0 if ag > 0 else 50.0, len(series), pct, params)
    return _result(round(100 - 100 / (1 + ag / al), 4), len(series), pct, params)


def _rsi_series(series, period):
    """Wilder RSI at every index from `period` on. Same recursion as rsi(),
    exposed as a series because divergence is a question about the past:
    the last value alone cannot say whether momentum is falling while price
    rises. Returns a list aligned to `series`, with None before warm-up."""
    out = [None] * len(series)
    if len(series) < period + 1:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = series[i] - series[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    ag, al = gains / period, losses / period
    out[period] = 100.0 if al == 0 and ag > 0 else (
        50.0 if al == 0 else round(100 - 100 / (1 + ag / al), 4))
    for i in range(period + 1, len(series)):
        d = series[i] - series[i - 1]
        ag = (ag * (period - 1) + max(d, 0.0)) / period
        al = (al * (period - 1) + max(-d, 0.0)) / period
        out[i] = 100.0 if al == 0 and ag > 0 else (
            50.0 if al == 0 else round(100 - 100 / (1 + ag / al), 4))
    return out


def _pivots(values, width, kind):
    """Indices of local extremes with `width` bars either side.

    kind='low' finds troughs, 'high' finds peaks. Strict on one side and
    non-strict on the other so a flat shoulder does not erase a real turn -
    common on a thin market where a price sits unchanged for a session.
    """
    out = []
    for i in range(width, len(values) - width):
        v = values[i]
        if v is None:
            continue
        window = values[i - width:i + width + 1]
        if any(w is None for w in window):
            continue
        if kind == "low" and v <= min(window) and v < max(window):
            out.append(i)
        elif kind == "high" and v >= max(window) and v > min(window):
            out.append(i)
    return out


def rsi_divergence(bars, period=RSI_PERIOD, lookback=RSI_DIV_LOOKBACK,
                   pivot=RSI_DIV_PIVOT, min_coverage=MIN_COVERAGE_PCT):
    """'bullish' | 'bearish' | 'none' - or None with a reason.

    Bullish: price makes a LOWER low while RSI makes a HIGHER low - selling
    continues but with less force behind it. Bearish is the mirror: a higher
    high in price on a lower high in RSI.

    'none' and None are different answers and must stay different. 'none'
    means two pivots were found and compared and they did not diverge - a
    measurement. None means the question could not be asked: too few bars,
    too many holes, or no second pivot inside the window. The writer this
    replaced collapsed the two, storing NULL for both, so a checked symbol
    and an unexaminable one were indistinguishable in the table.

    Moved here 2026-08-17. The previous source was the trading bridge, which
    was retired on 2026-08-16 (G-4) - after which nothing wrote this column
    at all, while dashboard_api kept raising a "bearish divergence" review
    alert on open positions from whatever value happened to be frozen in the
    row.
    """
    params = "RSIdiv %d/%d/%d" % (period, lookback, pivot)
    need = period + pivot * 2 + 2
    series, bad = _prepare(bars, need, params, min_coverage)
    if bad:
        return bad
    rs = _rsi_series(series, period)
    _, _, pct = coverage(bars)
    window = min(lookback, len(series) - period)
    px, rv = series[-window:], rs[-window:]

    for kind, verdict, price_cmp, rsi_cmp in (
            ("low", "bullish", lambda a, b: a < b, lambda a, b: a > b),
            ("high", "bearish", lambda a, b: a > b, lambda a, b: a < b)):
        idx = _pivots(px, pivot, kind)
        if len(idx) < 2:
            continue
        prev, last = idx[-2], idx[-1]
        if rv[prev] is None or rv[last] is None:
            continue
        if price_cmp(px[last], px[prev]) and rsi_cmp(rv[last], rv[prev]):
            return _result(verdict, len(series), pct, params)

    # Say WHY there is no verdict: "no pivot pair" is not the same as
    # "compared and flat", and only the second is a reading.
    if (len(_pivots(px, pivot, "low")) < 2
            and len(_pivots(px, pivot, "high")) < 2):
        return _result(None, len(series), pct, params,
                       "no pivot pair inside the last %d bars - nothing to "
                       "compare, which is not the same as no divergence"
                       % window)
    return _result("none", len(series), pct, params)


def ema_series(values, period):
    if len(values) < period:
        return []
    seed = sum(values[:period]) / period
    out = [seed]
    k = 2.0 / (period + 1)
    for v in values[period:]:
        seed = v * k + seed * (1 - k)
        out.append(seed)
    return out


def ema(bars, period, min_coverage=MIN_COVERAGE_PCT):
    params = "EMA %d" % period
    series, bad = _prepare(bars, period, params, min_coverage)
    if bad:
        return bad
    _, _, pct = coverage(bars)
    return _result(round(ema_series(series, period)[-1], 6), len(series), pct, params)


def macd(bars, fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL,
         min_coverage=MIN_COVERAGE_PCT):
    """MACD line, signal, histogram. Unbounded and SIGNED (SCALES.md)."""
    params = "MACD %d/%d/%d" % (fast, slow, signal)
    need = slow + signal
    series, bad = _prepare(bars, need, params, min_coverage)
    if bad:
        return bad
    ef, es = ema_series(series, fast), ema_series(series, slow)
    offset = slow - fast
    line = [a - b for a, b in zip(ef[offset:], es)]
    sig = ema_series(line, signal)
    _, _, pct = coverage(bars)
    if not sig:
        return _result(None, len(series), pct, params, "signal line unavailable")
    m, s = line[-1], sig[-1]
    return _result({"macd": round(m, 6), "signal": round(s, 6),
                    "histogram": round(m - s, 6),
                    "cross": "bullish" if m > s else "bearish",
                    "above_zero": m > 0},
                   len(series), pct, params)


def _hlc(bars):
    return ([b.get("high") for b in bars], [b.get("low") for b in bars],
            [b.get("close") for b in bars])


def _wilder(seed_vals, rest, n):
    a = sum(seed_vals) / n
    out = [a]
    for v in rest:
        a = (a * (n - 1) + v) / n
        out.append(a)
    return out


def _true_ranges(bars):
    H, L, C = _hlc(bars)
    trs = []
    for i in range(1, len(bars)):
        if None in (H[i], L[i], C[i - 1]):
            continue
        trs.append(max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])))
    return trs


def atr(bars, period=ATR_PERIOD, min_coverage=MIN_COVERAGE_PCT):
    """Average True Range. Unit: FILS, same as price (SCALES.md)."""
    params = "ATR %d (Wilder, fils)" % period
    _, _, pct = coverage(bars)
    if pct < min_coverage:
        return _result(None, 0, pct, params,
                       "coverage %.1f%% below the %.1f%% floor" % (pct, min_coverage))
    trs = _true_ranges(bars)
    if len(trs) < period * 2:
        return _result(None, len(trs), pct, params,
                       "need %d true ranges, have %d" % (period * 2, len(trs)))
    return _result(round(_wilder(trs[:period], trs[period:], period)[-1], 6),
                   len(trs), pct, params)


def adx(bars, period=ADX_PERIOD, min_coverage=MIN_COVERAGE_PCT):
    """ADX. Scale 0-100, UNSIGNED - it measures trend strength, not
    direction (SCALES.md)."""
    params = "ADX %d (Wilder)" % period
    _, _, pct = coverage(bars)
    if pct < min_coverage:
        return _result(None, 0, pct, params,
                       "coverage %.1f%% below the %.1f%% floor" % (pct, min_coverage))
    H, L, _C = _hlc(bars)
    trs, pdm, ndm = [], [], []
    for i in range(1, len(bars)):
        if None in (H[i], L[i], H[i - 1], L[i - 1], bars[i - 1].get("close")):
            continue
        pc = bars[i - 1]["close"]
        trs.append(max(H[i] - L[i], abs(H[i] - pc), abs(L[i] - pc)))
        up, dn = H[i] - H[i - 1], L[i - 1] - L[i]
        pdm.append(up if up > dn and up > 0 else 0.0)
        ndm.append(dn if dn > up and dn > 0 else 0.0)
    if len(trs) < period * 3:
        return _result(None, len(trs), pct, params,
                       "need %d periods, have %d" % (period * 3, len(trs)))
    atr_s = _wilder(trs[:period], trs[period:], period)
    p_s = _wilder(pdm[:period], pdm[period:], period)
    n_s = _wilder(ndm[:period], ndm[period:], period)
    dxs = []
    for a, p, m in zip(atr_s, p_s, n_s):
        if a <= 0:
            dxs.append(0.0)
            continue
        pdi, ndi = 100 * p / a, 100 * m / a
        dxs.append(100 * abs(pdi - ndi) / (pdi + ndi) if (pdi + ndi) else 0.0)
    if len(dxs) < period * 2:
        return _result(None, len(dxs), pct, params, "insufficient DX history")
    return _result(round(_wilder(dxs[:period], dxs[period:], period)[-1], 6),
                   len(dxs), pct, params)


def stoch_k(bars, period=STOCH_PERIOD, min_coverage=MIN_COVERAGE_PCT):
    """Stochastic %K. Scale 0-100, continuous."""
    params = "StochK %d" % period
    _, _, pct = coverage(bars)
    if pct < min_coverage:
        return _result(None, 0, pct, params,
                       "coverage %.1f%% below the %.1f%% floor" % (pct, min_coverage))
    w = bars[-period:]
    highs = [b["high"] for b in w if b.get("high") is not None]
    lows = [b["low"] for b in w if b.get("low") is not None]
    last = w[-1].get("close") if w else None
    if len(highs) < period or len(lows) < period or last is None:
        return _result(None, len(w), pct, params, "window has null OHLC")
    hh, ll = max(highs), min(lows)
    if hh == ll:
        return _result(None, len(w), pct, params,
                       "flat window (high == low) - %K undefined")
    return _result(round(100 * (last - ll) / (hh - ll), 4), len(w), pct, params)


def support_resistance(bars, lookback=SR_LOOKBACK, min_coverage=MIN_COVERAGE_PCT):
    """Rolling extremes over the lookback, EXCLUDING the newest bar.
    Unit: fils."""
    params = "S/R rolling %d" % lookback
    _, _, pct = coverage(bars)
    if pct < min_coverage:
        return _result(None, 0, pct, params,
                       "coverage %.1f%% below the %.1f%% floor" % (pct, min_coverage))
    w = bars[-(lookback + 1):-1] if len(bars) > lookback else []
    lows = [b["low"] for b in w if b.get("low") is not None]
    highs = [b["high"] for b in w if b.get("high") is not None]
    if not lows or not highs:
        return _result(None, len(w), pct, params, "no usable extremes")
    return _result({"support": round(min(lows), 6),
                    "resistance": round(max(highs), 6)}, len(w), pct, params)


def compute_all(bars, interval, now_utc_ts, min_coverage=MIN_COVERAGE_PCT):
    """Every indicator for one symbol, from complete bars only.

    Returns the values plus the evidence: how many bars were dropped as
    incomplete, why, the coverage of what remained, and the parameter set.
    """
    complete, dropped, drop_reason = drop_incomplete(bars, interval, now_utc_ts)
    nn, total, pct = coverage(complete)
    out = {
        "interval": interval,
        "bars_in": len(bars),
        "bars_dropped_incomplete": dropped,
        "drop_reason": drop_reason,
        "bars_complete": len(complete),
        "coverage_pct": pct,
        "coverage_floor_pct": min_coverage,
        "bar_complete": dropped >= 0 and bool(complete),
        "indicator_source": "local",
        "computed_from": "yahoo",
    }
    out["rsi"] = rsi(complete, min_coverage=min_coverage)
    out["macd"] = macd(complete, min_coverage=min_coverage)
    out["ema_9"] = ema(complete, 9, min_coverage=min_coverage)
    out["ema_21"] = ema(complete, 21, min_coverage=min_coverage)
    out["atr"] = atr(complete, min_coverage=min_coverage)
    out["adx"] = adx(complete, min_coverage=min_coverage)
    out["stoch_k"] = stoch_k(complete, min_coverage=min_coverage)
    out["sr"] = support_resistance(complete, min_coverage=min_coverage)
    out["rsi_divergence"] = rsi_divergence(complete, min_coverage=min_coverage)
    return out
