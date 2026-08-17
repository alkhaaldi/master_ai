#!/usr/bin/env python3
"""Inventory only: do the fields a page READS match the fields its endpoint SHIPS?

The third class, after invented numbers and undated numbers. Here the numbers
are correct AND dated AND they arrive - and the page asks for them under a
name nobody ships, so it renders "—" and says nothing. A payload check passes
(the payload is fine). A page check passes (the page does not crash). The only
thing that finds it is comparing the two vocabularies directly.

Found this way on 2026-08-17, in one page: the hero card read
`ts.score ?? ts.confluence_score` while the payload shipped confluence_pct, so
the strongest signal displayed "—" while carrying 90. And `o.rsi` against
rsi_14, `o.name` against name_ar, `p.entry` against entry_price.

Two directions, and they are not equally serious:

  READ NOT SHIPPED   the page wants a name nothing sends. Renders empty,
                     silently. This is the dangerous one.
  SHIPPED NOT READ   the endpoint sends something no page looks at. Wasted
                     payload, or a feature that was built and never wired.

Fallbacks matter: `o.rsi_14 ?? o.rsi` reads an unshipped name harmlessly
because a shipped one sits beside it. Those are reported separately as
`covered`, judged per line rather than dropped, because a chain whose FIRST
name is missing is still a smell.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict

BASE = "/home/pi/master_ai"
WWW = os.path.join(BASE, "www")
KEY = open(os.path.expanduser("~/.master_ai_key")).read().strip()

# Not payload fields: JS builtins, DOM, and our own helpers.
STOP_OBJ = {
    "document", "window", "Math", "JSON", "console", "Object", "Array",
    "String", "Number", "Date", "Promise", "localStorage", "sessionStorage",
    "location", "navigator", "history", "e", "ev", "err", "res", "resp",
    "el", "node", "style", "classList", "dataset", "this", "self",
}
STOP_FIELD = {
    "length", "className", "textContent", "innerHTML", "innerText", "value",
    "style", "classList", "dataset", "hidden", "checked", "target", "id",
    "parentNode", "children", "firstChild", "ok", "status", "statusText",
    "then", "catch", "finally", "prototype", "constructor", "name",
    "message", "stack", "size", "type", "key", "code", "detail",
    # DOM handlers and layout props that survived the first pass
    "onclick", "onchange", "oninput", "disabled", "selected", "scrollTop",
    "offsetWidth", "offsetHeight", "files", "result", "data",
}
# The lookbehind is the point. Without it this matched inside URLs
# ("googleapis.com"), filenames ("swing.html") and CSS selectors (".ic"), and
# reported every one of them as a payload read that nothing ships.
ACCESS = re.compile(r"""(?<![\w/'"`.])([A-Za-z_$][\w$]*)\.([A-Za-z_][\w]*)\b(?!\s*\()""")
# The trailing segment is OPTIONAL. It was mandatory until 2026-08-17, so a
# page fetching bare '/dashboard' was recorded as fetching nothing from it -
# and every field that lives there came back as READ NOT SHIPPED. That
# produced a confident "25 pages point at the wrong URL" finding about two
# pages that were fetching it correctly all along.
URLPAT = re.compile(r"""['"`](/(?:api|dashboard)(?:/[A-Za-z0-9_\-/]*)?)['"`]""")


def script_text(path):
    html = open(path, encoding="utf-8", errors="replace").read()
    return "\n".join(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
                                html, re.S))


def page_reads(path):
    """{field: [line numbers]} for every x.field access that could be a payload
    read. Over-reports; that is the safe direction for a sweep."""
    out = defaultdict(list)
    src = script_text(path)
    for i, line in enumerate(src.splitlines(), 1):
        if line.lstrip().startswith(("//", "/*", "*")):
            continue
        for obj, field in ACCESS.findall(line):
            if obj in STOP_OBJ or field in STOP_FIELD:
                continue
            if obj.startswith("$") or obj[0].isupper():
                continue
            # locals, not payload: a leading underscore is this codebase's
            # convention for a page-local, and a one-letter field name is
            # never a wire field here
            if field.startswith("_") or len(field) < 2:
                continue
            out[field].append(i)
    return out, src.splitlines()


def page_urls(path):
    return sorted(set(URLPAT.findall(open(path, encoding="utf-8",
                                          errors="replace").read())))


SAMPLE_VALUE = "NBK"
SAMPLES = {"symbol": SAMPLE_VALUE, "sym": SAMPLE_VALUE, "ticker": SAMPLE_VALUE,
           "id": "1"}


def concrete(url):
    """A parameterised route with a real value, or None if we cannot guess one.

    Skipping these was a silent hole: personality.html fetches
    /api/stocks/symbol/{symbol}, so all sixteen detailed-profile fields it
    reads were counted as shipped by nothing.
    """
    # A trailing slash means the page CONCATENATES the value:
    # `fetch('/api/stocks/symbol/' + sym)`. The literal in the source carries
    # no {param} at all, so a brace-substitution alone never fired and the
    # route was silently never called - which is how sixteen fields that ARE
    # shipped came back as shipped by nothing.
    if url.endswith("/") and url.count("/") > 2:
        return url + SAMPLE_VALUE
    if "{" not in url:
        return url
    def sub(m):
        return SAMPLES.get(m.group(1), SAMPLE_VALUE)
    filled = re.sub(r"\{(\w+)\}", sub, url)
    return filled if "{" not in filled else None


def call(path):
    req = urllib.request.Request("http://localhost:9000" + path,
                                 headers={"X-API-Key": KEY})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def keys_of(obj, out=None, depth=0):
    """Every field name the payload contains, at any depth."""
    if out is None:
        out = set()
    if depth > 7:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            keys_of(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj[:25]:
            keys_of(v, out, depth + 1)
    return out


def main():
    pages = sorted(os.path.join(r, f)
                   for r, _d, fs in os.walk(WWW) for f in fs
                   if f.endswith(".html") and ".bak" not in f)
    cache = {}
    tot_read_missing = tot_covered = tot_shipped_unread = 0
    rows = []

    # Every endpoint any page fetches, so a missing field can be told apart:
    # "this name exists, on a DIFFERENT endpoint" is a page pointed at the
    # wrong URL, and is a different repair from "this name exists nowhere".
    everywhere = {}
    for page0 in pages:
        for u0 in page_urls(page0):
            c0 = concrete(u0)
            if c0 is None or u0 == "/api/analyze" or c0 in cache:
                continue
            cache[c0] = call(c0)
    for u0, pay in cache.items():
        if pay is not None:
            for k0 in keys_of(pay):
                everywhere.setdefault(k0, set()).add(u0)

    for page in pages:
        urls = page_urls(page)
        if not urls:
            continue
        shipped = set()
        called = []
        for u in urls:
            if u == "/api/analyze":                 # a Gemini call per request
                continue
            c = concrete(u)
            if c is None:
                continue
            if c not in cache:
                cache[c] = call(c)
            if cache[c] is not None:
                shipped |= keys_of(cache[c])
                called.append(u)
        if not called:
            continue
        reads, lines = page_reads(page)
        read_missing, covered = {}, {}
        for field, lns in reads.items():
            if field in shipped:
                continue
            # is a shipped name on the same line? then a fallback covers it
            if any(any(s in lines[n - 1] for s in shipped) for n in lns):
                covered[field] = lns
            else:
                read_missing[field] = (lns, sorted(everywhere.get(field, ())))
        unread = sorted(shipped - set(reads))
        rows.append((os.path.relpath(page, WWW), called, read_missing,
                     covered, unread))
        tot_read_missing += len(read_missing)
        tot_covered += len(covered)
        tot_shipped_unread += len(unread)

    print("=" * 78)
    print("FIELD-NAME SWEEP — what the page asks for vs what the endpoint sends")
    print("=" * 78)
    print(f"\npages with endpoints: {len(rows)}")
    wrong_ep = sum(1 for r in rows for _f, (_l, e) in r[2].items() if e)
    nowhere = tot_read_missing - wrong_ep
    print(f"  READ NOT SHIPPED, uncovered : {tot_read_missing}   <- renders empty, silently")
    print(f"      of those, shipped by another endpoint : {wrong_ep}"
          f"   (page fetches the wrong URL)")
    print(f"      of those, shipped by no endpoint      : {nowhere}"
          f"   (wrong name, or never built)")
    print(f"  read not shipped, covered   : {tot_covered}   (a shipped name sits beside it)")
    print(f"  SHIPPED NOT READ            : {tot_shipped_unread}")

    print("\n" + "-" * 78)
    print("READ NOT SHIPPED — the dangerous direction")
    print("-" * 78)
    for rel, called, missing, _cov, _un in rows:
        if not missing:
            continue
        print(f"\n  {rel}   <- {', '.join(called)}")
        for f, (lns, elsewhere) in sorted(missing.items()):
            tail = (f" (+{len(lns)-1} more)" if len(lns) > 1 else "")
            if elsewhere:
                print(f"      {f:24} line {lns[0]}{tail}")
                print(f"          -> SHIPPED BY {', '.join(elsewhere)} "
                      f"— this page fetches the wrong endpoint")
            else:
                print(f"      {f:24} line {lns[0]}{tail}   (exists nowhere)")

    print("\n" + "-" * 78)
    print("read not shipped, but a fallback covers it on the same line")
    print("-" * 78)
    for rel, _c, _m, cov, _un in rows:
        if cov:
            print(f"  {rel:28} {', '.join(sorted(cov))}")

    print("\n" + "-" * 78)
    print("SHIPPED NOT READ — counted per page, listed for the top few")
    print("-" * 78)
    for rel, called, _m, _c, unread in sorted(rows, key=lambda r: -len(r[4]))[:6]:
        print(f"\n  {rel}  ({len(unread)})   <- {', '.join(called)}")
        print("      " + ", ".join(unread[:18]) + (" …" if len(unread) > 18 else ""))

    json.dump({r[0]: {"endpoints": r[1],
                      "read_not_shipped": {k: {"lines": v[0], "shipped_by": v[1]}
                                           for k, v in r[2].items()},
                      "covered": r[3], "shipped_not_read": r[4]} for r in rows},
              open("/tmp/field_names.json", "w"), ensure_ascii=False, indent=1)
    print("\n  full data: /tmp/field_names.json")


if __name__ == "__main__":
    main()
