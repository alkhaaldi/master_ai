#!/usr/bin/env python3
"""
rebuild_dashboard_v15.py — Replace trading pages with iframe cards pointing to HTML platform.
Replaces sub-radar, sub-signals, sub-journal with iframes.
Inserts new sub-positions page after sub-signals.
"""
import sys, os, shutil, datetime

DASH = "//192.168.109.123/config/master_ai_dashboard.yaml"
PATCHES = os.path.join(os.path.dirname(os.path.abspath(__file__)))


def read_patch(name):
    with open(os.path.join(PATCHES, name), "r", encoding="utf-8") as f:
        return f.readlines()


def main():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DASH + f".bak.v15_{ts}"
    shutil.copy2(DASH, backup)
    print(f"[OK] Backup: {backup}")

    with open(DASH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    total = len(lines)
    print(f"[OK] Read {total} lines")

    # Find page boundaries (0-indexed)
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

    # Load iframe patches
    radar_iframe = read_patch("page_radar_iframe.yaml")
    signals_iframe = read_patch("page_signals_iframe.yaml")
    positions_iframe = read_patch("page_positions_iframe.yaml")
    journal_iframe = read_patch("page_journal_iframe.yaml")

    # Get ranges
    r_start, r_end = page_range("sub-radar")
    s_start, s_end = page_range("sub-signals")
    j_start, j_end = page_range("sub-journal")

    print(f"[OK] sub-radar: {r_start+1}-{r_end}")
    print(f"[OK] sub-signals: {s_start+1}-{s_end}")
    print(f"[OK] sub-journal: {j_start+1}-{j_end}")

    result = []

    # Before sub-radar
    result.extend(lines[:r_start])

    # Iframe: sub-radar
    result.extend(radar_iframe)
    result.append("\n")

    # Iframe: sub-signals
    result.extend(signals_iframe)
    result.append("\n")

    # Iframe: sub-positions (NEW)
    result.extend(positions_iframe)
    result.append("\n")

    # Everything between end of sub-signals and start of sub-journal
    result.extend(lines[s_end:j_start])

    # Iframe: sub-journal
    result.extend(journal_iframe)
    result.append("\n")

    # Done (sub-journal was the last page)

    with open(DASH, "w", encoding="utf-8") as f:
        f.writelines(result)

    new_total = len(result)
    print(f"[OK] Written {new_total} lines (was {total})")
    print("[OK] Dashboard v15 iframe rebuild complete!")


if __name__ == "__main__":
    main()
