#!/usr/bin/env python3
"""30m bar collection for the rebuilt intraday layer (cron).

The TradingView bridge fed the 30m layer until it was retired 2026-08-16.
yahoo_gate serves 30m for .KW, but it throttles to one request every 2s and
the watchlist is 132 symbols - roughly four and a half minutes a pass. That
is fine on cron and impossible inside an HTTP handler, which is why this is
a separate job and why signal_engine reads the cache instead of fetching.

Writes land in yahoo_bar_cache through yahoo_gate.store_bars. Every run is
recorded in data_fetch_runs so a silent zero-fetch pass is visible the same
way intraday_refresh's is.
"""
import sqlite3
import sys
import time
from datetime import datetime

sys.path.insert(0, "/home/pi/master_ai")
sys.path.insert(0, "/home/pi/master_ai/_tools")

DB = "/home/pi/master_ai/data/life.db"
INTERVAL = "30m"
RANGE = "1mo"


def watchlist():
    c = sqlite3.connect(DB, timeout=10)
    try:
        rows = c.execute(
            "SELECT DISTINCT symbol FROM stock_radar_watchlist "
            "WHERE symbol IS NOT NULL AND symbol <> '' ORDER BY symbol"
        ).fetchall()
    finally:
        c.close()
    return [r[0].upper() for r in rows]


def record_run(fetched, expected, duration, status, error=None):
    c = sqlite3.connect(DB, timeout=10)
    try:
        c.execute(
            "INSERT INTO data_fetch_runs "
            "(run_date, source, status, symbols_fetched, symbols_expected, "
            " duration_sec, error_msg) VALUES (?,?,?,?,?,?,?)",
            (datetime.utcnow().strftime("%Y-%m-%d"), "collect_30m", status,
             fetched, expected, round(duration, 1), error))
        c.commit()
    except Exception as e:
        print("could not record run: %r" % (e,))
    finally:
        c.close()


def main():
    import yahoo_gate

    syms = watchlist()
    if not syms:
        print("watchlist empty - nothing to collect")
        record_run(0, 0, 0.0, "empty", "watchlist empty")
        return 1

    t0 = time.time()
    ok = 0
    blocked = None
    empty = []

    for sym in syms:
        try:
            bars, src = yahoo_gate.chart(sym, interval=INTERVAL, rng=RANGE)
        except Exception as e:
            # YahooBlocked means the circuit is shut; pushing 130 more
            # requests at a shut circuit only deepens the block.
            if type(e).__name__ == "YahooBlocked":
                blocked = repr(e)
                print("circuit shut at %s - stopping: %r" % (sym, e))
                break
            print("  %-12s failed: %r" % (sym, e))
            continue
        if bars:
            ok += 1
        else:
            empty.append(sym)

    dur = time.time() - t0
    if blocked:
        status = "blocked"
    elif ok == 0:
        status = "failed"
    elif ok < len(syms):
        status = "partial"
    else:
        status = "ok"

    record_run(ok, len(syms), dur, status, blocked)
    print("30m collection: %d/%d symbols in %.0fs (%s)" % (ok, len(syms), dur, status))
    if empty:
        print("no bars returned for %d: %s" % (len(empty), ", ".join(empty[:15])))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
