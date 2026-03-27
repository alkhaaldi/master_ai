#!/usr/bin/env python3
"""
rebuild_dashboard_v14.py — Rebuild trading dashboard: 3-page signal-driven layout.
Replaces sub-radar, sub-journal. Inserts sub-signals. Deletes portfolio/analysis/alerts/confluence.
Updates home nav button.
"""
import sys, os, shutil, datetime

DASH = "//192.168.109.123/config/master_ai_dashboard.yaml"
PATCHES = os.path.join(os.path.dirname(os.path.abspath(__file__)))

def main():
    # Backup
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DASH + f".bak.v14_{ts}"
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
    boundaries.append(total)  # sentinel

    def page_range(path_name):
        """Return (start, end) 0-indexed line range for a page."""
        for idx, b in enumerate(boundaries[:-1]):
            if lines[b].strip() == f"- path: {path_name}":
                return b, boundaries[idx + 1]
        return None, None

    # Load new page YAMLs
    with open(os.path.join(PATCHES, "page_trading.yaml"), "r", encoding="utf-8") as f:
        trading_lines = f.readlines()
    with open(os.path.join(PATCHES, "page_signals.yaml"), "r", encoding="utf-8") as f:
        signals_lines = f.readlines()
    with open(os.path.join(PATCHES, "page_journal.yaml"), "r", encoding="utf-8") as f:
        journal_lines = f.readlines()

    # Build the new file by processing pages in order
    # Strategy: iterate through boundaries, keep/replace/delete/insert as needed
    result = []

    # 1. Everything before sub-radar (lines 0..309)
    start_radar, end_radar = page_range("sub-radar")
    result.extend(lines[:start_radar])

    # 2. New Trading page (replaces sub-radar)
    result.extend(trading_lines)
    if not trading_lines[-1].endswith("\n"):
        result.append("\n")
    result.append("\n")

    # 3. NEW: sub-signals page (insert after trading)
    result.extend(signals_lines)
    if not signals_lines[-1].endswith("\n"):
        result.append("\n")
    result.append("\n")

    # 4. Keep everything from sub-calendar-tasks through sub-news (638..1773)
    start_cal, _ = page_range("sub-calendar-tasks")
    start_portfolio, _ = page_range("sub-portfolio")
    result.extend(lines[start_cal:start_portfolio])

    # 5. SKIP sub-portfolio (1774..1887) and sub-analysis (1888..2073)
    start_assistant, _ = page_range("sub-assistant")
    # Keep sub-assistant (2074..2225)
    start_journal, end_journal = page_range("sub-journal")
    result.extend(lines[start_assistant:start_journal])

    # 6. New Journal page (replaces sub-journal)
    result.extend(journal_lines)
    if not journal_lines[-1].endswith("\n"):
        result.append("\n")

    # 7. SKIP sub-alerts (2375..2518) and sub-confluence (2519..2723)
    # Nothing more to add

    # Write result
    with open(DASH, "w", encoding="utf-8") as f:
        f.writelines(result)

    new_total = len(result)
    print(f"[OK] Written {new_total} lines (was {total})")

    # Now update the home nav button: القرار -> الإشارات pointing to sub-signals
    with open(DASH, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace home nav button
    content = content.replace(
        "navigation_path: /master-ai-dashboard/sub-confluence",
        "navigation_path: /master-ai-dashboard/sub-signals"
    )
    content = content.replace(
        "name: القرار",
        "name: الإشارات"
    )
    content = content.replace(
        "icon: mdi:target",
        "icon: mdi:signal-variant"
    )

    with open(DASH, "w", encoding="utf-8") as f:
        f.write(content)

    print("[OK] Updated home nav: القرار → الإشارات")
    print("[OK] Dashboard v14 rebuild complete!")
    print(f"     Backup at: {backup}")

if __name__ == "__main__":
    main()
