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
  space            inject a full disk,   -> each must FAIL, and the
                   a full tmpfs, a          detached-share case is the
                   detached share           one df alone cannot see
  db_sanity        break each check in   -> every one must FAIL
                   turn, on a COPY
  falsy sentinel   plant a known `or 0`,  -> each count must rise, the
                   then a known `or "id"`    check must FAIL, and the two
                                            families must not bleed
  witness          drive one check red   -> the row must say so, with its
                                            reason and the service uptime
  telegram         refuse a send with an -> the refusal must be recorded.
                   invalid token            Nothing is delivered here.

Restoration runs from a finally block, so an interrupted run does not leave
the door shut or a fake row behind.

It REFUSES to run during a KSE session. The circuit it opens is the real one
and the cycle it halts is the real one, so a run at 10am costs live fetches
on a market the user trades. Pass --force to override, deliberately.

    python3 _tools/prove_guards.py
"""
import os
import re
import shutil
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
WORKDIR = BASE + "/.probe_work"      # on /, never tmpfs - see _probe_db
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


def _park(on):
    """Hide or restore the real yahoo_positions rows, so a synthetic history
    can be laid over them and taken away again without deleting anything."""
    conn = sqlite3.connect(DB, timeout=15)
    if on:
        conn.execute("UPDATE data_fetch_runs SET source='yahoo_positions__parked'"
                     " WHERE source='yahoo_positions'")
    else:
        conn.execute("UPDATE data_fetch_runs SET source='yahoo_positions'"
                     " WHERE source='yahoo_positions__parked'")
    conn.commit()
    conn.close()


def prove_positions_cycle():
    """Four cases, chosen because the FIRST version of this guard failed all
    of the first three: it aged the cycle in wall-clock hours, so it was red
    for ~41 hours every weekend, red at 09:00 every Sunday, and red for ever
    once the user closed their last position. Green in a normal state is not
    the property under test - staying green through normal states is."""
    print("\n[guard] positions cycle")
    show("positions cycle")
    if verdict("positions cycle") != "PASS":
        print("  ABORT: the check is not green to begin with - fix that first.")
        failures.append("positions cycle: not green at baseline")
        return

    ids = []
    try:
        _park(True)

        # 1. HOURS vs SESSIONS, the weekend defect in its smallest form.
        #    27 hours old is past the old 26-hour limit, so the first version
        #    of this guard would have called it broken - but only ONE trading
        #    session has passed, so nothing was missed. This single case is
        #    the whole weekend bug: every Friday afternoon crossed 26 hours
        #    with no session missed at all.
        #    27h is deliberate: it always lands on the previous calendar day,
        #    so at most one session can fall between it and now, whatever
        #    weekday this runs on.
        h27 = _utcnow() - timedelta(hours=27)
        ids.append(_insert("success", h27.isoformat(sep=" ", timespec="seconds"),
                           h27.strftime("%Y-%m-%d")))
        quick_check_lines()
        show("positions cycle")
        step("27h old but 1 session old -> PASSES (old rule said FAIL)",
             verdict("positions cycle"), "PASS")
        _delete([ids.pop()])

        # 2. NO OPEN POSITIONS. The cycle logs 'idle' - it fetched nothing
        #    because there was nothing to fetch. That is a correct outcome.
        idle = _utcnow() - timedelta(minutes=3)
        ids.append(_insert("idle", idle.isoformat(sep=" ", timespec="seconds"),
                           idle.strftime("%Y-%m-%d")))
        quick_check_lines()
        show("positions cycle")
        step("only 'idle' runs, no fetches at all -> PASSES",
             verdict("positions cycle"), "PASS")
        _delete([ids.pop()])

        # 3. THE OPENING MINUTES. Yesterday's cycle, nothing yet today. Inside
        #    the grace window that is the schedule, not a fault.
        y = _utcnow() - timedelta(days=1)
        ids.append(_insert("success", y.isoformat(sep=" ", timespec="seconds"),
                           y.strftime("%Y-%m-%d")))
        quick_check_lines()
        show("positions cycle")
        step("yesterday's cycle, one session old -> PASSES",
             verdict("positions cycle"), "PASS")
        _delete([ids.pop()])

        # 4. AND IT MUST STILL BREAK. Three sessions with no cycle at all is
        #    a real stoppage, weekend arithmetic or not.
        old = _utcnow() - timedelta(days=9)
        ids.append(_insert("success", old.isoformat(sep=" ", timespec="seconds"),
                           old.strftime("%Y-%m-%d")))
        quick_check_lines()
        show("positions cycle")
        step("several sessions with no cycle -> FAILS", verdict("positions cycle"),
             "FAIL")
        _delete([ids.pop()])

        # 5. A halted day is still loud.
        ids.append(_insert("halted", _utcnow().isoformat(sep=" ", timespec="seconds"),
                           _utcnow().strftime("%Y-%m-%d")))
        quick_check_lines()
        show("positions cycle")
        step("halted today -> FAILS", verdict("positions cycle"), "FAIL")
    finally:
        _delete(ids)
        _park(False)
        conn = sqlite3.connect(DB, timeout=15)
        left = conn.execute(
            "SELECT COUNT(*) FROM data_fetch_runs WHERE error_msg=?",
            (ARTIFICIAL,)).fetchone()[0]
        parked = conn.execute(
            "SELECT COUNT(*) FROM data_fetch_runs "
            "WHERE source='yahoo_positions__parked'").fetchone()[0]
        conn.close()
        print(f"     restored: {left} artificial row(s), {parked} still parked")
        if left or parked:
            failures.append("positions cycle: state left behind")
    quick_check_lines()
    step("restored -> passes again", verdict("positions cycle"), "PASS")


# ────────────────────────────── guard 3: space ──────────────────────────
def prove_space():
    """Three resources, three physics, three separate lines.

    Driven with QUICK_CHECK_FAKE_SPACE rather than by actually filling a
    117GB card or a 4GB tmpfs - the seam names itself in the output, so an
    injected reading can never be read as a real one.
    """
    print("\n[guard] space — disk, memory and network kept apart")
    for path, kind, inject, want, why in (
            ("/", "disk", "99", "FAIL", "card nearly full"),
            ("/tmp", "memory", "88", "FAIL", "tmpfs eating RAM"),
            ("/mnt/nas-backups", "network", "95", "FAIL", "share nearly full"),
            ("/mnt/nas-backups", "network", "unmounted", "FAIL",
             "share detached - the case df alone cannot see"),
    ):
        marker = f"space {path} ({kind})"
        env_val = f"{path}={inject}"
        r = subprocess.run(
            [BASE + "/venv/bin/python3", BASE + "/_tools/quick_check.py"],
            capture_output=True, text=True, cwd=BASE, timeout=300,
            env=dict(os.environ, QUICK_CHECK_FAKE_SPACE=env_val))
        got, line = None, None
        for ln in (r.stdout + r.stderr).splitlines():
            if marker in ln:
                m = re.search(r"\[(PASS|FAIL)\]", ln)
                if m:
                    got, line = m.group(1), ln.strip()
        step(f"{marker}: {why}", got, want)
        if got != want:
            print(f"       line was: {line}")
    quick_check_lines()
    for path, kind, _, _ in SPACE_KINDS:
        step(f"space {path} ({kind}) green again with no injection",
             verdict(f"space {path} ({kind})"), "PASS")


SPACE_KINDS = [("/", "disk", None, None), ("/tmp", "memory", None, None),
               ("/mnt/nas-backups", "network", None, None)]


# ─────────────────────────── guard 3: db_sanity ─────────────────────────
# Driven on a COPY. VACUUM INTO rather than a file copy, because life.db is
# in WAL mode and a plain copy would miss whatever is still in the log.
_probe_dirs = []


def _probe_db():
    """A throwaway copy of life.db. Every caller must hand it to _drop_probe.

    life.db is ~87MB and this function is called once per case, so leaking
    them fills a 4GB tmpfs in five runs - which it did on 2026-08-17 before
    the cleanup below existed. A proof tool that degrades the machine it
    runs on is not a proof tool.
    """
    # On /, not tmpfs (STORAGE_POLICY Rule 3, open item 2). tempfile puts
    # these in /tmp by default, which is 4GB of the Pi's RAM - so the copies
    # this tool makes were competing with the service for memory. / has 92GB
    # free and is the right kind of space for a working file.
    os.makedirs(WORKDIR, exist_ok=True)
    d = tempfile.mkdtemp(prefix="probe_", dir=WORKDIR)
    _probe_dirs.append(d)
    path = os.path.join(d, "probe.db")
    conn = sqlite3.connect(DB, timeout=30)
    conn.execute("VACUUM INTO ?", (path,))
    conn.close()
    return path


def _drop_probe(path):
    d = os.path.dirname(path)
    shutil.rmtree(d, ignore_errors=True)
    if d in _probe_dirs:
        _probe_dirs.remove(d)


def _drop_all_probes():
    for d in list(_probe_dirs):
        shutil.rmtree(d, ignore_errors=True)
        _probe_dirs.remove(d)


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
    _drop_probe(base_db)

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
        try:
            c = sqlite3.connect(broken, timeout=30)
            c.execute(sql)
            c.commit()
            c.close()
            v2, line2 = _db_verdict(_db_sanity_lines(broken), marker)
            step(f"{marker}", v2, "FAIL")
            if v2 != "FAIL":
                print(f"       line was: {line2}")
        finally:
            _drop_probe(broken)


# ──────────────────────── guard 6: the telegram channel ─────────────────
def prove_telegram():
    """An alert that does not arrive is not an alert.

    send_telegram already returned the truth; the truth went to stdout, and
    stdout from a cron job goes to a file nobody reads. So a refused alert
    and an alert never needed looked the same from the outside. This proves
    the refusal is now WRITTEN DOWN.

    Nothing is delivered here. The failing case uses a deliberately invalid
    token, which Telegram rejects at the door, so no message reaches any
    chat. Proving successful delivery needs a real send and the user's
    explicit say-so - it is not something a tool should decide to do.
    """
    print("\n[guard] telegram channel")
    sys.path.insert(0, BASE + "/_tools")
    import run_witness as w

    def table_exists():
        c3 = sqlite3.connect(DB, timeout=15)
        try:
            return c3.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
                " AND name='telegram_sends'").fetchone()[0]
        finally:
            c3.close()

    # 1. the credentials resolve at all - and from .env, so cron can send
    tok, chat, where = w.telegram_credentials()
    step("credentials resolve", bool(tok) and bool(chat), True)
    print(f"       {where}, chat {w._mask(chat) if chat else None}")

    # 2. and they resolve with NO environment, which is how cron runs
    r = subprocess.run(
        ["/usr/bin/env", "-i", BASE + "/venv/bin/python3", "-c",
         "import sys;sys.path.insert(0,'" + BASE + "/_tools');"
         "import run_witness as w;t,c,_=w.telegram_credentials();"
         "print(bool(t) and bool(c))"],
        capture_output=True, text=True, timeout=60)
    step("they resolve with an empty environment (the cron case)",
         r.stdout.strip(), "True")

    def newest():
        c2 = sqlite3.connect(DB, timeout=15)
        try:
            return c2.execute(
                "SELECT delivered, reason, http_status, caller FROM telegram_sends"
                " ORDER BY id DESC LIMIT 1").fetchone()
        finally:
            c2.close()

    # 3. a REFUSED send is recorded, with the reason. Invalid token on
    #    purpose: Telegram rejects it before any chat is touched.
    real_env = w._env
    w._env = lambda: dict(real_env(), TELEGRAM_BOT_TOKEN="000000:invalid-on-purpose")
    try:
        sent = w.send_telegram("prove_guards.py — must never be delivered")
    finally:
        w._env = real_env
    step("a refused send returns False", sent, False)
    row = newest()
    step("...and is recorded as not delivered", row[0], 0)
    step("...with a reason, not just a flag", bool(row[1]), True)
    print(f"       delivered={row[0]}  http={row[2]}  reason={str(row[1])[:60]}")
    print(f"       caller recorded as: {row[3]}")

    # Checked here, not at the top: the table is created on first write, so
    # asking before any send has happened tests the wrong moment.
    step("the telegram_sends table exists once something has been attempted",
         table_exists(), 1)


# ─────────────────────── guard 5: quick_check's witness ─────────────────
def prove_witness():
    """Does the witness actually record the red?

    Everything else here proves a guard CAN go red. This proves the red
    survives being seen - the half that was missing when today's 20/21 and
    22/24 both had to be reproduced to be diagnosed, and the second one
    never was.
    """
    print("\n[guard] quick_check witness")
    marker = "space /tmp (memory)"

    def newest(name):
        conn = sqlite3.connect(DB, timeout=15)
        try:
            return conn.execute(
                "SELECT ran_at, passed, detail, service_uptime_s"
                " FROM quick_check_runs WHERE check_name=?"
                " ORDER BY id DESC LIMIT 1", (name,)).fetchone()
        finally:
            conn.close()

    conn = sqlite3.connect(DB, timeout=15)
    try:
        have = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            " AND name='quick_check_runs'").fetchone()[0]
    finally:
        conn.close()
    step("the witness table exists", have, 1)
    if not have:
        return

    # A green run is recorded as green...
    quick_check_lines()
    before = newest(marker)
    step(f"a passing '{marker}' is recorded", before[1], 1)
    print(f"       {before[0]}  passed={before[1]}  uptime={before[3]}s")

    # ...and a red one as red, carrying its reason, not just a lower total.
    subprocess.run([BASE + "/venv/bin/python3", BASE + "/_tools/quick_check.py"],
                   capture_output=True, text=True, cwd=BASE, timeout=300,
                   env=dict(os.environ, QUICK_CHECK_FAKE_SPACE="/tmp=91"))
    after = newest(marker)
    step(f"a failing '{marker}' is recorded as failed", after[1], 0)
    step("and the reason is kept, not only the verdict",
         "91% used" in (after[2] or ""), True)
    print(f"       {after[0]}  passed={after[1]}  detail={(after[2] or '')[:54]}")

    # The uptime is the discriminator this table exists for: without it, a
    # restart artefact and a real fault are the same row.
    step("the service uptime rides along, so a restart artefact is separable",
         isinstance(after[3], float), True)
    print(f"       uptime beside the red: {after[3]}s")

    # And it comes back green, so the table is a log and not a latch.
    quick_check_lines()
    step("green again on the next run", newest(marker)[1], 1)


# ──────────────────────── guard 4: the falsy sentinel ───────────────────
# The ratchet caught three of my own additions during the 2026-08-17 session
# and each was rewritten rather than waived. But being caught three times is
# an anecdote, not a test: nobody had ever put a known violation in front of
# it and required the number to move. The tool that guards the other tools
# was the last one taking its own word for it.
FALSY_PROBE = BASE + "/_tools/_falsy_probe_artificial.py"
FALSY_PROBE_STR_SRC = '''"""ARTIFICIAL - written by prove_guards.py, deleted seconds later."""


def _probe_str(d):
    # The string violation: an absent config becoming a specific destination.
    return d.get("nobody_set_this") or "669769765"
'''
FALSY_PROBE_SRC = '''"""ARTIFICIAL - written by prove_guards.py, deleted seconds later.

If you are reading this file in a checkout, a proof run was interrupted:
delete it. While it exists, quick_check's falsy-defaults line is red on
purpose and the count is one above the committed baseline.
"""


def _probe(d):
    # The violation being proved: an absent reading becoming a confident 0.
    return float(d.get("nothing_is_here") or 0)
'''


def _falsy_counts():
    """(decision_path, other) from a SEPARATE process, so the scan is fresh."""
    code = ("import importlib.util as u;"
            "s=u.spec_from_file_location('f','%s/_tools/falsy_defaults_inventory.py');"
            "m=u.module_from_spec(s);s.loader.exec_module(m);print(*m.counts())"
            % BASE)
    r = subprocess.run([BASE + "/venv/bin/python3", "-c", code],
                       capture_output=True, text=True, cwd=BASE, timeout=300)
    parts = r.stdout.split()
    if len(parts) != 2:
        raise RuntimeError("inventory did not report counts: %r"
                           % (r.stdout + r.stderr)[:200])
    return int(parts[0]), int(parts[1])


def _falsy_counts_str():
    """(decision_path, other) for the string family, from a fresh process."""
    code = ("import importlib.util as u;"
            "s=u.spec_from_file_location('f','%s/_tools/falsy_defaults_inventory.py');"
            "m=u.module_from_spec(s);s.loader.exec_module(m);print(*m.counts_str())"
            % BASE)
    r = subprocess.run([BASE + "/venv/bin/python3", "-c", code],
                       capture_output=True, text=True, cwd=BASE, timeout=300)
    parts = r.stdout.split()
    if len(parts) != 2:
        raise RuntimeError("inventory did not report string counts: %r"
                           % (r.stdout + r.stderr)[:200])
    return int(parts[0]), int(parts[1])


def prove_falsy_sentinel():
    print("\n[guard] falsy-defaults sentinel")
    if os.path.exists(FALSY_PROBE):
        print("  ABORT: %s already exists - an earlier run was interrupted. "
              "Delete it, then re-run." % FALSY_PROBE)
        failures.append("falsy sentinel: stale probe file present")
        return

    marker = "other falsy defaults"
    base_d, base_o = _falsy_counts()
    print(f"       baseline: decision={base_d} other={base_o}")
    show(marker)
    step("baseline -> passes", verdict(marker), "PASS")

    try:
        with open(FALSY_PROBE, "w", encoding="utf-8") as fh:
            fh.write(FALSY_PROBE_SRC)
        d2, o2 = _falsy_counts()
        step(f"one planted `or 0` raises the count ({base_o} -> {o2})",
             o2 - base_o, 1)
        step("decision-path count is untouched", d2 - base_d, 0)
        quick_check_lines()
        show(marker)
        step("count above baseline -> check FAILS", verdict(marker), "FAIL")
    finally:
        if os.path.exists(FALSY_PROBE):
            os.remove(FALSY_PROBE)
        gone = not os.path.exists(FALSY_PROBE)
        print(f"     removed: probe gone={gone}")
        if not gone:
            failures.append("falsy sentinel: probe file left behind")

    d3, o3 = _falsy_counts()
    step(f"count returns to baseline ({o3})", (d3, o3), (base_d, base_o))
    quick_check_lines()
    step("back at baseline -> passes again", verdict(marker), "PASS")

    # The string family, added 2026-08-17. It exists because the numeric
    # sentinel walked past a hardcoded telegram id in 28 places, so it had
    # better be shown to catch the thing it was widened for.
    smarker = "other string defaults"
    base_ds, base_os = _falsy_counts_str()
    print(f"       string baseline: decision={base_ds} other={base_os}")
    step("string baseline -> passes", verdict(smarker), "PASS")
    try:
        with open(FALSY_PROBE, "w", encoding="utf-8") as fh:
            fh.write(FALSY_PROBE_STR_SRC)
        ds2, os2 = _falsy_counts_str()
        step(f'one planted `or "669769765"` raises the string count '
             f"({base_os} -> {os2})", os2 - base_os, 1)
        step("the NUMERIC counts stay put - the families do not bleed",
             _falsy_counts(), (base_d, base_o))
        quick_check_lines()
        show(smarker)
        step("string count above baseline -> check FAILS", verdict(smarker), "FAIL")
    finally:
        if os.path.exists(FALSY_PROBE):
            os.remove(FALSY_PROBE)
    quick_check_lines()
    step("string count back at baseline -> passes again",
         verdict(smarker), "PASS")


def _refuse_during_session():
    """Not during a live session, unless someone says so out loud.

    This tool is not a simulation. It opens the real circuit, so every fetch
    in that window raises YahooBlocked; it writes a real 'halted' row, so a
    positions cycle firing at that moment stands down. Two seconds of open
    circuit at 10am is a scan that never happened, on a market the user
    trades. Outside session hours it costs nothing.
    """
    if "--force" in sys.argv:
        print("  running inside the session by --force, as instructed")
        return
    from price_source import (_kse_local, _SESSION_OPEN_H, _SESSION_CLOSE_H,
                              _KSE_TRADING_WEEKDAYS)
    loc = _kse_local(_utcnow())
    if (loc.weekday() in _KSE_TRADING_WEEKDAYS
            and _SESSION_OPEN_H <= loc.hour < _SESSION_CLOSE_H):
        print(f"\nREFUSING: the KSE session is open ({loc:%H:%M} Kuwait, "
              f"{_SESSION_OPEN_H:02d}:00-{_SESSION_CLOSE_H:02d}:00).")
        print("This tool opens the real circuit and halts the real positions "
              "cycle for a few seconds.\nRun it after the close, or pass "
              "--force if you accept the lost fetches.")
        sys.exit(2)


print(__doc__.split("\n\n")[0])
_refuse_during_session()
try:
    prove_circuit()
    prove_positions_cycle()
    prove_space()
    prove_db_sanity()
    prove_falsy_sentinel()
    prove_witness()
    prove_telegram()
finally:
    # Belt and braces: each case drops its own copy, this catches an
    # interrupted run. 87MB a piece on a 4GB tmpfs is not survivable.
    _drop_all_probes()

print()
if failures:
    print("PROOF FAILED:\n  - " + "\n  - ".join(failures))
    sys.exit(1)
print("PROVEN: every guard above passes when healthy, FAILS when broken, and\n"
      "recovers. They are checks, not decoration.")
