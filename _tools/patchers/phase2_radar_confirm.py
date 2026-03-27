#!/usr/bin/env python3
"""Phase 2: Modify _radar_sender to send trade confirmation buttons."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_text_patch import apply_patch

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

OLD = '''            async def _radar_sender(text):
                _cid = ADMIN_TELEGRAM_ID or "669769765"
                # Smart filter: only send high-value signals
                _send = False
                _text_lower = text.lower() if text else ""
                # Always send A-class signals
                if "/A" in text or "A/" in text or "score_class: A" in _text_lower:
                    _send = True
                # Send if score >= 70 mentioned
                if not _send:
                    import re as _re
                    _score_match = _re.search(r"(\\d+)/[ABC]", text)
                    if _score_match:
                        try:
                            _sc = int(_score_match.group(1))
                            if _sc >= 70:
                                _send = True
                        except ValueError:
                            pass
                # Send if symbol is in open journal trades
                if not _send and JOURNAL_OK:
                    _open_syms = [t["symbol"] for t in get_open_trades()]
                    for _os in _open_syms:
                        if _os in text.upper():
                            _send = True
                            break
                # Send bullish cross signals (potential entries)
                if not _send and "bullish" in _text_lower:
                    _send = True
                if _send:
                    await tg_send(int(_cid), text)
                else:
                    logging.getLogger("radar").debug("Smart filter: suppressed alert")'''

NEW = '''            async def _radar_sender(text, sig_meta=None):
                _cid = ADMIN_TELEGRAM_ID or "669769765"
                # Smart filter: only send high-value signals
                _send = False
                _text_lower = text.lower() if text else ""
                _sc_val = sig_meta.get("score", 0) if sig_meta else 0
                _sc_cls = sig_meta.get("score_class", "") if sig_meta else ""
                # Always send A-class signals
                if _sc_cls == "A" or "/A" in text or "A/" in text:
                    _send = True
                # Send if score >= 70
                if not _send and _sc_val >= 70:
                    _send = True
                # Send if symbol is in open journal trades
                if not _send and JOURNAL_OK and sig_meta:
                    _open_syms = [t["symbol"] for t in get_open_trades()]
                    if sig_meta.get("symbol", "").upper() in [s.upper() for s in _open_syms]:
                        _send = True
                # Send bullish cross signals (potential entries)
                if not _send and sig_meta and sig_meta.get("signal") == "bullish_cross":
                    _send = True
                if not _send and "bullish" in _text_lower:
                    _send = True
                if _send:
                    await tg_send(int(_cid), text)
                    # Send trade confirmation buttons for buy/sell signals
                    if sig_meta and sig_meta.get("signal") in ("bullish_cross", "bearish_cross"):
                        try:
                            _r_sym = sig_meta["symbol"]
                            _r_price = sig_meta["price"]
                            _r_action = "buy" if sig_meta["signal"] == "bullish_cross" else "sell"
                            _r_score = sig_meta.get("score", 0)
                            _r_cls = sig_meta.get("score_class", "")
                            _r_cb = f"{_r_sym}|{_r_price}|{_r_action}|Radar EMA9/21|0|radar_{_r_score}"
                            _r_btns = [
                                {"text": "\\u0634\\u0631\\u064a\\u062a \\u2705", "callback_data": f"trade_confirm:{_r_cb}"},
                                {"text": "\\u062a\\u062c\\u0627\\u0647\\u0644\\u062a \\u274c", "callback_data": f"trade_skip:{_r_cb}"},
                            ]
                            await tg_send_inline(int(_cid), f"\\u0634\\u0631\\u064a\\u062a \\u0648\\u0644\\u0627 \\u062a\\u062c\\u0627\\u0647\\u0644\\u062a\\u061f", _r_btns, columns=2)
                        except Exception as _re:
                            logging.getLogger("radar").warning(f"Radar confirm buttons error: {_re}")
                else:
                    logging.getLogger("radar").debug("Smart filter: suppressed alert")'''

result = apply_patch(FILE, OLD, NEW, backup=True)
import json
print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
