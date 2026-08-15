#!/usr/bin/env python3
"""One way to ask what a symbol is worth.

    get_quote("EQUIPMENT") -> {"open":222.0, "high":225.0, "low":219.0,
                               "close":223.0, "volume":2321399,
                               "as_of":"2026-08-13T10:14:18+00:00",
                               "source":"yahoo", "state":"live"}

    get_price("EQUIPMENT") -> {"price":223.0, "as_of":..., "source":..., "state":...}

The rule this exists to enforce: a number is never returned bare. It arrives
with the time it was measured and an honest label, or it does not arrive.

state:
    live    - a real quote with a timestamp we trust
    stale   - the last value we ever stored, with the time it was stored
    missing - we do not know, and we will not pretend. values are None.

A value with no as_of is `missing` whatever its number. That is the whole point:
-2.51% P&L was published for months on a 134-day-old price because the number
arrived without its date.

combine() carries the composition rule: when two numbers of different vintage
meet, the result takes the WORST state and the OLDEST as_of. A live price times
a four-month-old volume is a four-month-old answer, and saying otherwise is how
a stale figure gets laundered into a fresh-looking one.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import logging
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
LIFE_DB = BASE / "data" / "life.db"
SYMBOL_MAP = BASE / "_tools" / "kse_symbol_map.json"

# Bridge first: when it is running it is a live feed and Yahoo is end-of-day.
# It is started by hand, so most of the time it fails fast and we fall through.
SOURCE_ORDER = ("bridge", "yahoo", "db")

QUOTE_TTL = 60          # seconds; this stands in front of ~39 call sites
BRIDGE_HEALTH_TIMEOUT = 2
BRIDGE_TIMEOUT = 3
YAHOO_TIMEOUT = 12

STATE_RANK = {"live": 0, "stale": 1, "missing": 2}

logger = logging.getLogger("price_source")

# Last line of defence for symbol identity. The name heuristic is a mark,
# not a gate (kse_symbol_map name_match); what actually catches a wrong
# ticker is its price landing far from the last stored one.
PRICE_DEVIATION_GUARD = 0.30

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
       "Accept": "application/json,text/plain,*/*"}

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}
_opener = None
_confirmed: set[str] | None = None

# Bridge circuit: one failure closes it for the rest of the process. Without
# this, a walk over 132 symbols with the bridge down costs 132 x the health
# timeout before anything else is even tried. It latches on purpose - an
# auto-resetting breaker is what let bridge_client hammer a dead host for
# months. reset_bridge_circuit() re-arms it deliberately.
_bridge_open = False
_bridge_reason: str | None = None


def reset_bridge_circuit() -> None:
    """Re-arm the bridge after starting it by hand."""
    global _bridge_open, _bridge_reason
    with _lock:
        _bridge_open, _bridge_reason = False, None


def bridge_circuit_state() -> dict:
    return {"open": _bridge_open, "reason": _bridge_reason}


# ----------------------------------------------------------------- helpers
def _empty(source: str, state: str, **extra) -> dict:
    out = {"open": None, "high": None, "low": None, "close": None, "volume": None,
           "as_of": None, "source": source, "state": state}
    out.update(extra)
    return out


def confirmed_symbols() -> set[str]:
    """Symbols whose Yahoo ticker has been verified against our own names."""
    global _confirmed
    if _confirmed is None:
        try:
            data = json.loads(SYMBOL_MAP.read_text(encoding="utf-8"))
            _confirmed = {r["our_symbol"] for r in data.get("records", [])
                          if r.get("verdict") == "confirmed"}
        except (OSError, json.JSONDecodeError, KeyError):
            _confirmed = set()
    return _confirmed


def _parse_as_of(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


# ---------------------------------------------------------------- sessions
# Data age is measured in TRADING SESSIONS, not hours, by user decision
# (2026-08-15): a last close while the market is closed is the freshest
# truth that can exist - normal, not stale. KSE trades Sun-Thu 09:00-13:00
# Kuwait (+03, no DST). The exchange calendar has two witnesses: the
# weekday rule, and daily_bars itself - a Sun-Thu date with no bars while
# later bars exist is a verified holiday and does not count as a missed
# session; dates beyond the last stored bar DO count (pessimistic, so
# staleness can never hide behind an unrefreshed table).

_KSE_TRADING_WEEKDAYS = (6, 0, 1, 2, 3)      # datetime.weekday(): Sun-Thu
_KSE_UTC_OFFSET = 3
_SESSION_OPEN_H, _SESSION_CLOSE_H = 9, 13

DATA_STATE_RANK = {"live": 0, "normal": 0, "degraded": 1, "broken": 2, "blind": 3}

_session_dates = {"ts": 0.0, "dates": frozenset(), "max": None}


def _known_session_dates():
    """Distinct trading dates present in daily_bars, cached one hour."""
    now = time.time()
    if now - _session_dates["ts"] < 3600:
        return _session_dates["dates"], _session_dates["max"]
    dates, mx = frozenset(), None
    try:
        conn = sqlite3.connect(f"file:{LIFE_DB}?mode=ro", uri=True, timeout=5)
        rows = conn.execute("SELECT DISTINCT trading_date FROM daily_bars").fetchall()
        conn.close()
        dates = frozenset(str(r[0]) for r in rows if r[0])
        mx = max(dates) if dates else None
    except sqlite3.Error:
        pass
    _session_dates.update(ts=now, dates=dates, max=mx)
    return dates, mx


def _kse_local(dt_utc):
    from datetime import timedelta as _td
    return dt_utc + _td(hours=_KSE_UTC_OFFSET)


def market_open_now(now_utc=None) -> bool:
    loc = _kse_local(now_utc or datetime.utcnow())
    return (loc.weekday() in _KSE_TRADING_WEEKDAYS
            and _SESSION_OPEN_H <= loc.hour < _SESSION_CLOSE_H)


def _sessions_since(as_of_utc, now_utc):
    """Trading sessions strictly after as_of, up to now. Verified holidays
    excluded; today counts only once its session has opened."""
    from datetime import timedelta as _td
    known, mx = _known_session_dates()
    loc_now = _kse_local(now_utc)
    d = _kse_local(as_of_utc).date() + _td(days=1)
    n = 0
    while d <= loc_now.date():
        if d.weekday() in _KSE_TRADING_WEEKDAYS:
            iso = d.isoformat()
            if mx and iso <= mx and iso not in known:
                pass                       # verified holiday
            elif d == loc_now.date() and loc_now.hour < _SESSION_OPEN_H:
                pass                       # today, session not yet open
            else:
                n += 1
        d += _td(days=1)
    return n


def classify_data_state(as_of, mid_session=False, now_utc=None) -> dict:
    """The five-state model, session-aged:

      closed + last close present        -> normal   (green)
      open   + price from this session   -> live     (green)
      open   + latest is a past close    -> degraded (yellow)
      last close older than 3 sessions   -> broken   (red)
      no data at all                     -> blind    (red)

    mid_session marks an intraday capture, which is never a close: it
    stays live while its own session runs, and degrades once it is all
    the market left behind.
    """
    now_utc = now_utc or datetime.utcnow()
    dt = _parse_as_of(as_of)
    if dt is None:
        return {"data_state": "blind", "data_state_ar": "أعمى · لا بيانات",
                "sessions_old": None, "market_open": market_open_now(now_utc)}
    is_open = market_open_now(now_utc)
    n = _sessions_since(dt, now_utc)
    loc_as_of, loc_now = _kse_local(dt), _kse_local(now_utc)
    same_session = (loc_as_of.date() == loc_now.date()
                    and loc_as_of.hour >= _SESSION_OPEN_H)
    date_str = loc_as_of.date().isoformat()

    if n > 3:
        st, ar = "broken", f"معطّل · آخر بيانات قبل {n} جلسات ({date_str})"
    elif is_open:
        if same_session:
            st, ar = "live", f"حي · جلسة {date_str}"
        else:
            st, ar = "degraded", "متدهور · السوق مفتوح وآخر بيانات من جلسة سابقة"
    elif n == 0:
        if mid_session:
            st, ar = "degraded", f"متدهور · التقاط أثناء جلسة {date_str}، ليس إغلاقاً"
        else:
            st, ar = "normal", f"مقفل · آخر إغلاق {date_str}"
    elif n <= 3:
        st, ar = "degraded", f"متدهور · آخر إغلاق قبل {n} جلسة ({date_str})"
    return {"data_state": st, "data_state_ar": ar,
            "sessions_old": n, "market_open": is_open}


def combine(*parts: dict, source: str | None = None, **extra) -> dict:
    """Worst state, oldest as_of. Use whenever two dated numbers are multiplied,
    divided or otherwise mixed into one answer."""
    parts = [p for p in parts if isinstance(p, dict)]
    if not parts:
        return {"as_of": None, "source": source or "none", "state": "missing",
                "reason": "nothing to combine", **extra}
    state = max((p.get("state", "missing") for p in parts),
                key=lambda s: STATE_RANK.get(s, 2))
    dated = [(d, p) for p in parts if (d := _parse_as_of(p.get("as_of")))]
    oldest = min(dated, key=lambda t: t[0])[1].get("as_of") if dated else None
    if oldest is None:
        state = "missing"
    srcs = sorted({p.get("source", "none") for p in parts})
    out = {"as_of": oldest, "source": source or "+".join(srcs), "state": state}
    out.update(extra)
    return out


# ----------------------------------------------------------------- sources
def _yahoo_opener():
    global _opener
    if _opener is None:
        import http.cookiejar
        jar = http.cookiejar.CookieJar()
        _opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        try:                       # query2 refuses a cookieless client with 429
            _opener.open(urllib.request.Request("https://fc.yahoo.com", headers=_UA),
                         timeout=YAHOO_TIMEOUT).read(1)
        except Exception:
            pass
    return _opener


def _from_yahoo(symbol: str) -> dict | None:
    if symbol not in confirmed_symbols():
        return None
    url = ("https://query2.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(symbol + ".KW") + "?range=5d&interval=1d")
    try:
        with _yahoo_opener().open(urllib.request.Request(url, headers=_UA),
                                  timeout=YAHOO_TIMEOUT) as f:
            res = json.loads(f.read().decode())["chart"]["result"][0]
    except (urllib.error.HTTPError, urllib.error.URLError, OSError,
            json.JSONDecodeError, KeyError, IndexError, TypeError):
        return None
    meta = res.get("meta") or {}
    ts = meta.get("regularMarketTime")
    if not isinstance(ts, int):
        return None                      # no timestamp means no usable quote
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    stamps = res.get("timestamp") or []
    idx = None
    for i in range(len(stamps) - 1, -1, -1):     # newest bar with a close
        if (q.get("close") or [None] * len(stamps))[i] is not None:
            idx = i
            break

    def bar(key):
        arr = q.get(key)
        return float(arr[idx]) if (arr and idx is not None and arr[idx] is not None) else None

    close = bar("close")
    if close is None:
        close = float(meta["regularMarketPrice"]) if meta.get("regularMarketPrice") else None
    if close is None:
        return None
    vol = bar("volume")
    if vol is None and meta.get("regularMarketVolume") is not None:
        vol = float(meta["regularMarketVolume"])
    return {"open": bar("open"), "high": bar("high"), "low": bar("low"),
            "close": close, "volume": vol,
            "as_of": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
            "source": "yahoo", "state": "live",
            "currency": meta.get("currency"),
            "bar_start": (datetime.fromtimestamp(stamps[idx], timezone.utc).isoformat()
                          if idx is not None and stamps else None)}


def _from_bridge(symbol: str) -> dict | None:
    global _bridge_open, _bridge_reason
    if _bridge_open:
        return None
    base = os.getenv("BRIDGE_URL", "http://192.168.111.214:8059")
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=BRIDGE_HEALTH_TIMEOUT) as f:
            if f.status != 200:
                raise OSError(f"health {f.status}")
    except Exception as exc:
        with _lock:
            _bridge_open, _bridge_reason = True, f"health: {type(exc).__name__}"
        return None
    try:
        with urllib.request.urlopen(
                f"{base}/quote?symbol={urllib.parse.quote(symbol)}",
                timeout=BRIDGE_TIMEOUT) as f:
            data = json.loads(f.read().decode())
    except Exception as exc:
        with _lock:
            _bridge_open, _bridge_reason = True, f"quote: {type(exc).__name__}"
        return None
    close = data.get("price") or data.get("close")
    if close is None:
        return None

    def num(k):
        v = data.get(k)
        return float(v) if v is not None else None

    return {"open": num("open"), "high": num("high"), "low": num("low"),
            "close": float(close), "volume": num("volume"),
            "as_of": datetime.now(timezone.utc).isoformat(),
            "source": "bridge", "state": "live"}


def _from_db(symbol: str) -> dict | None:
    """Last stored row. Always stale - this table is a record, not a feed."""
    if not LIFE_DB.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{LIFE_DB}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT price, volume, avg_volume, captured_at, updated_at, market_was_open "
            "FROM stock_radar_daily WHERE symbol = ? "
            "ORDER BY captured_at DESC LIMIT 1", (symbol.upper(),)).fetchone()
        conn.close()
    except sqlite3.Error:
        return None
    if not row or row["price"] is None:
        return None
    as_of = row["captured_at"] or row["updated_at"]
    if not as_of or _parse_as_of(as_of) is None:
        return None            # a stored number whose date we lost is worse than none
    age = (datetime.now(timezone.utc).replace(tzinfo=None) - _parse_as_of(as_of)).days
    vol = row["volume"] if row["volume"] is not None else row["avg_volume"]
    return {"open": None, "high": None, "low": None,
            "close": float(row["price"]),
            "volume": float(vol) if vol is not None else None,
            "avg_volume": float(row["avg_volume"]) if row["avg_volume"] is not None else None,
            "as_of": str(as_of), "source": "db", "state": "stale",
            "age_days": age, "captured_mid_session": bool(row["market_was_open"])}


_SOURCES = {"yahoo": _from_yahoo, "bridge": _from_bridge, "db": _from_db}


def _guard_against_wrong_symbol(sym: str, quote: dict) -> None:
    """Mark a live price sitting >30% from the last stored one - and say so.

    Never blocks and never mutates the price: a silent block would just
    rebuild the review gate this guard replaced. Consumers see
    db_deviation_flag / db_deviation_pct and decide; the WARNING makes it
    reach server.log.
    """
    try:
        ref = _from_db(sym)
    except Exception:
        return
    if not ref or not ref.get("close"):
        return
    dev = abs(quote["close"] - ref["close"]) / ref["close"]
    if dev > PRICE_DEVIATION_GUARD:
        quote["db_deviation_pct"] = round(dev * 100.0, 1)
        quote["db_deviation_flag"] = True
        logger.warning(
            "price guard: %s live %.1f fils vs stored %.1f (%s%%, stored as of %s)"
            " - possible wrong symbol or real move, marked not blocked",
            sym, quote["close"], ref["close"], quote["db_deviation_pct"],
            str(ref.get("as_of"))[:10])


# ----------------------------------------------------------------- public
def get_quote(symbol: str, use_cache: bool = True) -> dict:
    """OHLCV for one symbol, with the time it was measured and an honest state."""
    if not symbol or not isinstance(symbol, str) or not symbol.strip():
        return _empty("none", "missing", reason="no symbol given")
    sym = symbol.strip().upper()

    if use_cache:
        with _lock:
            hit = _cache.get(sym)
        if hit and (time.time() - hit[0]) < QUOTE_TTL:
            return dict(hit[1])

    tried = []
    for name in SOURCE_ORDER:
        try:
            got = _SOURCES[name](sym)
        except Exception as exc:          # one broken source must not hide the rest
            tried.append(f"{name}:{type(exc).__name__}")
            continue
        if got:
            got["tried"] = tried
            # session-aged truth: the five-state model decides, and the
            # binary state every existing consumer compares against is
            # aligned with it - a last close while the market is closed
            # reads live, an old "live" feed answer reads stale.
            _ds = classify_data_state(got.get("as_of"),
                                      got.get("captured_mid_session", False))
            got.update(_ds)
            if _ds["data_state"] in ("normal", "live"):
                got["state"] = "live"
            elif _ds["data_state"] == "blind":
                got["state"] = "missing"
            else:
                got["state"] = "stale"
            if got.get("state") == "live" and got.get("close"):
                _guard_against_wrong_symbol(sym, got)
            with _lock:
                _cache[sym] = (time.time(), dict(got))
            return got
        tried.append(f"{name}:none")
    return _empty("none", "missing",
                  reason=f"no source had a dated quote (tried {', '.join(tried)})")


def get_price(symbol: str, use_cache: bool = True) -> dict:
    """Thin view over get_quote. Contract unchanged: price, as_of, source, state."""
    q = get_quote(symbol, use_cache=use_cache)
    out = {"price": q.get("close"), "as_of": q.get("as_of"),
           "source": q.get("source"), "state": q.get("state")}
    for k in ("currency", "age_days", "captured_mid_session", "reason", "tried",
              "db_deviation_pct", "db_deviation_flag",
              "data_state", "data_state_ar", "sessions_old", "market_open"):
        if k in q:
            out[k] = q[k]
    return out


if __name__ == "__main__":
    import sys
    for s in (sys.argv[1:] or ["EQUIPMENT"]):
        print(f"quote {s}: {json.dumps(get_quote(s), ensure_ascii=False)}")
        print(f"price {s}: {json.dumps(get_price(s), ensure_ascii=False)}")
    print(f"bridge circuit: {bridge_circuit_state()}")
