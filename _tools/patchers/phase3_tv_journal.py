#!/usr/bin/env python3
"""Phase 3: Wire TradingView webhook to journal_engine — auto-log trades."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_text_patch import apply_patch

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

OLD = '''    if not TV_BRIDGE_OK:
        return JSONResponse(status_code=503, content={"ok": False, "error": "TV bridge not loaded"})
    status_code, response = tv_handle_webhook(payload)
    # Send TG alert if successful
    if status_code == 200 and response.get("ok") and response.get("tg_message"):'''

NEW = '''    if not TV_BRIDGE_OK:
        return JSONResponse(status_code=503, content={"ok": False, "error": "TV bridge not loaded"})
    status_code, response = tv_handle_webhook(payload)
    # Auto-log trade in journal
    if status_code == 200 and response.get("ok") and JOURNAL_OK:
        try:
            _sig = payload.get("signal", "").lower()
            _ticker = payload.get("ticker", "")
            _price = float(payload.get("price", 0)) if payload.get("price") else 0
            _strat = payload.get("strategy", payload.get("strategy_name", "TV Alert"))
            _qty = int(payload.get("quantity", 0)) if payload.get("quantity") else 0
            if _sig in ("buy", "entry", "long"):
                _tid = open_trade(
                    symbol=_ticker, entry_price=_price, quantity=_qty,
                    entry_reason=f"TradingView: {payload.get('message', _sig)}",
                    strategy=_strat, entry_signal_id=response.get("saved_id"),
                )
                logger.info(f"TV auto-journal: opened trade #{_tid} for {_ticker}")
            elif _sig in ("sell", "exit", "close", "short"):
                _open = get_open_trades()
                _match = [t for t in _open if t["symbol"].upper() == _ticker.upper()]
                if _match:
                    close_trade(_match[0]["id"], _price, exit_reason=f"TradingView: {_sig}")
                    logger.info(f"TV auto-journal: closed trade #{_match[0]['id']} for {_ticker}")
        except Exception as _je:
            logger.warning(f"TV auto-journal error: {_je}")
    # Send TG alert if successful
    if status_code == 200 and response.get("ok") and response.get("tg_message"):'''

result = apply_patch(FILE, OLD, NEW, backup=True)
import json
print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
