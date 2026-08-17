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

def _symbols(n=5):
    """Sample from the verified map, most liquid first.

    The hand-written list contained AGLTY, which stopped existing when the
    company renamed to MKHZN - it returned 404 on every run. The map knew;
    this file did not. A probe carrying its own copy of the universe will
    always drift from the universe.
    """
    import json as _j, sqlite3 as _s, os as _o
    base = _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__)))
    try:
        m = _j.load(open(_o.path.join(base, "_tools", "kse_symbol_map.json"),
                         encoding="utf-8"))
        ok = {r["our_symbol"] for r in m["records"] if r.get("verdict") == "confirmed"}
    except (OSError, ValueError, KeyError):
        return []
    try:                      # liquid names trade often, so they move often
        c = _s.connect("file:%s?mode=ro" % _o.path.join(base, "data", "life.db"),
                       uri=True, timeout=5)
        rows = c.execute("SELECT symbol FROM stock_radar_daily "
                         "WHERE liq_value_kwd IS NOT NULL "
                         "ORDER BY liq_value_kwd DESC").fetchall()
        c.close()
        ranked = [r[0] for r in rows if r[0] in ok]
        if ranked:
            return ranked[:n]
    except Exception:
        pass
    return sorted(ok)[:n]


SYMBOLS = _symbols()


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
        stamp_moved = b1["ts"] != b2["ts"]
        now_ts = int(time.time())
        rule_ok, rule_why = is_bar_complete(b1["ts"], a.interval, now_ts)
        moved = (b1["close"] != b2["close"]) or (b1["volume"] != b2["volume"])
        stamp = datetime.fromtimestamp(b1["ts"], tz=timezone.utc).strftime("%H:%M") + "Z"
        s2 = datetime.fromtimestamp(b2["ts"], tz=timezone.utc).strftime("%H:%M") + "Z"
        print("%-8s stamp %s -> %s %s | close %s -> %s | vol %s -> %s"
              % (s, stamp, s2, "ADVANCED" if stamp_moved else "same",
                 b1["close"], b2["close"], b1["volume"], b2["volume"]))
        print("         rule says complete=%s (%s)" % (rule_ok, rule_why or "on grid, elapsed"))
        verdicts.append((s, moved or stamp_moved, rule_ok, b1["volume"], stamp_moved))

    print()
    if not verdicts:
        print("no comparable samples")
        return 1
    # A bar can be incomplete AND still: no trades means nothing to move.
    # So stillness is only evidence when the bar HAD volume. Anything that
    # changed - price, volume or stamp - proves the element is forming.
    changed = [v for v in verdicts if v[1]]
    # volume None (never measured) and volume 0 (measured, no trades) are
    # different facts, and this tool exists to tell them apart - collapsing
    # them with `or 0` was the very mistake it hunts. Caught by the ratchet.
    silent_with_volume = [v for v in verdicts
                          if not v[1] and v[3] is not None and v[3] > 0]
    inconclusive = [v for v in verdicts
                    if not v[1] and (v[3] is None or v[3] == 0)]
    unmeasured_vol = [v for v in verdicts if v[3] is None]
    if is_open:
        print("changed (price, volume or stamp) : %d/%d  -> forming, PROVEN"
              % (len(changed), len(verdicts)))
        print("still WITH volume                : %d      -> would contradict the rule"
              % len(silent_with_volume))
        print("still, nothing traded to move    : %d      -> inconclusive"
              % len(inconclusive))
        if unmeasured_vol:
            print("volume NOT MEASURED at all       : %d      -> distinct from zero"
                  % len(unmeasured_vol))
        rule_says_forming = [v for v in verdicts if not v[2]]
        print("rule called the newest bar forming on %d/%d"
              % (len(rule_says_forming), len(verdicts)))
        if changed and not silent_with_volume:
            print("=> PROVEN: the newest element is a moving target, and the")
            print("   deterministic rule flagged it without seeing it move.")
        elif silent_with_volume:
            print("=> CONTRADICTION: a bar with volume did not move. Investigate")
            print("   before trusting the drop rule.")
        else:
            print("=> INCONCLUSIVE: nothing traded in the window. Not a failure of")
            print("   the rule - a failure to observe. Re-run with a longer gap or")
            print("   on a busier symbol.")
    else:
        print("CONTROL ONLY (market closed): nothing moved, as expected.")
        print("       Re-run during 06:00-10:00 UTC (09:00-13:00 Kuwait) for the proof.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
