#!/usr/bin/env python3
"""
rebuild_dashboard_v14b.py — Apply Fix 2-5: Replace sub-radar and sub-signals pages.
Reads the current dashboard, replaces sub-radar and sub-signals sections with v2 pages.
"""
import sys, os, shutil, datetime

DASH = "//192.168.109.123/config/master_ai_dashboard.yaml"
PATCHES = os.path.join(os.path.dirname(os.path.abspath(__file__)))


def main():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DASH + f".bak.v14b_{ts}"
    shutil.copy2(DASH, backup)
    print(f"[OK] Backup: {backup}")

    with open(DASH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    total = len(lines)
    print(f"[OK] Read {total} lines")

    # Find page boundaries
    boundaries = []
    for i, line in enumerate(lines):
        if line.startswith("  - path:"):
            boundaries.append(i)
    boundaries.append(total)

    def page_range(path_name):
        for idx, b in enumerate(boundaries[:-1]):
            if lines[b].strip() == f"- path: {path_name}":
                return b, boundaries[idx + 1]
        return None, None

    # Load v2 pages
    with open(os.path.join(PATCHES, "page_trading_v2.yaml"), "r", encoding="utf-8") as f:
        trading = f.readlines()
    with open(os.path.join(PATCHES, "page_signals_v2.yaml"), "r", encoding="utf-8") as f:
        signals = f.readlines()

    # Get ranges
    start_radar, end_radar = page_range("sub-radar")
    start_signals, end_signals = page_range("sub-signals")

    if start_radar is None or start_signals is None:
        print("[FAIL] Could not find sub-radar or sub-signals page")
        sys.exit(1)

    print(f"[OK] sub-radar: lines {start_radar+1}-{end_radar}")
    print(f"[OK] sub-signals: lines {start_signals+1}-{end_signals}")

    # Build new file
    result = []

    # Before sub-radar
    result.extend(lines[:start_radar])

    # New Trading page
    result.extend(trading)
    if not trading[-1].endswith("\n"):
        result.append("\n")
    result.append("\n")

    # New Signals page
    result.extend(signals)
    if not signals[-1].endswith("\n"):
        result.append("\n")
    result.append("\n")

    # Everything after sub-signals
    result.extend(lines[end_signals:])

    with open(DASH, "w", encoding="utf-8") as f:
        f.writelines(result)

    new_total = len(result)
    print(f"[OK] Written {new_total} lines (was {total})")
    print("[OK] Dashboard v14b fix applied!")


if __name__ == "__main__":
    main()
