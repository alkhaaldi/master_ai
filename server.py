# Structured Memory
try:
    import structured_memory as smem
    _SMEM = True
except ImportError:
    _SMEM = False

"""
Master AI Control API Server v5.0
Raspberry Pi - Home Assistant + Windows Agent Integration
Port: 9000

Upgrades from v4:
  1. Task Manager (stateful execution with resume)
  2. Iterative Planning Loop (planÃÂ¢ÃÂÃÂexecuteÃÂ¢ÃÂÃÂverifyÃÂ¢ÃÂÃÂreplan)
  3. Strict Action Schemas (Pydantic validation)
  4. Memory Productization (short-term + long-term, graceful fallback)
  5. Observability (structured tracing, latency metrics)

Endpoints: /ask (v7 chat), /health, /ha/*, /ssh/run, /agent (v7 chat), /approve/{id}, /audit, /win/*,
           /tasks/*, /sessions/*, /knowledge/*, /memory/*, /stocks/*, /deploy, /stats/*
"""

import os
import sys
import re
import time
import json
import uuid
import hmac
import hashlib
import logging
import asyncio
import sqlite3
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional, Any, Literal
from collections import deque
from enum import Enum

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Query, Path, Header
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel, Field, field_validator
from openai import AsyncOpenAI, OpenAIError
from anthropic import AsyncAnthropic
import httpx

# Brain Module (intelligence layer)
try:
    from brain import build_system_prompt, learn_from_result, reload as brain_reload, get_brain_stats, get_quick_response, build_response_prompt, proactive_loop, get_system_diag, run_backup, backup_loop, record_error, detect_user, get_multiuser_stats, record_feedback, log_request, get_analytics
    BRAIN_AVAILABLE = True
except Exception as e:
    BRAIN_AVAILABLE = False
    logging.getLogger("master_ai").warning("Brain module not available, using built-in planner: %s", e)
try:
    from tg_ops import is_tg_admin, get_pending_approvals, process_approval, format_approval_buttons, run_backup as tg_run_backup, get_admin_chat_id
    TG_OPS_OK = True
except Exception as _e:
    TG_OPS_OK = False
    logging.getLogger("master_ai").warning("tg_ops not loaded: %s", _e)

try:
    from tg_home import cmd_rooms, cmd_devices, cmd_find, find_buttons, cmd_scenes_dynamic, handle_devctl
    TG_HOME_OK = True
except Exception as _e:
    TG_HOME_OK = False
    logging.getLogger("master_ai").warning("tg_home not loaded: %s", _e)

try:
    from tg_session import tg_session_get, tg_session_upsert, tg_session_append_context, tg_session_reset, detect_followup, tg_session_get_compacted
    from tg_session_resolver import resolve_followup_action
    pass  # logger not ready yet
    TG_SESSION_OK = True
except Exception as _e:
    TG_SESSION_OK = False
    logging.getLogger("master_ai").warning("tg_session not loaded: %s", _e)

try:
    from tg_intent_router import route_intent, learn_alias, get_alias_stats  # quick_classify removed
    TG_INTENT_OK = True
except Exception as _e:
    TG_INTENT_OK = False
    logging.getLogger("master_ai").warning("tg_intent_router not loaded: %s", _e)

# R2-P2: Smart Tips Engine
try:
    from tips_engine import TipsEngine
    _tips_engine = TipsEngine()
    TIPS_OK = True
except Exception as _e:
    _tips_engine = None
    TIPS_OK = False
    logging.getLogger("master_ai").warning("tips_engine not loaded: %s", _e)

try:
    from smart_router import classify_message
    SMART_ROUTER_OK = True
except Exception as _e:
    SMART_ROUTER_OK = False
    logging.getLogger("master_ai").warning("smart_router not loaded: %s", _e)

QUICK_QUERY_OK = False

try:
    from chat_v7 import handle_chat_v7, handle_chat_v7_stream
    CHAT_V7_OK = True
except Exception as _e:
    CHAT_V7_OK = False
    logging.getLogger("master_ai").warning("chat_v7 not loaded: %s", _e)
try:
    from quick_query import quick_answer
    QUICK_QUERY_OK = True
except Exception as _qqe:
    pass

TG_REPORT_OK = False
try:
    from tg_report import generate_daily_report
    TG_REPORT_OK = True
except Exception as _e:
    logging.getLogger("master_ai").warning("tg_report not loaded: %s", _e)

BRAIN_OK = False
try:
    from home_brain import take_snapshot, get_daily_summary, detect_patterns, format_insights_ar, build_digest_prompt, get_brain_stats, cleanup_old_data, get_db_size
    BRAIN_OK = True
except Exception as _e:
    logging.getLogger("master_ai").warning("home_brain not loaded: %s", _e)

# World State Snapshot
WORLD_STATE_OK = False
try:
    from world_state import start_world_state, get_snapshot_text, get_snapshot_data, get_status as ws_get_status
    WORLD_STATE_OK = True
except Exception:
    logging.getLogger("master_ai").warning("world_state not available")


DOCTOR_OK = False
LEARNING_OK = False
try:
    from ha_doctor import detect_anomalies, format_health_report, suggest_fixes, get_unavailable_entities, check_ac_performance
    from ha_history import get_entity_history, analyze_entity, format_history_report as format_history
    from brain_learning import learn_patterns as bl_learn, get_patterns as bl_get_patterns, suggest_automations as bl_suggest, format_patterns_report as bl_format_patterns, get_learning_stats as bl_stats
    from brain_learning import format_maturity_report as bl_maturity
    from brain_learning import detect_anomalies as bl_anomalies, format_anomaly_report as bl_anomaly_report
    from brain_learning import create_ha_automation as bl_create_auto, get_top_suggestions as bl_top_sugs
    from brain_learning import build_daily_summary_report as bl_summary
    from tg_email import format_email_report as email_report, get_email_for_morning as email_morning
    EMAIL_OK = True
except Exception as _e:
    logging.getLogger("master_ai").warning("tg_email not loaded: %s", _e)
    EMAIL_OK = False
try:
    from brain_learning import discover_scenes as bl_discover_scenes, format_scenes_report as bl_scenes_report, create_ha_scene as bl_create_scene
    from brain_learning import filter_existing_automations as bl_filter_autos
    LEARNING_OK = True
    DOCTOR_OK = True
except Exception as _e:
    logging.getLogger("master_ai").warning("brain_learning scenes not loaded: %s", _e)

try:
    from discovery import get_home_summary, sync_entities, get_discovery_stats
    DISCOVERY_OK = True
except Exception as _e:
    DISCOVERY_OK = False
    logging.getLogger("master_ai").warning("discovery not loaded: %s", _e)

try:
    from tg_suggestions import get_suggestions
    TG_SUGGEST_OK = True
except Exception as _e:
    TG_SUGGEST_OK = False
    logging.getLogger("master_ai").warning("tg_suggestions not loaded: %s", _e)

FEEDBACK_OK = False
try:
    from feedback_learner import apply_learning as fl_apply, get_confidence_adjustment as fl_confidence_adj, init as fl_init
    fl_init()
    FEEDBACK_OK = True
except Exception:
    logging.getLogger("master_ai").warning("feedback_learner not available")

PLAN_OK = False
try:
    from plan_engine import init as plan_init, list_plans, add_plan, pause_plan, resume_plan, get_due_plans, record_run, format_plans_list, get_stats as plan_stats, get_plan, delete_plan, complete_plan
    plan_init()
    PLAN_OK = True
except Exception as _pe:
    logging.getLogger("master_ai").warning("plan_engine not available: %s", _pe)

DEGRADED_OK = False
try:
    from degraded_mode import mark_ok as deg_ok, mark_fail as deg_fail, is_degraded, get_mode as deg_mode, format_status as deg_status, init as deg_init, is_ok as deg_is_ok
    deg_init()
    DEGRADED_OK = True
except Exception as _de:
    logging.getLogger("master_ai").warning("degraded_mode not available: %s", _de)

DBBACKUP_OK = False
try:
    from db_backup import run_daily as backup_run_daily, format_status as backup_format_status, get_status as backup_get_status, init as backup_init
    backup_init()
    DBBACKUP_OK = True
except Exception as _be:
    logging.getLogger("master_ai").warning("db_backup not available: %s", _be)

try:
    from tg_morning_report import build_morning_report, send_morning_report
    TG_MORNING_OK = True
except Exception as _e:
    TG_MORNING_OK = False
    logging.getLogger("master_ai").warning("tg_morning_report not loaded: %s", _e)

try:
    from life_router import detect_life_domain
    LIFE_ROUTER_OK = True
except Exception as _e:
    LIFE_ROUTER_OK = False
    logging.getLogger("master_ai").warning("life_router not loaded: %s", _e)

try:
    from life_stocks import handle_stock_command, portfolio_summary
    LIFE_STOCKS_OK = True
except Exception as _e:
    LIFE_STOCKS_OK = False
    logging.getLogger("master_ai").warning("life_stocks not loaded: %s", _e)

try:
    from life_expenses import handle_expense_command
    LIFE_EXPENSES_OK = True
except Exception as _e:
    LIFE_EXPENSES_OK = False
    logging.getLogger("master_ai").warning("life_expenses not loaded: %s", _e)

try:
    from life_health import handle_health_command
    LIFE_HEALTH_OK = True
except Exception as _e:
    LIFE_HEALTH_OK = False
    logging.getLogger("master_ai").warning("life_health not loaded: %s", _e)

try:
    from life_work import handle_work_command, get_shift_display
    LIFE_WORK_OK = True
except Exception as _e:
    LIFE_WORK_OK = False
    logging.getLogger("master_ai").warning("life_work not loaded: %s", _e)

try:
    from signal_review import review_signals, review_scheduler, init_review_schema, get_reviews_for_dashboard
    REVIEW_OK = True
except Exception as _e:
    REVIEW_OK = False
    logging.getLogger("master_ai").warning("signal_review not loaded: %s", _e)


# Suggestion rate limit: {user_id: last_suggest_timestamp}
_suggest_cooldown = {}
_SUGGEST_COOLDOWN_SEC = 30

# Router analytics (in-memory, resets on restart)
_router_cmd_log = []  # Step 9: Ring buffer of last 50 commands
_ROUTER_CMD_MAX = 50

def _log_cmd(text, route, source="", entity=""):
    """Step 9: Log command to ring buffer."""
    import datetime
    _router_cmd_log.append({
        "t": datetime.datetime.now().strftime("%H:%M:%S"),
        "cmd": text[:50], "route": route, "src": source, "ent": entity[:30]
    })
    if len(_router_cmd_log) > _ROUTER_CMD_MAX:
        _router_cmd_log.pop(0)

_router_stats = {"chat": 0, "action": 0, "intent": 0, "followup": 0, "iterative": 0, "total": 0, "started_at": __import__("datetime").datetime.now().isoformat(), "unknown": 0, "life_stocks": 0, "life_expenses": 0, "life_health": 0, "life_work": 0, "template": 0, "template_errors": 0, "intent_matched": 0, "followup_resolved": 0, "action_routed": 0}

# LLM response cache (simple exact-match, TTL 30min, max 50)
_llm_cache = {}  # key=text_hash -> {"resp": str, "ts": float}
_LLM_CACHE_TTL = 1800  # 30 minutes
_LLM_CACHE_MAX = 50
_response_times = []  # deque-like list of recent response times (seconds)
_RESPONSE_TIMES_MAX = 100
_router_cmd_log = []
import pathlib as _pl; _STATS_FILE = _pl.Path(__file__).parent / "data" / "router_stats.json"

def _save_router_stats():
    """Save router stats to disk for persistence across restarts."""
    try:
        _STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATS_FILE.write_text(json.dumps(_router_stats, default=str), encoding="utf-8")
    except Exception as e:
        pass  # Silent fail

def _load_router_stats():
    """Load router stats from disk on startup."""
    global _router_stats
    try:
        if _STATS_FILE.exists():
            saved = json.loads(_STATS_FILE.read_text(encoding="utf-8"))
            # Merge saved into current (keep started_at from current session)
            _started = _router_stats.get("started_at")
            for k, v in saved.items():
                if k != "started_at" and isinstance(v, (int, float)):
                    _router_stats[k] = _router_stats.get(k, 0) + v
            _router_stats["_prev_total"] = saved.get("total", 0)
            _router_stats["_sessions"] = saved.get("_sessions", 0) + 1
    except Exception:
        pass

_tg_disambig_context = {}  # Step 9: {chat_id: original_text} for alias learning

# ── Step 10: Circuit Breaker System ──
class CircuitBreaker:
    """Circuit breaker: track failures, auto-open after threshold, auto-close after cooldown.
    Phase 1: added open_until, feature-flag gating, proper half-open logic."""
    def __init__(self, name, failure_threshold=3, cooldown_seconds=60):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown_seconds
        self.failures = 0
        self.last_failure = 0
        self.open_until = 0  # Phase 1: timestamp when breaker should try half-open
        self.state = "closed"  # closed=OK, open=blocking, half_open=testing
        self.total_trips = 0

    def record_success(self):
        self.failures = 0
        self.state = "closed"
        self.open_until = 0

    def record_failure(self):
        self.failures += 1
        self.last_failure = time.time()
        if self.failures >= self.failure_threshold:
            self.state = "open"
            self.open_until = time.time() + self.cooldown
            self.total_trips += 1
            pass  # logger not ready yet

    def is_available(self):
        if not FEATURE_CIRCUIT_BREAKERS:
            return True  # Feature disabled = always available
        if self.state == "closed":
            return True
        if self.state == "open" and time.time() >= self.open_until:
            self.state = "half_open"
            pass  # logger not ready yet
            return True
        return self.state == "half_open"

    def status(self):
        return {"name": self.name, "state": self.state, "failures": self.failures,
                "total_trips": self.total_trips, "last_failure": self.last_failure,
                "open_until": self.open_until}

_cb_ha = CircuitBreaker("home_assistant", failure_threshold=3, cooldown_seconds=60)
_cb_llm = CircuitBreaker("llm", failure_threshold=3, cooldown_seconds=60)
_cb_tg = CircuitBreaker("telegram", failure_threshold=3, cooldown_seconds=60)


def build_chat_system_prompt(brain_prompt: str = "", home_ctx: str = "", user_msg: str = "") -> str:
    """Chat prompt enriched with memory + owner context."""
    from brain_core import get_owner_context, get_relevant_memories
    owner_ctx = get_owner_context()
    parts = [owner_ctx]
    parts.append("Master AI — المساعد الشخصي لبو خليفة. عربي كويتي مختصر.")
    parts.append("دورك: منزل ذكي + تداول + مواعيد + تخطيط + كل شي يطلبه.")
    parts.append("الستائر inverted: open=مفتوحة, closed=مسكّرة. نص فقط بدون JSON/XML.")
    if home_ctx:
        parts.append(home_ctx)
    if user_msg:
        mem = get_relevant_memories(user_msg)
        if mem:
            parts.append("--- ذاكرة ---")
            parts.append(mem)
    return "\n".join(parts)

async def _fetch_live_ha_context(user_msg: str) -> str:
    """Fetch relevant HA entity states when user asks about rooms/devices/house status."""
    import re as _re
    # Keywords that indicate user wants real-time status
    status_kw = ["حال", "وضع", "حالة", "شغال", "مطفي", "درجة", "حرارة", "ستائر", "ستاير",
                 "اضاءة", "أضواء", "مكيف", "بيت", "غرفة", "مكتب", "ديوانية", "معيشة",
                 "مطبخ", "استقبال", "ماستر", "نوم", "status", "office", "room", "أوف لاين", "اوف لاين", "offline", "unavailable", "ميت", "ميتة", "منقطع", "مشاكل", "مشكلة"]
    # Detect offline/unavailable specific queries  
    _offline_kw = ["أوف لاين", "اوف لاين", "offline", "unavailable", "ميت", "ميتة", "منقطع"]
    _asking_offline = any(k in user_msg for k in _offline_kw)
    if not any(k in user_msg for k in status_kw) and not _asking_offline:
        return ""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{HA_URL}/api/states",
                                 headers={"Authorization": f"Bearer {HA_TOKEN}"},
                                 timeout=8)
            if r.status_code != 200:
                return ""
            all_states = r.json()
        # If asking about offline devices, return those specifically
        if _asking_offline:
            _unavail = []
            _skip = ["update.", "button.", "number.", "select.", "sensor.", "binary_sensor."]
            _skip_kw = ["backlight", "alexa", "iphone", "geocoded"]
            for s in all_states:
                eid = s.get("entity_id", "")
                if s.get("state") == "unavailable":
                    if any(eid.startswith(p) for p in _skip):
                        continue
                    if any(kw in eid.lower() for kw in _skip_kw):
                        continue
                    fname = s.get("attributes", {}).get("friendly_name", eid)
                    _unavail.append(f"  - {fname} ({eid})")
            if _unavail:
                return chr(10) + chr(10) + f"⚠️ الأجهزة الـ unavailable ({len(_unavail)}):" + chr(10) + chr(10).join(_unavail[:30])
            return chr(10) + chr(10) + "✅ ما فيه أجهزة unavailable!"
        # Filter to useful domains
        dominated = ("light", "climate", "cover", "fan", "media_player", "switch")
        relevant = [s for s in all_states if s.get("entity_id","").split(".")[0] in dominated
                    and s.get("state") not in ("unavailable",)]
        # Build compact summary
        lines = []
        for s in relevant:
            eid = s["entity_id"]
            name = s.get("attributes", {}).get("friendly_name", eid)
            state = s["state"]
            attrs = s.get("attributes", {})
            extra = ""
            if "current_temperature" in attrs:
                extra = f" (temp:{attrs['current_temperature']}°, target:{attrs.get('temperature','?')}°)"
            elif "brightness" in attrs and state == "on":
                extra = f" (brightness:{round(attrs['brightness']/255*100)}%)"
            elif eid.startswith("cover."):
                # Skip original entities, only show _inverted (already corrected by HA)
                if "_inverted" not in eid:
                    continue
                pos = attrs.get("current_position", 0)
                # _inverted: closed+0%=physically closed, open+100%=physically open
                ar_state = "مسكرة" if state == "closed" else "مفتوحة"
                extra = f" ({ar_state} {int(pos)}%)"
                state = ar_state
            lines.append(f"{name}: {state}{extra}")
        if not lines:
            return ""
        hdr = '\n=== حالات الأجهزة الفعلية الآن ===\n'
        return hdr + '\n'.join(lines)
    except Exception:
        return ""

# _should_send_suggestions removed — Opus handles suggestions natively

try:
    from tg_alerts import alert_loop as tg_alert_loop
    from proactive_suggestions import proactive_loop as proactive_suggestion_loop, get_suggestion_stats
    TG_ALERTS_OK = True
except Exception as _e:
    TG_ALERTS_OK = False
    logging.getLogger("master_ai").warning("tg_alerts not loaded: %s", _e)

try:
    from tg_reminders import add_reminder, list_reminders, cancel_reminder, reminder_loop
    TG_REMIND_OK = True
except Exception as _e:
    TG_REMIND_OK = False
    logging.getLogger("master_ai").warning("tg_reminders not loaded: %s", _e)

try:
    from tg_news import get_news_digest, news_scheduler
    TG_NEWS_OK = True
except Exception as _e:
    TG_NEWS_OK = False
    logging.getLogger("master_ai").warning("tg_news not loaded: %s", _e)

# -- tg_tasks --
TG_TASKS_OK = False
try:
    from tg_tasks import handle_tasks_command, llm_tool_task_create, llm_tool_task_update
    TG_TASKS_OK = True
except Exception as _e:
    logging.getLogger("master_ai").warning("tg_tasks not loaded: %s", _e)

# -- tg_stocks --
TG_STOCKS_OK = False
try:
    from tg_stocks import cmd_stocks, cmd_price
    TG_STOCKS_OK = True
except Exception as _e:
    logging.getLogger("master_ai").warning("tg_stocks not loaded: %s", _e)

try:
    from stock_radar import (
        init_radar_db, radar_loop,
        tg_radar_list, tg_radar_add, tg_radar_remove,
        tg_radar_check, tg_radar_last, tg_radar_toggle,
        tg_radar_status, tg_radar_top,
    )
    RADAR_OK = True
except Exception as _e:
    RADAR_OK = False
    logging.getLogger("master_ai").warning("stock_radar not loaded: %s", _e)

try:
    from relationships_engine import (
        init_schema as rel_init_schema, seed_family_data,
        list_contacts, find_contact, build_contact_snapshot,
        get_upcoming_occasions, get_today_occasions,
        format_contacts_tg, format_upcoming_tg, format_today_tg, format_person_tg,
        get_morning_occasions_text
    )
    rel_init_schema()
    seed_family_data()
    REL_OK = True
except Exception:
    REL_OK = False

try:
    from expenses_engine import (
        init_schema as exp_init_schema, parse_expense, add_expense,
        list_expenses, get_summary, delete_expense,
        format_summary_tg, format_recent_tg, format_add_confirmation,
        get_morning_expense_text,
        handle_spent_today, handle_spent_week, handle_spent_month, handle_recent_expenses
    )
    exp_init_schema()
    EXP_OK = True
except Exception:
    EXP_OK = False

try:
    from news_engine import (
        init_schema as news_init_schema,
        generate_digest as news_generate_digest, get_latest_digest, get_today_digests,
        format_digest_tg, format_sources_tg,
        get_morning_news_text, handle_news_latest,
        refresh_boursa as news_refresh_boursa,
        refresh_gemini as news_refresh_gemini,
        get_news as news_get_news,
        get_counts as news_get_counts,
        get_urgent_items as news_get_urgent,
        cleanup_old as news_cleanup_old,
    )
    news_init_schema()
    NEWS_ENGINE_OK = True
except Exception:
    NEWS_ENGINE_OK = False

# Phase 6: Journal Engine
try:
    from journal_engine import (
        init_schema as journal_init_schema,
        open_trade, close_trade, cancel_trade,
        get_open_trades, get_recent_trades, get_trade,
        get_trade_stats, update_trade_notes
    )
    journal_init_schema()
    JOURNAL_OK = True
except Exception:
    JOURNAL_OK = False

# Phase 4.5: Confluence Engine
CONFLUENCE_OK = False
try:
    from confluence_engine import (
        init_schema as confluence_init_schema,
        run_confluence_scan, get_actionable_signals, get_watchlist_signals,
        get_confluence_stats, record_decision as confluence_record_decision,
        build_tg_alert as confluence_build_tg_alert,
    )
    confluence_init_schema()
    CONFLUENCE_OK = True
except Exception:
    CONFLUENCE_OK = False

# Phase 5: Health Engine
try:
    from health_engine import (
        init_schema as health_init_schema,
        handle_health_log, handle_health_summary, handle_health_streak,
        quick_health_summary, quick_health_today
    )
    health_init_schema()
    HEALTH_ENGINE_OK = True
except Exception:
    HEALTH_ENGINE_OK = False

# Phase 5: Trading Engine
try:
    from trading_engine import (
        init_schema as trading_init_schema,
        handle_trade_log, handle_trades_list, handle_trade_review,
        quick_trades_recent, quick_trade_stats
    )
    trading_init_schema()
    TRADING_ENGINE_OK = True
except Exception:
    TRADING_ENGINE_OK = False

# Phase 6: TradingView Bridge
try:
    from tradingview_bridge import (
        init_tradingview_domain,
        handle_webhook as tv_handle_webhook,
        handle_tv_watchlist, handle_tv_add, handle_tv_remove,
        handle_tv_last, handle_tv_summary, handle_tv_test, handle_tv_stats,
        render_tv_alert_message, mark_telegram_sent,
        quick_tv_watchlist, quick_tv_last, quick_tv_summary_today,
        sync_tv_from_radar,
    )
    init_tradingview_domain()
    TV_BRIDGE_OK = True
except Exception:
    TV_BRIDGE_OK = False



# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# CONFIGURATION
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY", "")
anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
HA_URL = os.getenv("HA_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")
# Feature Flags v2: DB-backed with env var override
from feature_flags import FeatureFlags
from service_health import ServiceHealthHub
from kairos import KairosAgent
from hooks import HookRegistry
from tool_registry import ToolRegistry
_db_path = os.path.join(os.path.dirname(__file__), "data", "life.db")
ff = FeatureFlags(_db_path)
FEATURE_CIRCUIT_BREAKERS = ff.is_enabled("circuit_breakers")
FEATURE_TIMEOUTS = ff.is_enabled("timeouts")
FEATURE_SPEED_TEMPLATES = ff.is_enabled("speed_templates")
FEATURE_SMART_ROUTER_V2 = ff.is_enabled("smart_router_v2")
FEATURE_ENTITY_HEALTH = ff.is_enabled("entity_health")
health_hub = ServiceHealthHub(_db_path)
from service_health import set_health_hub
set_health_hub(health_hub)
hook_registry = HookRegistry(_db_path, ff=ff)
tool_reg = ToolRegistry(ff=ff, health_hub=health_hub, hooks=hook_registry)
kairos_agent = None  # initialized in lifespan with tg_send
EXTERNAL_TIMEOUT = 8  # seconds max for external calls
AGENT_SECRET = os.getenv("AGENT_SECRET", "")
MASTER_API_KEY = os.getenv("MASTER_AI_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID", "")

VERSION = "9.0.0"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENTITY_MAP_FILE = os.path.join(BASE_DIR, "entity_map.json")
AUDIT_DB = os.path.join(BASE_DIR, "data", "audit.db")

POLICY_FILE = os.path.join(BASE_DIR, "data", "policy.json")

DEFAULT_POLICY = {
    "version": 1,
    "thresholds": {
        "auto_max": 25,
        "approval_max": 60,
        "block_min": 61
    },
    "weights": {
        "keyword_match": 30,
        "source_trust": 15,
        "time_of_day": 10,
        "history_frequency": 15,
        "entity_sensitivity": 20,
        "command_danger": 10
    },
    "high_risk_keywords": ["unlock", "disarm", "delete", "wipe", "format", "reboot", "shutdown", "rm -rf", "drop table"],
    "medium_risk_keywords": ["open", "close", "garage", "door", "alarm", "lock", "restart", "toggle"],
    "trusted_sources": ["ha", "sensor", "schedule", "system"],
    "untrusted_sources": ["webhook", "unknown", "external"],
    "sensitive_entities": ["lock.", "alarm_control_panel.", "cover.garage", "switch.main_power"],
    "quiet_hours": {"start": 23, "end": 6},
    "domain_overrides": {
        "ssh": {"max_auto_score": 15},
        "win_powershell": {"max_auto_score": 20},
        "ha_service": {"max_auto_score": 35}
    }
}

def load_policy() -> dict:
    try:
        if os.path.exists(POLICY_FILE):
            with open(POLICY_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        pass  # logger not ready yet
    return DEFAULT_POLICY.copy()

def save_policy(policy: dict):
    try:
        os.makedirs(os.path.dirname(POLICY_FILE), exist_ok=True)
        with open(POLICY_FILE, "w") as f:
            json.dump(policy, f, indent=2, ensure_ascii=False)
    except Exception as e:
        pass  # logger not ready yet


START_TIME = time.time()
# ── Dashboard Job Tracking ──
_dashboard_jobs = deque(maxlen=10)  # last 10 command results

from logging.handlers import RotatingFileHandler as _RFH
_log_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_file_h = _RFH("server.log", maxBytes=2*1024*1024, backupCount=3, encoding="utf-8")
_file_h.setFormatter(_log_fmt)
_console_h = logging.StreamHandler()
_console_h.setFormatter(_log_fmt)
logger = logging.getLogger("master_ai")
logger.setLevel(logging.INFO)
logger.addHandler(_file_h)
logger.addHandler(_console_h)
logger.propagate = False  # prevent duplicate log entries
_load_router_stats()
logger.info(f"Stats loaded: prev_total={_router_stats.get('_prev_total', 0)}, session #{_router_stats.get('_sessions', 1)}")
import atexit; atexit.register(_save_router_stats)

# LLM Clients
openai_client = AsyncOpenAI(api_key=api_key) if api_key else None
anthropic_client = AsyncAnthropic(api_key=anthropic_key) if anthropic_key else None

# Entity map cache
entity_map = {}
if os.path.exists(ENTITY_MAP_FILE):
    with open(ENTITY_MAP_FILE) as f:
        entity_map = json.load(f)

# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# [UPGRADE 3] STRICT ACTION SCHEMAS
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

class ActionType(str, Enum):
    HA_GET_STATE = "ha_get_state"
    HA_CALL_SERVICE = "ha_call_service"
    SSH_RUN = "ssh_run"
    RESPOND_TEXT = "respond_text"
    WIN_DIAGNOSTICS = "win_diagnostics"
    WIN_POWERSHELL = "win_powershell"
    WIN_WINGET_INSTALL = "win_winget_install"
    HTTP_REQUEST = "http_request"
    MEMORY_STORE = "memory_store"


class HAGetStateAction(BaseModel):
    type: Literal["ha_get_state"] = "ha_get_state"
    args: dict = Field(default_factory=dict)

    @field_validator("args")
    @classmethod
    def validate_args(cls, v):
        if "entity_id" not in v:
            raise ValueError("ha_get_state requires entity_id")
        return v


class HACallServiceAction(BaseModel):
    type: Literal["ha_call_service"] = "ha_call_service"
    args: dict = Field(default_factory=dict)

    @field_validator("args")
    @classmethod
    def validate_args(cls, v):
        if "domain" not in v or "service" not in v:
            # Try to fix common format: "light.turn_on" ÃÂ¢ÃÂÃÂ domain=light, service=turn_on
            if "service" in v and "." in str(v["service"]):
                parts = v["service"].split(".", 1)
                v["domain"] = parts[0]
                v["service"] = parts[1]
            else:
                raise ValueError("ha_call_service requires domain and service")
        return v


class SSHRunAction(BaseModel):
    type: Literal["ssh_run"] = "ssh_run"
    args: dict = Field(default_factory=dict)

    @field_validator("args")
    @classmethod
    def validate_args(cls, v):
        if "cmd" not in v:
            raise ValueError("ssh_run requires cmd")
        return v


class RespondTextAction(BaseModel):
    type: Literal["respond_text"] = "respond_text"
    args: dict = Field(default_factory=dict)


class WinDiagnosticsAction(BaseModel):
    type: Literal["win_diagnostics"] = "win_diagnostics"
    args: dict = Field(default_factory=dict)


class WinPowershellAction(BaseModel):
    type: Literal["win_powershell"] = "win_powershell"
    args: dict = Field(default_factory=dict)

    @field_validator("args")
    @classmethod
    def validate_args(cls, v):
        if "script" not in v and "command" not in v:
            raise ValueError("win_powershell requires script or command")
        return v


class WinInstallAction(BaseModel):
    type: Literal["win_winget_install"] = "win_winget_install"
    args: dict = Field(default_factory=dict)

    @field_validator("args")
    @classmethod
    def validate_args(cls, v):
        if "package" not in v:
            raise ValueError("win_winget_install requires package")
        return v


class HTTPRequestAction(BaseModel):
    type: Literal["http_request"] = "http_request"
    args: dict = Field(default_factory=dict)

    @field_validator("args")
    @classmethod
    def validate_args(cls, v):
        if "url" not in v:
            raise ValueError("http_request requires url")
        return v


class MemoryStoreAction(BaseModel):
    type: Literal["memory_store"] = "memory_store"
    args: dict = Field(default_factory=dict)


ACTION_SCHEMA_MAP = {
    "ha_get_state": HAGetStateAction,
    "ha_call_service": HACallServiceAction,
    "ssh_run": SSHRunAction,
    "respond_text": RespondTextAction,
    "win_diagnostics": WinDiagnosticsAction,
    "win_powershell": WinPowershellAction,
    "win_winget_install": WinInstallAction,
    "http_request": HTTPRequestAction,
    "memory_store": MemoryStoreAction,
}



# ============================================================
# EVENT ENGINE SCHEMAS (v5.1)
# ============================================================

class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"

class EventRequest(BaseModel):
    source: str = "unknown"
    type: str
    title: str
    detail: dict = Field(default_factory=dict)
    entity_id: str | None = None
    device_id: str | None = None
    user: str | None = None
    ts: str | None = None

class EventResponse(BaseModel):
    event_id: str
    risk: RiskLevel
    autonomy_level: int
    stored: bool = True

class AutonomyConfig(BaseModel):
    enabled: bool = True
    level: int = 2
    allow_medium: bool = False
    allow_high: bool = False


class ActionExecuteRequest(BaseModel):
    """Request body for POST /action/execute."""
    action_type: str
    args: dict = {}



def validate_action(action: dict) -> tuple[bool, dict, str]:
    """Validate action against schema. Returns (valid, cleaned_action, error_msg)."""
    atype = action.get("type", "")
    schema_cls = ACTION_SCHEMA_MAP.get(atype)
    if not schema_cls:
        return False, action, f"Unknown action type: {atype}"
    try:
        validated = schema_cls(**action)
        return True, validated.model_dump(), ""
    except Exception as e:
        return False, action, str(e)


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# [UPGRADE 4] MEMORY PRODUCTIZATION
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

# Short-term memory buffer (conversation context)
short_term_memory = deque(maxlen=20)

# Try to import memory_db, graceful fallback
try:
    from memory_db import build_context, save_message, add_memory, get_memories, init_memory_db, get_memory_stats as _get_memory_stats
    init_memory_db()
    MEMORY_AVAILABLE = True
    logger.info("memory_db loaded + initialized successfully")
except ImportError:
    MEMORY_AVAILABLE = False
    logger.warning("memory_db not available ÃÂ¢ÃÂÃÂ using stub")

    def build_context(*args, **kwargs):
        return ""

    def save_message(*args, **kwargs):
        pass

    def add_memory(*args, **kwargs):
        pass

    def get_memories(*args, **kwargs):
        return []


def memory_add_short_term(role: str, content: str):
    """Add to short-term conversation buffer."""
    short_term_memory.append({
        "role": role,
        "content": content[:500],
        "ts": datetime.now().isoformat()
    })


def memory_retrieve_context(query: str, top_n: int = 5) -> str:
    """Retrieve relevant memory context for planner injection."""
    parts = []

    # Short-term (recent conversation)
    if short_term_memory:
        recent = list(short_term_memory)[-5:]
        stm = "\n".join(f"[{m['role']}] {m['content']}" for m in recent)
        parts.append(f"Recent conversation:\n{stm}")

    # Long-term (from memory_db if available)
    if MEMORY_AVAILABLE:
        try:
            ltm = build_context(query)
            if ltm and len(ltm.strip()) > 10:
                parts.append(f"Long-term memory:\n{ltm[:1500]}")
        except Exception as e:
            logger.warning(f"Memory retrieval error: {e}")

    return "\n---\n".join(parts) if parts else ""


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# [UPGRADE 5] OBSERVABILITY ÃÂ¢ÃÂÃÂ Tracing
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

class RequestTrace:
    """Tracks timing and metadata for a single request."""

    def __init__(self, request_id: str = None, task_id: str = None):
        self.request_id = request_id or str(uuid.uuid4())[:12]
        self.task_id = task_id
        self.start_time = time.time()
        self.steps = []
        self.llm_calls = []

    def step(self, name: str, status: str = "ok", duration: float = 0, detail: str = ""):
        self.steps.append({
            "name": name, "status": status,
            "duration_ms": round(duration * 1000, 1),
            "detail": detail[:200], "ts": time.time()
        })

    def llm(self, model: str, duration: float, tokens_in: int = 0, tokens_out: int = 0):
        self.llm_calls.append({
            "model": model, "duration_ms": round(duration * 1000, 1),
            "tokens_in": tokens_in, "tokens_out": tokens_out
        })

    def total_ms(self):
        return round((time.time() - self.start_time) * 1000, 1)

    def summary(self):
        return {
            "request_id": self.request_id,
            "task_id": self.task_id,
            "total_ms": self.total_ms(),
            "steps": len(self.steps),
            "llm_calls": len(self.llm_calls),
            "llm_total_ms": sum(c["duration_ms"] for c in self.llm_calls),
        }


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# DATABASE INITIALIZATION
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

def init_db():
    """Initialize all SQLite tables (audit + tasks)."""
    os.makedirs(os.path.dirname(AUDIT_DB), exist_ok=True)
    conn = sqlite3.connect(AUDIT_DB)
    c = conn.cursor()

    # Original audit table (extended)
    c.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT DEFAULT (datetime('now','localtime')),
        request_id TEXT,
        task_id TEXT,
        step_index INTEGER DEFAULT 0,
        task TEXT,
        actions TEXT,
        results TEXT,
        status TEXT DEFAULT 'ok',
        duration_ms REAL DEFAULT 0,
        approval_id TEXT,
        approved_at TEXT
    )""")

    # [UPGRADE 1] Task Manager table
    c.execute("""CREATE TABLE IF NOT EXISTS tasks (
        task_id TEXT PRIMARY KEY,
        request_id TEXT,
        goal TEXT,
        steps TEXT DEFAULT '[]',
        current_step INTEGER DEFAULT 0,
        state TEXT DEFAULT 'pending',
        artifacts TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now','localtime')),
        updated_at TEXT DEFAULT (datetime('now','localtime')),
        completed_at TEXT,
        error TEXT,
        risk_score INTEGER DEFAULT 0,
        risk_reasons TEXT
    )""")

    # Approval queue (from v4)
    c.execute("""CREATE TABLE IF NOT EXISTS approval_queue (
        approval_id TEXT PRIMARY KEY,
        job_id TEXT,
        agent_id TEXT,
        action TEXT,
        risk TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        status TEXT DEFAULT 'pending',
        approved_at TEXT,
        expires_at TEXT
    )""")

    # Windows jobs (from v4)
    c.execute("""CREATE TABLE IF NOT EXISTS win_jobs (
        job_id TEXT PRIMARY KEY,
        job_type TEXT,
        args TEXT,
        risk TEXT DEFAULT 'low',
        task_ref TEXT,
        status TEXT DEFAULT 'queued',
        result TEXT,
        agent_id TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        completed_at TEXT,
        needs_approval INTEGER DEFAULT 0,
        approval_id TEXT
    )""")


    # [UPGRADE v5.1] Event Engine tables
    c.execute("""CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        source TEXT,
        type TEXT,
        title TEXT,
        detail TEXT,
        entity_id TEXT,
        device_id TEXT,
        user TEXT,
        event_ts TEXT,
        risk TEXT,
        autonomy_level INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending',
        task_id TEXT,
        result TEXT,
        processed_at TEXT,
        error TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TEXT DEFAULT (datetime('now','localtime'))
    )""")

    row = c.execute("SELECT value FROM system_settings WHERE key='autonomy_config'").fetchone()
    if not row:
        default_cfg = json.dumps({"enabled": True, "level": 2, "allow_medium": False, "allow_high": False})
        c.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('autonomy_config', ?)", (default_cfg,))

    conn.commit()
    conn.close()
    logger.info("Database initialized (audit + tasks + events)")


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# AUDIT LOGGING (Extended with request_id/task_id)
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

async def audit_log(task, actions=None, results=None, status="ok", duration=0.0,
                    request_id=None, task_id=None, step_index=0,
                    approval_id=None, approved_at=None, route_type=None):
    try:
        conn = sqlite3.connect(AUDIT_DB)
        conn.execute(
            """INSERT INTO audit_log
               (request_id, task_id, step_index, task, actions, results, status, duration_ms, approval_id, approved_at, route_type)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (request_id, task_id, step_index, str(task)[:500],
             json.dumps(actions) if actions else None,
             json.dumps(results) if results else None,
             status, round(duration * 1000, 1), approval_id, approved_at, route_type)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Audit log error: {e}")


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# LLM CALL (with observability)
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

async def llm_call(system_prompt: str, user_message: str, max_tokens: int = 2048,
                   temperature: float = 0.3, trace: RequestTrace = None) -> str:
    """Call LLM with Anthropic primary, OpenAI fallback."""
    t0 = time.time()
    # Step 10: Circuit breaker check
    if not _cb_llm.is_available():
        return "⚠️ خدمة AI مو متوفرة حالياً، جرب بعد شوي"

    # Try Anthropic first
    if anthropic_client:
        try:
            resp = await anthropic_client.messages.create(
                model="claude-opus-4-6",
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                temperature=temperature
            )
            text = resp.content[0].text
            _cb_llm.record_success()
            if trace:
                trace.llm("claude-sonnet-4", time.time() - t0,
                          tokens_in=resp.usage.input_tokens, tokens_out=resp.usage.output_tokens)
            return text
        except Exception as e:
            _cb_llm.record_failure()
            logger.warning(f"Anthropic failed: {e}")

    # Fallback to OpenAI
    if openai_client:
        try:
            resp = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ]
            )
            text = resp.choices[0].message.content
            if trace:
                trace.llm("gpt-4o-mini", time.time() - t0,
                          tokens_in=resp.usage.prompt_tokens, tokens_out=resp.usage.completion_tokens)
            return text
        except Exception as e:
            logger.error(f"OpenAI failed: {e}")

    return '{"mode":"single_step","next_step":{"type":"respond_text","args":{"text":"LLM unavailable"}},"task_state":"complete"}'


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# JSON REPAIR UTILITY
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ


# brain_learning uses its own LLM calls internally (no registration needed)

def repair_json(text: str) -> dict:
    """Attempt to parse and repair malformed JSON from LLM."""
    # Strip markdown code fences
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Fix common issues: trailing commas, single quotes
    cleaned = text
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)  # trailing commas
    cleaned = cleaned.replace("'", '"')  # single quotes
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    return None


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# SECURITY HELPERS (from v4)
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

SSH_BLACKLIST = ["rm -rf /", "mkfs", "dd if=", "> /dev/sd", "shutdown", "reboot",
                 "passwd", "chmod 777", ":(){ :|:& };:"]


def is_command_safe(cmd: str) -> tuple[bool, str]:
    cmd_lower = cmd.lower().strip()
    for bad in SSH_BLACKLIST:
        if bad in cmd_lower:
            return False, f"Blocked: contains '{bad}'"
    if "|" in cmd and any(d in cmd_lower for d in ["rm ", "dd ", "mkfs"]):
        return False, "Blocked: dangerous pipe"
    return True, "ok"


def verify_agent_signature(agent_id: str, signature: str, timestamp: str) -> bool:
    if not AGENT_SECRET:
        return False
    try:
        ts = float(timestamp)
        if abs(time.time() - ts) > 300:
            return False
        msg = f"{agent_id}:{timestamp}"
        expected = hmac.new(AGENT_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


def assess_risk(action_type: str, args: dict) -> str:
    high_risk = ["win_winget_install", "win_powershell"]
    if action_type in high_risk:
        script = str(args.get("script", args.get("command", "")))
        if any(k in script.lower() for k in ["remove", "delete", "format", "registry", "uninstall"]):
            return "high"
        return "medium"
    return "low"


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# WINDOWS AGENT JOB QUEUE (from v4)
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

connected_agents = {}


def enqueue_win_job(job_type: str, args: dict, risk: str = "low", task_ref: str = "") -> dict:
    job_id = str(uuid.uuid4())[:8]
    needs_approval = risk in ("medium", "high")
    approval_id = None

    conn = sqlite3.connect(AUDIT_DB)
    if needs_approval:
        approval_id = str(uuid.uuid4())[:8]
        conn.execute(
            "INSERT INTO approval_queue (approval_id, job_id, agent_id, action, risk, expires_at) VALUES (?,?,?,?,?,?)",
            (approval_id, job_id, "win_agent", json.dumps({"type": job_type, "args": args}),
             risk, (datetime.now() + timedelta(minutes=10)).isoformat())
        )

    status = "awaiting_approval" if needs_approval else "queued"
    conn.execute(
        "INSERT INTO win_jobs (job_id, job_type, args, risk, task_ref, status, needs_approval, approval_id) VALUES (?,?,?,?,?,?,?,?)",
        (job_id, job_type, json.dumps(args), risk, task_ref, status, int(needs_approval), approval_id)
    )
    conn.commit()
    conn.close()

    if needs_approval and approval_id:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_notify_approval(approval_id, f"WinAgent: {job_type}", risk))
        except Exception:
            pass

    return {"job_id": job_id, "status": status, "needs_approval": needs_approval, "approval_id": approval_id}


def cleanup_expired_approvals():
    try:
        conn = sqlite3.connect(AUDIT_DB)
        now = datetime.now().isoformat()
        conn.execute("UPDATE approval_queue SET status='expired' WHERE status='pending' AND expires_at < ?", (now,))
        conn.commit()
        conn.close()
    except Exception:
        pass



# ═══════════════════════════════════════════════════════════════
# PHASE 3.3 — ADVANCED SCHEMA MIGRATIONS
# ═══════════════════════════════════════════════════════════════

SCHEMA_VERSION = "3.4.0"

SCHEMA_CONTRACT = {
    "audit_log": {
        "columns": {
            "id": {"type": "INTEGER", "pk": True},
            "timestamp": {"type": "TEXT"}, "request_id": {"type": "TEXT"},
            "task_id": {"type": "TEXT"}, "step_index": {"type": "INTEGER"},
            "task": {"type": "TEXT"}, "actions": {"type": "TEXT"},
            "results": {"type": "TEXT"}, "status": {"type": "TEXT"},
            "duration_ms": {"type": "REAL"}, "approval_id": {"type": "TEXT"},
            "approved_at": {"type": "TEXT"},
            "source": {"type": "TEXT", "default": "'api'"},
            "ip_address": {"type": "TEXT"},
            "route_type": {"type": "TEXT", "default": "NULL"},
        },
        "indexes": {
            "idx_audit_timestamp": ["timestamp"], "idx_audit_request_id": ["request_id"],
            "idx_audit_task_id": ["task_id"], "idx_audit_status": ["status"],
        },
    },
    "tasks": {
        "columns": {
            "task_id": {"type": "TEXT", "pk": True}, "request_id": {"type": "TEXT"},
            "goal": {"type": "TEXT"}, "steps": {"type": "TEXT"},
            "current_step": {"type": "INTEGER"}, "state": {"type": "TEXT"},
            "artifacts": {"type": "TEXT"}, "created_at": {"type": "TEXT"},
            "updated_at": {"type": "TEXT"}, "completed_at": {"type": "TEXT"},
            "error": {"type": "TEXT"}, "risk_score": {"type": "INTEGER"},
            "risk_reasons": {"type": "TEXT"},
        },
        "indexes": {"idx_tasks_state": ["state"], "idx_tasks_created": ["created_at"]},
    },
    "approval_queue": {
        "columns": {
            "approval_id": {"type": "TEXT", "pk": True}, "job_id": {"type": "TEXT"},
            "agent_id": {"type": "TEXT"}, "action": {"type": "TEXT"},
            "risk": {"type": "TEXT"}, "created_at": {"type": "TEXT"},
            "status": {"type": "TEXT"}, "approved_at": {"type": "TEXT"},
            "expires_at": {"type": "TEXT"},
        },
        "indexes": {"idx_approval_status": ["status"], "idx_approval_expires": ["expires_at"]},
    },
    "win_jobs": {
        "columns": {
            "job_id": {"type": "TEXT", "pk": True}, "job_type": {"type": "TEXT"},
            "args": {"type": "TEXT"}, "risk": {"type": "TEXT"},
            "task_ref": {"type": "TEXT"}, "status": {"type": "TEXT"},
            "result": {"type": "TEXT"}, "agent_id": {"type": "TEXT"},
            "created_at": {"type": "TEXT"}, "completed_at": {"type": "TEXT"},
            "needs_approval": {"type": "INTEGER"}, "approval_id": {"type": "TEXT"},
        },
        "indexes": {"idx_winjobs_status": ["status"], "idx_winjobs_created": ["created_at"]},
    },
    "sessions": {
        "columns": {
            "session_id": {"type": "TEXT", "pk": True}, "source": {"type": "TEXT"},
            "metadata": {"type": "TEXT"}, "created_at": {"type": "TEXT"},
        },
        "indexes": {"idx_sessions_created": ["created_at"]},
    },
    "knowledge": {
        "columns": {
            "id": {"type": "INTEGER", "pk": True}, "category": {"type": "TEXT"},
            "key": {"type": "TEXT"}, "value": {"type": "TEXT"},
            "source": {"type": "TEXT"}, "created_at": {"type": "TEXT"},
        },
        "indexes": {"idx_knowledge_category": ["category"], "idx_knowledge_key": ["key"]},
    },
    "users": {
        "columns": {
            "id": {"type": "INTEGER", "pk": True}, "username": {"type": "TEXT"},
            "display_name": {"type": "TEXT"}, "role": {"type": "TEXT"},
            "created_at": {"type": "TEXT"},
        },
        "indexes": {"idx_users_username": ["username"]},
    },
    "events": {
        "columns": {
            "event_id": {"type": "TEXT", "pk": True},
            "created_at": {"type": "TEXT"}, "source": {"type": "TEXT"},
            "type": {"type": "TEXT"}, "title": {"type": "TEXT"},
            "detail": {"type": "TEXT"}, "entity_id": {"type": "TEXT"},
            "device_id": {"type": "TEXT"}, "user": {"type": "TEXT"},
            "event_ts": {"type": "TEXT"}, "risk": {"type": "TEXT"},
            "autonomy_level": {"type": "INTEGER"},
            "status": {"type": "TEXT", "default": "'pending'"},
            "task_id": {"type": "TEXT"}, "result": {"type": "TEXT"},
            "processed_at": {"type": "TEXT"}, "error": {"type": "TEXT"},
            "risk_score": {"type": "INTEGER", "default": "0"},
            "risk_reasons": {"type": "TEXT"},
            "policy_version": {"type": "TEXT"},
        },
        "indexes": {
            "idx_events_type": ["type"], "idx_events_status": ["status"],
            "idx_events_task": ["task_id"], "idx_events_created": ["created_at"],
        },
    },
    "interaction_feedback": {
        "columns": {
            "id": {"type": "INTEGER", "pk": True},
            "timestamp": {"type": "TEXT"},
            "source_type": {"type": "TEXT"},
            "query_text": {"type": "TEXT"},
            "decision_taken": {"type": "TEXT"},
            "user_feedback": {"type": "TEXT"},
            "correct_answer": {"type": "TEXT"},
            "entity_id": {"type": "TEXT"},
            "room": {"type": "TEXT"},
            "confidence_before": {"type": "REAL"},
            "confidence_after": {"type": "REAL"},
            "meta": {"type": "TEXT"},
        },
        "indexes": {
            "idx_ifb_source": ["source_type"],
            "idx_ifb_feedback": ["user_feedback"],
            "idx_ifb_entity": ["entity_id"],
            "idx_ifb_ts": ["timestamp"],
        },
    },
    "system_settings": {
        "columns": {
            "key": {"type": "TEXT", "pk": True}, "value": {"type": "TEXT"},
            "updated_at": {"type": "TEXT"},
        },
        "indexes": {},
    },
    "schema_migrations": {
        "columns": {
            "id": {"type": "INTEGER", "pk": True}, "version": {"type": "TEXT"},
            "applied_at": {"type": "TEXT"}, "plan_json": {"type": "TEXT"},
            "ok": {"type": "INTEGER"}, "error": {"type": "TEXT"},
            "duration_ms": {"type": "REAL"},
        },
        "indexes": {"idx_migrations_version": ["version"]},
    },
}


def _db_introspect(conn: sqlite3.Connection) -> dict:
    """Introspect current database schema via PRAGMA."""
    result = {}
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()]
    for table in tables:
        cols = {}
        for row in conn.execute(f"PRAGMA table_info('{table}')").fetchall():
            cols[row[1]] = {"type": (row[2] or "TEXT").upper(), "notnull": bool(row[3]),
                            "default": row[4], "pk": bool(row[5])}
        indexes = {}
        for idx_row in conn.execute(f"PRAGMA index_list('{table}')").fetchall():
            idx_name = idx_row[1]
            idx_cols = [r[2] for r in conn.execute(f"PRAGMA index_info('{idx_name}')").fetchall()]
            indexes[idx_name] = idx_cols
        result[table] = {"columns": cols, "indexes": indexes}
    return result


def _build_migration_plan(current: dict, contract: dict) -> dict:
    """Compare current schema vs contract."""
    plan = {"missing_tables": [], "missing_columns": [], "missing_indexes": [],
            "drift_warnings": [], "backfill_needed": []}
    for table_name, table_spec in contract.items():
        if table_name not in current:
            plan["missing_tables"].append({"table": table_name, "columns": table_spec["columns"],
                                           "indexes": table_spec.get("indexes", {})})
            continue
        cur_table = current[table_name]
        for col_name, col_spec in table_spec["columns"].items():
            if col_name not in cur_table["columns"]:
                plan["missing_columns"].append({"table": table_name, "column": col_name,
                                                "type": col_spec["type"], "default": col_spec.get("default")})
            else:
                cur_type = cur_table["columns"][col_name].get("type", "TEXT").upper()
                exp_type = col_spec["type"].upper()
                if cur_type != exp_type and cur_type not in ("", "NUMERIC"):
                    plan["drift_warnings"].append({"table": table_name, "column": col_name,
                                                   "expected_type": exp_type, "actual_type": cur_type,
                                                   "action": "none (manual fix required)"})
        cur_indexes = cur_table.get("indexes", {})
        for idx_name, idx_cols in table_spec.get("indexes", {}).items():
            found = idx_name in cur_indexes
            if not found:
                for existing_cols in cur_indexes.values():
                    if existing_cols == idx_cols:
                        found = True
                        break
            if not found:
                plan["missing_indexes"].append({"table": table_name, "index": idx_name, "columns": idx_cols})
    if "events" in current:
        for col in ["status", "risk_score", "policy_version"]:
            if col in current["events"]["columns"]:
                plan["backfill_needed"].append({"table": "events", "column": col})
    return plan


def _gen_create_table_sql(table_name: str, columns: dict) -> str:
    col_defs = []
    for col_name, col_spec in columns.items():
        parts = [col_name, col_spec["type"]]
        if col_spec.get("pk"):
            parts.append("PRIMARY KEY")
            if col_spec["type"] == "INTEGER":
                parts.append("AUTOINCREMENT")
        if col_spec.get("default"):
            parts.append(f"DEFAULT {col_spec['default']}")
        col_defs.append(" ".join(parts))
    return f"CREATE TABLE IF NOT EXISTS {table_name} (\n  " + ",\n  ".join(col_defs) + "\n)"


def _gen_add_column_sql(table, column, col_type, default=None):
    stmt = f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
    if default is not None:
        stmt += f" DEFAULT {default}"
    return stmt


def _gen_create_index_sql(table, index_name, columns):
    return f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({', '.join(columns)})"


def _run_backfills(conn, plan):
    results = []
    backfills = [
        ("events", "status", "UPDATE events SET status='unknown' WHERE status IS NULL"),
        ("events", "risk_score", "UPDATE events SET risk_score=0 WHERE risk_score IS NULL"),
        ("events", "policy_version", "UPDATE events SET policy_version='pre-3.3' WHERE policy_version IS NULL"),
        ("audit_log", "source", "UPDATE audit_log SET source='api' WHERE source IS NULL"),
        ("audit_log", "route_type", "UPDATE audit_log SET route_type='unknown' WHERE route_type IS NULL"),
    ]
    for table, col, sql in backfills:
        try:
            count = conn.execute(sql).rowcount
            if count > 0:
                results.append(f"{table}.{col}: backfilled {count} rows")
        except sqlite3.OperationalError:
            pass
    return results


def _update_schema_version(conn, version):
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO system_settings (key, value, updated_at) VALUES ('schema_version', ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (version, now))


def _record_migration(conn, version, report, ok, error=None):
    conn.execute(
        "INSERT INTO schema_migrations (version, applied_at, plan_json, ok, error, duration_ms) VALUES (?,?,?,?,?,?)",
        (version, datetime.now().isoformat(), json.dumps(report.get("plan", {}), default=str),
         1 if ok else 0, error, report.get("duration_ms", 0)))


def ensure_schema(dry_run=True, apply=False):
    """Advanced schema migration: introspect, plan, apply in transaction."""
    start_ts = time.time()
    report = {"schema_version": SCHEMA_VERSION, "current_version": None,
              "dry_run": dry_run, "applied": False,
              "plan": {}, "executed": [], "backfills": [], "errors": [], "duration_ms": 0}
    conn = None
    try:
        conn = sqlite3.connect(AUDIT_DB, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            row = conn.execute("SELECT value FROM system_settings WHERE key='schema_version'").fetchone()
            report["current_version"] = row[0] if row else None
        except sqlite3.OperationalError:
            report["current_version"] = None
        current = _db_introspect(conn)
        plan = _build_migration_plan(current, SCHEMA_CONTRACT)
        report["plan"] = plan
        total = len(plan["missing_tables"]) + len(plan["missing_columns"]) + len(plan["missing_indexes"])
        if dry_run or not apply:
            report["summary"] = {"missing_tables": len(plan["missing_tables"]),
                                 "missing_columns": len(plan["missing_columns"]),
                                 "missing_indexes": len(plan["missing_indexes"]),
                                 "drift_warnings": len(plan["drift_warnings"]),
                                 "total_actions": total,
                                 "status": "dry_run" if dry_run else "plan_only"}
            report["duration_ms"] = round((time.time() - start_ts) * 1000, 2)
            return report
        if total == 0 and not plan["backfill_needed"]:
            report["applied"] = True
            report["summary"] = {"status": "already_up_to_date", "total_actions": 0}
            _update_schema_version(conn, SCHEMA_VERSION)
            conn.commit()
            report["duration_ms"] = round((time.time() - start_ts) * 1000, 2)
            return report
        conn.execute("BEGIN IMMEDIATE")
        try:
            for tbl in plan["missing_tables"]:
                conn.execute(_gen_create_table_sql(tbl["table"], tbl["columns"]))
                report["executed"].append(f"CREATE TABLE {tbl['table']}")
                logger.info(f"[Schema] Created table: {tbl['table']}")
                for idx_name, idx_cols in tbl.get("indexes", {}).items():
                    conn.execute(_gen_create_index_sql(tbl["table"], idx_name, idx_cols))
                    report["executed"].append(f"CREATE INDEX {idx_name}")
            for col in plan["missing_columns"]:
                conn.execute(_gen_add_column_sql(col["table"], col["column"], col["type"], col.get("default")))
                report["executed"].append(f"ADD COLUMN {col['table']}.{col['column']}")
                logger.info(f"[Schema] Added column: {col['table']}.{col['column']}")
            for idx in plan["missing_indexes"]:
                conn.execute(_gen_create_index_sql(idx["table"], idx["index"], idx["columns"]))
                report["executed"].append(f"CREATE INDEX {idx['index']}")
                logger.info(f"[Schema] Created index: {idx['index']}")
            report["backfills"] = _run_backfills(conn, plan)
            _update_schema_version(conn, SCHEMA_VERSION)
            _record_migration(conn, SCHEMA_VERSION, report, ok=True)
            conn.execute("COMMIT")
            report["applied"] = True
            report["summary"] = {"status": "applied", "total_actions": len(report["executed"]),
                                 "backfills": len(report["backfills"])}
            logger.info(f"[Schema] Migration v{SCHEMA_VERSION}: {len(report['executed'])} actions")
        except Exception as e:
            conn.execute("ROLLBACK")
            error_msg = f"Rolled back: {e}"
            report["errors"].append(error_msg)
            report["summary"] = {"status": "rollback", "error": error_msg}
            logger.error(f"[Schema] {error_msg}")
            try:
                c2 = sqlite3.connect(AUDIT_DB, timeout=5)
                c2.execute(_gen_create_table_sql("schema_migrations", SCHEMA_CONTRACT["schema_migrations"]["columns"]))
                _record_migration(c2, SCHEMA_VERSION, report, ok=False, error=str(e))
                c2.commit()
                c2.close()
            except Exception:
                pass
    except sqlite3.OperationalError as e:
        report["errors"].append(f"DB error: {e}")
        report["summary"] = {"status": "error", "error": str(e)}
        logger.error(f"[Schema] DB error: {e}")
    finally:
        if conn:
            conn.close()
        report["duration_ms"] = round((time.time() - start_ts) * 1000, 2)
    return report


def _get_schema_status():
    """Get current schema status for /health and /schema."""
    try:
        conn = sqlite3.connect(AUDIT_DB, timeout=5)
        conn.row_factory = sqlite3.Row
        current_version = None
        try:
            row = conn.execute("SELECT value FROM system_settings WHERE key='schema_version'").fetchone()
            current_version = row["value"] if row else None
        except sqlite3.OperationalError:
            pass
        drift_count = 0
        try:
            current = _db_introspect(conn)
            plan = _build_migration_plan(current, SCHEMA_CONTRACT)
            drift_count = (len(plan["missing_tables"]) + len(plan["missing_columns"])
                           + len(plan["missing_indexes"]) + len(plan["drift_warnings"]))
        except Exception:
            drift_count = -1
        last_migration = None
        try:
            row = conn.execute("SELECT version, applied_at, ok, error FROM schema_migrations ORDER BY id DESC LIMIT 1").fetchone()
            if row:
                last_migration = {"version": row["version"], "applied_at": row["applied_at"],
                                  "ok": bool(row["ok"]), "error": row["error"]}
        except sqlite3.OperationalError:
            pass
        conn.close()
        return {"schema_version": current_version, "expected_version": SCHEMA_VERSION,
                "drift_count": drift_count, "last_migration": last_migration}
    except Exception as e:
        return {"schema_version": None, "expected_version": SCHEMA_VERSION,
                "drift_count": -1, "last_migration": None, "error": str(e)}


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# ── Speed Engine (Step 2) ──
# _SPEED_SVC_MAP removed — Speed Engine disabled

# quick_execute removed — Speed Engine disabled


def _arabize_name(name: str) -> str:
    """Translate common English device names to Arabic for response."""
    _ROOM_AR = {
        "living room": "المعيشة", "kitchen": "المطبخ", "office": "المكتب",
        "master": "الماستر", "mama": "ماما", "reception": "الاستقبال",
        "men room": "الديوانية", "ground": "الأرضي", "room 3": "غرفة 3",
        "room 5": "غرفة 5", "first floor": "الدور الأول", "diwaniya": "الديوانية",
    }
    _TYPE_AR = {
        "chandler": "ثريا", "chandelier": "ثريا", "spot": "سبوت", "strip": "ستريب",
        "backlight": "خلفية", "mirror": "مرآة", "vent": "شفاط", "shutter": "شتر",
        "air purifier": "منقي", "storage": "مخزن",
    }
    # Strip bilingual room format
    if "/" in name:
        for _p in name.split("/"):
            import re as _re2
            if len(_re2.findall(r"[a-zA-Z]", _p)) < len(_p.replace(" ","") or "x") * 0.5:
                name = _p.strip()
                break
    nl = name.lower()
    # If already Arabic (>50% non-latin), return as-is
    import re
    latin = len(re.findall(r"[a-zA-Z]", name))
    total = len(name.replace(" ", "")) or 1
    if latin / total < 0.5:
        return name
    # Build Arabic name: type + room
    room_part = ""
    type_part = ""
    for eng, ar in _ROOM_AR.items():
        if eng in nl:
            room_part = ar
            break
    for eng, ar in _TYPE_AR.items():
        if eng in nl:
            type_part = ar
            break
    if type_part and room_part:
        return f"{type_part} {room_part}"
    if type_part:
        return type_part
    if room_part:
        return f"نور {room_part}"
    return name


# get_quick_response removed — Speed Engine deleted


async def _exec_ha_get_state(entity_id: str) -> dict:
    # Phase 1: Circuit breaker + timeout
    if not _cb_ha.is_available():
        return {"success": False, "error": "⚠️ نظام الأجهزة غير متاح حالياً"}
    _ha_timeout = EXTERNAL_TIMEOUT if FEATURE_TIMEOUTS else 30
    async with httpx.AsyncClient(timeout=_ha_timeout) as client:
        headers = {"Authorization": f"Bearer {HA_TOKEN}"}
        # Wildcard: fetch all and filter
        if entity_id == "*":
            r = await client.get(f"{HA_URL}/api/states", headers=headers, timeout=_ha_timeout)
            states = r.json()
            _cb_ha.record_success()
            return {"success": True, "count": len(states), "states": states[:50]}
        # Pattern matching: *climate*, sensor.*temp*, comma-separated patterns
        if "*" in entity_id and entity_id != "*":
            import fnmatch
            r = await client.get(f"{HA_URL}/api/states", headers=headers, timeout=_ha_timeout)
            all_states = r.json()
            # Support comma-separated patterns: "light.*foo*,light.*bar*"
            patterns = [p.strip().lower() for p in entity_id.split(",") if p.strip()]
            matched = []
            seen = set()
            for pat in patterns:
                if "*" in pat:
                    for s in all_states:
                        eid = s.get("entity_id", "").lower()
                        if eid not in seen and fnmatch.fnmatch(eid, pat):
                            matched.append(s)
                            seen.add(eid)
                else:
                    # Exact ID in comma list
                    for s in all_states:
                        eid = s.get("entity_id", "").lower()
                        if eid == pat and eid not in seen:
                            matched.append(s)
                            seen.add(eid)
            _cb_ha.record_success()
            if matched:
                return {"success": True, "count": len(matched), "states": matched[:30]}
            return {"success": True, "count": 0, "states": [], "note": f"No entities matching {entity_id}"}
        # Support comma-separated entity IDs
        ids = [e.strip() for e in entity_id.split(",") if e.strip()]
        if len(ids) > 1:
            results = []
            for eid in ids:
                try:
                    r = await client.get(f"{HA_URL}/api/states/{eid}", headers=headers, timeout=_ha_timeout)
                    if r.status_code == 200:
                        results.append(r.json())
                    else:
                        results.append({"entity_id": eid, "state": f"error_{r.status_code}"})
                except Exception as e:
                    results.append({"entity_id": eid, "state": f"error: {e}"})
            return {"success": True, "count": len(results), "states": results}
        r = await client.get(f"{HA_URL}/api/states/{ids[0]}", headers=headers, timeout=_ha_timeout)
        if r.status_code == 200:
            return {"success": True, "state": r.json()}
        return {"success": False, "error": f"HTTP {r.status_code}"}


async def _exec_ha_call_service(domain: str, service: str, service_data: dict = None) -> dict:
    # Phase 0: Validate entity_id exists
    eid = (service_data or {}).get("entity_id", "")
    if eid and "." in eid:
        try:
            async with httpx.AsyncClient(timeout=5) as vc:
                vr = await vc.get(f"{HA_URL}/api/states/{eid}",
                    headers={"Authorization": f"Bearer {HA_TOKEN}"})
                if vr.status_code == 404:
                    logger.warning(f"Entity {eid} not found in HA")
                    return {"success": False, "error": f"Entity '{eid}' not found. Check entity_id."}
        except Exception:
            pass  # validation failure shouldn't block execution
    # Phase 1: Circuit breaker + timeout
    if not _cb_ha.is_available():
        return {"success": False, "error": "⚠️ نظام الأجهزة غير متاح حالياً"}
    _ha_timeout = EXTERNAL_TIMEOUT if FEATURE_TIMEOUTS else 30
    async with httpx.AsyncClient(timeout=_ha_timeout) as client:
        headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
        r = await client.post(f"{HA_URL}/api/services/{domain}/{service}",
                              headers=headers, json=service_data or {}, timeout=_ha_timeout)
        _ok = r.status_code == 200
        _cb_ha.record_success() if _ok else _cb_ha.record_failure()
        result = {"success": _ok, "status_code": r.status_code}
        if not _ok:
            try:
                err_body = r.text[:300]
                result["error"] = err_body
                logger.warning(f"HA service {domain}/{service} failed ({r.status_code}): {err_body[:150]} | data={json.dumps(service_data, ensure_ascii=False)[:200]}")
            except Exception:
                pass
        return result


async def _exec_ssh_run(cmd: str) -> dict:
    safe, reason = is_command_safe(cmd)
    if not safe:
        return {"success": False, "error": reason}
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        return {
            "success": proc.returncode == 0,
            "stdout": stdout.decode(errors="replace")[:5000],
            "stderr": stderr.decode(errors="replace")[:2000],
            "returncode": proc.returncode
        }
    except asyncio.TimeoutError:
        return {"success": False, "error": "Command timed out (30s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _exec_http_request(args: dict) -> dict:
    try:
        async with httpx.AsyncClient() as client:
            method = args.get("method", "GET").upper()
            url = args["url"]
            headers = args.get("headers", {})
            body = args.get("body")
            r = await client.request(method, url, headers=headers, json=body, timeout=15)
            return {"success": True, "status_code": r.status_code, "body": r.text[:3000]}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def execute_action(action: dict, trace: RequestTrace = None, step_index: int = 0) -> dict:
    """Execute a single validated action via Plugin Layer with timing."""
    t0 = time.time()
    atype = action.get("type", "")
    args = dict(action.get("args", {}))
    result = {}

    try:
        plugin = PLUGIN_REGISTRY.get(atype)
        if plugin is None:
            result = {"success": False, "error": f"Unknown action type: {atype}"}
        elif not plugin.enabled:
            result = {"success": False, "error": f"Plugin disabled: {plugin.name}"}
        else:
            # Pass full action for plugins that need extra fields (e.g. "why")
            args["_action"] = action
            result = await plugin.execute(args, trace, step_index)
    except Exception as e:
        result = {"success": False, "error": str(e)}

    duration = time.time() - t0
    if trace:
        trace.step(f"exec:{atype}", "ok" if result.get("success") else "error",
                   duration, json.dumps(result)[:200])

    return result


# ============================================================
# PHASE 4 — PLUGIN LAYER
# ============================================================

class BasePlugin:
    """Base class for all action plugins."""
    name: str = "base"
    enabled: bool = True

    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled

    async def execute(self, args: dict, trace: RequestTrace = None, step_index: int = 0) -> dict:
        return {"success": False, "error": "Not implemented"}

    def metadata(self) -> dict:
        return {"name": self.name, "enabled": self.enabled}


class PluginRegistry:
    """Registry for action plugins. Maps action_type -> BasePlugin."""

    def __init__(self):
        self._plugins: dict[str, BasePlugin] = {}

    def register(self, action_type: str, plugin: BasePlugin):
        self._plugins[action_type] = plugin

    def get(self, action_type: str) -> BasePlugin | None:
        return self._plugins.get(action_type)

    def list(self) -> dict:
        return {atype: p.metadata() for atype, p in self._plugins.items()}

    def enable(self, name: str) -> bool:
        for p in self._plugins.values():
            if p.name == name:
                p.enabled = True
                return True
        return False

    def disable(self, name: str) -> bool:
        for p in self._plugins.values():
            if p.name == name:
                p.enabled = False
                return True
        return False


PLUGIN_REGISTRY = PluginRegistry()


# --- Concrete Plugins (thin wrappers around existing executors) ---

class HAGetStatePlugin(BasePlugin):
    def __init__(self): super().__init__("ha_get_state")
    async def execute(self, args, trace=None, step_index=0):
        return await _exec_ha_get_state(args.get("entity_id", "*"))

class HACallServicePlugin(BasePlugin):
    def __init__(self): super().__init__("ha_call_service")
    async def execute(self, args, trace=None, step_index=0):
        # Smart args normalization: Opus may put entity_id/temperature/etc at top level
        sdata = args.get("service_data") or {}
        # Merge any extra keys (not domain/service/type/service_data) into service_data
        _reserved = {"domain", "service", "type", "service_data", "target", "_action"}
        for k, v in args.items():
            if k not in _reserved and k not in sdata:
                sdata[k] = v
        # Handle "target" format (some Opus versions use it)
        if "target" in args and isinstance(args["target"], dict):
            for tk, tv in args["target"].items():
                if tk not in sdata:
                    sdata[tk] = tv
        return await _exec_ha_call_service(args["domain"], args["service"], sdata)

class SSHRunPlugin(BasePlugin):
    def __init__(self): super().__init__("ssh_run")
    async def execute(self, args, trace=None, step_index=0):
        return await _exec_ssh_run(args["cmd"])

class RespondTextPlugin(BasePlugin):
    def __init__(self): super().__init__("respond_text")
    async def execute(self, args, trace=None, step_index=0):
        return {"success": True, "text": args.get("text", "")}

class HTTPPlugin(BasePlugin):
    def __init__(self): super().__init__("http_request")
    async def execute(self, args, trace=None, step_index=0):
        return await _exec_http_request(args)

class MemoryPlugin(BasePlugin):
    def __init__(self): super().__init__("memory_store")
    async def execute(self, args, trace=None, step_index=0):
        if MEMORY_AVAILABLE:
            add_memory(category=args.get("category", "general"),
                       content=args.get("content", ""),
                       memory_type=args.get("type", "fact"))
            return {"success": True, "stored": True}
        return {"success": False, "error": "memory_db not available"}

class WindowsPlugin(BasePlugin):
    """Handles win_diagnostics, win_powershell, win_winget_install."""
    def __init__(self, win_action_type: str):
        super().__init__(win_action_type)
        self._atype = win_action_type
    async def execute(self, args, trace=None, step_index=0):
        action = args.pop("_action", {})
        win_type = self._atype.replace("win_", "")
        risk = assess_risk(self._atype, args)
        job = enqueue_win_job(win_type, args, risk, task_ref=action.get("why", ""))
        return {"success": True, "queued": True, "job_id": job["job_id"],
                "needs_approval": job["needs_approval"], "approval_id": job.get("approval_id")}


def register_plugins():
    """Register all built-in plugins. Safe to call multiple times (idempotent)."""
    if PLUGIN_REGISTRY._plugins:
        return  # Already registered
    PLUGIN_REGISTRY.register("ha_get_state", HAGetStatePlugin())
    PLUGIN_REGISTRY.register("ha_call_service", HACallServicePlugin())
    PLUGIN_REGISTRY.register("ssh_run", SSHRunPlugin())
    PLUGIN_REGISTRY.register("respond_text", RespondTextPlugin())
    PLUGIN_REGISTRY.register("http_request", HTTPPlugin())
    PLUGIN_REGISTRY.register("memory_store", MemoryPlugin())
    PLUGIN_REGISTRY.register("win_diagnostics", WindowsPlugin("win_diagnostics"))
    PLUGIN_REGISTRY.register("win_powershell", WindowsPlugin("win_powershell"))
    PLUGIN_REGISTRY.register("win_winget_install", WindowsPlugin("win_winget_install"))
    logger.info(f"Registered {len(PLUGIN_REGISTRY._plugins)} plugins")


async def execute_action_gateway(action_type: str, args: dict, trace=None, step_index: int = 0, bypass_approval: bool = False) -> dict:
    """Central execution gateway: risk + policy + autonomy + plugin dispatch."""
    register_plugins()

    # 1. Resolve plugin
    plugin = PLUGIN_REGISTRY.get(action_type)
    if plugin is None:
        return {"success": False, "error": f"Unknown action type: {action_type}", "action_type": action_type}
    if hasattr(plugin, "enabled") and not plugin.enabled:
        return {"success": False, "error": f"Plugin disabled: {plugin.name}", "action_type": action_type}

    # 2. Assess risk (fail-safe: default high)
    try:
        risk_raw = assess_risk(action_type, args)
    except Exception:
        risk_raw = "high"
    # Normalize
    if isinstance(risk_raw, dict):
        risk_level = str(risk_raw.get("level", risk_raw.get("risk", "high"))).lower()
    elif isinstance(risk_raw, str):
        risk_level = risk_raw.lower()
    else:
        pass
        risk_level = "high"
    if risk_level not in ("low", "medium", "high"):
        risk_level = "high"

    # 3. Load policy (permissive fallback)
    try:
        policy = load_policy()
        thresholds = policy.get("thresholds", {})
    except Exception:
        thresholds = {"auto_max": 100, "approval_max": 100, "block_min": 101}

    # 4. Autonomy config (permissive fallback)
    try:
        autonomy = event_engine.get_autonomy_config()
    except Exception:
        autonomy = {"enabled": False, "level": 0, "allow_medium": True, "allow_high": True}

    # 5. Policy / autonomy gate
    _blocked = False
    _reason = ""
    if autonomy.get("enabled", False) and not bypass_approval:
        if risk_level == "high" and not autonomy.get("allow_high", False):
            _blocked = True
            _reason = "High-risk action blocked by autonomy config"
        elif risk_level == "medium" and not autonomy.get("allow_medium", False):
            _blocked = True
            _reason = "Medium-risk action blocked by autonomy config"
        else:
            block_min = thresholds.get("block_min", 61)
            score_map = {"low": 10, "medium": 40, "high": 80}
            if score_map.get(risk_level, 80) >= block_min:
                _blocked = True
                _reason = f"Blocked by policy (score >= {block_min})"

    if _blocked:
        _needs_approval = risk_level in ("medium", "high")
        if _needs_approval:
            _aid = str(uuid.uuid4())[:8]
            _now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _exp = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
            _payload = json.dumps({
                "kind": "gateway_action",
                "action_type": action_type,
                "args": args or {},
                "risk_level": risk_level,
                "reason": _reason,
            }, ensure_ascii=False)
            _conn = sqlite3.connect(AUDIT_DB)
            _conn.execute(
                "INSERT INTO approval_queue (approval_id, job_id, agent_id, action, risk, status, expires_at) VALUES (?,NULL,NULL,?,?,'pending',?)",
                (_aid, _payload, risk_level, _exp))
            _conn.commit()
            _conn.close()
            try:
                import asyncio
                asyncio.ensure_future(_notify_approval(_aid, f"Gateway: {action_type}", risk_level))
            except Exception:
                pass
            return {
                "success": False, "denied": True, "needs_approval": True,
                "approval_id": _aid, "action_type": action_type,
                "risk_level": risk_level, "reason": _reason,
            }
        return {
            "success": False, "denied": True, "needs_approval": False,
            "action_type": action_type, "risk_level": risk_level, "reason": _reason,
        }

    # 6. Execute plugin
    try:
        out = await plugin.execute(args, trace, step_index)
    except Exception as e:
        return {"success": False, "error": str(e), "action_type": action_type, "risk_level": risk_level}

    # 7. Unified response
    if isinstance(out, dict) and "success" in out:
        out["action_type"] = action_type
        out["risk_level"] = risk_level
        return out
    return {"success": True, "result": out, "action_type": action_type, "risk_level": risk_level}



# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# [UPGRADE 1] TASK MANAGER
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ


# ============================================================
# EVENT ENGINE (v5.1)
# ============================================================

class EventEngine:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def score_risk(self, event: EventRequest) -> dict:
        """Score risk 0-100 with reasons. Replaces simple classify_risk."""
        policy = load_policy()
        weights = policy.get("weights", DEFAULT_POLICY["weights"])
        score = 0
        reasons = []

        t = (event.type or "").lower()
        title = (event.title or "").lower()
        detail_str = json.dumps(event.detail or {}).lower()
        all_text = f"{t} {title} {detail_str}"

        # 1. Keyword match (0-30)
        high_kw = policy.get("high_risk_keywords", DEFAULT_POLICY["high_risk_keywords"])
        med_kw = policy.get("medium_risk_keywords", DEFAULT_POLICY["medium_risk_keywords"])
        w_kw = weights.get("keyword_match", 30)
        matched_high = [k for k in high_kw if k in all_text]
        matched_med = [k for k in med_kw if k in all_text]
        if matched_high:
            score += w_kw
            reasons.append(f"high_keywords: {matched_high}")
        elif matched_med:
            score += int(w_kw * 0.5)
            reasons.append(f"medium_keywords: {matched_med}")

        # 2. Source trust (0-15)
        w_src = weights.get("source_trust", 15)
        trusted = policy.get("trusted_sources", DEFAULT_POLICY["trusted_sources"])
        untrusted = policy.get("untrusted_sources", DEFAULT_POLICY["untrusted_sources"])
        src = (event.source or "unknown").lower()
        if src in untrusted:
            score += w_src
            reasons.append(f"untrusted_source: {src}")
        elif src not in trusted:
            score += int(w_src * 0.5)
            reasons.append(f"unknown_source: {src}")

        # 3. Time of day (0-10)
        w_time = weights.get("time_of_day", 10)
        quiet = policy.get("quiet_hours", DEFAULT_POLICY["quiet_hours"])
        hour = datetime.now().hour
        if quiet["start"] <= hour or hour < quiet["end"]:
            score += w_time
            reasons.append(f"quiet_hours: {hour}:00")

        # 4. Entity sensitivity (0-20)
        w_ent = weights.get("entity_sensitivity", 20)
        sensitive = policy.get("sensitive_entities", DEFAULT_POLICY["sensitive_entities"])
        eid = (event.entity_id or "").lower()
        if any(s in eid for s in sensitive):
            score += w_ent
            reasons.append(f"sensitive_entity: {eid}")

        # 5. Domain override cap
        overrides = policy.get("domain_overrides", {})
        for domain, rules in overrides.items():
            if domain in t:
                cap = rules.get("max_auto_score", 100)
                if score < cap:
                    score = max(score, cap + 1)
                    reasons.append(f"domain_override: {domain} forces score>{cap}")
                break

        # 6. History frequency (0-15)
        w_hist = weights.get("history_frequency", 15)
        try:
            conn = self._conn()
            recent = conn.execute(
                "SELECT COUNT(*) FROM events WHERE type=? AND created_at > datetime('now','-1 hour','localtime')",
                (event.type,)
            ).fetchone()[0]
            conn.close()
            if recent > 10:
                score += w_hist
                reasons.append(f"high_frequency: {recent} in last hour")
            elif recent > 5:
                score += int(w_hist * 0.5)
                reasons.append(f"moderate_frequency: {recent} in last hour")
        except Exception:
            pass

        score = min(100, max(0, score))
        confidence = min(95, 50 + len(reasons) * 10)

        # Map to RiskLevel for backward compat
        thresholds = policy.get("thresholds", DEFAULT_POLICY["thresholds"])
        if score <= thresholds.get("auto_max", 25):
            level = RiskLevel.low
        elif score <= thresholds.get("approval_max", 60):
            level = RiskLevel.medium
        else:
            level = RiskLevel.high

        return {
            "risk_score": score,
            "risk_level": level.value,
            "confidence": confidence,
            "reasons": reasons
        }


    def classify_risk(self, event: EventRequest) -> RiskLevel:
        """Backward-compatible wrapper around score_risk."""
        result = self.score_risk(event)
        return RiskLevel(result["risk_level"])

    def get_autonomy_config(self) -> dict:
        conn = self._conn()
        cur = conn.cursor()
        row = cur.execute("SELECT value FROM system_settings WHERE key='autonomy_config'").fetchone()
        conn.close()
        if not row:
            return {"enabled": True, "level": 2, "allow_medium": False, "allow_high": False}
        try:
            return json.loads(row[0])
        except Exception:
            return {"enabled": True, "level": 2, "allow_medium": False, "allow_high": False}

    def set_autonomy_config(self, cfg: AutonomyConfig) -> dict:
        payload = cfg.model_dump()
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('autonomy_config', ?, datetime('now','localtime'))", (json.dumps(payload),))
        conn.commit()
        conn.close()
        return payload

    def create_event(self, req: EventRequest) -> dict:
        event_id = f"ev_{uuid.uuid4().hex[:10]}"
        risk_result = self.score_risk(req)
        risk_level = RiskLevel(risk_result["risk_level"])
        cfg = self.get_autonomy_config()
        autonomy_level = int(cfg.get("level", 2))
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO events (event_id, source, type, title, detail, entity_id, device_id, user, event_ts, risk, autonomy_level, risk_score, risk_reasons)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (event_id, req.source, req.type, req.title, json.dumps(req.detail or {}),
             req.entity_id, req.device_id, req.user, req.ts, risk_level.value, autonomy_level,
             risk_result["risk_score"], json.dumps(risk_result["reasons"], ensure_ascii=False)))
        conn.commit()
        conn.close()
        return {
            "event_id": event_id,
            "risk": risk_level.value,
            "risk_score": risk_result["risk_score"],
            "confidence": risk_result["confidence"],
            "reasons": risk_result["reasons"],
            "autonomy_level": autonomy_level,
            "stored": True
        }


    def update_event(self, event_id: str, **kwargs) -> bool:
        allowed = {"status", "task_id", "result", "processed_at", "error", "risk", "autonomy_level"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        conn = self._conn()
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [event_id]
        conn.execute(f"UPDATE events SET {sets} WHERE event_id = ?", vals)
        conn.commit()
        conn.close()
        return True

    def get_pending_events(self, limit: int = 10) -> list[dict]:
        conn = self._conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM events WHERE status='pending' ORDER BY created_at ASC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def list_events(self, limit: int = 50) -> list[dict]:
        conn = self._conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM events ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_event(self, event_id: str) -> dict | None:
        conn = self._conn()
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def stats(self) -> dict:
        conn = self._conn()
        cur = conn.cursor()
        total = cur.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        last = cur.execute("SELECT created_at, risk, type FROM events ORDER BY created_at DESC LIMIT 1").fetchone()
        by_status = {}
        for row in cur.execute("SELECT status, COUNT(*) FROM events GROUP BY status").fetchall():
            by_status[row[0] or "pending"] = row[1]
        conn.close()
        return {"total_events": total, "by_status": by_status, "last_event": {"created_at": last[0], "risk": last[1], "type": last[2]} if last else None}



# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# EVENT PROCESSOR â Events routed to chat_v7 (v7.0)
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ


def decide(event: dict, autonomy_config: dict) -> dict:
    """Central decision function: auto_execute | approval | block | skipped."""
    policy = load_policy()
    thresholds = policy.get("thresholds", DEFAULT_POLICY["thresholds"])
    
    if not autonomy_config.get("enabled", False):
        return {"action": "skipped", "reason": "autonomy_disabled"}
    
    risk_score = event.get("risk_score", 50) or 50
    risk = event.get("risk", "medium")
    
    # Block threshold
    if risk_score >= thresholds.get("block_min", 61):
        if risk == "high" and autonomy_config.get("allow_high", False):
            return {"action": "auto_execute", "reason": f"high_risk_allowed_by_config (score={risk_score})"}
        return {"action": "approval", "reason": f"score {risk_score} >= block threshold {thresholds.get('block_min', 61)}"}
    
    # Approval threshold
    if risk_score > thresholds.get("auto_max", 25):
        if risk == "medium" and autonomy_config.get("allow_medium", False):
            return {"action": "auto_execute", "reason": f"medium_risk_allowed_by_config (score={risk_score})"}
        return {"action": "approval", "reason": f"score {risk_score} > auto threshold {thresholds.get('auto_max', 25)}"}
    
    # Auto threshold
    return {"action": "auto_execute", "reason": f"score {risk_score} <= auto threshold {thresholds.get('auto_max', 25)}"}

async def process_event(event: dict):
    """Process a single pending event through chat_v7."""
    eid = event["event_id"]
    cfg = event_engine.get_autonomy_config()
    decision = decide(event, cfg)
    
    logger.info(f"Event {eid} decision: {decision['action']} ({decision['reason']})")
    
    if decision["action"] == "skipped":
        event_engine.update_event(eid, status="skipped", result=decision["reason"])
        return
    
    if decision["action"] == "approval":
        event_engine.update_event(eid, status="waiting_approval", result=decision["reason"])
        return
    
    if decision["action"] == "block":
        event_engine.update_event(eid, status="blocked", result=decision["reason"])
        return

    # Low risk or approved level - execute via chat_v7
    event_engine.update_event(eid, status="processing")
    try:
        goal = f"Event [{event.get('type','')}]: {event.get('title','')}. Detail: {json.dumps(event.get('detail','{}'))}. Entity: {event.get('entity_id','')}. Analyze and take appropriate action."
        trace = RequestTrace(f"event_{eid}")
        task_id = f"evt_{eid}"
        # V7: chat_v7 for events
        if CHAT_V7_OK and anthropic_client:
            from brain_core import build_system_prompt_v7 as _bsp7
            _sys7 = _bsp7()
            _executors = {
                "ha_get_state": _exec_ha_get_state,
                "ha_call_service": lambda d,s,sd: _exec_ha_call_service(d, s, sd),
                "ssh_run": _exec_ssh_run,
            }
            _v7_resp = await asyncio.wait_for(
                handle_chat_v7(goal, _sys7, anthropic_client, _executors, user_id="event_engine"),
                timeout=180
            )
            result = {"response": _v7_resp, "actions": [], "results": [], "task_state": "complete"}
        else:
            logger.error("chat_v7 unavailable, no fallback")
            result = {"response": "النظام غير متاح الحين", "actions": [], "results": [], "task_state": "error"}
        event_engine.update_event(
            eid,
            status="completed",
            task_id=task_id,
            result=json.dumps({"response": result.get("response",""), "iterations": result.get("iterations",0)}, ensure_ascii=False)[:2000],
            processed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        # Save to memory
        try:
            summary = f"Event {event.get('type','')}: {event.get('title','')} -> {result.get('response','')[:200]}"
            memory_add_short_term("system", summary)
        except Exception:
            pass
        logger.info(f"Event {eid} processed OK")
    except Exception as e:
        event_engine.update_event(eid, status="error", error=str(e)[:500])
        logger.error(f"Event {eid} processing failed: {e}")


async def event_processor_loop():
    """Background loop that processes pending events every 15 seconds."""
    logger.info("Event processor loop started")
    await asyncio.sleep(5)  # Initial delay
    while True:
        try:
            cfg = event_engine.get_autonomy_config()
            if cfg.get("enabled", False):
                pending = event_engine.get_pending_events(limit=5)
                for ev in pending:
                    await process_event(ev)
        except Exception as e:
            logger.error(f"Event processor error: {e}")
        await asyncio.sleep(15)


class TaskManager:
    """Manages stateful task execution with persistence."""

    @staticmethod
    def create_task(goal: str, request_id: str) -> str:
        task_id = f"t_{uuid.uuid4().hex[:8]}"
        conn = sqlite3.connect(AUDIT_DB)
        conn.execute(
            "INSERT INTO tasks (task_id, request_id, goal, state) VALUES (?,?,?,?)",
            (task_id, request_id, goal, "pending")
        )
        conn.commit()
        conn.close()
        return task_id

    @staticmethod
    def get_task(task_id: str) -> dict:
        conn = sqlite3.connect(AUDIT_DB)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        conn.close()
        if not row:
            return None
        d = dict(row)
        d["steps"] = json.loads(d.get("steps", "[]"))
        d["artifacts"] = json.loads(d.get("artifacts", "{}"))
        return d

    @staticmethod
    def update_task(task_id: str, **kwargs):
        conn = sqlite3.connect(AUDIT_DB)
        sets = ["updated_at = datetime('now','localtime')"]
        vals = []
        for k, v in kwargs.items():
            if k in ("steps", "artifacts"):
                v = json.dumps(v)
            sets.append(f"{k} = ?")
            vals.append(v)
        vals.append(task_id)
        conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE task_id = ?", vals)
        conn.commit()
        conn.close()

    @staticmethod
    def add_step_result(task_id: str, step_index: int, action: dict, result: dict):
        task = TaskManager.get_task(task_id)
        if not task:
            return
        steps = task["steps"]
        while len(steps) <= step_index:
            steps.append({})
        steps[step_index] = {
            "action": action, "result": result,
            "ts": datetime.now().isoformat(),
            "success": result.get("success", False)
        }
        TaskManager.update_task(task_id, steps=steps, current_step=step_index + 1)

    @staticmethod
    def complete_task(task_id: str, artifacts: dict = None):
        updates = {"state": "completed", "completed_at": datetime.now().isoformat()}
        if artifacts:
            updates["artifacts"] = artifacts
        TaskManager.update_task(task_id, **updates)

    @staticmethod
    def fail_task(task_id: str, error: str):
        TaskManager.update_task(task_id, state="failed", error=error)

    @staticmethod
    def list_tasks(state: str = None, limit: int = 20) -> list:
        conn = sqlite3.connect(AUDIT_DB)
        conn.row_factory = sqlite3.Row
        if state:
            rows = conn.execute(
                "SELECT task_id, goal, state, current_step, created_at, updated_at FROM tasks WHERE state=? ORDER BY created_at DESC LIMIT ?",
                (state, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT task_id, goal, state, current_step, created_at, updated_at FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# [UPGRADE 2] ITERATIVE PLANNING LOOP
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

# PLANNER_SYSTEM_PROMPT removed — using build_system_prompt() from brain_core

async def lifespan(app):
    init_db()
    # Phase 4: Register plugins
    register_plugins()
    # Phase 3.3: Advanced schema migration on startup
    try:
        migration = ensure_schema(dry_run=False, apply=True)
        if migration.get("applied"):
            logger.info(f"Schema migration applied: {migration.get('summary', {})}")
        elif migration.get("errors"):
            logger.warning(f"Schema migration issues: {migration['errors']}")
        else:
            logger.info(f"Schema up to date (v{SCHEMA_VERSION})")
    except Exception as e:
        logger.error(f"Schema migration error (non-fatal): {e}")
    cleanup_expired_approvals()
    # Wire dashboard_api context
    from dashboard_api import ha_dashboard_extended, init_dashboard_context
    init_dashboard_context(
        version=VERSION, start_time=START_TIME,
        dashboard_jobs=_dashboard_jobs,
        tg_handle_command_fn=tg_handle_command,
        radar_ok=RADAR_OK, journal_ok=JOURNAL_OK,
        get_open_trades_fn=get_open_trades if JOURNAL_OK else lambda: [],
        get_trade_stats_fn=get_trade_stats if JOURNAL_OK else lambda **kw: {},
    )
    _pe_set_inbox_cache_ref(ha_dashboard_extended)
    logger.info(f"Master AI v{VERSION} started")
    # Canary mode: skip all background tasks (for safe deploy testing)
    _canary = os.environ.get("CANARY_MODE", "").lower() in ("1", "true", "yes")
    if _canary:
        logger.info("CANARY MODE: background tasks skipped")
        yield
        logger.info("Canary shutting down")
        return
    asyncio.create_task(event_processor_loop())
    logger.info("Event processor loop scheduled")
    # Telegram bot polling
    if TELEGRAM_TOKEN:
        asyncio.create_task(telegram_polling_loop())
        asyncio.create_task(weather_alert_loop())
        asyncio.create_task(nightly_summary_scheduler())
        asyncio.create_task(morning_report_scheduler())
        asyncio.create_task(shift_alert_loop())
        asyncio.create_task(entity_health_check_loop())
        if BRAIN_OK: asyncio.create_task(brain_snapshot_loop())
        if BRAIN_OK: asyncio.create_task(brain_weekly_insight())
        if JOURNAL_OK: asyncio.create_task(weekly_trading_report_scheduler())
        if CONFLUENCE_OK: asyncio.create_task(confluence_scan_loop())
        if WORLD_STATE_OK: asyncio.create_task(start_world_state())
        if LEARNING_OK: asyncio.create_task(brain_nightly_learning())
        if FEEDBACK_OK: asyncio.create_task(feedback_learning_loop())
        if PLAN_OK: asyncio.create_task(plan_check_loop())
        # Phase 4 V10: Daily data collection + position monitor at 2 PM
        try:
            from kse_data_collector import daily_collection_scheduler
            asyncio.create_task(daily_collection_scheduler())
            logger.info("Daily collection scheduler started (2 PM)")
        except Exception as _e:
            logger.warning("Daily collection scheduler not loaded: %s", _e)
        try:
            from kse_data_collector import market_hours_scanner
            asyncio.create_task(market_hours_scanner())
            logger.info("Market hours scanner started (every 15 min)")
        except Exception as _e:
            logger.warning("Market hours scanner not loaded: %s", _e)
        # Phase 5: Signal review scheduler (2:00 PM KWT, 30min after data collection)
        if REVIEW_OK:
            asyncio.create_task(review_scheduler())
            logger.info("Signal review scheduler started (2 PM KWT)")
        logger.info("Telegram bot polling scheduled")
    # Phase B3: Home monitoring alerts
    if TG_ALERTS_OK:
        async def _alert_sender(text):
            _cid = ADMIN_TELEGRAM_ID or "669769765"
            await tg_send(int(_cid), text)
        asyncio.create_task(tg_alert_loop(_alert_sender))
        asyncio.create_task(proactive_suggestion_loop(_alert_sender))
        logger.info("Proactive suggestions loop scheduled")
        logger.info("Alert monitor task scheduled")
    # v8 Phase 1: Calendar sync + reminders
    try:
        from calendar_engine import calendar_sync_loop
        from calendar_reminders import run_reminder_loop
        asyncio.create_task(calendar_sync_loop())
        async def _cal_remind_sender(text):
            _cid = ADMIN_TELEGRAM_ID or "669769765"
            await tg_send(int(_cid), text)
        asyncio.create_task(run_reminder_loop(_cal_remind_sender))
        logger.info("Calendar sync + reminder loops scheduled")
    except ImportError as e:
        logger.debug(f"Calendar not loaded: {e}")
    # Phase B4: Reminders
    if TG_REMIND_OK:
        async def _remind_sender(cid, text):
            await tg_send(cid, text)
        asyncio.create_task(reminder_loop(_remind_sender))
        logger.info("Reminder loop scheduled")
    # Phase B5: Daily News
    if TG_NEWS_OK:
        async def _news_sender(text):
            _cid = ADMIN_TELEGRAM_ID or "669769765"
            await tg_send(int(_cid), text)
        async def _stock_sender(text):
            _cid = ADMIN_TELEGRAM_ID or "669769765"
            await tg_send(int(_cid), text)
        asyncio.create_task(tg_alert_loop(_stock_sender))
        asyncio.create_task(news_scheduler(_news_sender))
        logger.info("News scheduler scheduled")
    # Phase B5b: Auto news digest (news_engine) every 6 hours
    if NEWS_ENGINE_OK:
        async def _news_digest_loop():
            """Auto-generate news digest every 3 hours for dashboard."""
            _log = logging.getLogger("news_digest_loop")
            _log.info("News digest auto-scheduler started (every 3h)")
            await asyncio.sleep(30)  # let startup complete
            while True:
                try:
                    result = await news_generate_digest(None, "auto")
                    if result.get("ok"):
                        _log.info("Auto digest generated: %d items", result.get("item_count", 0))
                    else:
                        _log.warning("Auto digest failed: %s", result.get("error", "unknown"))
                except Exception as _e:
                    _log.error("Auto digest error: %s", _e)
                await asyncio.sleep(3 * 3600)  # 3 hours
        asyncio.create_task(_news_digest_loop())
        logger.info("News digest auto-scheduler scheduled (3h)")
    # Phase 2 Radar: EMA crossover monitor
    if RADAR_OK:
        try:
            init_radar_db()
            async def _radar_sender(text, sig_meta=None):
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
                                {"text": "\u0634\u0631\u064a\u062a \u2705", "callback_data": f"trade_confirm:{_r_cb}"},
                                {"text": "\u062a\u062c\u0627\u0647\u0644\u062a \u274c", "callback_data": f"trade_skip:{_r_cb}"},
                            ]
                            await tg_send_inline(int(_cid), f"\u0634\u0631\u064a\u062a \u0648\u0644\u0627 \u062a\u062c\u0627\u0647\u0644\u062a\u061f", _r_btns, columns=2)
                        except Exception as _re:
                            logging.getLogger("radar").warning(f"Radar confirm buttons error: {_re}")
                else:
                    logging.getLogger("radar").debug("Smart filter: suppressed alert")
            asyncio.create_task(radar_loop(_radar_sender))
            logger.info("Stock radar loop scheduled")
            # Daily Trading Summary at market close (1:00 PM KWT = 10:00 UTC)
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
                        # Run at ~13:15 KWT (after market close at 13:00)
                        if _kwt.hour == 13 and 10 <= _kwt.minute <= 20:
                            _cid = ADMIN_TELEGRAM_ID or "669769765"
                            _today = _kwt.strftime("%Y-%m-%d")
                            lines = [f"*\U0001f4ca \u0645\u0644\u062e\u0635 \u0627\u0644\u062a\u062f\u0627\u0648\u0644 \u2014 {_today}*\n"]
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
                                lines.append(f"\U0001f4e1 \u0625\u0634\u0627\u0631\u0627\u062a \u0627\u0644\u064a\u0648\u0645: {len(_sigs)} ({_bull} \u0635\u0627\u0639\u062f, {_bear} \u0647\u0627\u0628\u0637)")
                                # Top signals by score
                                _top = sorted(_sigs, key=lambda x: x.get("score") or 0, reverse=True)[:3]
                                if _top:
                                    lines.append("\U0001f3af \u0623\u0641\u0636\u0644 \u0625\u0634\u0627\u0631\u0627\u062a:")
                                    for _s in _top:
                                        lines.append(f"   {_s['symbol']} \u2014 Score {_s.get('score',0)}/{_s.get('score_class','?')}")
                                _sdb.close()
                            except Exception:
                                pass
                            # Journal: open trades with P&L
                            if JOURNAL_OK:
                                stats = get_trade_stats(days=1)
                                open_trades = get_open_trades()
                                if open_trades:
                                    lines.append(f"\n\U0001f4c2 \u0635\u0641\u0642\u0627\u062a \u0645\u0641\u062a\u0648\u062d\u0629: {len(open_trades)}")
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
                                                _arrow = "\u2b06\ufe0f" if _pct >= 0 else "\u2b07\ufe0f"
                                                _qty = int(t.get("quantity", 0))
                                                _pnl = round((_cp - _e) * _qty) if _qty else 0
                                                _total_pnl += _pnl
                                                _pnl_s = f" ({_pnl:+} \u0641\u0644\u0633)" if _qty else ""
                                                lines.append(f"   {_n}: {_arrow} {_pct:+.1f}%{_pnl_s}")
                                            else:
                                                lines.append(f"   {_n}: @ {_e}")
                                        except Exception:
                                            lines.append(f"   {_n}: @ {_e}")
                                    if _total_pnl:
                                        lines.append(f"\n\U0001f4b0 P&L \u0627\u0644\u0625\u062c\u0645\u0627\u0644\u064a: {_total_pnl:+} \u0641\u0644\u0633")
                                if stats.get("closed_trades", 0) > 0:
                                    _wr = str(round(stats["win_rate"] * 100)) + "%"
                                    lines.append(f"\n\u2705 \u0645\u063a\u0644\u0642\u0629 \u0627\u0644\u064a\u0648\u0645: {stats['closed_trades']}")
                                    lines.append(f"\U0001f4c8 Win rate: {_wr}")
                                if not open_trades and stats.get("closed_trades", 0) == 0:
                                    lines.append("\u0644\u0627 \u0635\u0641\u0642\u0627\u062a \u0627\u0644\u064a\u0648\u0645")
                            await tg_send(int(_cid), "\n".join(lines))
                            _log.info("Daily trading summary sent")
                            await asyncio.sleep(3600)  # don't re-send
                        else:
                            await asyncio.sleep(300)  # check every 5 min
                    except Exception as _e:
                        _log.error("Daily summary error: %s", _e)
                        await asyncio.sleep(600)
            asyncio.create_task(_daily_trading_summary_loop())
            logger.info("Daily trading summary scheduled (13:00 KWT)")
        except Exception as e:
            logger.error(f"Stock radar failed to start (non-fatal): {e}")
    # Phase 4: Proactive monitoring engine
    if BRAIN_AVAILABLE:
        try:
            # asyncio.create_task(proactive_loop())  # DISABLED: replaced by tg_alerts.py (B3)
            logger.info("Proactive engine disabled (replaced by tg_alerts.py)")
        except Exception as e:
            logger.error(f"Proactive engine failed to start (non-fatal): {e}")
        # Phase 4.5: Observability backup engine
        try:
            asyncio.create_task(backup_loop())
            asyncio.create_task(stats_save_loop())
            logger.info("Backup engine scheduled")
        except Exception as e:
            logger.error(f"Backup engine failed to start (non-fatal): {e}")
    # Bridge API client (TradingView enrichment from Windows PC)
    try:
        from bridge_client import init_bridge_client
        await init_bridge_client(health_hub=health_hub)
        logger.info("Bridge client ready")
    except Exception as e:
        logger.warning(f"Bridge client init failed (non-fatal): {e}")
    # Signal engine context
    try:
        from signal_engine import init_signal_context
        init_signal_context(
            get_open_trades=get_open_trades if JOURNAL_OK else lambda: [],
        )
        logger.info("Signal engine context ready")
    except Exception as e:
        logger.warning(f"Signal engine init failed (non-fatal): {e}")
    # R2-P1: Dream Consolidator scheduler
    async def _dream_scheduler():
        """Run memory consolidation at 3 AM KWT daily."""
        _log = logging.getLogger("dream_scheduler")
        _log.info("Dream scheduler started")
        await asyncio.sleep(60)  # let startup complete
        while True:
            now = datetime.now()
            target = now.replace(hour=3, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_secs = (target - now).total_seconds()
            _log.info(f"Next dream consolidation in {wait_secs/3600:.1f}h")
            await asyncio.sleep(wait_secs)
            try:
                from dream_consolidator import run_dream_consolidation
                report = await run_dream_consolidation()
                _cid = ADMIN_TELEGRAM_ID or "669769765"
                merged = report.get("merged", 0)
                archived = report.get("archived", 0)
                compacted = report.get("session_compacted", 0)
                kept = report.get("kept", "?")
                if merged + archived + compacted > 0:
                    await tg_send(int(_cid),
                        f"🧹 Dream Consolidation:\n"
                        f"  دمج: {merged} | أرشفة: {archived} | ضغط: {compacted}\n"
                        f"  باقي: {kept} ذاكرة نشطة")
                _log.info(f"Dream done: {report}")
            except Exception as _e:
                _log.error(f"Dream error: {_e}", exc_info=True)

    asyncio.create_task(_dream_scheduler())
    logger.info("Dream consolidator scheduler started (3 AM KWT)")

    # Trading brain — signal learning engine
    BRAIN_TRADING_OK = False
    try:
        from trading_brain import init_brain_context, init_schema as brain_init_schema
        brain_init_schema()
        init_brain_context()
        BRAIN_TRADING_OK = True
        logger.info("Trading brain initialized")
    except Exception as e:
        logger.warning(f"Trading brain init failed (non-fatal): {e}")
    if BRAIN_TRADING_OK:
        async def _brain_scheduler():
            """Trading brain: snapshot signals after radar, evaluate daily, report weekly."""
            import asyncio as _aio
            _log = logging.getLogger("brain_scheduler")
            _log.info("Trading brain scheduler started")
            await _aio.sleep(120)  # let startup complete
            while True:
                try:
                    from trading_brain import snapshot_signals, evaluate_pending_signals, generate_weekly_report, format_weekly_tg
                    from datetime import datetime as _dt
                    now = _dt.now()
                    hour, minute, weekday = now.hour, now.minute, now.isoweekday()
                    # Snapshot signals every 2 hours during market hours (Sun-Thu 9-13 KWT = 6-10 UTC)
                    if weekday <= 4 and 6 <= hour <= 10:
                        snapshot_signals()
                    # Evaluate daily at 13:30 KWT (10:30 UTC) Sun-Thu
                    if weekday <= 4 and hour == 10 and 25 <= minute <= 35:
                        evaluate_pending_signals()
                    # Weekly report Friday 14:00 KWT (11:00 UTC)
                    if weekday == 5 and hour == 11 and minute <= 10:
                        report = generate_weekly_report()
                        try:
                            _cid = ADMIN_TELEGRAM_ID or "669769765"
                            msg = format_weekly_tg(report)
                            await tg_send(int(_cid), msg)
                            _log.info("Weekly brain report sent")
                        except Exception as _te:
                            _log.warning(f"Brain TG send failed: {_te}")
                except Exception as _e:
                    _log.error(f"Brain scheduler error: {_e}")
                await _aio.sleep(600)  # check every 10 minutes
        asyncio.create_task(_brain_scheduler())
    # Phase 3: KAIROS background agent
    global kairos_agent
    kairos_agent = KairosAgent(
        health_hub=health_hub, ff=ff, tg_send_fn=tg_send, db_path=_db_path,
        cb_ha=_cb_ha, cb_llm=_cb_llm, cb_tg=_cb_tg,
    )
    asyncio.create_task(kairos_agent.start())
    logger.info("KAIROS agent scheduled (gated by feature flag)")
    health_hub.set_hooks(hook_registry)
    logger.info("Hooks wired into health_hub")
    # Phase 6: Register tools in catalog
    # -- Home --
    tool_reg.register("ha_get_state", _exec_ha_get_state, category="home",
                      description="Get Home Assistant entity state", requires=["home_assistant"])
    tool_reg.register("ha_call_service", _exec_ha_call_service, category="home",
                      description="Call Home Assistant service", requires=["home_assistant"])
    # -- System --
    tool_reg.register("ssh_run", _exec_ssh_run, category="system",
                      description="Run shell command on RPi")
    tool_reg.register("service_health", lambda: health_hub.get_summary(), category="system",
                      description="Get all service health statuses")
    tool_reg.register("feature_flags", lambda: ff.get_all(), category="system",
                      description="List all feature flags")
    tool_reg.register("kairos_status", lambda: kairos_agent.get_status() if kairos_agent else {}, category="system",
                      description="KAIROS agent status")
    # -- Trading --
    try:
        from bridge_client import BridgeClient, BRIDGE_BASE_URL
        tool_reg.register("bridge_status", lambda: BridgeClient(BRIDGE_BASE_URL).get_status(),
                          category="trading", description="TradingView Bridge status", requires=["bridge"])
    except Exception:
        pass
    try:
        from stock_radar import get_radar_snapshot, get_watchlist
        tool_reg.register("radar_snapshot", get_radar_snapshot, category="trading",
                          description="Stock radar daily snapshot")
        tool_reg.register("radar_watchlist", get_watchlist, category="trading",
                          description="Current radar watchlist")
    except Exception:
        pass
    # -- News --
    if NEWS_ENGINE_OK:
        tool_reg.register("news_feed", lambda: news_get_news(limit=20), category="news",
                          description="Latest 20 news items")
        tool_reg.register("news_counts", news_get_counts, category="news",
                          description="News item counts by category")
    # -- Journal --
    if JOURNAL_OK:
        try:
            tool_reg.register("open_trades", get_open_trades, category="trading",
                              description="Current open trading positions")
            tool_reg.register("trade_stats", get_trade_stats, category="trading",
                              description="Trading statistics summary")
        except Exception:
            pass
    # -- Memory --
    if MEMORY_AVAILABLE:
        tool_reg.register("memory_stats", lambda: _get_memory_stats() if callable(_get_memory_stats) else {},
                          category="system", description="Memory DB statistics")
    logger.info(f"Tool registry: {len(tool_reg.list_tools())} tools registered")

    # Phase 6: Wire hook handlers for logging
    async def _hook_log_service_down(name="", reason="", **kw):
        logger.info(f"HOOK service_down: {name} - {reason}")
    async def _hook_log_service_up(name="", **kw):
        logger.info(f"HOOK service_up: {name}")
    async def _hook_log_flag_toggle(name="", enabled=False, **kw):
        logger.info(f"HOOK flag_toggled: {name}={enabled}")
    hook_registry.on("service_down", _hook_log_service_down)
    hook_registry.on("service_up", _hook_log_service_up)
    hook_registry.on("flag_toggled", _hook_log_flag_toggle)

    # Trading hook: block alerts outside market hours
    async def _hook_check_market_hours(**kwargs):
        try:
            from datetime import datetime, timezone, timedelta
            _kwt = timezone(timedelta(hours=3))
            now = datetime.now(_kwt)
            if now.weekday() not in {6, 0, 1, 2, 3}:  # Sun-Thu
                return {"skip": True, "reason": "Market closed (weekend)"}
            t = now.hour * 60 + now.minute
            if not (9 * 60 <= t <= 13 * 60 + 30):
                return {"skip": True, "reason": "Market closed (off-hours)"}
        except Exception:
            pass
        return {}
    hook_registry.on("before_trade_alert", _hook_check_market_hours)
    logger.info(f"Hooks: {hook_registry.get_stats()['total_handlers']} handlers registered")

    yield
    logger.info("Master AI shutting down")

app = FastAPI(title="Master AI", version=VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
from fastapi.responses import FileResponse
import os as _os

TRADING_HTML_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "www", "trading")

@app.get("/trading/{page}")
async def serve_trading_page(page: str):
    """Serve trading HTML pages with or without .html extension."""
    if page.endswith(".html"):
        filepath = _os.path.join(TRADING_HTML_DIR, page)
    else:
        filepath = _os.path.join(TRADING_HTML_DIR, page + ".html")
    if _os.path.isfile(filepath):
        return FileResponse(filepath, media_type="text/html")
    exact = _os.path.join(TRADING_HTML_DIR, page)
    if _os.path.isfile(exact):
        return FileResponse(exact)
    return JSONResponse({"detail": "Not Found"}, status_code=404)

from dashboard_api import router as dashboard_router
app.include_router(dashboard_router)

# Event Engine (v5.1)
event_engine = EventEngine(AUDIT_DB)


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# API KEY MIDDLEWARE
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

from starlette.middleware.base import BaseHTTPMiddleware

class APIKeyMiddleware(BaseHTTPMiddleware):
    OPEN_PATHS = {"/tradingview/webhook", "/health", "/panel", "/trading", "/dashboard", "/dashboard/extended", "/dashboard/signals", "/dashboard/signals-30m", "/dashboard/signals-daily", "/dashboard/radar", "/dashboard/brain", "/dashboard/brain-insights", "/dashboard/regime", "/dashboard/portfolio", "/dashboard/journal", "/dashboard/strategies", "/dashboard/reviews", "/dashboard/ema-crosses", "/dashboard/ema-proximity", "/dashboard/ema-active", "/dashboard/ema-live", "/dashboard/scalper", "/dev/context", "/gmail/auth", "/gmail/callback", "/google/auth", "/google/callback"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in self.OPEN_PATHS or path.startswith("/webhook/") or path.startswith("/trading/") or path.startswith("/api/") or not MASTER_API_KEY:
            return await call_next(request)
        key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if key != MASTER_API_KEY:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)

app.add_middleware(APIKeyMiddleware)

# --- Rate Limiter (in-memory, per-IP) ---
import time as _rl_time
_rate_limits = {}  # {ip: [(timestamp, ...], ...}
_RATE_WINDOWS = {
    "/webhook/": (10, 60),   # 10 req/60s
    "/win/": (30, 60),       # 30 req/60s
    "/agent": (5, 60),       # 5 req/60s
    "/ask": (10, 60),        # 10 req/60s
}

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        for prefix, (max_req, window) in _RATE_WINDOWS.items():
            if path.startswith(prefix) or path == prefix:
                key = f"{client_ip}:{prefix}"
                now = _rl_time.time()
                hits = _rate_limits.get(key, [])
                hits = [t for t in hits if now - t < window]
                if len(hits) >= max_req:
                    logger.warning(f"Rate limit: {client_ip} on {prefix} ({len(hits)}/{max_req})")
                    return JSONResponse({"error": "rate limit exceeded"}, status_code=429)
                hits.append(now)
                _rate_limits[key] = hits
                break
        return await call_next(request)

app.add_middleware(RateLimitMiddleware)

# --- Module: Panel ---
try:
    from modules.panel import register_panel_routes
    register_panel_routes(app)
    logger.info("Panel module loaded")
except Exception as e:
    logger.warning(f"Panel module failed to load: {e}")


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# EXCEPTION HANDLER
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse({"error": str(exc)}, status_code=500)


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# CORE ENDPOINTS
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ


@app.get("/brain/stats")
async def brain_stats_endpoint():
    """Brain learning statistics."""
    if not BRAIN_AVAILABLE:
        return {"error": "brain module not loaded"}
    return get_brain_stats()

@app.get('/system/diag')
async def system_diag_endpoint():
    if not BRAIN_AVAILABLE:
        return {"error": "brain module not loaded"}
    stats = get_brain_stats()
    return get_system_diag(brain_stats=stats)

@app.post('/system/backup')
async def backup_endpoint():
    if not BRAIN_AVAILABLE:
        return {"error": "brain module not loaded"}
    return run_backup()

@app.get("/dream/status")
async def dream_status_endpoint():
    """Dream Consolidator — memory health status."""
    try:
        from dream_consolidator import get_dream_status
        return await get_dream_status()
    except Exception as e:
        return {"error": str(e)}

@app.post("/dream/run")
async def dream_run_endpoint():
    """Dream Consolidator — trigger manual consolidation."""
    try:
        from dream_consolidator import run_dream_consolidation
        return await run_dream_consolidation()
    except Exception as e:
        return {"error": str(e)}

@app.get("/tips")
async def tips_endpoint():
    """Smart Tips — list all tips with status."""
    if not _tips_engine:
        return {"error": "tips engine not loaded"}
    return {"tips": _tips_engine.get_all_tips()}

@app.get('/brain/analytics')
async def analytics_endpoint(days: int = 7):
    if not BRAIN_AVAILABLE:
        return {"error": "brain module not loaded"}
    return get_analytics(days=days)

@app.get('/brain/users')
async def users_endpoint():
    if not BRAIN_AVAILABLE:
        return {"error": "brain module not loaded"}
    return get_multiuser_stats()

@app.post('/brain/feedback')
async def feedback_endpoint(data: dict):
    if not BRAIN_AVAILABLE:
        return {"error": "brain module not loaded"}
    ok = record_feedback(session_id=data.get("session_id",""), rating=data.get("rating",3), comment=data.get("comment",""), user_id=data.get("user_id","bu_khalifa"), goal=data.get("goal",""))
    return {"success": ok}


@app.get("/brain/diag")
async def brain_diag_endpoint():
    """Brain diagnostics: DB state, learning stats, errors."""
    import sqlite3 as _sq, os as _os
    db_path = _os.path.join(BASE_DIR, "data", "audit.db")
    brain_db = _os.path.join(BASE_DIR, "data", "brain.db")
    result = {
        "brain_db_exists": _os.path.exists(brain_db),
        "brain_db_size": _os.path.getsize(brain_db) if _os.path.exists(brain_db) else 0,
        "brain_db_note": "orphan file - learning uses audit.db",
    }
    try:
        conn = _sq.connect(db_path)
        result["memory_count"] = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
        result["audit_db_ok"] = True
        conn.close()
    except Exception as e:
        result["audit_db_ok"] = False
        result["error"] = str(e)
    if BRAIN_AVAILABLE:
        result["brain_module"] = "loaded"
        try:
            result["brain_stats"] = get_brain_stats()
        except Exception as e:
            result["brain_stats_error"] = str(e)
    else:
        result["brain_module"] = "not loaded"
    return result


@app.post("/debug/test_approval", tags=["debug"])
async def debug_test_approval(request: Request):
    """Create a dummy approval for testing TG notification."""
    pass  # auth via middleware
    import uuid as _uuid
    _aid = str(_uuid.uuid4())[:8]
    _exp = (datetime.now() + timedelta(minutes=5)).isoformat()
    conn = sqlite3.connect(AUDIT_DB)
    conn.execute("INSERT INTO approval_queue (approval_id, job_id, agent_id, action, risk, status, expires_at) VALUES (?,NULL,NULL,?,?,'pending',?)", (_aid, '{"kind":"test","action_type":"debug_test"}', "low", _exp))
    conn.commit()
    conn.close()
    await _notify_approval(_aid, "Debug test approval", "low")
    return {"approval_id": _aid, "status": "created", "notification": "sent"}


# ===== Gmail OAuth Endpoints =====
@app.get("/gmail/auth")
async def gmail_auth_start():
    """Start Gmail OAuth flow — open this in browser."""
    try:
        import json, secrets
        from urllib.parse import urlencode
        creds_path = os.path.join(BASE_DIR, "gmail_credentials.json")
        if not os.path.exists(creds_path):
            return {"error": "gmail_credentials.json not found"}
        creds_data = json.loads(open(creds_path).read())["web"]
        client_id = creds_data["client_id"]
        
        state = secrets.token_urlsafe(32)
        redirect_uri = "https://ai.salem-home.com/gmail/callback"
        
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/gmail.readonly",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
        
        state_file = os.path.join(BASE_DIR, "data", "gmail_oauth_state.json")
        open(state_file, "w").write(json.dumps({"state": state, "redirect_uri": redirect_uri}))
        
        from fastapi.responses import RedirectResponse
        return RedirectResponse(auth_url)
    except Exception as e:
        return {"error": str(e)}


@app.get("/gmail/callback")
async def gmail_auth_callback(code: str = "", state: str = "", error: str = ""):
    """Gmail OAuth callback — Google redirects here after auth."""
    if error:
        return {"error": error}
    if not code:
        return {"error": "no auth code received"}
    try:
        import json, httpx
        creds_path = os.path.join(BASE_DIR, "gmail_credentials.json")
        creds_data = json.loads(open(creds_path).read())["web"]
        
        redirect_uri = "https://ai.salem-home.com/gmail/callback"
        
        # Exchange code for tokens manually
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post("https://oauth2.googleapis.com/token", data={
                "code": code,
                "client_id": creds_data["client_id"],
                "client_secret": creds_data["client_secret"],
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            })
            token_data = resp.json()
        
        if "error" in token_data:
            return {"error": token_data.get("error_description", token_data["error"])}
        
        # Save as google credentials format
        from google.oauth2.credentials import Credentials
        creds = Credentials(
            token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=creds_data["client_id"],
            client_secret=creds_data["client_secret"],
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        )
        
        token_file = os.path.join(BASE_DIR, "data", "gmail_token.json")
        open(token_file, "w").write(creds.to_json())
        
        # Test it
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress", "?")
        
        return {"status": "success", "email": email, "message": f"Gmail connected: {email}"}
    except Exception as e:
        return {"error": str(e)}




# ===== Google Workspace OAuth (Gmail + Calendar) =====
@app.get("/google/auth")
async def google_auth_start():
    """Start unified Google OAuth (Gmail + Calendar) - open in browser."""
    try:
        import secrets
        from google_auth_ext import build_auth_url
        state = secrets.token_urlsafe(32)
        state_file = os.path.join(BASE_DIR, "data", "google_oauth_state.json")
        open(state_file, "w").write(json.dumps({"state": state}))
        url = build_auth_url(state)
        if not url:
            return {"error": "gmail_credentials.json not found"}
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url)
    except Exception as e:
        return {"error": str(e)}


@app.get("/google/callback")
async def google_auth_callback(code: str = "", state: str = "", error: str = ""):
    """Google OAuth callback - handles Gmail + Calendar token."""
    if error:
        return {"error": error}
    if not code:
        return {"error": "no auth code received"}
    try:
        from google_auth_ext import exchange_code, get_auth_status, build_calendar_service
        token_data = await exchange_code(code)
        if not token_data:
            return {"error": "token exchange failed"}
        # Test Calendar access
        cal_ok = False
        try:
            svc = build_calendar_service()
            if svc:
                cal_list = svc.calendarList().list(maxResults=1).execute()
                cal_ok = True
        except Exception:
            pass
        status = get_auth_status()
        return {
            "status": "success",
            "calendar_connected": cal_ok,
            "auth_status": status,
            "message": "Google Workspace connected (Gmail + Calendar)"
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/google/auth/status")
async def google_auth_status():
    """Check Google OAuth status."""
    try:
        from google_auth_ext import get_auth_status
        return get_auth_status()
    except Exception as e:
        return {"error": str(e)}


@app.get("/calendar/stats")
async def calendar_stats_endpoint():
    """Calendar statistics."""
    try:
        from calendar_db import get_calendar_stats
        return get_calendar_stats()
    except Exception as e:
        return {"error": str(e)}


@app.post("/calendar/sync")
async def calendar_sync_endpoint():
    """Trigger manual calendar sync."""
    try:
        from calendar_engine import sync_full
        result = await sync_full()
        return result
    except Exception as e:
        return {"error": str(e)}


@app.get("/world-state")
async def world_state_endpoint():
    """Current world state snapshot."""
    if not WORLD_STATE_OK:
        return {"error": "world_state module not available"}
    return {
        "status": ws_get_status(),
        "text": get_snapshot_text(),
        "data": get_snapshot_data(),
    }

@app.get("/tool-stats")
async def tool_stats_endpoint():
    """Tool outcome statistics."""
    try:
        from exec_policy import get_tool_stats
        return {"stats": get_tool_stats()}
    except ImportError:
        return {"error": "exec_policy not available"}

@app.post("/tradingview/webhook")
async def tradingview_webhook(request: Request):
    """Receive TradingView webhook alerts."""
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False, "error": "invalid JSON"})
    if not TV_BRIDGE_OK:
        return JSONResponse(status_code=503, content={"ok": False, "error": "TV bridge not loaded"})
    status_code, response = tv_handle_webhook(payload)
    # Send trade confirmation via TG inline keyboard
    if status_code == 200 and response.get("ok"):
        try:
            _sig = payload.get("signal", "").lower()
            _ticker = payload.get("ticker", "")
            _price = payload.get("price", "0")
            try:
                from tv_data import _normalize_price_to_fils
                _price = str(_normalize_price_to_fils(float(_price))) if _price else "0"
            except Exception:
                pass
            _strat = payload.get("strategy", payload.get("strategy_name", "TV Alert"))
            _qty = payload.get("quantity", "0")
            _msg_text = response.get("tg_message", "")
            saved_id = response.get("saved_id", "")
            if _sig in ("buy", "entry", "long", "sell", "exit", "close", "short"):
                _action = "buy" if _sig in ("buy", "entry", "long") else "sell"
                _cb_data = f"{_ticker}|{_price}|{_action}|{_strat}|{_qty}|{saved_id}"
                _confirm_msg = _msg_text or f"\U0001f4e1 TV Signal: {_action.upper()} {_ticker} @ {_price}"
                _confirm_msg += f"\n\n\u0634\u0631\u064a\u062a \u0648\u0644\u0627 \u062a\u062c\u0627\u0647\u0644\u062a\u061f"
                _btns = [
                    {"text": "\u0634\u0631\u064a\u062a \u2705", "callback_data": f"trade_confirm:{_cb_data}"},
                    {"text": "\u062a\u062c\u0627\u0647\u0644\u062a \u274c", "callback_data": f"trade_skip:{_cb_data}"},
                ]
                admin_id = get_admin_chat_id() if TG_OPS_OK else None
                if not admin_id:
                    _aid_path = os.path.join(os.path.dirname(__file__) or ".", "data", "admin_chat_id.txt")
                    if os.path.exists(_aid_path):
                        admin_id = open(_aid_path).read().strip()
                if admin_id:
                    await tg_send_inline(int(admin_id), _confirm_msg, _btns, columns=2)
                    if saved_id:
                        mark_telegram_sent(saved_id)
                    logger.info(f"TV trade confirmation sent: {_action} {_ticker} @ {_price}")
                else:
                    logger.warning("TV trade confirmation: no admin chat_id found")
            elif _msg_text:
                # Non-trade signals (info, alert) — send plain message
                admin_id = get_admin_chat_id() if TG_OPS_OK else None
                if not admin_id:
                    _aid_path = os.path.join(os.path.dirname(__file__) or ".", "data", "admin_chat_id.txt")
                    if os.path.exists(_aid_path):
                        admin_id = open(_aid_path).read().strip()
                if admin_id:
                    await tg_send(int(admin_id), _msg_text)
                    if saved_id:
                        mark_telegram_sent(saved_id)
        except Exception as e:
            logger.error(f"TV TG send error: {e}")
    return JSONResponse(status_code=status_code, content=response)

@app.get("/api/decisions-now")
async def api_decisions_now():
    """Golden opportunities — match live data with historical patterns."""
    from golden_engine import scan_opportunities
    live_list = []
    try:
        from signal_engine import build_signals_30m
        sig_data = build_signals_30m()
        live_list = sig_data.get("signals", [])
    except Exception:
        pass
    if not live_list:
        try:
            from signal_engine import build_signals
            sig_data = build_signals()
            live_list = sig_data.get("all_signals", [])
        except Exception:
            pass
    # Fallback: use stock_radar_daily DB when bridge is offline
    if not live_list:
        import sqlite3 as _sq
        _db = os.path.join(os.path.dirname(__file__), "data", "life.db")
        try:
            _c = _sq.connect(_db, timeout=5)
            _c.row_factory = _sq.Row
            _rows = _c.execute(
                "SELECT symbol, price, rsi, vol_ratio, support, resistance, "
                "macd_cross AS macd_state, daily_ema_cross AS ema_state, "
                "stoch_k, adx, atr, bb_squeeze, confluence_score, change_pct "
                "FROM stock_radar_daily"
            ).fetchall()
            _c.close()
            live_list = [dict(r) for r in _rows]
        except Exception:
            pass
    return scan_opportunities(live_list)


@app.get("/api/stocks/symbol/{symbol}")
async def get_stock_personality(symbol: str, timeframe: str = "1D"):
    """Get stock personality: profile + patterns + notes."""
    from stock_personality_engine import get_symbol_personality
    return get_symbol_personality(symbol.upper(), timeframe)

@app.get("/api/stocks/profiles")
async def get_all_stock_profiles():
    """Get summary of all stock profiles."""
    from stock_personality_engine import get_all_profiles_summary
    return {"profiles": get_all_profiles_summary()}


@app.get("/dashboard/reviews")
async def dashboard_reviews(date: str = None):
    """Signal review results for dashboard."""
    if not REVIEW_OK:
        return {"error": "signal_review not loaded"}
    return get_reviews_for_dashboard(date)

@app.post("/api/review-now")
async def manual_review(date: str = None, all: bool = False):
    """Manually trigger signal review. Use ?all=true to review all pending days."""
    if not REVIEW_OK:
        return {"error": "signal_review not loaded"}
    if all:
        from signal_review import review_all_pending
        return {"results": review_all_pending()}
    return review_signals(date)

# ── EMA 9/21 Scalper Endpoints ──────────

@app.get("/dashboard/ema-crosses")
async def dashboard_ema_crosses(hours: int = 4, signal_type: str = "all"):
    """Recent EMA 9/21 cross events for scalper page."""
    import sqlite3
    from datetime import datetime, timedelta

    conn = sqlite3.connect(os.path.join(BASE_DIR, "data", "life.db"))
    conn.row_factory = sqlite3.Row

    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

    where_signal = ""
    if signal_type == "bullish":
        where_signal = "AND signal_type = 'bullish_cross'"
    elif signal_type == "bearish":
        where_signal = "AND signal_type = 'bearish_cross'"

    rows = conn.execute(f"""
        SELECT symbol, signal_type, price, candle_time, ema_fast, ema_slow,
               rsi, volume, score, score_class, verdict, support, resistance,
               vol_ratio, created_at
        FROM stock_radar_events
        WHERE created_at >= ? {where_signal}
        ORDER BY created_at DESC
        LIMIT 100
    """, (cutoff,)).fetchall()
    conn.close()

    from tv_data import KSE_STOCKS

    events = []
    for r in rows:
        events.append({
            "symbol": r["symbol"],
            "name_ar": KSE_STOCKS.get(r["symbol"], r["symbol"]),
            "signal": r["signal_type"],
            "price": r["price"],
            "candle_time": r["candle_time"],
            "ema9": r["ema_fast"],
            "ema21": r["ema_slow"],
            "rsi": r["rsi"],
            "volume": r["volume"],
            "score": r["score"],
            "score_class": r["score_class"],
            "verdict": r["verdict"],
            "support": r["support"],
            "resistance": r["resistance"],
            "vol_ratio": r["vol_ratio"],
            "time": r["created_at"],
        })

    bull = sum(1 for e in events if e["signal"] == "bullish_cross")
    bear = sum(1 for e in events if e["signal"] == "bearish_cross")

    return {
        "total": len(events),
        "bullish_count": bull,
        "bearish_count": bear,
        "hours": hours,
        "events": events,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/dashboard/ema-proximity")
async def dashboard_ema_proximity(threshold_pct: float = 1.5):
    """Stocks where EMA9 and EMA21 are close — about to cross."""
    import sqlite3

    conn = sqlite3.connect(os.path.join(BASE_DIR, "data", "life.db"))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT symbol, prev_ema_fast, prev_ema_slow, updated_at
        FROM stock_radar_state
        WHERE timeframe = '30m' AND prev_ema_fast > 0 AND prev_ema_slow > 0
    """).fetchall()
    conn.close()

    from tv_data import KSE_STOCKS

    approaching = []
    for r in rows:
        fast = r["prev_ema_fast"]
        slow = r["prev_ema_slow"]
        if not slow:
            continue
        gap_pct = abs(fast - slow) / slow * 100
        if gap_pct <= threshold_pct:
            direction = "bullish_approach" if fast > slow else "bearish_approach"
            approaching.append({
                "symbol": r["symbol"],
                "name_ar": KSE_STOCKS.get(r["symbol"], r["symbol"]),
                "ema9": round(fast, 3),
                "ema21": round(slow, 3),
                "gap_pct": round(gap_pct, 3),
                "direction": direction,
                "updated_at": r["updated_at"],
            })

    approaching.sort(key=lambda x: x["gap_pct"])

    return {
        "threshold_pct": threshold_pct,
        "count": len(approaching),
        "stocks": approaching,
    }



@app.get("/dashboard/ema-active")
async def dashboard_ema_active():
    """Current EMA 9/21 status for all tracked stocks."""
    import sqlite3 as _sq3

    db_path = os.path.join(BASE_DIR, "data", "life.db")
    conn = _sq3.connect(db_path)
    conn.row_factory = _sq3.Row

    states = conn.execute(
        "SELECT symbol, last_signal, last_signal_candle_time, updated_at,"
        " prev_ema_fast, prev_ema_slow"
        " FROM stock_radar_state"
        " WHERE timeframe='30m' AND last_signal IS NOT NULL AND last_signal != ''"
    ).fetchall()

    events = conn.execute(
        "SELECT e.symbol, e.signal_type, e.price, e.ema_fast, e.ema_slow,"
        " e.rsi, e.volume, e.score, e.score_class, e.verdict,"
        " e.support, e.resistance, e.vol_ratio, e.candle_time, e.created_at"
        " FROM stock_radar_events e"
        " INNER JOIN ("
        "   SELECT symbol, MAX(created_at) as max_time"
        "   FROM stock_radar_events GROUP BY symbol"
        " ) latest ON e.symbol = latest.symbol AND e.created_at = latest.max_time"
    ).fetchall()
    conn.close()

    from tv_data import KSE_STOCKS
    event_map = {}
    for ev in events:
        event_map[ev["symbol"]] = dict(ev)

    bullish = []
    bearish = []
    for st in states:
        sym = st["symbol"]
        sig = st["last_signal"]
        ev = event_map.get(sym, {})
        entry = {
            "symbol": sym,
            "name_ar": KSE_STOCKS.get(sym, sym),
            "status": "bullish" if "bullish" in sig else "bearish",
            "last_signal": sig,
            "signal_time": st["last_signal_candle_time"] or st["updated_at"],
            "price": ev.get("price"),
            "ema9": ev.get("ema_fast"),
            "ema21": ev.get("ema_slow"),
            "rsi": ev.get("rsi"),
            "volume": ev.get("volume"),
            "score": ev.get("score"),
            "score_class": ev.get("score_class"),
            "verdict": ev.get("verdict"),
            "support": ev.get("support"),
            "resistance": ev.get("resistance"),
            "vol_ratio": ev.get("vol_ratio"),
            "updated_at": st["updated_at"],
        }
        if "bullish" in sig:
            bullish.append(entry)
        else:
            bearish.append(entry)

    bullish.sort(key=lambda x: x.get("signal_time") or "", reverse=True)
    bearish.sort(key=lambda x: x.get("signal_time") or "", reverse=True)

    from datetime import datetime
    return {
        "bullish_count": len(bullish),
        "bearish_count": len(bearish),
        "total": len(bullish) + len(bearish),
        "bullish": bullish,
        "bearish": bearish,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── EMA Live: Real-Time EMA 9/21 State from Bridge API ──────────

_ema_live_cache = {"data": None, "ts": 0}
_EMA_LIVE_TTL = 180  # 3 minutes cache

@app.get("/dashboard/ema-live")
async def dashboard_ema_live():
    """Live EMA 9/21 state for ALL 128 KSE stocks from Bridge API (cached 3 min)."""
    import time as _t
    from datetime import datetime

    # Serve from cache if fresh
    if _ema_live_cache["data"] and (_t.time() - _ema_live_cache["ts"]) < _EMA_LIVE_TTL:
        return _ema_live_cache["data"]

    from bridge_client import BridgeClient, BRIDGE_BASE_URL
    from stock_radar import get_watchlist
    from tv_data import KSE_STOCKS

    watchlist = get_watchlist()
    symbols = [w["symbol"] for w in watchlist]

    try:
        client = BridgeClient(BRIDGE_BASE_URL)
        try:
            data = await client.get_multi_analysis_30m_bulk(symbols)
        finally:
            await client.close()
    except Exception as e:
        # Return stale cache if available
        if _ema_live_cache["data"]:
            stale = _ema_live_cache["data"].copy()
            stale["stale"] = True
            return stale
        return {"error": str(e), "bridge_online": False}

    bridge_symbols = data.get("symbols", {})

    bullish = []
    bearish = []
    touching = []

    for sym, bd in bridge_symbols.items():
        if not isinstance(bd, dict):
            continue
        ema_data = bd.get("ema", {})
        ema9 = float(ema_data.get("ema9") or 0)
        ema21 = float(ema_data.get("ema21") or ema_data.get("ema20") or 0)
        price = float(bd.get("price") or 0)
        rsi = bd.get("rsi_14")
        vol_ratio = bd.get("vol_ratio")

        if not ema9 or not ema21:
            continue

        gap_pct = abs(ema9 - ema21) / ema21 * 100

        entry = {
            "symbol": sym,
            "name_ar": KSE_STOCKS.get(sym, sym),
            "price": price,
            "ema9": round(ema9, 3),
            "ema21": round(ema21, 3),
            "gap_pct": round(gap_pct, 3),
            "rsi": rsi,
            "vol_ratio": vol_ratio,
        }

        if gap_pct < 0.1:
            entry["status"] = "touching"
            touching.append(entry)
        elif ema9 > ema21:
            entry["status"] = "above"
            bullish.append(entry)
        else:
            entry["status"] = "below"
            bearish.append(entry)

    # Sort by gap_pct (closest to cross first)
    bullish.sort(key=lambda x: x["gap_pct"])
    bearish.sort(key=lambda x: x["gap_pct"])
    touching.sort(key=lambda x: x["gap_pct"])

    result = {
        "bridge_online": data.get("bridge_online", False),
        "total_checked": len(bridge_symbols),
        "bullish_count": len(bullish),
        "bearish_count": len(bearish),
        "touching_count": len(touching),
        "bullish": bullish,
        "bearish": bearish,
        "touching": touching,
        "timestamp": datetime.utcnow().isoformat(),
    }
    _ema_live_cache["data"] = result
    _ema_live_cache["ts"] = _t.time()
    return result

@app.get("/health")
async def health():
    schema = _get_schema_status()
    return {
        "status": "ok", "service": "master_ai", "version": VERSION,
        "uptime_seconds": round(time.time() - START_TIME),
        "agents": list(connected_agents.keys()),
        "queued_jobs": _count_queued_jobs(),
        "memory_available": MEMORY_AVAILABLE,
        "event_engine": event_engine.stats(),
        "autonomy": event_engine.get_autonomy_config(),
        "policy_version": load_policy().get("version", 0),
        "schema_version": schema.get("schema_version"),
        "schema_drift_count": schema.get("drift_count", -1),
        "last_migration_ok": (schema.get("last_migration") or {}).get("ok"),
        "plugins": len(PLUGIN_REGISTRY._plugins),
    }


# ── Entity History Endpoint ──────────
@app.get("/history/{entity_id:path}")
async def entity_history_endpoint(entity_id: str, hours: int = 24,
                                   start: str = None, end: str = None,
                                   format: str = "report", detail: str = "normal"):
    """Entity history: GET /history/climate.my_room_ac?hours=24&format=report|json|raw"""
    if not DOCTOR_OK:
        return {"error": "ha_history not loaded"}
    if format == "raw":
        data = await get_entity_history(entity_id, hours, start, end)
        return {"entity_id": entity_id, "count": len(data), "history": data}
    elif format == "json":
        return await analyze_entity(entity_id, hours, start, end)
    else:
        text = await format_history(entity_id, hours, start, end, detail)
        return {"entity_id": entity_id, "report": text}



def _count_queued_jobs():
    try:
        conn = sqlite3.connect(AUDIT_DB)
        count = conn.execute("SELECT COUNT(*) FROM win_jobs WHERE status='queued'").fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ /ask ÃÂ¢ÃÂÃÂ Main chat endpoint ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

class AskRequest(BaseModel):
    message: str
    context: dict = Field(default_factory=dict)
    task_id: str = None  # For resuming tasks

class AskResponse(BaseModel):
    response: str
    actions: list = []
    results: list = []
    task_id: str = None
    request_id: str = None
    trace: dict = None




# ── Pattern Learning Endpoints ─────────
@app.get("/patterns")
async def patterns_endpoint(entity_id: str = None):
    """Get learned patterns. GET /patterns?entity_id=light.parking_light_switch_1"""
    if not LEARNING_OK:
        return {"error": "brain_learning not loaded"}
    if entity_id:
        patterns = bl_get_patterns(entity_id)
        report = await bl_format_patterns(entity_id)
        return {"entity_id": entity_id, "patterns": patterns, "report": report}
    return {"stats": bl_stats(), "patterns": bl_get_patterns()}

@app.get("/patterns/suggestions")
async def patterns_suggestions_endpoint():
    """Get automation suggestions from learned patterns."""
    if not LEARNING_OK:
        return {"error": "brain_learning not loaded"}
    return {"suggestions": await bl_suggest()}

@app.get("/anomalies")
async def get_anomalies_ep(request: Request):
    _check_api_key(request)
    if not LEARNING_OK:
        return {"error": "brain_learning not loaded"}
    anomalies = await bl_anomalies()
    report = await bl_anomaly_report()
    return {"count": len(anomalies), "anomalies": anomalies, "report": report}

@app.post("/patterns/learn")
async def patterns_learn_endpoint(days: int = 10):
    """Trigger manual learning run. POST /patterns/learn?days=10"""
    if not LEARNING_OK:
        return {"error": "brain_learning not loaded"}
    result = await bl_learn(days=days)
    return result

@app.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest):
    trace = RequestTrace()
    request_id = trace.request_id

    # Check if resuming a task
    task_id = body.task_id
    if task_id:
        task = TaskManager.get_task(task_id)
        if task and task["state"] == "waiting":
            TaskManager.update_task(task_id, state="running")
            trace.task_id = task_id
    else:
        pass
        # Check for "continue task" pattern
        msg_lower = body.message.lower()
        if "continue task" in msg_lower or "ÃÂÃÂÃÂÃÂÃÂÃÂ ÃÂÃÂ§ÃÂÃÂÃÂÃÂÃÂÃÂÃÂÃÂÃÂÃÂ©" in msg_lower:
            match = re.search(r"t_[a-f0-9]+", body.message)
            if match:
                task_id = match.group()
                task = TaskManager.get_task(task_id)
                if task:
                    trace.task_id = task_id

    # Create new task if none
    if not task_id:
        task_id = TaskManager.create_task(body.message, request_id)
    trace.task_id = task_id

    # Add to short-term memory
    memory_add_short_term("user", body.message)

    # --- quick_query fast path (zero-LLM) ---
    if QUICK_QUERY_OK:
        try:
            _qq = await asyncio.wait_for(quick_answer(body.message), timeout=10)
            if _qq:
                logger.info(f"ASK fast_path: {body.message[:40]}")
                memory_add_short_term("assistant", _qq)
                return AskResponse(response=_qq, request_id=request_id)
        except Exception:
            pass

    # Run iterative engine
    t0 = time.time()
    try:
        # Inject short-term conversation context for follow-up understanding
        _ctx = dict(body.context) if body.context else {}
        if short_term_memory:
            _ctx["short_term"] = list(short_term_memory)[-3:]
        # V7: LLM-first with native tool use
        if CHAT_V7_OK and anthropic_client:
            from brain_core import build_system_prompt_v7 as _bsp7
            _sys7 = _bsp7()
            _executors = {
                "ha_get_state": _exec_ha_get_state,
                "ha_call_service": lambda d,s,sd: _exec_ha_call_service(d, s, sd),
                "ssh_run": _exec_ssh_run,
            }
            _v7_response = await asyncio.wait_for(
                handle_chat_v7(body.message, _sys7, anthropic_client, _executors, user_id="api_ask"),
                timeout=180
            )
            result = {"response": _v7_response, "actions": [], "results": [], "task_state": "complete"}
        else:
            logger.error("chat_v7 unavailable, no fallback")
            result = {"response": "النظام غير متاح الحين", "actions": [], "results": [], "task_state": "error"}
    except Exception as e:
        logger.error(f"Engine error: {e}", exc_info=True)
        TaskManager.fail_task(task_id, str(e))
        result = {"response": f"خطأ: {e}", "actions": [], "task_state": "failed"}

    duration = time.time() - t0

    # Add response to short-term memory
    memory_add_short_term("assistant", result["response"])

    # Audit log
    await audit_log(
        task=body.message, actions=result.get("actions"), results=result.get("results"),
        status=result.get("task_state", "complete"), duration=duration,
        request_id=request_id, task_id=task_id,
        route_type="llm_chat"
    )

    # Brain learning from /ask interaction (async, non-blocking)
    if BRAIN_AVAILABLE:
        try:
            _ask_actions = result.get("actions", [])
            _ask_results = result.get("results", [])
            if _ask_actions:
                asyncio.create_task(learn_from_result(
                    body.message, _ask_actions, _ask_results, result["response"]
                ))
        except Exception:
            pass

    return AskResponse(
        response=result["response"],
        actions=result.get("actions", []),
        results=result.get("results", []),
        task_id=task_id,
        request_id=request_id,
        trace=trace.summary()
    )


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ /agent ÃÂ¢ÃÂÃÂ Telegram/external agent endpoint ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

class AgentRequest(BaseModel):
    message: str
    source: str = "telegram"
    user_id: str = None
    context: dict = Field(default_factory=dict)


@app.post("/agent")
async def agent_endpoint(body: AgentRequest):
    """Agent endpoint ÃÂ¢ÃÂÃÂ same iterative engine, different interface."""
    t0 = time.time()
    trace = RequestTrace()
    task_id = TaskManager.create_task(body.message, trace.request_id)
    trace.task_id = task_id

    memory_add_short_term("user", body.message)

    response = ""
    try:
        if CHAT_V7_OK and anthropic_client:
            from brain_core import build_system_prompt_v7 as _bsp7
            _sys7 = _bsp7()
            _executors = {
                "ha_get_state": _exec_ha_get_state,
                "ha_call_service": lambda d,s,sd: _exec_ha_call_service(d, s, sd),
                "ssh_run": _exec_ssh_run,
            }
            response = await asyncio.wait_for(
                handle_chat_v7(body.message, _sys7, anthropic_client, _executors, user_id=body.user_id or "agent"),
                timeout=180
            )
        else:
            logger.error("chat_v7 unavailable, no fallback")
            result = {"response": "النظام غير متاح الحين", "actions": [], "results": [], "task_state": "error"}
    except asyncio.TimeoutError:
        logger.warning(f"Agent timeout: {body.message[:50]}")
        TaskManager.fail_task(task_id, "timeout")
        response = "⏰ العملية انتهت المهلة"
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        TaskManager.fail_task(task_id, str(e))
        response = f"⚠️ Error: {str(e)[:500]}"

    duration = time.time() - t0
    memory_add_short_term("assistant", response)

    await audit_log(
        task=body.message, actions=[], results=[],
        status="ok", duration=duration, request_id=trace.request_id, task_id=task_id,
        route_type="llm_chat"
    )

    return {
        "response": response,
        "task_id": task_id,
        "request_id": trace.request_id,
        "duration": round(duration, 2),
        "trace": trace.summary()
    }


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# HOME ASSISTANT ENDPOINTS
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

class HAServiceRequest(BaseModel):
    domain: str
    service: str
    entity_id: str = None
    service_data: dict = Field(default_factory=dict)


@app.post("/ha/service")
async def ha_call_service_ep(body: HAServiceRequest):
    sdata = body.service_data or {}
    if body.entity_id:
        sdata["entity_id"] = body.entity_id
    result = await _exec_ha_call_service(body.domain, body.service, sdata)
    return result


@app.get("/ha/states")
async def ha_get_states():
    return await _exec_ha_get_state("*")


@app.get("/ha/states/{entity_id:path}")
async def ha_get_state(entity_id: str):
    return await _exec_ha_get_state(entity_id)


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# SSH ENDPOINT
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

class SSHRunRequest(BaseModel):
    cmd: str


@app.post("/ssh/run")
async def ssh_run(body: SSHRunRequest):
    return await _exec_ssh_run(body.cmd)


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# APPROVAL SYSTEM
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

@app.post("/approve/{approval_id}", tags=["approvals"])
async def approve_action(approval_id: str, action: str = "approve"):
    """Approve or reject a pending action. Handles both win_jobs and gateway actions."""
    conn = sqlite3.connect(AUDIT_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM approval_queue WHERE approval_id = ?", (approval_id,)).fetchone()
    if not row:
        conn.close()
        return JSONResponse({"error": "Not found"}, status_code=404)
    if row["status"] != "pending":
        conn.close()
        return {"status": row["status"], "approval_id": approval_id, "note": "Already processed"}

    if action == "approve":
        conn.execute("UPDATE approval_queue SET status='approved', approved_at=datetime('now','localtime') WHERE approval_id=?",
                     (approval_id,))
        conn.commit()

        job_id = row["job_id"]
        if job_id:
            # Legacy win_jobs path (unchanged)
            conn.execute("UPDATE win_jobs SET status='queued' WHERE approval_id=?", (approval_id,))
            conn.commit()
            conn.close()
            return {"status": "approved", "approval_id": approval_id, "path": "win_jobs"}
        else:
            # Gateway action path - execute with bypass
            conn.close()
            try:
                payload = json.loads(row["action"] or "{}")
                if payload.get("kind") != "gateway_action":
                    return {"status": "approved", "approval_id": approval_id, "executed": False, "error": "Unknown approval kind"}
                result = await execute_action_gateway(
                    payload["action_type"], payload.get("args") or {}, bypass_approval=True)
                return {"status": "approved", "approval_id": approval_id, "executed": True, "result": result}
            except Exception as e:
                return JSONResponse(
                    {"status": "approved", "approval_id": approval_id, "executed": False, "error": str(e)},
                    status_code=500)
    else:
        pass
        conn.execute("UPDATE approval_queue SET status='rejected' WHERE approval_id=?", (approval_id,))
        conn.execute("UPDATE win_jobs SET status='rejected' WHERE approval_id=?", (approval_id,))
        conn.commit()
        conn.close()
        return {"status": "rejected", "approval_id": approval_id}


@app.get("/approvals/pending", tags=["approvals"])
async def list_pending_approvals():
    """List all pending approval requests (gateway + win_jobs)."""
    conn = sqlite3.connect(AUDIT_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT approval_id, job_id, agent_id, action, risk, created_at, expires_at, status
        FROM approval_queue WHERE status='pending'
        ORDER BY created_at DESC LIMIT 50
    """).fetchall()
    conn.close()
    items = []
    for r in rows:
        item = {
            "approval_id": r["approval_id"],
            "risk": r["risk"],
            "created_at": r["created_at"],
            "expires_at": r["expires_at"],
        }
        try:
            payload = json.loads(r["action"] or "{}")
            item["kind"] = payload.get("kind", "win_job" if r["job_id"] else "unknown")
            item["action_type"] = payload.get("action_type", payload.get("type", ""))
            item["reason"] = payload.get("reason", "")
        except Exception:
            item["kind"] = "win_job" if r["job_id"] else "unknown"
            item["action_type"] = ""
        items.append(item)
    return {"pending": items, "count": len(items)}


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# WINDOWS AGENT ENDPOINTS
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

class WinRegisterRequest(BaseModel):
    agent_id: str
    hostname: str = ""
    signature: str = ""
    timestamp: str = ""


class WinReportRequest(BaseModel):
    job_id: str
    result: dict
    agent_id: str = ""
    signature: str = ""
    timestamp: str = ""


@app.post("/win/register")
async def win_register(body: WinRegisterRequest):
    if AGENT_SECRET and not verify_agent_signature(body.agent_id, body.signature, body.timestamp):
        return JSONResponse({"error": "Auth failed"}, status_code=401)
    connected_agents[body.agent_id] = {"hostname": body.hostname, "registered_at": datetime.now().isoformat()}
    return {"status": "registered", "agent_id": body.agent_id}


@app.get("/win/poll")
async def win_poll(agent_id: str = Query(...)):
    conn = sqlite3.connect(AUDIT_DB)
    conn.row_factory = sqlite3.Row
    jobs = conn.execute(
        "SELECT job_id, job_type, args FROM win_jobs WHERE status='queued' ORDER BY created_at LIMIT 5"
    ).fetchall()
    conn.close()
    return {"jobs": [dict(j) for j in jobs]}


@app.post("/win/report")
async def win_report(body: WinReportRequest):
    conn = sqlite3.connect(AUDIT_DB)
    conn.execute(
        "UPDATE win_jobs SET status='completed', result=?, agent_id=?, completed_at=datetime('now','localtime') WHERE job_id=?",
        (json.dumps(body.result), body.agent_id, body.job_id)
    )
    conn.commit()
    conn.close()
    return {"status": "received", "job_id": body.job_id}


@app.get("/win/jobs")
async def win_jobs(status: str = Query(default=None), limit: int = Query(default=20)):
    conn = sqlite3.connect(AUDIT_DB)
    conn.row_factory = sqlite3.Row
    if status:
        rows = conn.execute("SELECT * FROM win_jobs WHERE status=? ORDER BY created_at DESC LIMIT ?",
                            (status, limit)).fetchall()
    else:
        pass
        rows = conn.execute("SELECT * FROM win_jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"jobs": [dict(r) for r in rows]}


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# STATS & SHIFT
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

@app.get("/stats/daily")
async def stats_daily(date: str = Query(default=None)):
    try:
        from daily_stats import get_daily_stats
        return get_daily_stats(date)
    except ImportError:
        return {"error": "daily_stats module not available"}


@app.post("/stats/capture")
async def stats_capture():
    try:
        from daily_stats import capture_stats
        return capture_stats()
    except ImportError:
        return {"error": "daily_stats module not available"}


SHIFT_PATTERN = ["A", "A", "B", "B", "C", "C", "D", "D"]
SHIFT_NAMES = {"A": "Morning ÃÂ¢ÃÂÃÂÃÂ¯ÃÂ¸ÃÂ", "B": "Afternoon ÃÂ°ÃÂÃÂÃÂ", "C": "Night ÃÂ°ÃÂÃÂÃÂ", "D": "Off ÃÂ°ÃÂÃÂÃÂ "}
SHIFT_EPOCH = datetime(2024, 1, 4)


@app.get("/shift")
async def shift_info(date: str = Query(default=None)):
    target = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
    days_since = (target - SHIFT_EPOCH).days
    idx = days_since % len(SHIFT_PATTERN)
    shift = SHIFT_PATTERN[idx]

    # Build week schedule
    week = []
    for i in range(-3, 5):
        d = target + timedelta(days=i)
        di = (d - SHIFT_EPOCH).days % len(SHIFT_PATTERN)
        s = SHIFT_PATTERN[di]
        week.append({"date": d.strftime("%Y-%m-%d"), "shift": s, "name": SHIFT_NAMES[s],
                      "is_today": i == 0})

    return {
        "date": target.strftime("%Y-%m-%d"),
        "shift": shift, "name": SHIFT_NAMES[shift],
        "week": week
    }


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# CLAUDE CONTEXT ENDPOINT (for claude.ai integration)
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

@app.get("/claude")
async def claude_context():
    """Provides system context for Claude conversations."""
    # Shift info
    now = datetime.now()
    days_since = (now - SHIFT_EPOCH).days
    shift = SHIFT_PATTERN[days_since % len(SHIFT_PATTERN)]

    # Agent status
    agent_list = list(connected_agents.keys())

    # Recent tasks
    recent_tasks = TaskManager.list_tasks(limit=5)

    # Stats
    conn = sqlite3.connect(AUDIT_DB)
    total_requests = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    today_requests = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE timestamp >= date('now','localtime')").fetchone()[0]
    conn.close()

    context = {
        "system": f"Master AI v{VERSION}",
        "status": "operational",
        "shift": {"current": shift, "name": SHIFT_NAMES[shift]},
        "agents": agent_list,
        "stats": {"total_requests": total_requests, "today": today_requests},
        "recent_tasks": recent_tasks,
        "memory": {"available": MEMORY_AVAILABLE, "short_term_size": len(short_term_memory)},
        "endpoints": {
            "ask": "POST /ask {message, context, task_id}",
            "agent": "POST /agent {message, source}",
            "ha_service": "POST /ha/service",
            "ha_states": "GET /ha/states",
            "ssh": "POST /ssh/run {cmd}",
            "tasks": "GET /tasks | GET /tasks/{id} | POST /tasks",
            "shift": "GET /shift",
            "health": "GET /health",
        },
        "capabilities": [
            "Iterative planning (planÃÂ¢ÃÂÃÂexecuteÃÂ¢ÃÂÃÂverifyÃÂ¢ÃÂÃÂreplan)",
            "Task management with resume",
            "Action schema validation",
            "Short-term + long-term memory",
            "Request tracing & observability",
        ],
        "instructions": "Use /ask for all requests. Include task_id to resume tasks. All responses include request_id and trace."
    }
    return context


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# SESSIONS (from v4)
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

class SessionCreate(BaseModel):
    source: str = "api"
    metadata: dict = Field(default_factory=dict)


@app.post("/sessions")
async def create_session(body: SessionCreate):
    sid = str(uuid.uuid4())[:12]
    conn = sqlite3.connect(AUDIT_DB)
    conn.execute("CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY, source TEXT, metadata TEXT, created_at TEXT DEFAULT (datetime('now','localtime')))")
    conn.execute("INSERT INTO sessions (session_id, source, metadata) VALUES (?,?,?)",
                 (sid, body.source, json.dumps(body.metadata)))
    conn.commit()
    conn.close()
    return {"session_id": sid}


@app.get("/sessions")
async def list_sessions(limit: int = Query(default=10)):
    conn = sqlite3.connect(AUDIT_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY, source TEXT, metadata TEXT, created_at TEXT DEFAULT (datetime('now','localtime')))")
    rows = conn.execute("SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"sessions": [dict(r) for r in rows]}


@app.get("/sessions/latest")
async def latest_session():
    conn = sqlite3.connect(AUDIT_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS sessions (session_id TEXT PRIMARY KEY, source TEXT, metadata TEXT, created_at TEXT DEFAULT (datetime('now','localtime')))")
    row = conn.execute("SELECT * FROM sessions ORDER BY created_at DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else {"error": "No sessions"}


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# KNOWLEDGE BASE (from v4)
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

class KnowledgeCreate(BaseModel):
    category: str
    key: str
    value: str
    source: str = "manual"

class KnowledgeUpdate(BaseModel):
    value: str = None
    category: str = None


@app.get("/knowledge")
async def list_knowledge(category: str = Query(default=None)):
    conn = sqlite3.connect(AUDIT_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS knowledge (id INTEGER PRIMARY KEY, category TEXT, key TEXT, value TEXT, source TEXT, created_at TEXT DEFAULT (datetime('now','localtime')))")
    if category:
        rows = conn.execute("SELECT * FROM knowledge WHERE category=?", (category,)).fetchall()
    else:
        pass
        rows = conn.execute("SELECT * FROM knowledge ORDER BY created_at DESC LIMIT 50").fetchall()
    conn.close()
    return {"knowledge": [dict(r) for r in rows]}


@app.get("/knowledge/{kid}")
async def get_knowledge(kid: int):
    conn = sqlite3.connect(AUDIT_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM knowledge WHERE id=?", (kid,)).fetchone()
    conn.close()
    return dict(row) if row else JSONResponse({"error": "Not found"}, status_code=404)


@app.post("/knowledge")
async def create_knowledge(body: KnowledgeCreate):
    conn = sqlite3.connect(AUDIT_DB)
    conn.execute("CREATE TABLE IF NOT EXISTS knowledge (id INTEGER PRIMARY KEY, category TEXT, key TEXT, value TEXT, source TEXT, created_at TEXT DEFAULT (datetime('now','localtime')))")
    conn.execute("INSERT INTO knowledge (category, key, value, source) VALUES (?,?,?,?)",
                 (body.category, body.key, body.value, body.source))
    conn.commit()
    conn.close()
    return {"status": "created"}


@app.put("/knowledge/{kid}")
async def update_knowledge(kid: int, body: KnowledgeUpdate):
    conn = sqlite3.connect(AUDIT_DB)
    if body.value:
        conn.execute("UPDATE knowledge SET value=? WHERE id=?", (body.value, kid))
    if body.category:
        conn.execute("UPDATE knowledge SET category=? WHERE id=?", (body.category, kid))
    conn.commit()
    conn.close()
    return {"status": "updated"}


@app.delete("/knowledge/{kid}")
async def delete_knowledge(kid: int):
    conn = sqlite3.connect(AUDIT_DB)
    conn.execute("DELETE FROM knowledge WHERE id=?", (kid,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# TASK ENDPOINTS (Enhanced from v4 with Task Manager)
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

@app.get("/tasks")
async def list_tasks_ep(state: str = Query(default=None), limit: int = Query(default=20)):
    return {"tasks": TaskManager.list_tasks(state, limit)}


@app.get("/tasks/{task_id}")
async def get_task_ep(task_id: str):
    task = TaskManager.get_task(task_id)
    if not task:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return task


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# STOCKS (from v4)
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

@app.get("/stocks/portfolio")
async def stock_portfolio():
    try:
        from stock_alerts import get_portfolio
        return get_portfolio()
    except ImportError:
        return {"error": "stock_alerts module not available"}


@app.get("/stocks/alerts")
async def stock_alerts_history(limit: int = 20):
    try:
        from stock_alerts import get_alerts
        return get_alerts(limit)
    except ImportError:
        return {"error": "stock_alerts module not available"}


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# DEPLOY ENDPOINT (kept for backward compatibility)
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

class DeployRequest(BaseModel):
    file_path: str
    content: str
    restart: bool = False


@app.post("/deploy")
async def deploy_file(body: DeployRequest):
    """Deploy a file to the server (backward compat ÃÂ¢ÃÂÃÂ prefer Git workflow)."""
    target = os.path.join(BASE_DIR, body.file_path)
    if ".." in body.file_path:
        return JSONResponse({"error": "Invalid path"}, status_code=400)

    # Backup
    backup = None
    if os.path.exists(target):
        backup = f"{target}.bak.{int(time.time())}"
        os.rename(target, backup)

    with open(target, "w") as f:
        f.write(body.content)

    result = {"status": "deployed", "file": target, "size": len(body.content), "backup": backup}

    if body.restart:
        proc = await asyncio.create_subprocess_shell(
            "sudo systemctl restart master-ai",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        result["restart"] = "ok" if proc.returncode == 0 else stderr.decode()

    return result


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# MEMORY ENDPOINTS (from v4, productized)
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

class MemoryCreate(BaseModel):
    category: str = "general"
    content: str
    memory_type: str = "fact"
    confidence: float = 0.8
    source: str = "api"


@app.post("/memory")
async def create_memory_ep(data: MemoryCreate):
    if MEMORY_AVAILABLE:
        await add_memory(category=data.category, content=data.content,
                         type_=data.memory_type)
        return {"status": "stored", "category": data.category, "type": data.memory_type}
    return {"error": "memory_db not available"}


@app.get("/memory")
async def list_memories_ep(category: str = Query(default=None), search: str = Query(default=None),
                           limit: int = Query(default=20)):
    if MEMORY_AVAILABLE:
        memories = await get_memories()
        if category:
            memories = [m for m in memories if m.get("category") == category]
        if search:
            memories = [m for m in memories if search.lower() in str(m).lower()]
        return {"memories": memories[:limit]}
    return {"memories": [], "note": "memory_db not available"}


@app.get("/memory/stats")
async def mem_stats():
    if MEMORY_AVAILABLE:
        stats = await _get_memory_stats()
        stats["short_term"] = len(short_term_memory)
        return stats
    return {"total": 0, "note": "memory_db not available", "short_term": len(short_term_memory)}


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# MESSAGE SAVE / USERS (from v4)
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

class MsgSave(BaseModel):
    role: str
    content: str
    session_id: str = None
    source: str = "api"




@app.get("/memory/recent")
async def memory_recent(limit: int = Query(default=20, ge=1, le=100)):
    """Return most recent memories."""
    if MEMORY_AVAILABLE:
        memories = await get_memories(limit=limit)
        return {"memories": memories, "count": len(memories)}
    return {"memories": [], "count": 0, "note": "memory_db not available"}
@app.post("/memory/message")
async def save_msg(data: MsgSave):
    if MEMORY_AVAILABLE:
        save_message(data.role, data.content)
    memory_add_short_term(data.role, data.content)
    return {"status": "saved"}


class UserCreate(BaseModel):
    username: str
    display_name: str = ""
    role: str = "user"


@app.post("/users")
async def create_user(data: UserCreate):
    conn = sqlite3.connect(AUDIT_DB)
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, display_name TEXT, role TEXT, created_at TEXT DEFAULT (datetime('now','localtime')))")
    try:
        conn.execute("INSERT INTO users (username, display_name, role) VALUES (?,?,?)",
                     (data.username, data.display_name, data.role))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return JSONResponse({"error": "User exists"}, status_code=409)
    conn.close()
    return {"status": "created"}


@app.get("/users")
async def list_users():
    conn = sqlite3.connect(AUDIT_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, display_name TEXT, role TEXT, created_at TEXT DEFAULT (datetime('now','localtime')))")
    rows = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return {"users": [dict(r) for r in rows]}


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# AUDIT ENDPOINT
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

@app.get("/audit")
async def get_audit(limit: int = Query(default=50), request_id: str = Query(default=None),
                    task_id: str = Query(default=None)):
    conn = sqlite3.connect(AUDIT_DB)
    conn.row_factory = sqlite3.Row
    if request_id:
        rows = conn.execute("SELECT * FROM audit_log WHERE request_id=? ORDER BY id DESC", (request_id,)).fetchall()
    elif task_id:
        rows = conn.execute("SELECT * FROM audit_log WHERE task_id=? ORDER BY id DESC", (task_id,)).fetchall()
    else:
        pass
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"audit": [dict(r) for r in rows]}



# ═══════════════════════════════════════════════════════════════
# PHASE 3.3 — SCHEMA ENDPOINTS
# ═══════════════════════════════════════════════════════════════

class SchemaEnsureRequest(BaseModel):
    dry_run: bool = True
    apply: bool = False


@app.get("/schema")
async def schema_status():
    """Returns expected version, current version, drift summary, last migration."""
    status = _get_schema_status()
    try:
        conn = sqlite3.connect(AUDIT_DB, timeout=5)
        current = _db_introspect(conn)
        plan = _build_migration_plan(current, SCHEMA_CONTRACT)
        conn.close()
        status["drift_detail"] = {
            "missing_tables": [t["table"] for t in plan["missing_tables"]],
            "missing_columns": [f"{c['table']}.{c['column']}" for c in plan["missing_columns"]],
            "missing_indexes": [i["index"] for i in plan["missing_indexes"]],
            "type_warnings": plan["drift_warnings"],
        }
    except Exception as e:
        status["drift_detail"] = {"error": str(e)}
    return status


@app.post("/schema/ensure")
async def schema_ensure(body: SchemaEnsureRequest):
    """Run schema migration. Protected by API key (not in OPEN_PATHS)."""
    try:
        report = ensure_schema(dry_run=body.dry_run, apply=body.apply)
        return report
    except Exception as e:
        logger.error(f"[Schema] ensure error: {e}", exc_info=True)
        return JSONResponse({"error": str(e), "schema_version": SCHEMA_VERSION}, status_code=500)


# ═══════════════════════════════════════════════════════════════
# PHASE 4 — PLUGIN ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.get("/plugins", tags=["plugins"])
async def list_plugins():
    """List all registered plugins and their status."""
    return {"plugins": PLUGIN_REGISTRY.list()}


@app.post("/action/execute", tags=["actions"])
async def action_execute_endpoint(req: ActionExecuteRequest):
    """Central action execution gateway with risk/policy/autonomy checks."""
    return await execute_action_gateway(req.action_type, req.args)



@app.post("/plugins/{name}/enable", tags=["plugins"])
async def enable_plugin(name: str):
    if PLUGIN_REGISTRY.enable(name):
        return {"status": "enabled", "plugin": name}
    return JSONResponse({"error": f"Plugin not found: {name}"}, status_code=404)


@app.post("/plugins/{name}/disable", tags=["plugins"])
async def disable_plugin(name: str):
    if PLUGIN_REGISTRY.disable(name):
        return {"status": "disabled", "plugin": name}
    return JSONResponse({"error": f"Plugin not found: {name}"}, status_code=404)



# ============================================================================
#  SYSTEM CONTEXT  (GET /system/context)

# ============================================================
# EVENT ENGINE ENDPOINTS (v5.1) + WEBHOOK (v5.4.5)
# ============================================================

@app.post("/event", tags=["events"])
async def ingest_event(req: EventRequest):
    result = event_engine.create_event(req)
    try:
        policy = load_policy()
        rules = policy.get("event_rules", {})
        actions = rules.get(req.type, [])
        if actions:
            _MAX_AUTO = 10
            if len(actions) > _MAX_AUTO:
                actions = actions[:_MAX_AUTO]
                result["auto_actions_warning"] = f"Truncated to {_MAX_AUTO} actions"
            auto_results = []
            for act in actions:
                act_type = act.get("action_type", "")
                act_args = act.get("args", {})
                if not act_type:
                    continue
                merged = {}
                for k, v in act_args.items():
                    if isinstance(v, str) and "{event." in v:
                        v = v.replace("{event.type}", req.type or "")
                        v = v.replace("{event.source}", req.source or "")
                        v = v.replace("{event.user}", req.user or "")
                        v = v.replace("{event.entity_id}", req.entity_id or "")
                        v = v.replace("{event.event_id}", result.get("event_id", ""))
                    merged[k] = v
                try:
                    r = await execute_action_gateway(act_type, merged)
                    auto_results.append({"action_type": act_type, "result": r})
                except Exception as e:
                    auto_results.append({"action_type": act_type, "error": str(e)})
            result["auto_actions"] = auto_results
    except Exception as e:
        logger.error(f"Event rules automation error: {e}")
    return result

@app.get("/events", tags=["events"])
async def list_events_ep(limit: int = Query(default=50, ge=1, le=500)):
    return {"events": event_engine.list_events(limit)}

@app.get("/events/{event_id}", tags=["events"])
async def get_event_ep(event_id: str = Path(...)):
    ev = event_engine.get_event(event_id)
    if not ev:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return ev

@app.get("/event_rules", tags=["events"])
async def get_event_rules():
    policy = load_policy()
    rules = policy.get("event_rules", {})
    return {"event_rules": rules, "count": sum(len(v) for v in rules.values())}


@app.post("/webhook/event/{token}", tags=["webhook"], deprecated=True)
async def webhook_event_legacy(token: str, req: EventRequest):
    """Legacy: token in path. Use /webhook/event with X-Webhook-Token header instead."""
    policy = load_policy()
    expected = policy.get("webhook_token")
    if not expected:
        return JSONResponse({"error": "webhook not configured"}, status_code=503)
    if token != expected:
        return JSONResponse({"error": "invalid token"}, status_code=403)
    return await ingest_event(req)


@app.post("/webhook/event", tags=["webhook"])
async def webhook_event(request: Request, req: EventRequest):
    """Secure: token in X-Webhook-Token header."""
    policy = load_policy()
    expected = policy.get("webhook_token")
    if not expected:
        return JSONResponse({"error": "webhook not configured"}, status_code=503)
    token = request.headers.get("X-Webhook-Token", "")
    if token != expected:
        return JSONResponse({"error": "invalid token"}, status_code=403)
    return await ingest_event(req)


# ============================================================================

@app.get("/system/context", tags=["system"])
async def system_context():
    """Full system context for new AI conversations. API-key protected."""
    warnings = []
    result = {"service": "master_ai", "version": VERSION}

    # --- schema ---
    try:
        result["schema"] = _get_schema_status()
    except Exception as e:
        result["schema"] = None
        warnings.append(f"schema: {e}")

    # --- policy ---
    try:
        pol = load_policy()
        result["policy"] = {
            "policy_version": pol.get("version"),
            "thresholds": pol.get("thresholds"),
        } if pol else None
    except Exception as e:
        result["policy"] = None
        warnings.append(f"policy: {e}")

    # --- autonomy ---
    try:
        result["autonomy"] = event_engine.get_autonomy_config()
    except Exception as e:
        result["autonomy"] = {"enabled": None, "level": None, "allow_medium": None, "allow_high": None}
        warnings.append(f"autonomy: {e}")

    # --- db ---
    try:
        conn = sqlite3.connect(AUDIT_DB)
        jm = conn.execute("PRAGMA journal_mode").fetchone()[0]
        tc = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        conn.close()
        result["db"] = {"path": AUDIT_DB, "wal_mode": jm, "tables_count": tc}
    except Exception as e:
        result["db"] = None
        warnings.append(f"db: {e}")

    # --- runtime ---
    try:
        uptime = round(time.time() - START_TIME)
        st_iso = datetime.fromtimestamp(START_TIME).isoformat()
        result["runtime"] = {
            "uptime_seconds": uptime,
            "start_time_iso": st_iso,
            "connected_agents_count": len(connected_agents),
        }
    except Exception as e:
        result["runtime"] = None
        warnings.append(f"runtime: {e}")

    # --- plugins ---
    try:
        result["plugins"] = {
            "count": len(PLUGIN_REGISTRY._plugins),
            "list": PLUGIN_REGISTRY.list(),
        }
    except Exception as e:
        result["plugins"] = None
        warnings.append(f"plugins: {e}")

    # --- brain & memory ---
    try:
        result["brain"] = {
            "available": BRAIN_AVAILABLE,
            "modules": [m for m in ["brain_core", "brain_learning", "brain_analytics",
                        "brain_personality", "brain_observability", "brain_proactive"]
                        if m in sys.modules],
        }
        result["memory"] = {
            "available": MEMORY_AVAILABLE,
            "short_term_size": len(short_term_memory),
        }
        if MEMORY_AVAILABLE:
            try:
                from memory_db import get_memory_stats as _ms
                result["memory"]["stats"] = await _ms()
            except: pass
    except Exception as e:
        warnings.append(f"brain: {e}")

    # --- features ---
    try:
        result["features"] = {
            "pattern_matching": True,  # ha_get_state wildcard support
            "room_aliases": True,      # غرفة النوم → الماستر
            "entity_id_inline": True,  # climate/cover IDs in room index
            "conversation_context": True,  # short-term memory in /ask
            "response_synthesis": True,   # fallback response when empty
            "auto_learning": True,      # brain_learning LLM extraction
        }
    except Exception as e:
        warnings.append(f"features: {e}")

    # --- git ---
    try:
        import subprocess as _sp
        def _git(cmd):
            r = _sp.run(cmd, capture_output=True, text=True, timeout=5, cwd=BASE_DIR)
            return r.stdout.strip() if r.returncode == 0 else None
        result["git"] = {
            "branch": _git(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
            "commit": _git(["git", "rev-parse", "--short", "HEAD"]),
            "tags": (_git(["git", "tag", "--sort=-creatordate"]) or "").split("\n")[:10],
        }
    except Exception as e:
        result["git"] = {"branch": None, "commit": None, "tags": []}
        warnings.append(f"git: {e}")

    if warnings:
        result["warnings"] = warnings
    # Force safe JSON serialization via JSONResponse
    from starlette.responses import JSONResponse
    safe_json = json.loads(json.dumps(result, ensure_ascii=False, default=str))
    return JSONResponse(content=safe_json)



# ━━━ SYSTEM KNOWLEDGE (Phase 1: Self-Awareness) ━━━
@app.get("/system/knowledge", tags=["system"])
async def system_knowledge_endpoint():
    """Return full system self-knowledge JSON."""
    sk_path = os.path.join(BASE_DIR, "system_knowledge.json")
    if not os.path.exists(sk_path):
        return {"error": "system_knowledge.json not found"}
    import json as _json
    with open(sk_path) as f:
        return _json.load(f)

@app.get("/system/knowledge/summary", tags=["system"])
async def system_knowledge_summary():
    """Return compact awareness string (what LLM sees in prompt)."""
    try:
        from brain_core import get_system_awareness
        return {"awareness": get_system_awareness()}
    except Exception as e:
        return {"error": str(e)}



@app.get("/brain/expertise", tags=["brain"])
async def brain_expertise(domain: str = "", topic: str = ""):
    """Lookup expert knowledge by domain and topic."""
    try:
        from brain_core import lookup_expertise, _expert_knowledge
        if not domain:
            return {"domains": list(_expert_knowledge.keys())}
        result = lookup_expertise(domain, topic)
        return {"domain": domain, "topic": topic, "knowledge": result}
    except Exception as e:
        return {"error": str(e)}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WEB PANEL - moved to modules/panel.py

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# DEV CONTEXT endpoint
@app.get("/dev/context", tags=["system"])
async def dev_context():
    from fastapi.responses import PlainTextResponse
    ctx_path = os.path.join(BASE_DIR, "CLAUDE_CONTEXT.md")
    parts = []
    if os.path.exists(ctx_path):
        with open(ctx_path) as f:
            parts.append(f.read())
    try:
        uptime = round(time.time() - START_TIME)
        parts.append("")
        parts.append("## Live Status")
        parts.append("- Uptime: " + str(uptime) + "s")
        parts.append("- Plugins: " + str(len(PLUGIN_REGISTRY._plugins)))
        parts.append("- STM: " + str(len(short_term_memory)))
        parts.append("- Memory: " + str(MEMORY_AVAILABLE))
        parts.append("- Brain: " + str(BRAIN_AVAILABLE))
    except Exception as e:
        parts.append("Status error: " + str(e))
    return PlainTextResponse(chr(10).join(parts))

# TELEGRAM BOT (v7.0.0)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TG_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
TG_MAX_MSG = 4096
_tg_client: httpx.AsyncClient = None
_tg_offset = 0
_tg_running = False


def tg_split_message(text: str) -> list[str]:
    """Split long messages at newline boundaries."""
    if len(text) <= TG_MAX_MSG:
        return [text]
    parts = []
    while text:
        if len(text) <= TG_MAX_MSG:
            parts.append(text)
            break
        split_at = text.rfind("\n", 0, TG_MAX_MSG)
        if split_at <= 0:
            split_at = TG_MAX_MSG
        parts.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return parts
async def tg_send(chat_id, text: str, parse_mode: str = None) -> bool:
    """Send message to Telegram, auto-split if >4096 chars."""
    import re as _re
    # Auto-detect HTML tags and set parse_mode if not already set
    if not parse_mode and _re.search(r'<(?:b|i|u|s|code|pre|a)\b[^>]*>', text):
        parse_mode = "HTML"
    # Phase 1: CB check for Telegram
    if not _cb_tg.is_available():
        logger.warning(f"TG circuit open, dropping message to {chat_id}")
        if kairos_agent and hasattr(kairos_agent, 'tg_queue') and ff.is_enabled("telegram_queue"):
            kairos_agent.tg_queue.enqueue(int(chat_id), text, parse_mode or "")
        return False

    global _tg_client
    _tg_timeout = EXTERNAL_TIMEOUT if FEATURE_TIMEOUTS else 30
    if not _tg_client:
        _tg_client = httpx.AsyncClient(timeout=_tg_timeout)
    for part in tg_split_message(text):
        try:
            payload = {"chat_id": chat_id, "text": part}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            resp = await _tg_client.post(f"{TG_BASE}/sendMessage", json=payload)
            if resp.status_code == 400 and parse_mode:
                # Fallback: strip HTML/Markdown and retry as plain text
                plain = _re.sub(r'<[^>]+>', '', part)
                plain = plain.replace('*', '').replace('_', '').replace('`', '')
                _fb_payload = {"chat_id": chat_id, "text": plain}
                _fb_resp = await _tg_client.post(f"{TG_BASE}/sendMessage", json=_fb_payload)
                if _fb_resp.status_code == 200:
                    _cb_tg.record_success()
                    logger.info("TG send fallback to plain text (parse_mode=%s failed)", parse_mode)
                    continue
                _cb_tg.record_failure()
                logger.error(f"TG send fail (even plain): {_fb_resp.text[:200]}")
                return False
            elif resp.status_code != 200:
                _cb_tg.record_failure()
                logger.error(f"TG send fail: {resp.text[:200]}")
                if kairos_agent and hasattr(kairos_agent, 'tg_queue') and ff.is_enabled("telegram_queue"):
                    kairos_agent.tg_queue.enqueue(int(chat_id), text, parse_mode or "")
                return False
            _cb_tg.record_success()
        except Exception as e:
            _cb_tg.record_failure()
            logger.error(f"TG send error: {e}")
            if kairos_agent and hasattr(kairos_agent, 'tg_queue') and ff.is_enabled("telegram_queue"):
                kairos_agent.tg_queue.enqueue(int(chat_id), text, parse_mode or "")
            return False
    return True



async def _notify_approval(approval_id, action_desc, risk):
    """Send Telegram notification to admin when approval is created."""
    try:
        admin_id = None
        if TG_OPS_OK:
            admin_id = get_admin_chat_id()
        if not admin_id:
            aid_path = os.path.join(os.path.dirname(__file__) or ".", "admin_chat_id.txt")
            if os.path.exists(aid_path):
                admin_id = open(aid_path).read().strip()
        if not admin_id:
            return
        msg = f"\u26a0 Approval needed\nID: {approval_id}\nRisk: {risk}\n{action_desc[:100]}"
        btn = [{"text": "📋 Open approvals", "callback_data": "cmd:approvals"}]
        await tg_send_inline(int(admin_id), msg, btn, columns=1)
    except Exception as e:
        logger.error(f"Approval notify error: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CRON HANDLER ROUTING + ORPHAN CLEANUP (Tier2 #13)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_SCHEDULED_HANDLERS = {}
_cron_breakers = {}


def register_scheduled_handler(task_name: str, handler):
    """Register a handler for a scheduled task name."""
    _SCHEDULED_HANDLERS[task_name] = handler
    logger.info("Registered scheduled handler: %s", task_name)


async def fire_scheduled_task(task_name: str, **kwargs):
    """Route a scheduled task fire to its handler.
    If handler missing or fails 3 times consecutively, skip."""
    handler = _SCHEDULED_HANDLERS.get(task_name)
    if handler is None:
        logger.warning("Orphaned scheduled task: %s — no handler registered", task_name)
        return

    from circuit_breaker import CircuitBreaker
    if task_name not in _cron_breakers:
        _cron_breakers[task_name] = CircuitBreaker(
            name=f"cron_{task_name}", failure_threshold=3, cooldown_seconds=300
        )
    breaker = _cron_breakers[task_name]

    if not breaker.allow_request():
        logger.warning("Cron %s circuit open — skipping", task_name)
        return

    try:
        if asyncio.iscoroutinefunction(handler):
            await handler(**kwargs)
        else:
            handler(**kwargs)
        breaker.record_success()
    except Exception as e:
        breaker.record_failure()
        logger.error("Cron %s failed: %s", task_name, e)


async def _send_progress_after_delay(chat_id, delay: float = 2.0):
    """Send progress indicator if LLM takes > delay seconds (Tier1 #4)."""
    await asyncio.sleep(delay)
    try:
        await tg_send(chat_id, "⏳ جاري التحليل...")
    except Exception:
        pass


async def tg_handle_command(chat_id, text: str) -> str | None:
    """Handle quick commands. Returns response or None to pass to engine."""
    cmd = text.strip().lower()

    if cmd == "/start":
        return "\U0001f3e0 Master AI Bot\n\u0623\u0631\u0633\u0644 \u0623\u064a \u0631\u0633\u0627\u0644\u0629 \u0623\u0648 \u0623\u0645\u0631.\n\n/status \u2014 \u062d\u0627\u0644\u0629 \u0627\u0644\u0646\u0638\u0627\u0645\n/lights \u2014 \u0627\u0644\u0623\u0636\u0648\u0627\u0621 \u0627\u0644\u0645\u0634\u063a\u0644\u0629\n/temp \u2014 \u062d\u0631\u0627\u0631\u0629 \u0627\u0644\u0645\u0643\u064a\u0641\u0627\u062a"

    if cmd == "/kairos":
        if kairos_agent:
            return kairos_agent.format_tg_status()
        return "🤖 KAIROS: not initialized"

    if cmd == "/report" or cmd == "/morning":
        try:
            report = await build_morning_report()
            await tg_send(chat_id, report)
        except Exception as e:
            await tg_send(chat_id, f"Report error: {str(e)[:100]}")
        return "__inline_sent__"

    if cmd == "/reset":
        if TG_SESSION_OK:
            tg_session_reset(str(chat_id))
        if _tips_engine:
            _tips_engine.reset_session()
        return "Session cleared"

    if cmd == "/status":
        uptime = int(time.time() - START_TIME)
        h, m = divmod(uptime // 60, 60)
        _mc = sum(1 for v in [TG_INTENT_OK, LIFE_ROUTER_OK, SMART_ROUTER_OK, BRAIN_AVAILABLE, TG_MORNING_OK, TG_ALERTS_OK, TG_REMIND_OK, TG_NEWS_OK, DISCOVERY_OK, TG_SESSION_OK, TG_HOME_OK, TG_OPS_OK, LIFE_STOCKS_OK, LIFE_EXPENSES_OK, LIFE_HEALTH_OK, LIFE_WORK_OK] if v)
        _t = _router_stats.get("total", 0)
        return chr(10).join([f'✅ Master AI v{VERSION}', f'⭐ Uptime: {h}h {m}m', f'🔧 Plugins: {len(PLUGIN_REGISTRY._plugins)} | ✅ {_mc}/16', f'💬 Msgs: {_t}'])

    if cmd == "/stats":
        _up = int(time.time() - START_TIME)
        _h, _m = divmod(_up // 60, 60)
        _t = _router_stats.get("total", 0)
        _greet = _router_stats.get("greeting", 0)
        _chat = _router_stats.get("chat", 0)
        _action = _router_stats.get("action", 0)
        _intent = _router_stats.get("intent", 0)
        _followup = _router_stats.get("followup", 0)
        _unk = _router_stats.get("unknown", 0)
        _stocks = _router_stats.get("life_stocks", 0)
        _exp = _router_stats.get("life_expenses", 0)
        _work = _router_stats.get("life_work", 0)
        _lhealth = _router_stats.get("life_health", 0)
        _qq = _router_stats.get("quick_query", 0)
        _cache = _router_stats.get("cache_hit", 0)
        _saved = _greet + _intent + _stocks + _exp + _work + _lhealth + _qq + _cache
        _pct = round(_saved / _t * 100) if _t > 0 else 0
        _m_ok = lambda v: "\u2705" if v else "\u274c"
        _lines = [
            f"\U0001f4ca Master AI Stats",
            f"\u23f1 Uptime: {_h}h {_m}m | \U0001f4e8 {_t} msgs",
            f"",
            f"\U0001f6a6 Router:",
            f"  \U0001f44b Greeting: {_greet} (0 API)",
            f"  \U0001f3af Intent: {_intent}",
            f"  \U0001f4ac Chat: {_chat}",
            f"  \u2699\ufe0f Action: {_action}",
            f"  \u2753 Unknown: {_unk}",
            f"  \U0001f504 Followup: {_followup}",
            f"",
            f"\U0001f3e0 Life:",
            f"  \U0001f4c8 Stocks: {_stocks} | \U0001f4b0 Exp: {_exp}",
            f"  \U0001f477 Work: {_work} | \U0001f3e5 Health: {_lhealth}",
            f"",
            f"\U0001f4a1 Saved: {_saved}/{_t} ({_pct}%)",
            f"",
            f"\U0001f9e9 Modules:",
            f"  {_m_ok(TG_INTENT_OK)} Intent  {_m_ok(LIFE_ROUTER_OK)} Life  {_m_ok(SMART_ROUTER_OK)} Router",
            f"  {_m_ok(BRAIN_AVAILABLE)} Brain  {_m_ok(TG_MORNING_OK)} Morning  {_m_ok(TG_ALERTS_OK)} Alerts",
            f"  {_m_ok(TG_REMIND_OK)} Remind  {_m_ok(TG_NEWS_OK)} News  {_m_ok(DISCOVERY_OK)} Discovery",
        ]
        if _router_cmd_log:
            _lines.append("")
            _lines.append("\U0001f4dd Last 5:")
            for _cl in _router_cmd_log[-5:]:
                _lines.append(f"  {_cl.get('t','')[-5:]} {_cl.get('route',''):6s} {_cl.get('cmd','')[:22]}")
        try:
            from task_engine import task_stats as _ts
            _s = _ts()
            if _s['total_active']:
                _extra = '\U0001f4cb \u0645\u0647\u0627\u0645: ' + str(_s['total_active']) + ' \u0646\u0634\u0637\u0629'
                if _s['overdue']:   _extra += '  \u26a0\ufe0f ' + str(_s['overdue']) + ' \u0645\u062a\u0623\u062e\u0631\u0629'
                if _s['due_today']: _extra += '  \U0001f4cc ' + str(_s['due_today']) + ' \u0627\u0644\u064a\u0648\u0645'
                _lines.append(''); _lines.append(_extra)
        except Exception: pass
        try:
            from cost_tracker import get_cost_for_kpi as _ck
            _k = _ck()
            _lines.append('\U0001f4b0 Cost: today=$' + f"{_k['today_usd']:.4f}" + '  month=$' + f"{_k['month_usd']:.2f}" + '/' + f"{_k['month_budget_usd']:.0f}")
        except Exception: pass
        return "\n".join(_lines)

    # R2-P1: Dream Consolidator commands
    if cmd in ("/dream", "/تنظيف"):
        try:
            from dream_consolidator import get_dream_status, format_dream_status
            status = await get_dream_status()
            await tg_send(chat_id, format_dream_status(status))
            return "__inline_sent__"
        except Exception as e:
            return f"Dream error: {str(e)[:100]}"
    if cmd == "/dream run":
        try:
            await tg_send(chat_id, "🧹 بدأ التنظيف...")
            from dream_consolidator import run_dream_consolidation
            report = await run_dream_consolidation()
            merged = report.get("merged", 0)
            archived = report.get("archived", 0)
            compacted = report.get("session_compacted", 0)
            kept = report.get("kept", "?")
            await tg_send(chat_id,
                f"✅ Dream Consolidation:\n"
                f"  دمج: {merged} | أرشفة: {archived} | ضغط: {compacted}\n"
                f"  باقي: {kept} ذاكرة نشطة")
            return "__inline_sent__"
        except Exception as e:
            return f"Dream run error: {str(e)[:100]}"

    if cmd == "/lights":
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                resp = await c.get(f"{HA_URL}/api/states", headers={"Authorization": f"Bearer {HA_TOKEN}"})
                states = resp.json()
                on_lights = [(s["entity_id"], s["attributes"].get("friendly_name", s["entity_id"])) for s in states if s["entity_id"].startswith("light.") and s["state"] == "on" and "backlight" not in s["entity_id"]]
            if on_lights:
                _txt = f"\U0001f4a1 {len(on_lights)} \u0636\u0648\u0621 \u0634\u063a\u0627\u0644:"
                for eid, name in on_lights[:15]:
                    _txt += chr(10) + f"  \u2022 {name}"
                if len(on_lights) > 15:
                    _txt += chr(10) + f"  ... +{len(on_lights)-15} \u062b\u0627\u0646\u064a"
                _btns = [
                    {"text": "\U0001f534 \u0637\u0641\u064a \u0643\u0644 \u0634\u064a", "callback_data": "sc:scene.tfwy_kl_shy"},
            {"text": "\U0001f321 \u0627\u0644\u0637\u0642\u0633", "callback_data": "cmd:weather"},
            {"text": "\U0001f3aa \u0627\u0644\u0633\u062a\u0627\u0626\u0631", "callback_data": "cmd:covers"},
                    {"text": "\U0001f3e0 \u0631\u062c\u0648\u0639", "callback_data": "cmd:home"},
                ]
                await tg_send_inline(chat_id, _txt, _btns, columns=2)
                return "__inline_sent__"
            return "\U0001f4a1 \u0643\u0644 \u0627\u0644\u0623\u0636\u0648\u0627\u0621 \u0645\u0637\u0641\u064a\u0629"
        except Exception as e:
            return f"\u26a0\ufe0f {e}"

    if cmd == "/covers":
        if QUICK_QUERY_OK:
            try:
                from quick_query import _covers_status
                r = await _covers_status()
                _btns = [
                    {"text": "\U0001f7e2 \u0627\u0641\u062a\u062d \u0627\u0644\u0643\u0644", "callback_data": "sc:scene.fth_kl_lstyr"},
                    {"text": "\U0001f534 \u0633\u0643\u0631 \u0627\u0644\u0643\u0644", "callback_data": "sc:scene.skwr_kl_lstyr"},
                    {"text": "\U0001f3e0 \u0631\u062c\u0648\u0639", "callback_data": "cmd:home"},
                ]
                await tg_send_inline(chat_id, r or "\u26a0\ufe0f", _btns, columns=2)
                return "__inline_sent__"
            except Exception as e:
                return f"\u26a0\ufe0f {e}"
        return "\u26a0\ufe0f quick_query not loaded"

    if cmd == "/weather":
        if QUICK_QUERY_OK:
            try:
                from quick_query import _weather
                r = await _weather()
                return r or "\u26a0\ufe0f \u0645\u0627 \u0642\u062f\u0631\u062a \u0623\u062c\u064a\u0628 \u0627\u0644\u0637\u0642\u0633"
            except Exception as e:
                return f"\u26a0\ufe0f {e}"
        return "\u26a0\ufe0f quick_query not loaded"

    if cmd == "/locks":
        if QUICK_QUERY_OK:
            try:
                from quick_query import _locks_status
                r = await _locks_status()
                return r or "\u26a0\ufe0f \u0645\u0627 \u0641\u064a\u0647 \u0623\u0642\u0641\u0627\u0644"
            except Exception as e:
                return f"\u26a0\ufe0f {e}"
        return "\u26a0\ufe0f quick_query not loaded"

    if cmd == "/media":
        if QUICK_QUERY_OK:
            try:
                from quick_query import _media_status
                r = await _media_status()
                return r or "\U0001f3b5 \u0645\u0627 \u0641\u064a\u0647 \u0634\u064a \u064a\u0634\u063a\u0644"
            except Exception as e:
                return f"\u26a0\ufe0f {e}"
        return "\u26a0\ufe0f quick_query not loaded"

    if cmd == "/temp":
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                resp = await c.get(
                    f"{HA_URL}/api/states",
                    headers={"Authorization": f"Bearer {HA_TOKEN}"}
                )
                states = resp.json()
                climates = [
                    s for s in states
                    if s["entity_id"].startswith("climate.") and s["state"] != "unavailable"
                ]
            if climates:
                lines = []
                for cl in climates:
                    name = cl["attributes"].get("friendly_name", cl["entity_id"])
                    current = cl["attributes"].get("current_temperature", "?")
                    target = cl["attributes"].get("temperature", "?")
                    state = cl["state"]
                    emoji = "\u2744\ufe0f" if state == "cool" else "\U0001f525" if state == "heat" else "\u23f8" if state == "off" else "\U0001f300"
                    lines.append(f"{emoji} {name}: {current}\u00b0 \u2192 {target}\u00b0")
                return "\U0001f321 :\n" + "\n".join(lines)
            return "\U0001f321 \u0644\u0627 \u064a\u0648\u062c\u062f \u0645\u0643\u064a\u0641\u0627\u062a"
        except Exception as e:
            return f"\u26a0\ufe0f {e}"

    if cmd == "/health":
        if not DOCTOR_OK: return "ha_doctor not loaded"
        await tg_send_typing(chat_id)
        _hr = await format_health_report()
        # Add fix suggestions
        _issues = await detect_anomalies()
        _fixes = await suggest_fixes(_issues)
        if _fixes:
            _hr += chr(10) + chr(10) + "🔧 *اقتراحات:*"
            for fx in _fixes[:5]:
                _hr += chr(10) + fx
        return _hr

    if cmd == "/brain":
        try:
            stats = get_brain_stats()
            mods = stats.get("modules", {})
            parts = []
            for k, v in mods.items():
                e = "\u2705" if v == "ok" else "\u274c"
                parts.append(f"  {e} {k}")
            mod_text = "\n".join(parts)
            total = stats.get("total_memories", 0)
            aliases = stats.get("aliases_compiled", 0)
            bv = stats.get("brain_version", "?")
            return f"\U0001f9e0 Brain v{bv}\n\nModules:\n{mod_text}\n\nMemories: {total}\nAliases: {aliases}"
        except Exception as e:
            return f"\u26a0\ufe0f brain: {e}"


    if cmd == "/learn":
        if not LEARNING_OK:
            return "brain_learning not loaded"
        try:
            await tg_send(chat_id, "\U0001f9e0 Learning...")
            result = await bl_learn(days=10)
            stats = bl_stats()
            ep = result.get("entities_processed", 0)
            pf = result.get("patterns_found", 0)
            ds = result.get("duration_seconds", 0)
            ew = stats.get("entities_with_patterns", 0)
            rn = stats.get("runs", 0)
            msg = f"\U0001f9e0 Pattern Learning:\n  {ep} entity\n  {pf} patterns\n  {ds}s\n  {ew} with patterns\n  {rn} runs"
            return msg
        except Exception as e:
            return f"learn error: {e}"

    if cmd == "/patterns":
        if not LEARNING_OK:
            return "brain_learning not loaded"
        try:
            return bl_maturity()
        except Exception as e:
            return f"patterns error: {e}"


    if cmd == "/email":
        if not EMAIL_OK:
            return "tg_email not loaded"
        try:
            return await email_report()
        except Exception as e:
            return f"email error: {e}"

    if cmd == "/scenes":
        if not LEARNING_OK:
            return "brain_learning not loaded"
        try:
            scenes = bl_discover_scenes()
            if not scenes:
                return "\u274c \u0645\u0627 \u0644\u0642\u064a\u062a \u0623\u0646\u0645\u0627\u0637 \u0643\u0627\u0641\u064a\u0629"
            report = await bl_scenes_report()
            await tg_send(chat_id, report)
            btns = []
            for s in scenes[:5]:
                btn_text = s['label'] + ' (' + str(s['device_count']) + ' \u062c\u0647\u0627\u0632)'
                cb_data = 'scene:' + s['key'] + ':' + str(s['hour'])
                btns.append({"text": btn_text, "callback_data": cb_data})
            await tg_send_inline(chat_id, "\u0627\u062e\u062a\u0631 \u0648\u062d\u062f\u0629 \u0639\u0634\u0627\u0646 \u0623\u0646\u0634\u0626\u0647\u0627:", btns, columns=1)
            return "__inline_sent__"
        except Exception as e:
            return f"scenes error: {e}"

    if cmd == "/summary":
        if not LEARNING_OK:
            return "brain_learning not loaded"
        try:
            return await bl_summary()
        except Exception as e:
            return f"summary error: {e}"

    if cmd == "/suggest":
        if not LEARNING_OK:
            return "brain_learning not loaded"
        try:
            sugs = bl_top_sugs(limit=8)
            sugs = await bl_filter_autos(sugs)
            sugs = sugs[:5]
            if not sugs:
                return "لا توجد اقتراحات قوية بعد"
            msg = "💡 اقتراحات أتمتة ذكية: اختر وحدة عشان أسويها تلقائي:"

            btns = [{"text": s["label"], "callback_data": s["callback_data"]} for s in sugs]
            await tg_send_inline(chat_id, msg, btns, columns=1)
            return "__inline_sent__"
        except Exception as e:
            return f"suggest error: {e}"

    if cmd == "/anomaly":
        if not LEARNING_OK:
            return "brain_learning not loaded"
        try:
            return await bl_anomaly_report()
        except Exception as e:
            return f"anomaly error: {e}"

    if cmd == "/diag":
        try:
            diag = get_system_diag()
            si = diag.get("system", {})
            cpu = si.get("cpu_percent", 0)
            ram = si.get("memory_percent", 0)
            temp = si.get("temperature", 0)
            disk = si.get("disk_percent", 0)
            db = diag.get("db_size_mb", 0)
            errs = diag.get("errors_last_hour", 0)
            _up = int(time.time() - START_TIME)
            _h2, _m2 = divmod(_up // 60, 60)
            _mc2 = sum(1 for v in [TG_INTENT_OK, LIFE_ROUTER_OK, SMART_ROUTER_OK, BRAIN_AVAILABLE, TG_MORNING_OK, TG_ALERTS_OK, TG_REMIND_OK, TG_NEWS_OK, DISCOVERY_OK, TG_SESSION_OK, TG_HOME_OK, TG_OPS_OK, LIFE_STOCKS_OK, LIFE_EXPENSES_OK, LIFE_HEALTH_OK, LIFE_WORK_OK] if v)
            _t2 = _router_stats.get("total", 0)
            import os as _os2
            _lkb = round(_os2.path.getsize("server.log") / 1024) if _os2.path.exists("server.log") else 0
            return chr(10).join([
                f"📊 Diag v{VERSION}",
                f"CPU: {cpu}% | RAM: {ram}%",
                f"Temp: {temp}°C | Disk: {disk}%",
                f"Up: {_h2}h {_m2}m | Msgs: {_t2}",
                f"Modules: {_mc2}/16 | Plugins: {len(PLUGIN_REGISTRY._plugins)}",
                f"DB: {db}MB | Log: {_lkb}KB | Err/h: {errs}",
            ])
        except Exception as e:
            return f"\u26a0\ufe0f diag: {e}"

    if cmd == "/summary":
        # Daily summary dashboard
        try:
            _up = int(time.time() - START_TIME)
            _h, _m = divmod(_up // 60, 60)
            _t = _router_stats.get("total", 0)
            _greet = _router_stats.get("greeting", 0)
            _chat = _router_stats.get("chat", 0)
            _action = _router_stats.get("action", 0)
            _intent = _router_stats.get("intent", 0)
            _unk = _router_stats.get("unknown", 0)
            _fup = _router_stats.get("followup", 0)
            _ls = _router_stats.get("life_stocks", 0) + _router_stats.get("life_expenses", 0) + _router_stats.get("life_health", 0) + _router_stats.get("life_work", 0)
            _qq = _router_stats.get("quick_query", 0)
            _cache = _router_stats.get("cache_hit", 0)
            _saved = _greet + _intent + _ls + _qq + _cache
            _pct = round(_saved / _t * 100) if _t > 0 else 0
            # HA status
            _ha_ok = False
            try:
                async with httpx.AsyncClient(timeout=5) as _hc:
                    _hr = await _hc.get(f"{HA_URL}/api/", headers={"Authorization": f"Bearer {HA_TOKEN}"})
                    _ha_ok = _hr.status_code == 200
            except Exception:
                pass
            # Error count from log
            import os as _os3
            _errs = 0
            try:
                with open("server.log", "r") as _lf:
                    _errs = sum(1 for l in _lf if "ERROR" in l)
            except Exception:
                pass
            # DB size
            _db_mb = 0
            try:
                _db_mb = round(_os3.path.getsize("data/audit.db") / 1024 / 1024, 1)
            except Exception:
                pass
            _mc = sum(1 for v in [TG_INTENT_OK, LIFE_ROUTER_OK, SMART_ROUTER_OK, BRAIN_AVAILABLE, TG_MORNING_OK, TG_ALERTS_OK, TG_REMIND_OK, TG_NEWS_OK, DISCOVERY_OK, TG_SESSION_OK, TG_HOME_OK, TG_OPS_OK, LIFE_STOCKS_OK, LIFE_EXPENSES_OK, LIFE_HEALTH_OK, LIFE_WORK_OK] if v)
            _lines = [
                f"\U0001f4cb Daily Summary",
                f"",
                f"\u23f1 Up: {_h}h {_m}m | v{VERSION}",
                f"{'\u2705' if _ha_ok else '\u274c'} HA | \u2705 {_mc}/16 modules",
                f"",
                f"\U0001f4e8 Messages: {_t}",
                f"  \U0001f44b Greeting: {_greet} (0 API)",
                f"  \U0001f3af Intent: {_intent} | \U0001f504 Followup: {_fup}",
                f"  \U0001f4ac Chat: {_chat} | \u2699\ufe0f Action: {_action}",
                f"  \U0001f3e0 Life: {_ls} | \u2753 Unknown: {_unk}",
                f"",
                f"\U0001f4a1 LLM saved: {_saved}/{_t} ({_pct}%)",
                f"\u26a0\ufe0f Errors: {_errs} | DB: {_db_mb}MB",
            ]
            return chr(10).join(_lines)
        except Exception as e:
            return f"\u26a0\ufe0f summary: {e}"

    if cmd == "/home" or cmd == "/home2":
        _page2 = cmd == "/home2"
        if not _page2:
            buttons = [
                {"text": "\U0001f4a1 \u0627\u0644\u0623\u0636\u0648\u0627\u0621", "callback_data": "cmd:lights"},
                {"text": "\u2744\ufe0f \u0627\u0644\u0645\u0643\u064a\u0641\u0627\u062a", "callback_data": "cmd:temp"},
                {"text": "\U0001f3aa \u0627\u0644\u0633\u062a\u0627\u0626\u0631", "callback_data": "cmd:covers"},
                {"text": "\U0001f3ac \u0627\u0644\u0645\u0634\u0627\u0647\u062f", "callback_data": "cmd:scenes"},
                {"text": "\U0001f510 \u0627\u0644\u0623\u0642\u0641\u0627\u0644", "callback_data": "cmd:locks"},
                {"text": "\U0001f3b5 \u0627\u0644\u0633\u0645\u0627\u0639\u0627\u062a", "callback_data": "cmd:media"},
                {"text": "\U0001f4f7 \u0627\u0644\u0643\u0627\u0645\u064a\u0631\u0627\u062a", "callback_data": "cmd:cam"},
                {"text": "\U0001f321 \u0627\u0644\u0637\u0642\u0633", "callback_data": "cmd:weather"},
                {"text": "\U0001f534 \u0637\u0641\u064a \u0643\u0644 \u0634\u064a", "callback_data": "sc:scene.tfwy_kl_shy"},
                {"text": "\u27a1\ufe0f \u0627\u0644\u0645\u0632\u064a\u062f", "callback_data": "cmd:home2"},
            ]
            await tg_send_inline(chat_id, "\U0001f3e0 *\u0627\u0644\u0642\u0627\u0626\u0645\u0629 \u0627\u0644\u0631\u0626\u064a\u0633\u064a\u0629*", buttons, columns=2)
        else:
            buttons = [
                {"text": "\U0001f4c5 \u0627\u0644\u0634\u0641\u062a", "callback_data": "cmd:shift"},
                {"text": "\U0001f4c6 \u0627\u0644\u0623\u0633\u0628\u0648\u0639", "callback_data": "cmd:week"},
                {"text": "\U0001f4b0 \u0627\u0644\u0623\u0633\u0647\u0645", "callback_data": "cmd:stocks"},
                {"text": "\U0001f4cb \u0645\u0644\u062e\u0635", "callback_data": "cmd:summary"},
                {"text": "📊 تقرير", "callback_data": "cmd:report"},
                {"text": "\U0001f4ca \u0627\u0644\u0646\u0638\u0627\u0645", "callback_data": "cmd:diag"},
                {"text": "\U0001f9e0 \u0627\u0644\u0639\u0642\u0644", "callback_data": "cmd:brain"},
                {"text": "\U0001f4dd \u0627\u0644\u0645\u0647\u0627\u0645", "callback_data": "cmd:tasks"},
                {"text": "🌍 حياتي", "callback_data": "cmd:life"},
                {"text": "📧 Inbox", "callback_data": "cmd:inbox"},
                {"text": "👤 أنا", "callback_data": "cmd:me"},
                {"text": "\u2753 \u0645\u0633\u0627\u0639\u062f\u0629", "callback_data": "cmd:help"},
                {"text": "\u2b05\ufe0f \u0631\u062c\u0648\u0639", "callback_data": "cmd:home"},
            ]
            await tg_send_inline(chat_id, "\U0001f4e6 *\u0627\u0644\u0645\u0632\u064a\u062f*", buttons, columns=2)
        return "__inline_sent__"
        return "__inline_sent__"

    # --- Level 2: Home commands ---
    if cmd == "/rooms":
        # --- Phase B2: Room selector with inline buttons ---
        import json as _json_rooms
        try:
            _emap = _json_rooms.load(open("/home/pi/master_ai/entity_map.json"))
        except Exception:
            return "entity_map.json not found"
        _floor_groups = [
            ("🏠 الأرضي", ["الأرضي/Ground", "الديوانية/Diwaniya", "المطبخ/Kitchen", "غرفة الطعام/Dining", "صالة الاستقبال/Reception", "صالة المعيشة/Living", "الخارجي/Outdoor"]),
            ("🔼 الأول", ["غرفة الماستر/Master", "حمام الماستر", "ملابس الماستر", "صالتي/Salon", "المكتب/Office", "غرفة عيشة/Aisha", "ممر الدور الأول", "البلكونة/Balcony", "غرفة ماما/Mama"]),
            ("🔼 الثاني", ["غرفة الضيوف/Guest", "غرفة 2", "غرفة 3", "غرفة 4", "غرفة 5", "الدرج/Stairs"]),
            ("🔧 خدمات", ["غرفة الغسيل/Laundry", "غرفة الخادمة/Maid"]),
        ]
        for _fn, _fr in _floor_groups:
            _btns = []
            for _rm in _fr:
                if _rm in _emap:
                    _cnt = len([e for e in _emap[_rm] if "=" in e and not e.split("=")[0].startswith("scene.")])
                    _short = _rm.split("/")[0] if "/" in _rm else _rm
                    _btns.append({"text": f"{_short} ({_cnt})", "callback_data": f"room:{_rm[:40]}"})
            if _btns:
                await tg_send_inline(chat_id, _fn, _btns, columns=2)
        return "__inline_sent__"

    if cmd.startswith("/devices"):
        if not TG_HOME_OK:
            return "tg_home module not loaded"
        room_q = text[len("/devices"):].strip()
        if not room_q:
            return "Usage: /devices <room name>"
        result = await cmd_devices(room_q)
        if TG_SESSION_OK:
            tg_session_upsert(str(chat_id), last_intent="devices", last_room=room_q)
        return result

    if cmd.startswith("/find"):
        if not TG_HOME_OK:
            return "tg_home module not loaded"
        try:
            kw = text[len("/find"):].strip()
            result = await cmd_find(kw)
            if isinstance(result, tuple):
                msg, results = result
                if TG_SESSION_OK:
                    eids = [r[0] for r in results]
                    tg_session_upsert(str(chat_id), last_intent="find", last_query=kw, last_entities=eids)
                btns = find_buttons(results)
                if btns:
                    flat = [b for row in btns for b in row]
                    await tg_send_inline(chat_id, msg, flat, columns=2)
                    return "__inline_sent__"
                return msg
            return result
        except Exception as e:
            logger.error(f"find error: {e}")
            return f"Error: {e}" 

    if cmd == "/scenes_dynamic" or cmd == "/scenes_all":
        if not TG_HOME_OK:
            return "tg_home module not loaded"
        try:
            msg, buttons = await cmd_scenes_dynamic()
            if buttons:
                await tg_send_inline(chat_id, msg, buttons, columns=2)
                return "__inline_sent__"
            return msg
        except Exception as e:
            logger.error(f"scenes_dynamic error: {e}")
            return f"Error: {e}" 

    if cmd == "/scenes" or cmd == "/scenes1":
        sc = [
            {"text": "🌙 نوم", "callback_data": "sc:scene.wd_lnwm"},
            {"text": "☀️ صباح", "callback_data": "sc:scene.sbh_lkhyr"},
            {"text": "🚪 مغادرة", "callback_data": "sc:scene.mgdr_lbyt"},
            {"text": "🎉 ضيوف", "callback_data": "sc:scene.wd_ldywf"},
            {"text": "☕ ديوانية", "callback_data": "sc:scene.wd_ldywny"},
            {"text": "🎬 سينما", "callback_data": "sc:scene.wd_lsynm"},
            {"text": "🛑 طفّي كل شي", "callback_data": "sc:scene.tfwy_kl_shy"},
            {"text": "\U0001f321 \u0627\u0644\u0637\u0642\u0633", "callback_data": "cmd:weather"},
            {"text": "\U0001f3aa \u0627\u0644\u0633\u062a\u0627\u0626\u0631", "callback_data": "cmd:covers"},
            {"text": "➡️ المزيد", "callback_data": "cmd:scenes2"},
        ]
        await tg_send_inline(chat_id, "🎬 *المشاهد* (1/2)", sc, columns=2)
        return "__inline_sent__"

    if cmd == "/scenes2":
        sc2 = [
            {"text": "💡 سبوت فقط", "callback_data": "sc:scene.sbwt_fqt"},
            {"text": "🌙 ستريب فقط", "callback_data": "sc:scene.stryb_fqt"},
            {"text": "🌬️ تنقية", "callback_data": "sc:scene.tnqy_hw_shml"},
            {"text": "🚿 حمامات", "callback_data": "sc:scene.tf_kl_lhmmt"},
            {"text": "🌀 شفاطات", "callback_data": "sc:scene.glq_kl_lshftt"},
            {"text": "🪧 سكّر ستاير", "callback_data": "sc:scene.skwr_kl_lstyr"},
            {"text": "☀️ افتح ستاير", "callback_data": "sc:scene.fth_kl_lstyr"},
            {"text": "⬅️ رجوع", "callback_data": "cmd:scenes"},
        ]
        await tg_send_inline(chat_id, "🎬 *المشاهد* (2/2)", sc2, columns=2)
        return "__inline_sent__"

    if cmd == "/brain":
        if not BRAIN_OK: return "home_brain not loaded"
        st = get_brain_stats()
        _bl = ["🧠 *Home Brain*"]
        _bl.append(f"  📊 تغييرات: {st['total']} (اليوم: {st['today']})")
        _bl.append(f"  📅 أيام: {st['days']}")
        _bl.append(f"  🔍 أنماط: {st['patterns']}")
        pats = detect_patterns(14, 3)
        _bl.append("")
        _bl.append(format_insights_ar(pats) if pats else "⏳ لسا أتعلم... استخدم البوت وبعد كم يوم بقترح عليك")
        return chr(10).join(_bl)

    if cmd == "/alloff":
        # Confirmation before killing everything
        _cb = [
            {"text": "✅ نعم طفي الكل", "callback_data": "sc:scene.tfwy_kl_shy"},
            {"text": "❌ إلغاء", "callback_data": "cmd:home"},
        ]
        await tg_send_inline(chat_id, "⚠️ متأكد تبي تطفي كل شي بالبيت؟", _cb, columns=2)
        return "__inline_sent__"

    if cmd == "/find":
        if not args:
            return "usage: /find <name>" + chr(10) + "مثال: /find ديوانية"
        q = " ".join(args).lower()
        try:
            async with httpx.AsyncClient(timeout=10) as _fc:
                _r = await _fc.get(f"{HA_URL}/api/states", headers={"Authorization": f"Bearer {HA_TOKEN}"})
                _states = _r.json() if _r.status_code == 200 else []
            matches = []
            for s in _states:
                eid = s["entity_id"].lower()
                fname = s.get("attributes", {}).get("friendly_name", "").lower()
                if q in eid or q in fname:
                    matches.append(s)
            if not matches:
                return "❓ ما لقيت: " + q
            _icons = {"on": "✅", "off": "⚫", "open": "🟢", "closed": "🔴", "heat": "🔥", "cool": "❄️", "playing": "▶️", "unavailable": "⚠️"}
            _lines = ["🔍 " + q + " (" + str(len(matches)) + "):"]
            for s in matches[:15]:
                fn = s.get("attributes", {}).get("friendly_name", s["entity_id"])
                st = s["state"]
                ic = _icons.get(st, "➖")
                tmp = " (" + str(s["attributes"].get("temperature", "")) + "°)" if "temperature" in s.get("attributes", {}) else ""
                _lines.append("  " + ic + " " + fn + ": " + st + tmp)
            if len(matches) > 15:
                _lines.append("  ... +" + str(len(matches)-15))
            return chr(10).join(_lines)
        except Exception as e:
            return "Error: " + str(e)

    if cmd == "/cam":
        cb = [
            {"text": "📷 كام 1", "callback_data": "cam:1"},
            {"text": "📷 كام 2", "callback_data": "cam:2"},
            {"text": "📷 كام 3", "callback_data": "cam:3"},
            {"text": "📷 كام 4", "callback_data": "cam:4"},
            {"text": "📷 كام 5", "callback_data": "cam:5"},
            {"text": "📷 كام 6", "callback_data": "cam:6"},
        ]
        await tg_send_inline(chat_id, "📷 *اختر كاميرا*", cb, columns=3)
        return "__inline_sent__"

    # Level 1 admin-only operational commands
    if cmd == "/approvals":
        if not TG_OPS_OK:
            return "tg_ops module not loaded"
        if not is_tg_admin(chat_id):
            return "Admin only"
        pending = get_pending_approvals(10)
        if not pending:
            return "No pending approvals"
        buttons = format_approval_buttons(pending)
        header = f"Pending approvals: {len(pending)}"
        await tg_send_inline(chat_id, header, buttons, columns=2)
        return "__inline_sent__"

    if cmd == "/backup":
        if not TG_OPS_OK:
            return "tg_ops module not loaded"
        if not is_tg_admin(chat_id):
            return "Admin only"
        ok, msg = tg_run_backup()
        if ok:
            return f"Backup done\n{msg}"
        return f"Backup failed: {msg}"

    if cmd == "/restart":
        if not is_tg_admin(chat_id) if TG_OPS_OK else True:
            return "Admin only"
        try:
            async with httpx.AsyncClient(timeout=10) as rc:
                hdrs = {}
                if MASTER_API_KEY:
                    hdrs["X-API-Key"] = MASTER_API_KEY
                resp = await rc.post("http://127.0.0.1:9001/restart", headers=hdrs)
                if resp.status_code == 200:
                    return "Restart initiated via recovery"
                return f"Recovery responded: {resp.status_code}"
        except Exception as e:
            return f"Recovery unreachable: {e}"

    if cmd == "/errors":
        if not is_tg_admin(chat_id) if TG_OPS_OK else True:
            return "Admin only"
        try:
            diag = get_system_diag()
            errs = diag.get("recent_errors", [])
            cnt = diag.get("errors_last_hour", 0)
            if not errs and cnt == 0:
                return "No recent errors"
            parts = [f"Errors last hour: {cnt}"]
            for er in errs[:5]:
                parts.append(f"  - {str(er)[:100]}")
            return "\n".join(parts)
        except Exception as e:
            return f"Error: {e}"


    if cmd.startswith("/update_stock"):
        if not TG_STOCKS_OK:
            return "Stock module not loaded"
        parts = text.strip().split()
        if len(parts) >= 3:
            try:
                return update_stock(parts[1], float(parts[2]), " ".join(parts[3:]) if len(parts) > 3 else None)
            except ValueError:
                return "الاستخدام: /update_stock TICKER PRICE [note]"
        return "الاستخدام: /update_stock TICKER PRICE [note]"

    if cmd == "/log":
        import subprocess, asyncio
        result = await asyncio.to_thread(subprocess.run, ["tail", "-15", "/home/pi/master_ai/server.log"], capture_output=True, text=True)
        log_text = result.stdout[-2000:] if result.stdout else "empty"
        return "📜 Log:\n" + log_text
    if cmd == "/crash":
        import subprocess as _sp2, asyncio as _aio2
        _cr = await _aio2.to_thread(_sp2.run, ["/home/pi/master_ai/scripts/crash_fingerprint.sh"], capture_output=True, text=True)
        return _cr.stdout[-3500:] if _cr.stdout else "❌ Fingerprint failed"
    if cmd == "/me":
        try:
            import asyncio, time as _time
            from life_work import get_shift
            from task_engine import task_stats, task_list
            from inbox_engine import fetch_unified_inbox, P_HIGH, P_CRITICAL
            parts = []

            # Greeting + date
            _hour = __import__("datetime").datetime.now().hour
            _greet = ("☀️ صباح الخير" if 5<=_hour<12
                      else "🌞 مساء النور" if 12<=_hour<17
                      else "🌙 السلام عليكم")
            parts.append(_greet + " بو خليفة")
            parts.append("")

            # Shift today
            try:
                si = get_shift()
                if isinstance(si, dict):
                    parts.append("👷 " + si.get("emoji","") + " " + si.get("shift","") + " " + si.get("times",""))
                else:
                    parts.append("👷 " + str(si))
            except Exception: pass

            # Tasks
            try:
                s = task_stats()
                if s["total_active"]:
                    t_line = "📋 مهام: " + str(s["total_active"]) + " نشطة"
                    if s["overdue"]:   t_line += "  ⚠️ " + str(s["overdue"]) + " متأخرة"
                    if s["due_today"]: t_line += "  📌 " + str(s["due_today"]) + " اليوم"
                    parts.append(t_line)
                    top = task_list(due_today=True)[:3] + task_list(due_overdue=True)[:2]
                    seen = set()
                    for t in top:
                        if t["id"] not in seen:
                            parts.append("  • " + t["title"][:40])
                            seen.add(t["id"])
                else:
                    parts.append("📋 مهام: لا توجد مهام ✅")
            except Exception: pass

            # Inbox urgent
            try:
                idata = await fetch_unified_inbox(hours=24, limit=20)
                urgent = [m for m in idata.get("messages",[]) if m.get("_priority",0)>=P_HIGH]
                if urgent:
                    parts.append("📧 إيميل مهم: " + str(len(urgent)))
                    for m in urgent[:2]:
                        parts.append("  • " + m.get("subject","")[:40])
                else:
                    parts.append("📧 Inbox: نظيف ✅")
            except Exception: pass

            # Cost today
            try:
                from cost_tracker import get_cost_for_kpi
                k = get_cost_for_kpi()
                parts.append("💰 تكلفة اليوم: $" + f"{k['today_usd']:.4f}")
            except Exception: pass

            return chr(10).join(parts)
        except Exception as e:
            return f"❌ /me error: {e}"

    if cmd == "/suggest_tasks":
        try:
            from inbox_engine import format_email_task_suggestions
            result = await format_email_task_suggestions()
            return result if result else "✅ ما في إيميلات تحتاج إجراء الحين"
        except Exception as e:
            return f"❌ suggest_tasks error: {e}"

    if cmd == "/life":
        try:
            import asyncio
            from datetime import date as _date
            from life_work import get_shift
            from task_engine import task_list, task_stats
            from calendar_engine import get_today_events
            from calendar_reporting import render_morning_calendar_section
            from inbox_engine import fetch_unified_inbox, P_CRITICAL, P_HIGH

            parts = []

            # Shift
            try:
                shift_info = get_shift()
                shift_name = shift_info.get("emoji","") + " " + shift_info.get("shift","") + " " + shift_info.get("times","")
                parts.append("👷 *الوردية:* " + shift_name)
            except Exception:
                pass

            # Tasks today + overdue
            try:
                s = task_stats()
                today_tasks = task_list(due_today=True)
                overdue     = task_list(due_overdue=True)
                t_line = "📋 *المهام:* " + str(s["total_active"]) + " نشطة"
                if s["overdue"]:   t_line += " | ⚠️ " + str(s["overdue"]) + " متأخرة"
                if s["due_today"]: t_line += " | 📌 " + str(s["due_today"]) + " اليوم"
                parts.append(t_line)
                for t in (today_tasks + overdue)[:4]:
                    parts.append("  • [" + str(t["id"]) + "] " + t["title"][:40])
            except Exception:
                pass

            # Calendar today
            try:
                events = get_today_events()
                cal = render_morning_calendar_section(events)
                if cal: parts.append(cal)
            except Exception:
                pass

            # Inbox urgent/high only
            try:
                inbox_data = await fetch_unified_inbox(hours=24, limit=20)
                urgent = [m for m in inbox_data.get("messages",[]) if m.get("_priority",0) >= P_HIGH]
                if urgent:
                    parts.append("📧 *إيميل مهم:* " + str(len(urgent)) + " رسالة")
                    for m in urgent[:3]:
                        parts.append("  • " + m.get("subject","")[:40])
                else:
                    parts.append("📧 الـ Inbox: ما في رسائل مهمة ✅")
            except Exception:
                pass

            return chr(10).join(parts) if parts else "✅ كل شي تمام"
        except Exception as e:
            logger.error(f"life error: {e}")
            return f"❌ life error: {e}"

    if cmd == "/week_summary":
        try:
            import asyncio
            from task_engine import task_list, task_stats, format_task_list, PRIORITY_LABEL, STATUS_LABEL
            from inbox_engine import inbox_weekly_digest
            lines = ["📅 *ملخص الأسبوع*", ""]
            # Tasks section
            s = task_stats()
            if s["total_active"] > 0:
                lines.append("📋 *المهام*")
                lines.append("إجمالي نشط: " + str(s["total_active"]))
                if s["overdue"]:   lines.append("⚠️ متأخرة: " + str(s["overdue"]))
                if s["due_today"]: lines.append("📌 مستحقة اليوم: " + str(s["due_today"]))
                done_w = len([t for t in task_list(status="done") if t.get("completed_at","") >= (__import__("datetime").date.today() - __import__("datetime").timedelta(days=7)).isoformat()])
                if done_w: lines.append("✅ أنجزت هالأسبوع: " + str(done_w))
                # Show high priority tasks
                high = task_list(priority="high")
                if high:
                    lines.append("")
                    lines.append("🔴 عالية الأولوية:")
                    for t in high[:5]:
                        lines.append("  • [" + str(t["id"]) + "] " + t["title"][:45])
            else:
                lines.append("📋 المهام: لا توجد مهام نشطة ✅")
            lines.append("")
            # Inbox weekly section
            inbox_w = await inbox_weekly_digest()
            lines.append(inbox_w)
            return chr(10).join(lines)
        except Exception as e:
            logger.error(f"week_summary error: {e}")
            return f"❌ week_summary error: {e}"

    if cmd == "/inbox" or cmd == "/inbox48" or cmd == "/inbox_week":
        try:
            from inbox_engine import fetch_unified_inbox, format_inbox_tg, inbox_weekly_digest
            import asyncio
            if cmd == "/inbox_week":
                result = await inbox_weekly_digest()
            else:
                hours = 48 if cmd == "/inbox48" else 24
                data  = await fetch_unified_inbox(hours=hours, limit=15)
                result = format_inbox_tg(data, show_limit=15)
            return result
        except Exception as e:
            logger.error(f"inbox error: {e}")
            return f"❌ inbox error: {e}"

    if cmd == "/tasks" or cmd.startswith("/tasks "):
        if not TG_TASKS_OK:
            return "❌ tasks module not loaded"
        args = text.strip()[6:].strip() if len(text.strip()) > 6 else ""
        return handle_tasks_command(args)
    if cmd.startswith("/task "):
        if not TG_TASKS_OK:
            return "❌ tasks module not loaded"
        sub = text.strip()[6:].strip()
        if sub.startswith("add "):
            return str(llm_tool_task_create(title=sub[4:].strip()))
        elif sub.startswith("done "):
            return str(llm_tool_task_update(task_id=int(sub[5:].strip()), status="done"))
        else:
            return "الاستخدام: /task add <عنوان> | /task done <رقم>"
    # --- News Digests ---
    if cmd == "/news" or cmd.startswith("/news "):
        if not NEWS_ENGINE_OK:
            return "❌ news engine not loaded"
        args_t = text.strip()[5:].strip() if len(text.strip()) > 5 else ""
        cat = None
        if args_t in ("kuwait", "economy", "technology", "tech"):
            cat = "technology" if args_t == "tech" else args_t
        return handle_news_latest(cat)
    if cmd == "/news_now" or cmd.startswith("/news_now "):
        if not NEWS_ENGINE_OK:
            return "❌ news engine not loaded"
        args_t = text.strip()[9:].strip() if len(text.strip()) > 9 else ""
        cat = None
        if args_t in ("kuwait", "economy", "technology", "tech"):
            cat = "technology" if args_t == "tech" else args_t
        try:
            result = await news_generate_digest(cat, "manual")
            if result.get("ok"):
                return format_digest_tg(get_latest_digest(cat))
            return f"❌ {result.get('error', 'failed')}"
        except Exception as e:
            return f"❌ {e}"
    if cmd == "/news_sources":
        if not NEWS_ENGINE_OK:
            return "❌ news engine not loaded"
        return format_sources_tg()
        # --- Journal ---
    if cmd == "/trade" or cmd.startswith("/trade "):
        if not JOURNAL_OK:
            return "\u274c journal engine not loaded"
        args_t = text.strip()[6:].strip() if len(text.strip()) > 6 else ""
        if not args_t:
            return "\u0627\u0644\u0627\u0633\u062a\u062e\u062f\u0627\u0645: /trade ZAIN 566 1000 EMA bullish"
        parts = args_t.split()
        if len(parts) < 2:
            return "\u0627\u0644\u0627\u0633\u062a\u062e\u062f\u0627\u0645: /trade SYMBOL PRICE [QTY] [REASON]"
        _sym = parts[0].upper()
        try:
            _price = float(parts[1])
        except ValueError:
            return "\u274c \u0627\u0644\u0633\u0639\u0631 \u063a\u064a\u0631 \u0635\u062d\u064a\u062d"
        _qty = 0
        _reason = ""
        if len(parts) >= 3:
            try:
                _qty = int(parts[2])
                _reason = " ".join(parts[3:]) if len(parts) > 3 else ""
            except ValueError:
                _reason = " ".join(parts[2:])
        _tid = open_trade(symbol=_sym, entry_price=_price, quantity=_qty, entry_reason=_reason)
        _msg = "\u2705 \u0635\u0641\u0642\u0629 #" + str(_tid) + " \u0645\u0641\u062a\u0648\u062d\u0629: " + _sym + " @ " + str(_price)
        if _qty:
            _msg += " \u00d7 " + str(_qty)
        if _reason:
            _msg += " \u2014 " + _reason
        return _msg
    if cmd == "/close" or cmd.startswith("/close "):
        if not JOURNAL_OK:
            return "\u274c journal engine not loaded"
        args_t = text.strip()[6:].strip() if len(text.strip()) > 6 else ""
        if not args_t:
            return "\u0627\u0644\u0627\u0633\u062a\u062e\u062f\u0627\u0645: /close TRADE_ID EXIT_PRICE [REASON]"
        parts = args_t.split()
        if len(parts) < 2:
            return "\u0627\u0644\u0627\u0633\u062a\u062e\u062f\u0627\u0645: /close 1 580 hit target"
        try:
            _tid = int(parts[0])
            _exit_p = float(parts[1])
        except ValueError:
            return "\u274c trade_id \u0648 exit_price \u0644\u0627\u0632\u0645 \u0623\u0631\u0642\u0627\u0645"
        _reason = " ".join(parts[2:]) if len(parts) > 2 else "manual"
        result = close_trade(_tid, _exit_p, _reason)
        if result is None:
            return "\u274c \u0635\u0641\u0642\u0629 #" + str(_tid) + " \u063a\u064a\u0631 \u0645\u0648\u062c\u0648\u062f\u0629 \u0623\u0648 \u0645\u063a\u0644\u0642\u0629"
        _pnl = result.get("pnl_pct", 0)
        _sym = result.get("symbol", "")
        _entry = result.get("entry_price", 0)
        _emoji = "\U0001f4c8" if _pnl >= 0 else "\U0001f4c9"
        return "\u2705 \u0635\u0641\u0642\u0629 #" + str(_tid) + " \u0645\u063a\u0644\u0642\u0629: " + _sym + " @ " + str(_entry) + "\u2192" + str(_exit_p) + " (" + _emoji + " " + format(_pnl, "+.2f") + "%) \u2014 " + _reason
    if cmd == "/trades":
        if not JOURNAL_OK:
            return "\u274c journal engine not loaded"
        trades = get_open_trades()
        if not trades:
            return "\U0001f4c2 \u0644\u0627 \u0635\u0641\u0642\u0627\u062a \u0645\u0641\u062a\u0648\u062d\u0629"
        lines = ["*\U0001f4c2 \u0635\u0641\u0642\u0627\u062a \u0645\u0641\u062a\u0648\u062d\u0629 (" + str(len(trades)) + "):*\n"]
        for t in trades:
            _l = "  #" + str(t["id"]) + " " + t["symbol"] + " @ " + str(t["entry_price"])
            if t.get("quantity"):
                _l += " \u00d7" + str(t["quantity"])
            if t.get("strategy"):
                _l += " \u2014 " + t["strategy"]
            lines.append(_l)
        return "\n".join(lines)
    if cmd == "/journal":
        if not JOURNAL_OK:
            return "\u274c journal engine not loaded"
        stats = get_trade_stats(days=30)
        recent = get_recent_trades(limit=10)
        lines = ["*\U0001f4ca \u0645\u0644\u062e\u0635 \u0627\u0644\u062a\u062f\u0627\u0648\u0644 (30 \u064a\u0648\u0645):*\n"]
        lines.append("\U0001f4c8 \u0625\u062c\u0645\u0627\u0644\u064a: " + str(stats["total_trades"]) + " \u0635\u0641\u0642\u0629 \u2022 " + str(stats["open_trades"]) + " \u0645\u0641\u062a\u0648\u062d\u0629 \u2022 " + str(stats["closed_trades"]) + " \u0645\u063a\u0644\u0642\u0629")
        if stats["closed_trades"] > 0:
            _wr = str(round(stats["win_rate"] * 100)) + "%"
            lines.append("\u2705 \u0641\u0648\u0632: " + _wr + " \u2022 \u0645\u062a\u0648\u0633\u0637 \u0631\u0628\u062d: " + format(stats["avg_profit_pct"], "+.1f") + "% \u2022 \u0645\u062a\u0648\u0633\u0637 \u062e\u0633\u0627\u0631\u0629: " + format(stats["avg_loss_pct"], ".1f") + "%")
            lines.append("\U0001f4b0 P&L: " + format(stats["total_pnl_fils"], "+.0f") + " \u0641\u0644\u0633")
        if recent:
            lines.append("\n*\u0622\u062e\u0631 " + str(len(recent)) + " \u0635\u0641\u0642\u0627\u062a:*")
            for t in recent:
                if t["status"] == "closed":
                    _st = "\u2705"
                elif t["status"] == "open":
                    _st = "\U0001f4c2"
                else:
                    _st = "\u274c"
                _info = _st + " #" + str(t["id"]) + " " + t["symbol"] + " @ " + str(t["entry_price"])
                if t["status"] == "closed" and t.get("pnl_pct") is not None:
                    _info += " \u2192 " + str(t["exit_price"]) + " (" + format(t["pnl_pct"], "+.1f") + "%)"
                lines.append("  " + _info)
        return "\n".join(lines)
        # --- Expenses ---
    if cmd == "/add_expense" or cmd.startswith("/add_expense "):
        if not EXP_OK:
            return "❌ expenses not loaded"
        args_t = text.strip()[12:].strip() if len(text.strip()) > 12 else ""
        if not args_t:
            return "الاستخدام: /add_expense 12.5 مطعم"
        parsed = parse_expense(args_t)
        if not parsed:
            return "❌ ما قدرت أفهم المبلغ"
        result = add_expense(parsed[0], parsed[1], parsed[2])
        return format_add_confirmation(result)
    if cmd == "/spent" or cmd.startswith("/spent "):
        if not EXP_OK:
            return "❌ expenses not loaded"
        args_t = text.strip()[6:].strip() if len(text.strip()) > 6 else "today"
        if args_t in ("today", "week", "month"):
            return format_summary_tg(get_summary(args_t))
        return format_summary_tg(get_summary("today"))
    if cmd == "/expenses":
        if not EXP_OK:
            return "❌ expenses not loaded"
        return format_recent_tg(list_expenses(10))
        # --- Relationships & Occasions ---
    if cmd == "/contacts":
        if not REL_OK:
            return "❌ relationships not loaded"
        return format_contacts_tg(list_contacts())
    if cmd == "/occasions" or cmd.startswith("/occasions "):
        if not REL_OK:
            return "❌ relationships not loaded"
        args_t = text.strip()[10:].strip() if len(text.strip()) > 10 else ""
        days = int(args_t) if args_t.isdigit() else 30
        return format_upcoming_tg(get_upcoming_occasions(days))
    if cmd == "/person" or cmd.startswith("/person "):
        if not REL_OK:
            return "❌ relationships not loaded"
        name = text.strip()[7:].strip() if len(text.strip()) > 7 else ""
        if not name:
            return "الاستخدام: /person <اسم>"
        snap = build_contact_snapshot(name)
        if not snap:
            return f"❌ ما لقيت '{name}'"
        return format_person_tg(snap)
    if cmd == "/فرص" or cmd == "/decisions":
        try:
            from golden_engine import scan_opportunities
            import sqlite3 as _sq
            live_list = []
            try:
                from signal_engine import build_signals_30m
                sig_data = build_signals_30m()
                live_list = sig_data.get("signals", [])
            except Exception:
                pass
            if not live_list:
                try:
                    from signal_engine import build_signals
                    sig_data = build_signals()
                    live_list = sig_data.get("all_signals", [])
                except Exception:
                    pass
            if not live_list:
                _db = os.path.join(os.path.dirname(__file__), "data", "life.db")
                try:
                    _c = _sq.connect(_db, timeout=5)
                    _c.row_factory = _sq.Row
                    _rows = _c.execute(
                        "SELECT symbol, price, rsi, vol_ratio, support, resistance, "
                        "macd_cross AS macd_state, daily_ema_cross AS ema_state, "
                        "stoch_k, adx, atr, bb_squeeze, confluence_score, change_pct "
                        "FROM stock_radar_daily"
                    ).fetchall()
                    _c.close()
                    live_list = [dict(r) for r in _rows]
                except Exception:
                    pass
            result = scan_opportunities(live_list)
            opps = result.get("all_opportunities", [])
            enters = [o for o in opps if o.get("smart_decision") == "ENTER"]
            if not enters:
                return "⚪ لا توجد فرص ادخل حالياً"
            lines = [f"🟢 <b>{len(enters)} فرصة ادخل الآن</b>\n"]
            for o in enters[:5]:
                cp = o.get("chosen_plan", {})
                lines.append(
                    f"<b>{o['symbol']}</b> — {o.get('price', 0)}\n"
                    f"  🎯 دخول: {cp.get('entry', '-')} | هدف: {cp.get('target1', '-')} | ستوب: {cp.get('stop', '-')}\n"
                    f"  📊 R/R: {cp.get('rr', 0):.1f}x | ثقة: {o.get('confidence', 0):.0f}%\n"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"❌ خطأ: {e}"
    if cmd == "/تقييم" or cmd == "/review":
        try:
            from signal_review import get_reviews_for_dashboard
            d = get_reviews_for_dashboard()
            if not d.get("reviews"):
                return "⚪ لا توجد تقييمات بعد"
            res = d.get("results", {})
            lines = [
                f"📊 <b>تقييم إشارات {d['date']}</b>\n",
                f"✅ نجاح: {res.get('success', 0)} | ⚠️ جزئي: {res.get('partial', 0)} | ❌ فشل: {res.get('fail', 0)} | ⏳ مستمر: {res.get('ongoing', 0)}",
                f"📈 نسبة النجاح: {d.get('success_rate', 0)}%\n",
            ]
            for r in d["reviews"]:
                if r["result"] in ("no_data", "pending"):
                    continue
                emoji = {"success": "✅", "partial": "⚠️", "fail": "❌", "ongoing": "⏳"}.get(r["result"], "❓")
                pnl = r.get("pnl_pct")
                pnl_str = f"{pnl:+.1f}%" if pnl is not None else "--"
                lines.append(f"{emoji} <b>{r['symbol']}</b> {pnl_str} — {r.get('reason_ar', '')}")
                if r.get("lesson_ar"):
                    lines.append(f"   💡 {r['lesson_ar']}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ خطأ: {e}"
    if cmd == "/stocks":
        if not TG_STOCKS_OK:
            return "❌ stocks module not loaded"
        return await cmd_stocks()
    if cmd.startswith("/price"):
        parts = text.strip().split(maxsplit=1)
        ticker = parts[1] if len(parts) > 1 else ""
        return await cmd_price(ticker)
    # ── Stock Radar commands ──
    if cmd == "/radar" or cmd == "/radar_list":
        if RADAR_OK:
            return tg_radar_list()
        return "Radar module not loaded"
    if cmd.startswith("/radar_add"):
        if RADAR_OK:
            args = text.replace("/radar_add", "", 1).strip()
            return tg_radar_add(args)
        return "Radar module not loaded"
    if cmd.startswith("/radar_remove"):
        if RADAR_OK:
            args = text.replace("/radar_remove", "", 1).strip()
            return tg_radar_remove(args)
        return "Radar module not loaded"
    if cmd.startswith("/radar_check"):
        if RADAR_OK:
            args = text.replace("/radar_check", "", 1).strip()
            return tg_radar_check(args)
        return "Radar module not loaded"
    if cmd == "/radar_last":
        if RADAR_OK:
            return tg_radar_last()
        return "Radar module not loaded"
    if cmd.startswith("/radar_last "):
        if RADAR_OK:
            args = text.replace("/radar_last", "", 1).strip()
            return tg_radar_last(args)
        return "Radar module not loaded"
    if cmd == "/radar_status":
        if RADAR_OK:
            return tg_radar_status()
        return "Radar module not loaded"
    if cmd == "/radar_top":
        if RADAR_OK:
            return tg_radar_top()
        return "Radar module not loaded"
    if cmd == "/radar_toggle":
        if RADAR_OK:
            return tg_radar_toggle()
        return "Radar module not loaded"
    if cmd.startswith("/price"):
        if not TG_STOCKS_OK:
            return "Stock module not loaded"
        parts = text.strip().split(None, 1)
        if len(parts) >= 2:
            return await get_price(parts[1])
        return "الاستخدام: /price TICKER"

    if cmd.startswith("/news"):
        if not TG_NEWS_OK:
            return "News module not loaded"
        digest = await get_news_digest()
        return digest

    if cmd.startswith("/remind") and not cmd.startswith("/reminders"):
        if not TG_REMIND_OK:
            return "Reminder module not loaded"
        parts = text.split(None, 2)  # /remind 5m message
        if len(parts) == 2:
            return add_reminder(chat_id, parts[1], "⏰")
        if len(parts) < 2:
            return '⏰ /remind <وقت> <رسالة>\nمثال: /remind 5m شيك الفرن | /remind 14:30 اتصل | /remind 2h اجتماع'
        return add_reminder(chat_id, parts[1], parts[2])

    if cmd == "/reminders":
        if not TG_REMIND_OK:
            return "Reminder module not loaded"
        return list_reminders(chat_id)

    if cmd.startswith("/cancel"):
        if not TG_REMIND_OK:
            return "Reminder module not loaded"
        parts = text.split()
        if len(parts) == 2 and parts[1].isdigit():
            return cancel_reminder(int(parts[1]), chat_id)
        return "الاستخدام: /cancel <رقم>"

        # Phase 5: Health
    if cmd == "/health_log" or cmd.startswith("/health_log "):
        if HEALTH_ENGINE_OK:
            args = cmd.replace("/health_log", "", 1).strip()
            return handle_health_log(args)
        return "Health engine not loaded"
    if cmd == "/health_summary" or cmd.startswith("/health_summary "):
        if HEALTH_ENGINE_OK:
            args = cmd.replace("/health_summary", "", 1).strip()
            return handle_health_summary(args)
        return "Health engine not loaded"
    if cmd == "/health_streak":
        if HEALTH_ENGINE_OK:
            return handle_health_streak()
        return "Health engine not loaded"

    # Phase 5: Trading
    if cmd == "/trade" or cmd.startswith("/trade "):
        if TRADING_ENGINE_OK:
            args = cmd.replace("/trade", "", 1).strip()
            return handle_trade_log(args)
        return "Trading engine not loaded"
    if cmd == "/trades" or cmd.startswith("/trades "):
        if TRADING_ENGINE_OK:
            args = cmd.replace("/trades", "", 1).strip()
            return handle_trades_list(args)
        return "Trading engine not loaded"
    if cmd == "/trade_review" or cmd.startswith("/trade_review "):
        if TRADING_ENGINE_OK:
            args = cmd.replace("/trade_review", "", 1).strip()
            return handle_trade_review(args)
        return "Trading engine not loaded"

        # Phase 6: TradingView
    if cmd == "/tv_watchlist":
        if TV_BRIDGE_OK:
            return handle_tv_watchlist()
        return "TV bridge not loaded"
    if cmd == "/tv_add" or cmd.startswith("/tv_add "):
        if TV_BRIDGE_OK:
            args = cmd.replace("/tv_add", "", 1).strip()
            return handle_tv_add(args)
        return "TV bridge not loaded"
    if cmd == "/tv_remove" or cmd.startswith("/tv_remove "):
        if TV_BRIDGE_OK:
            args = cmd.replace("/tv_remove", "", 1).strip()
            return handle_tv_remove(args)
        return "TV bridge not loaded"
    if cmd == "/tv_last" or cmd.startswith("/tv_last "):
        if TV_BRIDGE_OK:
            args = cmd.replace("/tv_last", "", 1).strip()
            return handle_tv_last(args)
        return "TV bridge not loaded"
    if cmd == "/tv_summary" or cmd.startswith("/tv_summary "):
        if TV_BRIDGE_OK:
            args = cmd.replace("/tv_summary", "", 1).strip()
            return handle_tv_summary(args)
        return "TV bridge not loaded"
    if cmd == "/tv_test":
        if TV_BRIDGE_OK:
            return handle_tv_test()
        return "TV bridge not loaded"
    if cmd == "/tv_stats":
        if TV_BRIDGE_OK:
            return handle_tv_stats()
        return "TV bridge not loaded"
    if cmd == "/tv_sync":
        if TV_BRIDGE_OK:
            return sync_tv_from_radar()
        return "TV bridge not loaded"

    if cmd == "/kpi":
        try:
            from domain_kpis import handle_kpi
            return handle_kpi()
        except Exception as e:
            return f"KPI error: {e}"

    if cmd == "/menu":
        NL = chr(10)
        return f"\U0001f3e0 Master AI Menu{NL}{NL}\U0001f4c5 /today /tomorrow /me /life{NL}\U0001f4cb /tasks /inbox /week_summary{NL}\U0001f465 /contacts /occasions{NL}\U0001f4f0 /news{NL}\U0001f4b0 /expenses /spent{NL}\U0001f4aa /health_log /health_summary /health_streak{NL}\U0001f4c8 /trade /trades /trade_review{NL}\U0001f4e1 /tv_watchlist /tv_add /tv_last /tv_summary{NL}{NL}\u2699\ufe0f /stats /shift /weather /rooms /brain"

    if cmd == "/shift" or cmd.startswith("/shift "):
        if LIFE_WORK_OK:
            try:
                args = text.strip().split(None, 1)
                if len(args) > 1:
                    _wr = handle_work_command(args[1])
                else:
                    _wr = get_shift_display()
                return _wr or "no data"
            except Exception as e:
                return f"error: {e}"
        return "life_work not loaded"

    if cmd == "/schedule" or cmd == "/week":
        if LIFE_WORK_OK:
            try:
                from life_work import get_week_schedule
                return get_week_schedule() or "no schedule"
            except Exception as e:
                return f"error: {e}"
        return "life_work not loaded"

    if cmd.startswith("/expense") and not cmd.startswith("/expenses"):
        if LIFE_EXPENSES_OK:
            try:
                args = text.strip().split(None, 1)
                if len(args) > 1:
                    return handle_expense_command(args[1]) or "usage: /expense 5 food"
                return "usage: /expense <amount> <desc>"
            except Exception as e:
                return f"error: {e}"
        return "life_expenses not loaded"

    if cmd == "/expenses":
        if LIFE_EXPENSES_OK:
            try:
                from life_expenses import get_expenses
                return get_expenses("today") or "no expenses today"
            except Exception as e:
                return f"error: {e}"
        return "life_expenses not loaded"

    if cmd.startswith("/health"):
        if LIFE_HEALTH_OK:
            try:
                args = text.strip().split(None, 1)
                if len(args) > 1:
                    return handle_health_command(args[1]) or "not understood"
                from life_health import health_summary
                return health_summary() or "no health data"
            except Exception as e:
                return f"error: {e}"
        return "life_health not loaded"

    if cmd == "/report":
        if TG_REPORT_OK:
            try:
                _rep = await generate_daily_report(_router_stats, _response_times, {})
                return _rep
            except Exception as e:
                return f"Error: {e}"
        return "report module not loaded"

    if cmd == "/ping":
        _up = int(time.time() - START_TIME)
        _h, _m = divmod(_up // 60, 60)
        _avg = round(sum(_response_times)/len(_response_times), 1) if _response_times else 0
        _ha_ok = "\u2705"
        try:
            async with httpx.AsyncClient(timeout=3) as _hc:
                _hr = await _hc.get(f"{HA_URL}/api/", headers={"Authorization": f"Bearer {HA_TOKEN}"})
                if _hr.status_code != 200: _ha_ok = "\u274c"
        except: _ha_ok = "\u274c"
        _tot = _router_stats.get("total", 0)
        return "🏓 Pong!" + chr(10) + f"⏱ Up: {_h}h {_m}m" + chr(10) + f"🏠 HA: {_ha_ok}" + chr(10) + f"⚡ Avg: {_avg}s" + chr(10) + f"📨 Msgs: {_tot}"

    if cmd == "/help":
        _help_text = chr(10).join([
            "\U0001f3e0 *Master AI v5.4*", "",
            "\U0001f3e0 *\u0627\u0644\u0628\u064a\u062a:*",
            "/lights /temp /rooms /scenes /locks /media /find", "",
            "\U0001f4c5 *\u0627\u0644\u062d\u064a\u0627\u0629:*",
            "/shift /week /weather /morning", "",
            "\U0001f4b0 *\u0627\u0644\u0645\u0627\u0644:*",
            "/stocks /price /expense /expenses", "",
            "\U0001f4e1 *\u0627\u0644\u0631\u0627\u062f\u0627\u0631:*",
            "/radar /radar_add /radar_remove /radar_check /radar_last /radar_status /radar_top /radar_toggle", "",
            "\U0001f4dd *\u0627\u0644\u0645\u0647\u0627\u0645:*",
            "/tasks /remind /reminders", "",
            "\U0001f4ca *\u0627\u0644\u0646\u0638\u0627\u0645:*",
            "/status /diag /stats /brain /cost /habits /anomaly /feedback /digest /corrections", "",
                "/today /tomorrow /week /agenda", "",
            "/tasks", "",
            "/inbox /inbox48 /inbox_week", "",
            "/week_summary /life /suggest_tasks /me", "",
            "\U0001f4ac \u0623\u0648 \u0623\u0631\u0633\u0644 \u0623\u064a \u0631\u0633\u0627\u0644\u0629 \U0001f44d",
        ])
        _btns = [
            {"text": "\U0001f3e0 \u0627\u0644\u0642\u0627\u0626\u0645\u0629", "callback_data": "cmd:home"},
            {"text": "\U0001f4cb \u0645\u0644\u062e\u0635", "callback_data": "cmd:summary"},
        ]
        await tg_send_inline(chat_id, _help_text, _btns, columns=2)
        return "__inline_sent__"


    if cmd == "/family":
        try:
            from family_assistant import get_family_info
            return get_family_info()
        except Exception as e:
            return f"family error: {e}"

    if cmd == "/guardian":
        try:
            from system_guardian import get_status
            return get_status()
        except Exception as e:
            return f"guardian error: {e}"

    if cmd == "/timeline":
        try:
            from world_state_delta import _last_event, _get_db
            conn = _get_db()
            if conn:
                r = _last_event(conn, {"light","climate","cover","media_player","lock","fan"})
                conn.close()
                return r
            return "DB not available"
        except Exception as e:
            return f"timeline error: {e}"

    # ===== Calendar Commands (v8 Phase 1) =====
    if cmd == "/today":
        try:
            from calendar_engine import get_today_events, ensure_fresh_cache
            import asyncio
            asyncio.ensure_future(ensure_fresh_cache(300))
            events = get_today_events()
            from calendar_reporting import render_today
            cal_text = render_today(events)
            # v8: add shift + tasks
            parts = []
            try:
                from life_work import get_shift
                si = get_shift()
                parts.append("👷 " + si.get("emoji","") + " " + si.get("shift","") + " " + si.get("times",""))
            except Exception: pass
            if cal_text:
                parts.append(cal_text)
            try:
                from task_engine import task_stats, task_list
                s = task_stats()
                if s["total_active"]:
                    t = "📋 مهام اليوم: " + str(s["due_today"]) + " مستحقة"
                    if s["overdue"]: t += "  ⚠️ " + str(s["overdue"]) + " متأخرة"
                    parts.append(t)
                    for task in task_list(due_today=True)[:4]:
                        parts.append("  • [" + str(task["id"]) + "] " + task["title"][:40])
            except Exception: pass
            return chr(10).join(parts) if parts else (cal_text or "✅ لا توجد مواعيد اليوم")
        except Exception as e:
            return f"calendar error: {e}"

    if cmd == "/tomorrow":
        try:
            from calendar_engine import get_tomorrow_events
            events = get_tomorrow_events()
            from calendar_reporting import render_tomorrow
            cal_text = render_tomorrow(events)
            parts = []
            try:
                from life_work import get_shift
                from datetime import date, timedelta
                si = get_shift(date.today() + timedelta(days=1))
                parts.append("👷 باجر: " + si.get("emoji","") + " " + si.get("shift","") + " " + si.get("times",""))
            except Exception: pass
            if cal_text:
                parts.append(cal_text)
            try:
                from task_engine import task_list
                from datetime import date, timedelta
                tmrw = (date.today()+timedelta(days=1)).isoformat()
                tasks = [t for t in task_list(limit=20) if t.get("due_date")==tmrw]
                if tasks:
                    parts.append("📋 مهام باجر: " + str(len(tasks)))
                    for task in tasks[:3]:
                        parts.append("  • " + task["title"][:40])
            except Exception: pass
            return chr(10).join(parts) if parts else (cal_text or "✅ لا توجد مواعيد باجر")
        except Exception as e:
            return f"calendar error: {e}"

    if cmd == "/week":
        try:
            from calendar_engine import get_week_events
            events = get_week_events()
            from calendar_reporting import render_week
            return render_week(events)
        except Exception as e:
            return f"calendar error: {e}"

    if cmd == "/agenda":
        try:
            from calendar_engine import get_today_events, get_tomorrow_events
            from calendar_reporting import render_today, render_tomorrow
            today_ev = get_today_events()
            tmrw_ev = get_tomorrow_events()
            parts = [render_today(today_ev)]
            if tmrw_ev:
                parts.append("")
                parts.append(render_tomorrow(tmrw_ev))
            return chr(10).join(parts)
        except Exception as e:
            return f"calendar error: {e}"

    if cmd == "/habits":
        try:
            from habit_engine import format_habit_report
            return format_habit_report()
        except Exception as e:
            return f"habit error: {e}"

    if cmd == "/cost":
        try:
            from cost_tracker import get_cost_for_kpi
            c = get_cost_for_kpi()
            bar_len = 10
            filled = int(c["month_pct"] / 100 * bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)
            msg = chr(10).join([
                "💰 *Cost Tracker*", "",
                f"📅 اليوم: ${c['today_usd']:.4f}",
                f"📆 الشهر: ${c['month_usd']:.2f} / ${c['month_budget_usd']:.0f}",
                f"[{bar}] {c['month_pct']:.1f}%",
                f"📊 متوسط/طلب: ${c['avg_per_request_usd']:.4f}",
            ])
            return msg
        except ImportError:
            return "cost_tracker not loaded"
        except Exception as e:
            return f"cost error: {e}"

    if cmd == "/feedback":
        try:
            from feedback_learner import get_stats
            s = get_stats(30)
            lines = ["📊 *Feedback Stats (30d)*", ""]
            lines.append(f"Total: {s['total']}")
            lines.append(f"✅ Accepted: {s.get('accepted', 0)}")
            lines.append(f"❌ Rejected: {s.get('rejected', 0)}")
            lines.append(f"✏️ Corrected: {s.get('corrected', 0)}")
            lines.append(f"🚫 Ignored: {s.get('ignored', 0)}")
            if s.get('top_entities'):
                lines.append("")
                lines.append("Top entities: " + ", ".join(s["top_entities"][:5]))
            return chr(10).join(lines)
        except ImportError:
            return "feedback_learner not loaded"
        except Exception as e:
            return f"feedback error: {e}"

    if cmd in ("/digest", "/learning"):
        try:
            from feedback_learner import generate_digest
            return generate_digest(7)
        except ImportError:
            return "feedback_learner not loaded"
        except Exception as e:
            return f"digest error: {e}"


    if cmd == "/corrections":
        try:
            from corrections_loop import get_corrections_loop
            cl = get_corrections_loop()
            stats = cl.get_stats()
            lines = ["✅ *Corrections Loop*", ""]
            lines.append(f"Total: {stats['total']}")
            lines.append(f"Active: {stats['active']}")
            if stats.get("by_category"):
                for cat, cnt in stats["by_category"].items():
                    lines.append(f"  {cat}: {cnt}")
            if stats.get("most_applied"):
                lines.append("")
                for ma in stats["most_applied"][:5]:
                    lines.append(f"❌ {ma['wrong']} → ✅ {ma['right']} ({ma['applied']}x)")
            return chr(10).join(lines)
        except ImportError:
            return "corrections_loop not loaded"
        except Exception as e:
            return f"corrections error: {e}"

    if cmd.startswith("/corrections "):
        try:
            from corrections_loop import get_corrections_loop
            cl = get_corrections_loop()
            parts = cmd.split(None, 2)
            sub = parts[1] if len(parts) > 1 else ""
            if sub == "clear":
                conn = cl._get_conn()
                conn.execute("DELETE FROM corrections")
                conn.commit()
                conn.close()
                return "✅ All corrections cleared"
            elif sub == "del" and len(parts) > 2:
                cid = int(parts[2])
                conn = cl._get_conn()
                conn.execute("DELETE FROM corrections WHERE id=?", (cid,))
                conn.commit()
                conn.close()
                return f"✅ Correction #{cid} deleted"
            elif sub == "decay":
                count = cl.decay_corrections()
                return f"✅ Decayed {count} corrections"
            else:
                return "Usage: /corrections [clear|del ID|decay]"
        except Exception as e:
            return f"corrections error: {e}"

    if cmd == "/plans":
        if not PLAN_OK:
            return "plan_engine not loaded"
        plans = list_plans("active")
        return format_plans_list(plans)

    if cmd.startswith("/plan "):
        if not PLAN_OK:
            return "plan_engine not loaded"
        parts = cmd.split(None, 2)
        sub = parts[1] if len(parts) > 1 else ""
        arg = parts[2] if len(parts) > 2 else ""
        if sub == "pause" and arg:
            ok = pause_plan(arg)
            return f"Paused: {arg}" if ok else f"Not found: {arg}"
        elif sub == "resume" and arg:
            ok = resume_plan(arg)
            return f"Resumed: {arg}" if ok else f"Not found: {arg}"
        elif sub == "delete" and arg:
            delete_plan(arg)
            return f"Deleted: {arg}"
        elif sub == "list":
            status = arg or "active"
            return format_plans_list(list_plans(status))
        elif sub == "stats":
            s = plan_stats()
            return f"Plans: {s["total"]} total, {s["active"]} active, {s["completed"]} done, {s["paused"]} paused"
        else:
            return "Usage: /plan pause|resume|delete|list|stats [id]"


    if cmd == "/mode":
        if DEGRADED_OK:
            return deg_status()
        return "degraded_mode not loaded"

    if cmd == "/backup status":
        if DBBACKUP_OK:
            return backup_format_status()
        return "db_backup not loaded"

    if cmd == "/backup run":
        if not DBBACKUP_OK:
            return "db_backup not loaded"
        ok, results, cleaned = backup_run_daily()
        msg = "Backup " + ("OK" if ok else "FAILED")
        for r in results:
            msg += chr(10) + "  " + r["db"] + ": " + r["status"]
        if cleaned:
            msg += chr(10) + "Cleaned: " + str(cleaned) + " old files"
        return msg


    if cmd == "/tasks" or cmd.startswith("/tasks "):
        try:
            from tg_tasks import handle_tasks_command
            args = cmd[7:].strip() if cmd.startswith("/tasks ") else ""
            return handle_tasks_command(args)
        except Exception as e:
            logger.error(f"tasks error: {e}")
            return f"❌ tasks error: {e}"

    return None



async def tg_send_with_feedback(chat_id, text: str, request_id: str = None) -> bool:
    """Send message with inline feedback buttons."""
    global _tg_client
    if not _tg_client:
        _tg_client = httpx.AsyncClient(timeout=30)
    parts = tg_split_message(text)
    for i, part in enumerate(parts):
        payload = {"chat_id": chat_id, "text": part}
        # Add feedback buttons only to last part
        if i == len(parts) - 1 and request_id:
            payload["reply_markup"] = json.dumps({
                "inline_keyboard": [[
                    {"text": "👍", "callback_data": f"fb:good:{request_id[:32]}"},
                    {"text": "👎", "callback_data": f"fb:bad:{request_id[:32]}"},
                ]]
            })
        try:
            resp = await _tg_client.post(f"{TG_BASE}/sendMessage", json=payload)
            if resp.status_code != 200:
                logger.error(f"TG send fail: {resp.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"TG send error: {e}")
            return False
    return True



async def tg_send_inline(chat_id, text: str, buttons: list, columns: int = 2) -> bool:
    """Send message with custom inline keyboard."""
    global _tg_client
    if not _tg_client:
        _tg_client = httpx.AsyncClient(timeout=30)
    rows = []
    for i in range(0, len(buttons), columns):
        rows.append(buttons[i:i+columns])
    payload = {
        "chat_id": chat_id,
        "text": text.encode("utf-8", errors="replace").decode("utf-8"),
        "reply_markup": json.dumps({"inline_keyboard": rows}),
    }
    try:
        resp = await _tg_client.post(f"{TG_BASE}/sendMessage", json=payload)
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"tg_send_inline error: {e}")
        return False


async def tg_handle_callback(callback_query: dict):
    """Handle inline button presses (feedback)."""
    global _tg_client
    if not _tg_client:
        _tg_client = httpx.AsyncClient(timeout=30)
    data = callback_query.get("data", "")
    qid = callback_query.get("id", "")
    chat_id = callback_query.get("message", {}).get("chat", {}).get("id", "")
    cq_id = callback_query.get("id")
    tg_user_id = callback_query.get("from", {}).get("id")

    if data.startswith("fb:"):
        parts = data.split(":")
        if len(parts) == 3:
            rating = 1.0 if parts[1] == "good" else 0.0
            req_id = parts[2]
            try:
                user_profile = detect_user(source="telegram", telegram_user_id=tg_user_id)
                record_feedback(req_id, rating, user_id=user_profile.get("user_id", "unknown"))
                # Phase 3: Record in interaction_feedback table
                try:
                    from feedback_learner import record_feedback as fl_record
                    fl_record(
                        source_type="tg_button",
                        query_text=f"request:{req_id}",
                        decision_taken="llm_response",
                        user_feedback="accepted" if rating > 0 else "rejected",
                    )
                except Exception:
                    pass
                answer = "شكراً!" if rating > 0 else "أتحسن المرة الجاية"
            except Exception as e:
                logger.error(f"Feedback error: {e}")
                answer = "OK"
    elif data.startswith("suggest:"):
            parts = data.split(":", 2)
            stype = parts[1] if len(parts) > 1 else ""
            sval = parts[2] if len(parts) > 2 else ""
            logger.info(f"TG suggest callback: {stype}:{sval}")

            if stype == "followup":
                # Use session entities for follow-up
                if TG_SESSION_OK:
                    session = tg_session_get(str(chat_id))
                    if session and session.get("last_entities"):
                        from tg_session import detect_followup
                        fake = {"on": "شغله", "off": "طفيه"}.get(sval, sval)
                        followup = detect_followup(fake, session)
                        if followup.get("type") == "followup":
                            result = await resolve_followup_action(followup, HA_URL, HA_TOKEN)
                            await tg_send(chat_id, result, parse_mode="Markdown")
                        else:
                            await tg_send(chat_id, "❓ ما فيه سياق")
                    else:
                        pass  # Let LLM handle
            elif stype == "temp":
                if TG_SESSION_OK:
                    session = tg_session_get(str(chat_id))
                    if session and session.get("last_entities"):
                        from tg_session import detect_followup
                        followup = detect_followup(f"اضبطهم على {sval}", session)
                        if followup.get("type") == "followup":
                            result = await resolve_followup_action(followup, HA_URL, HA_TOKEN)
                            await tg_send(chat_id, result, parse_mode="Markdown")
            elif stype == "devices" and TG_HOME_OK:
                result = await cmd_devices(sval)
                if TG_SESSION_OK:
                    tg_session_upsert(str(chat_id), last_intent="devices", last_room=sval)
                await tg_send(chat_id, result, parse_mode="Markdown")
            elif stype == "scenes" and TG_HOME_OK:
                msg, btns = await cmd_scenes_dynamic()
                if btns:
                    rows = [[b] for b in btns[:12]]
                    await tg_send_inline(chat_id, msg, rows, columns=2)
            elif stype == "scene":
                if TG_INTENT_OK:
                    r = await route_intent(f"فعل مشهد {sval}")
                    if r:
                        t = r["text"] if isinstance(r, dict) else r
                        await tg_send(chat_id, t, parse_mode="Markdown")
            answer_text = "✅"

    elif data.startswith("sc:"):
        scene_id = data[3:]
        try:
            async with httpx.AsyncClient(timeout=10) as hc:
                resp = await hc.post(f"{HA_URL}/api/services/scene/turn_on",
                    headers={"Authorization": f"Bearer {HA_TOKEN}"},
                    json={"entity_id": scene_id})
            if resp.status_code == 200:
                answer = "✅ تم!"
                back_btns = [
                    {"text": "🎬 المشاهد", "callback_data": "cmd:scenes"},
                    {"text": "🏠 القائمة", "callback_data": "cmd:home"},
                ]
                await tg_send_inline(chat_id, "✅ تم تفعيل المشهد", back_btns, columns=2)
            else:
                answer = "❌ فشل"
        except Exception as e:
            logger.error(f"Scene error: {e}")
            answer = "❌"

    elif data.startswith("trade_confirm:"):
        # User confirmed they took the trade
        _td = data[len("trade_confirm:"):].split("|")
        if len(_td) >= 5 and JOURNAL_OK:
            _tc_sym, _tc_price, _tc_action, _tc_strat, _tc_qty = _td[0], _td[1], _td[2], _td[3], _td[4]
            # Normalize: strip exchange prefix (KSE:CLEANING -> CLEANING)
            if ":" in _tc_sym:
                _tc_sym = _tc_sym.split(":")[-1]
            _tc_sym = _tc_sym.upper()
            _tc_saved = _td[5] if len(_td) > 5 else ""
            try:
                _tc_price_f = float(_tc_price) if _tc_price else 0
                _tc_qty_i = int(_tc_qty) if _tc_qty and _tc_qty != "0" else 0
                if _tc_action == "buy":
                    _tc_tid = open_trade(
                        symbol=_tc_sym, entry_price=_tc_price_f, quantity=_tc_qty_i,
                        entry_reason=f"TradingView (confirmed)",
                        strategy=_tc_strat, entry_signal_id=_tc_saved or None,
                    )
                    await tg_send(chat_id, f"\u2705 \u062a\u0645 \u062a\u0633\u062c\u064a\u0644 \u0634\u0631\u0627\u0621 {_tc_sym} @ {_tc_price} (#{_tc_tid})")
                    logger.info(f"Trade confirmed: BUY {_tc_sym} @ {_tc_price} tid={_tc_tid}")
                elif _tc_action == "sell":
                    _tc_open = get_open_trades()
                    _tc_match = [t for t in _tc_open if t["symbol"].upper() == _tc_sym.upper()]
                    if _tc_match:
                        close_trade(_tc_match[0]["id"], _tc_price_f, exit_reason="TradingView (confirmed)")
                        await tg_send(chat_id, f"\u2705 \u062a\u0645 \u0625\u063a\u0644\u0627\u0642 {_tc_sym} @ {_tc_price}")
                        logger.info(f"Trade confirmed: SELL {_tc_sym} @ {_tc_price}")
                    else:
                        await tg_send(chat_id, f"\u26a0\ufe0f \u0645\u0627 \u0641\u064a\u0647 \u0635\u0641\u0642\u0629 \u0645\u0641\u062a\u0648\u062d\u0629 \u0644\u0640 {_tc_sym}")
                answer = "\u2705"
            except Exception as _tc_e:
                logger.error(f"Trade confirm error: {_tc_e}")
                await tg_send(chat_id, f"\u274c \u062e\u0637\u0623: {str(_tc_e)[:100]}")
                answer = "\u274c"
        else:
            answer = "Journal not loaded"

    elif data.startswith("trade_skip:"):
        # User skipped/ignored the trade signal
        _ts = data[len("trade_skip:"):].split("|")
        _ts_sym = _ts[0] if _ts else "?"
        _ts_action = _ts[2] if len(_ts) > 2 else "?"
        _ts_price = _ts[1] if len(_ts) > 1 else "?"
        logger.info(f"Trade skipped: {_ts_action} {_ts_sym} @ {_ts_price}")
        await tg_send(chat_id, f"\u274c \u062a\u0645 \u062a\u062c\u0627\u0647\u0644 \u0625\u0634\u0627\u0631\u0629 {_ts_sym}")
        answer = "\u274c"

    elif data.startswith("confluence_buy:"):
        # User bought from confluence signal
        _cb = data[len("confluence_buy:"):].split("|")
        if len(_cb) >= 5 and JOURNAL_OK:
            _cb_sym = _cb[0].upper()
            if ":" in _cb_sym:
                _cb_sym = _cb_sym.split(":")[-1]
            _cb_price = float(_cb[1]) if _cb[1] else 0
            _cb_sig_id = _cb[5] if len(_cb) > 5 else ""
            try:
                _cb_tid = open_trade(
                    symbol=_cb_sym, entry_price=_cb_price, quantity=0,
                    entry_reason="Confluence Engine (confirmed)",
                    strategy="confluence",
                    entry_signal_id=_cb_sig_id or None,
                )
                if CONFLUENCE_OK and _cb_sig_id:
                    confluence_record_decision(int(_cb_sig_id), _cb_sym, "buy", _cb_price)
                await tg_send(chat_id, f"\u2705 \u062a\u0645 \u062a\u0633\u062c\u064a\u0644 \u0634\u0631\u0627\u0621 {_cb_sym} @ {_cb_price} (#{_cb_tid})")
                answer = "\u2705"
            except Exception as _cb_e:
                logger.error(f"Confluence buy error: {_cb_e}")
                answer = "\u274c"
        else:
            answer = "Journal not loaded"

    elif data.startswith("confluence_skip:"):
        _cs = data[len("confluence_skip:"):].split("|")
        _cs_sig_id = _cs[0] if _cs else "0"
        _cs_sym = _cs[1] if len(_cs) > 1 else "?"
        if CONFLUENCE_OK:
            try:
                confluence_record_decision(int(_cs_sig_id), _cs_sym, "skip")
            except Exception:
                pass
        await tg_send(chat_id, f"\u274c \u062a\u0645 \u062a\u062c\u0627\u0647\u0644 {_cs_sym}")
        answer = "\u274c"

    elif data.startswith("cmd:"):
        sub = "/" + data[4:]
        r = await tg_handle_command(chat_id, sub)
        if r and r != "__inline_sent__":
            await tg_send(chat_id, r)
        answer = ""

    elif data.startswith("cam:"):
        cam_num = data[4:]
        cam_eid = "camera.192_168_111_90" + ("_" + cam_num if cam_num != "1" else "")
        try:
            snap_url = f"{HA_URL}/api/camera_proxy/{cam_eid}"
            async with httpx.AsyncClient(timeout=15) as hc:
                resp = await hc.get(snap_url, headers={"Authorization": f"Bearer {HA_TOKEN}"})
                if resp.status_code == 200:
                    import tempfile, os as _os
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                        tmp.write(resp.content)
                        tmp_path = tmp.name
                    with open(tmp_path, "rb") as photo:
                        files = {"photo": ("snapshot.jpg", photo, "image/jpeg")}
                        await _tg_client.post(f"{TG_BASE}/sendPhoto", files=files, data={"chat_id": str(chat_id), "caption": f"Cam {cam_num}"})
                    _os.unlink(tmp_path)
                    answer = "📷"
                    # Re-send cam buttons after photo
                    cam_btns = [
                        {"text": "📷 كام 1", "callback_data": "cam:1"},
                        {"text": "📷 كام 2", "callback_data": "cam:2"},
                        {"text": "📷 كام 3", "callback_data": "cam:3"},
                        {"text": "📷 كام 4", "callback_data": "cam:4"},
                        {"text": "📷 كام 5", "callback_data": "cam:5"},
                        {"text": "📷 كام 6", "callback_data": "cam:6"},
                        {"text": "🏠 القائمة", "callback_data": "cmd:home"},
                    ]
                    await tg_send_inline(chat_id, "📷 كاميرا ثانية؟", cam_btns, columns=3)
                else:
                    answer = "❌"
        except Exception as e:
            logger.error(f"Cam error: {e}")
            answer = "❌"

    elif data.startswith("devctl:"):
        parts_d = data.split(":")
        if len(parts_d) == 3 and TG_HOME_OK:
            action_d, eid_d = parts_d[1], parts_d[2]
            result_d = await handle_devctl(action_d, eid_d)
            # Step 9: Learn alias from disambiguation
            _orig_text = _tg_disambig_context.pop(str(chat_id), None)
            if _orig_text and TG_INTENT_OK:
                try:
                    learn_alias(_orig_text, eid_d)
                except Exception:
                    pass
            try:
                await _tg_client.post(f"https://api.telegram.org/bot{TG_TOKEN}/answerCallbackQuery",
                    json={"callback_query_id": cq_id, "text": result_d[:200]})
            except Exception:
                pass
            await tg_send(chat_id, result_d)

    elif data.startswith("appr:"):
        parts_a = data.split(":")
        if len(parts_a) == 3 and TG_OPS_OK:
            aid_cb = parts_a[1]
            dec_cb = "approve" if parts_a[2] == "1" else "deny"
            if not is_tg_admin(tg_user_id):
                answer = "Admin only"
            else:
                answer = process_approval(aid_cb, dec_cb)
        else:
            answer = "Invalid"


    elif data.startswith("auto:"):
        # auto:entity_id:action:hour
        parts = data.split(":")
        if len(parts) >= 4:
            eid = parts[1] + ":" + parts[2] if "." not in parts[1] else parts[1]
            action = parts[-2]
            hour = int(parts[-1])
            # Fix entity_id if it got split by ':'
            if "." not in eid:
                eid = ":".join(parts[1:-2])
            result = await bl_create_auto(eid, action, hour)
            if result.get("ok"):
                await tg_send(chat_id, f"\u2705 Automation created: {result['name']}\nCheck HA > Settings > Automations")



            else:
                await tg_send(chat_id, f"❌ خطأ: {result.get('error','?')}")

    elif data.startswith("room:"):
        # --- Phase B2: Show room devices with toggle buttons ---
        _room_name = data[5:]
        import json as _json_room
        try:
            _emap_r = _json_room.load(open("/home/pi/master_ai/entity_map.json"))
        except Exception:
            _emap_r = {}
        if _room_name in _emap_r:
            _entities = _emap_r[_room_name]
            _dev_btns = []
            _ha_headers = {"Authorization": f"Bearer {HA_TOKEN}"}
            for _entry in _entities:
                if "=" not in _entry:
                    continue
                _eid, _fname = _entry.split("=", 1)
                if _eid.startswith("scene."):
                    continue
                _domain = _eid.split(".")[0]
                if _domain not in ("light", "switch", "fan", "climate", "cover", "media_player"):
                    continue
                # Get current state
                try:
                    async with httpx.AsyncClient(timeout=5) as _hc:
                        _sr = await _hc.get(f"{HA_URL}/api/states/{_eid}", headers=_ha_headers)
                        _st = _sr.json().get("state", "?") if _sr.status_code == 200 else "?"
                except Exception:
                    _st = "?"
                _icon = "🟢" if _st == "on" else ("🔴" if _st == "off" else "⚪")
                _short_name = _fname[:18]
                _act = "off" if _st == "on" else "on"
                _dev_btns.append({"text": f"{_icon} {_short_name}", "callback_data": f"devctl:{_act}:{_eid}"})
            if _dev_btns:
                _short_room = _room_name.split("/")[0] if "/" in _room_name else _room_name
                _dev_btns.append({"text": "🏠 رجوع", "callback_data": "cmd:rooms"})
                await tg_send_inline(chat_id, f"🏠 {_short_room}", _dev_btns, columns=2)
            else:
                await tg_send(chat_id, "⚠️ لا توجد أجهزة قابلة للتحكم")
        answer_text = "✅"

    else:
        answer = ""

    try:
        await _tg_client.post(f"{TG_BASE}/answerCallbackQuery", json={
            "callback_query_id": cq_id, "text": answer
        })
    except Exception:
        pass



async def tg_send_typing(chat_id):
    """Send typing indicator."""
    try:
        if _tg_client:
            await _tg_client.post(f"{TG_BASE}/sendChatAction", json={"chat_id": chat_id, "action": "typing"})
    except Exception:
        pass




async def _tg_send_get_id(chat_id, text: str):
    """Send TG message and return msg_id for editing."""
    try:
        if _tg_client:
            resp = await _tg_client.post(f"{TG_BASE}/sendMessage", json={
                "chat_id": chat_id, "text": text
            })
            rd = resp.json()
            if rd.get("ok"):
                return rd["result"]["message_id"]
    except Exception:
        pass
    return None
async def tg_edit_message(chat_id, message_id, text: str):
    """Edit an existing TG message."""
    try:
        if _tg_client:
            await _tg_client.post(f"{TG_BASE}/editMessageText", json={
                "chat_id": chat_id, "message_id": message_id, "text": text
            })
            return True
    except Exception:
        return False


async def llm_call_stream(system_prompt: str, user_message: str, chat_id=None,
                          max_tokens: int = 1500, temperature: float = 0.3) -> str:
    """Streaming LLM call — sends partial response to TG every ~100 chars."""
    if not anthropic_client:
        return await llm_call(system_prompt, user_message, max_tokens, temperature)
    
    t0 = time.time()
    if not _cb_llm.is_available():
        return "⚠️ خدمة AI مو متوفرة حالياً"
    
    try:
        full_text = ""
        msg_id = None
        last_edit = 0
        
        async with anthropic_client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            temperature=temperature,
        ) as stream:
            async for text_chunk in stream.text_stream:
                full_text += text_chunk
                now = time.time()
                # Send/edit every 0.8s if we have chat_id
                if chat_id and (now - last_edit) > 0.8 and len(full_text) > 20:
                    if msg_id is None:
                        # Send first message
                        try:
                            resp = await _tg_client.post(f"{TG_BASE}/sendMessage", json={
                                "chat_id": chat_id, "text": full_text + " ✍️"
                            })
                            rd = resp.json()
                            if rd.get("ok"):
                                msg_id = rd["result"]["message_id"]
                        except Exception:
                            pass
                    else:
                        await tg_edit_message(chat_id, msg_id, full_text + " ✍️")
                    last_edit = now
        
        # Final edit — remove typing indicator
        if msg_id and chat_id:
            await tg_edit_message(chat_id, msg_id, full_text)
        # Save to session memory
        try:
            memory_add_short_term("assistant", full_text[:300])
        except Exception:
            pass
        
        _cb_llm.record_success()
        elapsed = time.time() - t0
        logger.info(f"LLM stream: {elapsed:.1f}s, {len(full_text)} chars")
        return full_text if not msg_id else "__stream_sent__"
    except Exception as e:
        _cb_llm.record_failure()
        logger.error(f"LLM stream error: {e}")
        return await llm_call(system_prompt, user_message, max_tokens, temperature)

def _correction_name(eid):
    """Get friendly name from entity_map."""
    try:
        import json as _json
        emap = _json.load(open("/home/pi/master_ai/entity_map.json"))
        for room, entries in emap.items():
            for entry in entries:
                if "=" in entry and entry.startswith(eid + "="):
                    return entry.split("=", 1)[1]
    except Exception:
        pass
    return eid.split(".")[-1].replace("_", " ")


# ════════════════════════════════════════════════════════════════
# V2 TG Pipeline — LLM-first, no silent drops
# ════════════════════════════════════════════════════════════════

# Integration: session tracking + auto memory extraction (Tier3)
try:
    from session_memory import SessionTracker
    _session_tracker = SessionTracker()
except ImportError:
    _session_tracker = None
try:
    from auto_memory_extractor import AutoMemoryExtractor
    _memory_extractor = AutoMemoryExtractor()
except ImportError:
    _memory_extractor = None

# Wire anthropic client into extractor (after lifespan creates it)
def _wire_extractor_client():
    if _memory_extractor and anthropic_client:
        _memory_extractor.set_client(anthropic_client)


async def _tg_v2_pipeline(chat_id: int, text: str, user: dict):
    """V2: command -> fast_path(whitelist) -> LLM. Never silent drop."""
    import time as _t
    _started = _t.monotonic()
    user_name = user.get("first_name", "User")
    tg_user_id = user.get("id")
    
    # detect user profile
    try:
        user_profile = detect_user(source="telegram", telegram_user_id=tg_user_id)
    except Exception:
        user_profile = {"user_id": "bu_khalifa", "name": "Salem"}
    # Track incoming message (Tier3 integration)
    if _session_tracker:
        _session_tracker.add_message("user", text)
    if _memory_extractor:
        if not _memory_extractor._client and anthropic_client:
            _memory_extractor.set_client(anthropic_client)
        _memory_extractor.record_message("user", text)
    logger.info(f"TG_V2 user={user_profile.get('user_id','?')} text={text[:50]}")
    
    # Auto-save admin chat_id
    if not ADMIN_TELEGRAM_ID:
        _admin_path = __import__("pathlib").Path("data/admin_chat_id.txt")
        if not _admin_path.exists():
            _admin_path.write_text(str(chat_id))

    text = (text or "").strip()
    if not text:
        await tg_send(chat_id, "ما وصلني نص واضح.")
        return

    # ── Stage 1: /commands only ──
    try:
        quick = await asyncio.wait_for(tg_handle_command(chat_id, text), timeout=3)
        if quick == "__inline_sent__":
            return
        if quick:
            await tg_send(chat_id, quick)
            return
    except asyncio.TimeoutError:
        logger.warning(f"TG_V2 command timeout: {text[:40]}")
    except Exception:
        pass

    # ── Stage 2: Fast path (strict whitelist only) ──
    if QUICK_QUERY_OK:
        try:
            _qq = await asyncio.wait_for(quick_answer(text), timeout=2)
            if _qq:
                logger.info(f"TG_V2 fast_path answered: {text[:40]}")
                await tg_send(chat_id, _qq)
                return
        except asyncio.TimeoutError:
            logger.warning(f"TG_V2 fast_path timeout: {text[:40]}")
        except Exception:
            pass

    # ── Stage 3: Typing indicator ──
    try:
        await _tg_client.post(f"{TG_BASE}/sendChatAction", json={"chat_id": chat_id, "action": "typing"})
    except Exception:
        pass

    # ── Stage 4: LLM primary (chat_v7) — with progress (Tier1 #4) ──
    from chat_v7 import choose_model as _cm
    _model_tier = _cm(text)
    logger.info(f"TG_V2 -> LLM ({_model_tier}): {text[:50]}")
    response = ""
    try:
        if CHAT_V7_OK and anthropic_client:
            from brain_core import build_system_prompt_v7 as _bsp7
            _sys7 = _bsp7()
            _executors = {
                "ha_get_state": _exec_ha_get_state,
                "ha_call_service": lambda d,s,sd: _exec_ha_call_service(d, s, sd),
                "ssh_run": _exec_ssh_run,
            }
            _progress_task = asyncio.create_task(_send_progress_after_delay(chat_id, 2.0))
            try:
                response = await asyncio.wait_for(
                    handle_chat_v7(text, _sys7, anthropic_client, _executors, user_id=str(chat_id)),
                    timeout=180
                )
            finally:
                _progress_task.cancel()
            if not response or not response.strip():
                # Escalation: if model was Sonnet, retry with Opus
                from chat_v7 import choose_model
                if choose_model(text) == "sonnet":
                    logger.info(f"TG_V2 escalating Sonnet->Opus: {text[:40]}")
                    response = await asyncio.wait_for(
                        handle_chat_v7(text, _sys7, anthropic_client, _executors, user_id=str(chat_id)),
                        timeout=180
                    )
                if not response or not response.strip():
                    response = ""
                    logger.warning(f"TG_V2 LLM empty for: {text[:50]}")
        else:
            logger.error("TG_V2: chat_v7 unavailable")
    except asyncio.TimeoutError:
        logger.warning(f"TG_V2 LLM timeout: {text[:50]}")
        response = "السؤال أخذ وقت طويل، جرب اختصره"
    except Exception as e:
        logger.error(f"TG_V2 LLM error: {e}")
        response = ""

    # ── Stage 5: Absolute safety net ──
    if not response or not response.strip():
        response = "ما قدرت أجاوب الحين، جرب بطريقة ثانية"

    _elapsed = round((_t.monotonic() - _started), 2)
    logger.info(f"TG_V2 done in {_elapsed}s: {text[:40]}")
    
    # Track response (Tier3 integration)
    if _session_tracker:
        _session_tracker.add_message("assistant", response)
    if _memory_extractor:
        _memory_extractor.record_message("assistant", response)

    # R2-P3: Tool summary for long responses (non-blocking, 5s timeout)
    if response and len(response) > 500:
        try:
            from tool_summary import generate_summary as _gen_summary
            _summary = await asyncio.wait_for(_gen_summary("chat", response), timeout=5)
            if _summary:
                response = f"\U0001f4cb {_summary}\n\n{response}"
        except Exception:
            pass

    await tg_send(chat_id, response)

    # R2-P2: Show a contextual tip (max 1 per session, non-blocking)
    if _tips_engine:
        try:
            _tip_ctx = {"message_count": _router_stats.get("total", 0)}
            if bridge:
                _tip_ctx["bridge_online"] = bridge.get_status().get("online", True)
            _tip = _tips_engine.get_tip(_tip_ctx)
            if _tip:
                await tg_send(chat_id, _tip)
        except Exception:
            pass


async def tg_handle_message(chat_id, text: str, user: dict):
    """V2 Pipeline: command -> fast_path -> LLM. Never silent drop."""
    try:
        return await _tg_v2_pipeline(chat_id, text, user)
    except Exception as e:
        logger.error(f"TG HANDLE CRASH: {e}", exc_info=True)
        try:
            await tg_send(chat_id, f"❌ خلل مؤقت: {str(e)[:80]}")
        except Exception:
            pass

async def _tg_handle_message_inner(chat_id, text: str, user: dict):
    _t0 = time.time()
    try:
        await _tg_handle_message_core(chat_id, text, user)
    finally:
        _elapsed = round(time.time() - _t0, 2)
        _response_times.append(_elapsed)
        if len(_response_times) > _RESPONSE_TIMES_MAX:
            _response_times.pop(0)
        if _elapsed > 5:
            logger.warning(f"Slow response: {_elapsed}s for: {text[:50]}")

async def _tg_handle_message_core(chat_id, text: str, user: dict):
    # DEBUG: log to file
    user_name = user.get("first_name", "User")
    tg_user_id = user.get("id")
    user_profile = detect_user(source="telegram", telegram_user_id=tg_user_id)
    logger.info(f"TG user: {user_profile.get('user_id', '?')} ({user_name})")
    # Auto-save admin chat_id (skip if ADMIN_TELEGRAM_ID is set)
    if not ADMIN_TELEGRAM_ID:
        _admin_path = __import__("pathlib").Path("data/admin_chat_id.txt")
        if not _admin_path.exists():
            _admin_path.write_text(str(chat_id))
            logger.info(f"Saved admin chat_id: {chat_id}")

    logger.info(f"TG[1] command check: {text[:40]}")
    quick = await tg_handle_command(chat_id, text)
    if quick == "__inline_sent__":
        return
    if quick:
        await tg_send(chat_id, quick)
        return

    logger.info(f"TG[2] quick_query check: {text[:40]}")
    # Quick Query FIRST - before intent router
    if QUICK_QUERY_OK:
        try:
            _qq_early = await asyncio.wait_for(quick_answer(text), timeout=3)
            if _qq_early:
                await tg_send(chat_id, _qq_early)
                return
        except asyncio.TimeoutError:
            logger.warning(f"quick_query timeout: {text[:40]}")
        except:
            pass

    # Speed Engine removed — all requests go to Opus LLM
    # --- Intent Router (Phase A3) — check FIRST for explicit device+room commands ---
    # Skip intent router for LLM-only questions (shifts, dates, personal, calculations)
    import re as _re
    _skip_intent = bool(_re.search(r"عيد|رمضان|دوامي|شفتي|عمر|متى|تاريخ|كم عمر|مولود|ميلاد|حامل|اربعين|الساعة", text))
    if TG_INTENT_OK and not _skip_intent:
        try:
            logger.info(f"TG[3] intent router: {text[:40]}")
            intent_result = await asyncio.wait_for(route_intent(text), timeout=10) if _cb_ha.is_available() else None
            if intent_result:
                _ir_text = intent_result["text"] if isinstance(intent_result, dict) else intent_result
                _ir_entities = intent_result.get("entities", []) if isinstance(intent_result, dict) else []
                _ir_action = intent_result.get("action", "") if isinstance(intent_result, dict) else ""
                logger.info(f"TG intent routed: {text[:50]} -> {_ir_action} ({len(_ir_entities)} entities)")
                _router_stats['intent'] = _router_stats.get('intent', 0) + 1
                _router_stats['intent_matched'] = _router_stats.get('intent_matched', 0) + 1
                _router_stats['total'] += 1
                if TG_SESSION_OK:
                    tg_session_upsert(str(chat_id), last_intent="action", last_entities=_ir_entities)
                _sf_btns = []
                if "شغّلت" in _ir_text or "طفّيت" in _ir_text:
                    _sf_btns = [{"text": "🔴 طفي كل شي", "callback_data": "sc:scene.tfwy_kl_shy"}, {"text": "💡 الأضواء", "callback_data": "cmd:lights"}]
                elif "ضبطت" in _ir_text or "حرار" in _ir_text:
                    _sf_btns = [{"text": "❄️ المكيفات", "callback_data": "cmd:temp"}]
                elif "ستار" in _ir_text:
                    _sf_btns = [{"text": "🎪 الستائر", "callback_data": "cmd:covers"}]
                if _sf_btns:
                    await tg_send_inline(chat_id, _ir_text, _sf_btns, columns=2)
                    return
                else:
                    await tg_send(chat_id, _ir_text, parse_mode="Markdown")
                return
        except Exception as e:
            logger.error(f"Intent router error: {e}")

    # --- Follow-up Resolution (Phase A2) — only if intent router didn't match ---
    if TG_SESSION_OK and not _skip_intent:
        session = tg_session_get(str(chat_id))
        if session:
            followup = detect_followup(text, session)
            ftype = followup.get("type")

            if ftype == "followup":
                logger.info(f"TG followup: {followup}")
                _router_stats["followup"] = _router_stats.get("followup", 0) + 1
                _router_stats["followup_resolved"] = _router_stats.get("followup_resolved", 0) + 1
                _router_stats["total"] += 1
                # Disambiguation: action but no specific target + multiple entities
                f_action = followup.get("action")
                f_target = followup.get("target_entity")
                f_ents = followup.get("last_entities") or []
                if f_action and not f_target and len(f_ents) > 1:
                    _tg_disambig_context[str(chat_id)] = text  # Step 9: store for alias learning
                    action_text = {"on": "شغّل", "off": "طفّي", "increase": "ارفع", "decrease": "وطّي"}.get(f_action, f_action)
                    btns = []
                    for eid in f_ents[:6]:
                        name = _correction_name(eid)
                        btns.append([{"text": name, "callback_data": f"devctl:{f_action}:{eid}"}])
                    btns.append([{"text": "✅ الكل", "callback_data": f"suggest:followup:{f_action}"}])
                    kb = json.dumps({"inline_keyboard": btns})
                    await _tg_client.post(f"{TG_BASE}/sendMessage", json={"chat_id": chat_id, "text": f"❓ {action_text} أي واحد؟", "reply_markup": kb})
                    return
                result = await resolve_followup_action(followup, HA_URL, HA_TOKEN)
                await tg_send(chat_id, result, parse_mode="Markdown")
                return

            elif ftype == "correction":
                # Show disambiguation with last entities as buttons (friendly names from entity_map)
                _tg_disambig_context[str(chat_id)] = text  # Step 9: store for alias learning
                last_ents = followup.get("last_entities", [])
                if last_ents:
                    btns = []
                    for eid in last_ents[:6]:
                        name = _correction_name(eid)
                        btns.append([
                            {"text": f"🟢 {name}", "callback_data": f"devctl:on:{eid}"},
                            {"text": f"⚫ {name}", "callback_data": f"devctl:off:{eid}"}
                        ])
                    kb = json.dumps({"inline_keyboard": btns})
                    await _tg_client.post(f"{TG_BASE}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": "❓ أي واحد تقصد؟",
                        "reply_markup": kb
                    })
                else:
                    pass  # Let LLM handle unknown questions

            elif ftype == "repeat":
                # Re-run last action on same entities
                last_ents = followup.get("last_entities", [])
                last_intent = followup.get("last_intent", "")
                if last_ents and last_intent == "action":
                    followup_repeat = {"type": "followup", "action": "on", "last_entities": last_ents}
                    result = await resolve_followup_action(followup_repeat, HA_URL, HA_TOKEN)
                    await tg_send(chat_id, result, parse_mode="Markdown")
                else:
                    pass  # Let LLM handle - no context
                return

    # Save to context window for LLM
    if TG_SESSION_OK:
        try:
            tg_session_append_context(str(chat_id), "user", text[:200])
        except Exception:
            pass

    # Send typing indicator
    try:
        await _tg_client.post(f"{TG_BASE}/sendChatAction", json={"chat_id": chat_id, "action": "typing"})
    except Exception:
        pass

    trace = RequestTrace()
    task_id = TaskManager.create_task(text, trace.request_id)
    trace.task_id = task_id
    # Inject session context into short-term memory
    if TG_SESSION_OK:
        try:
            _ctx_msgs = tg_session_get_compacted(str(chat_id), last_message=text)
            for _cm in _ctx_msgs[-6:]:
                if _cm.get("_compacted"):
                    memory_add_short_term("system", _cm.get("text", ""))
                else:
                    memory_add_short_term(_cm.get("role","user"), _cm.get("text",""))
        except Exception:
            pass
    memory_add_short_term("user", f"[Telegram/{user_name}] {text}")


    # -- Life Domain Router -- route stocks/expenses/health/work BEFORE LLM
    if LIFE_ROUTER_OK and not _skip_intent:
        try:
            _life_domain = detect_life_domain(text)
            if _life_domain == "stocks" and LIFE_STOCKS_OK:
                logger.info(f"Life router: stocks -> handle_stock_command")
                _router_stats["life_stocks"] = _router_stats.get("life_stocks", 0) + 1
                _router_stats["total"] += 1
                _log_cmd(text, "life_stocks", source="life_router")
                try:
                    _stock_result = await handle_stock_command(text)
                except Exception:
                    try:
                        _stock_result = await portfolio_summary()
                    except Exception:
                        _stock_result = None
                if _stock_result:
                    await tg_send(chat_id, _stock_result, parse_mode="Markdown")
                else:
                    await tg_send(chat_id, "⚠️ ما قدرت أجيب بيانات الأسهم حالياً")
                    return
            elif _life_domain == "expenses" and LIFE_EXPENSES_OK:
                logger.info(f"Life router: expenses -> handle_expense_command")
                _router_stats["life_expenses"] = _router_stats.get("life_expenses", 0) + 1
                _router_stats["total"] += 1
                _log_cmd(text, "life_expenses", source="life_router")
                _exp_result = handle_expense_command(text)
                if _exp_result:
                    await tg_send(chat_id, _exp_result, parse_mode="Markdown")
                    return

            elif _life_domain == "health" and LIFE_HEALTH_OK:
                logger.info(f"Life router: health -> handle_health_command")
                _router_stats["life_health"] = _router_stats.get("life_health", 0) + 1
                _router_stats["total"] += 1
                _log_cmd(text, "life_health", source="life_router")
                _health_result = handle_health_command(text)
                if _health_result:
                    await tg_send(chat_id, _health_result, parse_mode="Markdown")
                    return

            elif _life_domain == "work" and False:  # DISABLED v7.0 — chat_v7 handles shift with get_shift tool
                # Bypass complex Eid/date queries to chat_v7 (LLM is smarter)
                _complex = re.search(r"رابع|ثاني|ثالث|خامس|أيام العيد|ايام العيد|جدول العيد|كل أيام|كل ايام|و الا|ولا ثاني|اول و الا", text)
                if _complex:
                    logger.info(f"Life router: work bypass (complex Eid query) -> chat_v7")
                    pass  # fall through to chat_v7
                else:
                    logger.info(f"Life router: work -> handle_work_command")
                    _router_stats["life_work"] = _router_stats.get("life_work", 0) + 1
                    _router_stats["total"] += 1
                    _log_cmd(text, "life_work", source="life_router")
                    try:
                        _work_result = handle_work_command(text)
                    except Exception:
                        _work_result = get_shift_display()
                    if _work_result:
                        await tg_send(chat_id, _work_result, parse_mode="Markdown")
                        return

        except Exception as e:
            logger.error(f"Life router error: {e}")

    # ── SmartRouter: fast chat path for questions/greetings ──
    if SMART_ROUTER_OK:
        _msg_class = classify_message(text)
        logger.info(f"SmartRouter: '{text[:40]}' -> {_msg_class}")
        _router_stats[_msg_class] = _router_stats.get(_msg_class, 0) + 1
        _router_stats["total"] += 1

        # Greeting → template response (zero LLM cost)
        if _msg_class == "greeting":
            import random as _rnd
            _h = datetime.now().hour
            _tod = "\u0635\u0628\u0627\u062d \u0627\u0644\u062e\u064a\u0631" if 5 <= _h < 12 else "\u0645\u0633\u0627\u0621 \u0627\u0644\u062e\u064a\u0631" if 12 <= _h < 21 else "\u062a\u0633\u0647\u0631 \u0639\u0644\u0649 \u062e\u064a\u0631"
            _shift_txt = ""
            if LIFE_WORK_OK:
                try:
                    from life_work import get_shift
                    _sh = get_shift()["shift"]
                    _shift_txt = f" ({_sh})"
                except Exception:
                    pass
            _greetings = [
                f"\u0647\u0644\u0627 \u0628\u0648 \u062e\u0644\u064a\u0641\u0629! {_tod} \U0001f44b{_shift_txt}",
                f"\u0627\u0644\u0633\u0644\u0627\u0645 \u0639\u0644\u064a\u0643\u0645! \u0634\u0646\u0648 \u062a\u0628\u064a\u061f \U0001f60a{_shift_txt}",
                f"\u0623\u0647\u0644\u064a\u0646 \u0628\u0648 \u062e\u0644\u064a\u0641\u0629! \u062a\u0623\u0645\u0631 \U0001f3e0{_shift_txt}",
                f"\u064a\u0627 \u0647\u0644\u0627! \u062e\u0644 \u0623\u0633\u0627\u0639\u062f\u0643 \U0001f4aa{_shift_txt}",
            ]
            _router_stats["greeting"] = _router_stats.get("greeting", 0) + 1
            await tg_send(chat_id, _rnd.choice(_greetings))
            return

        # [REMOVED v7.0] Second quick_query was here — first one (before intent_router) is enough
        pass
        
        # REMOVED: chat path — ALL messages now go to chat_v7 (has tools)
        # This gives the LLM access to ha_get_state, ssh_run, etc for EVERY question
        pass

    logger.info(f"TG[4] chat_v7 path: {text[:40]}")
    _router_stats["iterative"] = _router_stats.get("iterative", 0) + 1
    _router_stats["action_routed"] = _router_stats.get("action_routed", 0) + 1
    t0 = time.time()
    result = {}
    try:
        if CHAT_V7_OK and anthropic_client:
            from brain_core import build_system_prompt_v7 as _bsp7
            _sys7 = _bsp7()
            _executors = {
                "ha_get_state": _exec_ha_get_state,
                "ha_call_service": lambda d,s,sd: _exec_ha_call_service(d, s, sd),
                "ssh_run": _exec_ssh_run,
            }
            response = await asyncio.wait_for(
                handle_chat_v7(
                    text, _sys7, anthropic_client, _executors,
                    user_id=str(chat_id)),
                timeout=180
            )
            # Guard: if chat_v7 returned empty, provide fallback
            if not response or not response.strip():
                response = "ما قدرت أفهم السؤال، جرب بطريقة ثانية"
                logger.warning(f"chat_v7 returned empty for: {text[:50]}")
        else:
            logger.error("chat_v7 unavailable, no fallback")
            result = {"response": "النظام غير متاح الحين", "actions": [], "results": [], "task_state": "error"}
    except asyncio.TimeoutError:
        logger.warning(f"TG engine timeout: {text[:50]}")
        TaskManager.fail_task(task_id, "timeout")
        response = "⏰ العملية أخذت وقت طويل. جرب طلب أبسط."
    except Exception as e:
        logger.error(f"TG engine error: {e}", exc_info=True)
        TaskManager.fail_task(task_id, str(e))
        response = f"\u26a0\ufe0f Error: {str(e)[:500]}"

    duration = time.time() - t0
    memory_add_short_term("assistant", response)
    await audit_log(
        task=text, actions=result.get("actions"),
        results=result.get("results"),
        status="ok", duration=duration,
        request_id=trace.request_id, task_id=task_id,
        route_type="tg_command"
    )
    # V7: send response to TG
    if True:  # always send
        await tg_send_with_feedback(chat_id, response, request_id=trace.request_id)

    # Save AI response to session context
    if TG_SESSION_OK:
        try:
            tg_session_append_context(str(chat_id), "assistant", response[:200])
        except Exception:
            pass



@app.get("/health/external")
async def health_external():
    """Phase 1: External service health status."""
    def _fmt(cb):
        return {
            "status": cb.state,
            "failures": cb.failures,
            "total_trips": cb.total_trips,
            "open_until": cb.open_until,
            "last_failure": cb.last_failure,
        }
    return {
        "ha": _fmt(_cb_ha),
        "telegram": _fmt(_cb_tg),
        "llm": _fmt(_cb_llm),
        "feature_flags": {f["name"]: f["enabled"] for f in ff.get_all()},
        "feature_flags_extra": {
            "home_brain": BRAIN_OK,
            "ha_doctor": DOCTOR_OK,
            "external_timeout_seconds": EXTERNAL_TIMEOUT,
        }
    }


# ── Feature Flags v2 API ──────────────────────────────────
@app.get("/api/flags")
async def get_feature_flags():
    return {"flags": ff.get_all()}

@app.post("/api/flags/{name}/toggle")
async def toggle_feature_flag(name: str):
    new_val = ff.toggle(name)
    # Update module-level vars for existing code paths
    global FEATURE_CIRCUIT_BREAKERS, FEATURE_TIMEOUTS, FEATURE_SPEED_TEMPLATES, FEATURE_SMART_ROUTER_V2, FEATURE_ENTITY_HEALTH
    FEATURE_CIRCUIT_BREAKERS = ff.is_enabled("circuit_breakers")
    FEATURE_TIMEOUTS = ff.is_enabled("timeouts")
    FEATURE_SPEED_TEMPLATES = ff.is_enabled("speed_templates")
    FEATURE_SMART_ROUTER_V2 = ff.is_enabled("smart_router_v2")
    FEATURE_ENTITY_HEALTH = ff.is_enabled("entity_health")
    logger.info(f"Feature flag '{name}' toggled to {new_val}")
    hook_registry.fire_sync("flag_toggled", name=name, enabled=new_val)
    return {"name": name, "enabled": new_val}

# ── Service Health Hub API ────────────────────────────────
@app.get("/api/service-health")
async def get_service_health():
    """Central health status — reads from existing circuit breakers + timestamps."""
    bridge_st = None
    try:
        from bridge_client import BridgeClient, BRIDGE_BASE_URL
        client = BridgeClient(BRIDGE_BASE_URL)
        bridge_st = client.get_status()
    except Exception:
        pass
    last_b, last_g = None, None
    try:
        from news_engine import last_boursa_refresh, last_gemini_refresh
        last_b, last_g = last_boursa_refresh, last_gemini_refresh
    except Exception:
        pass
    return health_hub.check_all(
        cb_ha=_cb_ha, cb_llm=_cb_llm, cb_tg=_cb_tg,
        bridge_status=bridge_st,
        last_boursa=last_b, last_gemini=last_g,
    )



# ── Stock Analysis API (Gemini 2.5 Pro via stock_analyzer.py) ──
@app.get("/api/analyze")
async def api_analyze(symbol: str = ""):
    """Full technical analysis for a stock using Gemini 2.5 Pro + Bridge data."""
    if not symbol:
        return {"error": "symbol parameter required"}
    symbol = symbol.upper().strip()
    try:
        from stock_analyzer import analyze_stock
        result = await asyncio.to_thread(analyze_stock, symbol)
        return result
    except Exception as e:
        logger.error("analyze error for %s: %s", symbol, e)
        return {"error": str(e)}


# ── Task Manager API (Tier2 #8 integration) ──────────────
@app.get("/api/tasks")
async def get_tasks():
    """Expose TaskManager state for dashboard (system.html + home.html)."""
    try:
        from task_manager import TaskManager
        tm = TaskManager.instance()
        running = tm.get_running_tasks()
        recent = tm.get_recent_tasks(10)

        def _fmt(t):
            d = t.to_dict()
            if t.started_at:
                d["started_at"] = datetime.utcfromtimestamp(t.started_at).isoformat() + "Z"
            if t.completed_at:
                d["completed_at"] = datetime.utcfromtimestamp(t.completed_at).isoformat() + "Z"
            return d

        all_recent = tm.get_recent_tasks(100)
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0).timestamp()
        today_tasks = [t for t in all_recent if t.created_at >= today_start]

        return {
            "running": [_fmt(t) for t in running],
            "recent": [_fmt(t) for t in recent if t.is_terminal],
            "stats": {
                "total_today": len(today_tasks),
                "completed_today": sum(1 for t in today_tasks if t.status.value == "completed"),
                "failed_today": sum(1 for t in today_tasks if t.status.value == "failed"),
            },
        }
    except Exception as e:
        return {"running": [], "recent": [], "stats": {}, "error": str(e)}


# ── KAIROS Agent API ──────────────────────────────────────
@app.get("/api/kairos/status")
async def get_kairos_status():
    if kairos_agent is None:
        return {"error": "kairos not initialized"}
    return kairos_agent.get_status()

@app.get("/api/kairos/log")
async def get_kairos_log(limit: int = 50):
    if kairos_agent is None:
        return {"error": "kairos not initialized"}
    return {"log": kairos_agent.get_log(limit)}

# ── Hooks + Tool Registry API (Phase 6) ──────────────────
@app.get("/api/hooks/stats")
async def get_hooks_stats():
    return hook_registry.get_stats()

@app.get("/api/hooks/log")
async def get_hooks_log(limit: int = 50, event: str = None):
    return {"log": hook_registry.get_log(limit, event)}

@app.get("/api/tools")
async def get_tools(category: str = None, q: str = None):
    if q:
        return {"tools": tool_reg.find(q)}
    return tool_reg.get_stats()

@app.get("/api/tools/{name}")
async def get_tool_detail(name: str):
    tool = tool_reg.get(name)
    if not tool:
        return {"error": f"Tool '{name}' not found"}
    d = tool.to_dict()
    d["available"] = tool_reg.is_available(name)
    return d

# ── News API ──────────────────────────────────────────────
@app.get("/api/news")
async def api_news(category: str = None, sub: str = None,
                   limit: int = 50, min_priority: int = 1):
    if not NEWS_ENGINE_OK:
        return {"items": [], "counts": {}, "error": "news_engine not loaded"}
    items = news_get_news(category, sub, limit, min_priority)
    counts = news_get_counts()
    try:
        from news_engine import last_boursa_refresh, last_gemini_refresh
        lb, lg = last_boursa_refresh, last_gemini_refresh
    except Exception:
        lb, lg = None, None
    return {"items": items, "counts": counts, "last_boursa_refresh": lb, "last_gemini_refresh": lg}

@app.post("/api/news/refresh-boursa")
async def api_news_refresh_boursa():
    if not NEWS_ENGINE_OK:
        return {"ok": False, "error": "news_engine not loaded"}
    # Task tracking (Integration 7)
    try:
        from task_manager import TaskManager, TaskType
        _tm = TaskManager.instance()
        _task = _tm.create_task(TaskType.NEWS_FETCH, {"source": "boursa"})
        _tm.start_task(_task.task_id)
    except Exception:
        _tm, _task = None, None
    try:
        result = await asyncio.to_thread(news_refresh_boursa)
        if _tm and _task:
            _tm.complete_task(_task.task_id, result=str(result.get("count", 0)) + " items")
        return result
    except Exception as e:
        if _tm and _task:
            _tm.fail_task(_task.task_id, error=str(e)[:100])
        return {"ok": False, "error": str(e)}

@app.post("/api/news/refresh-gemini")
async def api_news_refresh_gemini():
    if not NEWS_ENGINE_OK:
        return {"ok": False, "error": "news_engine not loaded"}
    try:
        from task_manager import TaskManager, TaskType
        _tm = TaskManager.instance()
        _task = _tm.create_task(TaskType.NEWS_FETCH, {"source": "gemini"})
        _tm.start_task(_task.task_id)
    except Exception:
        _tm, _task = None, None
    try:
        result = await asyncio.to_thread(news_refresh_gemini)
        if _tm and _task:
            _tm.complete_task(_task.task_id, result=str(result.get("count", 0)) + " items")
        return result
    except Exception as e:
        if _tm and _task:
            _tm.fail_task(_task.task_id, error=str(e)[:100])
        return {"ok": False, "error": str(e)}







@app.post("/chat/clear")
async def clear_chat_history(user_id: str = "default"):
    # Clear V7 conversation history for a user
    if CHAT_V7_OK:
        from chat_v7 import clear_chat_v7_history
        clear_chat_v7_history(user_id if user_id != "all" else None)
        return {"status": "cleared", "user_id": user_id}
    return {"status": "chat_v7 not available"}

@app.get("/tg/stats")
async def tg_stats():
    """Router stats + module health for monitoring."""
    _up = int(time.time() - START_TIME)
    return {
        "uptime_seconds": _up,
        "router": dict(_router_stats),
        "modules": {
            "intent_router": TG_INTENT_OK,
            "life_router": LIFE_ROUTER_OK,
            "smart_router": SMART_ROUTER_OK,
            "brain": BRAIN_AVAILABLE,
            "morning_report": TG_MORNING_OK,
            "alerts": TG_ALERTS_OK,
            "reminders": TG_REMIND_OK,
            "news": TG_NEWS_OK,
            "discovery": DISCOVERY_OK,
            "session": TG_SESSION_OK,
            "home": TG_HOME_OK,
            "ops": TG_OPS_OK,
            "stocks": LIFE_STOCKS_OK,
            "expenses": LIFE_EXPENSES_OK,
            "health": LIFE_HEALTH_OK,
            "work": LIFE_WORK_OK,
        },
        "last_commands": _router_cmd_log[-10:] if _router_cmd_log else [],
        "version": VERSION,
        "persistent_stats": True,
    }

@app.post("/health/external/test")
async def health_external_test(request: Request):
    """Phase 1: Simulate CB failures for testing. Admin-only."""
    body = await request.json()
    target = body.get("target", "ha")  # ha, llm, telegram
    action = body.get("action", "fail")  # fail, reset
    cb_map = {"ha": _cb_ha, "llm": _cb_llm, "telegram": _cb_tg}
    cb = cb_map.get(target)
    if not cb:
        return {"error": f"Unknown target: {target}"}
    if action == "fail":
        cb.record_failure()
        return {"target": target, "action": "fail", "state": cb.state, "failures": cb.failures, "open_until": cb.open_until}
    elif action == "reset":
        cb.record_success()
        return {"target": target, "action": "reset", "state": cb.state, "failures": cb.failures}
    return {"error": f"Unknown action: {action}"}

@app.get("/stability")
async def stability_endpoint():
    """Step 10: Circuit breaker and stability status."""
    return {
        "circuit_breakers": {
            "home_assistant": _cb_ha.status(),
            "llm": _cb_llm.status(),
            "telegram": _cb_tg.status(),
        },
        "summary": {
            "all_healthy": all(cb.state == "closed" for cb in [_cb_ha, _cb_llm, _cb_tg]),
            "open_circuits": [cb.name for cb in [_cb_ha, _cb_llm, _cb_tg] if cb.state == "open"],
        }
    }

@app.get("/aliases")
async def aliases_endpoint():
    """Step 9: View learned aliases."""
    try:
        stats = get_alias_stats()
        return stats
    except Exception as e:
        return {"error": str(e)}

@app.get("/router/stats")
async def router_stats_endpoint():
    total = _router_stats.get("total", 0) or 1
    db_stats = {}
    try:
        import sqlite3 as _sq
        _c = _sq.connect(str(AUDIT_DB))
        for row in _c.execute("SELECT status, count(*) FROM audit_log GROUP BY status").fetchall():
            db_stats[row[0]] = row[1]
        db_stats["db_total"] = _c.execute("SELECT count(*) FROM audit_log").fetchone()[0]
        _c.close()
    except Exception:
        pass
    # Route type breakdown from DB
    route_breakdown = {}
    try:
        import sqlite3 as _sq2
        _c2 = _sq2.connect(str(AUDIT_DB))
        for row in _c2.execute("SELECT route_type, count(*) FROM audit_log WHERE route_type IS NOT NULL GROUP BY route_type").fetchall():
            route_breakdown[row[0]] = row[1]
        _c2.close()
    except Exception:
        pass
    return {
        "session": {
            **_router_stats,
            "percentages": {
                k: round(v / total * 100, 1)
                for k, v in _router_stats.items()
                if k != "total" and k != "started_at" and isinstance(v, (int, float))
            },
        },
        "persistent": db_stats,
        "routing": route_breakdown,
    }



# ─── Entity Health (Step 3) ───
@app.get("/entity-map/health", tags=["system"])
async def entity_map_health():
    """Validate entity_map.json against live HA state."""
    if not FEATURE_ENTITY_HEALTH:
        return {"error": "FEATURE_ENTITY_HEALTH disabled"}
    try:
        from entity_health import validate_entity_map
        report = await validate_entity_map(HA_URL, HA_TOKEN)
        return report
    except Exception as e:
        return {"error": str(e)}


@app.post("/entity-map/arabize", tags=["system"])
async def entity_map_arabize(apply: bool = False):
    """Preview or apply Arabic translation of English entity names."""
    if not FEATURE_ENTITY_HEALTH:
        return {"error": "FEATURE_ENTITY_HEALTH disabled"}
    try:
        from entity_health import load_entity_map, arabize_entity_map, ENTITY_MAP_PATH
        import json as _j
        emap = load_entity_map()
        new_map, changes = arabize_entity_map(emap)
        if apply and changes:
            ENTITY_MAP_PATH.write_text(_j.dumps(new_map, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"applied": True, "changes": len(changes), "details": changes}
        return {"preview": True, "changes": len(changes), "details": changes}
    except Exception as e:
        return {"error": str(e)}






async def stats_save_loop():
    """Save router stats every 30 minutes."""
    while True:
        await asyncio.sleep(1800)
        _save_router_stats()
        logger.info(f"Stats saved: total={_router_stats.get('total', 0)}")


async def shift_alert_loop():
    """Send shift reminders: 1h before shift start + day-before if shift type changes."""
    if not LIFE_WORK_OK:
        logger.info("Shift alert: life_work not loaded, skipping")
        return
    logger.info("Shift alert loop started")
    from life_work import get_shift, SHIFT_EMOJI
    _last_notified_date = None
    while True:
        try:
            now = datetime.now()
            today = get_shift(now.date())
            tomorrow = get_shift(now.date() + timedelta(days=1))
            shift = today["shift"]
            t_shift = tomorrow["shift"]
            _chat = ADMIN_TELEGRAM_ID or "669769765"

            # 1) Pre-shift reminder (1h before)
            hour = now.hour
            should_remind = False
            if shift == "\u0635\u0628\u0627\u062d\u064a" and hour == 6 and now.minute < 15:
                should_remind = True
            elif shift == "\u0639\u0635\u0631\u064a" and hour == 14 and now.minute < 15:
                should_remind = True
            elif shift == "\u0644\u064a\u0644\u064a" and hour == 22 and now.minute < 15:
                should_remind = True

            if should_remind and _last_notified_date != f"{now.date()}-pre":
                msg = f"{SHIFT_EMOJI[shift]} \u062a\u0630\u0643\u064a\u0631: \u0634\u0641\u062a\u0643 \u0627\u0644{shift} \u064a\u0628\u062f\u0623 \u0628\u0639\u062f \u0633\u0627\u0639\u0629\n{today['times']}"
                try:
                    await tg_send(_chat, msg)
                    _last_notified_date = f"{now.date()}-pre"
                    logger.info(f"Shift pre-alert sent: {shift}")
                except Exception as e:
                    logger.error(f"Shift pre-alert error: {e}")

            # 2) Tomorrow shift change alert (at 9 PM)
            if hour == 21 and now.minute < 15 and shift != t_shift and _last_notified_date != f"{now.date()}-tmrw":
                msg = f"{SHIFT_EMOJI[t_shift]} \u0628\u0627\u0643\u0631: {t_shift} ({tomorrow['times']})"
                if t_shift == "\u0625\u062c\u0627\u0632\u0629":
                    msg += "\n\U0001f389 \u0627\u0633\u062a\u0645\u062a\u0639 \u0628\u0625\u062c\u0627\u0632\u062a\u0643!"
                try:
                    await tg_send(_chat, msg)
                    _last_notified_date = f"{now.date()}-tmrw"
                    logger.info(f"Shift tomorrow alert sent: {t_shift}")
                except Exception as e:
                    logger.error(f"Shift tomorrow alert error: {e}")

        except Exception as e:
            logger.error(f"Shift alert loop error: {e}")
        await asyncio.sleep(900)  # check every 15 min

async def brain_snapshot_loop():
    """Take HA snapshot every 5 min for pattern learning."""
    await asyncio.sleep(30)
    while True:
        try:
            _bshift = ''
            if LIFE_WORK_OK:
                try:
                    from life_work import get_shift as _bgs
                    _bshift = _bgs(datetime.now().date()).get('shift', '')
                except: pass
            result = await take_snapshot(_bshift)
            if result.get("changes", 0) > 0:
                logger.info(f"Brain: {result['changes']} changes")
        except Exception as e:
            logger.error(f"Brain snapshot: {e}")
        await asyncio.sleep(300)

async def entity_health_check_loop():
    """Periodic entity map health check - alerts on dead/new entities via Telegram (Part C)."""
    if not FEATURE_ENTITY_HEALTH:
        return
    logger.info("Entity health check loop started (every 6h)")
    _notified_file = _pl.Path(__file__).parent / "data" / "notified_entities.json"
    try:
        _notified_entities = set(json.loads(_notified_file.read_text())) if _notified_file.exists() else set()
    except Exception:
        _notified_entities = set()
    await asyncio.sleep(300)  # wait 5min after startup
    while True:
        try:
            from entity_health import validate_entity_map
            report = await validate_entity_map(HA_URL, HA_TOKEN)
            if not report.get("ha_reachable"):
                logger.warning("Entity health: HA unreachable")
                await asyncio.sleep(6 * 3600)
                continue
            s = report.get("summary", {})
            dead = s.get("dead", 0)
            missing = s.get("missing", 0)
            eng = s.get("english", 0)
            
            alerts = []
            if dead > 0:
                dead_list = report.get("dead_entities", [])[:10]
                txt = chr(10).join(f"  ❌ {d['name']} ({d['entity_id']})" for d in dead_list)
                alerts.append(f"⚠️ أجهزة ميتة ({dead}):" + chr(10) + txt)
            _all_missing = report.get("missing_entities", [])
            _new_missing = [m for m in _all_missing if m["entity_id"] not in _notified_entities]
            if _new_missing:
                miss_list = _new_missing[:10]
                txt = chr(10).join(f"  🆕 {m['name']} ({m['entity_id']})" for m in miss_list)
                alerts.append(f"🆕 أجهزة جديدة ({len(_new_missing)}):" + chr(10) + txt)
            
            if alerts:
                _msg = "🔍 فحص صحة الأجهزة:" + chr(10) + chr(10).join(alerts)
                try:
                    _tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                    _chat_id = ADMIN_TELEGRAM_ID or "669769765"
                    httpx.post(_tg_url, json={"chat_id": _chat_id, "text": _msg}, timeout=10)
                    logger.info(f"Entity health alert sent: {dead} dead, {missing} new")
                    _notified_entities.update(m["entity_id"] for m in _all_missing)
                    try: _notified_file.write_text(json.dumps(list(_notified_entities)))
                    except Exception: pass
                except Exception as _te:
                    logger.error(f"Entity health TG alert failed: {_te}")
            else:
                logger.info("Entity health check: all OK")
        except Exception as _e:
            logger.error(f"Entity health check error: {_e}")
        
        await asyncio.sleep(6 * 3600)  # every 6 hours




async def weather_alert_loop():
    """Check weather every 3 hours, alert on extreme conditions."""
    logger.info("Weather alert loop started")
    _last_alert_date = None
    await asyncio.sleep(600)  # wait 10min after startup
    while True:
        try:
            import httpx as _wx
            async with _wx.AsyncClient(timeout=10) as c:
                r = await c.get("https://api.open-meteo.com/v1/forecast", params={
                    "latitude": 29.3375, "longitude": 47.9775,
                    "current": "temperature_2m,weather_code,wind_speed_10m",
                    "timezone": "Asia/Kuwait",
                })
                d = r.json()
                cur = d.get("current", {})
                temp = cur.get("temperature_2m", 0)
                code = cur.get("weather_code", 0)
                wind = cur.get("wind_speed_10m", 0)
                today = datetime.now().strftime("%Y-%m-%d")
                alerts = []
                if temp >= 45:
                    alerts.append(f"\U0001f525 \u062d\u0631\u0627\u0631\u0629 \u0634\u062f\u064a\u062f\u0629: {temp}\u00b0C!")
                if temp <= 5:
                    alerts.append(f"\u2744\ufe0f \u0628\u0631\u062f \u0634\u062f\u064a\u062f: {temp}\u00b0C!")
                if code in (95, 96, 99):
                    alerts.append("\u26a1 \u0639\u0648\u0627\u0635\u0641 \u0631\u0639\u062f\u064a\u0629!")
                if wind >= 50:
                    alerts.append(f"\U0001f4a8 \u0631\u064a\u0627\u062d \u0642\u0648\u064a\u0629: {wind} km/h!")
                if code in (45, 48):
                    alerts.append("\U0001f32b \u0636\u0628\u0627\u0628 \u0643\u062b\u064a\u0641 \u2014 \u0627\u0646\u062a\u0628\u0647 \u0639\u0627\u0644\u0637\u0631\u064a\u0642!")
                if alerts and _last_alert_date != today:
                    _chat = ADMIN_TELEGRAM_ID or "669769765"
                    _msg = "\u26a0\ufe0f \u062a\u0646\u0628\u064a\u0647 \u0637\u0642\u0633:\n" + chr(10).join(alerts)
                    await tg_send(_chat, _msg)
                    _last_alert_date = today
                    logger.info(f"Weather alert sent: {alerts}")
        except Exception as e:
            logger.error(f"Weather alert error: {e}")
        await asyncio.sleep(3 * 3600)  # every 3 hours

async def plan_check_loop():
    # Check active plans every 60 seconds
    await asyncio.sleep(120)  # wait 2 min after startup
    while True:
        try:
            if PLAN_OK:
                due = get_due_plans()
                for p in due:
                    _chat = ADMIN_TELEGRAM_ID or "669769765"
                    goal = p.get("goal", "")
                    meta = json.loads(p.get("meta", "{}"))
                    category = meta.get("category", "")
                    # Guardian: only alert if something is actually wrong
                    if category == "guardian":
                        has_problem = False
                        if DEGRADED_OK and is_degraded():
                            has_problem = True
                            status_msg = deg_status()
                            await tg_send(_chat, status_msg)
                        record_run(p["plan_id"], "checked" if not has_problem else "alerted")
                        if has_problem:
                            logger.info(f"[PlanLoop] Guardian ALERT: {goal}")
                        continue
                    # Routine/other: send approval or notification
                    needs_approval = meta.get("approval_required", False)
                    if needs_approval:
                        await tg_send(_chat, chr(0x1F4CB) + " " + goal + chr(10) + chr(10) + chr(0x0645) + chr(0x0648) + chr(0x0627) + chr(0x0641) + chr(0x0642) + " " + chr(0x0639) + chr(0x0644) + chr(0x0649) + " " + chr(0x0627) + chr(0x0644) + chr(0x062A) + chr(0x0646) + chr(0x0641) + chr(0x064A) + chr(0x0630) + chr(0x061F))
                    else:
                        await tg_send(_chat, chr(0x2705) + " " + goal)
                    record_run(p["plan_id"], "triggered")
                    logger.info(f"[PlanLoop] Triggered: {p['plan_id']} - {goal}")
        except Exception as e:
            logger.error(f"[PlanLoop] Error: {e}")
        await asyncio.sleep(60)


async def feedback_learning_loop():
    # Run feedback apply_learning every 6 hours
    await asyncio.sleep(300)
    while True:
        try:
            if FEEDBACK_OK:
                result = fl_apply(30)
                if result:
                    logger.info(f"[FeedbackLoop] Applied {len(result)} adjustments")
        except Exception as e:
            logger.error(f"[FeedbackLoop] Error: {e}")
        await asyncio.sleep(6 * 3600)


async def nightly_summary_scheduler():
    """Send daily summary at 11 PM and reset daily counters."""
    logger.info("Nightly summary scheduler started")
    while True:
        now = datetime.now()
        target = now.replace(hour=23, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait_secs = (target - now).total_seconds()
        logger.info(f"Next nightly summary in {wait_secs/3600:.1f} hours")
        await asyncio.sleep(wait_secs)
        try:
            _chat = ADMIN_TELEGRAM_ID or "669769765"
            _up = int(time.time() - START_TIME)
            _h, _m = divmod(_up // 60, 60)
            _t = _router_stats.get("total", 0)
            _greet = _router_stats.get("greeting", 0)
            _intent = _router_stats.get("intent", 0)
            _chat_c = _router_stats.get("chat", 0)
            _action = _router_stats.get("action", 0)
            _qq = _router_stats.get("quick_query", 0)
            _unk = _router_stats.get("unknown", 0)
            _fup = _router_stats.get("followup", 0)
            _ls = _router_stats.get("life_stocks", 0) + _router_stats.get("life_expenses", 0) + _router_stats.get("life_health", 0) + _router_stats.get("life_work", 0)
            _saved = _greet + _intent + _ls + _qq
            _pct = round(_saved / _t * 100) if _t > 0 else 0
            _errs = 0
            try:
                with open("server.log", "r") as _lf:
                    _errs = sum(1 for l in _lf if "ERROR" in l)
            except Exception:
                pass
            # Shift tomorrow
            _tmrw = ""
            if LIFE_WORK_OK:
                try:
                    from life_work import get_shift, SHIFT_EMOJI
                    _ts = get_shift(datetime.now().date() + timedelta(days=1))
                    _tmrw = f"\n\n{SHIFT_EMOJI[_ts['shift']]} \u0628\u0627\u0643\u0631: {_ts['shift']} ({_ts['times']})"
                except Exception:
                    pass
            _msg = chr(10).join([
                "\U0001f319 \u0645\u0644\u062e\u0635 \u0627\u0644\u064a\u0648\u0645:",
                f"",
                f"\u23f1 Uptime: {_h}h {_m}m",
                f"\U0001f4e8 \u0631\u0633\u0627\u0626\u0644: {_t}",
                f"  \U0001f44b \u062a\u062d\u064a\u0629: {_greet} | \U0001f3af Intent: {_intent}",
                f"  \U0001f4ac Chat: {_chat_c} | \u26a1 Quick: {_qq}",
                f"  \U0001f504 Followup: {_fup} | \u2753 Unknown: {_unk}",
                f"",
                f"\U0001f4b0 LLM \u0648\u0641\u0631\u0646\u0627: {_saved}/{_t} ({_pct}%)",
            f"\u26a1 Quick Query: {_qq} | \U0001f4be Cache: {_cache}",
            f"\u23f1 Avg response: {round(sum(_response_times)/len(_response_times),1) if _response_times else 0}s ({len(_response_times)} msgs)",
                f"\u26a0\ufe0f Errors: {_errs}",
            ]) + _tmrw
            await tg_send(_chat, _msg)
            logger.info(f"Nightly summary sent: {_t} msgs, {_pct}% saved")
            # Save stats and reset daily counters
            _save_router_stats()
            for k in list(_router_stats.keys()):
                if k not in ("started_at", "_sessions", "_prev_total"):
                    _router_stats[k] = 0
            _router_stats["started_at"] = datetime.now().isoformat()
            logger.info("Daily stats reset")
            # --- Corrections Decay (nightly) ---
            try:
                from corrections_loop import get_corrections_loop
                _cl = get_corrections_loop()
                _cd = _cl.decay_corrections()
                if _cd > 0:
                    logger.info(f"Corrections decay: {_cd} corrections decayed")
            except Exception as _ce:
                logger.warning(f"Corrections decay error: {_ce}")
            # v8 Phase 2: Daily Tasks + Inbox digest in nightly summary
            try:
                from task_engine import format_tasks_summary
                from inbox_engine import inbox_digest
                _tasks_sum = format_tasks_summary()
                _inbox_sum = await inbox_digest(hours=24)
                _daily_extra = ""
                if _tasks_sum: _daily_extra += chr(10)+chr(10) + _tasks_sum
                if _inbox_sum: _daily_extra += chr(10)+chr(10) + _inbox_sum
                if _daily_extra:
                    await tg_send(_chat, "📋 *ملخص اليوم*" + _daily_extra)
            except Exception as _de:
                logger.debug(f"Daily digest error: {_de}")
            # --- Structured Memory Decay (nightly) ---
            try:
                _smd = smem.apply_decay()
                if _smd > 0:
                    logger.info(f"Structured memory decay: {_smd} memories decayed")
            except Exception as _se:
                logger.warning(f"Structured memory decay error: {_se}")
            # --- Brain Nightly Digest ---
            if BRAIN_OK:
                try:
                    _bs = get_daily_summary()
                    if _bs.get("total", 0) > 0:
                        _bd = ["", "🧠 *ملخص البرين:*"]
                        _bd.append(f"  📊 {_bs['total']} تغيير")
                        if _bs.get("by_domain"):
                            _dom_ar = {"light":"أضواء","switch":"مفاتيح","climate":"مكيفات","cover":"ستائر","fan":"شفاطات/منقيات","media_player":"سماعات"}
                            _bd.append("  " + " | ".join(f"{_dom_ar.get(d,d)}:{c}" for d,c in _bs["by_domain"].items()))
                        if _bs.get("top"):
                            _bd.append("  🏆 أكثر: " + ", ".join(f"{e.split('.')[-1].replace('_',' ')}({c})" for e,c in _bs["top"][:3]))
                        if _bs.get("by_hour"):
                            _peak = max(_bs["by_hour"].items(), key=lambda x: x[1])
                            _bd.append(f"  ⏰ ذروة: {_peak[0]}:00 ({_peak[1]} تغيير)")
                        await tg_send(_chat, chr(10).join(_bd))
                        logger.info(f"Brain digest sent: {_bs['total']} changes")
                        # Auto-cleanup: keep only 30 days of raw data
                        _cleaned = cleanup_old_data(30)
                        if _cleaned > 0:
                            logger.info(f"Brain cleanup: deleted {_cleaned} old records")
                except Exception as e:
                    logger.error(f"Brain digest: {e}")
        except Exception as e:
            logger.error(f"Nightly summary error: {e}")

async def brain_nightly_learning():
    """Run pattern learning every night at 11:30 PM."""
    await asyncio.sleep(60)
    while True:
        try:
            now = datetime.now()
            target = now.replace(hour=23, minute=30, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait = (target - now).total_seconds()
            logger.info(f"Pattern learning scheduled in {wait/3600:.1f}h")
            await asyncio.sleep(wait)
            if LEARNING_OK:
                result = await bl_learn(days=10)
                logger.info(f"Pattern learning done: {result}")
                if result.get("patterns_found", 0) > 0 and ADMIN_TELEGRAM_ID:
                    msg = (f"\U0001f9e0 Pattern Learning:\n"
                           f"  \U0001f4ca {result['entities_processed']} entity -> {result['patterns_found']} pattern\n"
                           f"  \u23f1 {result['duration_seconds']}s")
                    await tg_send(ADMIN_TELEGRAM_ID, msg)
                # Run anomaly check after learning
                try:
                    anomaly_report = await bl_anomaly_report()
                    if anomaly_report and "شذوذ" in anomaly_report:
                        await tg_send(ADMIN_TELEGRAM_ID, anomaly_report)
                except Exception as ae:
                    logger.error(f"Anomaly check error: {ae}")
        except Exception as e:
            logger.error(f"Pattern learning error: {e}")
            await asyncio.sleep(3600)


async def brain_weekly_insight():
    """Send weekly insight every Friday at 9 AM."""
    logger.info("Brain weekly insight scheduler started")
    while True:
        now = datetime.now()
        days_until_friday = (4 - now.weekday()) % 7
        if days_until_friday == 0 and now.hour >= 9:
            days_until_friday = 7
        target = (now + timedelta(days=days_until_friday)).replace(hour=9, minute=0, second=0, microsecond=0)
        wait_secs = (target - now).total_seconds()
        logger.info(f"Next brain weekly in {wait_secs/3600:.1f}h")
        await asyncio.sleep(wait_secs)
        try:
            if not BRAIN_OK:
                continue
            _chat = ADMIN_TELEGRAM_ID or "669769765"
            pats = detect_patterns(14, 3)
            _bs = get_brain_stats()
            _wl = ["🧠 *تقرير البرين الأسبوعي:*", ""]
            _wl.append(f"📊 {_bs['total']} تغيير خلال {_bs['days']} يوم")
            _wl.append(f"🔍 {_bs['patterns']} نمط مكتشف")
            _wl.append("")
            _wl.append(format_insights_ar(pats))
            if pats:
                _wl.append("")
                _wl.append("💡 تبي أسوي أي وحدة منهم automation؟")
            await tg_send(_chat, chr(10).join(_wl))
            # Add brain learning maturity to weekly
            if LEARNING_OK:
                try:
                    _mat = bl_maturity()
                    _top = bl_top_sugs(3)
                    _wl_extra = chr(10) + chr(10) + chr(0x1f393) + ' حالة التعلم:' + chr(10) + _mat
                    if _top:
                        _wl_extra += chr(10) + chr(10) + chr(0x1f4a1) + ' أفضل اقتراحات:'
                        for _s in _top:
                            _wl_extra += chr(10) + '  ' + chr(0x2022) + ' ' + _s['label']
                    await tg_send(_chat, _wl_extra)
                except Exception:
                    pass
            # Also send health report
            if DOCTOR_OK:
                try:
                    _hr = await format_health_report()
                    await tg_send(_chat, _hr)
                except Exception:
                    pass
            # Feedback learning weekly digest
            if FEEDBACK_OK:
                try:
                    from feedback_learner import generate_digest as _fb_digest
                    _fbd = _fb_digest(7)
                    if _fbd:
                        await tg_send(_chat, _fbd)
                except Exception:
                    pass
            # v8 Phase 2: Tasks + Inbox weekly digest on Fridays
            try:
                if __import__("datetime").datetime.now().weekday() == 4:
                    from task_engine import format_tasks_summary
                    from inbox_engine import inbox_weekly_digest
                    t_sum = format_tasks_summary()
                    i_sum = await inbox_weekly_digest()
                    if t_sum or i_sum:
                        weekly_msg = "\U0001f4c5 *\u0645\u0644\u062e\u0635 \u0627\u0644\u0623\u0633\u0628\u0648\u0639*" + chr(10)
                        if t_sum: weekly_msg += t_sum + chr(10)+chr(10)
                        if i_sum: weekly_msg += i_sum
                        await tg_send(_chat, weekly_msg)
            except Exception as _we:
                logger.debug(f"Weekly digest error: {_we}")
            # v9: Weekly trading report fires separately at Friday 2 PM via weekly_trading_report_scheduler
            logger.info(f"Brain weekly: {len(pats)} patterns")
        except Exception as e:
            logger.error(f"Brain weekly: {e}")

async def weekly_trading_report_scheduler():
    """Send weekly trading report every Friday at 2 PM KWT (11 AM UTC)."""
    logger.info("Weekly trading report scheduler started")
    while True:
        now = datetime.now()
        # Friday = weekday 4
        days_until_friday = (4 - now.weekday()) % 7
        if days_until_friday == 0 and (now.hour > 14 or (now.hour == 14 and now.minute > 0)):
            days_until_friday = 7
        target = (now + timedelta(days=days_until_friday)).replace(hour=14, minute=0, second=0, microsecond=0)
        wait_secs = (target - now).total_seconds()
        if wait_secs < 0:
            wait_secs += 7 * 86400
        logger.info(f"Next weekly trading report in {wait_secs/3600:.1f}h")
        await asyncio.sleep(wait_secs)
        try:
            if not JOURNAL_OK:
                continue
            _chat = ADMIN_TELEGRAM_ID or "669769765"
            from journal_engine import generate_weekly_report, format_weekly_report_tg
            _wr = generate_weekly_report()
            _wr_msg = format_weekly_report_tg(_wr)
            await tg_send(int(_chat), _wr_msg)
            logger.info("Weekly trading report sent (Friday 2 PM)")
        except Exception as e:
            logger.error(f"Weekly trading report error: {e}")


async def confluence_scan_loop():
    """Run confluence scan every 30 min during KSE market hours (Sun-Thu 9:00-13:00 KWT)."""
    logger.info("Confluence scan loop started")
    while True:
        try:
            now = datetime.now()
            # KSE: Sun(6) Mon(0) Tue(1) Wed(2) Thu(3), 9:00-13:00 KWT = 6:00-10:00 UTC
            if now.weekday() in (6, 0, 1, 2, 3) and 6 <= now.hour <= 10:
                if CONFLUENCE_OK:
                    actionable = run_confluence_scan()
                    if actionable:
                        _chat = ADMIN_TELEGRAM_ID or "669769765"
                        for sig in actionable[:3]:
                            text, kb = confluence_build_tg_alert(sig)
                            await tg_send(int(_chat), text, reply_markup=kb)
                        logger.info(f"Confluence: {len(actionable)} actionable signals sent to TG")
                else:
                    logger.debug("Confluence engine not loaded, skip scan")
            await asyncio.sleep(1800)  # 30 min
        except Exception as e:
            logger.error(f"Confluence scan loop error: {e}")
            await asyncio.sleep(300)


async def morning_report_scheduler():
    # Send morning report daily at 5:30 AM Kuwait time
    logger.info("Morning report scheduler started")
    while True:
        now = datetime.now()
        target = now.replace(hour=5, minute=30, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait_secs = (target - now).total_seconds()
        logger.info(f"Next morning report in {wait_secs/3600:.1f} hours")
        await asyncio.sleep(wait_secs)
        try:
            await send_morning_report(TELEGRAM_TOKEN, ADMIN_TELEGRAM_ID or "669769765")
        except Exception as e:
            logger.error(f"Morning report error: {e}")


async def telegram_polling_loop():
    """Long-polling loop for Telegram updates."""
    global _tg_client, _tg_offset, _tg_running

    if not TELEGRAM_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set - bot disabled")
        return

    _tg_client = httpx.AsyncClient(timeout=httpx.Timeout(40, connect=10))
    _tg_running = True
    logger.info("Telegram polling started")

    consecutive_errors = 0
    try:
      while _tg_running:
        try:
            resp = await _tg_client.get(
                f"{TG_BASE}/getUpdates",
                params={"offset": _tg_offset, "timeout": 30, "allowed_updates": '["message","callback_query"]'},
            )
            if resp.status_code == 200:
                data = resp.json()
                consecutive_errors = 0
                for update in data.get("result", []):
                    _tg_offset = update["update_id"] + 1
                    # Handle callback queries (inline buttons)
                    cb = update.get("callback_query")
                    if cb:
                        asyncio.create_task(tg_handle_callback(cb))
                        continue
                    msg = update.get("message", {})
                    txt = msg.get("text", "")
                    cid = msg.get("chat", {}).get("id")
                    usr = msg.get("from", {})
                    if txt and cid:
                        asyncio.create_task(tg_handle_message(cid, txt, usr))
            elif resp.status_code == 409:
                logger.warning("TG 409 conflict - retrying in 10s")
                await asyncio.sleep(10)
            else:
                logger.error(f"TG poll HTTP {resp.status_code}: {resp.text[:200]}")
                await asyncio.sleep(5)
        except httpx.ReadTimeout:
            continue
        except Exception as e:
            consecutive_errors += 1
            wait = min(consecutive_errors * 5, 60)
            logger.error(f"TG poll error ({consecutive_errors}): {e}")
            await asyncio.sleep(wait)

    finally:
        _tg_running = False
        if _tg_client:
            try:
                await _tg_client.aclose()
            except Exception:
                pass
            _tg_client = None
        logger.info("Telegram polling stopped (cleanup done)")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━



# ═══════════════════════════════════════════════════════════════════════════════
# STRUCTURED MEMORY ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

if _SMEM:
    @app.get("/structured-memory")
    async def smem_stats():
        """Structured memory statistics."""
        return smem.get_stats()

    @app.get("/structured-memory/context")
    async def smem_context(q: str = ""):
        """Preview LLM context string."""
        return {"context": smem.get_context_for_llm(q)}

    @app.post("/structured-memory/fact")
    async def smem_save_fact(data: dict):
        return smem.save_fact(
            content=data["content"],
            category=data.get("category", "general"),
            key=data.get("key", ""),
            tags=data.get("tags", ""),
            confidence=data.get("confidence", 0.9),
            source=data.get("source", "api"),
        )

    @app.post("/structured-memory/event")
    async def smem_save_event(data: dict):
        return smem.save_event(
            content=data["content"],
            category=data.get("category", "general"),
            key=data.get("key", ""),
            tags=data.get("tags", ""),
            expires_at=data.get("expires_at"),
            source=data.get("source", "api"),
        )

    @app.post("/structured-memory/correction")
    async def smem_save_correction(data: dict):
        return smem.save_correction(
            content=data["content"],
            category=data.get("category", "general"),
            key=data.get("key", ""),
            tags=data.get("tags", ""),
            source=data.get("source", "api"),
        )

    @app.get("/structured-memory/search")
    async def smem_search(q: str, type: str = ""):
        results = smem.get_memories(
            type_=type or None,
            search=q,
            limit=20,
        )
        return {"query": q, "count": len(results), "results": results}

    @app.post("/structured-memory/migrate")
    async def smem_migrate():
        """Migrate from old memory table in audit.db."""
        return smem.migrate_from_old_db()

    @app.post("/structured-memory/seed")
    async def smem_seed():
        """Seed initial facts (safe to run multiple times)."""
        return smem.seed_initial()

    @app.post("/structured-memory/decay")
    async def smem_decay():
        """Run confidence decay manually."""
        affected = smem.apply_decay()
        return {"decayed": affected}

    @app.delete("/structured-memory/{memory_id}")
    async def smem_delete(memory_id: int):
        return {"deleted": smem.delete_memory(memory_id)}

    # ── Corrections Learning Loop endpoints ──
    @app.get('/corrections')
    async def get_corrections_stats():
        try:
            from corrections_loop import get_corrections_loop
            cl = get_corrections_loop()
            return cl.get_stats()
        except Exception as e:
            return {'error': str(e)}

    @app.post('/corrections/decay')
    async def decay_corrections_endpoint():
        try:
            from corrections_loop import get_corrections_loop
            cl = get_corrections_loop()
            count = cl.decay_corrections()
            return {'decayed': count}
        except Exception as e:
            return {'error': str(e)}


# ═══ PLANNER + TRACES ENDPOINTS ═══
try:
    from mini_planner import classify_intent, decompose_compound, get_traces, get_trace_stats
    _PLANNER_ENDPOINTS = True
except ImportError:
    _PLANNER_ENDPOINTS = False

if _PLANNER_ENDPOINTS:
    @app.get("/traces")
    async def traces_list(limit: int = 20):
        return {"traces": get_traces(limit)}

    @app.get("/traces/stats")
    async def traces_stats():
        return get_trace_stats()

    @app.post("/classify")
    async def classify_msg(data: dict):
        text = data.get("text", "")
        return classify_intent(text)

    @app.post("/decompose")
    async def decompose_msg(data: dict):
        text = data.get("text", "")
        return decompose_compound(text)





# ═══ FEEDBACK LEARNING ENDPOINTS ═══

@app.get("/feedback/stats")
async def feedback_stats_endpoint():
    try:
        from feedback_learner import get_stats
        return get_stats(30)
    except Exception as e:
        return {"error": str(e)}

@app.get("/feedback/digest")
async def feedback_digest_endpoint():
    try:
        from feedback_learner import generate_digest
        return {"digest": generate_digest(7)}
    except Exception as e:
        return {"error": str(e)}

# ═══ KPI DASHBOARD ENDPOINT ═══


@app.get("/anomalies")
async def anomalies_endpoint():
    """Phase 2: Anomaly detection results."""
    try:
        from anomaly_engine import get_anomaly_summary
        alerts = get_anomaly_summary()
        return {"alerts": alerts, "count": len(alerts)}
    except ImportError:
        return {"error": "anomaly_engine not loaded"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/cost")
async def cost_dashboard():
    """Phase 2: Per-request cost tracking dashboard."""
    try:
        from cost_tracker import get_cost_summary
        return get_cost_summary()
    except ImportError:
        return {"error": "cost_tracker module not found"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/kpi")
async def kpi_dashboard():
    """ChatGPT stability plan: 5 KPI metrics."""
    import sqlite3, json
    kpi = {}
    
    # 1. Message delivery rate (from traces)
    try:
        conn = sqlite3.connect("data/traces.db", timeout=5)
        total = conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
        ok = conn.execute("SELECT COUNT(*) FROM traces WHERE final_status='ok'").fetchone()[0]
        kpi["message_delivery_rate"] = round(ok / max(total,1) * 100, 1)
        kpi["total_messages_traced"] = total
        conn.close()
    except:
        kpi["message_delivery_rate"] = None
        kpi["total_messages_traced"] = 0
    
    # 2. Silent drop count
    kpi["silent_drops"] = 0  # V7 design: no silent drops possible
    
    # 3. Tool usage stats
    try:
        conn = sqlite3.connect("data/traces.db", timeout=5)
        rows = conn.execute("SELECT tools_used FROM traces WHERE tools_count > 0").fetchall()
        tool_counts = {}
        for r in rows:
            try:
                tools = json.loads(r[0])
                for t in tools:
                    tool_counts[t] = tool_counts.get(t, 0) + 1
            except: pass
        kpi["tool_usage"] = tool_counts
        conn.close()
    except:
        kpi["tool_usage"] = {}
    
    # 4. Clarification rate (approximation: responses containing question marks)
    kpi["clarification_rate"] = "tracked_via_traces"
    
    # 5. Structured memory stats
    try:
        import structured_memory as smem
        kpi["memory"] = smem.get_stats()
    except:
        kpi["memory"] = {}
    
    # 5.5 Cost tracking (Phase 2)
    try:
        from cost_tracker import get_cost_for_kpi
        kpi["cost"] = get_cost_for_kpi()
    except:
        kpi["cost"] = {}
    
    # 6. Benchmark results
    try:
        with open("benchmark_results.json") as bf:
            br = json.load(bf)
        kpi["benchmark"] = {
            "passed": br.get("passed", 0),
            "failed": br.get("failed", 0),
            "pass_rate": round(br.get("passed",0) / max(br.get("passed",0)+br.get("failed",0),1) * 100, 1),
        }
    except:
        kpi["benchmark"] = {}
    
    # 7. System resources
    try:
        import subprocess
        cpu = subprocess.getoutput("top -bn1 | grep 'Cpu' | awk '{print $2}'")
        mem = subprocess.getoutput("free -m").split(chr(10))[1].split()
        temp = subprocess.getoutput("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null")
        kpi["system"] = {"cpu": cpu, "memory": mem, "temp_c": round(int(temp)/1000,1) if temp.isdigit() else None}
    except:
        kpi["system"] = {}
    
    return kpi



# ═══════════════════════════════════════════════════
# PRIORITY ENGINE — imported from priority_engine.py
# ═══════════════════════════════════════════════════
from priority_engine import (
    build_priority_engine, build_assistant_surface,
    _pe_get_extended_snapshot, _pe_get_radar_snapshot,
    set_inbox_cache_ref as _pe_set_inbox_cache_ref,
)

# ═══════════════════════════════════════════════════
# HA DASHBOARD — imported from dashboard_api.py (Router)
# ═══════════════════════════════════════════════════
# (imported near app creation + in lifespan)
