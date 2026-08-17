#!/usr/bin/env python3
"""
quick_check.py — Fast health check after any Master AI change.
Run: python3 _tools/quick_check.py
"""
import subprocess, json, sys, os, ast, time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_KEY_FILE = os.path.expanduser("~/.master_ai_key")
PORT = 9000
CORE_FILES = [
    "server.py", "chat_v7.py", "brain_core.py", "quick_query.py",
    "tg_intent_router.py", "stock_radar.py", "trading_engine.py",
]

PASS = 0
FAIL = 0

SPACE_TARGETS = [
    ("/", "disk", 85.0,
     "the SD card carries the databases, the logs and the git tree, and "
     "SQLite corrupts on a full volume rather than failing cleanly"),
    ("/tmp", "memory", 50.0,
     "tmpfs lives in RAM, not on the card: filling it is memory pressure, "
     "and the OOM killer picks a victim that need not be whatever "
     "overflowed it. prove_guards put 4GB here on 2026-08-17 and the "
     "service survived on luck"),
    ("/mnt/nas-backups", "network", 90.0,
     "an 11TB share does not fill, it VANISHES - and when the CIFS mount "
     "drops, this path stays a plain directory on the SD card while df "
     "reports the root filesystem's free space, so backups keep "
     "'succeeding' onto the card. Mounted-ness is the reading that matters"),
]


def _space_reading(path):
    """(pct_used, state, note). state is 'ok', or why no number is trusted.

    df runs under a timeout because a dropped CIFS mount does not error, it
    HANGS - and a health check that hangs is worse than one that fails.

    QUICK_CHECK_FAKE_SPACE is a test seam, and it announces itself in the
    note so an injected reading can never be mistaken for a real one. Format:
    "/=99,/tmp=88,/mnt/nas-backups=unmounted".
    """
    import subprocess as _sp
    fake = os.environ.get("QUICK_CHECK_FAKE_SPACE")
    if fake:
        for part in fake.split(","):
            if "=" not in part:
                continue
            p, v = part.split("=", 1)
            if p != path:
                continue
            if v == "unmounted":
                return None, "NOT A MOUNT POINT", "INJECTED READING"
            if v == "unreachable":
                return None, "unreadable", "INJECTED READING"
            return float(v), "ok", "INJECTED READING"

    # For the network share, mounted-ness comes first: a plain directory
    # where a mount should be reports the root filesystem and looks healthy.
    if path.startswith("/mnt/") and not os.path.ismount(path):
        return None, "NOT A MOUNT POINT", ("the share is detached; anything "
                                           "written here lands on the SD card")
    try:
        r = _sp.run(["df", "-P", path], capture_output=True, text=True, timeout=8)
    except _sp.TimeoutExpired:
        return None, "unresponsive", "df did not return in 8s - a hung mount"
    lines = r.stdout.strip().splitlines()
    if len(lines) < 2:
        return None, "unreadable", (r.stderr or "df gave no rows").strip()[:80]
    cols = lines[1].split()
    for c in cols:
        if c.endswith("%"):
            return float(c[:-1]), "ok", ""
    return None, "unreadable", "df row carried no percentage"


def check(name, ok, detail=""):
    global PASS, FAIL
    status = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    suffix = f" — {detail}" if detail else ""
    print(f"  [{status}] {name}{suffix}")
    return ok


def get_api_key():
    if os.path.exists(API_KEY_FILE):
        return open(API_KEY_FILE).read().strip()
    return os.environ.get("MASTER_AI_KEY", "")


def curl_json(path, api_key=None):
    """Fetch a local endpoint and return parsed JSON."""
    cmd = ["curl", "-s", f"http://localhost:{PORT}{path}"]
    if api_key:
        cmd += ["-H", f"X-API-Key: {api_key}"]
    try:
        out = subprocess.check_output(cmd, timeout=10, stderr=subprocess.DEVNULL)
        return json.loads(out)
    except Exception as e:
        return {"_error": str(e)}


def main():
    print("=" * 60)
    print("Quick Check — Master AI")
    print("=" * 60)
    api_key = get_api_key()

    # ── 1. Syntax check core files ──
    print("\n[Syntax Check]")
    for fname in CORE_FILES:
        fpath = os.path.join(BASE_DIR, fname)
        if not os.path.exists(fpath):
            check(fname, True, "skipped (not found)")
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                ast.parse(f.read(), filename=fname)
            check(fname, True, "syntax OK")
        except SyntaxError as e:
            check(fname, False, f"line {e.lineno}: {e.msg}")

    # ── 2. Service status ──
    print("\n[Service]")
    try:
        out = subprocess.check_output(
            ["systemctl", "is-active", "master-ai.service"],
            timeout=5, stderr=subprocess.DEVNULL
        ).decode().strip()
        check("master-ai.service", out == "active", out)
    except Exception as e:
        check("master-ai.service", False, str(e))

    # ── 3. /health ──
    print("\n[Endpoints]")
    h = curl_json("/health")
    if "_error" in h:
        check("/health", False, h["_error"])
    else:
        check("/health", h.get("status") == "ok",
              f"v{h.get('version','?')} schema={h.get('schema_version','?')} up={h.get('uptime_seconds',0):.0f}s")

    # ── 4. /dashboard ──
    d = curl_json("/dashboard", api_key)
    if "_error" in d or "error" in d:
        check("/dashboard", False, d.get("error", d.get("_error", "?")))
    else:
        check("/dashboard", True,
              f"cpu={d.get('cpu','?')} mem={d.get('memory','?')} temp={d.get('temperature','?')}")

    # ── 5. /dashboard/extended (no radar fields — they moved to /dashboard/radar) ──
    de = curl_json("/dashboard/extended", api_key)
    if "_error" in de or "error" in de:
        check("/dashboard/extended", False, de.get("error", de.get("_error", "?")))
    else:
        check("/dashboard/extended", True,
              f"OK — {len(de)} fields (radar moved to /dashboard/radar)")

    # ── 5b. /dashboard/radar ──
    dr = curl_json("/dashboard/radar", api_key)
    if "_error" in dr or "error" in dr:
        check("/dashboard/radar", False, dr.get("error", dr.get("_error", "?")))
    else:
        fields = ["radar_enabled", "radar_recent_signals", "radar_daily_context"]
        found = [f for f in fields if f in dr]
        check("/dashboard/radar", len(found) == len(fields),
              f"{len(found)}/{len(fields)} radar fields present")

    # -- 5c. Data feed liveness (proof of life, user decision 2026-08-15) --
    print("")
    print("[Data]")
    try:
        sys.path.insert(0, os.path.join(BASE_DIR, "_tools"))
        import run_witness
        n, when = run_witness.sessions_since_last_success("yahoo_close")
        if n is None:
            check("daily fill age", False,
                  "no successful yahoo_close run ever recorded")
        else:
            check("daily fill age", n <= 3,
                  f"last success {when} UTC - {n} session(s) old")
    except Exception as e:
        check("daily fill age", False, f"witness unavailable: {e}")

    # The 2-minute positions cycle announces its age (user condition
    # 2026-08-17). Rewritten the same day, before it ever misled anyone: the
    # first version aged it in wall-clock hours, 10 minutes during a session
    # and 26 outside one. That is red for ~41 hours EVERY WEEKEND - Thursday's
    # last cycle passes 26h on Friday afternoon - and red again at 09:00 sharp
    # each Sunday, when the limit drops to 10 minutes while the newest cycle
    # is still 68 hours old. A guard that goes red every week for a normal
    # reason becomes "the known red", which is the exact failure this whole
    # session was spent removing.
    #
    # So: sessions, not hours, by the 2026-08-15 rule - and 'idle' counts,
    # because a cycle with no open positions did its job.
    try:
        import sqlite3 as _sq2
        from datetime import datetime as _dt2
        from price_source import (_kse_local, _SESSION_OPEN_H,
                                  _SESSION_CLOSE_H, _KSE_TRADING_WEEKDAYS)
        _pc = _sq2.connect(os.path.join(BASE_DIR, "data", "life.db"))
        _phalt = _pc.execute(
            "SELECT status FROM data_fetch_runs WHERE source='yahoo_positions'"
            " AND run_date=? ORDER BY id DESC LIMIT 1",
            (_dt2.utcnow().strftime("%Y-%m-%d"),)).fetchone()
        _pc.close()
        _sess, _pwhen = run_witness.sessions_since_last_ok("yahoo_positions")
        _loc = _kse_local(_dt2.utcnow())
        _in_hours = (_loc.weekday() in _KSE_TRADING_WEEKDAYS
                     and _SESSION_OPEN_H <= _loc.hour < _SESSION_CLOSE_H)
        # Six minutes of grace after the bell: the cycle fires every two, so
        # before then "nothing yet today" is the schedule, not a fault.
        _mins_in = (_loc.hour - _SESSION_OPEN_H) * 60 + _loc.minute
        _live = _in_hours and _mins_in >= 6
        if _phalt and _phalt[0] == "halted":
            check("positions cycle", False,
                  "HALTED today after consecutive failures - prices are not moving")
        elif _sess is None:
            check("positions cycle", False,
                  "no completed cycle ever recorded (neither a fetch nor an "
                  "idle run with no positions)")
        elif _live:
            _pm = (_dt2.utcnow() - _dt2.fromisoformat(_pwhen)).total_seconds() / 60
            check("positions cycle", _pm <= 10,
                  f"last cycle {_pwhen} UTC - {_pm:.0f}m old "
                  f"(session open {_mins_in}m, limit 10m)")
        else:
            check("positions cycle", _sess <= 1,
                  f"last cycle {_pwhen} UTC - {_sess} session(s) old, limit 1 "
                  f"({'in the opening minutes' if _in_hours else 'market closed'})")
    except Exception as _pe:
        check("positions cycle", False, f"witness unavailable: {_pe}")

    # ── Space: three resources that share one word and nothing else ──
    # Kept apart deliberately. Rolling them into one "disk" check would put a
    # RAM-pressure problem, an SD-card problem and a network problem behind a
    # single number, which is the shape of defect this project keeps finding.
    for _path, _kind, _max_pct, _why in SPACE_TARGETS:
        _pct, _state, _note = _space_reading(_path)
        _name = f"space {_path} ({_kind})"
        if _state != "ok":
            check(_name, False, f"{_state} - {_note}. {_why}")
        else:
            check(_name, _pct <= _max_pct,
                  f"{_pct:.0f}% used, limit {_max_pct:.0f}%"
                  + (f" - {_why}" if _pct > _max_pct else "")
                  + (f" [{_note}]" if _note else ""))

    # F-1.5 + user order 2026-08-16: EVERY backup path announces its
    # age - the shell backups failed silently for 4.5 months into a
    # log nobody read. Red until a path has its first success.
    try:
        import sqlite3 as _sq
        from datetime import datetime as _dt
        _bc = _sq.connect(os.path.join(BASE_DIR, "data", "life.db"))
        for _src in ("nas_backup", "local_backup", "gdrive_backup"):
            _row = _bc.execute(
                "SELECT MAX(created_at) FROM data_fetch_runs "
                "WHERE source=? AND status='success'", (_src,)).fetchone()
            if not _row or not _row[0]:
                check(_src + " age", False, "no successful run ever recorded")
            else:
                _h = (_dt.utcnow() - _dt.fromisoformat(_row[0])).total_seconds() / 3600
                check(_src + " age", _h < 26,
                      f"last success {_row[0]} UTC - {_h:.1f}h old")
        _bc.close()
    except Exception as _be:
        check("backup ages", False, f"witness unavailable: {_be}")


    # Numeric falsy-default ratchet. A new `or 50` or `if x else 40` in a
    # decision path is a new way for an absent reading to become a
    # confident one - the family behind confluence 0, updated_at "",
    # avg_volume 0 and rsi 50. Rising is a FAIL; falling is progress and
    # should be committed with a lowered baseline.
    print("")
    print("[Falsy defaults]")
    try:
        import json as _json, importlib.util as _ilu
        _bl = _json.load(open(os.path.join(BASE_DIR, "_tools", "falsy_baseline.json")))
        _spec = _ilu.spec_from_file_location(
            "fdi", os.path.join(BASE_DIR, "_tools", "falsy_defaults_inventory.py"))
        _m = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_m)
        _d, _o = _m.counts()
        _bd, _bo = _bl["decision_path"], _bl["other"]
        check("decision-path falsy defaults", _d <= _bd,
              f"{_d} vs baseline {_bd}" + (" - NEW ONES ADDED" if _d > _bd
              else " - lowered, update the baseline" if _d < _bd else ""))
        check("other falsy defaults", _o <= _bo, f"{_o} vs baseline {_bo}")
    except Exception as _fe:
        check("falsy defaults", False, f"inventory unavailable: {_fe}")

    # G-3: a shut price source must be visible here, not discovered later.
    # Until 2026-08-17 this could not happen: the gate kept its state in
    # module globals, so importing it here created a brand-new door in
    # quick_check's own process. It reported "closed, 0 requests" whatever
    # the server or cron was doing - green, and structurally unable to go
    # red. Now it reads the shared store, and _tools/prove_guards.py
    # opens the circuit on purpose to show that this line does turn red.
    print("")
    print("[Price source]")
    try:
        sys.path.insert(0, BASE_DIR)
        from yahoo_gate import circuit_state as _cs
        _st = _cs()
        if not _st.get("shared", False):
            # Losing sight of the shared door is its own failure. Reporting
            # this process's private counters as if they were the system's is
            # exactly the defect being removed.
            check("yahoo circuit", False,
                  "shared state unreadable (%s) - this reading is process-local"
                  % _st.get("shared_reason"))
        elif _st.get("open"):
            check("yahoo circuit", False,
                  "OPEN - %s (%ss cooldown remaining)"
                  % (_st.get("reason"), _st.get("cooldown_remaining_s")))
        else:
            # Indexed, not .get(...,0): reaching here means shared state
            # was read, so these keys exist. A default would print a
            # confident 0 for a key that had gone missing.
            check("yahoo circuit", True,
                  "closed, %s requests, %s rate-limited, %s consecutive failures"
                  " (shared, since %s)"
                  % (_st["requests"], _st["rate_limited"],
                     _st["consecutive_failures"], _st["counters_since"]))
    except Exception as _se:
        check("yahoo circuit", False, f"gate unavailable: {_se}")

    # ── 6. Git status ──
    print("\n[Git]")
    try:
        branch = subprocess.check_output(
            ["git", "-C", BASE_DIR, "branch", "--show-current"],
            timeout=5, stderr=subprocess.DEVNULL
        ).decode().strip()
        status = subprocess.check_output(
            ["git", "-C", BASE_DIR, "status", "--porcelain"],
            timeout=5, stderr=subprocess.DEVNULL
        ).decode().strip()
        dirty = len(status.split("\n")) if status else 0
        check("git", True, f"branch={branch} dirty={dirty} files")
    except Exception as e:
        check("git", False, str(e))

    # ── Summary ──
    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"Results: {PASS}/{total} passed, {FAIL} failed")
    print("=" * 60)
    return FAIL == 0


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
