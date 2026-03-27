#!/usr/bin/env python3
"""Phase 3: Add sync_tv_from_radar to imports + /tv_sync command."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_text_patch import apply_patches

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

patches = [
    # 1. Add sync_tv_from_radar to imports
    (
        '        quick_tv_watchlist, quick_tv_last, quick_tv_summary_today\n'
        '    )\n'
        '    init_tradingview_domain()\n'
        '    TV_BRIDGE_OK = True',

        '        quick_tv_watchlist, quick_tv_last, quick_tv_summary_today,\n'
        '        sync_tv_from_radar,\n'
        '    )\n'
        '    init_tradingview_domain()\n'
        '    TV_BRIDGE_OK = True',
    ),
]

result = apply_patches(FILE, patches)
import json
print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
