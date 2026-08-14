#!/usr/bin/env python3
"""Sunday verification for the P0-B changes. WRITE-ONLY-ON-DEMAND.

The steps are tied to clock times, so run them one at a time:

    venv/bin/python3 _tools/verify_sunday.py --step 1     # any time after restart
    venv/bin/python3 _tools/verify_sunday.py --step 2     # ~10:35 local
    venv/bin/python3 _tools/verify_sunday.py --step 3     # ~11:00, market open
    venv/bin/python3 _tools/verify_sunday.py --step 4     # right after step 3
    venv/bin/python3 _tools/verify_sunday.py --step 5     # ~13:35
    venv/bin/python3 _tools/verify_sunday.py --step 6     # any time
    venv/bin/python3 _tools/verify_sunday.py --step 7     # after 13:00, bridge up
    venv/bin/python3 _tools/verify_sunday.py --step 8     # ~12:50, before the close
    venv/bin/python3 _tools/verify_sunday.py --step 9     # ~13:45

Steps 1, 2, 5, 6, 8, 9 only observe. Steps 3, 4 and 7 deliberately call
refresh_daily_snapshot and will write to stock_radar_daily when they succeed.

Step 7 is the real test: the first successful pull since 2026-04-02.

Steps 8 and 9 watch the trading-brain scheduler, which was corrected on
2026-08-14. Until then isoweekday() <= 4 meant Mon-Thu, so snapshot_signals and
evaluate_pending_signals had never once run on a Sunday, and both windows fired
three hours early. This is their first Sunday, on live data - nobody knows yet
what they do with it.
"""
import argparse
import os
import sqlite3
import sys
import urllib.request
import json
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
LIFE_DB = os.path.join(BASE, "data", "life.db")
SERVER_LOG = os.path.join(BASE, "server.log")
ENV_FILE = os.path.join(BASE, ".env")

TRIP_PHRASES = ("Bridge offline", "Bridge unreachable", "Bridge circuit open")


def utc_now():
    """DB columns are UTC; the Pi's clock is Asia/Kuwait. See CLAUDE_CONTEXT.md."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def api_key():
    for line in open(ENV_FILE, encoding="utf-8", errors="replace"):
        if line.startswith("MASTER_AI_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("MASTER_AI_API_KEY missing from .env")


def get_json(path):
    req = urllib.request.Request(
        f"http://127.0.0.1:9000{path}", headers={"X-API-Key": api_key()}
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def post_json(path, timeout=600):
    req = urllib.request.Request(
        f"http://127.0.0.1:9000{path}", headers={"X-API-Key": api_key()}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def q(sql, params=()):
    conn = sqlite3.connect(f"file:{LIFE_DB}?mode=ro", uri=True, timeout=10)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def log_lines_today(*phrases):
    """Lines from today's server.log matching any phrase. Timestamps are LOCAL."""
    if not os.path.exists(SERVER_LOG):
        return []
    today = datetime.now().strftime("%Y-%m-%d")
    out = []
    with open(SERVER_LOG, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith(today) and any(p in line for p in phrases):
                out.append(line.rstrip())
    return out


def report(step, ok, msg):
    print(f"[{'PASS' if ok else 'FAIL'}] step {step}: {msg}")
    return 0 if ok else 1


# ---------------------------------------------------------------- steps
def step1():
    """daily_refresh must still be off after the restart."""
    from feature_flags import FeatureFlags
    val = FeatureFlags("data/life.db").is_enabled("daily_refresh")
    return report(1, val is False, f"daily_refresh = {val} (want False)")


def step2():
    """Nothing should fire at 10:30 any more. If something did, a third caller
    exists that we never found."""
    rows = q("SELECT id, status, created_at, error_msg FROM data_fetch_runs "
             "WHERE created_at >= ? ORDER BY id DESC",
             ((utc_now() - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"),))
    started = log_lines_today("Starting daily collection")
    if rows:
        return report(2, False,
                      f"a run was logged despite the flag being off -> THIRD CALLER: {rows}")
    if started:
        return report(2, False, f"collection start logged: {started[-1]}")
    return report(2, True, "no data_fetch_runs row and no collection start in the last 6h")


def step3():
    """While the session runs, an unforced snapshot must refuse."""
    from tv_data import _is_market_open
    from stock_radar import refresh_daily_snapshot
    if not _is_market_open():
        return report(3, False, "market is CLOSED right now - rerun between 09:00 and 13:00")
    res = refresh_daily_snapshot()
    ok = res.get("msg") == "market_open" and res.get("market_was_open") is True
    return report(3, ok, f"refresh() -> {res}")


def step4():
    """force=True must get past the guard and stamp market_was_open=1."""
    from tv_data import _is_market_open
    from stock_radar import refresh_daily_snapshot
    if not _is_market_open():
        return report(4, False, "market is CLOSED right now - rerun between 09:00 and 13:00")
    res = refresh_daily_snapshot(force=True)
    if res.get("msg") == "bridge_no_data":
        return report(4, False,
                      "guard was bypassed but the bridge is down - start it and rerun")
    rows = q("SELECT symbol, captured_at, market_was_open FROM stock_radar_daily "
             "ORDER BY captured_at DESC LIMIT 1")
    ok = bool(rows) and rows[0][2] == 1
    return report(4, ok, f"refresh(force=True) -> {res}; newest row {rows[0] if rows else None}")


def step5():
    """At 13:30 the scheduler must skip loudly, not silently."""
    skipped = log_lines_today("daily_refresh flag off")
    ran = log_lines_today("Starting daily collection")
    if ran:
        return report(5, False, f"it ran instead of skipping: {ran[-1]}")
    if not skipped:
        return report(5, False,
                      "no skip line logged - either 13:30 has not passed yet, or the "
                      "scheduler died silently (check for a traceback in server.log)")
    return report(5, True, skipped[-1])


def step6():
    """A flat trip count only means something when something actually called."""
    status = get_json("/bridge/status")
    circuits = status.get("circuit", {})
    attempts = sum(c.get("attempts", 0) for c in circuits.values())
    blocked = sum(c.get("blocked", 0) for c in circuits.values())
    trips = len(log_lines_today(*TRIP_PHRASES))
    up = int(status.get("uptime_seconds", 0))
    ok = attempts > 0 and trips <= 1
    return report(6, ok,
                  f"attempts={attempts} blocked={blocked} trip_lines_today={trips} "
                  f"uptime={up // 3600}h{up % 3600 // 60}m "
                  f"(want attempts>0 and at most the single trip from the first outage)")


def step7():
    """The real one: bridge started by hand after the close, snapshot succeeds."""
    from tv_data import _is_market_open
    if _is_market_open():
        return report(7, False, "market is still open - wait until after 13:00")
    before = q("SELECT MAX(captured_at) FROM stock_radar_daily")[0][0]
    res = post_json("/daily-snapshot/refresh")
    result = res.get("result", {})
    rows = q("SELECT symbol, captured_at, market_was_open FROM stock_radar_daily "
             "ORDER BY captured_at DESC LIMIT 1")
    newest = rows[0] if rows else None
    ok = result.get("ok", 0) > 0 and newest and newest[2] == 0 and newest[1] != before
    return report(7, ok,
                  f"POST /daily-snapshot/refresh -> {result}; newest row {newest}; "
                  f"previous captured_at {before}")


def step8():
    """snapshot_signals on a Sunday - it has never run on one before.

    isoweekday() <= 4 meant Mon-Thu, so Sunday got no snapshot at all. This is
    the first Sunday it fires, and on live intraday data. signal_time is written
    in local time.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    rows = q("SELECT signal_time, COUNT(*) FROM signal_snapshots "
             "WHERE signal_time LIKE ? GROUP BY substr(signal_time, 1, 13) "
             "ORDER BY signal_time", (today + "%",))
    if not rows:
        return report(8, False,
                      "no snapshot rows for today - either the window has not opened "
                      "yet (09:00) or the scheduler is not firing on Sunday")
    hours = sorted({int(t[11:13]) for t, _ in rows})
    total = sum(n for _, n in rows)
    outside = [h for h in hours if not (9 <= h < 13)]
    ok = not outside
    return report(8, ok,
                  f"{total} snapshot rows today across hours {hours}"
                  f"{'; OUTSIDE the window: ' + str(outside) if outside else ''}. "
                  f"Note: the loop ticks every 10 min and has no 2-hour gate despite "
                  f"its old comment, so a full session is roughly 24 ticks, not 2 "
                  f"(recorded as C-13).")


def step9():
    """evaluate_pending_signals at 13:30, and whether it fires twice.

    The gate is 13:25-13:35, an 11-minute window, while the loop ticks every 10
    minutes - two ticks can land inside it. outcome_evaluated_at is written with
    SQLite CURRENT_TIMESTAMP, which is UTC, unlike signal_time.
    """
    today_utc = utc_now().strftime("%Y-%m-%d")
    rows = q("SELECT outcome_evaluated_at, COUNT(*) FROM signal_snapshots "
             "WHERE outcome_evaluated_at LIKE ? "
             "GROUP BY substr(outcome_evaluated_at, 1, 16) "
             "ORDER BY outcome_evaluated_at", (today_utc + "%",))
    if not rows:
        return report(9, False,
                      "nothing evaluated today - either 13:30 local has not passed "
                      "yet, or the evaluation branch did not fire")
    minutes = [t[:16] for t, _ in rows]
    total = sum(n for _, n in rows)
    distinct_runs = len({m for m in minutes})
    ok = distinct_runs <= 1
    return report(9, ok,
                  f"{total} rows evaluated across {distinct_runs} distinct minute(s) "
                  f"{minutes} (UTC). More than one cluster means the 11-minute gate "
                  f"caught two 10-minute ticks and evaluation ran twice - C-14.")


STEPS = {1: step1, 2: step2, 3: step3, 4: step4, 5: step5, 6: step6, 7: step7,
         8: step8, 9: step9}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--step", type=int, choices=sorted(STEPS), required=True)
    args = ap.parse_args()
    print(f"local time {datetime.now():%Y-%m-%d %H:%M %Z} | UTC {utc_now():%H:%M}")
    return STEPS[args.step]()


if __name__ == "__main__":
    sys.exit(main())
