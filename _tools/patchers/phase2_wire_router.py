#!/usr/bin/env python3
"""Phase 2: Wire dashboard Router into FastAPI app + init context in lifespan."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_text_patch import apply_patches

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

patches = [
    # 1. Include router after app creation
    (
        'app = FastAPI(title="Master AI", version=VERSION, lifespan=lifespan)\n'
        'app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])',
        'app = FastAPI(title="Master AI", version=VERSION, lifespan=lifespan)\n'
        'app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])\n'
        'app.include_router(dashboard_router)',
    ),
    # 2. Init dashboard context in lifespan (after _pe_set_inbox_cache_ref)
    (
        '    _pe_set_inbox_cache_ref(ha_dashboard_extended)\n'
        '    logger.info(f"Master AI v{VERSION} started")',
        '    # Wire dashboard_api context\n'
        '    from dashboard_api import ha_dashboard_extended, init_dashboard_context\n'
        '    init_dashboard_context(\n'
        '        version=VERSION, start_time=START_TIME,\n'
        '        dashboard_jobs=_dashboard_jobs,\n'
        '        tg_handle_command_fn=tg_handle_command,\n'
        '        radar_ok=RADAR_OK, journal_ok=JOURNAL_OK,\n'
        '        get_open_trades_fn=get_open_trades if JOURNAL_OK else lambda: [],\n'
        '        get_trade_stats_fn=get_trade_stats if JOURNAL_OK else lambda **kw: {},\n'
        '    )\n'
        '    _pe_set_inbox_cache_ref(ha_dashboard_extended)\n'
        '    logger.info(f"Master AI v{VERSION} started")',
    ),
]

result = apply_patches(FILE, patches)
import json
print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
