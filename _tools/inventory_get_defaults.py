#!/usr/bin/env python3
"""Inventory only, no edits: `.get(key, <number>)` and where it lands.

The 4g question is not how many exist but how many sit inside a SERIES. A
scalar with an invented default is one wrong number. A series is a SHAPE, and
a consumer reads a trend out of a shape - so two invented points in the middle
of a rising RSI look like a crash and a recovery that never happened, and no
range check catches it because every value is in range.

Classification, both axes reported separately:
  series   the call sits inside a comprehension/generator, or inside a for
           loop whose body appends to a list
  scalar   everything else
"""
import ast
import os
import sys
from collections import Counter, defaultdict

BASE = "/home/pi/master_ai"
SKIP_DIRS = {"venv", "_archive", "_deprecated", "examples", ".git", "backups",
             "node_modules", "__pycache__", ".probe_work", "data"}
DECISION = {
    "indicators.py", "gemini_scanner.py", "golden_engine.py", "signal_engine.py",
    "risk_engine.py", "trading_brain.py", "trading_decision_engine.py",
    "position_engine.py", "journal_engine.py", "price_source.py",
    "confluence_engine.py", "signal_review.py", "paper_trading.py",
    "sr_engine.py", "stock_radar.py", "kse_data_collector.py",
    "equity_tracker.py", "priority_engine.py",
}


def numeric(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = numeric(node.operand)
        if inner is not None:
            return -inner
    return None


class Finder(ast.NodeVisitor):
    def __init__(self, src):
        self.lines = src.splitlines()
        self.hits = []
        self.stack = []          # enclosing nodes
        self.func = []           # enclosing function names

    def generic_visit(self, node):
        self.stack.append(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.func.append(node.name)
            super().generic_visit(node)
            self.func.pop()
        else:
            super().generic_visit(node)
        self.stack.pop()

    def _contains(self, node, target):
        for sub in ast.walk(node):
            if sub is target:
                return True
        return False

    @staticmethod
    def _is_record(elt):
        """A dict/list element is a ROW, not a point on a curve.

        This is the distinction that matters for 4g. `{"rsi": d.get("rsi", 0)}`
        appended to a list is one field of one record carrying an invented
        value - bad, but bad once. `d.get("rsi", 0)` appended as a bare number
        is a point in a trajectory, and the consumer reads a SHAPE from those.
        """
        return isinstance(elt, (ast.Dict, ast.DictComp, ast.List, ast.ListComp,
                                ast.Tuple, ast.JoinedStr))

    def _in_series(self, call):
        """Only a scalar element counts. A row that happens to contain a
        default is the ordinary scalar defect wearing a loop."""
        for n in reversed(self.stack):
            if isinstance(n, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
                if self._contains(n.elt, call):
                    if self._is_record(n.elt):
                        return "row-comprehension"
                    return "trajectory (comprehension)"
            if isinstance(n, ast.DictComp):
                return "row-comprehension"
            if isinstance(n, ast.For):
                for sub in ast.walk(n):
                    if (isinstance(sub, ast.Call)
                            and isinstance(sub.func, ast.Attribute)
                            and sub.func.attr == "append"
                            and sub.args and self._contains(sub.args[0], call)):
                        if self._is_record(sub.args[0]):
                            return "row-append"
                        return "trajectory (append)"
        return None

    def visit_Call(self, node):
        if (isinstance(node.func, ast.Attribute) and node.func.attr == "get"
                and len(node.args) == 2):
            n = numeric(node.args[1])
            if n is not None:
                key = None
                if isinstance(node.args[0], ast.Constant):
                    key = node.args[0].value
                self.hits.append({
                    "line": node.lineno,
                    "default": n,
                    "key": key,
                    "series": self._in_series(node),
                    "func": self.func[-1] if self.func else "<module>",
                    "src": self.lines[node.lineno - 1].strip()[:96],
                })
        self.generic_visit(node)


def scan(path):
    try:
        src = open(path, encoding="utf-8", errors="replace").read()
        tree = ast.parse(src)
    except (OSError, SyntaxError):
        return []
    f = Finder(src)
    f.visit(tree)
    return f.hits


def main():
    per_file = defaultdict(list)
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(root, fn)
            hits = scan(p)
            if hits:
                per_file[os.path.relpath(p, BASE)] = hits

    tot = Counter()
    for rel, hits in per_file.items():
        decision = os.path.basename(rel) in DECISION and not os.path.dirname(rel)
        for h in hits:
            kind = h["series"]
            if kind and kind.startswith("trajectory"):
                bucket = "trajectory"
            elif kind:
                bucket = "row"
            else:
                bucket = "scalar"
            tot[bucket] += 1
            tot[("decision" if decision else "other") + "/" + bucket] += 1

    print("=" * 74)
    print("`.get(key, <number>)` INVENTORY — read only, nothing changed")
    print("=" * 74)
    print(f"\ntotal: {tot['series'] + tot['scalar']}"
          f"   series: {tot['series']}   scalar: {tot['scalar']}")
    print(f"  decision path : series {tot['decision/series']:3}  "
          f"scalar {tot['decision/scalar']:3}")
    print(f"  elsewhere     : series {tot['other/series']:3}  "
          f"scalar {tot['other/scalar']:3}")

    print("\n" + "-" * 74)
    print("THE TRAJECTORY ONES — every occurrence. This is the 4g class.")
    print("-" * 74)
    for rel in sorted(per_file):
        s = [h for h in per_file[rel]
             if h["series"] and h["series"].startswith("trajectory")]
        if not s:
            continue
        mark = "*" if (os.path.basename(rel) in DECISION
                       and not os.path.dirname(rel)) else " "
        print(f"\n{mark} {rel}  ({len(s)})")
        for h in s:
            print(f"    {h['line']:>5}  in {h['func']}()  [{h['series']}]"
                  f"  default={h['default']}")
            print(f"           {h['src']}")

    print("\n" + "-" * 74)
    print("SCALAR ONES — counted, listed by file only (not the 4g class)")
    print("-" * 74)
    rows = sorted(((len([h for h in v if not h["series"]]), k)
                   for k, v in per_file.items()), reverse=True)
    for n, rel in rows:
        if n:
            mark = "*" if (os.path.basename(rel) in DECISION
                           and not os.path.dirname(rel)) else " "
            print(f"  {mark} {rel:<44} {n}")
    print("\n* = decision-path module")


if __name__ == "__main__":
    main()
