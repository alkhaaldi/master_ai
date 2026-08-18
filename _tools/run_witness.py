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
import urllib.error
import urllib.request
from datetime import datetime, timedelta

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


# Retention for telegram_sends, declared before the first row
# (STORAGE_POLICY Rule 4):
#   what          one row per send attempt, delivered or not
#   why it grows  alerts: halted cycles, open circuits, zero-fetch runs
#   kept          90 days
#   deleted by    send_telegram itself, on every write
TELEGRAM_KEEP_DAYS = 90


def telegram_credentials():
    """(token, chat_id, where_from) or (None, None, why not).

    THE one resolver, added 2026-08-17. There were four, and they disagreed:

      run_witness        parsed .env directly           -> worked from cron
      server.py          os.getenv, systemd loads .env  -> worked in service
      signal_review      os.environ then ~/.telegram_*  -> the files do not
                                                          exist, and cron
                                                          gives it no env, so
                                                          it logged
                                                          "credentials not
                                                          found" and returned
                                                          False for ever
      kse_data_collector same, but reading TELEGRAM_CHAT_ID, a name .env has
                         never contained - it declares ADMIN_TELEGRAM_ID

    .env first because cron does not load it for us; the environment second
    because systemd does. Both chat-id spellings are accepted, since two
    modules were written against a name the config does not use.
    """
    env = _env()
    token = (env.get("TELEGRAM_BOT_TOKEN")
             or os.environ.get("TELEGRAM_BOT_TOKEN"))
    chat = (env.get("ADMIN_TELEGRAM_ID") or env.get("TELEGRAM_CHAT_ID")
            or os.environ.get("ADMIN_TELEGRAM_ID")
            or os.environ.get("TELEGRAM_CHAT_ID"))
    if not token:
        return None, None, "no TELEGRAM_BOT_TOKEN in .env or the environment"
    if not chat:
        return None, None, ("no ADMIN_TELEGRAM_ID / TELEGRAM_CHAT_ID in .env "
                            "or the environment")
    where = "from .env" if _env().get("TELEGRAM_BOT_TOKEN") else "from the environment"
    return token.strip(), str(chat).strip(), where


def _mask(chat):
    """Last four digits only. The destination matters for diagnosis; the
    whole id does not need to sit in a table."""
    s = str(chat)
    if len(s) <= 4:
        return "***"
    return "***" + s[-4:]


def _log_send(delivered, reason, http_status, chat, caller, text):
    """Every attempt lands here, delivered or not.

    send_telegram already returned the truth; the problem was that the truth
    went to stdout, and stdout from a cron job goes into a log nobody reads.
    An alert that did not arrive, unrecorded, is indistinguishable from an
    alert that was never needed.
    """
    try:
        conn = sqlite3.connect(DB, timeout=15)
        conn.execute("""CREATE TABLE IF NOT EXISTS telegram_sends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sent_at TEXT NOT NULL,
            delivered INTEGER NOT NULL,
            reason TEXT,
            http_status INTEGER,
            chat_masked TEXT,
            caller TEXT,
            text_preview TEXT)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tgs_sent_at"
                     " ON telegram_sends(sent_at)")
        conn.execute(
            "INSERT INTO telegram_sends (sent_at, delivered, reason,"
            " http_status, chat_masked, caller, text_preview)"
            " VALUES (?,?,?,?,?,?,?)",
            (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), int(delivered),
             reason, http_status, _mask(chat) if chat else None, caller,
             str(text)[:120]))
        cutoff = (datetime.utcnow()
                  - timedelta(days=TELEGRAM_KEEP_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("DELETE FROM telegram_sends WHERE sent_at < ?", (cutoff,))
        conn.commit()
        conn.close()
    except Exception as e:
        print("witness: telegram send NOT recorded: %r" % e)


def _caller():
    try:
        import inspect
        for fr in inspect.stack()[1:]:
            mod = os.path.basename(fr.filename)
            if mod != "run_witness.py":
                return "%s:%s" % (mod, fr.lineno)
    except Exception:
        pass
    return "unknown"


def _payload(chat, text, parse_mode):
    """parse_mode is optional and omitted when None, so every existing caller
    sends exactly the bytes it sent before this argument existed."""
    body = {"chat_id": chat, "text": text}
    if parse_mode:
        body["parse_mode"] = parse_mode
    return body


def send_telegram(text: str, parse_mode: str | None = None) -> bool:
    """Direct Bot API send (stdlib only). Returns delivery truthfully, and
    now records the attempt so the truth outlives the stdout it was printed
    to."""
    who = _caller()
    token, chat, where = telegram_credentials()
    if not token:
        print("witness: telegram not configured (%s) - alert NOT sent: %s"
              % (where, text))
        _log_send(False, where, None, None, who, text)
        return False
    try:
        req = urllib.request.Request(
            "https://api.telegram.org/bot%s/sendMessage" % token,
            data=json.dumps(_payload(chat, text, parse_mode)).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            status = r.status
            body = json.loads(r.read().decode())
        # 200 is not delivery. Telegram answers 200 with {"ok": false} for a
        # wrong chat id among others, so the body is the reading, not the code.
        if body.get("ok") is True:
            _log_send(True, None, status, chat, who, text)
            return True
        reason = str(body.get("description"))[:160]
        print("witness: telegram refused: %s - alert text was: %s" % (reason, text))
        _log_send(False, reason, status, chat, who, text)
        return False
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode()).get("description", "")
        except Exception:
            pass
        reason = "HTTP %s %s" % (e.code, str(detail)[:120])
        print("witness: telegram send failed: %s - alert text was: %s" % (reason, text))
        _log_send(False, reason, e.code, chat, who, text)
        return False
    except Exception as e:
        reason = repr(e)[:160]
        print("witness: telegram send failed: %s - alert text was: %s" % (reason, text))
        _log_send(False, reason, None, chat, who, text)
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


def last_ok(source: str, statuses=("success", "idle")):
    """(created_at_utc, run_date) of the newest run that went RIGHT.

    Wider than last_success on purpose. A positions cycle with no open
    positions logs 'idle': it fetched nothing because there was nothing to
    fetch, which is a correct outcome, not a failure. Judging freshness on
    'success' alone means the guard turns red 26 hours after the user closes
    their last position and stays red - blaming the cycle for the portfolio
    being empty.
    """
    conn = sqlite3.connect(DB, timeout=15)
    marks = ",".join("?" * len(statuses))
    row = conn.execute(
        "SELECT created_at, run_date FROM data_fetch_runs"
        " WHERE source=? AND status IN (%s)"
        " ORDER BY id DESC LIMIT 1" % marks, (source, *statuses)).fetchone()
    conn.close()
    return row


def sessions_since_last_ok(source: str, statuses=("success", "idle")):
    """(sessions_old, created_at) for the newest run that went right.

    Sessions, not hours, by the 2026-08-15 rule: a last reading taken while
    the market was open is the freshest that CAN exist once it closes, and
    counting wall-clock hours through a weekend turns that into a fault.
    """
    row = last_ok(source, statuses)
    if not row:
        return None, None
    from price_source import _sessions_since, _parse_as_of
    dt = _parse_as_of(row[0])
    if dt is None:
        return None, row[0]
    return _sessions_since(dt, datetime.utcnow()), row[0]


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
