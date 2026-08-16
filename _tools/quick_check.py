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
