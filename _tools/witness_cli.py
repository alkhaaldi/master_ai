#!/usr/bin/env python3
"""Witness CLI for shell scripts: log a run + alert on failure.

    witness_cli.py log <source> <status> <duration_sec> [error...]
    witness_cli.py alert <text...>

Shell backups failed silently for 4.5 months into a log nobody read
(156 KB of errors); every backup path now reports through the same
witness the Yahoo feeds use.
"""
import sys

sys.path.insert(0, "/home/pi/master_ai")
sys.path.insert(0, "/home/pi/master_ai/_tools")
import run_witness


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "log":
        source, status = sys.argv[2], sys.argv[3]
        dur = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
        err = " ".join(sys.argv[5:]) or None
        run_witness.log_run(source, status,
                            1 if status == "success" else 0, 1, dur, err)
        if status == "failed":
            run_witness.send_telegram("⚠️ %s فشل: %s" % (source, err or "بلا تفاصيل"))
        return 0
    if cmd == "alert":
        run_witness.send_telegram(" ".join(sys.argv[2:]))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
