"""
dashboard_api.py — HA Dashboard API endpoints (FastAPI Router)
Extracted from server.py v8.3.0
"""
import os
import time
import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from collections import deque
from fastapi import APIRouter, Request

from priority_engine import (
    build_priority_engine, build_assistant_surface,
    _pe_get_extended_snapshot, _pe_get_radar_snapshot,
)

logger = logging.getLogger("dashboard_api")

router = APIRouter()

# Server context — populated by server.py at startup via init_dashboard_context()
_ctx = {}

def init_dashboard_context(version, start_time, dashboard_jobs, tg_handle_command_fn,
                           radar_ok, journal_ok, get_open_trades_fn, get_trade_stats_fn):
    """Called by server.py to inject shared state."""
    global _ctx
    _ctx = {
        "version": version,
        "start_time": start_time,
        "dashboard_jobs": dashboard_jobs,
        "tg_handle_command": tg_handle_command_fn,
        "radar_ok": radar_ok,
        "journal_ok": journal_ok,
        "get_open_trades": get_open_trades_fn,
        "get_trade_stats": get_trade_stats_fn,
    }


# ═══════════════════════════════════════════════════
# Room entity helpers
# ═══════════════════════════════════════════════════

_ROOM_ENTITIES = None

def _load_room_entities():
    global _ROOM_ENTITIES
    if _ROOM_ENTITIES is not None:
        return _ROOM_ENTITIES
    import json as _j
    try:
        em = _j.load(open(os.path.join(os.path.dirname(__file__), "entity_map.json")))
    except Exception:
        em = {}
    mapping = {}
    for room, ents in em.items():
        rn = room.split("/")[0].strip()
        lights, climates, covers = [], [], []
        for e in ents:
            eid = e.split("=")[0]
            if eid.startswith("light."):
                lights.append(eid)
            elif eid.startswith("climate."):
                climates.append(eid)
            elif eid.startswith("cover.") and "_inverted" in eid:
                covers.append(eid)
        if lights or climates or covers:
            mapping[rn] = {"lights": lights, "climates": climates, "covers": covers}
    _ROOM_ENTITIES = mapping
    return mapping

def _build_rooms_summary(states):
    if not states:
        return []
    mapping = _load_room_entities()
    state_map = {s["entity_id"]: s for s in states}
    rooms = []
    for rn, ents in mapping.items():
        lo = sum(1 for eid in ents["lights"] if state_map.get(eid, {}).get("state") == "on" and "backlight" not in eid)
        lt = len([eid for eid in ents["lights"] if "backlight" not in eid])
        ac_state = "off"
        ac_temp = None
        ac_target = None
        for eid in ents["climates"]:
            st = state_map.get(eid, {})
            attrs = st.get("attributes", {})
            cur_t = attrs.get("current_temperature")
            if cur_t is not None:
                ac_temp = cur_t
                ac_target = attrs.get("temperature")
            if st.get("state") not in ("off", "unavailable", "unknown", None):
                ac_state = st.get("state", "off")
                break
        co = sum(1 for eid in ents["covers"] if state_map.get(eid, {}).get("state") == "closed")
        ct = len(ents["covers"])
        rooms.append({
            "room": rn,
            "lights_on": lo,
            "lights_total": lt,
            "ac_state": ac_state,
            "ac_temp": ac_temp,
            "ac_target": ac_target,
            "covers_closed": co,
            "covers_total": ct,
        })
    rooms.sort(key=lambda r: (-(r["lights_on"]), r["ac_state"] == "off", r["room"]))
    return rooms


# ═══════════════════════════════════════════════════
# /dashboard — Single call for all sensors
# ═══════════════════════════════════════════════════

@router.get("/dashboard")
async def ha_dashboard():
    """Returns all data needed for HA Master AI dashboard page."""
    import psutil, sqlite3
    data = {}
    data["version"] = _ctx["version"]
    data["uptime"] = round(time.time() - _ctx["start_time"])
    data["api_online"] = True
    try:
        data["cpu"] = psutil.cpu_percent(interval=0.5)
        data["memory"] = psutil.virtual_memory().percent
        data["disk"] = psutil.disk_usage("/").percent
        try:
            data["temperature"] = round(float(open("/sys/class/thermal/thermal_zone0/temp").read().strip()) / 1000, 1)
        except Exception:
            data["temperature"] = 0
    except Exception:
        data["cpu"] = 0; data["memory"] = 0; data["disk"] = 0; data["temperature"] = 0
    data["background_tasks"] = 22
    data["degraded_mode"] = "normal"
    try:
        from life_work import get_shift
        from datetime import date as _d
        st = get_shift(_d.today())
        data["shift_today"] = st.get("shift", "?") + " " + st.get("emoji", "")
        st2 = get_shift(_d.today() + timedelta(days=1))
        data["shift_tomorrow"] = st2.get("shift", "?") + " " + st2.get("emoji", "")
    except Exception:
        data["shift_today"] = "?"; data["shift_tomorrow"] = "?"
    try:
        from stock_radar import get_watchlist, get_recent_events, _get_config, get_daily_snapshot
        from tv_data import _is_market_open
        cfg = _get_config()
        data["radar_enabled"] = cfg.get("enabled", False)
        data["radar_watch_count"] = len(get_watchlist())
        data["market_open"] = _is_market_open()
        events = get_recent_events(5)
        data["radar_alerts_today"] = len([e for e in events if e.get("created_at","")[:10] == str(_d.today())])
        if events:
            last = events[0]
            data["last_signal_symbol"] = last.get("symbol", "")
            data["last_signal_type"] = last.get("signal_type", "")
            data["last_signal_price"] = last.get("price", 0)
            data["last_signal_time"] = last.get("created_at", "")[:16]
        else:
            data["last_signal_symbol"] = ""; data["last_signal_type"] = ""; data["last_signal_price"] = 0; data["last_signal_time"] = ""
        if events:
            best = events[0]
            data["top_signal"] = f"{best.get('symbol','')} ({best.get('signal_type','').replace('_',' ')}) @ {best.get('price',0)} fils"
        else:
            data["top_signal"] = ""
    except Exception:
        data["radar_enabled"] = False; data["radar_watch_count"] = 0; data["market_open"] = False; data["radar_alerts_today"] = 0
        data["last_signal_symbol"] = ""; data["last_signal_type"] = ""; data["last_signal_price"] = 0; data["last_signal_time"] = ""
        data["top_signal"] = ""
    try:
        conn = sqlite3.connect("data/life.db", timeout=3)
        data["tasks_open"] = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='todo'").fetchone()[0]
        data["tasks_high"] = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='todo' AND priority<=1").fetchone()[0]
        conn.close()
    except Exception:
        data["tasks_open"] = 0; data["tasks_high"] = 0
    try:
        conn = sqlite3.connect("data/life.db", timeout=3)
        today = str(_d.today())
        data["events_today"] = conn.execute("SELECT COUNT(*) FROM calendar_events WHERE start_ts LIKE ? AND status='confirmed'", (today+"%",)).fetchone()[0]
        row = conn.execute("SELECT summary, start_ts FROM calendar_events WHERE start_ts >= ? AND status='confirmed' ORDER BY start_ts LIMIT 1", (datetime.utcnow().isoformat(),)).fetchone()
        data["next_event"] = row[0] if row else ""
        data["next_event_time"] = row[1][:16] if row else ""
        conn.close()
    except Exception:
        data["events_today"] = 0; data["next_event"] = ""; data["next_event_time"] = ""
    try:
        conn = sqlite3.connect("data/life.db", timeout=3)
        today = str(_d.today())
        data["expenses_today"] = conn.execute("SELECT COALESCE(SUM(amount),0) FROM expense_entries WHERE spent_at LIKE ?", (today+"%",)).fetchone()[0]
        conn.close()
    except Exception:
        data["expenses_today"] = 0
    try:
        import glob
        bks = sorted(glob.glob("backups/*.gz"))
        data["last_backup"] = bks[-1].split("/")[-1] if bks else "none"
    except Exception:
        data["last_backup"] = "unknown"
    states = []
    try:
        import aiohttp
        ha_token = ""
        try:
            ha_token = open(os.path.expanduser("~/.ha_token")).read().strip()
        except Exception:
            pass
        if ha_token:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://127.0.0.1:8123/api/states",
                                       headers={"Authorization": f"Bearer {ha_token}"},
                                       timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        states = await resp.json()
                        data["home_lights_on"] = sum(1 for s in states if s["entity_id"].startswith("light.") and s["state"] == "on" and "backlight" not in s["entity_id"])
                        data["home_ac_on"] = sum(1 for s in states if s["entity_id"].startswith("climate.") and s["state"] not in ("off", "unavailable", "unknown"))
                        ci = sum(1 for s in states if s["entity_id"].startswith("cover.") and "_inverted" in s["entity_id"] and s["state"] == "closed")
                        data["home_covers_open"] = ci
                    else:
                        data["home_lights_on"] = -1; data["home_ac_on"] = -1; data["home_covers_open"] = -1
        else:
            data["home_lights_on"] = -1; data["home_ac_on"] = -1; data["home_covers_open"] = -1
    except Exception:
        data["home_lights_on"] = -1; data["home_ac_on"] = -1; data["home_covers_open"] = -1
    try:
        data["rooms_summary"] = _build_rooms_summary(states)
    except Exception as _rs_err:
        logging.getLogger("master_ai").warning("rooms_summary error: %s", _rs_err)
        data["rooms_summary"] = []
    if _ctx["dashboard_jobs"]:
        lj = _ctx["dashboard_jobs"][-1]
        data["last_cmd_command"] = lj.get("command", "")
        data["last_cmd_status"] = lj.get("status", "")
        data["last_cmd_result"] = lj.get("result", "")[:200]
        data["last_cmd_time"] = lj.get("time", "")
    else:
        data["last_cmd_command"] = ""; data["last_cmd_status"] = ""; data["last_cmd_result"] = ""; data["last_cmd_time"] = ""
    # --- Priority Engine ---
    try:
        # A1: Warm inbox cache on cold start so PE sees emails
        if not hasattr(ha_dashboard_extended, "_inbox_cache") or not ha_dashboard_extended._inbox_cache.get("data"):
            try:
                from inbox_engine import fetch_unified_inbox
                import asyncio as _aio
                _inbox_warm = await fetch_unified_inbox(hours=24, limit=15)
                import time as _tw
                ha_dashboard_extended._inbox_cache = {"data": _inbox_warm, "ts": _tw.time()}
            except Exception:
                pass
        pe_ext = _pe_get_extended_snapshot()
        pe_rad = _pe_get_radar_snapshot()
        pe = build_priority_engine(data, pe_ext, pe_rad)
        data["priority_engine"] = pe
        # A1: Assistant Surface Layer
        try:
            data["assistant_surface"] = build_assistant_surface(pe, data)
        except Exception as _as_err:
            logging.getLogger("master_ai").warning("assistant_surface error: %s", _as_err)
            data["assistant_surface"] = {"top_action": {"headline": "", "why_now": ""}, "next_actions": [], "later_today": [], "changes": {}, "meta": {"quiet_mode": True}}
        # A1: ai_insight from assistant surface (action-framed)
        asf_ta = data.get("assistant_surface", {}).get("top_action", {})
        if asf_ta.get("headline"):
            why = asf_ta.get("why_now", "")
            data["ai_insight"] = asf_ta["headline"] + (" \u2014 " + why if why else "")
        elif pe.get("summary_line"):
            data["ai_insight"] = pe["summary_line"]
        else:
            data["ai_insight"] = "\u2705 كل شي تحت السيطرة"
    except Exception as _pe_err:
        logging.getLogger("master_ai").warning("priority_engine in /dashboard error: %s", _pe_err)
        data["priority_engine"] = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "stale": True, "empty_state": True,
            "summary_line": "", "top_priority": None, "priorities": []
        }
        # Fallback to old ai_insight
        parts = []
        if data.get("degraded_mode") not in ("normal", None):
            parts.append("\u26a0 " + str(data["degraded_mode"]))
        sh = data.get("shift_today", "")
        sh2 = data.get("shift_tomorrow", "")
        if sh:
            parts.append(sh + (" \u2192 " + sh2 if sh2 else ""))
        lo = data.get("home_lights_on", -1)
        ao = data.get("home_ac_on", -1)
        if lo >= 0:
            parts.append("\U0001f3e0 " + str(lo) + "\U0001f4a1 " + str(ao) + "\u2744")
        if data.get("top_signal"):
            parts.append("\U0001f4ca " + data["top_signal"])
        if data.get("next_event"):
            parts.append("\U0001f4c5 " + data["next_event"])
        if not parts:
            parts.append("\u2705 كل شي تحت السيطرة")
        data["ai_insight"] = " | ".join(parts[:4])
    return data


# ═══════════════════════════════════════════════════
# /dashboard/cmd — Execute TG command from HA dashboard
# ═══════════════════════════════════════════════════

@router.post("/dashboard/cmd")
async def dashboard_cmd(request: Request):
    """Execute a TG command from HA dashboard. Fire-and-forget with job tracking."""
    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid JSON"}
    cmd = body.get("command", "").strip()
    if not cmd:
        return {"ok": False, "error": "no command"}
    job = {"command": cmd, "status": "running", "result": "", "time": datetime.now().strftime("%H:%M:%S")}
    _ctx["dashboard_jobs"].append(job)
    # Fire-and-forget: return immediately, execute in background
    async def _run_bg():
        try:
            result = await asyncio.wait_for(_ctx["tg_handle_command"](0, cmd), timeout=25)
            job["status"] = "done"
            job["result"] = str(result)[:2000] if result else "done"
        except asyncio.TimeoutError:
            job["status"] = "timeout"
            job["result"] = "قيد التنفيذ — النتيجة بالتلقرام"
        except Exception as ex:
            job["status"] = "error"
            job["result"] = str(ex)[:500]
    asyncio.create_task(_run_bg())
    return {"ok": True, "result": "⏳ جاري التنفيذ..."}


# ═══════════════════════════════════════════════════
# /dashboard/jobs — Last 10 dashboard command results
# ═══════════════════════════════════════════════════

@router.get("/dashboard/jobs")
async def dashboard_jobs_list():
    """Return last 10 dashboard command results."""
    return {"jobs": list(_ctx["dashboard_jobs"])}


# ═══════════════════════════════════════════════════
# /dashboard/radar — Dedicated radar data for HA radar sensor
# ═══════════════════════════════════════════════════

@router.get("/dashboard/radar")
async def ha_dashboard_radar():
    """Dedicated radar data for HA radar sensor -- lightweight, read-only from DB."""
    import sqlite3
    from datetime import date as _d
    data = {}
    try:
        from stock_radar import get_watchlist, get_recent_events, _get_config, get_daily_snapshot
        from tv_data import KSE_STOCKS
        cfg = _get_config()
        wl = get_watchlist()
        events = get_recent_events(20)
        today_str = str(_d.today())
        data["radar_enabled"] = cfg.get("enabled", False)
        data["radar_watch_count"] = len(wl)
        # Enrich watchlist with price/change/reason from daily snapshot
        _daily_by_sym = {}
        try:
            _daily_all = get_daily_snapshot(top_n=200, min_score=0)
            _daily_by_sym = {d["symbol"]: d for d in _daily_all}
        except Exception:
            pass
        _enriched_wl = []
        for s in wl[:12]:
            _sym = s["symbol"] if isinstance(s, dict) else s
            _tf = s.get("timeframe", "30m") if isinstance(s, dict) else "30m"
            _dd = _daily_by_sym.get(_sym, {})
            _price = _dd.get("price", 0)
            _chg = _dd.get("change_pct", 0)
            _score = _dd.get("score", 0)
            _trend = _dd.get("trend", "")
            _rsi = _dd.get("rsi") or 50
            _sup = _dd.get("support")
            _res = _dd.get("resistance")
            # Derive watch_reason
            if _score >= 70 and _trend == "\u0635\u0627\u0639\u062f":
                _reason = "\u0632\u062e\u0645 \u0635\u0627\u0639\u062f \u0642\u0648\u064a"
            elif _rsi and _rsi < 30:
                _reason = "RSI \u0645\u0646\u062e\u0641\u0636 — \u0642\u0631\u064a\u0628 \u0645\u0646 \u0627\u0644\u0642\u0627\u0639"
            elif _rsi and _rsi > 70:
                _reason = "RSI \u0645\u0631\u062a\u0641\u0639 — \u062d\u0630\u0631"
            elif _sup and _price and _price > 0 and abs(_price - _sup) / _price < 0.02:
                _reason = "\u0642\u0631\u064a\u0628 \u0645\u0646 \u0627\u0644\u062f\u0639\u0645"
            elif _res and _price and _price > 0 and abs(_price - _res) / _price < 0.02:
                _reason = "\u0642\u0631\u064a\u0628 \u0645\u0646 \u0627\u0644\u0645\u0642\u0627\u0648\u0645\u0629"
            elif _trend == "\u0647\u0627\u0628\u0637":
                _reason = "\u0627\u062a\u062c\u0627\u0647 \u0647\u0627\u0628\u0637"
            elif _score >= 50:
                _reason = "\u062a\u0642\u064a\u064a\u0645 \u0645\u062a\u0648\u0633\u0637"
            else:
                _reason = "\u0645\u0631\u0627\u0642\u0628\u0629"
            _enriched_wl.append({
                "symbol": _sym,
                "name_ar": KSE_STOCKS.get(_sym, str(_sym)),
                "price": _price,
                "change_pct": round(_chg, 2) if _chg else 0,
                "timeframe": _tf,
                "watch_reason": _reason,
            })
        data["radar_watchlist"] = _enriched_wl
        enriched_signals = []
        for e in events[:10]:
            sym = e.get("symbol", "")
            gap = abs(float(e.get("ema_fast", 0)) - float(e.get("ema_slow", 0)))
            sig = {
                "symbol": sym,
                "name_ar": KSE_STOCKS.get(sym, sym),
                "type": e.get("signal_type", ""),
                "signal_type": e.get("signal_type", ""),
                "type_ar": "\u0635\u0627\u0639\u062f" if "bullish" in e.get("signal_type","") else "\u0647\u0627\u0628\u0637",
                "price": e.get("price", 0),
                "time": e.get("created_at", "")[:16],
                "timeframe": e.get("timeframe", "30m"),
                "ema_fast": round(float(e.get("ema_fast", 0)), 2),
                "ema_slow": round(float(e.get("ema_slow", 0)), 2),
                "ema_gap": round(gap, 3),
                "strength": "\u0642\u0648\u064a\u0629" if gap > 0.5 else "\u0645\u062a\u0648\u0633\u0637\u0629" if gap > 0.1 else "\u0636\u0639\u064a\u0641\u0629",
                "rsi": e.get("rsi"),
                "vwap": e.get("vwap"),
                "volume": e.get("volume", 0),
                "score": e.get("score", 0),
                "score_class": e.get("score_class", ""),
                "verdict": e.get("verdict", ""),
                "support": e.get("support"),
                "resistance": e.get("resistance"),
                "vol_ratio": e.get("vol_ratio", 0),
                "enriched_available": e.get("rsi") is not None,
            }
            enriched_signals.append(sig)
        data["radar_recent_signals"] = enriched_signals
        data["radar_alerts_today"] = len([e for e in events if e.get("created_at","")[:10] == today_str])
    except Exception as _e:
        logging.getLogger("master_ai").warning("dashboard/radar signals error: %s", _e)
        data["radar_enabled"] = False; data["radar_watch_count"] = 0
        data["radar_watchlist"] = []; data["radar_recent_signals"] = []; data["radar_alerts_today"] = 0
    try:
        daily = get_daily_snapshot(top_n=10, min_score=0)
        # Collect 30m signal symbols for action derivation
        _sig_syms = set()
        for _sig in data.get("radar_recent_signals", []):
            _sig_syms.add(_sig.get("symbol", ""))
        daily_clean = []
        for d in daily:
            # Derive action from score + trend + RSI + signals + EMA cross
            _score = d.get("score", 0)
            _trend = d.get("trend", "")
            _rsi = d.get("rsi") or 50
            _in_signals = d["symbol"] in _sig_syms
            _ema9 = d.get("ema_fast") or d.get("daily_ema9") or 0
            _ema21 = d.get("ema_slow") or d.get("daily_ema21") or 0
            _ema_bull = _ema9 > _ema21 > 0
            _ema_bear = 0 < _ema9 < _ema21
            if _score >= 70 and _trend == "\u0635\u0627\u0639\u062f" and _rsi < 70 and _ema_bull:
                _action = "buy"
                _action_ar = "\u0634\u0631\u0627\u0621 \u2014 \u0645\u0624\u0643\u062f"
            elif _score >= 70 and _trend == "\u0635\u0627\u0639\u062f" and _rsi < 70 and _ema_bear:
                _action = "watch"
                _action_ar = "\u0645\u0631\u0627\u0642\u0628\u0629 \u2014 EMA \u0645\u062a\u0636\u0627\u0631\u0628"
            elif _score >= 70 and _trend == "\u0635\u0627\u0639\u062f" and _rsi < 70:
                _action = "buy"
                _action_ar = "\u0634\u0631\u0627\u0621"
            elif _score >= 70 and _trend == "\u0635\u0627\u0639\u062f" and _rsi >= 70:
                _action = "watch"
                _action_ar = "\u0645\u0631\u0627\u0642\u0628\u0629 \u2014 RSI \u0645\u0631\u062a\u0641\u0639"
            elif _trend == "\u0647\u0627\u0628\u0637" and _ema_bear:
                _action = "sell"
                _action_ar = "\u0628\u064a\u0639 \u2014 \u0645\u0624\u0643\u062f"
            elif _trend == "\u0647\u0627\u0628\u0637" and _ema_bull:
                _action = "watch"
                _action_ar = "\u0645\u0631\u0627\u0642\u0628\u0629 \u2014 EMA \u0625\u064a\u062c\u0627\u0628\u064a"
            elif _trend == "\u0647\u0627\u0628\u0637" and _rsi < 30:
                _action = "watch"
                _action_ar = "\u0645\u0631\u0627\u0642\u0628\u0629 \u2014 \u0642\u0631\u064a\u0628 \u0645\u0646 \u0627\u0644\u0642\u0627\u0639"
            elif _trend == "\u0647\u0627\u0628\u0637":
                _action = "sell"
                _action_ar = "\u0628\u064a\u0639"
            elif _in_signals and _score >= 50:
                _action = "watch"
                _action_ar = "\u0645\u0631\u0627\u0642\u0628\u0629 \u2014 \u0625\u0634\u0627\u0631\u0629 30m"
            else:
                _action = "hold"
                _action_ar = "\u0627\u0646\u062a\u0638\u0627\u0631"
            # EMA cross derivation
            if _ema9 > 0 and _ema21 > 0:
                _ema_gap = round((_ema9 - _ema21) / _ema21 * 100, 2)
                if abs(_ema_gap) < 0.3:
                    _ema_cross = "neutral"
                elif _ema9 > _ema21:
                    _ema_cross = "bullish"
                else:
                    _ema_cross = "bearish"
            else:
                _ema_gap = 0
                _ema_cross = None  # null in JSON → JS falls through to daily_ema_cross
            # Compute avg_volume from vol_ratio
            _vol = d.get("volume", 0) or 0
            _vr = d.get("vol_ratio", 0) or 0
            _avg_vol = round(_vol / _vr) if _vr > 0 else 0
            # MACD + Confluence from daily snapshot
            _macd = d.get("macd")
            _macd_sig = d.get("macd_signal")
            _macd_hist = d.get("macd_histogram")
            _macd_cross = d.get("macd_cross", "none")
            _macd_above_zero = bool(d.get("macd_above_zero", False))
            _conf_score = d.get("confluence_score", 0)
            _conf_dir = d.get("confluence_direction", "neutral")
            _daily_ema_cross = d.get("daily_ema_cross", "none")
            _vol_spike = bool(d.get("volume_spike", False))
            # Confluence strength
            _conf_str = "\u0642\u0648\u064a" if abs(_conf_score or 0) >= 60 else "\u0645\u062a\u0648\u0633\u0637" if abs(_conf_score or 0) >= 30 else "\u0636\u0639\u064a\u0641"
            daily_clean.append({
                "symbol": d["symbol"],
                "name_ar": d.get("name_ar", d["symbol"]),
                "price": d.get("price", 0),
                "trend": d.get("trend", ""),
                "rsi": d.get("rsi"),
                "support": d.get("support"),
                "resistance": d.get("resistance"),
                "score": d.get("score", 0),
                "score_class": d.get("score_class", ""),
                "verdict": d.get("verdict", ""),
                "volume": _vol,
                "avg_volume": _avg_vol,
                "vol_ratio": round(_vr, 2) if _vr else 0,
                "change_pct": d.get("change_pct", 0),
                "updated_at": d.get("updated_at", ""),
                "data_age_hours": d.get("data_age_hours", 999),
                "is_stale": d.get("is_stale", True),
                "source_timeframe": d.get("source_timeframe", "1D"),
                "action": _action,
                "action_ar": _action_ar,
                "ema9": round(_ema9, 2) if _ema9 else None,
                "ema21": round(_ema21, 2) if _ema21 else None,
                "ema_cross": _ema_cross,
                "ema_gap_pct": _ema_gap,
                # MACD data
                "macd": round(_macd, 3) if _macd is not None else None,
                "macd_signal": round(_macd_sig, 3) if _macd_sig is not None else None,
                "macd_histogram": round(_macd_hist, 3) if _macd_hist is not None else None,
                "macd_cross": _macd_cross,
                "macd_above_zero": _macd_above_zero,
                # Daily EMA cross
                "daily_ema_cross": _daily_ema_cross,
                # Volume spike
                "volume_spike": _vol_spike,
                # Confluence
                "confluence": {
                    "score": _conf_score or 0,
                    "direction": _conf_dir,
                    "strength_ar": _conf_str,
                },
                # New indicators
                "stoch_k": d.get("stoch_k"),
                "adx": d.get("adx"),
                "rsi_divergence": d.get("rsi_divergence"),
                "atr": d.get("atr"),
            })
        data["radar_daily_context"] = daily_clean
        data["daily_context_stale"] = all(d.get("is_stale", True) for d in daily) if daily else True
        if not daily_clean:
            data["daily_context_reason"] = "daily context not initialized yet"
        elif data["daily_context_stale"]:
            data["daily_context_reason"] = "data available but stale"
        else:
            data["daily_context_reason"] = "ok"
    except Exception as _e:
        logging.getLogger("master_ai").warning("dashboard/radar daily context error: %s", _e)
        data["radar_daily_context"] = []
        data["daily_context_stale"] = True
        data["daily_context_reason"] = f"error: {_e}"
    # ── Journal data with live P&L in KWD + broker fees ──
    try:
        if _ctx.get("journal_ok", False):
            _open_trades = _ctx["get_open_trades"]()
            # Enrich with live P&L from daily snapshot (no blocking API calls)
            try:
                import sqlite3 as _sq3
                from journal_engine import calculate_real_pnl
                _rdb = _sq3.connect("data/life.db", timeout=3)
                _rdb.row_factory = _sq3.Row
                for _t in _open_trades:
                    try:
                        from tv_data import resolve_symbol, _normalize_price_to_fils
                        _rsym = resolve_symbol(_t["symbol"])
                        _dr = _rdb.execute(
                            "SELECT price FROM stock_radar_daily WHERE symbol=? ORDER BY rowid DESC LIMIT 1",
                            (_rsym,)
                        ).fetchone()
                        if _dr:
                            _cur = _normalize_price_to_fils(float(_dr["price"]), _rsym)
                            _entry = float(_t.get("entry_price", 0))
                            _qty = int(_t.get("quantity", 0))
                            _t["current_price"] = _cur
                            if _entry and _qty:
                                _t["pnl"] = calculate_real_pnl(_entry, _cur, _qty)
                            else:
                                _t["pnl_pct"] = round((_cur / _entry - 1) * 100, 2) if _entry else 0
                                _t["pnl_fils"] = round((_cur - _entry) * _qty) if _qty else 0
                    except Exception:
                        pass
                _rdb.close()
            except Exception:
                pass
            data["journal_open"] = _open_trades
            data["journal_stats"] = _ctx["get_trade_stats"](days=30)
        else:
            data["journal_open"] = []
            data["journal_stats"] = {}
    except Exception as _je:
        logging.getLogger("master_ai").warning("dashboard/radar journal error: %s", _je)
        data["journal_open"] = []
        data["journal_stats"] = {}
    return data


# ═══════════════════════════════════════════════════
# /dashboard/portfolio — Portfolio + Journal data
# ═══════════════════════════════════════════════════

@router.get("/dashboard/portfolio")
async def ha_dashboard_portfolio():
    """Portfolio data for HA dashboard — open positions, closed trades, stats."""
    data = {}

    # Open positions with live P&L in KWD + broker fees
    try:
        if _ctx.get("journal_ok", False):
            from journal_engine import get_open_trades, get_trade_stats, get_recent_trades, calculate_real_pnl, get_fresh_price
            open_trades = get_open_trades()
            # Enrich with current prices + S/R + P&L
            _rdb = None
            try:
                _rdb = sqlite3.connect("data/life.db", timeout=3)
                _rdb.row_factory = sqlite3.Row
            except Exception:
                pass
            for t in open_trades:
                _entry = float(t.get("entry_price", 0) or 0)
                _qty = int(t.get("quantity", 0) or 0)
                _cur = None
                _src = "unknown"
                _stale = True
                sym = t.get("symbol", "").upper()

                # Layer 1: Bridge cache (freshest)
                try:
                    fp = get_fresh_price(sym)
                    if fp.get("price"):
                        _cur = float(fp["price"])
                        _src = fp.get("source", "bridge")
                        _stale = fp.get("stale", False)
                except Exception:
                    pass

                # Layer 2: Radar daily DB (fallback)
                if _cur is None and _rdb:
                    try:
                        from tv_data import resolve_symbol, _normalize_price_to_fils
                        _rsym = resolve_symbol(sym)
                        _dr = _rdb.execute(
                            "SELECT price, support, resistance FROM stock_radar_daily WHERE symbol=? ORDER BY rowid DESC LIMIT 1",
                            (_rsym,)
                        ).fetchone()
                        if _dr and _dr["price"]:
                            _cur = _normalize_price_to_fils(float(_dr["price"]), _rsym)
                            _src = "radar_daily"
                            _stale = True
                            t["support"] = _dr["support"]
                            t["resistance"] = _dr["resistance"]
                    except Exception:
                        pass

                # Set current price + source
                if _cur:
                    t["current_price"] = _cur
                t["quote_source"] = _src
                t["quote_stale"] = _stale

                # ALWAYS compute P&L when we have entry + current price
                if _entry and _cur:
                    t["pnl_pct"] = round((_cur / _entry - 1) * 100, 2)
                    if _qty:
                        t["pnl"] = calculate_real_pnl(_entry, _cur, _qty)
                        t["pnl_fils"] = round((_cur - _entry) * _qty)
                        t["pnl_kwd"] = round((_cur - _entry) * _qty / 1000, 3)
                    else:
                        t["pnl_fils"] = round(_cur - _entry)
                        t["pnl_kwd"] = round((_cur - _entry) / 1000, 3)
                else:
                    t["pnl_pct"] = 0
                    t["pnl_fils"] = 0
                    t["pnl_kwd"] = 0

            if _rdb:
                try:
                    _rdb.close()
                except Exception:
                    pass
            # Enrich with signal_health + alerts from signal_engine
            try:
                from signal_engine import build_signals
                sig_result = build_signals()
                sig_map = {s["symbol"]: s for s in (sig_result.get("all_signals") or [])}
                for t in open_trades:
                    sym = t.get("symbol", "").upper()
                    sig = sig_map.get(sym)
                    if sig:
                        t["signal_health"] = {
                            "confluence_score": sig.get("confluence_score", 0),
                            "verdict": sig.get("verdict", ""),
                            "rsi_14": sig.get("rsi_14"),
                            "macd_momentum": sig.get("macd_momentum", ""),
                            "rsi_divergence": sig.get("rsi_divergence"),
                            "adx": sig.get("adx"),
                        }
                        alerts = []
                        cs = sig.get("confluence_score", 100)
                        if cs < 40:
                            alerts.append({"level": "danger", "message": "\u0628\u064a\u0639 \u2014 confluence \u0636\u0639\u064a\u0641"})
                        if sig.get("rsi_divergence") == "bearish":
                            alerts.append({"level": "warning", "message": "\u0645\u0631\u0627\u062c\u0639\u0629 \u2014 divergence \u0633\u0644\u0628\u064a"})
                        sl = t.get("stop_loss")
                        cp = t.get("current_price", 0)
                        if sl and cp and cp < sl:
                            alerts.append({"level": "danger", "message": "\u0628\u064a\u0639 \u0641\u0648\u0631\u0627\u064b \u2014 \u0648\u0642\u0641 \u0627\u0644\u062e\u0633\u0627\u0631\u0629"})
                        mom = sig.get("macd_momentum", "")
                        if "bearish" in mom and cs < 50:
                            alerts.append({"level": "warning", "message": "\u0645\u0631\u0627\u062c\u0639\u0629 \u2014 momentum \u0633\u0644\u0628\u064a"})
                        t["alerts"] = alerts
                    else:
                        t["signal_health"] = {}
                        t["alerts"] = []
            except Exception:
                for t in open_trades:
                    t["signal_health"] = {}
                    t["alerts"] = []

            # ATR trailing stop suggestions
            try:
                from journal_engine import suggest_trailing_stop
                for t in open_trades:
                    if t.get("id"):
                        ts = suggest_trailing_stop(t["id"])
                        if ts:
                            t["trailing_stop"] = ts["suggested_stop"]
                            t["atr"] = ts["atr"]
                            t["trailing_distance_pct"] = ts["distance_pct"]
            except Exception:
                pass

            data["open_positions"] = open_trades
        else:
            data["open_positions"] = []
    except Exception:
        data["open_positions"] = []

    # Closed trades (recent)
    try:
        from journal_engine import get_recent_trades
        all_trades = get_recent_trades(limit=50)
        data["closed_trades"] = [t for t in all_trades if t.get("status") == "closed"][:20]
    except Exception:
        data["closed_trades"] = []

    # 30-day and 7-day stats
    try:
        from journal_engine import get_trade_stats
        data["stats_30d"] = get_trade_stats(days=30)
        data["stats_7d"] = get_trade_stats(days=7)
    except Exception:
        data["stats_30d"] = {}
        data["stats_7d"] = {}

    # Signal vs trade ratio (7 days)
    try:
        conn = sqlite3.connect("data/life.db", timeout=3)
        signals_7d = conn.execute(
            "SELECT COUNT(*) FROM stock_radar_events WHERE created_at > datetime('now', '-7 days')"
        ).fetchone()[0]
        confirmed_7d = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE created_at > datetime('now', '-7 days')"
        ).fetchone()[0]
        data["signal_vs_trade"] = {
            "signals_7d": signals_7d,
            "confirmed_7d": confirmed_7d,
            "skip_rate": round((1 - confirmed_7d / max(signals_7d, 1)) * 100, 1)
        }
        conn.close()
    except Exception:
        data["signal_vs_trade"] = {}

    return data


# ═══════════════════════════════════════════════════
# /dashboard/journal — Detailed trade journal + monthly stats
# ═══════════════════════════════════════════════════

@router.get("/dashboard/journal")
async def ha_dashboard_journal():
    """Detailed trade journal with P&L in KWD, monthly stats, best/worst trades."""
    data = {}
    try:
        from journal_engine import get_open_trades, get_recent_trades, get_trade_stats, calculate_real_pnl, get_fresh_price
        from tv_data import resolve_symbol, _normalize_price_to_fils

        # ── Open positions with real P&L + S/R ──
        open_trades = get_open_trades()
        total_net_pnl_kwd = 0
        total_gross_pnl_kwd = 0
        total_fees_kwd = 0
        _rdb2 = None
        try:
            _rdb2 = sqlite3.connect("data/life.db", timeout=3)
            _rdb2.row_factory = sqlite3.Row
        except Exception:
            pass
        for t in open_trades:
            _entry = float(t.get("entry_price", 0) or 0)
            _qty = int(t.get("quantity", 0) or 0)
            _cur = None
            sym = t.get("symbol", "").upper()
            # Layer 1: Bridge
            try:
                fp = get_fresh_price(sym)
                if fp.get("price"):
                    _cur = float(fp["price"])
                    t["quote_source"] = fp.get("source", "bridge")
                    t["quote_stale"] = fp.get("stale", False)
            except Exception:
                pass
            # Layer 2: Radar daily
            if _cur is None and _rdb2:
                try:
                    _rsym = resolve_symbol(sym)
                    _dr = _rdb2.execute(
                        "SELECT price, support, resistance FROM stock_radar_daily WHERE symbol=? ORDER BY rowid DESC LIMIT 1",
                        (_rsym,)
                    ).fetchone()
                    if _dr and _dr["price"]:
                        _cur = _normalize_price_to_fils(float(_dr["price"]), _rsym)
                        t["quote_source"] = "radar_daily"
                        t["quote_stale"] = True
                        t["support"] = _dr["support"]
                        t["resistance"] = _dr["resistance"]
                except Exception:
                    pass
            if _cur:
                t["current_price"] = _cur
            # Always compute P&L
            if _entry and _cur:
                t["pnl_pct"] = round((_cur / _entry - 1) * 100, 2)
                if _qty:
                    pnl = calculate_real_pnl(_entry, _cur, _qty)
                    t["pnl"] = pnl
                    t["pnl_kwd"] = pnl["net_pnl_kwd"]
                    t["pnl_fils"] = pnl["net_pnl_fils"]
                    total_net_pnl_kwd += pnl["net_pnl_kwd"]
                    total_gross_pnl_kwd += pnl["gross_pnl_kwd"]
                    total_fees_kwd += pnl["total_fees_kwd"]
                else:
                    t["pnl_fils"] = round(_cur - _entry)
                    t["pnl_kwd"] = round((_cur - _entry) / 1000, 3)
            else:
                t["pnl_pct"] = 0
                t["pnl_fils"] = 0
                t["pnl_kwd"] = 0
        if _rdb2:
            try:
                _rdb2.close()
            except Exception:
                pass
        data["open_positions"] = open_trades

        # ── Closed trades with P&L in KWD ──
        all_trades = get_recent_trades(limit=100)
        closed = [t for t in all_trades if t.get("status") == "closed"]
        for t in closed:
            _entry = float(t.get("entry_price", 0))
            _exit = float(t.get("exit_price", 0))
            _qty = int(t.get("quantity", 0))
            if _entry and _exit and _qty:
                t["pnl"] = calculate_real_pnl(_entry, _exit, _qty)
        data["closed_trades"] = closed[:20]

        # ── Summary stats ──
        stats_30d = get_trade_stats(days=30)
        stats_7d = get_trade_stats(days=7)
        data["stats_30d"] = stats_30d
        data["stats_7d"] = stats_7d

        # ── Total portfolio P&L ──
        data["portfolio_summary"] = {
            "open_count": len(open_trades),
            "total_net_pnl_kwd": round(total_net_pnl_kwd, 3),
            "total_gross_pnl_kwd": round(total_gross_pnl_kwd, 3),
            "total_fees_kwd": round(total_fees_kwd, 3),
        }

        # ── Monthly stats ──
        try:
            conn = sqlite3.connect("data/life.db", timeout=3)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT strftime('%Y-%m', entry_date) as month,
                       COUNT(*) as total,
                       SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN pnl_pct <= 0 THEN 1 ELSE 0 END) as losses,
                       SUM(pnl_fils) as total_pnl_fils,
                       AVG(pnl_pct) as avg_pnl_pct
                FROM trades WHERE status='closed'
                GROUP BY month ORDER BY month DESC LIMIT 6
            """).fetchall()
            data["monthly_stats"] = [{
                "month": r["month"],
                "total": r["total"],
                "wins": r["wins"] or 0,
                "losses": r["losses"] or 0,
                "total_pnl_kwd": round((r["total_pnl_fils"] or 0) / 1000, 3),
                "win_rate": round((r["wins"] or 0) / max(r["total"], 1) * 100, 0),
            } for r in rows]
            conn.close()
        except Exception:
            data["monthly_stats"] = []

        # ── Best/Worst trades ──
        data["best_trade"] = stats_30d.get("best_trade")
        data["worst_trade"] = stats_30d.get("worst_trade")

    except Exception as e:
        logging.getLogger("master_ai").warning("dashboard/journal error: %s", e)
        data = {"open_positions": [], "closed_trades": [], "stats_30d": {},
                "stats_7d": {}, "portfolio_summary": {}, "monthly_stats": [],
                "best_trade": None, "worst_trade": None}

    return data


# ═══════════════════════════════════════════════════
# /dashboard/alerts — Smart trading alerts
# ═══════════════════════════════════════════════════

@router.get("/dashboard/alerts")
async def ha_dashboard_alerts():
    """Smart alerts: volume spikes, S/R proximity, confluence, RSI extremes."""
    data = {"volume_spikes": [], "sr_proximity": [], "confluence_alerts": [], "rsi_extremes": []}
    try:
        from stock_radar import get_daily_snapshot
        from tv_data import KSE_STOCKS
        daily = get_daily_snapshot(top_n=200, min_score=0)
        if not daily:
            return data

        for d in daily:
            sym = d["symbol"]
            name_ar = d.get("name_ar", KSE_STOCKS.get(sym, sym))
            price = d.get("price", 0)
            vr = d.get("vol_ratio", 0) or 0
            vol = d.get("volume", 0) or 0
            avg_vol = d.get("avg_volume") or (round(vol / vr) if vr > 0 else 0)
            rsi = d.get("rsi")
            support = d.get("support")
            resistance = d.get("resistance")
            conf_score = d.get("confluence_score", 0) or 0
            conf_dir = d.get("confluence_direction", "neutral")
            macd_cross = d.get("macd_cross", "none")
            daily_ema_cross = d.get("daily_ema_cross", "none")

            # Volume spikes (>=2x average)
            if vr >= 2:
                data["volume_spikes"].append({
                    "symbol": sym, "name_ar": name_ar, "price": price,
                    "volume": vol, "avg_volume": avg_vol,
                    "vol_ratio": round(vr, 1),
                    "is_spike": vr >= 3,
                })

            # S/R proximity (within 5%)
            if price and price > 0:
                if support and abs(price - support) / price < 0.05:
                    dist_pct = round((price - support) / price * 100, 1)
                    data["sr_proximity"].append({
                        "symbol": sym, "name_ar": name_ar, "price": price,
                        "level": support, "type": "support",
                        "distance_pct": dist_pct,
                    })
                if resistance and abs(price - resistance) / price < 0.05:
                    dist_pct = round((resistance - price) / price * 100, 1)
                    data["sr_proximity"].append({
                        "symbol": sym, "name_ar": name_ar, "price": price,
                        "level": resistance, "type": "resistance",
                        "distance_pct": dist_pct,
                    })

            # Multi-TF Confluence alerts (strong only)
            if abs(conf_score) >= 40:
                data["confluence_alerts"].append({
                    "symbol": sym, "name_ar": name_ar, "price": price,
                    "confluence_score": conf_score,
                    "direction": conf_dir,
                    "macd_cross": macd_cross,
                    "daily_ema_cross": daily_ema_cross,
                })

            # RSI extremes
            if rsi and (rsi > 70 or rsi < 30):
                data["rsi_extremes"].append({
                    "symbol": sym, "name_ar": name_ar, "price": price,
                    "rsi": round(rsi, 1),
                    "type": "overbought" if rsi > 70 else "oversold",
                    "type_ar": "\u062a\u0634\u0628\u0639 \u0634\u0631\u0627\u0626\u064a" if rsi > 70 else "\u062a\u0634\u0628\u0639 \u0628\u064a\u0639\u064a",
                })

        # Sort by relevance
        data["volume_spikes"].sort(key=lambda x: x["vol_ratio"], reverse=True)
        data["sr_proximity"].sort(key=lambda x: abs(x["distance_pct"]))
        data["confluence_alerts"].sort(key=lambda x: abs(x["confluence_score"]), reverse=True)
        data["rsi_extremes"].sort(key=lambda x: abs(x["rsi"] - 50), reverse=True)

    except Exception as e:
        logging.getLogger("master_ai").warning("dashboard/alerts error: %s", e)

    return data


# ═══════════════════════════════════════════════════
# /dashboard/confluence — Smart Confluence Decision Engine
# ═══════════════════════════════════════════════════

@router.get("/dashboard/confluence")
async def ha_dashboard_confluence():
    """Confluence decision engine data — actionable BUY signals + watchlist."""
    data = {
        "scan_active": False, "last_scan": "", "scan_stale": False,
        "stocks_scanned": 0, "actionable_count": 0, "watch_count": 0,
        "actionable": [], "watchlist": [], "market_summary": {},
    }
    try:
        from confluence_engine import get_actionable_signals, get_watchlist_signals, get_confluence_stats, _dedup_items_keep_latest
        stats = get_confluence_stats()

        # Dual mode: discovery + confirmation
        disc_act = get_actionable_signals(limit=5, mode="discovery")
        conf_act = get_actionable_signals(limit=5, mode="confirmation")
        disc_watch = get_watchlist_signals(limit=8, mode="discovery")
        conf_watch = get_watchlist_signals(limit=8, mode="confirmation")

        last_scan = stats.get("last_scan", "")
        scan_stale = False
        if last_scan:
            from datetime import datetime, timedelta
            try:
                ls_dt = datetime.fromisoformat(last_scan)
                scan_stale = (datetime.now() - ls_dt) > timedelta(hours=2)
            except Exception:
                pass

        data["scan_active"] = bool(last_scan and not scan_stale)
        data["last_scan"] = last_scan
        data["scan_stale"] = scan_stale
        data["stocks_scanned"] = stats.get("total_scanned", 0)
        # Backward compatible flat lists (discovery first) — dedup safety net
        all_actionable = _dedup_items_keep_latest(disc_act + conf_act)
        all_watchlist = _dedup_items_keep_latest(disc_watch + conf_watch)
        data["actionable"] = all_actionable
        data["actionable_count"] = len(all_actionable)
        data["watchlist"] = all_watchlist
        data["watch_count"] = len(all_watchlist)
        # Dual mode split
        data["discovery"] = {
            "actionable": disc_act, "actionable_count": len(disc_act),
            "watchlist": disc_watch, "watch_count": len(disc_watch),
        }
        data["confirmation"] = {
            "actionable": conf_act, "actionable_count": len(conf_act),
            "watchlist": conf_watch, "watch_count": len(conf_watch),
        }
        data["market_summary"] = {
            "high_count": stats.get("high_count", 0),
            "medium_count": stats.get("medium_count", 0),
            "low_count": max(0, stats.get("total_scanned", 0) - stats.get("high_count", 0) - stats.get("medium_count", 0)),
            "avg_confluence": stats.get("avg_confluence", 0),
        }
    except Exception as e:
        logging.getLogger("master_ai").warning("dashboard/confluence error: %s", e)

    return data


# ═══════════════════════════════════════════════════
# /dashboard/analysis — Trading analysis + signal stats
# ═══════════════════════════════════════════════════

@router.get("/dashboard/analysis")
async def ha_dashboard_analysis():
    """Trading analysis data for HA dashboard — TV alerts, signal history, stats."""
    data = {}

    try:
        conn = sqlite3.connect("data/life.db", timeout=3)
        conn.row_factory = sqlite3.Row
    except Exception:
        return {"tv_alerts": [], "signal_history": [], "signal_stats": [], "radar_accuracy": {}}

    # TV alert history
    try:
        rows = conn.execute(
            "SELECT ticker, price, signal, strategy_name, evaluation_score, event_time "
            "FROM tv_alert_events ORDER BY id DESC LIMIT 20"
        ).fetchall()
        data["tv_alerts"] = []
        for r in rows:
            _p = r["price"]
            if _p is not None and float(_p) < 10:
                _p = round(float(_p) * 1000, 1)
            data["tv_alerts"].append({
                "ticker": r["ticker"], "price": _p, "signal": r["signal"],
                "strategy": r["strategy_name"], "score": r["evaluation_score"],
                "time": r["event_time"]
            })
    except Exception:
        data["tv_alerts"] = []

    # Signal history (radar events)
    try:
        rows = conn.execute(
            "SELECT symbol, signal_type, price, score, created_at "
            "FROM stock_radar_events ORDER BY created_at DESC LIMIT 30"
        ).fetchall()
        data["signal_history"] = [
            {"symbol": r["symbol"], "type": r["signal_type"], "price": r["price"],
             "score": r["score"], "time": r["created_at"]}
            for r in rows
        ]
    except Exception:
        data["signal_history"] = []

    # Signal stats per ticker (TV)
    try:
        rows = conn.execute(
            "SELECT ticker, strategy_name, signal_type, count_total, last_seen_at "
            "FROM tv_signal_stats ORDER BY count_total DESC LIMIT 20"
        ).fetchall()
        data["signal_stats"] = [
            {"ticker": r["ticker"], "strategy": r["strategy_name"],
             "signal_type": r["signal_type"], "count": r["count_total"], "last_seen": r["last_seen_at"]}
            for r in rows
        ]
    except Exception:
        data["signal_stats"] = []

    # Radar accuracy summary
    try:
        total = conn.execute("SELECT COUNT(*) FROM stock_radar_events").fetchone()[0]
        bullish = conn.execute(
            "SELECT COUNT(*) FROM stock_radar_events WHERE signal_type='bullish_cross'"
        ).fetchone()[0]
        bearish = conn.execute(
            "SELECT COUNT(*) FROM stock_radar_events WHERE signal_type='bearish_cross'"
        ).fetchone()[0]
        avg_score = conn.execute("SELECT AVG(score) FROM stock_radar_events").fetchone()[0]
        data["radar_accuracy"] = {
            "total_signals": total,
            "bullish": bullish,
            "bearish": bearish,
            "avg_score": round(avg_score, 1) if avg_score else 0
        }
    except Exception:
        data["radar_accuracy"] = {}

    # Daily summary — built from today's data
    try:
        from datetime import date as _date
        _today = _date.today().isoformat()
        _sig_today = conn.execute(
            "SELECT COUNT(*) FROM stock_radar_events WHERE date(created_at)=?", (_today,)
        ).fetchone()[0]
        _bull_today = conn.execute(
            "SELECT COUNT(*) FROM stock_radar_events WHERE date(created_at)=? AND signal_type='bullish_cross'",
            (_today,)
        ).fetchone()[0]
        _bear_today = conn.execute(
            "SELECT COUNT(*) FROM stock_radar_events WHERE date(created_at)=? AND signal_type='bearish_cross'",
            (_today,)
        ).fetchone()[0]
        # Today's trades
        _trades_today = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE date(created_at)=?", (_today,)
        ).fetchone()[0]
        data["daily_summary"] = {
            "date": _today,
            "signals_today": _sig_today,
            "bullish_today": _bull_today,
            "bearish_today": _bear_today,
            "trades_today": _trades_today,
        }
    except Exception:
        data["daily_summary"] = None

    conn.close()
    return data


# ═══════════════════════════════════════════════════
# _parse_news_items helper
# ═══════════════════════════════════════════════════

def _parse_news_items(digest: dict) -> list:
    """Parse news category text blobs into structured items array."""
    items = []
    categories = [
        ("urgent", "عاجل", "🔥", 1),
        ("economic", "اقتصاد", "💰", 2),
        ("local", "محلي", "🇰🇼", 3),
        ("tech", "تقنية", "💻", 4),
        ("ai", "ذكاء اصطناعي", "🤖", 5),
        ("gadgets", "أجهزة", "📱", 6),
    ]
    for key, ar, emoji, pri in categories:
        text = digest.get(key, "") or ""
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            clean = line
            for ch in ["🔥", "💰", "🇰🇼", "💻", "🤖", "📱", "⚡", "🛡"]:
                clean = clean.lstrip(ch)
            clean = clean.strip(" \u200f\u200e")
            if not clean:
                continue
            source = ""
            if clean.endswith(")") and "(" in clean:
                idx = clean.rfind("(")
                source = clean[idx+1:-1].strip()
                clean = clean[:idx].strip()
            items.append({
                "category": key,
                "category_ar": ar,
                "emoji": emoji,
                "text": clean,
                "source": source,
                "priority": pri,
            })
    return items


# ═══════════════════════════════════════════════════
# /dashboard/extended — Extended data for HA subviews
# ═══════════════════════════════════════════════════

@router.get("/dashboard/extended")
async def ha_dashboard_extended():
    """Extended data for HA subviews: radar details, tasks list, events, system health."""
    import psutil, subprocess, sqlite3
    from datetime import date as _d
    data = {}

    # -- Radar data moved to /dashboard/radar endpoint --
    # Radar fields are now served by sensor.master_ai_radar
    # via /dashboard/radar -- no longer in /dashboard/extended.

    # ── Tasks List ──
    try:
        conn = sqlite3.connect("data/life.db", timeout=3)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, title, priority, category, due_date, status FROM tasks WHERE status='todo' ORDER BY priority, due_date LIMIT 15").fetchall()
        data["tasks_list"] = [dict(r) for r in rows]
        data["tasks_done_today"] = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='done' AND updated_at LIKE ?", (str(_d.today())+"%",)).fetchone()[0]
        conn.close()
    except Exception:
        data["tasks_list"] = []; data["tasks_done_today"] = 0

    # ── Calendar Events ──
    try:
        conn = sqlite3.connect("data/life.db", timeout=3)
        conn.row_factory = sqlite3.Row
        today_str = str(_d.today())
        tomorrow_str = str(_d.today() + timedelta(days=1))
        rows = conn.execute("SELECT summary, start_ts, end_ts, location FROM calendar_events WHERE (start_ts LIKE ? OR start_ts LIKE ?) AND status='confirmed' ORDER BY start_ts LIMIT 10", (today_str+"%", tomorrow_str+"%")).fetchall()
        data["events_list"] = [dict(r) for r in rows]
        conn.close()
    except Exception:
        data["events_list"] = []

    # ── System Health ──
    try:
        data["cpu"] = psutil.cpu_percent(interval=0.3)
        data["memory_pct"] = psutil.virtual_memory().percent
        data["memory_used_mb"] = round(psutil.virtual_memory().used / 1024 / 1024)
        data["memory_total_mb"] = round(psutil.virtual_memory().total / 1024 / 1024)
        data["disk_pct"] = psutil.disk_usage("/").percent
        data["disk_used_gb"] = round(psutil.disk_usage("/").used / 1024**3, 1)
        data["disk_total_gb"] = round(psutil.disk_usage("/").total / 1024**3, 1)
        try:
            data["temperature"] = round(float(open("/sys/class/thermal/thermal_zone0/temp").read().strip()) / 1000, 1)
        except Exception:
            data["temperature"] = 0
        data["uptime_hours"] = round((time.time() - _ctx["start_time"]) / 3600, 1)
        data["load_avg"] = list(os.getloadavg())
    except Exception:
        data["cpu"] = 0; data["memory_pct"] = 0; data["memory_used_mb"] = 0; data["memory_total_mb"] = 0
        data["disk_pct"] = 0; data["disk_used_gb"] = 0; data["disk_total_gb"] = 0
        data["temperature"] = 0; data["uptime_hours"] = 0; data["load_avg"] = [0,0,0]

    # ── Git Info ──
    try:
        git_log = subprocess.check_output(
            ["git", "log", "--oneline", "-5"], cwd="/var/lib/homeassistant/share/master_ai",
            timeout=5, text=True
        ).strip().split("\n")
        data["git_log"] = git_log
        data["git_branch"] = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd="/var/lib/homeassistant/share/master_ai",
            timeout=3, text=True
        ).strip()
        data["git_commit_count"] = subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"], cwd="/var/lib/homeassistant/share/master_ai",
            timeout=3, text=True
        ).strip()
    except Exception:
        data["git_log"] = []; data["git_branch"] = "?"; data["git_commit_count"] = "?"

    # ── Tool Usage (top 10) ──
    try:
        conn = sqlite3.connect("data/audit.db", timeout=3)
        rows = conn.execute("SELECT COALESCE(route_type,'unknown'), COUNT(*) as cnt FROM audit_log GROUP BY route_type ORDER BY cnt DESC LIMIT 10").fetchall()
        data["tool_usage"] = [{"tool": r[0], "count": r[1]} for r in rows]
        data["total_requests"] = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        conn.close()
    except Exception:
        data["tool_usage"] = []; data["total_requests"] = 0

    # ── Cost (real token tracking from cost_tracker.py) ──
    try:
        from cost_tracker import get_cost_for_kpi
        _ck = get_cost_for_kpi()
        data["cost_today_usd"] = _ck.get("today_usd", 0)
        data["cost_total_usd"] = _ck.get("month_usd", 0)
        data["avg_cost_per_request"] = _ck.get("avg_per_request_usd", 0)
    except Exception:
        data["cost_today_usd"] = 0; data["cost_total_usd"] = 0; data["avg_cost_per_request"] = 0

    # ── Memory Stats ──
    try:
        conn = sqlite3.connect("data/structured_memory.db", timeout=3)
        data["memory_total"] = conn.execute("SELECT COUNT(*) FROM memories WHERE active=1").fetchone()[0]
        rows = conn.execute("SELECT type, COUNT(*) FROM memories WHERE active=1 GROUP BY type").fetchall()
        data["memory_by_type"] = {r[0]: r[1] for r in rows}
        conn.close()
    except Exception:
        data["memory_total"] = 0; data["memory_by_type"] = {}

    # ── Shift Week Schedule ──
    try:
        from life_work import get_shift
        from datetime import date as _d
        week = []
        day_names_ar = ["الإثنين","الثلاثاء","الأربعاء","الخميس","الجمعة","السبت","الأحد"]
        for i in range(7):
            d = _d.today() + timedelta(days=i)
            s = get_shift(d)
            week.append({
                "day": day_names_ar[d.weekday()],
                "date": str(d),
                "shift": s.get("shift","?"),
                "emoji": s.get("emoji","")
            })
        data["shift_week"] = week
    except Exception:
        data["shift_week"] = []

    # ── Anomaly Count (from home_brain) ──
    try:
        conn = sqlite3.connect("data/home_brain.db", timeout=3)
        today_str = str(_d.today())
        data["anomalies_today"] = conn.execute("SELECT COUNT(*) FROM anomaly_log WHERE detected_at LIKE ?", (today_str+"%",)).fetchone()[0]
        conn.close()
    except Exception:
        data["anomalies_today"] = 0

    # ── Email Inbox (last 24h, cached 5min) ──
    try:
        from inbox_engine import fetch_unified_inbox
        import time as _time_mod
        _now = _time_mod.time()
        if not hasattr(ha_dashboard_extended, '_inbox_cache') or (_now - ha_dashboard_extended._inbox_cache.get('ts', 0)) > 300:
            inbox_data = await fetch_unified_inbox(hours=24, limit=15)
            ha_dashboard_extended._inbox_cache = {'data': inbox_data, 'ts': _now}
        else:
            inbox_data = ha_dashboard_extended._inbox_cache['data']
        msgs = inbox_data.get("messages", [])
        email_list = []
        for m in msgs[:10]:
            pri = m.get("_priority", 1)
            pri_label = {4: "\u0639\u0627\u062c\u0644", 3: "\u0645\u0647\u0645", 2: "\u0639\u0627\u062f\u064a", 1: "\u0645\u0646\u062e\u0641\u0636"}.get(pri, "?")
            pri_emoji = {4: "\U0001f6a8", 3: "\U0001f534", 2: "\U0001f7e1", 1: "\U0001f7e2"}.get(pri, "")
            email_list.append({
                "from": (m.get("sender") or m.get("from_name") or m.get("from", ""))[:30],
                "subject": m.get("subject", "(no subject)")[:50],
                "source": m.get("source", ""),
                "source_label": "Gmail" if m.get("source") == "gmail" else "KNPC",
                "priority": pri,
                "priority_label": pri_emoji + " " + pri_label,
                "unread": m.get("unread", False),
                "time": (m.get("date") or m.get("time", ""))[:16],
            })
        data["email_messages"] = email_list
        data["email_total"] = inbox_data.get("total", 0)
        data["email_unread"] = sum(1 for m in msgs if m.get("unread"))
        data["email_critical"] = sum(1 for m in msgs if m.get("_priority") == 4)
        data["email_high"] = sum(1 for m in msgs if m.get("_priority") == 3)
        data["email_errors"] = inbox_data.get("errors", [])
    except Exception as _e:
        logging.getLogger("master_ai").warning("dashboard/extended email error: %s", _e)
        data["email_messages"] = []
        data["email_total"] = 0
        data["email_unread"] = 0
        data["email_critical"] = 0
        data["email_high"] = 0
        data["email_errors"] = [str(_e)]

    # ── News Digest ──
    try:
        from news_engine import get_today_digests, get_latest_digest, CATEGORIES
        digests_today = get_today_digests()
        latest = digests_today[0] if digests_today else get_latest_digest()
        if latest:
            cat_info = CATEGORIES.get(latest.get("category", ""), {})
            # Split summary into category fields to avoid HA truncation
            _raw_summary = latest.get("summary_text", "")
            _lines = [ln.strip() for ln in _raw_summary.split("\n") if ln.strip()]
            _urgent, _economic, _local, _tech, _ai, _gadgets, _other = [], [], [], [], [], [], []
            for _ln in _lines:
                if any(_ln.startswith(p) for p in ["\U0001f525", "\u2694", "\U0001f494", "\u26a0"]):
                    _urgent.append(_ln)
                elif any(_ln.startswith(p) for p in ["\U0001f4b0", "\U0001f4ca", "\U0001f4c8", "\U0001f4c9"]):
                    _economic.append(_ln)
                elif _ln.startswith("\U0001f1f0\U0001f1fc"):
                    _local.append(_ln)
                elif any(_ln.startswith(p) for p in ["\u26a1", "\U0001f6e1", "\U0001f4bb"]):
                    _tech.append(_ln)
                elif _ln.startswith("\U0001f916"):
                    _ai.append(_ln)
                elif _ln.startswith("\U0001f4f1"):
                    _gadgets.append(_ln)
                else:
                    _other.append(_ln)
            data["news_digest"] = {
                "summary": _raw_summary[:500],
                "urgent": "\n".join(_urgent),
                "economic": "\n".join(_economic),
                "local": "\n".join(_local),
                "tech": "\n".join(_tech),
                "ai": "\n".join(_ai),
                "gadgets": "\n".join(_gadgets),
                "other": "\n".join(_other),
                "category": latest.get("category", "mixed"),
                "category_ar": cat_info.get("ar", latest.get("category", "")),
                "category_emoji": cat_info.get("emoji", "\U0001f4f0"),
                "item_count": latest.get("item_count", 0),
                "date": latest.get("digest_date", ""),
                "slot": latest.get("digest_slot", ""),
                "created_at": latest.get("created_at", ""),
            }
            data["news_available"] = True
            data["news_digest"]["news_items"] = _parse_news_items(data["news_digest"])
        else:
            data["news_digest"] = {}
            data["news_available"] = False
            data["news_reason"] = "no digest yet"
    except Exception as _e:
        logging.getLogger("master_ai").warning("dashboard/extended news error: %s", _e)
        data["news_digest"] = {}
        data["news_available"] = False
        data["news_reason"] = str(_e)

    return data


# ═══════════════════════════════════════════════════
# Bridge API endpoints (TradingView Bridge enrichment)
# ═══════════════════════════════════════════════════

@router.get("/dashboard/bridge")
async def dashboard_bridge(
    symbols: str = None,
    mode: str = "auto",
    force_refresh: bool = False,
):
    """Compact bridge analysis for dashboard. Auto-selects symbols if none specified."""
    from bridge_client import get_bridge_client
    client = get_bridge_client()

    if not symbols:
        selected = _get_bridge_candidates(mode)
    else:
        selected = [s.strip() for s in symbols.split(",") if s.strip()]

    if not selected:
        return {"status": "ok", "bridge_online": client._online, "symbols_count": 0, "symbols": {}}

    selected = selected[:15]
    result = await client.get_multi_analysis(selected, force=force_refresh)
    return {"status": "ok", **result}


@router.get("/dashboard/bridge/{symbol}")
async def dashboard_bridge_symbol(
    symbol: str,
    exchange: str = "KSE",
    force_refresh: bool = False,
):
    """Detailed single-symbol bridge analysis."""
    from bridge_client import get_bridge_client
    client = get_bridge_client()
    analysis = await client.get_analysis(symbol, exchange, force=force_refresh)
    return {"status": "ok", **analysis}


def _get_bridge_candidates(mode: str = "auto") -> list[str]:
    """Select symbols for bridge enrichment from portfolio + watchlist."""
    candidates = set()

    # 1. Portfolio open positions
    try:
        fn = _ctx.get("get_open_trades")
        if fn:
            trades = fn()
            for t in trades:
                if t.get("symbol"):
                    candidates.add(t["symbol"].upper())
    except Exception:
        pass

    # 2. Radar watchlist
    try:
        from stock_radar import get_watchlist
        wl = get_watchlist()
        for item in wl[:10]:
            sym = item.get("symbol", "")
            if sym:
                candidates.add(sym.upper())
    except Exception:
        pass

    return list(candidates)[:15]


# ═══════════════════════════════════════════════════
# Signal Engine endpoint (composite trading signals)
# ═══════════════════════════════════════════════════

@router.get("/dashboard/signals")
async def dashboard_signals():
    """Composite trading signals: radar + bridge + journal merged."""
    from signal_engine import build_signals
    return build_signals()


@router.get("/dashboard/signals-30m")
async def dashboard_signals_30m():
    """30m signals for all watchlist symbols using Brain weights."""
    from signal_engine import build_signals_30m
    return build_signals_30m()


# ═══════════════════════════════════════════════════
# Trading Brain endpoint (signal learning stats)
# ═══════════════════════════════════════════════════

@router.get("/dashboard/regime")
async def dashboard_regime():
    """Market regime analysis per symbol."""
    from stock_radar import get_daily_snapshot
    snapshot = get_daily_snapshot(top_n=None, min_score=0)
    regimes = {}
    for s in snapshot:
        adx = s.get("adx")
        if adx and adx >= 25:
            regime = "trending"
        elif adx and adx <= 20:
            regime = "ranging"
        else:
            regime = "transition"
        regimes[s["symbol"]] = {
            "regime": regime,
            "regime_ar": "\u0627\u062a\u062c\u0627\u0647\u064a" if regime == "trending" else "\u0639\u0631\u0636\u064a" if regime == "ranging" else "\u0627\u0646\u062a\u0642\u0627\u0644\u064a",
            "adx": round(adx, 1) if adx else None,
            "atr": s.get("atr"),
            "trend": s.get("trend"),
        }
    trending = sum(1 for r in regimes.values() if r["regime"] == "trending")
    ranging = sum(1 for r in regimes.values() if r["regime"] == "ranging")
    return {
        "regimes": regimes,
        "summary": {
            "trending": trending,
            "ranging": ranging,
            "transition": len(regimes) - trending - ranging,
            "total": len(regimes),
        }
    }


@router.get("/dashboard/brain")
async def dashboard_brain():
    """Trading brain stats: indicator weights, hit rates, recent evaluations."""
    try:
        from trading_brain import get_brain_stats, get_optimal_thresholds
        result = get_brain_stats()
        result["thresholds"] = get_optimal_thresholds()
        return result
    except Exception as e:
        return {"brain_active": False, "error": str(e)}


# ═══════════════════════════════════════════════════
# Trade Management API
# ═══════════════════════════════════════════════════

from fastapi import Body

@router.post("/api/trade/open")
async def api_trade_open(data: dict = Body(...)):
    """Open a new trade."""
    try:
        from journal_engine import open_trade
        required = ["symbol", "entry_price", "quantity"]
        for f in required:
            if f not in data:
                return {"success": False, "error": f"Missing field: {f}"}
        trade_id = open_trade(
            symbol=data["symbol"],
            entry_price=float(data["entry_price"]),
            quantity=int(data.get("quantity", 0)),
            entry_reason=data.get("notes", ""),
            strategy=data.get("strategy", "manual"),
            timeframe=data.get("timeframe", "1D"),
            direction=data.get("direction", "long"),
            name_ar=data.get("name_ar", ""),
            stop_loss=float(data["stop_loss"]) if data.get("stop_loss") else None,
            take_profit=float(data["take_profit"]) if data.get("take_profit") else None,
        )
        return {"success": True, "trade_id": trade_id, "message": "Trade opened"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/trade/close")
async def api_trade_close(data: dict = Body(...)):
    """Close an existing trade."""
    try:
        from journal_engine import close_trade
        trade_id = data.get("trade_id")
        exit_price = data.get("exit_price")
        if not trade_id or exit_price is None:
            return {"success": False, "error": "Missing trade_id or exit_price"}
        result = close_trade(int(trade_id), float(exit_price), data.get("reason", "manual"))
        if result is None:
            return {"success": False, "error": "Trade not found or already closed"}
        return {"success": True, "trade": result, "message": "Trade closed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/trade/update")
async def api_trade_update(data: dict = Body(...)):
    """Update stop loss / take profit on a trade."""
    try:
        from journal_engine import update_trade_levels
        trade_id = data.get("trade_id")
        if not trade_id:
            return {"success": False, "error": "Missing trade_id"}
        sl = float(data["stop_loss"]) if data.get("stop_loss") is not None else None
        tp = float(data["take_profit"]) if data.get("take_profit") is not None else None
        result = update_trade_levels(int(trade_id), stop_loss=sl, take_profit=tp)
        if result is None:
            return {"success": False, "error": "Trade not found or not open"}
        return {"success": True, "message": "Trade updated"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/symbols")
async def api_symbols():
    """List all tracked stock symbols."""
    try:
        import sqlite3 as _sql
        db = _sql.connect("data/life.db", timeout=3)
        db.row_factory = _sql.Row
        rows = db.execute(
            "SELECT DISTINCT symbol, name_ar FROM stock_radar_daily ORDER BY symbol"
        ).fetchall()
        db.close()
        return {"symbols": [{"symbol": r["symbol"], "name_ar": r["name_ar"] or ""} for r in rows]}
    except Exception:
        # Fallback: try watchlist
        try:
            from stock_radar import get_watchlist
            wl = get_watchlist()
            return {"symbols": [{"symbol": w["symbol"], "name_ar": ""} for w in wl]}
        except Exception:
            return {"symbols": []}
