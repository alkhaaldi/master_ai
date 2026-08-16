#!/usr/bin/env python3
"""Prove the last bar is forming: fetch twice, spaced, and diff it.

User requirement (2026-08-16): do not compute indicators on the current
bar. The rule in indicators.is_bar_complete() is deterministic (on-grid +
elapsed), but a rule nobody tested is an assumption. This measures it.

    while the market is OPEN  -> the last bar's close/volume MOVES
                                 between two fetches. That is the proof.
    while the market is SHUT  -> nothing moves. That is only a control:
                                 it cannot prove the rule, and this tool
                                 says so instead of claiming a pass.

Run:  python3 _tools/bar_completeness_probe.py [--gap 120] [--interval 30m]
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, "/home/pi/master_ai")
from price_source import _yahoo_opener, _UA, YAHOO_TIMEOUT
from indicators import is_bar_complete, KSE_OPEN_UTC_H, KSE_CLOSE_UTC_H, \
    KSE_TRADING_WEEKDAYS

SYMBOLS = ["KFH", "NBK", "ZAIN"]


def market_open(now=None):
    n = now or datetime.now(timezone.utc)
    return (n.weekday() in KSE_TRADING_WEEKDAYS
            and KSE_OPEN_UTC_H <= n.hour < KSE_CLOSE_UTC_H)


def fetch_last_bars(sym, interval, n=3):
    url = ("https://query2.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(sym + ".KW")
           + "?range=5d&interval=%s" % interval)
    try:
        with _yahoo_opener().open(urllib.request.Request(url, headers=_UA),
                                  timeout=YAHOO_TIMEOUT) as f:
            raw = json.loads(f.read().decode())
    except urllib.error.HTTPError as e:
        return None, ("rate_limited" if e.code == 429 else "http_%d" % e.code)
    except Exception as e:
        return None, type(e).__name__
    res = (raw.get("chart") or {}).get("result")
    if not res:
        return None, "empty_result"
    r = res[0]
    stamps = r.get("timestamp") or []
    q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    bars = []
    for i, ts in enumerate(stamps[-n:], start=max(0, len(stamps) - n)):
        bars.append({"ts": ts,
                     "close": (q.get("close") or [None] * len(stamps))[i],
                     "volume": (q.get("volume") or [None] * len(stamps))[i]})
    return bars, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", type=int, default=120)
    ap.add_argument("--interval", default="30m")
    a = ap.parse_args()

    is_open = market_open()
    print("=" * 88)
    print("BAR COMPLETENESS PROBE  interval=%s  gap=%ds  market=%s  (%s UTC)"
          % (a.interval, a.gap, "OPEN" if is_open else "CLOSED",
             datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")))
    print("=" * 88)
    if not is_open:
        print("NOTE: market is closed. Anything that does not move here proves")
        print("      NOTHING about a forming bar - this run is a control only.")
    print()

    first = {}
    for s in SYMBOLS:
        bars, err = fetch_last_bars(s, a.interval)
        first[s] = (bars, err)
        time.sleep(2)

    print("waiting %ds ..." % a.gap)
    time.sleep(a.gap)

    verdicts = []
    for s in SYMBOLS:
        bars2, err2 = fetch_last_bars(s, a.interval)
        time.sleep(2)
        bars1, err1 = first[s]
        if err1 or err2:
            print("%-8s ERROR %s / %s" % (s, err1, err2))
            continue
        b1, b2 = bars1[-1], bars2[-1]
        now_ts = int(time.time())
        rule_ok, rule_why = is_bar_complete(b1["ts"], a.interval, now_ts)
        moved = (b1["close"] != b2["close"]) or (b1["volume"] != b2["volume"])
        stamp = datetime.fromtimestamp(b1["ts"], tz=timezone.utc).strftime("%H:%M") + "Z"
        print("%-8s last bar %s | close %s -> %s | vol %s -> %s | MOVED=%s"
              % (s, stamp, b1["close"], b2["close"], b1["volume"], b2["volume"], moved))
        print("         rule says complete=%s (%s)" % (rule_ok, rule_why or "on grid, elapsed"))
        verdicts.append((s, moved, rule_ok))

    print()
    if not verdicts:
        print("no comparable samples")
        return 1
    agree = all((moved != ok) for _s, moved, ok in verdicts)
    if is_open:
        moved_any = any(m for _s, m, _o in verdicts)
        print("PROOF: last bar moved between fetches on %d/%d symbols"
              % (sum(1 for _s, m, _o in verdicts if m), len(verdicts)))
        print("       rule agreed with observation on all symbols: %s" % agree)
        if moved_any and agree:
            print("       => the deterministic rule matches reality. Dropping the")
            print("          last bar is correct and now demonstrated, not assumed.")
    else:
        print("CONTROL ONLY (market closed): nothing moved, as expected.")
        print("       rule currently says complete=%s for the newest bar."
              % [ok for _s, _m, ok in verdicts])
        print("       Re-run during 06:00-10:00 UTC (09:00-13:00 Kuwait) for the proof.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
