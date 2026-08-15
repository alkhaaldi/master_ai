#!/usr/bin/env python3
"""Daily decision logging + signal review — Phase 2 Section E-1.

Cron: 14:20 local Sun-Thu, AFTER the 14:00 backfill_daily_bars.py close job
(the reviewer grades against daily_bars, which that job fills from Yahoo).

Steps:
1. scan_opportunities() over stock_radar_daily — logs today's ENTER
   decisions into decision_audit even when nobody opens decisions.html
   (the fix written 2026-03-30 in FIX_AUTO_LOG_DECISIONS.md but never
   applied; that starvation is why the loop was silent for 114 days).
2. review_all_pending() — grades every decision_audit date still
   'pending' against the first available next-session bar. no_data stays
   a first-class result: a missing bar is never converted into a value,
   and the row stays pending for the next session's run.
3. Telegram summary for the most recent reviewed day (daily mode only).
4. run_witness.log_run("signal_review", ...) — proof of life.

--backfill: one-time historical grading — steps 2+4 only, no telegram.
"""
import sqlite3
import sys
import time

sys.path.insert(0, "/home/pi/master_ai")
sys.path.insert(0, "/home/pi/master_ai/_tools")

import run_witness
from signal_review import review_all_pending, _send_review_telegram

DB = "/home/pi/master_ai/data/life.db"


def _scan_and_log_today():
    """Log today's ENTER decisions from the fresh close snapshot."""
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT symbol, price, rsi, vol_ratio, support, resistance, "
        "macd_cross AS macd_state, daily_ema_cross AS ema_state, "
        "stoch_k, adx, atr, bb_squeeze, confluence_score, change_pct "
        "FROM stock_radar_daily").fetchall()
    conn.close()
    from golden_engine import scan_opportunities
    out = scan_opportunities([dict(r) for r in rows])
    return out.get("enter_count", 0), out.get("total_scanned", 0)


def main():
    backfill = "--backfill" in sys.argv
    t0 = time.time()
    err = None
    enter_count = 0

    if not backfill:
        try:
            enter_count, scanned = _scan_and_log_today()
            print("scan: %d ENTER decisions from %d stocks" % (enter_count, scanned))
        except Exception as e:
            err = "scan failed: %s" % e
            print(err)

    summaries = []
    graded = considered = 0
    try:
        summaries = review_all_pending()
        for s in summaries:
            if s.get("status") != "ok":
                continue
            considered += s.get("total_reviewed", 0)
            res = s.get("results", {})
            graded += sum(v for k, v in res.items() if k != "no_data")
            print("reviewed %s: %s" % (s.get("market_date"), res))
    except Exception as e:
        err = ((err + "; ") if err else "") + "review failed: %s" % e
        print(err)

    if not backfill:
        ok = [s for s in summaries if s.get("status") == "ok"]
        if ok:
            latest = max(ok, key=lambda s: s.get("market_date") or "")
            try:
                _send_review_telegram(latest)
            except Exception as e:
                print("telegram failed:", e)

    status = "failed" if err else ("success" if graded or not summaries or considered == 0 else "partial")
    run_witness.log_run("signal_review", status, graded, considered,
                        time.time() - t0, err)
    print("witness: signal_review %s (graded %d / considered %d)"
          % (status, graded, considered))


if __name__ == "__main__":
    main()
