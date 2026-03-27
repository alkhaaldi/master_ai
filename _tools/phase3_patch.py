#!/usr/bin/env python3
"""
Phase 3 patch runner — runs ON the RPi.
Reads the actual file content to build exact match strings.
"""
import sys, os, re, logging
sys.path.insert(0, "/home/pi/master_ai")
from _tools.patchers.apply_text_patch import apply_patches, apply_patch

FILE = "/home/pi/master_ai/server.py"

# Read current content
with open(FILE, "r", encoding="utf-8") as f:
    content = f.read()

lines = content.split("\n")

# ════════════════════════════════════════════════════════
# PART A: Fix all silent import except blocks (patches 1-22)
# Strategy: find all "except Exception:\n    XXXX_OK = False" 
# and "except Exception:\n    pass" patterns, add logging
# ════════════════════════════════════════════════════════

# Map of FLAG_NAME -> module_name for logging
FLAG_MAP = {
    "TG_OPS_OK": "tg_ops",
    "TG_HOME_OK": "tg_home",
    "TG_SESSION_OK": "tg_session",
    "TG_INTENT_OK": "tg_intent_router",
    "SMART_ROUTER_OK": "smart_router",
    "CHAT_V7_OK": "chat_v7",
    "DISCOVERY_OK": "discovery",
    "TG_SUGGEST_OK": "tg_suggestions",
    "TG_MORNING_OK": "tg_morning_report",
    "LIFE_ROUTER_OK": "life_router",
    "LIFE_STOCKS_OK": "life_stocks",
    "LIFE_EXPENSES_OK": "life_expenses",
    "LIFE_HEALTH_OK": "life_health",
    "LIFE_WORK_OK": "life_work",
    "TG_ALERTS_OK": "tg_alerts",
    "TG_REMIND_OK": "tg_reminders",
    "TG_NEWS_OK": "tg_news",
    "TG_STOCKS_OK": "tg_stocks",
    "RADAR_OK": "stock_radar",
}

patches = []

# Type 1: "except Exception:\n    XXXX_OK = False" -> add warning
for flag, module in FLAG_MAP.items():
    old = f"except Exception:\n    {flag} = False"
    new = f'except Exception as _e:\n    {flag} = False\n    logging.getLogger("master_ai").warning("{module} not loaded: %s", _e)'
    if old in content:
        patches.append((old, new))
        print(f"  [FOUND] {flag} = False (silent)")
    else:
        # Check if already patched
        if f'except Exception as _e:\n    {flag} = False' in content:
            print(f"  [SKIP]  {flag} = False (already patched)")
        else:
            print(f"  [MISS]  {flag} = False (pattern not found)")

# Type 2: "BRAIN_OK = True\nexcept Exception:\n    pass" (home_brain)
old2 = "    BRAIN_OK = True\nexcept Exception:\n    pass"
if old2 in content:
    new2 = '    BRAIN_OK = True\nexcept Exception as _e:\n    logging.getLogger("master_ai").warning("home_brain not loaded: %s", _e)'
    patches.append((old2, new2))
    print(f"  [FOUND] BRAIN_OK pass (silent)")

# Type 3: "TG_REPORT_OK = True\nexcept Exception:\n    pass" (tg_report)
old3 = "    TG_REPORT_OK = True\nexcept Exception:\n    pass"
if old3 in content:
    new3 = '    TG_REPORT_OK = True\nexcept Exception as _e:\n    logging.getLogger("master_ai").warning("tg_report not loaded: %s", _e)'
    patches.append((old3, new3))
    print(f"  [FOUND] TG_REPORT_OK pass (silent)")

# Type 4: "DOCTOR_OK = True\nexcept Exception:\n    pass" (brain_learning scenes)
old4 = "    DOCTOR_OK = True\nexcept Exception:\n    pass"
if old4 in content:
    new4 = '    DOCTOR_OK = True\nexcept Exception as _e:\n    logging.getLogger("master_ai").warning("brain_learning scenes not loaded: %s", _e)'
    patches.append((old4, new4))
    print(f"  [FOUND] DOCTOR_OK pass (silent)")

# ════════════════════════════════════════════════════════
# PART B: Fix daily_context_reason (patch 23)
# Find the EXACT text by locating the key lines
# ════════════════════════════════════════════════════════

# Find the daily_context_stale line and the except block after it
idx_stale = None
for i, line in enumerate(lines):
    if 'data["daily_context_stale"]' in line and "all(d.get" in line:
        idx_stale = i
        break

if idx_stale is not None:
    # Build old_text from actual lines (stale line through except block)
    # Find the except Exception after this block
    idx_except = None
    for j in range(idx_stale + 1, min(idx_stale + 10, len(lines))):
        if "except Exception" in lines[j] and "daily" not in lines[j]:
            idx_except = j
            break
    
    if idx_except is not None:
        # Find end of except block (3 lines: except + 3 assignments)
        idx_end = idx_except
        for j in range(idx_except + 1, min(idx_except + 5, len(lines))):
            if lines[j].strip().startswith('data["'):
                idx_end = j
            else:
                break
        
        old_block = "\n".join(lines[idx_stale:idx_end + 1])
        
        # Build new block
        stale_line = lines[idx_stale]
        # Find the "if not daily_clean:" line
        if_line = lines[idx_stale + 1] if idx_stale + 1 < len(lines) else ""
        reason_line = lines[idx_stale + 2] if idx_stale + 2 < len(lines) else ""
        
        new_block = stale_line + "\n"
        new_block += if_line + "\n"
        new_block += reason_line + "\n"
        new_block += '        elif data["daily_context_stale"]:\n'
        new_block += '            data["daily_context_reason"] = "data available but stale — awaiting market refresh"\n'
        new_block += "        else:\n"
        new_block += '            data["daily_context_reason"] = "ok"\n'
        new_block += '    except Exception as _e:\n'
        new_block += '        logging.getLogger("master_ai").warning("dashboard/extended daily context error: %s", _e)\n'
        new_block += '        data["radar_daily_context"] = []\n'
        new_block += '        data["daily_context_stale"] = True\n'
        new_block += '        data["daily_context_reason"] = f"error loading daily context: {_e}"'
        
        patches.append((old_block, new_block))
        print(f"  [FOUND] daily_context_reason block (lines {idx_stale}-{idx_end})")
    else:
        print(f"  [MISS]  Could not find except after daily_context_stale")
else:
    print(f"  [MISS]  daily_context_stale line not found")

# ════════════════════════════════════════════════════════
# PART C: Fix dashboard/extended radar except (patch 24)
# ════════════════════════════════════════════════════════

old_radar_except = '    except Exception:\n        data["radar_enabled"] = False; data["radar_watch_count"] = 0\n        data["radar_watchlist"] = []; data["radar_recent_signals"] = []; data["radar_alerts_today"] = 0'
if old_radar_except in content:
    new_radar_except = '    except Exception as _e:\n        logging.getLogger("master_ai").warning("dashboard/extended radar error: %s", _e)\n        data["radar_enabled"] = False; data["radar_watch_count"] = 0\n        data["radar_watchlist"] = []; data["radar_recent_signals"] = []; data["radar_alerts_today"] = 0'
    patches.append((old_radar_except, new_radar_except))
    print(f"  [FOUND] radar except block (silent)")
else:
    print(f"  [MISS]  radar except block not found (may be already patched)")

# ════════════════════════════════════════════════════════
# APPLY ALL PATCHES
# ════════════════════════════════════════════════════════
print(f"\nApplying {len(patches)} patches to server.py...")
if not patches:
    print("No patches to apply!")
    sys.exit(0)

result = apply_patches(FILE, patches, backup=True)
print(result)
if result.success:
    print(f"\nSUCCESS: {result.changes} patches applied")
    print(f"Backup: {result.backup_path}")
else:
    print(f"\nFAILED: {result.message}")
    sys.exit(1)
