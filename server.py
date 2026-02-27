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

Endpoints: /ask, /health, /ha/*, /ssh/run, /agent, /approve/{id}, /audit, /win/*,
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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel, Field, field_validator
from openai import AsyncOpenAI, OpenAIError
from anthropic import AsyncAnthropic
import httpx

# Brain Module (intelligence layer)
try:
    from brain import build_system_prompt, build_user_message, learn_from_result, reload as brain_reload, get_brain_stats, get_quick_response, build_response_prompt, proactive_loop, get_system_diag, run_backup, backup_loop, record_error, detect_user, get_multiuser_stats, record_feedback, log_request, get_analytics
    BRAIN_AVAILABLE = True
except Exception as e:
    BRAIN_AVAILABLE = False
    logging.getLogger("master_ai").warning("Brain module not available, using built-in planner: %s", e)
try:
    from tg_ops import is_tg_admin, get_pending_approvals, process_approval, format_approval_buttons, run_backup as tg_run_backup, get_admin_chat_id
    TG_OPS_OK = True
except Exception:
    TG_OPS_OK = False

try:
    from tg_home import cmd_rooms, cmd_devices, cmd_find, find_buttons, cmd_scenes_dynamic, handle_devctl
    TG_HOME_OK = True
except Exception:
    TG_HOME_OK = False

try:
    from tg_session import tg_session_get, tg_session_upsert, tg_session_append_context, tg_session_reset, detect_followup
    from tg_session_resolver import resolve_followup_action
    TG_SESSION_OK = True
except Exception:
    TG_SESSION_OK = False

try:
    from tg_intent_router import route_intent
    TG_INTENT_OK = True
except Exception:
    TG_INTENT_OK = False

try:
    from tg_suggestions import get_suggestions
    from tg_morning_report import build_morning_report, send_morning_report
    TG_SUGGEST_OK = True
except Exception:
    TG_SUGGEST_OK = False

# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# CONFIGURATION
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY", "")
anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
HA_URL = os.getenv("HA_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")
AGENT_SECRET = os.getenv("AGENT_SECRET", "")
MASTER_API_KEY = os.getenv("MASTER_AI_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID", "")

VERSION = "5.4.0"
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
        logger.error(f"Policy load failed: {e}")
    return DEFAULT_POLICY.copy()

def save_policy(policy: dict):
    try:
        os.makedirs(os.path.dirname(POLICY_FILE), exist_ok=True)
        with open(POLICY_FILE, "w") as f:
            json.dump(policy, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Policy save failed: {e}")


START_TIME = time.time()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("master_ai")

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
                    approval_id=None, approved_at=None):
    try:
        conn = sqlite3.connect(AUDIT_DB)
        conn.execute(
            """INSERT INTO audit_log
               (request_id, task_id, step_index, task, actions, results, status, duration_ms, approval_id, approved_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (request_id, task_id, step_index, str(task)[:500],
             json.dumps(actions) if actions else None,
             json.dumps(results) if results else None,
             status, round(duration * 1000, 1), approval_id, approved_at)
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

    # Try Anthropic first
    if anthropic_client:
        try:
            resp = await anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                temperature=temperature
            )
            text = resp.content[0].text
            if trace:
                trace.llm("claude-sonnet-4", time.time() - t0,
                          tokens_in=resp.usage.input_tokens, tokens_out=resp.usage.output_tokens)
            return text
        except Exception as e:
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

SCHEMA_VERSION = "3.3.0"

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
# ACTION EXECUTORS
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

async def _exec_ha_get_state(entity_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {HA_TOKEN}"}
        if entity_id == "*":
            r = await client.get(f"{HA_URL}/api/states", headers=headers, timeout=10)
            states = r.json()
            return {"success": True, "count": len(states), "states": states[:50]}
        # Support comma-separated entity IDs
        ids = [e.strip() for e in entity_id.split(",") if e.strip()]
        if len(ids) > 1:
            results = []
            for eid in ids:
                try:
                    r = await client.get(f"{HA_URL}/api/states/{eid}", headers=headers, timeout=10)
                    if r.status_code == 200:
                        results.append(r.json())
                    else:
                        results.append({"entity_id": eid, "state": f"error_{r.status_code}"})
                except Exception as e:
                    results.append({"entity_id": eid, "state": f"error: {e}"})
            return {"success": True, "count": len(results), "states": results}
        r = await client.get(f"{HA_URL}/api/states/{ids[0]}", headers=headers, timeout=10)
        if r.status_code == 200:
            return {"success": True, "state": r.json()}
        return {"success": False, "error": f"HTTP {r.status_code}"}


async def _exec_ha_call_service(domain: str, service: str, service_data: dict = None) -> dict:
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
        r = await client.post(f"{HA_URL}/api/services/{domain}/{service}",
                              headers=headers, json=service_data or {}, timeout=10)
        return {"success": r.status_code == 200, "status_code": r.status_code}


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
        return await _exec_ha_call_service(args["domain"], args["service"], args.get("service_data"))

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
# EVENT PROCESSOR â Glue between EventEngine + iterative_engine (v5.2)
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
    """Process a single pending event through iterative_engine."""
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

    # Low risk or approved level - execute via iterative_engine
    event_engine.update_event(eid, status="processing")
    try:
        goal = f"Event [{event.get('type','')}]: {event.get('title','')}. Detail: {json.dumps(event.get('detail','{}'))}. Entity: {event.get('entity_id','')}. Analyze and take appropriate action."
        trace = RequestTrace(f"event_{eid}")
        task_id = f"evt_{eid}"
        result = await iterative_engine(goal=goal, context={"source": "event_engine", "event_id": eid}, trace=trace, task_id=task_id)
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

PLANNER_SYSTEM_PROMPT = """You are Master AI v5, a central intelligence system controlling a smart home and PC.

Available action types:
- ha_get_state: {entity_id} ÃÂ¢ÃÂÃÂ get HA entity state (use "*" for all)
- ha_call_service: {domain, service, service_data} ÃÂ¢ÃÂÃÂ call HA service
- ssh_run: {cmd} ÃÂ¢ÃÂÃÂ run shell command on Raspberry Pi
- respond_text: {text} ÃÂ¢ÃÂÃÂ respond to user with text
- win_diagnostics: {checks[]} ÃÂ¢ÃÂÃÂ run Windows diagnostics
- win_powershell: {script} ÃÂ¢ÃÂÃÂ run PowerShell on Windows PC
- win_winget_install: {package} ÃÂ¢ÃÂÃÂ install via winget
- http_request: {url, method, headers, body} ÃÂ¢ÃÂÃÂ HTTP request
- memory_store: {category, content, type} ÃÂ¢ÃÂÃÂ store to long-term memory

Entity map (rooms and devices):
{entity_context}

You MUST respond ONLY with valid JSON (no markdown, no explanation):
{{
  "mode": "single_step" | "multi_step",
  "thought": "brief reasoning",
  "next_step": {{"type": "action_type", "args": {{...}}}},
  "plan": [list of steps if multi_step],
  "task_state": "running" | "waiting" | "complete",
  "response": "text response to user"
}}

Rules:
- For simple questions/greetings ÃÂ¢ÃÂÃÂ mode: single_step, next_step: respond_text, task_state: complete
- For device control ÃÂ¢ÃÂÃÂ mode: single_step or multi_step with ha_call_service actions
- For complex tasks ÃÂ¢ÃÂÃÂ mode: multi_step with a plan array
- If you need more info before continuing ÃÂ¢ÃÂÃÂ task_state: waiting
- Always include "response" with a user-facing message in Arabic
- NEVER invent entity IDs ÃÂ¢ÃÂÃÂ use ONLY from the entity map above
"""


def build_entity_context() -> str:
    """Build concise entity context for planner."""
    if not entity_map:
        return "(no entity map loaded)"
    parts = []
    rooms = entity_map.get("rooms", entity_map)
    if isinstance(rooms, dict):
        for room_name, room_data in list(rooms.items())[:25]:
            entities = room_data if isinstance(room_data, list) else room_data.get("entities", [])
            if isinstance(entities, list):
                ids = [e.get("entity_id", e) if isinstance(e, dict) else str(e) for e in entities[:10]]
                parts.append(f"{room_name}: {', '.join(ids)}")
            elif isinstance(entities, dict):
                ids = list(entities.keys())[:10]
                parts.append(f"{room_name}: {', '.join(ids)}")
    return "\n".join(parts) if parts else "(entity map format unknown)"


async def plan_step(goal: str, context: dict = None, trace: RequestTrace = None,
                    previous_results: list = None, retry: bool = False) -> dict:
    """Single planning step ÃÂ¢ÃÂÃÂ LLM generates next action(s)."""
    if BRAIN_AVAILABLE:
        system = build_system_prompt()
    else:
        pass
        entity_ctx = build_entity_context()
        system = PLANNER_SYSTEM_PROMPT.replace("{entity_context}", entity_ctx)

    if BRAIN_AVAILABLE:
        user_msg = build_user_message(goal, context, previous_results)
    else:
        pass
        user_msg = f"User request: {goal}"

    if not BRAIN_AVAILABLE:
        # Fallback: add memory and context manually
        # Add memory context
        mem_ctx = memory_retrieve_context(goal)
        if mem_ctx:
            user_msg += f"\n\nContext from memory:\n{mem_ctx}"

        # Add previous step results for iterative planning
        if previous_results:
            user_msg += "\n\nPrevious step results:\n"
            for i, pr in enumerate(previous_results[-5:]):
                user_msg += f"Step {i}: {json.dumps(pr)[:300]}\n"

        # Add retry correction
        if retry and context and context.get("validation_error"):
            user_msg += f"\n\nYour previous response had a validation error: {context['validation_error']}\nPlease fix and respond with valid JSON."

        # Add extra context
        if context:
            for k in ("extra", "task_context"):
                if k in context:
                    user_msg += f"\n\n{k}: {context[k]}"

    else:
        pass
        # Brain already handles memory, previous_results, and context
        if retry and context and context.get("validation_error"):
            user_msg += f"\n\nRetry correction: {context['validation_error']}"

    raw = await llm_call(system, user_msg, max_tokens=2048, trace=trace)

    # Parse response
    parsed = repair_json(raw)
    if not parsed:
        logger.error(f"Failed to parse planner output: {raw[:200]}")
        return {
            "mode": "single_step",
            "next_step": {"type": "respond_text", "args": {"text": "ÃÂÃÂ¹ÃÂÃÂ°ÃÂÃÂ±ÃÂÃÂ§ÃÂÃÂÃÂÃÂ ÃÂÃÂÃÂÃÂ§ÃÂÃÂ¬ÃÂÃÂÃÂÃÂª ÃÂÃÂÃÂÃÂ´ÃÂÃÂÃÂÃÂÃÂÃÂ© ÃÂÃÂÃÂÃÂ ÃÂÃÂÃÂÃÂ¹ÃÂÃÂ§ÃÂÃÂÃÂÃÂ¬ÃÂÃÂ© ÃÂÃÂ§ÃÂÃÂÃÂÃÂ·ÃÂÃÂÃÂÃÂ¨"}},
            "task_state": "complete",
            "response": "ÃÂÃÂ¹ÃÂÃÂ°ÃÂÃÂ±ÃÂÃÂ§ÃÂÃÂÃÂÃÂ ÃÂÃÂÃÂÃÂ§ÃÂÃÂ¬ÃÂÃÂÃÂÃÂª ÃÂÃÂÃÂÃÂ´ÃÂÃÂÃÂÃÂÃÂÃÂ© ÃÂÃÂÃÂÃÂ ÃÂÃÂÃÂÃÂ¹ÃÂÃÂ§ÃÂÃÂÃÂÃÂ¬ÃÂÃÂ© ÃÂÃÂ§ÃÂÃÂÃÂÃÂ·ÃÂÃÂÃÂÃÂ¨",
            "_parse_error": True
        }

    return parsed


async def iterative_engine(goal: str, context: dict = None, trace: RequestTrace = None,
                           task_id: str = None, max_iterations: int = 8) -> dict:
    """
    [UPGRADE 2] Iterative planning loop: plan ÃÂ¢ÃÂÃÂ execute ÃÂ¢ÃÂÃÂ verify ÃÂ¢ÃÂÃÂ replan
    Returns final result with all step outputs.
    """
    all_results = []
    all_actions = []
    final_response = ""
    iteration = 0

    if task_id:
        TaskManager.update_task(task_id, state="running")

    while iteration < max_iterations:
        iteration += 1
        if trace:
            trace.step(f"plan_iteration_{iteration}", "start")

        # 1. PLAN
        plan = await plan_step(goal, context, trace, previous_results=all_results)

        task_state = plan.get("task_state", "complete")
        final_response = plan.get("response", "")
        mode = plan.get("mode", "single_step")

        # 2. DETERMINE ACTIONS
        if mode == "multi_step" and "plan" in plan:
            actions = plan["plan"]
        elif "next_step" in plan:
            actions = [plan["next_step"]]
        else:
            actions = [{"type": "respond_text", "args": {"text": final_response or "ÃÂÃÂªÃÂÃÂ"}}]

        # 3. VALIDATE & EXECUTE each action
        for i, action in enumerate(actions):
            # [UPGRADE 3] Schema validation
            valid, cleaned, error = validate_action(action)
            if not valid:
                # Retry planning once with correction
                if not context:
                    context = {}
                context["validation_error"] = error
                retry_plan = await plan_step(goal, context, trace, previous_results=all_results, retry=True)
                retry_action = retry_plan.get("next_step", action)
                valid2, cleaned2, error2 = validate_action(retry_action)
                if valid2:
                    action = cleaned2
                else:
                    logger.warning(f"Action validation failed after retry: {error2}")
                    result = {"success": False, "error": f"Invalid action: {error2}"}
                    all_results.append(result)
                    continue
            else:
                action = cleaned

            # Execute
            step_idx = len(all_actions)
            result = await execute_action(action, trace, step_idx)
            all_actions.append(action)
            all_results.append(result)

            # [UPGRADE 1] Record step in task
            if task_id:
                TaskManager.add_step_result(task_id, step_idx, action, result)

        # 4. CHECK STATE
        if task_state == "complete":
            break
        elif task_state == "waiting":
            if task_id:
                TaskManager.update_task(task_id, state="waiting")
            break
        # else: "running" ÃÂ¢ÃÂÃÂ loop continues with results fed back to planner

    # Finalize task
    if task_id:
        if task_state == "complete":
            TaskManager.complete_task(task_id, {"response": final_response})
        elif task_state != "waiting":
            TaskManager.complete_task(task_id)

    # Brain learning (async, non-blocking)
    if BRAIN_AVAILABLE and all_actions:
        try:
            logger.info(f"BRAIN_LEARN_HOOK: goal={goal[:40]}, actions={len(all_actions)}, results={len(all_results)}")
            asyncio.create_task(learn_from_result(goal, all_actions, all_results, final_response))
        except Exception as e:
            logger.error(f"BRAIN_LEARN_HOOK error: {e}")
    else:
        pass

    # Quick response template (skip LLM if simple action)
    if BRAIN_AVAILABLE and all_actions:
        try:
            quick = get_quick_response(all_actions, all_results)
            if quick:
                final_response = quick
                logger.info(f"QUICK_RESPONSE: {quick[:50]}")
        except Exception as e:
            logger.error(f"Quick response error: {e}")
    return {
        "response": final_response,
        "actions": all_actions,
        "results": all_results,
        "iterations": iteration,
        "task_state": task_state,
    }


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# SUMMARY GENERATOR
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

async def generate_summary(task: str, actions: list, results: list, trace: RequestTrace = None) -> str:
    if not results:
        return ""
    if BRAIN_AVAILABLE:
        try:
            summary_prompt = build_response_prompt()
        except Exception:
            summary_prompt = "Summarize the results of this task in Arabic. Be concise."
    else:
        summary_prompt = "Summarize the results of this task in Arabic. Be concise."
    detail = f"Task: {task}\nResults: {json.dumps(results)[:2000]}"
    try:
        return await llm_call(summary_prompt, detail, max_tokens=500, trace=trace)
    except Exception:
        return ""


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# FASTAPI APP
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

@asynccontextmanager
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
    logger.info(f"Master AI v{VERSION} started")
    asyncio.create_task(event_processor_loop())
    logger.info("Event processor loop scheduled")
    # Telegram bot polling
    if TELEGRAM_TOKEN:
        asyncio.create_task(telegram_polling_loop())
        asyncio.create_task(morning_report_scheduler())
        logger.info("Telegram bot polling scheduled")
    # Phase 4: Proactive monitoring engine
    if BRAIN_AVAILABLE:
        try:
            asyncio.create_task(proactive_loop())
            logger.info("Proactive engine scheduled")
        except Exception as e:
            logger.error(f"Proactive engine failed to start (non-fatal): {e}")
        # Phase 4.5: Observability backup engine
        try:
            asyncio.create_task(backup_loop())
            logger.info("Backup engine scheduled")
        except Exception as e:
            logger.error(f"Backup engine failed to start (non-fatal): {e}")
    yield
    logger.info("Master AI shutting down")

app = FastAPI(title="Master AI", version=VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Event Engine (v5.1)
event_engine = EventEngine(AUDIT_DB)


# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ
# API KEY MIDDLEWARE
# ÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂÃÂ¢ÃÂÃÂ

from starlette.middleware.base import BaseHTTPMiddleware

class APIKeyMiddleware(BaseHTTPMiddleware):
    OPEN_PATHS = {"/health", "/panel"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in self.OPEN_PATHS or path.startswith("/webhook/") or not MASTER_API_KEY:
            return await call_next(request)
        key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if key != MASTER_API_KEY:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)

app.add_middleware(APIKeyMiddleware)

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

    # Run iterative engine
    t0 = time.time()
    try:
        result = await iterative_engine(
            body.message, context=body.context, trace=trace, task_id=task_id
        )
    except Exception as e:
        logger.error(f"Engine error: {e}", exc_info=True)
        TaskManager.fail_task(task_id, str(e))
        result = {"response": f"ÃÂÃÂ®ÃÂÃÂ·ÃÂÃÂ£: {e}", "actions": [], "results": [], "task_state": "failed", "iterations": 0}

    duration = time.time() - t0

    # Add response to short-term memory
    memory_add_short_term("assistant", result["response"])

    # Audit log
    await audit_log(
        task=body.message, actions=result.get("actions"), results=result.get("results"),
        status=result.get("task_state", "complete"), duration=duration,
        request_id=request_id, task_id=task_id
    )

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
    trace = RequestTrace()
    task_id = TaskManager.create_task(body.message, trace.request_id)
    trace.task_id = task_id

    memory_add_short_term("user", body.message)

    t0 = time.time()
    try:
        result = await iterative_engine(
            body.message, context=body.context, trace=trace, task_id=task_id
        )
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        TaskManager.fail_task(task_id, str(e))
        return {"response": f"ÃÂÃÂ®ÃÂÃÂ·ÃÂÃÂ£: {e}", "task_id": task_id}

    duration = time.time() - t0
    memory_add_short_term("assistant", result["response"])

    await audit_log(
        task=body.message, actions=result.get("actions"), results=result.get("results"),
        status="ok", duration=duration, request_id=trace.request_id, task_id=task_id
    )

    # Quick response template (skip LLM if simple action)
    if BRAIN_AVAILABLE and all_actions:
        try:
            quick = get_quick_response(all_actions, all_results)
            if quick:
                final_response = quick
                logger.info(f"QUICK_RESPONSE: {quick[:50]}")
        except Exception as e:
            logger.error(f"Quick response error: {e}")
    return {
        "response": result["response"],
        "task_id": task_id,
        "request_id": trace.request_id,
        "actions_count": len(result.get("actions", [])),
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

    # Quick response template (skip LLM if simple action)
    if BRAIN_AVAILABLE and all_actions:
        try:
            quick = get_quick_response(all_actions, all_results)
            if quick:
                final_response = quick
                logger.info(f"QUICK_RESPONSE: {quick[:50]}")
        except Exception as e:
            logger.error(f"Quick response error: {e}")
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


@app.post("/webhook/event/{token}", tags=["webhook"])
async def webhook_event(token: str, req: EventRequest):
    policy = load_policy()
    expected = policy.get("webhook_token")
    if not expected:
        return JSONResponse({"error": "webhook not configured"}, status_code=503)
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
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WEB PANEL - moved to modules/panel.py

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TELEGRAM BOT (v5.4.6)
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


    global _tg_client
    if not _tg_client:
        _tg_client = httpx.AsyncClient(timeout=30)
    for part in tg_split_message(text):
        try:
            payload = {"chat_id": chat_id, "text": part}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            resp = await _tg_client.post(f"{TG_BASE}/sendMessage", json=payload)
            if resp.status_code != 200:
                logger.error(f"TG send fail: {resp.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"TG send error: {e}")
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

async def tg_handle_command(chat_id, text: str) -> str | None:
    """Handle quick commands. Returns response or None to pass to engine."""
    cmd = text.strip().lower()

    if cmd == "/start":
        return "\U0001f3e0 Master AI Bot\n\u0623\u0631\u0633\u0644 \u0623\u064a \u0631\u0633\u0627\u0644\u0629 \u0623\u0648 \u0623\u0645\u0631.\n\n/status \u2014 \u062d\u0627\u0644\u0629 \u0627\u0644\u0646\u0638\u0627\u0645\n/lights \u2014 \u0627\u0644\u0623\u0636\u0648\u0627\u0621 \u0627\u0644\u0645\u0634\u063a\u0644\u0629\n/temp \u2014 \u062d\u0631\u0627\u0631\u0629 \u0627\u0644\u0645\u0643\u064a\u0641\u0627\u062a"

    if cmd == "/report":
        try:
            report = await build_morning_report()
            await tg_send(chat_id, report)
        except Exception as e:
            await tg_send(chat_id, f"Report error: {str(e)[:100]}")
        return "__inline_sent__"

    if cmd == "/reset":
        if TG_SESSION_OK:
            tg_session_reset(str(chat_id))
        return "Session cleared"

    if cmd == "/status":
        uptime = int(time.time() - START_TIME)
        h, m = divmod(uptime // 60, 60)
        return f"\u2705 Master AI v{VERSION}\n\u23f1 Uptime: {h}h {m}m\n\U0001f50c Plugins: {len(PLUGIN_REGISTRY._plugins)}"

    if cmd == "/lights":
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                resp = await c.get(
                    f"{HA_URL}/api/states",
                    headers={"Authorization": f"Bearer {HA_TOKEN}"}
                )
                states = resp.json()
                on_lights = [
                    s["attributes"].get("friendly_name", s["entity_id"])
                    for s in states
                    if s["entity_id"].startswith("light.") and s["state"] == "on"
                ]
            if on_lights:
                return f"\U0001f4a1 ({len(on_lights)}):\n" + "\n".join(f"\u2022 {n}" for n in on_lights)
            return "\U0001f4a1 \u0643\u0644 \u0627\u0644\u0623\u0636\u0648\u0627\u0621 \u0645\u0637\u0641\u064a\u0629"
        except Exception as e:
            return f"\u26a0\ufe0f {e}"

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
            return f"\U0001f4ca Diagnostics\n\nCPU: {cpu}%\nRAM: {ram}%\nTemp: {temp}\u00b0C\nDisk: {disk}%\nDB: {db}MB\nErrors/h: {errs}"
        except Exception as e:
            return f"\u26a0\ufe0f diag: {e}"

    if cmd == "/home":
        buttons = [
            {"text": "💡 الأضواء", "callback_data": "cmd:lights"},
            {"text": "❄️ المكيفات", "callback_data": "cmd:temp"},
            {"text": "🎬 المشاهد", "callback_data": "cmd:scenes"},
            {"text": "📷 الكاميرات", "callback_data": "cmd:cam"},
            {"text": "🧠 العقل", "callback_data": "cmd:brain"},
            {"text": "📊 النظام", "callback_data": "cmd:diag"},
        ]
        await tg_send_inline(chat_id, "🏠 *القائمة الرئيسية*", buttons, columns=2)
        return "__inline_sent__"

    # --- Level 2: Home commands ---
    if cmd == "/rooms":
        if not TG_HOME_OK:
            return "tg_home module not loaded"
        result = await cmd_rooms()
        if TG_SESSION_OK:
            tg_session_upsert(str(chat_id), last_intent="rooms")
        return result

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


    if cmd == "/help":
        return "\U0001f3e0 Master AI\n\n/status - \u0627\u0644\u0646\u0638\u0627\u0645\n/lights - \u0627\u0644\u0623\u0636\u0648\u0627\u0621\n/temp - \u0627\u0644\u0645\u0643\u064a\u0641\u0627\u062a\n/brain - \u0627\u0644\u0639\u0642\u0644\n/diag - \u062a\u0634\u062e\u064a\u0635\n\n\u0623\u0631\u0633\u0644 \u0623\u064a \u0631\u0633\u0627\u0644\u0629 \U0001f44d"

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
                        await tg_send(chat_id, "❓ ما فيه سياق — جرب /find")
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


    else:
        answer = ""

    try:
        await _tg_client.post(f"{TG_BASE}/answerCallbackQuery", json={
            "callback_query_id": cq_id, "text": answer
        })
    except Exception:
        pass


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

async def tg_handle_message(chat_id, text: str, user: dict):
    """Process a Telegram message through the iterative engine."""
    try:
        return await _tg_handle_message_inner(chat_id, text, user)
    except Exception as e:
        logger.error(f"TG HANDLE CRASH: {e}", exc_info=True)
        try:
            await tg_send(chat_id, f"❌ Error: {str(e)[:100]}")
        except Exception:
            pass

async def _tg_handle_message_inner(chat_id, text: str, user: dict):
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

    quick = await tg_handle_command(chat_id, text)
    if quick == "__inline_sent__":
        return
    if quick:
        await tg_send(chat_id, quick)
        return

    # --- Intent Router (Phase A3) — check FIRST for explicit device+room commands ---
    if TG_INTENT_OK:
        try:
            intent_result = await route_intent(text)
            if intent_result:
                _ir_text = intent_result["text"] if isinstance(intent_result, dict) else intent_result
                _ir_entities = intent_result.get("entities", []) if isinstance(intent_result, dict) else []
                _ir_action = intent_result.get("action", "") if isinstance(intent_result, dict) else ""
                logger.info(f"TG intent routed: {text[:50]} -> {_ir_action} ({len(_ir_entities)} entities)")
                if TG_SESSION_OK:
                    tg_session_upsert(str(chat_id), last_intent="action", last_entities=_ir_entities)
                if TG_SUGGEST_OK:
                    _sact = "on" if "شغّلت" in _ir_text else "off" if "طفّيت" in _ir_text else "set_temp" if "ضبطت" in _ir_text else "scene" if "مشهد" in _ir_text else "query" if "الحالة" in _ir_text else None
                    _sbtns = get_suggestions(_sact) if _sact else []
                    if _sbtns:
                        # _sbtns is already rows format [[btn1,btn2],[btn3]]
                        _kb = json.dumps({"inline_keyboard": _sbtns})
                        _payload = {"chat_id": chat_id, "text": _ir_text, "reply_markup": _kb, "parse_mode": "Markdown"}
                        try:
                            await _tg_client.post(f"{TG_BASE}/sendMessage", json=_payload)
                        except Exception as _e:
                            logger.error(f"suggest send error: {_e}")
                            await tg_send(chat_id, _ir_text, parse_mode="Markdown")
                    else:
                        await tg_send(chat_id, _ir_text, parse_mode="Markdown")
                else:
                    await tg_send(chat_id, _ir_text, parse_mode="Markdown")
                return
        except Exception as e:
            logger.error(f"Intent router error: {e}")

    # --- Follow-up Resolution (Phase A2) — only if intent router didn't match ---
    if TG_SESSION_OK:
        session = tg_session_get(str(chat_id))
        if session:
            followup = detect_followup(text, session)
            ftype = followup.get("type")

            if ftype == "followup":
                logger.info(f"TG followup: {followup}")
                result = await resolve_followup_action(followup, HA_URL, HA_TOKEN)
                await tg_send(chat_id, result, parse_mode="Markdown")
                return

            elif ftype == "correction":
                # Show disambiguation with last entities as buttons (friendly names from entity_map)
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
                    await tg_send(chat_id, "❓ وش تقصد؟ جرب /find")
                return

            elif ftype == "repeat":
                # Re-run last action on same entities
                last_ents = followup.get("last_entities", [])
                last_intent = followup.get("last_intent", "")
                if last_ents and last_intent == "action":
                    followup_repeat = {"type": "followup", "action": "on", "last_entities": last_ents}
                    result = await resolve_followup_action(followup_repeat, HA_URL, HA_TOKEN)
                    await tg_send(chat_id, result, parse_mode="Markdown")
                else:
                    await tg_send(chat_id, "❓ ما فيه سياق سابق — جرب /find")
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
            _sess = tg_session_get(str(chat_id))
            if _sess and _sess.get("context_window"):
                for _cm in _sess["context_window"][-4:]:  # last 4 context items
                    memory_add_short_term(_cm.get("role","user"), _cm.get("text",""))
        except Exception:
            pass
    memory_add_short_term("user", f"[Telegram/{user_name}] {text}")

    t0 = time.time()
    result = {}
    try:
        result = await asyncio.wait_for(iterative_engine(
            goal=text,
            context={"source": "telegram", "chat_id": str(chat_id), "user_name": user_name, "user_profile": user_profile},
            trace=trace,
            task_id=task_id,
        ), timeout=120)
        response = result.get("response", "\u2705 Done")
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
    )
    await tg_send_with_feedback(chat_id, response, request_id=trace.request_id)

    # Save AI response to session context
    if TG_SESSION_OK:
        try:
            tg_session_append_context(str(chat_id), "assistant", response[:200])
        except Exception:
            pass


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
            await send_morning_report(TELEGRAM_BOT_TOKEN, ADMIN_TELEGRAM_ID or "669769765")
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

    logger.info("Telegram polling stopped")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

