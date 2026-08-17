"""Sort the shipped-nowhere reads into three baskets, without fixing any.

  RENAME   a near-neighbour exists in the payload (rsi vs rsi_14). Cheapest,
           and the class already found by hand on swing.html.
  SHIP     no neighbour, but the name appears in a Python payload builder -
           it was meant to exist and does not reach the wire.
  DELETE   appears nowhere at all - a read of something never built. The page
           is making a promise on the system's behalf.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request

BASE = "/home/pi/master_ai"
KEY = open(os.path.expanduser("~/.master_ai_key")).read().strip()

ns = {}
exec(compile(open(BASE + "/_tools/inventory_field_names.py", encoding="utf-8")
             .read().replace('if __name__ == "__main__":\n    main()', ""),
             "fn", "exec"), ns)


def neighbours(field, shipped):
    """Names in the payload that plausibly mean the same thing."""
    f = field.lower()
    out = []
    for s in shipped:
        sl = s.lower()
        if sl == f:
            continue
        if sl.startswith(f + "_") or f.startswith(sl + "_"):
            out.append(s)
        elif sl.replace("_", "") == f.replace("_", ""):
            out.append(s)
        elif len(f) >= 4 and (f in sl or sl in f):
            out.append(s)
    return sorted(set(out))[:4]


def in_python(field):
    """Does a Python payload builder mention this name as a dict key?"""
    try:
        r = subprocess.run(
            ["grep", "-rl", '"%s"' % field, "--include=*.py", BASE],
            capture_output=True, text=True, timeout=60)
    except Exception:
        return []
    files = [os.path.relpath(p, BASE) for p in r.stdout.split()
             if "_archive" not in p and ".bak" not in p and "/venv/" not in p]
    return files[:3]


def main():
    data = json.load(open("/tmp/field_names.json"))
    cache = {}
    baskets = {"RENAME": [], "SHIP": [], "DELETE": []}
    for page, rec in sorted(data.items()):
        shipped = set()
        for ep in rec["endpoints"]:
            if ep not in cache:
                req = urllib.request.Request("http://localhost:9000" + ep,
                                             headers={"X-API-Key": KEY})
                try:
                    with urllib.request.urlopen(req, timeout=60) as r:
                        cache[ep] = json.load(r)
                except Exception:
                    cache[ep] = None
            if cache[ep] is not None:
                shipped |= ns["keys_of"](cache[ep])
        for field, info in sorted(rec["read_not_shipped"].items()):
            if info["shipped_by"]:
                continue                      # wrong-endpoint bucket, not here
            nb = neighbours(field, shipped)
            if nb:
                baskets["RENAME"].append((page, field, info["lines"][0], nb))
                continue
            py = in_python(field)
            if py:
                baskets["SHIP"].append((page, field, info["lines"][0], py))
            else:
                baskets["DELETE"].append((page, field, info["lines"][0], []))

    print("=" * 78)
    print("TRIAGE — reads whose name is shipped by no endpoint")
    print("=" * 78)
    print("\n  " + " · ".join(f"{k} {len(v)}" for k, v in baskets.items()))
    for name, note in (
            ("RENAME", "a near-neighbour is already on the wire"),
            ("SHIP", "a Python builder names it; it does not reach the wire"),
            ("DELETE", "appears nowhere — the page promises what was never built")):
        print("\n" + "-" * 78)
        print("%s — %s" % (name, note))
        print("-" * 78)
        for page, field, line, extra in baskets[name]:
            tail = ("  -> " + ", ".join(extra)) if extra else ""
            print(f"  {page:26} {field:24} line {line}{tail}")
    json.dump({k: [[p, f, l, e] for p, f, l, e in v] for k, v in baskets.items()},
              open("/tmp/triage45.json", "w"), ensure_ascii=False, indent=1)
    print("\n  full data: /tmp/triage45.json")


if __name__ == "__main__":
    main()
