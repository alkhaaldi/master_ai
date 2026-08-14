#!/usr/bin/env python3
"""C-8: import every top-level module and fail loudly if any of them breaks.

This is the check that would have caught daily_stats.py five months ago: commit
651b154 deleted it while server.py kept importing it, and the failure hid inside
a try/except that returned an error dict.

Each import gets its own alarm so a module that blocks on a socket or a lock
cannot stall the whole run. Modules are imported in one process, so a module
already pulled in as someone else's dependency is reported from cache - that is
fine, the question is only whether it imports at all.

Run:  venv/bin/python3 _tools/import_test.py [--verbose]
Exit: 0 if every module imports, 1 otherwise.
"""
import argparse
import importlib
import pathlib
import signal
import sys
import traceback

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

PER_MODULE_TIMEOUT = 25  # seconds

# Not modules: entrypoint scripts that do work at import time by design.
SKIP = {
    "import_test",
}


class Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise Timeout(f"import exceeded {PER_MODULE_TIMEOUT}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true", help="print every module, not just failures")
    args = ap.parse_args()

    names = sorted(p.stem for p in REPO.glob("*.py")
                   if not p.name.startswith(".") and ".bak" not in p.name)
    names = [n for n in names if n not in SKIP]

    signal.signal(signal.SIGALRM, _alarm)
    failures = []
    slow = []

    for name in names:
        signal.alarm(PER_MODULE_TIMEOUT)
        try:
            import time as _t
            t0 = _t.time()
            importlib.import_module(name)
            dt = _t.time() - t0
            signal.alarm(0)
            if dt > 3:
                slow.append((name, dt))
            if args.verbose:
                print(f"  ok    {name}  ({dt:.1f}s)")
        except Timeout as e:
            signal.alarm(0)
            failures.append((name, "Timeout", str(e), ""))
            print(f"  HUNG  {name}: {e}")
        except BaseException as e:
            # BaseException on purpose: a module calling sys.exit() at import
            # time is a failure worth reporting, not something to sail past.
            signal.alarm(0)
            failures.append((name, type(e).__name__, str(e), traceback.format_exc()))
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")

    print()
    print("=" * 70)
    print(f"{len(names) - len(failures)}/{len(names)} modules import cleanly")
    if slow:
        print(f"slow imports (>3s): {', '.join(f'{n} {d:.1f}s' for n, d in slow)}")
    if failures:
        print(f"\n{len(failures)} FAILED:")
        for name, kind, msg, tb in failures:
            print(f"\n--- {name} ({kind}) ---")
            print(msg)
            if args.verbose and tb:
                print(tb)
    print("=" * 70)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
