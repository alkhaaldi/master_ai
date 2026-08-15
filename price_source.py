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
    for k in ("currency", "age_days", "captured_mid_session", "reason", "tried"):
        if k in q:
            out[k] = q[k]
    return out


if __name__ == "__main__":
    import sys
    for s in (sys.argv[1:] or ["EQUIPMENT"]):
        print(f"quote {s}: {json.dumps(get_quote(s), ensure_ascii=False)}")
        print(f"price {s}: {json.dumps(get_price(s), ensure_ascii=False)}")
    print(f"bridge circuit: {bridge_circuit_state()}")
