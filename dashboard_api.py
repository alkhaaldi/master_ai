"""
dashboard_api.py — HA Dashboard API endpoints (FastAPI Router)
Extracted from server.py v8.3.0
"""
import os
import time
import json
import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from collections import deque
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from priority_engine import (
    build_priority_engine, build_assistant_surface,
    _pe_get_extended_snapshot, _pe_get_radar_snapshot,
)

logger = logging.getLogger("dashboard_api")

router = APIRouter()

# Server context — populated by server.py at startup via init_dashboard_context()
_ctx = {}

# Short-TTL cache for the heavy /dashboard aggregate (shared across all callers)
_DASH_CACHE = {"ts": 0.0, "data": None}
_DASH_TTL = 30  # seconds

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

def _check_bridge_health():
    """The bridge is RETIRED (G-4), so its absence is not degradation.

    This used to report degraded=True / "Bridge offline" / data_source=
    "cache" forever, which is a dead vocabulary describing a dependency
    that no longer exists - and /dashboard/radar has 863 consumers in 26
    hours (the D-5 counter), every one of them being told the system is
    degraded because a retired component is not running.

    Health now means the health of the source that actually serves data.
    """
    try:
        from yahoo_gate import circuit_state
        st = circuit_state()
        if st.get("open"):
            return False, {
                "degraded": True,
                "degraded_reason": "yahoo circuit open: %s" % st.get("reason"),
                "data_source": "unavailable",
            }
    except Exception as e:
        return False, {
            "degraded": True,
            "degraded_reason": "price source state unknown: %r" % e,
            "data_source": "unknown",
        }
    return True, {}


@router.get("/dashboard")
async def ha_dashboard():
    """Returns all data needed for HA Master AI dashboard page."""
    if _DASH_CACHE["data"] is not None and (time.time() - _DASH_CACHE["ts"]) < _DASH_TTL:
        return _DASH_CACHE["data"]
    import psutil, sqlite3
    data = {}
    data["version"] = _ctx["version"]
    data["uptime"] = round(time.time() - _ctx["start_time"])
    data["api_online"] = True
    # assistant.html and home.html both read dash.autonomy_level and both
    # rendered the 'standard' fallback, because /dashboard never carried it -
    # while /health has been reporting autonomy.level all along. One source,
    # surfaced where the pages already look.
    # Straight from system_settings, the same row event_engine reads in
    # server.py. Not an import of server (that would be circular) and not a
    # second copy of the default - if the row is missing, the level is
    # unknown, and unknown is what gets reported.
    try:
        import sqlite3 as _sqa
        import json as _jsa
        _ac = _sqa.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "data", "audit.db"), timeout=3)
        _arow = _ac.execute("SELECT value FROM system_settings"
                            " WHERE key='autonomy_config'").fetchone()
        _ac.close()
        data["autonomy_level"] = _jsa.loads(_arow[0]).get("level") if _arow else None
        if not _arow:
            data["autonomy_level_reason"] = "no autonomy_config row in system_settings"
    except Exception as _ae:
        # None, not a guessed level: an unknown autonomy setting is not
        # "standard", and a page saying standard when nobody knows is the
        # defect this whole phase removed.
        data["autonomy_level"] = None
        data["autonomy_level_reason"] = repr(_ae)[:120]
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
    bridge_up, bridge_degraded = _check_bridge_health()
    if not bridge_up:
        data["degraded_mode"] = "bridge_offline"
        data["degraded_info"] = bridge_degraded
    else:
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
    # active_devices_count - read by home.html and home-control.html, both with
    # `|| 0`, and shipped by nobody: both pages have always said "0 جهاز نشط".
    # Computed from the /api/states fetch above, so it costs no extra call.
    #
    # Covers are counted from the _inverted entities ONLY. Each physical cover
    # has two entities (measured 2026-08-18: 14 real + 14 _inverted twins), so
    # counting the cover domain the way quick_query._active_devices_count does
    # is right only while the twins happen to mirror each other - 14 today by
    # coincidence of state, not by construction. This is the same rule as
    # home_covers_open above: one entity per cover.
    #
    # -1, not 0, when states could not be read. That is the convention of the
    # three siblings above, and both pages already render it as '--'.
    if states:
        _ADC_ON = {"on", "playing", "open", "heat", "cool", "auto", "heat_cool", "fan_only"}
        _ADC_DOMAINS = ("light", "switch", "fan", "climate", "media_player")
        _adc = sum(1 for s in states
                   if s["state"] in _ADC_ON
                   and s["entity_id"].split(".")[0] in _ADC_DOMAINS
                   and "backlight" not in s["entity_id"])
        _adc += sum(1 for s in states
                    if s["entity_id"].startswith("cover.")
                    and "_inverted" in s["entity_id"]
                    and s["state"] == "closed")
        data["active_devices_count"] = _adc
    else:
        data["active_devices_count"] = -1
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
    _DASH_CACHE["ts"] = time.time()
    _DASH_CACHE["data"] = data
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
    _count_endpoint_hit("/dashboard/radar")
    # D-5 answered by evidence, not assumption: 863 hits in 26 hours (HA
    # sensors, 120s interval). It has a heavy consumer, so it joins the
    # contract rather than being declared dead. A live endpoint answering
    # in a dead vocabulary is how April's numbers survived four months.
    _contract = dict(_source_state())
    import sqlite3
    from datetime import date as _d
    data = {}
    bridge_up, bridge_degraded = _check_bridge_health()
    if bridge_degraded:
        data.update(bridge_degraded)
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
                # D-4: session-aged state; 999 is dead - absence is null
                # plus a reason. Old keys ride as aliases for one release.
                **_session_freshness(d.get("captured_at"), d.get("market_was_open")),
                "market_was_open": d.get("market_was_open"),
                "captured_at": d.get("captured_at"),
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
                "bb_squeeze": bool(d.get("bb_squeeze", False)),
                "bb_bandwidth": d.get("bb_bandwidth"),
            })
        data["radar_daily_context"] = daily_clean

        def _untrusted(d):
            """Daily context is only trustworthy if it is fresh AND was taken
            after the close. A mid-session capture stores intraday prices in
            the columns this tab presents as closing values, and a NULL means
            we never recorded which side of the close it came from - unknown
            provenance is not trust.
            """
            if d.get("is_stale", True):
                return True
            return d.get("market_was_open") != 0

        _mid = [d for d in daily if d.get("market_was_open") == 1]
        _unknown = [d for d in daily if d.get("market_was_open") is None]
        data["daily_context_stale"] = all(_untrusted(d) for d in daily) if daily else True
        data["daily_context_mid_session"] = len(_mid)
        data["daily_context_unknown_provenance"] = len(_unknown)
        if not daily_clean:
            data["daily_context_reason"] = "daily context not initialized yet"
        elif len(_mid) == len(daily):
            data["daily_context_reason"] = (
                "captured while the market was open - intraday prices, not closing values"
            )
        elif len(_unknown) == len(daily):
            data["daily_context_reason"] = "capture time not recorded - provenance unknown"
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
                        # One price path for the whole system now:
                        # price_source (bridge -> yahoo -> db) through
                        # get_fresh_price. The provenance vocabulary below is
                        # unchanged - the page still gets what it needs to
                        # refuse a number.
                        from journal_engine import get_fresh_price
                        _q = get_fresh_price(_rsym)
                        if _q.get("price") is not None:
                            _cur = float(_q["price"])
                            _entry = float(_t.get("entry_price", 0))
                            _qty = int(_t.get("quantity", 0))
                            _t["current_price"] = _cur
                            if _entry and _qty:
                                _t["pnl"] = calculate_real_pnl(_entry, _cur, _qty)
                            else:
                                _t["pnl_pct"] = round((_cur / _entry - 1) * 100, 2) if _entry else 0
                                _t["pnl_fils"] = round((_cur - _entry) * _qty) if _qty else 0

                            _as_of = _q.get("as_of")
                            _t["price_as_of"] = _as_of
                            _t["price_source"] = _q.get("source")
                            _mid = bool(_q.get("captured_mid_session"))
                            _t["price_captured_mid_session"] = _mid
                            _age = _q.get("age_days")
                            if _age is None and _as_of:
                                try:
                                    _aged = datetime.fromisoformat(str(_as_of))
                                    if _aged.tzinfo:
                                        _aged = _aged.replace(tzinfo=None)
                                    _age = (datetime.utcnow() - _aged).days
                                except (ValueError, TypeError) as _ae:
                                    logging.getLogger("master_ai").warning(
                                        "radar: unparseable price_as_of %r for %s (%s)",
                                        _as_of, _rsym, _ae)
                            _t["price_age_days"] = _age
                            if _q.get("state") == "live" and not _mid:
                                _t["price_state"] = "live"
                                _t["pnl_valid"] = True
                                _t["pnl_invalid_reason"] = None
                            elif _q.get("state") == "live":
                                # captured while the session was running, so it
                                # is not a valid close even on its own day
                                _t["price_state"] = "intraday"
                                _t["pnl_valid"] = False
                                _t["pnl_invalid_reason"] = "price captured mid-session"
                            elif _as_of is None:
                                _t["price_state"] = "unknown"
                                _t["pnl_valid"] = False
                                _t["pnl_invalid_reason"] = "price has no as_of"
                            else:
                                _t["price_state"] = "stale"
                                _t["pnl_valid"] = False
                                _t["pnl_invalid_reason"] = (
                                    f"price_as_of is {_age} days old"
                                    if _age is not None else "price is stale")
                        else:
                            _t["price_state"] = "unknown"
                            _t["pnl_valid"] = False
                            _t["pnl_invalid_reason"] = (
                                _q.get("reason") or "no source had a price")
                    except Exception as _pe:
                        # the fifth silent swallow of the day
                        logging.getLogger("master_ai").warning(
                            "radar: price lookup failed for %s: %r",
                            _t.get("symbol"), _pe)
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
    # The contract, merged last so it cannot be shadowed by an earlier
    # key: source / source_state / source_reason, and the session-aged
    # data_state computed from the newest radar row. Same vocabulary as
    # /dashboard/swing, so one payload cannot say fresh while the other
    # says blind for the same data (D-4 reconciliation, now for the
    # endpoint that actually has consumers).
    try:
        import sqlite3 as _sq6
        from price_source import classify_data_state as _cds
        _c6 = _sq6.connect("data/life.db", timeout=3)
        _mx6 = _c6.execute("SELECT MAX(captured_at) FROM stock_radar_daily").fetchone()[0]
        _c6.close()
        _ds6 = _cds(_mx6)
        _contract.update(data_state=_ds6["data_state"],
                         data_state_ar=_ds6["data_state_ar"],
                         data_sessions_old=_ds6["sessions_old"])
    except Exception as _e6:
        _contract.update(data_state="unknown", data_state_ar=None,
                         data_sessions_old=None,
                         data_state_reason=repr(_e6)[:120])
    data.update(_contract)
    return data


# ═══════════════════════════════════════════════════
# /dashboard/portfolio — Portfolio + Journal data
# ═══════════════════════════════════════════════════

def _apply_price_contract(t: dict, fp: dict):
    """Canonical price fields on a position dict (PHASE2_SECTION_D, D-1) -
    the same vocabulary journal_open in /dashboard/radar uses. Returns the
    current price or None. quote_* stay as deprecated aliases; readers
    should migrate to price_* (see _tools/PHASE2_SECTION_D.md)."""
    cur = None
    if fp.get("price"):
        cur = float(fp["price"])
        t["current_price"] = cur
    as_of = fp.get("as_of")
    mid = bool(fp.get("captured_mid_session"))
    age = fp.get("age_days")
    if age is None and as_of:
        try:
            _d = datetime.fromisoformat(str(as_of))
            if _d.tzinfo:
                _d = _d.replace(tzinfo=None)
            age = (datetime.utcnow() - _d).days
        except (ValueError, TypeError):
            age = None
    t["price_as_of"] = as_of
    t["price_source"] = fp.get("source")
    t["price_age_days"] = age
    t["price_captured_mid_session"] = mid
    if cur and fp.get("state") == "live" and not mid and as_of:
        t["price_state"], t["pnl_valid"], t["pnl_invalid_reason"] = "live", True, None
    elif cur and fp.get("state") == "live":
        t["price_state"], t["pnl_valid"] = "intraday", False
        t["pnl_invalid_reason"] = "price captured mid-session"
    elif cur is None or as_of is None:
        t["price_state"], t["pnl_valid"] = "unknown", False
        t["pnl_invalid_reason"] = fp.get("reason") or "no dated price"
    else:
        t["price_state"], t["pnl_valid"] = "stale", False
        t["pnl_invalid_reason"] = (f"price_as_of is {age} days old"
                                   if age is not None else "price is stale")
    t["quote_as_of"] = t["price_as_of"]
    t["quote_state"] = t["price_state"]
    t["quote_source"] = t["price_source"]
    t["quote_stale"] = t["price_state"] != "live"
    return cur


def _source_state() -> dict:
    """G-3.4: the price source's own health, separate from data age.

    A shut door and stale data are different failures: data can be old
    because the market is closed (normal), or because we cannot ask
    (blind). Collapsing them is what let April prices render as current
    for four months.
    """
    # The feed's delay is a property of the source, so it travels with the
    # source on every path - including the blind ones, where knowing the feed
    # is 15 minutes behind is exactly what stops a reader treating the last
    # stored number as current.
    try:
        from price_source import SOURCE_DELAY_MINUTES as _sdm
    except Exception:
        _sdm = None                  # unknown delay, not zero delay
    _src = {"source": "yahoo", "source_delay_minutes": _sdm}
    try:
        from yahoo_gate import circuit_state
        st = circuit_state()
    except Exception as e:
        return {"source_state": "unknown", "source_reason": repr(e)[:120],
                **_src}
    if st.get("open"):
        return {"source_state": "blind",
                "source_reason": "circuit open: %s (%ss remaining)"
                                 % (st.get("reason"), st.get("cooldown_remaining_s")),
                **_src}
    if st.get("consecutive_failures", 0) >= 2:
        return {"source_state": "degraded",
                "source_reason": "%d consecutive failures, last %s"
                                 % (st["consecutive_failures"], st.get("last_failure")),
                **_src}
    return {"source_state": "ok", "source_reason": None, **_src}


def _data_contract() -> dict:
    """The evidence contract, in ONE place.

    Extracted 2026-08-17. It was inline in /dashboard/swing, and
    /dashboard/radar had its own copy, while /dashboard/signals and
    /dashboard/signals-daily had none at all - three sibling endpoints
    answering the same question in three vocabularies, which is how a
    vocabulary drifts in the first place. A fourth copy would have been
    the joke writing itself.

    Everything here describes stock_radar_daily, which is what all of these
    endpoints actually read. as_of is MAX(captured_at): the SOURCE's own
    last-trade time, not our fetch time (see SCALES.md, and the caveat in
    OPEN_ITEMS 4b about the two writers).
    """
    out = {"data_state": "blind", "data_state_ar": "أعمى · لا بيانات",
           "data_sessions_old": None, "as_of": None, "as_of_kind": None,
           "as_of_age_minutes": None}
    out.update(_source_state())
    try:
        import sqlite3 as _sqc
        from price_source import classify_data_state, as_of_age_minutes
        # An absolute path off this file, not BASE_DIR (undefined here) and
        # not a relative "data/life.db" (which only works while the process
        # cwd happens to be right). The first version used BASE_DIR, raised
        # NameError, and the except below turned it into a confident
        # `blind` - the failure mode this whole contract exists to prevent,
        # reproduced inside the contract itself.
        _dbp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "data", "life.db")
        _c = _sqc.connect(_dbp, timeout=3)
        _mx = _c.execute(
            "SELECT MAX(captured_at) FROM stock_radar_daily").fetchone()[0]
        _c.close()
        _st = classify_data_state(_mx)
        out["data_state"] = _st.get("data_state")
        out["data_state_ar"] = _st.get("data_state_ar")
        out["data_sessions_old"] = _st.get("sessions_old")
        out["as_of"] = _mx
        out["as_of_kind"] = "source_market_time" if _mx else None
        out["as_of_age_minutes"] = as_of_age_minutes(_mx)
    except Exception as _dce:
        # `blind` with no reason is indistinguishable from a genuinely empty
        # table. Say which it was.
        logging.getLogger("master_ai").warning("data contract error: %r", _dce)
        out["data_state_ar"] = "أعمى · تعذّر قراءة حالة البيانات"
        out["data_state_reason"] = repr(_dce)[:160]
    return out


def _session_freshness(as_of, was_open) -> dict:
    """Session-aged freshness block (PHASE2_SECTION_D, D-4). The 999
    sentinel is dead: an age that cannot be computed is null plus a
    reason, never a number someone will average."""
    from price_source import classify_data_state
    ds = classify_data_state(as_of, bool(was_open))
    out = {"data_state": ds["data_state"], "data_state_ar": ds["data_state_ar"],
           "sessions_old": ds["sessions_old"],
           "data_age_hours": None, "age_reason": None}
    if as_of:
        try:
            _d = datetime.fromisoformat(str(as_of))
            if _d.tzinfo:
                _d = _d.replace(tzinfo=None)
            out["data_age_hours"] = round(
                (datetime.utcnow() - _d).total_seconds() / 3600, 1)
        except (ValueError, TypeError):
            out["age_reason"] = "unparseable capture time"
    else:
        out["age_reason"] = "capture time not recorded"
    # old vocabulary, kept as aliases for one release
    out["is_stale"] = ds["data_state"] not in ("normal", "live")
    out["freshness"] = ("fresh" if ds["data_state"] in ("normal", "live")
                        else "aging" if ds["data_state"] == "degraded" else "stale")
    return out


def _count_endpoint_hit(name: str) -> None:
    """PHASE2_SECTION_D, D-5: /dashboard/radar may have no consumer - count
    for a week, then decide. A file, not a log line, because INFO from this
    module never reaches server.log (C-20)."""
    try:
        import json as _j, time as _t
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "data", "endpoint_hits.json")
        d = {}
        if os.path.exists(p):
            with open(p) as f:
                d = _j.load(f)
        e = d.setdefault(name, {"count": 0, "first": None})
        e["count"] += 1
        e["first"] = e["first"] or _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime())
        e["last"] = _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime())
        with open(p, "w") as f:
            _j.dump(d, f, indent=1)
    except Exception:
        pass


@router.get("/dashboard/portfolio")
async def ha_dashboard_portfolio():
    """Portfolio data for HA dashboard — open positions, closed trades, stats."""
    data = {}
    bridge_up, bridge_degraded = _check_bridge_health()
    if bridge_degraded:
        data.update(bridge_degraded)

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
                sym = t.get("symbol", "").upper()
                fp = {}
                try:
                    fp = get_fresh_price(sym)
                except Exception:
                    pass
                # D-1: canonical contract + deprecated quote_* aliases
                _cur = _apply_price_contract(t, fp)

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

                # ── S/R from Bridge analysis (if not already set from radar_daily) ──
                # G-4: S/R came from the bridge here. Retired - the values
                # now come from stock_radar_daily, computed by indicators.py
                # (20-bar rolling, newest bar excluded). Block disabled
                # rather than deleted so the old shape stays readable.
                if False and _cur and not t.get("support"):
                    try:
                        import urllib.request as _urlreq, json as _json
                        _aurl = f"{os.getenv('BRIDGE_URL', 'http://192.168.111.214:8059')}/analysis?symbol={sym}&interval=1D"
                        with _urlreq.urlopen(_aurl, timeout=5) as _aresp:
                            _adata = _json.loads(_aresp.read().decode())
                        _abars = _adata.get("bars", [])
                        if _abars and len(_abars) >= 20:
                            from sr_engine import compute_sr
                            _sr = compute_sr(sym, _abars, _cur)
                            if _sr.get("key_support"):
                                t["support"] = _sr["key_support"]
                            if _sr.get("key_resistance"):
                                t["resistance"] = _sr["key_resistance"]
                    except Exception:
                        pass

                # ── Suggested stop loss (if user hasn't set one) ──
                if not t.get("stop_loss") and _entry:
                    _sup = t.get("support")
                    if _sup and _sup < _entry:
                        t["suggested_stop"] = _sup
                    else:
                        t["suggested_stop"] = round(_entry * 0.95, 1)

            if _rdb:
                try:
                    _rdb.close()
                except Exception:
                    pass
            # Enrich with signal_health + alerts from signal_engine
            try:
                from signal_engine import build_signals
                import asyncio as _asyncio
                sig_result = await _asyncio.get_event_loop().run_in_executor(None, build_signals)
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
                            # Added 2026-08-17. positions.html has been
                            # rendering "الدعم —" and "المقاومة —" and hiding
                            # its ATR and TREND chips because these four never
                            # reached the page - not because they were
                            # missing. The signal row carries all of them, two
                            # of them under different names, and THIS is the
                            # right place for that translation: signal_health
                            # is already the block that carries per-symbol
                            # technicals onto a position, so widening the
                            # position row instead would have put market
                            # readings among trade facts.
                            "support": sig.get("support"),
                            "resistance": sig.get("resistance"),
                            "atr": sig.get("atr_14"),
                            "trend": sig.get("daily_trend"),
                            # volume_signal is NOT here on purpose. The page
                            # reads it as a text label; the signal row carries
                            # vol_ratio, a number. tv_analysis has a
                            # detect_volume_signal that produces the label,
                            # but wiring it is a decision about which module
                            # owns volume classification, not a rename.
                            # Tracked in OPEN_ITEMS.
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
            # trades.created_at moved to UTC on 2026-08-15 (D-11), so the
            # threshold is plain UTC now again
            "SELECT COUNT(*) FROM trades WHERE created_at > datetime('now', '-7 days')"
            " AND COALESCE(trade_kind, 'real') != 'void'"
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
            sym = t.get("symbol", "").upper()
            fp = {}
            try:
                fp = get_fresh_price(sym)
            except Exception:
                pass
            # D-1: canonical contract + deprecated quote_* aliases
            _cur = _apply_price_contract(t, fp)
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
                  AND COALESCE(trade_kind, 'real') != 'void'
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
            # created_at is UTC (D-11); _today is a Kuwait calendar day
            "SELECT COUNT(*) FROM trades WHERE date(datetime(created_at, '+3 hours'))=? "
            "AND COALESCE(trade_kind, 'real') != 'void'", (_today,)
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
    from bridge_client import circuit_stats
    return {"status": "ok", **result, "circuit": circuit_stats()}


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

def _retire_bridge_flag(payload: dict) -> dict:
    """`bridge_online: false` names a RETIRED dependency as though it might
    come back, which invites someone to go and fix a host that no longer
    exists. Replaced by a field that says what actually happened, once.

    Kept as a key rather than deleted so an old page reading it does not
    throw - but it now reads `retired`, which is not a boolean anyone will
    mistake for a health signal.
    """
    payload.pop("bridge_online", None)
    payload.pop("bridge_cached_count", None)
    payload["bridge"] = "retired 2026-08-16 (G-4) — not offline, gone. "\
                        "Prices come from the local store; see source below."
    return payload


@router.get("/dashboard/signals")
def dashboard_signals():
    """Composite trading signals: radar + journal merged.

    Joined the data contract 2026-08-17. It served 131 real signals with no
    data_state, no source_state and no as_of - correct numbers with no way
    to judge their age. That class does not fail a value check, because
    every value in it is fine.
    """
    from signal_engine import build_signals
    out = build_signals()
    out.update(_data_contract())
    return _retire_bridge_flag(out)


@router.get("/dashboard/signals-daily")
def dashboard_signals_daily():
    """Daily-only signals — uses closing prices, NOT live 30m data.
    Separated from 30m to prevent timeframe mixing (Trading V2 Phase 1)."""
    import sqlite3 as _sq, os as _os
    from signal_engine import build_signals
    data = build_signals()

    # Load daily closing prices from DB to replace live bridge prices
    _closing = {}
    try:
        _db = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "data", "life.db")
        _c = _sq.connect(_db, timeout=5)
        _c.row_factory = _sq.Row
        for r in _c.execute(
            "SELECT symbol, close FROM daily_bars WHERE trading_date = "
            "(SELECT MAX(trading_date) FROM daily_bars)"
        ).fetchall():
            _closing[r["symbol"]] = float(r["close"])
        _c.close()
    except Exception:
        pass

    for sig in data.get("all_signals", []):
        sig["timeframe"] = "1D"
        # Use closing price from DB if available (NOT live 30m bridge price)
        sym = sig.get("symbol", "")
        if sym in _closing:
            sig["price"] = _closing[sym]
            sig["price_source"] = "daily_close"
        else:
            sig["price_source"] = "bridge_live"
        # Strip 30m-only scalping fields
        for k in ("scalp_confluence_pct", "scalp_action", "scalp_factors",
                   "scalp_reason", "scalping_vwap_ok"):
            sig.pop(k, None)

    data["timeframe"] = "1D"
    data["price_note"] = "Prices are daily closing prices from DB, not live 30m."

    # ═══ Gemini Analysis Overlay ═══
    try:
        from stock_analyzer import get_all_cached_analyses
        _analyses = {a["symbol"]: a for a in get_all_cached_analyses()}

        for sig in data.get("all_signals", []):
            sym = sig.get("symbol", "")
            ga = _analyses.get(sym)
            if ga and ga.get("structured_json"):
                sj = ga["structured_json"]
                a_date = ga.get("analysis_date", "")
                _stale = False
                try:
                    from datetime import datetime as _dt, timedelta as _td
                    _stale = (_dt.now() - _dt.strptime(a_date, "%Y-%m-%d")) > _td(days=3)
                except Exception:
                    pass
                sig["gemini"] = {
                    "signal": ga.get("signal", ""),
                    "confidence": ga.get("confidence", 0),
                    "direction": sj.get("direction", ""),
                    "targets": sj.get("targets", []),
                    "stop_loss": sj.get("stop_loss", ""),
                    "entry": sj.get("entry", ""),
                    "support": sj.get("support", []),
                    "resistance": sj.get("resistance", []),
                    "analysis_date": a_date,
                    "stale": _stale,
                }
                # Conflict detection
                radar_verdict = sig.get("verdict_key", "")
                gemini_signal = (ga.get("signal") or "").lower()
                _conflict = False
                if radar_verdict == "buy" and any(w in gemini_signal for w in ["\u0628\u064a\u0639", "\u0627\u0646\u062a\u0638\u0627\u0631"]):
                    _conflict = True
                elif radar_verdict == "avoid" and "\u0634\u0631\u0627\u0621" in gemini_signal:
                    _conflict = True
                sig["gemini_conflict"] = _conflict
            else:
                sig["gemini"] = None
                sig["gemini_conflict"] = False

        # Gemini-boosted decision card
        dc = data.get("decision_card")
        if dc and dc.get("gemini") and not dc["gemini"].get("stale"):
            gc = dc["gemini"].get("confidence", 0)
            if gc >= 70:
                old_score = dc.get("confluence_score", 0)
                boost = min(15, int((gc - 50) * 0.3))
                dc["confluence_score_raw"] = old_score
                dc["gemini_boost"] = boost
    except Exception as _ge:
        import logging
        logging.getLogger("dashboard_api").warning("Gemini overlay failed: %s", _ge)

    # ═══ Risk Summary ═══
    try:
        from risk_engine import _get_risk_config
        _rc = _get_risk_config()
        _open_count = len([s for s in data.get("all_signals", []) if s.get("trade_state") in ("entered", "manage")])
        _max_pos = int(_rc.get("max_open_positions", 5))
        data["risk_summary"] = {
            "capital": _rc.get("account_capital", 0),
            "risk_per_trade_pct": _rc.get("risk_per_trade_pct", 2),
            "max_positions": _max_pos,
            "open_positions_count": _open_count,
            "slots_available": max(0, _max_pos - _open_count),
            "portfolio_heat_pct": round(_open_count / max(_max_pos, 1) * 100, 1),
        }
    except Exception:
        data["risk_summary"] = None

    # ═══ Transaction counts for open positions ═══
    try:
        _tdb = _sq.connect(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "data", "life.db"), timeout=3)
        for pos in data.get("open_positions", []):
            _tid = pos.get("id") or pos.get("trade_id")
            if _tid:
                _txr = _tdb.execute(
                    "SELECT COUNT(*) as cnt, "
                    "COALESCE(SUM(CASE WHEN tx_type='partial_sell' THEN quantity ELSE 0 END), 0) as sold "
                    "FROM trade_transactions WHERE trade_id=?", (_tid,)).fetchone()
                pos["tx_count"] = _txr[0] if _txr else 0
                pos["qty_sold"] = _txr[1] if _txr else 0
            else:
                pos["tx_count"] = 0
                pos["qty_sold"] = 0
        _tdb.close()
    except Exception:
        pass

    # Same contract as /dashboard/signals and /dashboard/swing, from the same
    # builder (2026-08-17). This endpoint replaces the live prices with daily
    # closes, so the age question matters here MORE than on its siblings, not
    # less - and it was the one carrying no answer to it at all.
    data.update(_data_contract())
    return _retire_bridge_flag(data)


@router.get("/dashboard/signals-30m")
def dashboard_signals_30m():
    """30m signals for all watchlist symbols using Brain weights."""
    from signal_engine import build_signals_30m
    return build_signals_30m()


@router.get("/dashboard/swing")
def dashboard_swing():
    """
    Swing Trading dashboard — daily signals with ATR stops, pivots,
    simplified confluence (Volume+ADX only), whitelist filtered.
    Trading V2 Phase 4+5+6.
    """
    from datetime import datetime as _dt
    from signal_engine import (
        build_signals, SWING_MODE, WHITELIST_MODE, WHITELIST, BLACKLIST,
        DAILY_TREND_FILTER, MARKET_REGIME_FILTER, LIQUIDITY_FILTER,
        check_scalping_exit, get_trading_flags, check_market_regime,
    )

    raw = build_signals()
    all_sigs = raw.get("all_signals", [])
    bridge_online = raw.get("bridge_online", False)

    # Top signal = best swing opportunity
    top_signal = None
    opportunities = []
    for s in all_sigs:
        action = s.get("swing_action", "")
        if action in ("STRONG_BUY", "BUY"):
            entry = {
                "symbol": s["symbol"],
                "name_ar": s.get("name_ar", ""),
                "price": s.get("price", 0),
                "change_pct": s.get("change_pct", 0),
                "daily_trend": s.get("daily_trend", "UNKNOWN"),
                "daily_sma20": s.get("daily_sma20", 0),
                "confluence_pct": s.get("swing_confluence_pct", 0),
                "action": action,
                "factors": s.get("swing_factors", []),
                "blockers": s.get("swing_blockers", []),
                "reason": s.get("swing_reason", ""),
                "stop_loss": s.get("swing_stop"),
                "stop_pct": s.get("swing_stop_pct"),
                "stop_type": s.get("swing_stop_type"),
                "target": s.get("swing_target"),
                "target_pct": s.get("swing_target_pct"),
                "target_type": s.get("swing_target_type"),
                "risk_reward": s.get("swing_rr", 0),
                "rsi_14": s.get("rsi_14"),
                "adx": s.get("adx"),
                "vol_ratio": s.get("vol_ratio"),
                "atr_14": s.get("atr_14"),
                "pivots": s.get("pivots", {}),
                "support": s.get("support"),
                "resistance": s.get("resistance"),
                "market_regime": s.get("market_regime", "UNKNOWN"),
                "regime_allow_buy": s.get("regime_allow_buy", True),
                "liquidity": s.get("liquidity", {}),
                "sector": s.get("sector", "unknown"),
                "sector_ar": s.get("sector_ar", ""),
                "checklist": s.get("checklist"),
            }
            opportunities.append(entry)
            if not top_signal or entry["confluence_pct"] > top_signal["confluence_pct"]:
                top_signal = entry

    # Watch list (not yet buy but close)
    watchlist = []
    for s in all_sigs:
        action = s.get("swing_action", "")
        if action == "WATCH":
            from signal_engine import _name_ar as _nm_w
            watchlist.append({
                "symbol": s["symbol"],
                # Same resolver again. The watchlist sat beside a positions
                # list and an opportunities list on one page, and was the
                # only one of the three with no name.
                "name_ar": _nm_w(s["symbol"]),
                "price": s.get("price", 0),
                "daily_trend": s.get("daily_trend", "UNKNOWN"),
                "confluence_pct": s.get("swing_confluence_pct", 0),
                "action": action,
                "factors": s.get("swing_factors", []),
                "blockers": s.get("swing_blockers", []),
            })

    # Active positions with exit check
    active_positions = []
    for pos in raw.get("open_positions", []):
        sym = (pos.get("symbol") or "").upper()
        # signal_engine emits "entry" and "current"; this read used to ask for
        # entry_price/avg_price and current_price/price, got 0 for both, and the
        # `if entry_p and cur_p` below dropped the row. One open position was
        # invisible here for 142 days without a single log line. The old names
        # stay as fallbacks in case another producer ever feeds this.
        entry_p = pos.get("entry") or pos.get("entry_price") or pos.get("avg_price") or 0
        cur_p = pos.get("current") or pos.get("current_price") or pos.get("price") or 0

        if not entry_p:
            logger.warning(
                "swing: dropping position %s - no entry price in source. keys=%s",
                sym or "<no symbol>", sorted(pos.keys()),
            )
            continue

        # signal_engine sets state="manage" only when the symbol was present in
        # the bridge response; "entered" means current was filled from entry as a
        # fallback, so it is not a market price. Reporting a P&L off it would be
        # the same fault as a Bearish regime computed from a zero sample: an
        # absence dressed up as a confident number.
        price_is_live = pos.get("state") == "manage" and cur_p != 0
        pnl_pct = round((cur_p - entry_p) / entry_p * 100, 2) if price_is_live else None

        days_held = pos.get("days_held")
        if days_held is None and pos.get("entry_date"):
            try:
                days_held = (_dt.now() - _dt.fromisoformat(str(pos["entry_date"])[:10])).days
            except (ValueError, TypeError) as _de:
                logger.warning("swing: unparseable entry_date for %s (%r)", sym, _de)
                days_held = None

        cur_sig = next((s for s in all_sigs if s["symbol"] == sym), None)
        # The name was absent from this list entirely - signal_engine's fix
        # could not reach it, because swing builds its positions here rather
        # than from build_signals. Same resolver, so the two lists on this
        # page cannot drift apart again.
        from signal_engine import _name_ar as _nm
        active_positions.append({
            "symbol": sym,
            "name_ar": _nm(sym, pos),
            "entry_price": entry_p,
            # null, not a stale number, when there is no live price
            "current_price": cur_p if price_is_live else None,
            "pnl_pct": pnl_pct,
            # pnl_valid was ABSENT here, while the other position builder
            # (_position_price_block) has always set it. swing.html reads
            # `p.pnl_valid !== false`, so a missing flag passed as VALID -
            # the page showed -1.79% as a trusted number with nothing
            # asserting it was trustworthy. Two builders for one row, and
            # only one carrying the verdict.
            #
            # Explicit true/false now, never absent, and a reason when false:
            # the reader should not have to infer validity from the presence
            # of a key.
            "pnl_valid": bool(price_is_live and pnl_pct is not None),
            "pnl_invalid_reason": (
                None if (price_is_live and pnl_pct is not None)
                else ("no live price for this position — current was filled "
                      "from entry, so a P&L off it would be an absence "
                      "dressed as a number")),
            "price_state": "live" if price_is_live else "stale",
            # the position's own stamp, straight from the price source -
            # it was computed upstream and then dropped here, so the row
            # said "live" and could not say when
            "price_as_of": pos.get("price_as_of"),
            "last_known_price": cur_p or None,
            "quantity": pos.get("quantity"),
            "entry_date": pos.get("entry_date"),
            "days_held": days_held,
            # absent in the source: explicitly null rather than 0, which would
            # read as "stop at zero"
            "stop_loss": pos.get("stop_loss"),
            "target": pos.get("target_price"),
            "daily_trend": (cur_sig or {}).get("daily_trend", "UNKNOWN"),
        })

    # Market trend summary: how many whitelist stocks are UP?
    trend_up = sum(1 for s in all_sigs if s.get("daily_trend") == "UP")
    trend_down = sum(1 for s in all_sigs if s.get("daily_trend") == "DOWN")
    trend_side = sum(1 for s in all_sigs if s.get("daily_trend") == "SIDEWAYS")

    # Market regime from signal engine
    regime = raw.get("market_regime", check_market_regime())

    # Page-level data state, session-aged (swing.html falls back to
    # bridge_online only while this field is absent). The page's snapshot
    # age is the age of the newest radar row.
    # The contract now comes from _data_contract(), one place, shared with
    # /dashboard/signals and /dashboard/signals-daily. The block below is
    # kept only for the two keys the swing payload has always spelled its
    # own way (`data_sessions_old` arrives from the contract; `market_open`
    # is swing-local).
    _page_state = {"data_state": "blind", "data_state_ar": "أعمى · لا بيانات",
                   "sessions_old": None, "market_open": False}
    try:
        import sqlite3 as _sq5
        from price_source import classify_data_state
        _c5 = _sq5.connect("data/life.db", timeout=3)
        _mx = _c5.execute(
            "SELECT MAX(captured_at) FROM stock_radar_daily").fetchone()[0]
        _c5.close()
        _page_state = classify_data_state(_mx)
        # as_of is the stamp of the newest real fetch, not the time this
        # response was assembled. During an open session "live" without a
        # time says nothing: it cannot distinguish a two-minute-old price
        # from an hour-old one, which is the only question that matters
        # while the market moves.
        _page_state["as_of"] = _mx
        # ...and a time nobody can name is barely better. Measured on the wire
        # 2026-08-17: this stamp is neither our fetch time (that is scan_time)
        # nor the bar's time (that is bar_start, pinned at 06:00Z all session).
        # It is the SOURCE's own last-trade time - Yahoo's regularMarketTime,
        # carried into captured_at by _tools/intraday_refresh.py. Naming it
        # costs one field and settles a question a reader cannot answer from
        # the payload today.
        # CAVEAT, tracked in _tools/OPEN_ITEMS.md: stock_radar.py stamps the
        # same column from utcnow(). 131 of 132 rows are source-clock, so this
        # label holds today by weight of rows, not by construction.
        from price_source import as_of_age_minutes as _aom
        _page_state["as_of_kind"] = "source_market_time" if _mx else None
        _page_state["as_of_age_minutes"] = _aom(_mx)
    except Exception as _dse:
        logging.getLogger("master_ai").warning("swing data_state error: %r", _dse)

    return {
        "flags": get_trading_flags(),
        "scan_time": _dt.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "market_status": "open" if raw.get("market_open") else "closed",
        # `bridge_online` removed here too, 2026-08-17. It came off
        # /dashboard/signals and /dashboard/signals-daily first and was left
        # on its own neighbour, which is the same inconsistency the contract
        # work existed to remove - three siblings, and only two of them
        # corrected. `bridge` below says retired; source/source_state say
        # what is actually feeding the numbers.
        **_source_state(),
        "data_state": _page_state.get("data_state"),
        "data_state_ar": _page_state.get("data_state_ar"),
        "data_sessions_old": _page_state.get("sessions_old"),
        "as_of": _page_state.get("as_of"),
        "as_of_kind": _page_state.get("as_of_kind"),
        "as_of_age_minutes": _page_state.get("as_of_age_minutes"),
        "market_regime": regime,
        "market_trend": {
            "up": trend_up,
            "down": trend_down,
            "sideways": trend_side,
            "total": len(all_sigs),
            "status": "bullish" if trend_up > trend_down else ("bearish" if trend_down > trend_up else "mixed"),
        },
        "top_signal": top_signal,
        "opportunities": sorted(opportunities, key=lambda x: x["confluence_pct"], reverse=True),
        "watchlist": sorted(watchlist, key=lambda x: x["confluence_pct"], reverse=True),
        "active_positions": active_positions,
        "stats": {
            "total_scanned": len(all_sigs),
            "opportunities": len(opportunities),
            "watching": len(watchlist),
            "active": len(active_positions),
            "filtered_out": raw.get("filtered_out", 0),
        },
    }






@router.get("/dashboard/paper-trading")
def dashboard_paper_trading():
    """Paper trading dashboard — simulated trades with slippage."""
    try:
        from paper_trading import get_paper_trading_stats
        return get_paper_trading_stats()
    except Exception as e:
        return {"error": str(e), "mode": "paper", "open_trades": 0}


@router.post("/api/paper-trade/open")
async def api_paper_trade_open(request: Request):
    """Open a paper trade from signal data."""
    _require_api_key(request)
    try:
        body = await request.json()
        from paper_trading import open_paper_trade
        return open_paper_trade(body)
    except Exception as e:
        return {"error": str(e)}


@router.post("/api/paper-trade/close")
async def api_paper_trade_close(request: Request):
    """Close a paper trade."""
    _require_api_key(request)
    try:
        body = await request.json()
        from paper_trading import close_paper_trade
        return close_paper_trade(body["trade_id"], body["exit_price"], body.get("reason", "manual"))
    except Exception as e:
        return {"error": str(e)}




@router.get("/dashboard/equity")
def dashboard_equity():
    """Equity curve + drawdown + trade journal stats."""
    try:
        from equity_tracker import get_equity_dashboard
        return get_equity_dashboard()
    except Exception as e:
        return {"error": str(e), "current_equity": 0}


@router.get("/dashboard/risk-status")
def dashboard_risk_status():
    """Portfolio risk status — capital, heat, sectors, position sizing."""
    try:
        from risk_engine import get_risk_status
        return get_risk_status()
    except Exception as e:
        return {"error": str(e), "capital": 0, "open_positions": 0}


@router.get("/dashboard/scalper")
def dashboard_scalper():
    """
    Scalper dashboard — hot stocks filtered by VWAP+Volume+ADX+Stoch.
    Phase 5 of Scalping Optimization Plan.
    """
    from datetime import datetime as _dt
    from signal_engine import (
        build_signals_30m, SCALPING_MODE,
        calculate_scalping_stop, check_scalping_exit,
    )

    raw = build_signals_30m()
    all_sigs = raw.get("signals", [])
    bridge_online = raw.get("bridge_online", False)

    # --- Filter: scalping candidates ---
    hot = []
    for s in all_sigs:
        # Must have scalping data
        if not s.get("scalp_action"):
            continue
        # Only BUY or STRONG_BUY
        if s["scalp_action"] not in ("BUY", "STRONG_BUY"):
            continue
        # Must be above VWAP
        if s.get("price_vs_vwap") != "above":
            continue
        # Minimum volume ratio
        if (s.get("vol_ratio") or 0) < 3.0:
            continue
        # Minimum ADX
        if (s.get("adx") or 0) < 25:
            continue

        # Calculate stop/target
        price = s.get("price", 0)
        ema21 = s.get("ema21", 0)
        # Use support as candle_low proxy when no bar data available
        candle_low = s.get("support") or (price * 0.997)
        stop_data = calculate_scalping_stop(price, candle_low, ema21)

        hot.append({
            "symbol": s["symbol"],
            "name_ar": s.get("name_ar", ""),
            "price": price,
            "change_pct": s.get("change_pct", 0),
            "volume_ratio": s.get("vol_ratio"),
            "adx": s.get("adx"),
            "stoch_k": s.get("stoch_k"),
            "stoch_d": s.get("stoch_d"),
            "vwap": s.get("vwap"),
            "vwap_distance_pct": s.get("vwap_distance_pct"),
            "price_vs_vwap": s.get("price_vs_vwap"),
            "confluence_pct": s.get("scalp_confluence_pct", 0),
            "action": s.get("scalp_action"),
            "factors": s.get("scalp_factors", []),
            "stop_loss": stop_data.get("stop_loss"),
            "target": stop_data.get("target"),
            "risk_pct": stop_data.get("risk_pct"),
            "reward_pct": stop_data.get("reward_pct"),
            "risk_reward": stop_data.get("risk_reward"),
            "stop_type": stop_data.get("stop_type"),
            "ema9": s.get("ema9"),
            "ema21": ema21,
        })

    # Sort by confluence descending, take top 10
    hot.sort(key=lambda x: x.get("confluence_pct", 0), reverse=True)
    hot = hot[:10]

    # --- Active scalps: open positions with exit check ---
    active_scalps = []
    try:
        from journal_engine import get_open_trades
        for t in get_open_trades():
            sym = (t.get("symbol") or "").upper()
            entry_p = t.get("entry_price") or t.get("avg_price") or 0
            # Find current price from signals
            cur_sig = next((s for s in all_sigs if s["symbol"] == sym), None)
            if not cur_sig or not entry_p:
                continue
            cur_price = cur_sig.get("price", 0)
            if not cur_price:
                continue
            pnl_pct = ((cur_price - entry_p) / entry_p * 100) if entry_p > 0 else 0
            ema9 = cur_sig.get("ema9", 0)
            bars_held = t.get("bars_held", 0)
            exit_ck = check_scalping_exit(bars_held, pnl_pct, cur_price, ema9)
            active_scalps.append({
                "symbol": sym,
                "entry_price": entry_p,
                "current_price": cur_price,
                "bars_held": bars_held,
                "pnl_pct": round(pnl_pct, 2),
                "stop_loss": t.get("stop_loss"),
                "target": t.get("target_price"),
                "exit_check": exit_ck,
            })
    except Exception:
        pass

    avg_conf = round(sum(h["confluence_pct"] for h in hot) / len(hot), 1) if hot else 0

    return {
        "scalper_active": SCALPING_MODE,
        "scan_time": _dt.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "market_status": "open" if raw.get("market_open") else "closed",
        # See the note in /dashboard/swing. scalper.html never read this key,
        # so nothing on the page changes.
        "hot_stocks": hot,
        "active_scalps": active_scalps,
        "stats": {
            "total_scanned": len(all_sigs),
            "hot_count": len(hot),
            "active_scalps": len(active_scalps),
            "avg_confluence": avg_conf,
        },
        "filters_applied": {
            "min_volume_ratio": 3.0,
            "min_adx": 25,
            "vwap_required": True,
            "scalping_mode": SCALPING_MODE,
        },
    }


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
# /dashboard/brain-insights — Phase 5: Trading Learnings
# ═══════════════════════════════════════════════════

def _bi_conn():
    db_path = os.path.join(os.path.dirname(__file__), "data", "life.db")
    c = sqlite3.connect(db_path, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def _rows_to_list(rows):
    return [dict(r) for r in rows] if rows else []


def _build_key_learnings(c):
    """4 cards: best timeframe, top pattern, top indicator proxy, best regime."""
    # 1. Timeframe comparison (from signal_snapshots)
    timeframe_stats = c.execute("""
        SELECT
            source as timeframe,
            COUNT(*) as samples,
            ROUND(100.0 * SUM(CASE WHEN outcome='hit' THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
            ROUND(AVG(CASE WHEN outcome='hit' THEN max_gain_pct ELSE -max_loss_pct END), 2) as avg_return
        FROM signal_snapshots
        WHERE outcome IN ('hit','miss')
        GROUP BY source
        ORDER BY avg_return DESC
    """).fetchall()

    # 2. Top pattern (from mined_strategies)
    top_pattern = c.execute("""
        SELECT
            pattern_atoms, pattern_ar, timeframe, regime,
            ROUND(profitable_rate * 100, 1) as win_pct,
            ROUND(ev, 2) as ev,
            sample_size as samples,
            ROUND(profit_factor, 2) as pf
        FROM mined_strategies
        WHERE sample_size >= 30
        ORDER BY ev DESC
        LIMIT 1
    """).fetchone()

    # 3. Best indicator proxy — which single-atom patterns have highest EV
    best_indicator = c.execute("""
        SELECT
            pattern_atoms as indicator,
            COUNT(*) as strategy_count,
            ROUND(AVG(ev), 2) as avg_ev,
            ROUND(AVG(profitable_rate) * 100, 1) as avg_win_pct
        FROM mined_strategies
        WHERE sample_size >= 30 AND ev > 0
          AND pattern_atoms NOT LIKE '%,%'
        GROUP BY pattern_atoms
        HAVING COUNT(*) >= 2
        ORDER BY avg_ev DESC
        LIMIT 1
    """).fetchone()

    # 4. Best regime context (from signal_outcomes)
    best_context = c.execute("""
        SELECT
            regime_calc as regime,
            regime_dir as direction,
            COUNT(*) as samples,
            ROUND(100.0 * SUM(CASE WHEN outcome_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
            ROUND(AVG(outcome_pct), 2) as avg_return
        FROM signal_outcomes
        WHERE regime_calc IS NOT NULL
        GROUP BY regime_calc, regime_dir
        HAVING COUNT(*) >= 50
        ORDER BY avg_return DESC
        LIMIT 1
    """).fetchone()

    return {
        "timeframe_comparison": _rows_to_list(timeframe_stats),
        "top_pattern": dict(top_pattern) if top_pattern else None,
        "best_indicator": dict(best_indicator) if best_indicator else None,
        "best_context": dict(best_context) if best_context else None,
    }


def _build_edge_map(c):
    """Performance map: timeframe × regime × direction."""
    # By timeframe
    by_timeframe = c.execute("""
        SELECT
            timeframe,
            COUNT(*) as samples,
            ROUND(100.0 * SUM(CASE WHEN outcome_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
            ROUND(AVG(outcome_pct), 2) as avg_return
        FROM signal_outcomes
        GROUP BY timeframe
    """).fetchall()

    # Top 5 contexts
    top_contexts = c.execute("""
        SELECT
            timeframe,
            regime_calc as regime,
            regime_dir as direction,
            COUNT(*) as samples,
            ROUND(100.0 * SUM(CASE WHEN outcome_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
            ROUND(AVG(outcome_pct), 2) as avg_return
        FROM signal_outcomes
        WHERE regime_calc IS NOT NULL
        GROUP BY timeframe, regime_calc, regime_dir
        HAVING COUNT(*) >= 30
        ORDER BY avg_return DESC
        LIMIT 5
    """).fetchall()

    # Worst 5 contexts
    worst_contexts = c.execute("""
        SELECT
            timeframe,
            regime_calc as regime,
            regime_dir as direction,
            COUNT(*) as samples,
            ROUND(100.0 * SUM(CASE WHEN outcome_pct > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
            ROUND(AVG(outcome_pct), 2) as avg_return
        FROM signal_outcomes
        WHERE regime_calc IS NOT NULL
        GROUP BY timeframe, regime_calc, regime_dir
        HAVING COUNT(*) >= 30
        ORDER BY avg_return ASC
        LIMIT 5
    """).fetchall()

    return {
        "by_timeframe": _rows_to_list(by_timeframe),
        "top_contexts": _rows_to_list(top_contexts),
        "worst_contexts": _rows_to_list(worst_contexts),
    }


def _build_top_strategies(c):
    """Best/worst 5 strategies + helpful patterns."""
    best = c.execute("""
        SELECT
            strategy_id, pattern_ar, timeframe, regime,
            sample_size as samples,
            ROUND(profitable_rate * 100, 1) as win_pct,
            ROUND(ev, 2) as ev,
            ROUND(profit_factor, 2) as pf,
            ROUND(stability, 2) as stability
        FROM mined_strategies
        WHERE sample_size >= 30
        ORDER BY ev DESC
        LIMIT 5
    """).fetchall()

    worst = c.execute("""
        SELECT
            strategy_id, pattern_ar, timeframe, regime,
            sample_size as samples,
            ROUND(profitable_rate * 100, 1) as win_pct,
            ROUND(ev, 2) as ev,
            ROUND(profit_factor, 2) as pf,
            ROUND(stability, 2) as stability
        FROM mined_strategies
        WHERE sample_size >= 30
        ORDER BY ev ASC
        LIMIT 5
    """).fetchall()

    # Helpful patterns: multi-atom patterns with high EV
    helpful = c.execute("""
        SELECT
            pattern_atoms, pattern_ar,
            COUNT(*) as strategy_count,
            ROUND(AVG(ev), 2) as avg_ev,
            ROUND(AVG(profitable_rate) * 100, 1) as avg_win_pct
        FROM mined_strategies
        WHERE ev > 3 AND sample_size >= 30
        GROUP BY pattern_atoms
        ORDER BY avg_ev DESC
        LIMIT 10
    """).fetchall()

    return {
        "best_5": _rows_to_list(best),
        "worst_5": _rows_to_list(worst),
        "helpful_patterns": _rows_to_list(helpful),
    }


def _build_decision_scorecard(c):
    """Decision audit performance."""
    # Check if table has data
    cnt = c.execute("SELECT COUNT(*) FROM decision_audit").fetchone()[0]
    if cnt == 0:
        return {"message": "لا توجد بيانات بعد", "total_decisions": 0}

    total = c.execute("""
        SELECT smart_decision, COUNT(*) as count
        FROM decision_audit
        GROUP BY smart_decision
    """).fetchall()

    by_confidence = c.execute("""
        SELECT
            CASE
                WHEN confidence >= 90 THEN '90+'
                WHEN confidence >= 80 THEN '80-89'
                WHEN confidence >= 70 THEN '70-79'
                ELSE '<70'
            END as bucket,
            COUNT(*) as count,
            ROUND(AVG(confidence), 1) as avg_conf,
            ROUND(AVG(data_quality), 1) as avg_quality
        FROM decision_audit
        WHERE smart_decision = 'ENTER'
        GROUP BY bucket
        ORDER BY bucket DESC
    """).fetchall()

    by_quality = c.execute("""
        SELECT
            CASE
                WHEN data_quality >= 80 THEN 'عالية'
                WHEN data_quality >= 60 THEN 'متوسطة'
                ELSE 'ضعيفة'
            END as quality_ar,
            COUNT(*) as count,
            ROUND(AVG(rr_ratio), 2) as avg_rr
        FROM decision_audit
        WHERE smart_decision = 'ENTER'
        GROUP BY quality_ar
    """).fetchall()

    top_used = c.execute("""
        SELECT
            strategy_id,
            COUNT(*) as used_count,
            ROUND(AVG(rr_ratio), 2) as avg_rr,
            ROUND(AVG(confidence), 1) as avg_conf
        FROM decision_audit
        WHERE smart_decision = 'ENTER' AND strategy_id IS NOT NULL AND strategy_id != ''
        GROUP BY strategy_id
        ORDER BY used_count DESC
        LIMIT 5
    """).fetchall()

    # Recent ENTER decisions (last 7 days)
    recent = c.execute("""
        SELECT symbol, market_date, confidence, data_quality, rr_ratio, sector,
               chosen_plan_source, outcome
        FROM decision_audit
        WHERE smart_decision = 'ENTER'
        ORDER BY decision_time DESC
        LIMIT 10
    """).fetchall()

    return {
        "total_decisions": cnt,
        "total_by_decision": _rows_to_list(total),
        "enter_by_confidence": _rows_to_list(by_confidence),
        "enter_by_quality": _rows_to_list(by_quality),
        "top_used_strategies": _rows_to_list(top_used),
        "recent_enters": _rows_to_list(recent),
    }


def _build_action_panel(c):
    """3 lists: do more / avoid / system stats."""
    do_more = c.execute("""
        SELECT timeframe, regime_calc as regime, regime_dir as direction,
            COUNT(*) as samples,
            ROUND(AVG(outcome_pct), 2) as avg_return
        FROM signal_outcomes
        WHERE regime_calc IS NOT NULL
        GROUP BY timeframe, regime_calc, regime_dir
        HAVING COUNT(*) >= 50 AND AVG(outcome_pct) > 2
        ORDER BY avg_return DESC
        LIMIT 3
    """).fetchall()

    avoid = c.execute("""
        SELECT timeframe, regime_calc as regime, regime_dir as direction,
            COUNT(*) as samples,
            ROUND(AVG(outcome_pct), 2) as avg_return
        FROM signal_outcomes
        WHERE regime_calc IS NOT NULL
        GROUP BY timeframe, regime_calc, regime_dir
        HAVING COUNT(*) >= 50 AND AVG(outcome_pct) < 0
        ORDER BY avg_return ASC
        LIMIT 3
    """).fetchall()

    stats = c.execute("""
        SELECT
            (SELECT COUNT(*) FROM mined_strategies) as total_strategies,
            (SELECT COUNT(*) FROM signal_outcomes) as total_signals,
            (SELECT COUNT(DISTINCT symbol) FROM signal_outcomes) as unique_stocks,
            (SELECT COUNT(*) FROM decision_audit) as total_decisions,
            (SELECT COUNT(*) FROM decision_audit WHERE smart_decision='ENTER') as total_enters,
            (SELECT ROUND(AVG(ev), 2) FROM mined_strategies WHERE sample_size >= 30) as avg_strategy_ev
    """).fetchone()

    return {
        "do_more": _rows_to_list(do_more),
        "avoid": _rows_to_list(avoid),
        "system_stats": dict(stats) if stats else {},
    }


@router.get("/dashboard/brain-insights")
async def dashboard_brain_insights():
    """Phase 5: Trading learnings — what the system learned, what works, what doesn't."""
    try:
        c = _bi_conn()
        result = {
            "generated_at": datetime.now().isoformat(),
            "key_learnings": _build_key_learnings(c),
            "edge_map": _build_edge_map(c),
            "top_strategies": _build_top_strategies(c),
            "decision_scorecard": _build_decision_scorecard(c),
            "action_panel": _build_action_panel(c),
        }
        c.close()
        return result
    except Exception as e:
        logger.error("brain-insights error: %s", e, exc_info=True)
        return {"error": str(e)}


@router.get("/dashboard/strategies")
async def dashboard_strategies():
    """Mined strategies from FP-Growth engine — ranked by final_score."""
    import json as _json
    db_path = os.path.join(os.path.dirname(__file__), "data", "life.db")
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Total count
        total = cursor.execute("SELECT COUNT(*) FROM mined_strategies").fetchone()[0]

        # Top 30 strategies
        rows = cursor.execute("""
            SELECT strategy_id, pattern_atoms, pattern_ar,
                   timeframe, regime, sample_size, unique_stocks, unique_months,
                   profitable_rate, hit_rate_3pct, hit_rate_5pct,
                   baseline_profitable, uplift, ev, speed_score,
                   profit_factor, rr_proxy,
                   avg_max_gain, avg_max_loss, avg_outcome, median_outcome,
                   entry_discount_pct, entry_method, target_1_pct, target_2_pct,
                   stop_pct, rr_ratio, est_hold_days,
                   p_value, stability, walk_forward,
                   final_score, rank, status
            FROM mined_strategies
            WHERE status IN ('production', 'candidate')
            ORDER BY final_score DESC
            LIMIT 30
        """).fetchall()

        strategies = []
        for r in rows:
            s = dict(r)
            # Parse JSON fields for frontend
            if s.get("pattern_atoms"):
                try:
                    s["pattern_atoms_list"] = _json.loads(s["pattern_atoms"])
                except Exception:
                    s["pattern_atoms_list"] = []
            if s.get("walk_forward"):
                try:
                    s["walk_forward_parsed"] = _json.loads(s["walk_forward"])
                except Exception:
                    s["walk_forward_parsed"] = []
            strategies.append(s)

        # Summary by segment
        segments = cursor.execute("""
            SELECT timeframe, regime, COUNT(*) as cnt,
                   ROUND(AVG(ev), 2) as avg_ev,
                   ROUND(AVG(profitable_rate), 3) as avg_wr
            FROM mined_strategies
            WHERE status IN ('production', 'candidate')
            GROUP BY timeframe, regime
            ORDER BY AVG(ev) DESC
        """).fetchall()

        conn.close()

        return {
            "total": total,
            "showing": len(strategies),
            "segments": [dict(s) for s in segments],
            "strategies": strategies,
        }
    except Exception as e:
        return {"total": 0, "error": str(e), "strategies": []}


# ═══════════════════════════════════════════════════
# Trade Management API
# ═══════════════════════════════════════════════════

from fastapi import Body

@router.post("/api/trade/open")
async def api_trade_open(data: dict = Body(...)):
    """Open a new trade."""
    try:
        from journal_engine import open_trade
        # D-3: the broker execution date is required - defaulting to today
        # forged same-day entries on backdated logs
        required = ["symbol", "entry_price", "quantity", "entry_date"]
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
            entry_date=str(data["entry_date"])[:10],
            entry_date_precision=data.get("entry_date_precision", "exact"),
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
    """Update trade fields: entry_price, quantity, stop_loss, take_profit."""
    try:
        trade_id = data.get("trade_id")
        if not trade_id:
            return {"success": False, "error": "Missing trade_id"}
        trade_id = int(trade_id)

        import sqlite3 as _sq
        db_path = os.path.join(os.path.dirname(__file__), "data", "life.db")
        conn = _sq.connect(db_path, timeout=5)
        conn.row_factory = _sq.Row

        row = conn.execute("SELECT id, status FROM trades WHERE id=?", (trade_id,)).fetchone()
        if not row or row["status"] != "open":
            conn.close()
            return {"success": False, "error": "Trade not found or not open"}

        updates = []
        params = []
        if data.get("entry_price") is not None:
            updates.append("entry_price=?")
            params.append(float(data["entry_price"]))
        if data.get("quantity") is not None:
            updates.append("quantity=?")
            params.append(int(data["quantity"]))
        if data.get("stop_loss") is not None:
            updates.append("stop_loss=?")
            params.append(float(data["stop_loss"]))
        if data.get("take_profit") is not None:
            updates.append("take_profit=?")
            params.append(float(data["take_profit"]))

        if not updates:
            conn.close()
            return {"success": False, "error": "Nothing to update"}

        from datetime import datetime as _dt2
        updates.append("updated_at=?")
        params.append(_dt2.now().strftime("%Y-%m-%d %H:%M:%S"))
        params.append(trade_id)
        conn.execute(f"UPDATE trades SET {','.join(updates)} WHERE id=?", params)
        conn.commit()
        conn.close()
        return {"success": True, "message": "Trade updated"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════
# /api/risk-config — Get/Update risk configuration
# ═══════════════════════════════════════════════════

@router.get("/api/risk-config")
async def api_risk_config_get():
    """Get current risk configuration."""
    try:
        from risk_engine import _get_risk_config
        return _get_risk_config()
    except Exception as e:
        return {"error": str(e)}

@router.post("/api/risk-config")
async def api_risk_config_update(data: dict = Body(...)):
    """Update risk configuration (capital, max positions, risk per trade, etc.)."""
    try:
        import sqlite3 as _sq3
        db_path = os.path.join(os.path.dirname(__file__), "data", "life.db")
        conn = _sq3.connect(db_path, timeout=5)
        conn.execute("CREATE TABLE IF NOT EXISTS risk_config (key TEXT PRIMARY KEY, value TEXT)")
        allowed_keys = ["account_capital", "risk_per_trade_pct", "max_positions", "max_heat_pct", "max_sector_positions"]
        updated = []
        for k, v in data.items():
            if k in allowed_keys:
                conn.execute("INSERT OR REPLACE INTO risk_config (key, value) VALUES (?, ?)", (k, str(v)))
                updated.append(k)
        conn.commit()
        conn.close()
        if not updated:
            return {"success": False, "error": "No valid keys provided. Allowed: " + ", ".join(allowed_keys)}
        return {"success": True, "updated": updated}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════
# /api/data-health — Data collection health status
# ═══════════════════════════════════════════════════

@router.get("/api/data-health")
async def api_data_health():
    """Data health: last collection, freshness, coverage."""
    try:
        from kse_data_collector import get_data_health
        return get_data_health()
    except Exception as e:
        logger.error("data-health error: %s", e, exc_info=True)
        return {"error": str(e)}


@router.get("/api/data-freshness")
async def api_data_freshness():
    """Data freshness: last update, age, bridge status, per-stock staleness."""
    try:
        db_path = os.path.join(os.path.dirname(__file__), "data", "life.db")
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row

        # Last radar update
        row = conn.execute(
            "SELECT MAX(updated_at) as last_update FROM stock_radar_daily"
        ).fetchone()
        last_update = row["last_update"] if row else None

        # D-4: session-aged, no sentinel
        _fr = _session_freshness(last_update, None)
        age_hours = _fr.get("data_age_hours")
        is_stale = _fr["is_stale"]
        freshness = _fr["freshness"]

        # Total and stale counts
        total_row = conn.execute("SELECT COUNT(*) as cnt FROM stock_radar_daily").fetchone()
        total = total_row["cnt"] if total_row else 0

        stale_count = 0
        fresh_count = 0
        aging_count = 0
        rows = conn.execute("SELECT updated_at FROM stock_radar_daily").fetchall()
        for r in rows:
            if r["updated_at"]:
                try:
                    from datetime import datetime as _dt
                    from kse_data_collector import parse_utc_naive
                    u = parse_utc_naive(r["updated_at"])
                    if u is None:
                        stale_count += 1
                        continue
                    h = (_dt.utcnow() - u).total_seconds() / 3600
                    if h < 6:
                        fresh_count += 1
                    elif h < 18:
                        aging_count += 1
                    else:
                        stale_count += 1
                except Exception:
                    stale_count += 1
            else:
                stale_count += 1
        conn.close()

        # Bridge connectivity
        # G-4 (2026-08-16): the bridge is retired. A dangling endpoint that times
        # out is a silent failure waiting to be misread as "no signal", so
        # the probe is gone rather than left to fail quietly every call.
        bridge_online = False

        return {
            "last_radar_update": last_update,
            "age_hours": age_hours,
            "age_reason": _fr.get("age_reason"),
            "data_state": _fr.get("data_state"),
            "data_state_ar": _fr.get("data_state_ar"),
            "sessions_old": _fr.get("sessions_old"),
            "is_stale": is_stale,
            "freshness": freshness,
            "bridge_online": bridge_online,
            "total_stocks": total,
            "fresh_count": fresh_count,
            "aging_count": aging_count,
            "stale_count": stale_count,
        }
    except Exception as e:
        logger.error("data-freshness error: %s", e)
        return {"error": str(e)}


def _require_api_key(request: Request) -> None:
    """Endpoint-level key check.

    APIKeyMiddleware skips the whole /api/ prefix, and narrowing that would
    break seven dashboard pages (table 0.4 in _tools/ARCHITECTURE_MAP.md), so
    state-changing endpoints under /api/ that no page calls enforce the key
    themselves. Fails closed when the server has no key configured.
    """
    expected = os.getenv("MASTER_AI_API_KEY", "")
    if not expected:
        logger.warning("MASTER_AI_API_KEY is empty - refusing %s", request.url.path)
        raise HTTPException(status_code=401, detail="Unauthorized")
    supplied = request.headers.get("X-API-Key")
    if supplied is None:
        supplied = request.query_params.get("api_key")
        if supplied is not None:
            logger.warning(
                "api_key passed in the query string for %s - move it to the "
                "X-API-Key header", request.url.path,
            )
    if supplied != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/api/collect-now")
async def api_collect_now(request: Request):
    """Trigger manual data collection (on-demand).

    Requires the API key: no dashboard page calls this, and it starts a long
    outbound job. A second request while one is running gets 409 rather than
    queueing for an executor worker.
    """
    _require_api_key(request)
    try:
        from kse_data_collector import collect_and_refresh, is_collecting
        if is_collecting():
            return JSONResponse(
                {"success": False, "error": "collection already running"},
                status_code=409,
            )
        # collect_and_refresh() is sync and talks to the bridge over raw
        # requests. Called directly it held the event loop for the whole
        # batch walk - every other request on the server stalled behind it,
        # and this endpoint sits under the /api/ prefix that skips the API
        # key, so any caller could trigger that.
        result = await asyncio.to_thread(collect_and_refresh)
        if result.get("status") == "busy":
            # lost the race between is_collecting() and the lock
            return JSONResponse(
                {"success": False, "error": "collection already running"},
                status_code=409,
            )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error("collect-now error: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════
# /api/portfolio-status — Position Engine Summary + Alerts
# ═══════════════════════════════════════════════════

@router.get("/api/portfolio-status")
async def api_portfolio_status():
    """Portfolio status with position monitoring alerts."""
    try:
        from position_engine import PositionEngine, init_position_schema
        init_position_schema()
        engine = PositionEngine()

        summary = engine.get_portfolio_summary()
        active_alerts = engine.get_active_alerts(days=7)
        last_monitored = engine.get_last_monitor_time()

        # Parse alert_data JSON for each alert
        for a in active_alerts:
            if a.get("alert_data"):
                try:
                    a["alert_data"] = json.loads(a["alert_data"])
                except Exception:
                    pass

        return {
            "portfolio": summary,
            "active_alerts": active_alerts,
            "last_monitored": last_monitored,
        }
    except Exception as e:
        logger.error("portfolio-status error: %s", e, exc_info=True)
        return {"error": str(e), "portfolio": None, "active_alerts": []}


@router.post("/api/portfolio-monitor")
async def api_portfolio_monitor(request: Request):
    """Trigger daily position monitoring scan (on-demand)."""
    _require_api_key(request)
    try:
        from position_engine import run_daily_monitor
        result = run_daily_monitor()
        return {"success": True, "result": result}
    except Exception as e:
        logger.error("portfolio-monitor error: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/api/portfolio-alert-ack")
async def api_portfolio_alert_ack(request: Request):
    """Acknowledge a position alert."""
    _require_api_key(request)
    try:
        body = await request.json()
        alert_id = body.get("alert_id")
        if not alert_id:
            return {"success": False, "error": "alert_id required"}
        from position_engine import PositionEngine
        engine = PositionEngine()
        engine.acknowledge_alert(int(alert_id))
        return {"success": True}
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


# ═══════════════════════════════════════════════════
# TIER 3 DASHBOARD ENDPOINTS
# ═══════════════════════════════════════════════════

_DB = os.path.join(os.path.dirname(__file__), "data", "audit.db")


@router.get("/api/memory-extraction/stats")
async def api_memory_extraction_stats():
    """Enhancement 1: Auto-learning card stats."""
    try:
        conn = sqlite3.connect(_DB, timeout=3)
        conn.row_factory = sqlite3.Row

        # Total active observations
        total = conn.execute("SELECT COUNT(*) as c FROM memory WHERE active=1").fetchone()["c"]

        # By scope
        scope_rows = conn.execute(
            "SELECT COALESCE(scope,'global') as s, COUNT(*) as c FROM memory WHERE active=1 GROUP BY s"
        ).fetchall()
        by_scope = {r["s"]: r["c"] for r in scope_rows}

        # Extracted today (auto_extract source)
        today = datetime.utcnow().strftime("%Y-%m-%d")  # memory.created_at is UTC
        today_count = conn.execute(
            "SELECT COUNT(*) as c FROM memory WHERE source='auto_extract' AND created_at LIKE ?",
            (today + "%",)
        ).fetchone()["c"]

        # This week
        week_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        week_count = conn.execute(
            "SELECT COUNT(*) as c FROM memory WHERE source='auto_extract' AND created_at >= ?",
            (week_ago,)
        ).fetchone()["c"]

        # Last extraction
        last_row = conn.execute(
            "SELECT created_at, category FROM memory WHERE source='auto_extract' ORDER BY id DESC LIMIT 5"
        ).fetchall()

        last_at = last_row[0]["created_at"] if last_row else None
        last_topics = list(set(r["category"] for r in last_row)) if last_row else []

        conn.close()
        return {
            "today_extracted": today_count,
            "week_extracted": week_count,
            "last_extraction_at": last_at,
            "last_topics": last_topics,
            "total_observations": total,
            "by_scope": by_scope,
        }
    except Exception as e:
        return {"error": str(e), "today_extracted": 0, "week_extracted": 0,
                "total_observations": 0, "by_scope": {}}


@router.get("/api/intent-analytics")
async def api_intent_analytics():
    """Enhancement 2: Intent routing analytics."""
    try:
        conn = sqlite3.connect(_DB, timeout=3)
        conn.row_factory = sqlite3.Row

        today = datetime.now().strftime("%Y-%m-%d")

        # Today totals
        total = conn.execute(
            "SELECT COUNT(*) as c FROM intent_audit WHERE created_at LIKE ?",
            (today + "%",)
        ).fetchone()["c"]

        success = conn.execute(
            "SELECT COUNT(*) as c FROM intent_audit WHERE created_at LIKE ? AND final_state='responded'",
            (today + "%",)
        ).fetchone()["c"]

        failed = conn.execute(
            "SELECT COUNT(*) as c FROM intent_audit WHERE created_at LIKE ? AND final_state='failed'",
            (today + "%",)
        ).fetchone()["c"]

        # Avg duration
        avg_row = conn.execute(
            "SELECT AVG(duration_ms) as avg FROM intent_audit WHERE created_at LIKE ?",
            (today + "%",)
        ).fetchone()
        avg_ms = int(avg_row["avg"] or 0)

        # Top intents
        top = conn.execute(
            "SELECT intent, COUNT(*) as c FROM intent_audit "
            "WHERE created_at LIKE ? AND intent IS NOT NULL "
            "GROUP BY intent ORDER BY c DESC LIMIT 10",
            (today + "%",)
        ).fetchall()

        # Recent 5
        recent = conn.execute(
            "SELECT created_at as timestamp, intent, final_state as state, "
            "duration_ms, transitions FROM intent_audit "
            "ORDER BY id DESC LIMIT 5"
        ).fetchall()

        conn.close()
        return {
            "today_total": total,
            "today_success": success,
            "today_failed": failed,
            "avg_duration_ms": avg_ms,
            "top_intents": [{"intent": r["intent"], "count": r["c"]} for r in top],
            "recent": [dict(r) for r in recent],
        }
    except Exception as e:
        return {"error": str(e), "today_total": 0, "today_success": 0,
                "today_failed": 0, "avg_duration_ms": 0, "top_intents": [], "recent": []}


@router.get("/api/brain/stats")
async def api_brain_stats():
    """Enhancement 3: Brain observations statistics."""
    try:
        conn = sqlite3.connect(_DB, timeout=3)
        conn.row_factory = sqlite3.Row

        total = conn.execute("SELECT COUNT(*) as c FROM memory WHERE active=1").fetchone()["c"]

        # By scope
        scope_rows = conn.execute(
            "SELECT COALESCE(scope,'global') as s, COUNT(*) as c FROM memory WHERE active=1 GROUP BY s"
        ).fetchall()
        by_scope = {r["s"]: r["c"] for r in scope_rows}

        # Recent 24h
        yesterday = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        recent_24h = conn.execute(
            "SELECT COUNT(*) as c FROM memory WHERE active=1 AND COALESCE(updated_at, created_at) >= ?",
            (yesterday,)
        ).fetchone()["c"]

        # Staleness distribution
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        one_day = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        one_week = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

        fresh = conn.execute(
            "SELECT COUNT(*) as c FROM memory WHERE active=1 AND COALESCE(updated_at, created_at) >= ?",
            (one_day,)
        ).fetchone()["c"]
        recent_count = conn.execute(
            "SELECT COUNT(*) as c FROM memory WHERE active=1 AND COALESCE(updated_at, created_at) >= ? AND COALESCE(updated_at, created_at) < ?",
            (one_week, one_day)
        ).fetchone()["c"]
        old = total - fresh - recent_count

        # Oldest
        oldest = conn.execute(
            "SELECT MIN(created_at) as oldest FROM memory WHERE active=1"
        ).fetchone()["oldest"]
        oldest_days = 0
        if oldest:
            try:
                from brain_core import memory_age_days
                oldest_days = memory_age_days(oldest)
            except Exception:
                pass

        conn.close()
        return {
            "total_observations": total,
            "by_scope": by_scope,
            "recent_24h": recent_24h,
            "oldest_observation_days": oldest_days,
            "staleness_distribution": {
                "fresh": fresh,
                "recent": recent_count,
                "old": max(old, 0),
            },
        }
    except Exception as e:
        return {"error": str(e), "total_observations": 0, "by_scope": {},
                "recent_24h": 0, "staleness_distribution": {}}


# Context health counters (in-memory, reset on restart)
_context_layer_stats = {
    "trim": {"fires": 0, "last": None},
    "compress": {"fires": 0, "last": None},
    "summarize": {"fires": 0, "last": None},
    "emergency": {"fires": 0, "last": None},
}
_context_tokens_current = 0


def record_context_layer(layer_name: str):
    """Called by context_manager.py when a layer fires."""
    if layer_name in _context_layer_stats:
        _context_layer_stats[layer_name]["fires"] += 1
        _context_layer_stats[layer_name]["last"] = datetime.now().isoformat()


def set_context_tokens(tokens: int):
    """Update current token estimate."""
    global _context_tokens_current
    _context_tokens_current = tokens


@router.get("/api/context-health")
async def api_context_health():
    """Enhancement 4: Context management health."""
    today = datetime.now().strftime("%Y-%m-%d")
    compactions = sum(
        s["fires"] for s in _context_layer_stats.values()
        if s["last"] and s["last"].startswith(today)
    )
    active = "idle"
    if _context_layer_stats["emergency"]["fires"] > 0:
        active = "emergency"
    elif _context_layer_stats["summarize"]["fires"] > 0:
        active = "summarize"
    elif _context_layer_stats["compress"]["fires"] > 0:
        active = "compress"
    elif _context_layer_stats["trim"]["fires"] > 0:
        active = "trim"

    return {
        "current_tokens_estimate": _context_tokens_current,
        "max_tokens": 180000,
        "active_layer": active,
        "compactions_today": compactions,
        "layer_stats": _context_layer_stats,
    }


# Radar progress (in-memory, updated by parallel_coordinator)
_radar_progress = {
    "status": "idle",
    "total_stocks": 0,
    "completed": 0,
    "workers": 0,
    "elapsed_ms": 0,
    "last_completed": None,
}


def update_radar_progress(**kwargs):
    """Called during radar refresh to update progress."""
    _radar_progress.update(kwargs)


@router.get("/api/radar/progress")
async def api_radar_progress():
    """Enhancement 5: Radar parallel refresh progress."""
    return _radar_progress


@router.get("/api/latency-stats")
async def api_latency_stats():
    """Enhancement 6: Response latency breakdown."""
    try:
        conn = sqlite3.connect(_DB, timeout=3)
        conn.row_factory = sqlite3.Row

        today = datetime.now().strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT duration_ms FROM intent_audit WHERE created_at LIKE ? AND duration_ms IS NOT NULL",
            (today + "%",)
        ).fetchall()
        conn.close()

        if not rows:
            return {"avg_total_ms": 0, "samples": 0}

        durations = [r["duration_ms"] for r in rows]
        avg_total = sum(durations) // len(durations)

        # Rough breakdown estimate (real tracking requires instrumented code)
        return {
            "avg_total_ms": avg_total,
            "avg_intent_ms": min(avg_total // 10, 200),
            "avg_memory_ms": min(avg_total // 8, 300),
            "avg_llm_ms": max(avg_total - 400, 0),
            "prefetch_savings_ms": min(avg_total // 5, 500),
            "samples": len(durations),
        }
    except Exception as e:
        return {"error": str(e), "avg_total_ms": 0, "samples": 0}


@router.get("/api/skills")
async def api_skills():
    """List all available skills from skills/ directory (#20 Tier3)."""
    try:
        from skill_loader import SkillLoader
        loader = SkillLoader()
        return {"skills": loader.list_skills(), "count": len(loader.list_skills())}
    except Exception as e:
        return {"skills": [], "count": 0, "error": str(e)}
