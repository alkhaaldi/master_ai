#!/usr/bin/env python3
"""Proof-of-life witness for the scheduled Yahoo fetchers.

The rule this file exists to enforce, by user decision 2026-08-15: a data
source without a liveness trail dies silently, like its predecessor. Every
run is recorded in data_fetch_runs (when, how many rows, errors or not);
a zero-result run or a missed trading day raises a Telegram alert; and
quick_check surfaces the age of the last successful fill in sessions.
"""
import json
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
DB = os.path.join(BASE, "data", "life.db")


def _env():
    """KEY=VALUE pairs from .env - cron does not load it for us."""
    out = {}
    try:
        with open(os.path.join(BASE, ".env"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def send_telegram(text: str) -> bool:
    """Direct Bot API send (stdlib only). Returns delivery truthfully."""
    env = _env()
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("ADMIN_TELEGRAM_ID")
    if not token or not chat:
        print("witness: telegram not configured - alert NOT sent:", text)
        return False
    try:
        req = urllib.request.Request(
            "https://api.telegram.org/bot%s/sendMessage" % token,
            data=json.dumps({"chat_id": chat, "text": text}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except Exception as e:
        print("witness: telegram send failed: %r - alert text was: %s" % (e, text))
        return False


def log_run(source: str, status: str, fetched: int, expected: int,
            duration: float, error: str | None) -> None:
    conn = sqlite3.connect(DB, timeout=15)
    conn.execute(
        "INSERT INTO data_fetch_runs (run_date, source, status,"
        " symbols_fetched, symbols_expected, duration_sec, error_msg)"
        " VALUES (?,?,?,?,?,?,?)",
        (datetime.utcnow().strftime("%Y-%m-%d"), source, status,
         fetched, expected, round(duration, 1), error))
    conn.commit()
    conn.close()


def last_success(source: str):
    """(created_at_utc_str, run_date) of the newest successful run, or None."""
    conn = sqlite3.connect(DB, timeout=15)
    row = conn.execute(
        "SELECT created_at, run_date FROM data_fetch_runs"
        " WHERE source=? AND status='success' AND symbols_fetched > 0"
        " ORDER BY id DESC LIMIT 1", (source,)).fetchone()
    conn.close()
    return row


def recent_statuses(source: str, n: int = 2, today_only: bool = False):
    """Newest-first statuses for a source. Feeds the kill switch: a job that
    fires every 2 minutes must be able to see its own recent history, since
    each cron run is a fresh process with no memory of the last one.

    today_only scopes to this run_date so a halt lasts the session, not
    forever - tomorrow starts clean with nobody having to reset anything.
    """
    conn = sqlite3.connect(DB, timeout=15)
    if today_only:
        rows = conn.execute(
            "SELECT status FROM data_fetch_runs WHERE source=? AND run_date=?"
            " ORDER BY id DESC LIMIT ?",
            (source, datetime.utcnow().strftime("%Y-%m-%d"), n)).fetchall()
    else:
        rows = conn.execute(
            "SELECT status FROM data_fetch_runs WHERE source=?"
            " ORDER BY id DESC LIMIT ?", (source, n)).fetchall()
    conn.close()
    return [r[0] for r in rows]


def runs_today(source: str, status: str = "success") -> int:
    conn = sqlite3.connect(DB, timeout=15)
    n = conn.execute(
        "SELECT COUNT(*) FROM data_fetch_runs WHERE source=? AND status=?"
        " AND run_date=?",
        (source, status, datetime.utcnow().strftime("%Y-%m-%d"))).fetchone()[0]
    conn.close()
    return n


def sessions_since_last_success(source: str):
    """(sessions_old, created_at) - session-aged, exchange calendar.
    (None, None) means no successful run was ever recorded."""
    row = last_success(source)
    if not row:
        return None, None
    from price_source import _sessions_since, _parse_as_of
    dt = _parse_as_of(row[0])
    if dt is None:
        return None, row[0]
    return _sessions_since(dt, datetime.utcnow()), row[0]


def is_trading_day(now_utc=None) -> bool:
    from price_source import _kse_local, _KSE_TRADING_WEEKDAYS
    loc = _kse_local(now_utc or datetime.utcnow())
    return loc.weekday() in _KSE_TRADING_WEEKDAYS
