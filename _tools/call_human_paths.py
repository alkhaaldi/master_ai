#!/usr/bin/env python3
"""Call every page-reachable endpoint and ask the only question that matters:
when it cannot answer, does it SAY so, or does it hand back zeros?

Reading the code missed this twice (analysis.html, check_symbol), so this
reads nothing. It calls.

Verdicts:
  loud      carries an explicit error / state / layer_state / *_reason
  suspect   no state field AND its numbers are all zero or all null
  ok        no state field, but real numbers came back
  expensive skipped on purpose, with the reason
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = "http://localhost:9000"
KEY = open(os.path.expanduser("~/.master_ai_key")).read().strip()

# Endpoints deliberately not called, and why. Silence here is a decision,
# not an oversight.
EXPENSIVE = {
    "/api/analyze": "burns a Gemini 2.5 Pro call (~60-120s) per invocation",
    "/api/analyze/refresh": "same as /api/analyze",
    "/api/analyze/refresh-all": "already disabled in code; would be ~128 calls",
}

STATE_KEYS = ("error", "state", "data_state", "source_state", "layer_state",
              "bridge_online", "bridge_status", "status", "degraded",
              "layer_reason", "source_reason", "reason")


def numbers(obj, out=None, depth=0):
    if out is None:
        out = []
    if depth > 6:
        return out
    if isinstance(obj, dict):
        for v in obj.values():
            numbers(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj[:40]:
            numbers(v, out, depth + 1)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        out.append(obj)
    return out


def call(path):
    req = urllib.request.Request(BASE_URL + path, headers={"X-API-Key": KEY})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, None
    except Exception as e:
        return None, {"_transport": repr(e)[:90]}


CONTEXT_KEYS = ("as_of", "as_of_kind", "source", "source_state", "data_state")


def context(payload):
    """Does this endpoint declare its age and its source?

    The second class, and the harder one. A value check cannot find it,
    because every number in it is CORRECT - /dashboard/signals served 131
    real signals for months with no data_state, no source and no as_of, and
    nothing about that payload looked wrong. The only way to see it is to
    ask each endpoint the question directly.

    Endpoints carrying no numbers are not asked: there is nothing to date.
    """
    if not isinstance(payload, dict):
        return "n/a", ""
    if not numbers(payload):
        return "n/a", "no numbers to date"
    have = [k for k in CONTEXT_KEYS if k in payload]
    if not have:
        return "NO CONTEXT", "numbers with no age and no source"
    missing = [k for k in CONTEXT_KEYS if k not in payload]
    if missing:
        return "partial", "missing " + ",".join(missing)
    return "full", "age and source declared"


def classify(payload):
    if payload is None:
        return "unreadable", "response was not JSON"
    flat = payload if isinstance(payload, dict) else {"_list": payload}
    present = [k for k in STATE_KEYS if k in flat]
    nums = numbers(payload)
    all_zero = bool(nums) and all(n == 0 for n in nums)
    if present:
        bits = ", ".join(f"{k}={json.dumps(flat[k], ensure_ascii=False)[:26]}"
                         for k in present[:3])
        if all_zero:
            return "loud", bits + "  [and every number is 0 - check it means it]"
        return "loud", bits
    if not nums:
        return "ok", "no numbers to fake"
    if all_zero:
        return "SUSPECT", f"no state field and all {len(nums)} numbers are 0"
    return "ok", f"{len(nums)} numbers, not all zero"


def main():
    data = json.load(open("/tmp/human_paths.json"))
    routes = data["called_routes"]
    seen, rows = set(), []
    for method, path, handler, rel in sorted(routes, key=lambda r: r[1]):
        if method != "GET" or path in seen:
            continue
        seen.add(path)
        if "{" in path:
            rows.append(("skipped", path, handler, "needs a path parameter",
                         "n/a", ""))
            continue
        if path in EXPENSIVE:
            rows.append(("expensive", path, handler, EXPENSIVE[path],
                         "n/a", "not called"))
            continue
        status, payload = call(path)
        verdict, why = classify(payload)
        if status and status >= 500:
            verdict = "5xx"
            why = f"HTTP {status}"
        ctx, ctx_why = context(payload)
        rows.append((verdict, path, handler, why, ctx, ctx_why))

    order = {"SUSPECT": 0, "5xx": 1, "unreadable": 2, "expensive": 3,
             "skipped": 4, "loud": 5, "ok": 6}
    rows.sort(key=lambda r: (order.get(r[0], 9), r[1]))
    print("=" * 80)
    print("CALLED, not read — every page-reachable GET")
    print("=" * 80)
    last = None
    for verdict, path, handler, why, _c, _cw in rows:
        if verdict != last:
            print(f"\n[{verdict}]")
            last = verdict
        print(f"  {path:<34} {why[:44]}")
    counts = {}
    for v, *_ in rows:
        counts[v] = counts.get(v, 0) + 1
    print("\n" + "-" * 80)
    print("  " + " · ".join(f"{k} {v}" for k, v in sorted(counts.items())))

    print("\n" + "=" * 80)
    print("SECOND CLASS — correct numbers, no context. Does the endpoint")
    print("declare its age and its source? No value check can ask this.")
    print("=" * 80)
    order2 = {"NO CONTEXT": 0, "partial": 1, "full": 2, "n/a": 3}
    last = None
    for _v, path, _h, _w, ctx, ctx_why in sorted(
            rows, key=lambda r: (order2.get(r[4], 9), r[1])):
        if ctx != last:
            print(f"\n[{ctx}]")
            last = ctx
        print(f"  {path:<34} {ctx_why[:42]}")
    c2 = {}
    for r in rows:
        c2[r[4]] = c2.get(r[4], 0) + 1
    print("\n  " + " · ".join(f"{k} {v}" for k, v in sorted(c2.items())))


if __name__ == "__main__":
    main()
