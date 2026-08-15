#!/usr/bin/env python3
"""One way to ask what a symbol is worth.

    get_price("EQUIPMENT") -> {"price": 223.0,
                               "as_of": "2026-08-13T10:14:18+00:00",
                               "source": "yahoo",
                               "state": "live"}

The rule this exists to enforce: a price is never returned as a bare number.
It arrives with the time it was measured and an honest label, or it does not
arrive at all. Every caller can then decide for itself, and none of them has to
guess.

state:
    live    - a real quote with a timestamp we trust
    stale   - the last value we ever stored, with the time it was stored
    missing - we do not know, and we will not pretend. price is None.

A price with no as_of is `missing`, whatever its numeric value. That is the
whole point: the system published -2.51% P&L on a 134-day-old number for months
because the number arrived without its date.

Yahoo is consulted only for symbols marked `confirmed` in
_tools/kse_symbol_map.json. The 61 symbols still marked `review` returned valid
Kuwait-exchange data but have not been eyeballed against our own names, so they
are not trusted here yet.

Nothing is wired to this yet. Import it, call it, compare it to what the caller
does today, then switch that caller over - one at a time.
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

# Order matters and is deliberate. See the note in the module docstring of the
# commit that introduced this: yahoo first as specified, bridge second. Swapping
# them makes the bridge authoritative whenever it is running, which is arguably
# better during a live session - it is one line, here.
SOURCE_ORDER = ("yahoo", "bridge", "db")

YAHOO_TTL = 60          # seconds; this replaces ~39 call sites, so it must not hammer
BRIDGE_TIMEOUT = 3      # the bridge is on the LAN or it is not there at all
YAHOO_TIMEOUT = 12

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}
_opener = None
_confirmed: set[str] | None = None


# ----------------------------------------------------------------- helpers
def _result(price, as_of, source, state, **extra) -> dict:
    out = {"price": price, "as_of": as_of, "source": source, "state": state}
    out.update(extra)
    return out


def _missing(reason: str) -> dict:
    return _result(None, None, "none", "missing", reason=reason)


def confirmed_symbols() -> set[str]:
    """Symbols whose Yahoo ticker has been verified. Empty set if the map is absent."""
    global _confirmed
    if _confirmed is None:
        try:
            data = json.loads(SYMBOL_MAP.read_text(encoding="utf-8"))
            _confirmed = {r["our_symbol"] for r in data.get("records", [])
                          if r.get("verdict") == "confirmed"}
        except (OSError, json.JSONDecodeError, KeyError):
            _confirmed = set()
    return _confirmed


def _yahoo_opener():
    global _opener
    if _opener is None:
        import http.cookiejar
        jar = http.cookiejar.CookieJar()
        _opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        # priming call: query2 refuses a cookieless client with 429
        try:
            _opener.open(urllib.request.Request(
                "https://fc.yahoo.com", headers=_UA), timeout=YAHOO_TIMEOUT).read(1)
        except Exception:
            pass
    return _opener


_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
       "Accept": "application/json,text/plain,*/*"}


# ----------------------------------------------------------------- sources
def _from_yahoo(symbol: str) -> dict | None:
    if symbol not in confirmed_symbols():
        return None
    url = ("https://query2.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(symbol + ".KW") + "?range=5d&interval=1d")
    try:
        with _yahoo_opener().open(
                urllib.request.Request(url, headers=_UA), timeout=YAHOO_TIMEOUT) as f:
            meta = json.loads(f.read().decode())["chart"]["result"][0]["meta"]
    except (urllib.error.HTTPError, urllib.error.URLError, OSError,
            json.JSONDecodeError, KeyError, IndexError, TypeError):
        return None
    price, ts = meta.get("regularMarketPrice"), meta.get("regularMarketTime")
    if price is None or not isinstance(ts, int):
        return None                       # a price with no timestamp is not a price
    return _result(float(price),
                   datetime.fromtimestamp(ts, timezone.utc).isoformat(),
                   "yahoo", "live", currency=meta.get("currency"))


def _from_bridge(symbol: str) -> dict | None:
    base = os.getenv("BRIDGE_URL", "http://192.168.111.214:8059")
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=2) as f:
            if f.status != 200:
                return None
    except Exception:
        return None
    try:
        with urllib.request.urlopen(
                f"{base}/quote?symbol={urllib.parse.quote(symbol)}",
                timeout=BRIDGE_TIMEOUT) as f:
            data = json.loads(f.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError, OSError,
            json.JSONDecodeError):
        return None
    price = data.get("price")
    if price is None:
        return None
    # the bridge answers from a live feed, so "now" is the measurement time
    return _result(float(price), datetime.now(timezone.utc).isoformat(),
                   "bridge", "live")


def _from_db(symbol: str) -> dict | None:
    """Last stored value. Always stale - this table is a record, not a feed."""
    if not LIFE_DB.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{LIFE_DB}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT price, captured_at, updated_at, market_was_open "
            "FROM stock_radar_daily WHERE symbol = ? "
            "ORDER BY captured_at DESC LIMIT 1", (symbol.upper(),)).fetchone()
        conn.close()
    except sqlite3.Error:
        return None
    if not row or row["price"] is None:
        return None
    as_of = row["captured_at"] or row["updated_at"]
    if not as_of:
        # a stored number whose date we lost is worse than nothing: it is the
        # exact shape that produced a confident P&L on a four-month-old price
        return None
    age_days = None
    try:
        age_days = (datetime.now(timezone.utc).replace(tzinfo=None)
                    - datetime.fromisoformat(str(as_of))).days
    except (ValueError, TypeError):
        return None
    return _result(float(row["price"]), str(as_of), "db", "stale",
                   age_days=age_days,
                   captured_mid_session=bool(row["market_was_open"]))


_SOURCES = {"yahoo": _from_yahoo, "bridge": _from_bridge, "db": _from_db}


# ----------------------------------------------------------------- public
def get_price(symbol: str, use_cache: bool = True) -> dict:
    """Best available price for one symbol. Always a dict, never a bare number."""
    if not symbol or not isinstance(symbol, str):
        return _missing("no symbol given")
    sym = symbol.strip().upper()
    if not sym:
        return _missing("no symbol given")

    if use_cache:
        with _lock:
            hit = _cache.get(sym)
        if hit and (time.time() - hit[0]) < YAHOO_TTL:
            return dict(hit[1])

    tried = []
    for name in SOURCE_ORDER:
        try:
            got = _SOURCES[name](sym)
        except Exception as exc:            # a broken source must not mask the rest
            tried.append(f"{name}:{type(exc).__name__}")
            continue
        if got:
            got["tried"] = tried
            with _lock:
                _cache[sym] = (time.time(), dict(got))
            return got
        tried.append(f"{name}:none")

    return _missing(f"no source had a dated price (tried {', '.join(tried)})")


if __name__ == "__main__":
    import sys
    for s in (sys.argv[1:] or ["EQUIPMENT"]):
        print(f"{s}: {json.dumps(get_price(s), ensure_ascii=False)}")
