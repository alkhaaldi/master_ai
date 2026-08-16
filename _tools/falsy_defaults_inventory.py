#!/usr/bin/env python3
"""Inventory only: numeric falsy-defaults in decision paths. No edits.

Two shapes, both of which turn a legitimate 0 into a different number:
    x = something or <number>
    x = <number> if cond else <number>      (cond being a bare truthiness)
    d.get(key, <number>) or <number>

Scope: modules that feed a trade/risk/score decision. Display-only and
tooling modules are counted separately so the urgent set stays readable.
"""
import ast
import os
import sys

BASE = "/home/pi/master_ai"

DECISION = {
    "gemini_scanner.py", "golden_engine.py", "signal_engine.py",
    "risk_engine.py", "trading_brain.py", "trading_decision_engine.py",
    "position_engine.py", "journal_engine.py", "price_source.py",
    "confluence_engine.py", "signal_review.py", "paper_trading.py",
    "sr_engine.py", "stock_radar.py", "kse_data_collector.py",
    "equity_tracker.py", "priority_engine.py",
}


class Finder(ast.NodeVisitor):
    def __init__(self, path, src):
        self.path = path
        self.lines = src.splitlines()
        self.hits = []

    def _num(self, node):
        """The numeric constant a fallback yields, or None."""
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            inner = self._num(node.operand)
            return -inner if inner is not None else None
        return None

    def visit_BoolOp(self, node):
        # `a or 5`  ->  the last value is a bare number
        if isinstance(node.op, ast.Or):
            n = self._num(node.values[-1])
            if n is not None and len(node.values) >= 2:
                self.hits.append((node.lineno, "or", n))
        self.generic_visit(node)

    def visit_IfExp(self, node):
        # `X if cond else 40` where the else-branch is a bare number and
        # the condition is a bare truthiness test (not a comparison, not
        # an `is None`) - those are the ones that swallow a real 0.
        n = self._num(node.orelse)
        if n is not None and isinstance(node.test, (ast.Name, ast.Attribute, ast.Call,
                                                    ast.Subscript)):
            self.hits.append((node.lineno, "if/else", n))
        self.generic_visit(node)


def scan(path):
    src = open(path, encoding="utf-8", errors="replace").read()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    f = Finder(path, src)
    f.visit(tree)
    return [(ln, kind, val, f.lines[ln - 1].strip()[:88]) for ln, kind, val in f.hits]


def main():
    decision_hits, other_hits = {}, {}
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in
                   {"venv", "_archive", "_deprecated", "examples", ".git",
                    "backups", "node_modules", "__pycache__"}]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(root, fn)
            hits = scan(p)
            if not hits:
                continue
            rel = os.path.relpath(p, BASE)
            (decision_hits if fn in DECISION and os.path.dirname(rel) == ""
             else other_hits)[rel] = hits

    d_total = sum(len(v) for v in decision_hits.values())
    o_total = sum(len(v) for v in other_hits.values())
    print("=" * 74)
    print("NUMERIC FALSY-DEFAULT INVENTORY — read-only, %d decision-path sites"
          % d_total)
    print("=" * 74)
    for rel in sorted(decision_hits, key=lambda k: -len(decision_hits[k])):
        hits = decision_hits[rel]
        print("\n%s  (%d)" % (rel, len(hits)))
        for ln, kind, val, text in hits:
            print("  %-5s %-8s -> %-6s | %s" % (ln, kind, val, text))
    print("\n" + "-" * 74)
    print("decision-path modules : %d sites in %d files"
          % (d_total, len(decision_hits)))
    print("everything else       : %d sites in %d files (not listed)"
          % (o_total, len(other_hits)))
    print("top non-decision files:", ", ".join(
        "%s(%d)" % (k, len(v)) for k, v in
        sorted(other_hits.items(), key=lambda kv: -len(kv[1]))[:6]))


def counts():
    """(decision_path_sites, other_sites) - the numbers quick_check ratchets."""
    d = o = 0
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [x for x in dirs if x not in
                   {"venv", "_archive", "_deprecated", "examples", ".git",
                    "backups", "node_modules", "__pycache__"}]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(root, fn)
            hits = scan(p)
            if not hits:
                continue
            rel = os.path.relpath(p, BASE)
            if fn in DECISION and not os.path.dirname(rel):
                d += len(hits)
            else:
                o += len(hits)
    return d, o


if __name__ == "__main__":
    if "--count" in sys.argv:
        d, o = counts()
        print("%d %d" % (d, o))
    else:
        main()
