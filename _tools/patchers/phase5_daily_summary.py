#!/usr/bin/env python3
"""Phase 5: Enhance daily trading summary — run at 13:00 KWT, add radar signals + P&L."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_text_patch import apply_patch

FILE = os.path.join(os.path.dirname(__file__), "..", "..", "server.py")

OLD = '''            # Daily Trading Summary at market close (6:30 PM KWT = 15:30 UTC)
            async def _daily_trading_summary_loop():
                _log = logging.getLogger("daily_summary")
                _log.info("Daily trading summary scheduler started")
                await asyncio.sleep(120)
                while True:
                    try:
                        from datetime import datetime as _dt, timedelta as _td
                        _kwt = _dt.utcnow() + _td(hours=3)
                        # Only run Sun-Thu (KSE trading days)
                        if _kwt.weekday() in (4, 5):  # Fri=4, Sat=5
                            await asyncio.sleep(3600)
                            continue
                        # Check if it's ~18:30 KWT
                        if _kwt.hour == 18 and 25 <= _kwt.minute <= 35:
                            if JOURNAL_OK:
                                stats = get_trade_stats(days=1)
                                open_trades = get_open_trades()
                                lines = ["*\\U0001f4ca \\u0645\\u0644\\u062e\\u0635 \\u0627\\u0644\\u062a\\u062f\\u0627\\u0648\\u0644 \\u0627\\u0644\\u064a\\u0648\\u0645\\u064a*\\n"]
                                if open_trades:
                                    lines.append("\\U0001f4c2 \\u0635\\u0641\\u0642\\u0627\\u062a \\u0645\\u0641\\u062a\\u0648\\u062d\\u0629: " + str(len(open_trades)))
                                    for t in open_trades:
                                        _n = t.get("name_ar") or t["symbol"]
                                        lines.append("  \\u2022 " + _n + " @ " + str(t["entry_price"]) + " \\u2014 " + (t.get("strategy") or ""))
                                if stats["closed_trades"] > 0:
                                    _wr = str(round(stats["win_rate"] * 100)) + "%"
                                    lines.append("\\n\\u2705 \\u0645\\u063a\\u0644\\u0642\\u0629 \\u0627\\u0644\\u064a\\u0648\\u0645: " + str(stats["closed_trades"]))
                                    lines.append("\\U0001f4c8 Win rate: " + _wr)
                                    lines.append("\\U0001f4b0 P&L: " + format(stats["total_pnl_fils"], "+.0f") + " \\u0641\\u0644\\u0633")
                                if not open_trades and stats["closed_trades"] == 0:
                                    lines.append("\\u0644\\u0627 \\u0635\\u0641\\u0642\\u0627\\u062a \\u0627\\u0644\\u064a\\u0648\\u0645")
                                _cid = ADMIN_TELEGRAM_ID or "669769765"
                                await tg_send(int(_cid), "\\n".join(lines))
                                _log.info("Daily trading summary sent")
                            await asyncio.sleep(3600)  # don't re-send
                        else:
                            await asyncio.sleep(300)  # check every 5 min
                    except Exception as _e:
                        _log.error("Daily summary error: %s", _e)
                        await asyncio.sleep(600)
            asyncio.create_task(_daily_trading_summary_loop())
            logger.info("Daily trading summary scheduled (18:30 KWT)")'''

NEW = '''            # Daily Trading Summary at market close (1:00 PM KWT = 10:00 UTC)
            async def _daily_trading_summary_loop():
                _log = logging.getLogger("daily_summary")
                _log.info("Daily trading summary scheduler started")
                await asyncio.sleep(120)
                while True:
                    try:
                        from datetime import datetime as _dt, timedelta as _td
                        _kwt = _dt.utcnow() + _td(hours=3)
                        # Only run Sun-Thu (KSE trading days)
                        if _kwt.weekday() in (4, 5):  # Fri=4, Sat=5
                            await asyncio.sleep(3600)
                            continue
                        # Run at ~13:00 KWT (after market close 12:40)
                        if _kwt.hour == 13 and 0 <= _kwt.minute <= 10:
                            _cid = ADMIN_TELEGRAM_ID or "669769765"
                            _today = _kwt.strftime("%Y-%m-%d")
                            lines = [f"*\\U0001f4ca \\u0645\\u0644\\u062e\\u0635 \\u0627\\u0644\\u062a\\u062f\\u0627\\u0648\\u0644 \\u2014 {_today}*\\n"]
                            # Radar signals today
                            try:
                                import sqlite3 as _s3
                                _sdb = _s3.connect("data/life.db", timeout=3)
                                _sdb.row_factory = _s3.Row
                                _sigs = _sdb.execute(
                                    "SELECT * FROM stock_radar_events WHERE date(created_at)=? ORDER BY created_at DESC",
                                    (_today,)
                                ).fetchall()
                                _bull = sum(1 for s in _sigs if s["signal_type"] == "bullish_cross")
                                _bear = sum(1 for s in _sigs if s["signal_type"] == "bearish_cross")
                                lines.append(f"\\U0001f4e1 \\u0625\\u0634\\u0627\\u0631\\u0627\\u062a \\u0627\\u0644\\u064a\\u0648\\u0645: {len(_sigs)} ({_bull} \\u0635\\u0627\\u0639\\u062f, {_bear} \\u0647\\u0627\\u0628\\u0637)")
                                # Top signals by score
                                _top = sorted(_sigs, key=lambda x: x.get("score") or 0, reverse=True)[:3]
                                if _top:
                                    lines.append("\\U0001f3af \\u0623\\u0641\\u0636\\u0644 \\u0625\\u0634\\u0627\\u0631\\u0627\\u062a:")
                                    for _s in _top:
                                        lines.append(f"   {_s['symbol']} \\u2014 Score {_s.get('score',0)}/{_s.get('score_class','?')}")
                                _sdb.close()
                            except Exception:
                                pass
                            # Journal: open trades with P&L
                            if JOURNAL_OK:
                                stats = get_trade_stats(days=1)
                                open_trades = get_open_trades()
                                if open_trades:
                                    lines.append(f"\\n\\U0001f4c2 \\u0635\\u0641\\u0642\\u0627\\u062a \\u0645\\u0641\\u062a\\u0648\\u062d\\u0629: {len(open_trades)}")
                                    _total_pnl = 0
                                    for t in open_trades:
                                        _n = t.get("name_ar") or t["symbol"]
                                        _e = t.get("entry_price", 0)
                                        # Get current price from daily snapshot
                                        try:
                                            from tv_data import resolve_symbol, _normalize_price_to_fils
                                            _rsym = resolve_symbol(t["symbol"])
                                            _ddb = _s3.connect("data/life.db", timeout=3)
                                            _ddb.row_factory = _s3.Row
                                            _dr = _ddb.execute("SELECT price FROM stock_radar_daily WHERE symbol=? ORDER BY rowid DESC LIMIT 1", (_rsym,)).fetchone()
                                            _ddb.close()
                                            if _dr:
                                                _cp = _normalize_price_to_fils(float(_dr["price"]), _rsym)
                                                _pct = round((_cp / _e - 1) * 100, 1) if _e else 0
                                                _arrow = "\\u2b06\\ufe0f" if _pct >= 0 else "\\u2b07\\ufe0f"
                                                _qty = int(t.get("quantity", 0))
                                                _pnl = round((_cp - _e) * _qty) if _qty else 0
                                                _total_pnl += _pnl
                                                _pnl_s = f" ({_pnl:+} \\u0641\\u0644\\u0633)" if _qty else ""
                                                lines.append(f"   {_n}: {_arrow} {_pct:+.1f}%{_pnl_s}")
                                            else:
                                                lines.append(f"   {_n}: @ {_e}")
                                        except Exception:
                                            lines.append(f"   {_n}: @ {_e}")
                                    if _total_pnl:
                                        lines.append(f"\\n\\U0001f4b0 P&L \\u0627\\u0644\\u0625\\u062c\\u0645\\u0627\\u0644\\u064a: {_total_pnl:+} \\u0641\\u0644\\u0633")
                                if stats.get("closed_trades", 0) > 0:
                                    _wr = str(round(stats["win_rate"] * 100)) + "%"
                                    lines.append(f"\\n\\u2705 \\u0645\\u063a\\u0644\\u0642\\u0629 \\u0627\\u0644\\u064a\\u0648\\u0645: {stats['closed_trades']}")
                                    lines.append(f"\\U0001f4c8 Win rate: {_wr}")
                                if not open_trades and stats.get("closed_trades", 0) == 0:
                                    lines.append("\\u0644\\u0627 \\u0635\\u0641\\u0642\\u0627\\u062a \\u0627\\u0644\\u064a\\u0648\\u0645")
                            await tg_send(int(_cid), "\\n".join(lines))
                            _log.info("Daily trading summary sent")
                            await asyncio.sleep(3600)  # don't re-send
                        else:
                            await asyncio.sleep(300)  # check every 5 min
                    except Exception as _e:
                        _log.error("Daily summary error: %s", _e)
                        await asyncio.sleep(600)
            asyncio.create_task(_daily_trading_summary_loop())
            logger.info("Daily trading summary scheduled (13:00 KWT)")'''

result = apply_patch(FILE, OLD, NEW, backup=True)
import json
print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
