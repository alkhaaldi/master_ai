#!/usr/bin/env python3
"""P0-A: Health watchdog. Standalone — does NOT import server.py.

Checks four facts and sends a Telegram alert only when a check changes to FAIL
(or is still failing after RENOTIFY_HOURS). Results are persisted to
data/health.db so the dashboard can read them later.

Run:  venv/bin/python3 health_watchdog.py [--dry-run] [--verbose]

Rule for this file: no silent failures. A check that raises becomes a FAIL
carrying the exception text; a watchdog-level failure exits non-zero.
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import traceback
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
LIFE_DB = os.path.join(BASE, "data", "life.db")
AUDIT_DB = os.path.join(BASE, "data", "audit.db")
HEALTH_DB = os.path.join(BASE, "data", "health.db")
SERVER_LOG = os.path.join(BASE, "server.log")
ENV_FILE = os.path.join(BASE, ".env")

# thresholds
DATA_FETCH_MAX_AGE_H = 48
RADAR_DAILY_MAX_AGE_H = 48
APPROVAL_BACKLOG_MAX = 10
BRIDGE_WINDOW_H = 24
BRIDGE_MAX_OFFLINE_LINES = 0   # bridge is manual-only: any retry loop is a bug
RENOTIFY_HOURS = 24            # still-failing reminder interval
NOTIFY_RECOVERY = True         # also announce FAIL -> OK

LOG_TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


# ---------------------------------------------------------------- helpers
def load_env(path):
    """Read KEY=VALUE lines. Missing file is fatal — we need the TG token."""
    env = {}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def parse_ts(value):
    """Parse the timestamp formats actually present in these tables.

    data_fetch_runs.created_at -> '2026-08-13 07:30:00'
    stock_radar_daily.updated_at -> '2026-04-02T07:40:36.694769'
    Raises ValueError if unparseable — never guesses.
    """
    if value is None:
        raise ValueError("timestamp is NULL")
    text = str(value).strip().replace("T", " ")
    if "." in text:
        text = text.split(".", 1)[0]
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


def age_hours(ts):
    return (datetime.now() - ts).total_seconds() / 3600.0


def query_one(db_path, sql, params=()):
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"database missing: {db_path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


# ---------------------------------------------------------------- checks
def check_data_fetch_success():
    """1. Last successful data_fetch_runs younger than 48h?"""
    row = query_one(
        LIFE_DB,
        "SELECT id, created_at FROM data_fetch_runs "
        "WHERE status = 'success' ORDER BY id DESC LIMIT 1",
    )
    if not row:
        return False, "no successful data_fetch_runs row exists at all"
    age = age_hours(parse_ts(row[1]))
    ok = age < DATA_FETCH_MAX_AGE_H
    return ok, f"last success id={row[0]} at {row[1]} ({age:.1f}h ago, limit {DATA_FETCH_MAX_AGE_H}h)"


def check_bridge_quiet():
    """2. Bridge is manual-only, so any retry-loop chatter is a bug."""
    if not os.path.exists(SERVER_LOG):
        return False, f"server.log missing at {SERVER_LOG} — cannot verify bridge quiet"
    cutoff = datetime.now() - timedelta(hours=BRIDGE_WINDOW_H)
    hits = 0
    last_seen = None
    with open(SERVER_LOG, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "Bridge offline" not in line:
                continue
            m = LOG_TS.match(line)
            if not m:
                continue
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            if ts >= cutoff:
                hits += 1
                last_seen = m.group(1)
    ok = hits <= BRIDGE_MAX_OFFLINE_LINES
    detail = f"{hits} 'Bridge offline' lines in last {BRIDGE_WINDOW_H}h (limit {BRIDGE_MAX_OFFLINE_LINES})"
    if last_seen:
        detail += f", last {last_seen}"
    return ok, detail


def check_approval_backlog():
    """3. Approval queue not piling up."""
    row = query_one(
        AUDIT_DB, "SELECT COUNT(*) FROM events WHERE status = 'waiting_approval'"
    )
    count = row[0]
    ok = count < APPROVAL_BACKLOG_MAX
    return ok, f"{count} events waiting_approval (limit {APPROVAL_BACKLOG_MAX})"


def check_radar_daily_age():
    """4. stock_radar_daily freshness."""
    row = query_one(LIFE_DB, "SELECT MAX(updated_at) FROM stock_radar_daily")
    if not row or not row[0]:
        return False, "stock_radar_daily is empty"
    age = age_hours(parse_ts(row[0]))
    ok = age < RADAR_DAILY_MAX_AGE_H
    return ok, f"newest row {row[0]} ({age:.1f}h ago, limit {RADAR_DAILY_MAX_AGE_H}h)"


CHECKS = [
    ("data_fetch_success", check_data_fetch_success),
    ("bridge_quiet", check_bridge_quiet),
    ("approval_backlog", check_approval_backlog),
    ("radar_daily_age", check_radar_daily_age),
]


# ---------------------------------------------------------------- storage
def init_db():
    conn = sqlite3.connect(HEALTH_DB, timeout=10)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS health_status (
               check_name TEXT PRIMARY KEY,
               ok         INTEGER NOT NULL,
               detail     TEXT,
               checked_at TEXT NOT NULL
           )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS health_alert_state (
               check_name    TEXT PRIMARY KEY,
               last_ok       INTEGER NOT NULL,
               last_alert_at TEXT
           )"""
    )
    conn.commit()
    return conn


def should_alert(conn, name, ok):
    """Alert on OK->FAIL, on repeat failure past RENOTIFY_HOURS, and on recovery."""
    row = conn.execute(
        "SELECT last_ok, last_alert_at FROM health_alert_state WHERE check_name = ?",
        (name,),
    ).fetchone()
    if row is None:
        return not ok
    last_ok, last_alert_at = bool(row[0]), row[1]
    if ok:
        return NOTIFY_RECOVERY and not last_ok
    if last_ok:
        return True
    if not last_alert_at:
        return True
    return age_hours(parse_ts(last_alert_at)) >= RENOTIFY_HOURS


def record(conn, name, ok, detail, alerted, now_iso, dry_run=False):
    """Persist check outcome. Under --dry-run the alert state is left untouched,
    so a rehearsal never consumes the real first alert."""
    if dry_run:
        return
    conn.execute(
        "INSERT INTO health_status (check_name, ok, detail, checked_at) VALUES (?,?,?,?) "
        "ON CONFLICT(check_name) DO UPDATE SET ok=excluded.ok, detail=excluded.detail, "
        "checked_at=excluded.checked_at",
        (name, int(ok), detail, now_iso),
    )
    prev = conn.execute(
        "SELECT last_alert_at FROM health_alert_state WHERE check_name = ?", (name,)
    ).fetchone()
    last_alert_at = now_iso if alerted else (prev[0] if prev else None)
    conn.execute(
        "INSERT INTO health_alert_state (check_name, last_ok, last_alert_at) VALUES (?,?,?) "
        "ON CONFLICT(check_name) DO UPDATE SET last_ok=excluded.last_ok, "
        "last_alert_at=excluded.last_alert_at",
        (name, int(ok), last_alert_at),
    )
    conn.commit()


# ---------------------------------------------------------------- telegram
def send_telegram(env, text, dry_run):
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("ADMIN_TELEGRAM_ID", "")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or ADMIN_TELEGRAM_ID missing from .env")
    if dry_run:
        print(f"[dry-run] would send Telegram:\n{text}\n")
        return
    import httpx

    resp = httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram send failed: HTTP {resp.status_code} {resp.text[:200]}")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="run checks, print instead of sending")
    ap.add_argument("--verbose", action="store_true", help="print every check result")
    args = ap.parse_args()

    env = load_env(ENV_FILE)
    conn = init_db()
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    results = []
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as exc:
            ok = False
            detail = f"CHECK RAISED {type(exc).__name__}: {exc}"
            if args.verbose:
                traceback.print_exc()
        results.append((name, ok, detail))

    to_send = []
    for name, ok, detail in results:
        alert = should_alert(conn, name, ok)
        if alert:
            mark = "✅ RECOVERED" if ok else "🔴 FAIL"
            to_send.append(f"{mark} {name}\n   {detail}")
        record(conn, name, ok, detail, alert, now_iso, dry_run=args.dry_run)
        if args.verbose:
            print(f"{'OK  ' if ok else 'FAIL'} {name}: {detail}{'  [alert]' if alert else ''}")

    if to_send:
        body = "master_ai health watchdog — " + now_iso + "\n\n" + "\n\n".join(to_send)
        send_telegram(env, body, args.dry_run)

    conn.close()
    failed = [r for r in results if not r[1]]
    print(json.dumps({"checked_at": now_iso, "failed": len(failed),
                      "total": len(results), "alerts_sent": len(to_send)}))
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # watchdog-level failure must be loud, never swallowed
        traceback.print_exc()
        sys.exit(2)
