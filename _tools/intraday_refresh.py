#!/usr/bin/env python3
"""Intraday price refresh - every 15 minutes during the KSE session (cron).

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
from price_source import (_yahoo_opener, _UA, YAHOO_TIMEOUT, _kse_local,
                          _SESSION_OPEN_H, _SESSION_CLOSE_H)

DB = "/home/pi/master_ai/data/life.db"
SOURCE = "yahoo_intraday"


def scope_symbols():
    syms = set()
    try:
        from journal_engine import get_open_trades
        syms |= {t["symbol"].upper() for t in get_open_trades() if t.get("symbol")}
    except Exception as e:
        print("scope: open trades unavailable: %r" % e)
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
        with _yahoo_opener().open(urllib.request.Request(url, headers=_UA),
                                  timeout=YAHOO_TIMEOUT) as f:
            res = json.loads(f.read().decode())["chart"]["result"][0]
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
    if not run_witness.is_trading_day():
        run_witness.log_run(SOURCE, "skipped", 0, 0, time.time() - t0,
                            "not a trading day")
        print("not a trading day - skipped")
        return

    syms = scope_symbols()
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
    run_witness.log_run(SOURCE, status, fetched, len(syms),
                        time.time() - t0, err_txt)
    print("%s: %d/%d fetched, errors=%s" % (SOURCE, fetched, len(syms), err_txt))

    if fetched == 0:
        run_witness.send_telegram(
            "⚠️ التحديث اللحظي: صفر أسعار من %d رمزاً (%s) — المصدر لا يجيب"
            % (len(syms), err_txt or "بلا تفاصيل"))

    # First run of the day: did yesterday's post-close fill happen?
    now_loc = _kse_local(datetime.utcnow())
    if now_loc.hour == _SESSION_OPEN_H and now_loc.minute < 15:
        n, when = run_witness.sessions_since_last_success("yahoo_close")
        if n is None or n > 1:
            run_witness.send_telegram(
                "⚠️ تعبئة الإغلاق لم تجرِ في جلسة الأمس — آخر نجاح: %s (%s جلسة)"
                % (when or "لا يوجد إطلاقاً", n))


if __name__ == "__main__":
    main()
