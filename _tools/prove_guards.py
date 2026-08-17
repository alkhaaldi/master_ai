#!/usr/bin/env python3
"""Prove today's guards can fail — one that cannot go red has never been
shown to work.

Written 2026-08-17, after finding that quick_check's circuit line was green
and STRUCTURALLY incapable of turning red: the gate kept its state in module
globals, so quick_check saw a brand-new door in its own process and reported
"closed, 0 requests" whatever the server or cron was doing. That is worse
than no check - a missing check is visible, a false one reassures.

Every guard here is driven into its failing state on purpose, observed going
red FROM A SEPARATE PROCESS (which is how cron and the operator run it), then
restored.

  yahoo circuit    open the circuit      -> the check must FAIL
  positions cycle  halt today's cycle    -> the check must FAIL
                   age out the cycle     -> the check must FAIL
  db_sanity        break each check in   -> every one must FAIL
                   turn, on a COPY

Restoration runs from a finally block, so an interrupted run does not leave
the door shut or a fake row behind. It does blind the price source for a few
seconds, so do not run it mid-scan.

    python3 _tools/prove_guards.py
"""
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone


def _utcnow():
    """Naive UTC, matching what data_fetch_runs.created_at stores."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

BASE = "/home/pi/master_ai"
DB = BASE + "/data/life.db"
sys.path.insert(0, BASE)

import yahoo_gate  # noqa: E402

ARTIFICIAL = "prove_guards.py — artificial, remove if you see this"
failures = []
_cached_output = None


def quick_check_lines(refresh=True):
    """quick_check's output, from a SEPARATE process. In-process would prove
    nothing about what a fresh interpreter sees."""
    global _cached_output
    if refresh or _cached_output is None:
        r = subprocess.run([BASE + "/venv/bin/python3", BASE + "/_tools/quick_check.py"],
                           capture_output=True, text=True, cwd=BASE, timeout=300)
        _cached_output = r.stdout + r.stderr
    return _cached_output


def line_for(marker):
    for line in quick_check_lines().splitlines():
        if marker in line:
            return line.strip()
    return None


def verdict(marker):
    line = line_for(marker)
    if line is None:
        return None
    m = re.search(r"\[(PASS|FAIL)\]", line)
    return m.group(1) if m else None


def step(what, got, want):
    ok = got == want
    print(f"     want={want!s:<5} got={got!s:<5} "
          f"{'OK' if ok else '*** MISMATCH ***'}  {what}")
    if not ok:
        failures.append(what)


def show(marker):
    print(f"       {line_for(marker)}")


# ───────────────────────────── guard 1: circuit ─────────────────────────
def prove_circuit():
    print("\n[guard] yahoo circuit")
    st = yahoo_gate.circuit_state()
    if not st.get("shared"):
        print("  ABORT: shared gate state unreadable (%s) - without it this "
              "proof is meaningless." % st.get("shared_reason"))
        failures.append("circuit: shared state unreadable")
        return
    if st.get("open"):
        print("  ABORT: circuit already OPEN (%s). Refusing to mask a real "
              "outage with a test." % st.get("reason"))
        failures.append("circuit: already open")
        return
    show("yahoo circuit")
    step("closed -> passes", verdict("yahoo circuit"), "PASS")
    try:
        yahoo_gate.set_circuit(True, ARTIFICIAL)
        step("set_circuit(True) visible in the shared store",
             bool(yahoo_gate.circuit_state().get("open")), True)
        quick_check_lines()
        show("yahoo circuit")
        step("OPEN -> FAILS", verdict("yahoo circuit"), "FAIL")
    finally:
        yahoo_gate.set_circuit(False, "prove_guards.py finished - restored")
        print(f"     restored: open={yahoo_gate.circuit_state().get('open')}")
    quick_check_lines()
    step("closed again -> passes again", verdict("yahoo circuit"), "PASS")


# ────────────────────────── guard 2: positions cycle ────────────────────
def _insert(status, created_at, run_date):
    conn = sqlite3.connect(DB, timeout=15)
    cur = conn.execute(
        "INSERT INTO data_fetch_runs (run_date, source, status, symbols_fetched,"
        " symbols_expected, duration_sec, error_msg, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (run_date, "yahoo_positions", status, 1, 1, 0.0, ARTIFICIAL, created_at))
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def _delete(ids):
    if not ids:
        return
    conn = sqlite3.connect(DB, timeout=15)
    conn.execute("DELETE FROM data_fetch_runs WHERE id IN (%s)"
                 % ",".join("?" * len(ids)), tuple(ids))
    conn.commit()
    conn.close()


def prove_positions_cycle():
    print("\n[guard] positions cycle")
    show("positions cycle")
    base = verdict("positions cycle")
    if base != "PASS":
        print("  ABORT: the check is not green to begin with - fix that first.")
        failures.append("positions cycle: not green at baseline")
        return

    ids = []
    try:
        # (a) a halted day must be loud
        ids.append(_insert("halted", _utcnow().isoformat(sep=" ", timespec="seconds"),
                           _utcnow().strftime("%Y-%m-%d")))
        quick_check_lines()
        show("positions cycle")
        step("halted today -> FAILS", verdict("positions cycle"), "FAIL")
        _delete([ids.pop()])

        # (b) an aged-out cycle must be loud too. The limit is 10 minutes
        # while the session is open and 26 hours once it has closed, so age
        # the newest success past whichever applies right now.
        from price_source import (_kse_local, _SESSION_OPEN_H,
                                  _SESSION_CLOSE_H, _KSE_TRADING_WEEKDAYS)
        loc = _kse_local(_utcnow())
        session_open = (loc.weekday() in _KSE_TRADING_WEEKDAYS
                        and _SESSION_OPEN_H <= loc.hour < _SESSION_CLOSE_H)
        old = _utcnow() - timedelta(minutes=30 if session_open else 60 * 30)
        # the check reads MAX(created_at) of successes, so the real rows must
        # be hidden for this one - park them, then put them straight back
        conn = sqlite3.connect(DB, timeout=15)
        conn.execute("UPDATE data_fetch_runs SET source='yahoo_positions__parked'"
                     " WHERE source='yahoo_positions'")
        conn.commit()
        conn.close()
        ids.append(_insert("success", old.isoformat(sep=" ", timespec="seconds"),
                           old.strftime("%Y-%m-%d")))
        quick_check_lines()
        show("positions cycle")
        step("stale cycle -> FAILS (%s)" % ("session open, >10m"
                                            if session_open else "closed, >26h"),
             verdict("positions cycle"), "FAIL")
    finally:
        _delete(ids)
        conn = sqlite3.connect(DB, timeout=15)
        conn.execute("UPDATE data_fetch_runs SET source='yahoo_positions'"
                     " WHERE source='yahoo_positions__parked'")
        conn.commit()
        left = conn.execute(
            "SELECT COUNT(*) FROM data_fetch_runs WHERE error_msg=?",
            (ARTIFICIAL,)).fetchone()[0]
        conn.close()
        print(f"     restored: {left} artificial row(s) left behind"
              f"{' *** CLEAN UP ***' if left else ''}")
        if left:
            failures.append("positions cycle: artificial rows left behind")
    quick_check_lines()
    step("restored -> passes again", verdict("positions cycle"), "PASS")


# ─────────────────────────── guard 3: db_sanity ─────────────────────────
# Driven on a COPY. VACUUM INTO rather than a file copy, because life.db is
# in WAL mode and a plain copy would miss whatever is still in the log.
def _probe_db():
    path = os.path.join(tempfile.mkdtemp(), "probe.db")
    conn = sqlite3.connect(DB, timeout=30)
    conn.execute("VACUUM INTO ?", (path,))
    conn.close()
    return path


def _db_sanity_lines(db_path):
    env = dict(os.environ, DB_SANITY_DB=db_path)
    r = subprocess.run([BASE + "/venv/bin/python3", BASE + "/_tools/db_sanity.py"],
                       capture_output=True, text=True, cwd=BASE, timeout=300, env=env)
    return r.stdout + r.stderr


def _db_verdict(out, marker):
    for line in out.splitlines():
        if marker in line:
            m = re.search(r"\[(PASS|FAIL)\]", line)
            if m:
                return m.group(1), line.strip()
    return None, None


def prove_db_sanity():
    print("\n[guard] db_sanity — every check, driven red on a copy")
    base_db = _probe_db()
    out = _db_sanity_lines(base_db)

    # Each entry: the check's marker, and the SQL that should turn it red.
    cases = [
        ("stock_radar_events exists", "DELETE FROM stock_radar_events"),
        ("stock_radar_daily exists", "DELETE FROM stock_radar_daily"),
        ("stock_radar_watchlist exists", "DELETE FROM stock_radar_watchlist"),
        ("stock_radar_state exists", "DELETE FROM stock_radar_state"),
        ("stock_radar_daily.price nulls",
         "UPDATE stock_radar_daily SET price=NULL"),
        ("stock_radar_daily.captured_at nulls",
         "UPDATE stock_radar_daily SET captured_at=NULL"),
        ("stock_radar_daily.rsi_divergence nulls",
         "UPDATE stock_radar_daily SET rsi_divergence=NULL"),
        ("open trades entry_date vs created_at",
         "INSERT INTO trades (symbol, status, entry_date, created_at, entry_price,"
         " quantity) VALUES ('PROVE', 'open', DATE(datetime('now','+3 hours')),"
         " datetime('now'), 1, 1)"),
        ("closed trades bookkeeping candidates",
         "INSERT INTO trades (symbol, status, entry_date, exit_date, created_at,"
         " entry_price, quantity) VALUES ('PROVE', 'closed',"
         " DATE(datetime('now','+3 hours')), DATE(datetime('now','+3 hours')),"
         " datetime('now'), 1, 1)"),
    ]

    for marker, sql in cases:
        v, line = _db_verdict(out, marker)
        if v != "PASS":
            print(f"     want=PASS  got={v!s:<5} *** MISMATCH ***  "
                  f"{marker} (baseline)")
            failures.append(f"db_sanity: {marker} not green at baseline")
            continue
        broken = _probe_db()
        c = sqlite3.connect(broken, timeout=30)
        c.execute(sql)
        c.commit()
        c.close()
        v2, line2 = _db_verdict(_db_sanity_lines(broken), marker)
        step(f"{marker}", v2, "FAIL")
        if v2 != "FAIL":
            print(f"       line was: {line2}")


print(__doc__.split("\n\n")[0])
prove_circuit()
prove_positions_cycle()
prove_db_sanity()

print()
if failures:
    print("PROOF FAILED:\n  - " + "\n  - ".join(failures))
    sys.exit(1)
print("PROVEN: every guard above passes when healthy, FAILS when broken, and\n"
      "recovers. They are checks, not decoration.")
