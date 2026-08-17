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

# The state lives in its own tiny database, not in module globals
# (2026-08-17). Globals gave every process a private door: cron spawns a
# fresh interpreter per run, so the */15 scan and the */2 positions cycle
# each spaced their own requests 2s apart and neither knew the other was
# knocking. Worse, quick_check imported this module in ITS own process and
# reported "0 requests, circuit closed" for ever - a green check that could
# not go red, which is more dangerous than no check at all.
#
# Its own file, not life.db: this is a high-frequency write on the hot path
# of every request, and a locked or corrupt gate must never be able to block
# the tables it exists to protect.
GATE_DB = BASE / "data" / "yahoo_gate.db"

_lock = threading.Lock()
_last_request = 0.0          # fallback only, used when the shared store fails
_state = {                   # fallback only - see _shared_reason
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
_shared_reason = None        # None = shared store healthy; str = why we fell back

_FIELDS = ("last_request", "consecutive_failures", "is_open", "opened_at",
           "reason", "last_success", "last_failure", "requests",
           "throttled_seconds", "rate_limited", "counters_since")

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
       "Accept": "application/json,text/plain,*/*"}


class YahooBlocked(Exception):
    """Raised when the circuit is open. Deliberately NOT a data condition:
    callers must not turn it into an empty result."""


def _gate_conn():
    conn = sqlite3.connect(str(GATE_DB), timeout=15, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute("""CREATE TABLE IF NOT EXISTS gate_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        last_request REAL NOT NULL DEFAULT 0,
        consecutive_failures INTEGER NOT NULL DEFAULT 0,
        is_open INTEGER NOT NULL DEFAULT 0,
        opened_at REAL,
        reason TEXT,
        last_success TEXT,
        last_failure TEXT,
        requests INTEGER NOT NULL DEFAULT 0,
        throttled_seconds REAL NOT NULL DEFAULT 0,
        rate_limited INTEGER NOT NULL DEFAULT 0,
        counters_since TEXT)""")
    conn.execute("INSERT OR IGNORE INTO gate_state (id, counters_since)"
                 " VALUES (1, ?)",
                 (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),))
    return conn


def _mark(reason):
    global _shared_reason
    _shared_reason = reason


def _read_row(conn):
    r = conn.execute("SELECT %s FROM gate_state WHERE id=1"
                     % ",".join(_FIELDS)).fetchone()
    return dict(zip(_FIELDS, r))


def _write_row(conn, d):
    conn.execute("UPDATE gate_state SET %s WHERE id=1"
                 % ",".join("%s=?" % f for f in _FIELDS),
                 tuple(d[f] for f in _FIELDS))


def circuit_state() -> dict:
    try:
        conn = _gate_conn()
        try:
            d = _read_row(conn)
        finally:
            conn.close()
        s = {"consecutive_failures": d["consecutive_failures"],
             "open": bool(d["is_open"]), "opened_at": d["opened_at"],
             "reason": d["reason"], "last_success": d["last_success"],
             "last_failure": d["last_failure"], "requests": d["requests"],
             "throttled_seconds": round(d["throttled_seconds"], 1),
             "rate_limited": d["rate_limited"],
             "counters_since": d["counters_since"]}
        _mark(None)
    except sqlite3.Error as e:
        _mark("read: %r" % e)
        with _lock:
            s = dict(_state)
        s["counters_since"] = None
    # A caller must be able to tell "the door is fine" from "we lost sight of
    # the door and are guessing from this process alone".
    s["shared"] = _shared_reason is None
    s["shared_reason"] = _shared_reason
    if s["open"] and s["opened_at"]:
        s["cooldown_remaining_s"] = round(
            max(0.0, CIRCUIT_COOLDOWN - (time.time() - s["opened_at"])), 1)
    return s


def _throttle():
    """Space requests. Sleeps whoever arrives early - one scan must not be
    able to burst 132 requests, and two concurrent runs must not be able to
    interleave into one.

    BEGIN IMMEDIATE makes the read-modify-write of the next slot atomic
    across processes, which is the whole point: reserving the slot before
    sleeping means a second process sees the reservation, not the clock.
    """
    global _last_request
    gap = MIN_INTERVAL + random.uniform(-JITTER, JITTER)
    try:
        conn = _gate_conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            d = _read_row(conn)
            now = time.time()
            slot = max(now, d["last_request"] + gap)
            wait = slot - now
            d["last_request"] = slot
            # No `or 0.0` here: the column is NOT NULL DEFAULT 0, so a
            # None is impossible and a default would only hide a schema
            # change behind an invented zero.
            d["throttled_seconds"] = round(
                d["throttled_seconds"] + max(wait, 0.0), 1)
            _write_row(conn, d)
            conn.execute("COMMIT")
        finally:
            conn.close()
        _mark(None)
    except sqlite3.Error as e:
        _mark("throttle: %r" % e)
        with _lock:                      # degraded: space against ourselves only
            now = time.time()
            wait = max(0.0, (_last_request + gap) - now)
            _state["throttled_seconds"] = round(
                _state["throttled_seconds"] + wait, 1)
            _last_request = now + wait
    if wait > 0:
        time.sleep(wait)


def _record(ok, reason=None, rate_limited=False):
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    opened_reason = None
    try:
        conn = _gate_conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            d = _read_row(conn)
            d["requests"] += 1
            if rate_limited:
                d["rate_limited"] += 1
            if ok:
                d["consecutive_failures"] = 0
                d["last_success"] = now_iso
                if d["is_open"]:
                    d.update(is_open=0, opened_at=None,
                             reason="recovered at %s" % now_iso)
            else:
                d["consecutive_failures"] += 1
                d["last_failure"] = now_iso
                if (d["consecutive_failures"] >= CIRCUIT_THRESHOLD
                        and not d["is_open"]):
                    opened_reason = ("%d consecutive failures, last: %s"
                                     % (d["consecutive_failures"], reason))
                    d.update(is_open=1, opened_at=time.time(),
                             reason=opened_reason)
            _write_row(conn, d)
            conn.execute("COMMIT")
        finally:
            conn.close()
        _mark(None)
    except sqlite3.Error as e:
        _mark("record: %r" % e)
        with _lock:
            _state["requests"] += 1
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
                    opened_reason = ("%d consecutive failures, last: %s"
                                     % (_state["consecutive_failures"], reason))
                    _state.update(open=True, opened_at=time.time(),
                                  reason=opened_reason)
    if opened_reason:
        _witness("circuit_open", opened_reason)


def set_circuit(is_open: bool, reason: str):
    """Open or close the door by hand, in the shared store.

    This exists so the guard can be tested. A check that cannot be made to
    fail has never been shown to work, so `_tools/prove_circuit_check.py`
    opens the circuit with this, watches quick_check go red, and closes it
    again. Also the manual recovery path when a circuit is stuck open.
    """
    conn = _gate_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        d = _read_row(conn)
        # Written as two branches, not four ternaries. The `else 0` form is
        # what the falsy-defaults sentinel counts, and while these zeros are
        # real values rather than invented ones, raising the ratchet to let
        # my own code through is the exact leniency the ratchet exists to
        # prevent. Cheaper to say it plainly.
        if is_open:
            d.update(is_open=1, opened_at=time.time(), reason=reason,
                     consecutive_failures=CIRCUIT_THRESHOLD)
        else:
            d.update(is_open=0, opened_at=None, reason=reason,
                     consecutive_failures=0)
        _write_row(conn, d)
        conn.execute("COMMIT")
    finally:
        conn.close()
    return circuit_state()


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
        # cooldown elapsed: allow one probe through. In the shared store, so
        # a sibling process does not go on believing the door is shut.
        try:
            set_circuit(False, "cooldown elapsed, probing")
        except sqlite3.Error:
            with _lock:
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
