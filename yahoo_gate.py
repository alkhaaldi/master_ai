"""G-3: one throttled, cached, circuit-broken door to Yahoo.

Yahoo is now the single source, so the failure path matters as much as the
happy one. Measured facts this is built on:

  - the rate limit is BURST-sensitive, not volume-sensitive: 9 back-to-back
    requests returned 429 on every one, while 33 requests spaced 2s returned
    zero 429s (G-1).
  - a 132-symbol sweep at 2s is ~4.4 minutes - comfortably inside the
    15-minute intraday window.

The rule that shapes the whole module: **a 429 is not "no data", it is "we
could not ask".** Those are different states and must never collapse into
one. `blocked` is reported as its own state so a dashboard can render
`blind` instead of the last good value.
"""
from __future__ import annotations

import json
import random
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB = BASE / "data" / "life.db"

MIN_INTERVAL = 2.0          # seconds between requests, measured safe in G-1
JITTER = 0.4                # +/- so a fleet of callers cannot align
BACKOFF_BASE = 8.0          # first 429 wait
BACKOFF_MAX = 300.0
CIRCUIT_THRESHOLD = 5       # consecutive failures before the door shuts
CIRCUIT_COOLDOWN = 600.0    # seconds shut before one probe is allowed

_lock = threading.Lock()
_last_request = 0.0
_state = {
    "consecutive_failures": 0,
    "open": False,
    "opened_at": None,
    "reason": None,
    "last_success": None,
    "last_failure": None,
    "requests": 0,
    "throttled_seconds": 0.0,
    "rate_limited": 0,
}

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
       "Accept": "application/json,text/plain,*/*"}


class YahooBlocked(Exception):
    """Raised when the circuit is open. Deliberately NOT a data condition:
    callers must not turn it into an empty result."""


def circuit_state() -> dict:
    with _lock:
        s = dict(_state)
    if s["open"] and s["opened_at"]:
        s["cooldown_remaining_s"] = round(
            max(0.0, CIRCUIT_COOLDOWN - (time.time() - s["opened_at"])), 1)
    return s


def _throttle():
    """Space requests. Sleeps whoever arrives early - one scan must not be
    able to burst 132 requests."""
    global _last_request
    with _lock:
        now = time.time()
        wait = (_last_request + MIN_INTERVAL + random.uniform(-JITTER, JITTER)) - now
        if wait > 0:
            _state["throttled_seconds"] = round(
                _state["throttled_seconds"] + wait, 1)
        else:
            wait = 0.0
        _last_request = now + wait
    if wait > 0:
        time.sleep(wait)


def _record(ok, reason=None, rate_limited=False):
    with _lock:
        _state["requests"] += 1
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if rate_limited:
            _state["rate_limited"] += 1
        if ok:
            _state["consecutive_failures"] = 0
            _state["last_success"] = now_iso
            if _state["open"]:
                _state.update(open=False, opened_at=None,
                              reason="recovered at %s" % now_iso)
        else:
            _state["consecutive_failures"] += 1
            _state["last_failure"] = now_iso
            if (_state["consecutive_failures"] >= CIRCUIT_THRESHOLD
                    and not _state["open"]):
                _state.update(open=True, opened_at=time.time(),
                              reason="%d consecutive failures, last: %s"
                                     % (_state["consecutive_failures"], reason))
                _witness("circuit_open", _state["reason"])


def _witness(status, detail):
    """A shut door must announce itself - the lesson of the backups that
    failed silently for 4.5 months."""
    try:
        conn = sqlite3.connect(str(DB), timeout=10)
        conn.execute(
            "INSERT INTO data_fetch_runs (run_date, source, status,"
            " symbols_fetched, symbols_expected, duration_sec, error_msg)"
            " VALUES (?,?,?,?,?,?,?)",
            (datetime.utcnow().strftime("%Y-%m-%d"), "yahoo_gate", status,
             0, 0, 0.0, str(detail)[:300]))
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass
    if status == "circuit_open":
        try:
            import sys
            sys.path.insert(0, str(BASE / "_tools"))
            import run_witness
            run_witness.send_telegram(
                "⚠️ قاطع Yahoo فُتح: %s — النظام أعمى عن الأسعار حتى يتعافى"
                % str(detail)[:180])
        except Exception:
            pass


_opener = None


def _get_opener():
    global _opener
    if _opener is None:
        import http.cookiejar
        jar = http.cookiejar.CookieJar()
        _opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar))
        try:
            _opener.open(urllib.request.Request("https://fc.yahoo.com",
                                                headers=_UA), timeout=10).read(1)
        except Exception:
            pass
    return _opener


def get(url, timeout=12, retries=2):
    """One throttled request. Returns parsed JSON.

    Raises YahooBlocked when the circuit is open or a 429 survives the
    backoff - never an empty dict, because an empty dict is what a caller
    would mistake for "no data".
    """
    st = circuit_state()
    if st["open"]:
        if st.get("cooldown_remaining_s", 0) > 0:
            raise YahooBlocked("circuit open, %ss remaining: %s"
                               % (st["cooldown_remaining_s"], st["reason"]))
        with _lock:            # cooldown elapsed: allow one probe through
            _state["open"] = False

    backoff = BACKOFF_BASE
    for attempt in range(retries + 1):
        _throttle()
        try:
            with _get_opener().open(
                    urllib.request.Request(url, headers=_UA), timeout=timeout) as f:
                data = json.loads(f.read().decode())
            _record(True)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 429:
                _record(False, "429 rate limited", rate_limited=True)
                if attempt < retries:
                    time.sleep(min(backoff, BACKOFF_MAX)
                               + random.uniform(0, 2))
                    backoff *= 2
                    continue
                raise YahooBlocked("429 after %d attempts - we could not ask, "
                                   "which is not the same as no data" % (attempt + 1))
            _record(False, "http %d" % e.code)
            raise
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            _record(False, type(e).__name__)
            if attempt < retries:
                time.sleep(min(backoff, BACKOFF_MAX))
                backoff *= 2
                continue
            raise


# ─────────────────────────────── cache ────────────────────────────────

def _ensure_cache():
    conn = sqlite3.connect(str(DB), timeout=15)
    conn.execute("""CREATE TABLE IF NOT EXISTS yahoo_bar_cache (
        symbol TEXT NOT NULL,
        interval TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        payload TEXT NOT NULL,
        bars INTEGER,
        PRIMARY KEY (symbol, interval))""")
    conn.commit()
    return conn


def cached_bars(symbol, interval, max_age_s):
    """Stored bars if fresh enough, else None. A completed daily bar does
    not change; refetching it is a request spent to learn nothing."""
    try:
        conn = _ensure_cache()
        row = conn.execute(
            "SELECT fetched_at, payload FROM yahoo_bar_cache "
            "WHERE symbol=? AND interval=?", (symbol, interval)).fetchone()
        conn.close()
    except sqlite3.Error:
        return None
    if not row:
        return None
    try:
        age = (datetime.utcnow()
               - datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")).total_seconds()
    except (ValueError, TypeError):
        return None
    if age > max_age_s:
        return None
    try:
        return json.loads(row[1])
    except json.JSONDecodeError:
        return None


def store_bars(symbol, interval, bars):
    try:
        conn = _ensure_cache()
        conn.execute(
            "INSERT OR REPLACE INTO yahoo_bar_cache "
            "(symbol, interval, fetched_at, payload, bars) VALUES (?,?,?,?,?)",
            (symbol, interval,
             datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
             json.dumps(bars), len(bars)))
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass


def chart(symbol, interval="1d", rng="6mo", suffix=".KW", max_age_s=0):
    """Bars for one symbol, cache-first. Raises YahooBlocked when shut."""
    if max_age_s:
        hit = cached_bars(symbol, interval, max_age_s)
        if hit is not None:
            return hit, "cache"
    url = ("https://query2.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(symbol + suffix)
           + "?range=%s&interval=%s" % (rng, interval))
    raw = get(url)
    res = (raw.get("chart") or {}).get("result")
    if not res:
        return [], "empty"
    r = res[0]
    stamps = r.get("timestamp") or []
    q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    bars = []
    for i, ts in enumerate(stamps):
        bars.append({"ts": ts,
                     "open": (q.get("open") or [None] * len(stamps))[i],
                     "high": (q.get("high") or [None] * len(stamps))[i],
                     "low": (q.get("low") or [None] * len(stamps))[i],
                     "close": (q.get("close") or [None] * len(stamps))[i],
                     "volume": (q.get("volume") or [None] * len(stamps))[i]})
    store_bars(symbol, interval, bars)
    return bars, "yahoo"


def quotes(symbols, suffix=".KW"):
    """Batch quote endpoint - many symbols per call, unlike chart.
    One request for a whole watchlist instead of one per symbol."""
    if not symbols:
        return {}
    syms = ",".join(urllib.parse.quote(s + suffix) for s in symbols)
    url = "https://query1.finance.yahoo.com/v7/finance/quote?symbols=" + syms
    raw = get(url)
    out = {}
    for item in ((raw.get("quoteResponse") or {}).get("result") or []):
        sym = str(item.get("symbol", "")).replace(suffix, "")
        out[sym] = {
            "price": item.get("regularMarketPrice"),
            "volume": item.get("regularMarketVolume"),
            "change_pct": item.get("regularMarketChangePercent"),
            "ts": item.get("regularMarketTime"),
            "currency": item.get("currency"),
        }
    return out
