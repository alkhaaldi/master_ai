#!/usr/bin/env python3
"""Intraday price refresh - two cadences during the KSE session (cron).

  full       */15  every symbol clearing the liquidity floor (117 today)
  positions  */2   open positions only, via --positions-only

The split exists because the two answer different questions: the universe
feeds the ranking, the positions feed live P&L. Measured 2026-08-17: Yahoo's
own delay is a 15-minute FLOOR (18 samples, never once below 15.10). So the
2-minute cycle cuts OUR staleness, never the source's - worst case moves from
~30 minutes to ~17, and no faster. See price_source.SOURCE_DELAY_MINUTES.

Scope, updated by user decision 2026-08-15 (whitelist suspended, C-27):
open positions + every symbol clearing the liquidity floor.
Yahoo serves session prices at a 15-minute delay, free and token-less;
without this the whole session sits yellow (degraded) unless a human
presses refresh. The bridge is NEVER touched here - it is manual-only.

Each symbol's stock_radar_daily row gets price / volume / change_pct and
captured_at stamped from the SOURCE's own market time - never from our
clock - with market_was_open set by whether that stamp falls inside its
own day's session. Indicators are not touched intraday: they are
close-based and belong to the 14:00 post-close run.

Proof of life: every run lands in data_fetch_runs; a zero-fetch run
alerts Telegram; the first run of each day checks that yesterday's
post-close fill actually happened.
"""
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

sys.path.insert(0, "/home/pi/master_ai")
sys.path.insert(0, "/home/pi/master_ai/_tools")

import run_witness
import yahoo_gate
from price_source import (YAHOO_TIMEOUT, _kse_local,
                          _SESSION_OPEN_H, _SESSION_CLOSE_H)

DB = "/home/pi/master_ai/data/life.db"
SOURCE = "yahoo_intraday"
SOURCE_POSITIONS = "yahoo_positions"

# Two consecutive failed cycles stop the day (user condition 2026-08-17).
# A 2-minute job that keeps failing is 120 identical errors per session and
# one alert nobody reads twice; halting says it once and stays quiet. Scoped
# to today's run_date, so tomorrow starts clean without anyone resetting it.
HALT_AFTER_CONSECUTIVE_FAILURES = 2


def scope_symbols(positions_only=False):
    syms = set()
    try:
        from journal_engine import get_open_trades
        syms |= {t["symbol"].upper() for t in get_open_trades() if t.get("symbol")}
    except Exception as e:
        print("scope: open trades unavailable: %r" % e)
        if positions_only:
            # An empty positions cycle and an unreadable journal are different
            # states. Returning [] here would log a clean zero-symbol run and
            # look like "no positions" forever.
            raise
    if positions_only:
        return sorted(syms)
    # whitelist suspended 2026-08-15 (C-27): scope is now every symbol
    # that clears the liquidity floor, straight from the store
    try:
        from risk_engine import RiskEngine
        conn = sqlite3.connect(DB, timeout=15)
        for r in conn.execute(
                "SELECT symbol, price, liq_vol FROM stock_radar_daily"):
            if (r[1] and r[2]
                    and r[1] * r[2] / 1000.0 >= RiskEngine.LIQUIDITY_FLOOR_KWD):
                syms.add(str(r[0]).upper())
        conn.close()
    except Exception as e:
        print("scope: liquidity universe unavailable: %r" % e)
    return sorted(syms)


def fetch_quote(symbol):
    """(price, volume, change_pct, ts_iso, was_open) or (None, err_name)."""
    url = ("https://query2.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(symbol + ".KW") + "?range=5d&interval=1d")
    try:
        res = yahoo_gate.get(url, timeout=YAHOO_TIMEOUT)["chart"]["result"][0]
    except yahoo_gate.YahooBlocked:
        # Kept distinct on purpose: the door was shut, so we never asked.
        # That is not "this symbol has no data".
        return None, "blocked"
    except urllib.error.HTTPError as e:
        return None, ("not_found" if e.code == 404 else
                      "rate_limited" if e.code == 429 else "http_%d" % e.code)
    except urllib.error.URLError:
        return None, "timeout"
    except (OSError, json.JSONDecodeError, KeyError, IndexError, TypeError):
        return None, "bad_payload"
    meta = res.get("meta") or {}
    ts = meta.get("regularMarketTime")
    price = meta.get("regularMarketPrice")
    if not isinstance(ts, int) or price is None:
        return None, "empty_result"
    prev = meta.get("chartPreviousClose")
    chg = round((price / prev - 1) * 100, 2) if prev else None
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    vol = None
    for v in reversed(q.get("volume") or []):
        if v is not None:
            vol = v
            break
    dt = datetime.utcfromtimestamp(ts)
    loc = _kse_local(dt)
    was_open = 1 if _SESSION_OPEN_H <= loc.hour < _SESSION_CLOSE_H else 0
    return (float(price), vol, chg, dt.isoformat() + "+00:00", was_open), None


def main():
    t0 = time.time()
    positions_only = "--positions-only" in sys.argv
    source = SOURCE_POSITIONS if positions_only else SOURCE

    if not run_witness.is_trading_day():
        run_witness.log_run(source, "skipped", 0, 0, time.time() - t0,
                            "not a trading day")
        print("not a trading day - skipped")
        return

    # Kill switch, before anything is fetched.
    recent = run_witness.recent_statuses(source, 2, today_only=True)
    if recent and recent[0] == "halted":
        print("halted earlier today - staying down until tomorrow")
        return
    if (len(recent) >= HALT_AFTER_CONSECUTIVE_FAILURES
            and all(s == "failed" for s in recent[:HALT_AFTER_CONSECUTIVE_FAILURES])):
        run_witness.log_run(source, "halted", 0, 0, time.time() - t0,
                            "%d consecutive failed cycles"
                            % HALT_AFTER_CONSECUTIVE_FAILURES)
        run_witness.send_telegram(
            "⚠️ دورة %s فشلت %d مرات متتالية — أُوقفت لبقية اليوم. "
            "الأسعار لن تتحدّث حتى تُعالَج."
            % (source, HALT_AFTER_CONSECUTIVE_FAILURES))
        print("halting: %d consecutive failures" % HALT_AFTER_CONSECUTIVE_FAILURES)
        return

    try:
        syms = scope_symbols(positions_only=positions_only)
    except Exception as e:
        run_witness.log_run(source, "failed", 0, 0, time.time() - t0,
                            "scope unavailable: %r" % e)
        print("scope unavailable: %r" % e)
        return

    if positions_only and not syms:
        # No open positions is a real, healthy answer - but it is not a
        # successful fetch, and it must not age the freshness check.
        run_witness.log_run(source, "idle", 0, 0, time.time() - t0,
                            "no open positions")
        print("no open positions - nothing to poll")
        return

    conn = sqlite3.connect(DB, timeout=15)
    fetched, errors = 0, {}
    for sym in syms:
        got, err = fetch_quote(sym)
        if err:
            errors.setdefault(err, []).append(sym)
            continue
        price, vol, chg, ts_iso, was_open = got
        conn.execute(
            "UPDATE stock_radar_daily SET price=?, volume=?, change_pct=?,"
            " captured_at=?, updated_at=?, market_was_open=? WHERE symbol=?",
            (price, vol, chg, ts_iso, ts_iso, was_open, sym))
        conn.commit()
        fetched += 1
    conn.close()

    err_txt = "; ".join("%s:%s" % (k, ",".join(v)) for k, v in errors.items()) or None
    status = "success" if fetched > 0 else "failed"
    # The witness records the failures too, not only the wins (user condition
    # 2026-08-17): err_txt rides along on a partial success as well, so a
    # cycle that fetched 4 of 5 does not read as clean.
    run_witness.log_run(source, status, fetched, len(syms),
                        time.time() - t0, err_txt)
    if status == "failed":
        print("cycle FAILED: 0 of %d fetched - %s" % (len(syms), err_txt))
    print("%s: %d/%d fetched, errors=%s" % (source, fetched, len(syms), err_txt))

    # The per-cycle alert belongs to the 15-minute run only. Firing it from a
    # 2-minute job would send an alert every 2 minutes for the whole session -
    # the halt above is the positions cycle's voice, and it speaks once.
    if fetched == 0 and not positions_only:
        run_witness.send_telegram(
            "⚠️ التحديث اللحظي: صفر أسعار من %d رمزاً (%s) — المصدر لا يجيب"
            % (len(syms), err_txt or "بلا تفاصيل"))

    # First run of the day: did yesterday's post-close fill happen?
    # Once a day means the 15-minute run: the 2-minute job passes through this
    # window seven times, and this check would alert on every one of them.
    now_loc = _kse_local(datetime.utcnow())
    if (not positions_only
            and now_loc.hour == _SESSION_OPEN_H and now_loc.minute < 15):
        n, when = run_witness.sessions_since_last_success("yahoo_close")
        if n is None or n > 1:
            run_witness.send_telegram(
                "⚠️ تعبئة الإغلاق لم تجرِ في جلسة الأمس — آخر نجاح: %s (%s جلسة)"
                % (when or "لا يوجد إطلاقاً", n))


if __name__ == "__main__":
    main()
