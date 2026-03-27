#!/usr/bin/env python3
"""
smoke_test.py — Verify radar fields in /dashboard/radar.
Run: python3 _tools/smoke_test.py
"""
import subprocess, json, sys, os

PORT = 9000
API_KEY_FILE = os.path.expanduser("~/.master_ai_key")

PASS = 0
FAIL = 0
WARN = 0

def check(name, ok, detail="", warn=False):
    global PASS, FAIL, WARN
    if warn:
        WARN += 1
        status = "WARN"
    elif ok:
        PASS += 1
        status = "PASS"
    else:
        FAIL += 1
        status = "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"  [{status}] {name}{suffix}")


def get_api_key():
    if os.path.exists(API_KEY_FILE):
        return open(API_KEY_FILE).read().strip()
    return os.environ.get("MASTER_AI_KEY", "")


def main():
    print("=" * 60)
    print("Smoke Test — Radar Fields")
    print("=" * 60)

    api_key = get_api_key()
    cmd = ["curl", "-s", f"http://localhost:{PORT}/dashboard/radar"]
    if api_key:
        cmd += ["-H", f"X-API-Key: {api_key}"]

    try:
        out = subprocess.check_output(cmd, timeout=10, stderr=subprocess.DEVNULL)
        data = json.loads(out)
    except Exception as e:
        print(f"\n  [FAIL] Cannot reach /dashboard/radar: {e}")
        sys.exit(1)

    if "error" in data:
        print(f"\n  [FAIL] Endpoint returned error: {data['error']}")
        sys.exit(1)

    # Required fields (FAIL if missing)
    REQUIRED = {
        "radar_recent_signals": "list",
        "radar_daily_context": "list_or_dict",
        "daily_context_stale": "bool_or_str",
    }
    # Optional fields (WARN if missing)
    OPTIONAL = {
        "daily_context_reason": "str_or_none",
    }

    print()
    for field, _ in {**REQUIRED, **OPTIONAL}.items():
        val = data.get(field, "<<MISSING>>")
        is_optional = field in OPTIONAL

        if val == "<<MISSING>>":
            if is_optional:
                check(field, False, "not in response (optional)", warn=True)
            else:
                check(field, False, "MISSING from response")
            continue

        if isinstance(val, list):
            check(field, True, f"list, count={len(val)}")
        elif isinstance(val, dict):
            check(field, True, f"dict, keys={len(val)}")
        elif isinstance(val, bool):
            check(field, True, f"bool={val}")
        elif val is None:
            check(field, True, "null")
        else:
            check(field, True, f"value={val}")

    print("\n" + "=" * 60)
    total = PASS + FAIL + WARN
    parts = [f"{PASS} passed"]
    if FAIL:
        parts.append(f"{FAIL} failed")
    if WARN:
        parts.append(f"{WARN} warnings")
    print(f"Results: {', '.join(parts)} out of {total}")
    print("=" * 60)
    return FAIL == 0


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
