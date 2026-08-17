#!/usr/bin/env python3
"""Inventory: every path that starts from a human, and what it does when the
source behind it is retired.

Two entry kinds:
  HTTP     a route whose URL appears in www/**/*.html - a page calls it
  TELEGRAM a command handler reachable from the bot router

For each, a static reachability walk to the known-retired stubs. Static means
by NAME, so it over-reports rather than under-reports - which is the right
direction for a sweep whose job is to find what nobody looked at. Anything it
flags is then CALLED, because the last two of these (analysis.html and
check_symbol) both looked fine until they were run.
"""
import ast
import json
import os
import re
import sys
from collections import defaultdict

BASE = "/home/pi/master_ai"
SKIP = {"venv", "_archive", "_deprecated", "examples", ".git", "backups",
        "node_modules", "__pycache__", ".probe_work", "data", "logs"}

# Functions that return empty/None because the source behind them is gone.
RETIRED = {
    "_fetch_bridge_30m", "_fetch_bridge_daily", "_fetch_bridge_bars",
    "_from_bridge", "_get_bridge_data_safe", "_get_bridge_data_30m_safe",
    "_bridge_available",
}


def py_files():
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for fn in files:
            if fn.endswith(".py"):
                yield os.path.join(root, fn)


def build_graph():
    """name -> set(names it calls), and name -> (file, line)."""
    calls = defaultdict(set)
    where = {}
    for p in py_files():
        try:
            tree = ast.parse(open(p, encoding="utf-8", errors="replace").read())
        except SyntaxError:
            continue
        rel = os.path.relpath(p, BASE)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                where.setdefault(node.name, (rel, node.lineno))
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        f = sub.func
                        if isinstance(f, ast.Name):
                            calls[node.name].add(f.id)
                        elif isinstance(f, ast.Attribute):
                            calls[node.name].add(f.attr)
    return calls, where


def reaches(start, calls, targets, seen=None, depth=0):
    """Shortest path from start to any target, or None. Depth-capped."""
    if seen is None:
        seen = set()
    if start in seen or depth > 8:
        return None
    seen.add(start)
    for callee in sorted(calls.get(start, ())):
        if callee in targets:
            return [start, callee]
        sub = reaches(callee, calls, targets, seen, depth + 1)
        if sub:
            return [start] + sub
    return None


def http_routes():
    """(method, path, handler) for every FastAPI route."""
    out = []
    pat = re.compile(r'@(?:app|router)\.(get|post|put|delete)\(\s*["\']([^"\']+)["\']')
    for p in py_files():
        src = open(p, encoding="utf-8", errors="replace").read()
        lines = src.splitlines()
        for i, line in enumerate(lines):
            m = pat.search(line)
            if not m:
                continue
            for j in range(i + 1, min(i + 6, len(lines))):
                d = re.match(r'\s*(?:async\s+)?def\s+(\w+)', lines[j])
                if d:
                    out.append((m.group(1).upper(), m.group(2), d.group(1),
                                os.path.relpath(p, BASE)))
                    break
    return out


def page_urls():
    """Every path a page fetches."""
    urls = set()
    pat = re.compile(r'''['"`](/(?:api|dashboard)/[a-zA-Z0-9_\-/]*)''')
    for root, dirs, files in os.walk(os.path.join(BASE, "www")):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for fn in files:
            if not fn.endswith((".html", ".js")):
                continue
            src = open(os.path.join(root, fn), encoding="utf-8",
                       errors="replace").read()
            for m in pat.finditer(src):
                urls.add(m.group(1).rstrip("/"))
    return urls


def telegram_handlers():
    """Command handlers: tg_* functions referenced by the router/server."""
    names = set()
    for p in py_files():
        src = open(p, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r'\b(tg_[a-z0-9_]+)\b', src):
            names.add(m.group(1))
    defined = set()
    for p in py_files():
        try:
            tree = ast.parse(open(p, encoding="utf-8", errors="replace").read())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("tg_"):
                    defined.add(node.name)
    return sorted(names & defined)


def main():
    calls, where = build_graph()
    routes = http_routes()
    urls = page_urls()

    print("=" * 78)
    print("HUMAN-ENTRY INVENTORY — read only")
    print("=" * 78)
    print(f"\nroutes defined: {len(routes)}   urls a page actually calls: {len(urls)}")

    called = [r for r in routes if r[1].rstrip("/") in urls]
    print(f"routes a page calls: {len(called)}")

    tg = telegram_handlers()
    print(f"telegram handlers: {len(tg)}")

    print("\n" + "-" * 78)
    print("FLAGGED — reaches a retired stub. CALL THESE, do not trust the graph.")
    print("-" * 78)
    flagged = []
    for method, path, handler, rel in sorted(called, key=lambda r: r[1]):
        chain = reaches(handler, calls, RETIRED)
        if chain:
            flagged.append(("HTTP", f"{method} {path}", handler, rel, chain))
    for name in tg:
        chain = reaches(name, calls, RETIRED)
        if chain:
            rel, ln = where.get(name, ("?", 0))
            flagged.append(("TELEGRAM", name, name, f"{rel}:{ln}", chain))

    if not flagged:
        print("  none")
    for kind, label, handler, rel, chain in flagged:
        print(f"\n  [{kind}] {label}")
        print(f"      {rel}")
        print(f"      {' -> '.join(chain)}")

    print("\n" + "-" * 78)
    print(f"CLEAN by the graph: {len(called) + len(tg) - len(flagged)} entry points")
    print("-" * 78)
    print("  (the graph is name-based and over-reports; a clean result here is")
    print("   weaker evidence than a flagged one, so the loud/silent question")
    print("   is answered by calling, not by reading)")

    json.dump({"flagged": [[k, l, h, r, c] for k, l, h, r, c in flagged],
               "called_routes": [[m, p, h, r] for m, p, h, r in called],
               "telegram": tg},
              open("/tmp/human_paths.json", "w"), ensure_ascii=False, indent=1)
    print("\n  full data: /tmp/human_paths.json")


if __name__ == "__main__":
    main()
