"""
chat_v7.py — Direct LLM + Tool Use (Anthropic native)
NO planner. NO JSON. NO synthesis. NO truncation.
"""
import json, time, logging
from collections import defaultdict, deque
logger = logging.getLogger("chat_v7")

# Integration: context management (Tier3 #15)
try:
    from context_manager import manage_context as _manage_ctx
    _CTX_MGR_OK = True
except ImportError:
    _CTX_MGR_OK = False

# Structured Memory
try:
    import structured_memory as smem
    _SMEM = True
except ImportError:
    _SMEM = False

# Self-check + Tool outcome
try:
    from self_check import validate_answer, save_tool_outcomes, save_session_summary
    _SELF_CHECK = True
except ImportError:
    _SELF_CHECK = False

# Corrections Learning Loop
try:
    from corrections_loop import process_correction as _process_correction, get_correction_context as _get_correction_context, apply_corrections_to_text as _apply_corrections
    _CORRECTIONS = True
except ImportError:
    _CORRECTIONS = False

# Confidence engine
try:
    from confidence_engine import score_tool_call, choose_response_layer
    _CONF_ENGINE = True
except ImportError:
    _CONF_ENGINE = False

try:
    from approval_ux import format_approval_message
    _APPROVAL_UX = True
except Exception:
    _APPROVAL_UX = False

# Mini planner + intent + tracing
try:
    from mini_planner import classify_intent, decompose_compound, save_trace, get_trace_stats
    _PLANNER = True
except ImportError:
    _PLANNER = False

# Smart tools enrichment
try:
    from smart_tools import enrich_ha_state, enrich_shift_result, summarize_tool_result
    _SMART_TOOLS = True
except ImportError:
    _SMART_TOOLS = False

# Tool cache + parallel execution (Phase 2)
try:
    from tool_cache import execute_tools_parallel, cache_get, cache_set, cache_stats
    _TOOL_CACHE = True
except ImportError:
    _TOOL_CACHE = False

# Cost tracking (Phase 2)
try:
    from cost_tracker import track_cost, track_cost_openai
    _COST_TRACK = True
except ImportError:
    _COST_TRACK = False

# Phase 3: Execution Policy + Tool Outcome
try:
    from exec_policy import check_policy, record_outcome, track_session, get_tool_stats
    _EXEC_POLICY = True
except ImportError:
    _EXEC_POLICY = False

# OpenAI fallback
_openai_client = None
def _init_openai():
    global _openai_client
    if _openai_client: return _openai_client
    try:
        import os as _os
        from openai import AsyncOpenAI
        _k = _os.getenv("OPENAI_API_KEY", "")
        if _k:
            _openai_client = AsyncOpenAI(api_key=_k)
            logger.info("OpenAI fallback ready")
    except Exception as e:
        logger.warning(f"OpenAI fallback unavailable: {e}")
    return _openai_client

def _tools_to_openai_functions():
    """Convert Anthropic tool format to OpenAI function format."""
    funcs = []
    for t in TOOLS:
        funcs.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"]
            }
        })
    return funcs

def _safe_json_truncate(data, max_len=4000):
    """Truncate JSON string safely without cutting mid-object."""
    s = json.dumps(data, ensure_ascii=False, default=str)
    if len(s) <= max_len:
        return s
    return json.dumps({"truncated": True, "data": s[:max_len-50], "original_len": len(s)})

# Conversation history per user (max 10 turns = 20 messages)
_conversations: dict[str, deque] = defaultdict(lambda: deque(maxlen=20))
MAX_ROUNDS = 15  # max tool-use rounds per request

# Per-user locks to prevent race conditions on _conversations
import asyncio as _aio
_conversation_locks: dict[str, _aio.Lock] = {}

def _get_user_lock(user_id: str) -> _aio.Lock:
    if user_id not in _conversation_locks:
        _conversation_locks[user_id] = _aio.Lock()
    return _conversation_locks[user_id]

# ── V7 System Prompt Override ──────────────────────────────────────
# This overrides old iterative_engine instructions from brain_core
V8_SYSTEM_OVERRIDE = """
[V8 SYSTEM]

You are Master AI v8.0 — Salem's smart home assistant in Kuwait.
Speak Kuwaiti Arabic naturally. Salem uses Telegram.

RULES:
1. Natural Arabic only — no JSON, code blocks, markdown (**bold**, `code`), or structured formats
2. YOU decide. Search memory FIRST for any person/name/date before saying "I don't know"
3. AC max=23°C (house rule). No room specified=ASK which room
4. Covers=INVERTED (open→close_cover, close→open_cover in HA)
5. Fan types: شفاط(exhaust), منقي(purifier), معطر(freshener) — never مروحة
6. Short answers preferred. If tool fails, try best answer or ask — never silent
7. Compound questions: answer ALL parts using multiple tools

TOOL RULES:
- ha_get_state: use wildcards (climate.*, light.*) or entity_id
- ha_call_service: provide entity_id, domain, service. For scenes use scene domain + turn_on
- get_shift: date format YYYY-MM-DD. No date=today. Returns shift letter + timing
- get_stock_price: Get real-time KSE stock price. Use Arabic names: كلينينق, بيتك, زين, بوبيان etc
- analyze_stock: Full technical analysis (RSI, EMA, VWAP, MACD, S/R, trend, verdict). Use for "شرايك بسهم X" or "حلل X"
- get_trading_advice: AI advisor opinion with entry/exit/SL. Combines analysis + user strategies. Use for "نصيحتك عن X"
- calendar_list_events: range_type=today/tomorrow/week. Shows events from Google Calendar with shift conflicts
- calendar_create_event: Create event in Google Calendar. title+start_iso+end_iso (ISO: 2026-03-20T19:00:00). You ARE connected to Google Calendar
- calendar_delete_event: Delete event by title_search. Searches upcoming week events
- task_list: List user tasks (personal+work). Filter by status/category/due_today/due_overdue
- task_create: Create a new task. title required. category=personal|work, priority=high|med|low, due_date=YYYY-MM-DD
- task_update: Update task by task_id. Change status/priority/due_date/title
TASK RULES:
- When user says "خلصت X" or "انجزت X" — use task_list to find task then task_update status=done
- When user asks to add a task — use task_create. Guess category (personal/work) from context
- When user asks about tasks without specifying — use task_list with no filters (shows active only)
- task_list due_today=true for "مهام اليوم", due_overdue=true for "المتأخرة"
- relationship_lookup: person info, birthday, occasions
- relationship_add: add person/occasion/note
- relationship_upcoming: upcoming occasions/birthdays
- expense_add_entry: add expense (سجل / صرف / أضف)
- expense_get_summary: expense summary (كم صرفت)
- expense_list_recent: recent expenses
- health_log_entry: log sleep/exercise/weight/water. Use when user says نمت/مشيت/وزني
- health_get_summary: health summary for N days
- trade_log_entry: log buy/sell/close trade. Include ticker+action at minimum
- trade_get_journal: trade journal with stats
- tv_watchlist_add: add stock to TradingView watchlist
- tv_watchlist_list: list TradingView watchlist
- tv_last_signal: last TradingView signal for ticker
- tv_signal_summary: signal summary (day/week) (آخر مصاريف)
- hours=24 for today, hours=48 for yesterday too, hours=168 for this week
- IMPORTANT: You have FULL access to Google Calendar. You can read, create, and delete events. Always use calendar tools when asked about appointments or schedule.
- ssh_run: safe commands only. No rm -rf, no reboot without asking

SCENES:
- طفي كل شي=scene.tfwy_kl_shy | مغادرة=scene.mgdr_lbyt | صباح الخير=scene.sbh_lkhyr
- افتح الستائر=scene.fth_kl_lstyr | سكر الستائر=scene.skwr_kl_lstyr
- Bulk commands MUST use scenes, not individual tool calls

ALIASES:
- عبود/عبودي/الولد=عبدالله(son, 4 Feb 2025) | عائشة/عيوشة/البنت=عائشة(daughter)
- أوانا/زوجتي/أم عبود=Oana(wife) | ناهد/أمي/أم سالم=ناهد(mother, room=غرفة ماما)

DATES (Kuwaiti):
- اليوم=today | باجر=tomorrow | عقب باجر=day after | أمس=yesterday | أول أمس=2 days ago
- الحين/هسه=now | هالأسبوع=this week | الياي=next
- Calculate Gregorian dates yourself, then call get_shift. Never ask "which date?"

ISLAMIC DATES:
{islamic_dates}

EXECUTION POLICY:
- Read/status/info: execute immediately
- Lights/AC/scenes: execute immediately
- Delete/settings/restart: ASK first
- Factory reset/mass changes: REFUSE

SESSION: Each message is independent. Use tools for ALL info — never assume from past messages.
"""

# ── Smart Model Routing ─────────────────────────────────────
import re as _model_re

from model_tiers import MODEL_ROUTINE, MODEL_DEEP

MODEL_MAP = {
    "sonnet": MODEL_ROUTINE,
    "opus": MODEL_DEEP,
}

# Opus for: reasoning, dates, memory, follow-up, Hijri, calculations
# TODO: These patterns are unused while choose_model() always returns "sonnet".
# Re-enable when smart model routing is implemented.
_OPUS_PATTERNS = [
    _model_re.compile(r"(?:ليش|لماذا|فسر|اشرح|حلل|قارن|استنتج|رتب|خطط)", _model_re.I),
    _model_re.compile(r"(?:العيد|عيد|رمضان|هجري|ميلادي)", _model_re.I),
    _model_re.compile(r"(?:احسب|تذكر|تتذكر|عبود|اربعين|الاربعين)", _model_re.I),
    _model_re.compile(r"(?:مولود|ميلاد|عمر|زوجتي|ولادة|حامل)", _model_re.I),
    _model_re.compile(r"(?:كم عمر|متى تخلص|متى ينتهي)", _model_re.I),
]

# Sonnet for: device control, simple status, greetings
_SONNET_PATTERNS = [
    _model_re.compile(r"(?:شغل|طفي|سكر|افتح|شغللي|طفي|فعل|عطل)", _model_re.I),
    _model_re.compile(r"(?:مرحبا|هلا|السلام|صباح|مساء)", _model_re.I),
    _model_re.compile(r"(?:دوامي|ورديتي|شفتي|شفت|اجازة|اجازتي)", _model_re.I),
    _model_re.compile(r"(?:كم يوم|كم باقي|متى اجازتي)", _model_re.I),
    _model_re.compile(r"(?:حالة|حرارة|أنوار|ستاير|ستائر|أجهزة|مكيف)", _model_re.I),
]

def choose_model(text, followup_hint=None):
    """Always Sonnet first. Opus only via self_check retry (Phase 2 cost optimization)."""
    return "sonnet"


TOOLS = [
    {
        "name": "ha_get_state",
        "description": "Get Home Assistant entity state. entity_id='*' for ALL, or patterns: 'climate.*', 'light.*living*', 'camera.*', 'automation.*', 'cover.*', 'lock.*'",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity ID or pattern. '*'=all, 'climate.*'=ACs, 'automation.*'=automations"}
            },
            "required": ["entity_id"]
        }
    },
    {
        "name": "ha_call_service",
        "description": "Call HA service. Controls: lights, ACs, covers(INVERTED!), automations, scenes, locks, fans(شفاط/منقي/معطر).",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "service": {"type": "string"},
                "service_data": {"type": "object"}
            },
            "required": ["domain", "service", "service_data"]
        }
    },
    {
        "name": "ssh_run",
        "description": "Run shell command on RPi. For: system health, logs, services, network diagnostics.",
        "input_schema": {
            "type": "object",
            "properties": {"cmd": {"type": "string"}},
            "required": ["cmd"]
        }
    },
    {
        "name": "http_request",
        "description": "HTTP request. Internal: localhost:9000/health, /brain/stats, /brain/expertise?domain=X, /system/knowledge",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "method": {"type": "string", "default": "GET"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "memory_search",
        "description": "Search long-term memory for stored facts, preferences, past decisions. Use when user asks about something you should remember.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query in Arabic or English"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "memory_save",
        "description": "Save important fact/preference to long-term memory. Use when user tells you something to remember.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The fact to remember"},
                "category": {"type": "string", "enum": ["preference","fact","decision","routine"], "default": "fact"}
            },
            "required": ["content"]
        }
    },
    {
        "name": "get_weather",
        "description": "Get current weather in Kuwait. Returns temperature, humidity, wind, conditions.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_shift",
        "description": "Get work shift schedule for Salem (Unit 114 Hydrocracker, KNPC). Pattern: AABBCCDD. Returns current shift or for a date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD format. Empty=today."},
                "date_end": {"type": "string", "description": "YYYY-MM-DD end date for range query."}
            }
        }
    }
    ,{"name": "get_system_info", "description": "Get RPi system info.", "input_schema": {"type": "object", "properties": {}}}
    ,{"name": "calendar_list_events", "description": "List calendar events. range_type: today/tomorrow/week/custom. For custom, provide start_iso and end_iso.", "input_schema": {"type": "object", "properties": {"range_type": {"type": "string", "description": "today|tomorrow|week|custom"}, "start_iso": {"type": "string", "description": "ISO date for custom range start"}, "end_iso": {"type": "string", "description": "ISO date for custom range end"}}, "required": ["range_type"]}}
    ,{"name": "calendar_create_event", "description": "Create a new calendar event in Google Calendar. Use ISO format for dates.", "input_schema": {"type": "object", "properties": {"title": {"type": "string"}, "start_iso": {"type": "string", "description": "ISO datetime e.g. 2026-03-20T19:00:00"}, "end_iso": {"type": "string", "description": "ISO datetime e.g. 2026-03-20T20:00:00"}, "location": {"type": "string"}, "description": {"type": "string"}, "is_all_day": {"type": "boolean"}}, "required": ["title", "start_iso", "end_iso"]}}
    ,{"name": "calendar_delete_event", "description": "Delete a calendar event by searching for matching title.", "input_schema": {"type": "object", "properties": {"title_search": {"type": "string", "description": "Part of event title to find and delete"}}, "required": ["title_search"]}}
    ,{"name": "task_list", "description": "List personal/work tasks. Filter by status (todo/in_progress/done), category (personal/work), due_today or due_overdue.", "input_schema": {"type": "object", "properties": {"status": {"type": "string", "description": "todo|in_progress|done|cancelled"}, "category": {"type": "string", "description": "personal|work"}, "due_today": {"type": "boolean"}, "due_overdue": {"type": "boolean"}, "limit": {"type": "integer", "default": 20}}}}
    ,{"name": "task_create", "description": "Create a new task for the user. category=personal or work.", "input_schema": {"type": "object", "properties": {"title": {"type": "string"}, "category": {"type": "string", "description": "personal|work", "default": "personal"}, "priority": {"type": "string", "description": "high|med|low", "default": "med"}, "due_date": {"type": "string", "description": "YYYY-MM-DD"}, "description": {"type": "string"}}, "required": ["title"]}}
    ,{"name": "task_update", "description": "Update a task status, priority, due_date, or title by task_id.", "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}, "status": {"type": "string", "description": "todo|in_progress|done|cancelled"}, "priority": {"type": "string"}, "due_date": {"type": "string"}, "title": {"type": "string"}}, "required": ["task_id"]}}
    ,{"name": "relationship_lookup", "description": "Look up a person and their occasions/notes. Use for birthday, info queries.", "input_schema": {"type": "object", "properties": {"name": {"type": "string", "description": "Person name"}}, "required": ["name"]}}
    ,{"name": "relationship_add", "description": "Add person/occasion/note. action=add_contact|add_occasion|add_note", "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "name": {"type": "string"}, "relationship_type": {"type": "string"}, "birth_date": {"type": "string"}, "aliases": {"type": "string"}, "occasion_title": {"type": "string"}, "occasion_date": {"type": "string"}, "occasion_type": {"type": "string"}, "note_text": {"type": "string"}, "note_type": {"type": "string"}}, "required": ["action", "name"]}}
    ,{"name": "relationship_upcoming", "description": "List upcoming occasions in next N days.", "input_schema": {"type": "object", "properties": {"days": {"type": "integer", "default": 30}}}}
    ,{"name": "expense_add_entry", "description": "Add expense. amount+category required.", "input_schema": {"type": "object", "properties": {"amount": {"type": "number"}, "category": {"type": "string", "description": "restaurant|coffee|groceries|fuel|pharmacy|shopping|kids|bills|transport|misc"}, "note": {"type": "string"}}, "required": ["amount", "category"]}}
    ,{"name": "expense_get_summary", "description": "Get expense summary for period.", "input_schema": {"type": "object", "properties": {"period": {"type": "string", "description": "today|week|month"}}, "required": ["period"]}}
    ,{"name": "expense_list_recent", "description": "List recent expenses.", "input_schema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 10}}}}
    ,{"name": "health_log_entry", "description": "Log health data: sleep hours, exercise minutes, weight kg, water cups.", "input_schema": {"type": "object", "properties": {"log_type": {"type": "string", "description": "sleep|exercise|weight|water"}, "value": {"type": "number"}, "unit": {"type": "string"}, "note": {"type": "string"}, "log_date": {"type": "string"}}, "required": ["log_type", "value"]}}
    ,{"name": "health_get_summary", "description": "Get health summary for last N days.", "input_schema": {"type": "object", "properties": {"days": {"type": "integer", "default": 7}}}}
    ,{"name": "trade_log_entry", "description": "Log a trade. action: buy/sell/close.", "input_schema": {"type": "object", "properties": {"ticker": {"type": "string"}, "action": {"type": "string"}, "shares": {"type": "integer"}, "price": {"type": "number"}, "strategy": {"type": "string"}, "reason": {"type": "string"}, "emotion": {"type": "string"}, "outcome": {"type": "string"}, "pnl": {"type": "number"}, "review": {"type": "string"}, "trade_date": {"type": "string"}}, "required": ["ticker", "action"]}}
    ,{"name": "trade_get_journal", "description": "Trade journal with stats.", "input_schema": {"type": "object", "properties": {"days": {"type": "integer", "default": 30}, "ticker": {"type": "string"}}}}
    ,{"name": "tv_watchlist_add", "description": "Add stock to TradingView watchlist.", "input_schema": {"type": "object", "properties": {"ticker": {"type": "string"}, "strategy_name": {"type": "string"}, "label": {"type": "string"}, "notes": {"type": "string"}}, "required": ["ticker"]}}
    ,{"name": "tv_watchlist_list", "description": "List TradingView watchlist.", "input_schema": {"type": "object", "properties": {"active_only": {"type": "boolean", "default": True}}}}
    ,{"name": "tv_last_signal", "description": "Get last TradingView signal for ticker.", "input_schema": {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]}}
    ,{"name": "tv_signal_summary", "description": "TradingView signal summary.", "input_schema": {"type": "object", "properties": {"period": {"type": "string", "description": "day|week|month"}, "ticker": {"type": "string"}}}}
    ,{"name": "get_stock_price", "description": "Get real-time KSE stock price from TradingView. Accepts Arabic or English names: كلينينق=CLEANING, بيتك=KFH, زين=ZAIN, etc.", "input_schema": {"type": "object", "properties": {"symbol": {"type": "string", "description": "Stock ticker or Arabic name"}}, "required": ["symbol"]}}
    ,{"name": "analyze_stock", "description": "Full technical analysis for KSE stock: RSI, EMA, VWAP, MACD, support/resistance, trend, volume, verdict (BUY/SELL/HOLD). Zero LLM cost.", "input_schema": {"type": "object", "properties": {"symbol": {"type": "string", "description": "Stock ticker or Arabic name"}}, "required": ["symbol"]}}
    ,{"name": "get_trading_advice", "description": "AI trading advisor opinion on KSE stock. Combines technical analysis + user strategies (CLEANING V3, SENERGY V5) + LLM judgment. Returns entry/exit/SL recommendations.", "input_schema": {"type": "object", "properties": {"symbol": {"type": "string", "description": "Stock ticker or Arabic name"}, "question": {"type": "string", "description": "Specific question about the stock"}}, "required": ["symbol"]}}
    ,{"name": "top_traded_stocks", "description": "Get top 10 most traded KSE stocks today by volume. Shows price, change%, and volume for each.", "input_schema": {"type": "object", "properties": {"count": {"type": "integer", "description": "Number of stocks to show (default 10)", "default": 10}}}}
]
if _SMEM: TOOLS.extend(smem.MEMORY_TOOLS)


async def execute_tool(name, args, executors):
    try:
        # v8 Phase 2: Task tools
        if name == "task_list":
            from tg_tasks import llm_tool_task_list
            return llm_tool_task_list(**args)
        if name == "task_create":
            from tg_tasks import llm_tool_task_create
            return llm_tool_task_create(**args)
        if name == "task_update":
            from tg_tasks import llm_tool_task_update
            return llm_tool_task_update(**args)
        # v8 Phase 3: Relationship tools
        if name == "relationship_lookup":
            from relationships_engine import build_contact_snapshot, format_person_tg
            snap = build_contact_snapshot(args.get("name", ""))
            if not snap: return {"ok": False, "error": f"Person not found"}
            return {"ok": True, "snapshot": format_person_tg(snap)}
        if name == "relationship_add":
            from relationships_engine import find_contact, add_contact, add_occasion, add_note
            act = args.get("action", ""); pn = args.get("name", "")
            if act == "add_contact":
                al = args.get("aliases","").split(",") if args.get("aliases") else None
                return add_contact(pn, display_name=pn, relationship_type=args.get("relationship_type"), aliases=al, birth_date=args.get("birth_date"))
            elif act == "add_occasion":
                ct = find_contact(pn); cid = ct["id"] if ct else None
                return add_occasion(title=args.get("occasion_title",f"occasion {pn}"), occasion_date=args.get("occasion_date",""), occasion_type=args.get("occasion_type","custom"), contact_id=cid)
            elif act == "add_note":
                ct = find_contact(pn)
                if not ct: return {"ok": False, "error": f"Person not found"}
                return add_note(ct["id"], args.get("note_text",""), args.get("note_type","fact"))
            return {"ok": False, "error": f"Unknown action: {act}"}
        if name == "relationship_upcoming":
            from relationships_engine import get_upcoming_occasions, format_upcoming_tg
            return {"ok": True, "text": format_upcoming_tg(get_upcoming_occasions(args.get("days",30)))}
        # v8 Phase 4: Expense tools
        if name == "expense_add_entry":
            from expenses_engine import add_expense, format_add_confirmation
            return add_expense(args.get("amount",0), args.get("category","misc"), args.get("note"))
        if name == "expense_get_summary":
            from expenses_engine import get_summary, format_summary_tg
            return {"ok": True, "text": format_summary_tg(get_summary(args.get("period","today")))}
        if name == "expense_list_recent":
            from expenses_engine import list_expenses, format_recent_tg
            return {"ok": True, "text": format_recent_tg(list_expenses(args.get("limit",10)))}
        # Phase 5: Health tools
        if name == "health_log_entry":
            from health_engine import llm_tool_health_log
            return llm_tool_health_log(args.get("log_type"), args.get("value"), args.get("unit"), args.get("note"), args.get("log_date"))
        if name == "health_get_summary":
            from health_engine import llm_tool_health_summary
            return llm_tool_health_summary(args.get("days", 7))
        # Phase 5: Trading tools
        if name == "trade_log_entry":
            from trading_engine import llm_tool_trade_log
            return llm_tool_trade_log(args.get("ticker"), args.get("action"), args.get("shares"), args.get("price"), args.get("strategy"), args.get("reason"), args.get("emotion"), args.get("outcome"), args.get("pnl"), args.get("review"), args.get("trade_date"))
        if name == "trade_get_journal":
            from trading_engine import llm_tool_trade_journal
            return llm_tool_trade_journal(args.get("days", 30), args.get("ticker"))

        # Phase 6: TradingView tools
        if name == "tv_watchlist_add":
            from tradingview_bridge import llm_tool_tv_watchlist_add
            return llm_tool_tv_watchlist_add(args.get("ticker"), args.get("strategy_name"), args.get("label"), args.get("notes"))
        if name == "tv_watchlist_list":
            from tradingview_bridge import llm_tool_tv_watchlist_list
            return llm_tool_tv_watchlist_list(args.get("active_only", True))
        if name == "tv_last_signal":
            from tradingview_bridge import llm_tool_tv_last_signal
            return llm_tool_tv_last_signal(args.get("ticker"))
        if name == "tv_signal_summary":
            from tradingview_bridge import llm_tool_tv_signal_summary
            return llm_tool_tv_signal_summary(args.get("period", "day"), args.get("ticker"))

        # Phase 7: Real-time stock data + analysis
        if name == "get_stock_price":
            from tv_data import get_price
            result = get_price(args.get("symbol", ""))
            return json.dumps(result, ensure_ascii=False, default=str)
        if name == "analyze_stock":
            from tv_data import get_price
            from tv_analysis import full_analysis, format_analysis_arabic
            price_data = get_price(args.get("symbol", ""))
            if "error" in price_data:
                return json.dumps(price_data, ensure_ascii=False)
            analysis = full_analysis(price_data)
            analysis["formatted"] = format_analysis_arabic(analysis)
            return json.dumps(analysis, ensure_ascii=False, default=str)
        if name == "get_trading_advice":
            from tv_data import get_price
            from tv_analysis import full_analysis, format_analysis_arabic
            from tv_advisor import build_advisor_prompt, format_advisor_response
            import anthropic as _anth
            price_data = get_price(args.get("symbol", ""))
            if "error" in price_data:
                return json.dumps(price_data, ensure_ascii=False)
            analysis = full_analysis(price_data)
            advisor_prompt = build_advisor_prompt(analysis, args.get("question", ""))
            try:
                import os as _os, asyncio as _aio
                def _sync_advisor():
                    _client = _anth.Anthropic(api_key=_os.getenv("ANTHROPIC_API_KEY", ""))
                    return _client.messages.create(
                        model=MODEL_ROUTINE, max_tokens=500,
                        messages=[{"role": "user", "content": advisor_prompt}])
                _resp = await _aio.to_thread(_sync_advisor)
                _advice = _resp.content[0].text
                try:
                    from cost_tracker import track_cost
                    track_cost(_resp.usage, MODEL_ROUTINE, source="advisor")
                except Exception:
                    pass
            except Exception as _ae:
                logger.warning(f"Advisor LLM error: {_ae}")
                _advice = analysis.get("verdict", "N/A")
            return format_advisor_response(analysis, _advice)
        if name == "top_traded_stocks":
            from tv_data import get_top_volume, format_top_volume_arabic
            count = args.get("count", 10)
            stocks = get_top_volume(count)
            return format_top_volume_arabic(stocks)
        # Phase 3: Policy + Tracking
        if _EXEC_POLICY:
            track_session("default", name)
            _ok, _rsn = check_policy(name, args)
            if not _ok:
                return json.dumps({"error": _rsn, "blocked": True})
        # Confidence scoring
        if _CONF_ENGINE:
            _cscore = score_tool_call(name, args)
            if _cscore["level"] == "low" and name in ("ha_call_service","ssh_run"):
                logger.warning(f"Low confidence: {name} {_cscore}")
                if _APPROVAL_UX:
                    _appr = format_approval_message(name, args, _cscore)
                    return json.dumps({"needs_approval": True, "approval_message": _appr["message"], "action_summary": _appr["action_summary"], "reversible": _appr["reversible"], "confidence": _cscore})
                return json.dumps({"error": "Low confidence", "confidence": _cscore})
        if name == "ha_get_state":
            r = await executors["ha_get_state"](args["entity_id"])
            r_enriched = enrich_ha_state(args["entity_id"], r) if _SMART_TOOLS else r
            return json.dumps(r_enriched, ensure_ascii=False, default=str)[:8000]
        elif name == "ha_call_service":
            r = await executors["ha_call_service"](args["domain"], args["service"], args.get("service_data", {}))
            return _safe_json_truncate(r, 4000)
        elif name == "ssh_run":
            r = await executors["ssh_run"](args["cmd"])
            return _safe_json_truncate(r, 4000)
        elif name == "http_request":
            from urllib.parse import urlparse as _urlparse
            _parsed = _urlparse(args["url"])
            _allowed_hosts = ("localhost", "127.0.0.1", "192.168.109.123")
            _allowed_ports = (8123, 9000, None)
            if _parsed.hostname not in _allowed_hosts or _parsed.port not in _allowed_ports:
                return json.dumps({"error": "URL not allowed - only internal hosts permitted"})
            if _parsed.scheme not in ("http", "https"):
                return json.dumps({"error": "Invalid URL scheme"})
            import httpx
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as c:
                resp = await c.request(args.get("method", "GET"), args["url"])
                return resp.text[:4000]
        elif name == "memory_search":
            try:
                from memory_db import get_memories
                mems = await get_memories(search=args["query"], limit=5)
                if mems:
                    return json.dumps([{"content": m["content"], "category": m.get("category","")} for m in mems], ensure_ascii=False)
                return json.dumps({"result": "nothing found"})
            except Exception as e:
                return json.dumps({"error": str(e)})
        elif name == "memory_save":
            try:
                from memory_db import save_memory_with_facts
                await save_memory_with_facts(args.get("category","fact"), args["content"], source="chat_v7")
                return json.dumps({"saved": True})
            except Exception as e:
                return json.dumps({"error": str(e)})
        elif name == "get_weather":
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10) as c:
                    resp = await c.get("https://api.open-meteo.com/v1/forecast?latitude=29.3759&longitude=47.9774&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code&timezone=Asia/Kuwait")
                    w = resp.json().get("current", {})
                    return json.dumps({"temp": w.get("temperature_2m"), "humidity": w.get("relative_humidity_2m"), "wind_kmh": w.get("wind_speed_10m"), "code": w.get("weather_code")}, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"error": str(e)})
        elif name == "get_shift":
            try:
                from life_work import get_shift_display, get_shift
                from datetime import date, timedelta
                d_start = None
                if args.get("date"):
                    p = args["date"].split("-")
                    d_start = date(int(p[0]), int(p[1]), int(p[2]))
                if args.get("date_end"):
                    p2 = args["date_end"].split("-")
                    d_end = date(int(p2[0]), int(p2[1]), int(p2[2]))
                    results = []
                    d = d_start or date.today()
                    while d <= d_end:
                        s = get_shift(d)
                        wd = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][d.weekday()]
                        results.append({"date": str(d), "day": wd, "shift": s["shift"], "position": s.get("position","")})
                        d += timedelta(days=1)
                    return json.dumps(results, ensure_ascii=False, default=str)
                result = get_shift_display(d_start)
                result = enrich_shift_result(result) if _SMART_TOOLS else result
                return json.dumps(result, ensure_ascii=False, default=str)
            except Exception as e:
                return json.dumps({"error": str(e)})
        # Structured Memory tools
        elif name.startswith("memory_") and _SMEM:
            r = smem.execute_memory_tool(name, args)
            return _safe_json_truncate(r, 4000)
        elif name == "get_system_info":
            import asyncio as _aio
            def _sync_sysinfo():
                import subprocess as _sp
                _i = {}
                try:
                    _i["cpu"] = _sp.getoutput("top -bn1 | grep Cpu | awk '{print $2}'")
                    _mp = _sp.getoutput("free -m").split(chr(10))[1].split()
                    _i["ram"] = _mp[2]+"/"+_mp[1]+"MB"
                    _dk = _sp.getoutput("df -h /").split(chr(10))[1].split()
                    _i["disk"] = _dk[2]+"/"+_dk[1]+" ("+_dk[4]+")"
                    _t = _sp.getoutput("cat /sys/class/thermal/thermal_zone0/temp")
                    _i["temp"] = str(round(int(_t)/1000,1))+"C" if _t.strip().isdigit() else "?"
                    _i["uptime"] = _sp.getoutput("uptime -p")
                    _i["git"] = _sp.getoutput("cd /home/pi/master_ai && git log --oneline -1")
                except Exception as _e:
                    _i["error"] = str(_e)
                return _i
            _info = await _aio.to_thread(_sync_sysinfo)
            return json.dumps(_info, ensure_ascii=False)
        elif name == "calendar_list_events":
            from calendar_engine import get_today_events, get_tomorrow_events, get_week_events, get_events_range
            from calendar_reporting import render_today, render_tomorrow, render_week
            rt = args.get("range_type", "today")
            if rt == "today": result = render_today(get_today_events())
            elif rt == "tomorrow": result = render_tomorrow(get_tomorrow_events())
            elif rt == "week": result = render_week(get_week_events())
            elif rt == "custom" and args.get("start_iso") and args.get("end_iso"):
                evs = get_events_range(args["start_iso"], args["end_iso"])
                result = json.dumps([{"s": e.get("summary"), "start": e["start_ts"], "loc": e.get("location")} for e in evs], ensure_ascii=False)
            else: result = render_today(get_today_events())
            return result
        elif name == "calendar_create_event":
            from calendar_engine import create_event
            r = await create_event(title=args["title"], start_iso=args["start_iso"], end_iso=args["end_iso"], location=args.get("location"), description=args.get("description"), is_all_day=args.get("is_all_day", False))
            return json.dumps(r, ensure_ascii=False)
        elif name == "calendar_delete_event":
            from calendar_engine import get_week_events, delete_event
            search = args.get("title_search", "").lower()
            found = [e for e in get_week_events() if search in (e.get("summary","") or "").lower()]
            if not found: return json.dumps({"error": f"No event matching '{search}'"})
            ev = found[0]
            r = await delete_event(ev["google_event_id"])
            r["deleted"] = ev.get("summary")
            return json.dumps(r, ensure_ascii=False)
        return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as e:
        _err = json.dumps({"error": str(e)})
        if _EXEC_POLICY: record_outcome(name, _err)
        return _err

async def _prepare_chat_context(user_text, system_prompt, user_id):
    """Shared context preparation for both chat handlers.
    Returns (enriched_system_prompt, enriched_user_text, selected_model)."""

    # 1. Inject dynamic TODAY date + Islamic dates
    from datetime import datetime as _dt
    _today_str = _dt.now().strftime("TODAY: %A %d %B %Y, %H:%M Kuwait time")
    try:
        from brain_core import get_islamic_dates_context
        _islamic = get_islamic_dates_context()
    except Exception:
        _islamic = ""
    _dates_block = _today_str + chr(10) + _islamic
    _v7 = V8_SYSTEM_OVERRIDE.replace("{islamic_dates}", _dates_block)
    system_prompt = system_prompt + _v7

    # 2. World state snapshot
    try:
        from world_state import get_snapshot_text
        try:
            from world_state_delta import get_delta_text
            _delta = get_delta_text()
            _ws = _delta if _delta else get_snapshot_text()
        except ImportError:
            _ws = get_snapshot_text()
        if _ws:
            system_prompt = system_prompt + chr(10)*2 + _ws
    except Exception:
        pass

    # 3. Structured Memory context
    if _SMEM:
        try:
            _mem_ctx = smem.get_context_for_llm(user_text)
            if _mem_ctx:
                system_prompt = system_prompt + chr(10)*2 + _mem_ctx
        except Exception:
            pass

    # 4. Corrections Learning Loop context
    if _CORRECTIONS:
        try:
            _corr_ctx = _get_correction_context()
            if _corr_ctx:
                system_prompt = system_prompt + chr(10)*2 + _corr_ctx
                logger.info("Corrections context injected")
        except Exception:
            pass

    # 5. Model selection
    _tier = choose_model(user_text)
    model = MODEL_MAP.get(_tier, MODEL_MAP["sonnet"])
    logger.info(f"Model: {_tier} for: {user_text[:40]}")

    # 6. Apply stored corrections to user text
    enriched_text = user_text
    if _CORRECTIONS:
        try:
            _corrected_text, _applied = _apply_corrections(user_text)
            if _applied:
                logger.info(f"Applied {len(_applied)} corrections")
                enriched_text = _corrected_text
        except Exception:
            pass

    # 7. Auto-inject relevant memories
    try:
        from memory_db import search_memory_smart
        _mems = await search_memory_smart(enriched_text, limit=5)
        if _mems:
            _ml = [m["content"] for m in _mems if m.get("content")]
            if _ml:
                enriched_text = enriched_text + chr(10) + "[Memory: " + " | ".join(_ml[:5]) + "]"
                logger.info(f"Memory injected: {len(_ml)} items")
    except Exception:
        pass

    return system_prompt, enriched_text, model


async def handle_chat_v7(user_text, system_prompt, client, executors, model=None, max_tokens=4096, user_id="default"):
    t0 = time.time()
    # Shared context preparation (world state, memory, corrections, model)
    if model is None:
        system_prompt, _enriched, model = await _prepare_chat_context(user_text, system_prompt, user_id)
    else:
        system_prompt, _enriched, _ = await _prepare_chat_context(user_text, system_prompt, user_id)
    # Build messages with conversation history (lock to prevent race)
    async with _get_user_lock(user_id):
        history = _conversations[user_id]
    history.append({"role": "user", "content": _enriched})
    messages = list(history)  # copy for this request
    # Context management: trim/compress if too large (Tier3 #15)
    if _CTX_MGR_OK and len(messages) > 12:
        try:
            messages = await _manage_ctx(messages, anthropic_client=client)
        except Exception:
            pass
    tools_used = []
    tool_results = []

    for _ in range(MAX_ROUNDS):
        try:
            resp = await client.messages.create(
                model=model, max_tokens=max_tokens, system=system_prompt,
                messages=messages, tools=TOOLS, temperature=0.3
            )
            # Cost tracking
            if _COST_TRACK:
                try: track_cost(resp.usage, model, user_id)
                except: pass
        except Exception as e:
            err_str = str(e)
            if "usage limits" in err_str or "rate_limit" in err_str or "overloaded" in err_str or "429" in err_str:
                logger.warning(f"Anthropic limit hit, trying OpenAI fallback: {err_str[:80]}")
                oi = _init_openai()
                if oi:
                    try:
                        oai_msgs = [{"role": "system", "content": system_prompt}]
                        for m in messages:
                            if m["role"] == "user":
                                if isinstance(m["content"], list):
                                    oai_msgs.append({"role": "user", "content": json.dumps(m["content"], ensure_ascii=False)[:3000]})
                                else:
                                    oai_msgs.append({"role": "user", "content": str(m["content"])[:3000]})
                            elif m["role"] == "assistant":
                                if isinstance(m["content"], list):
                                    txt = " ".join(getattr(b, "text", "") for b in m["content"] if hasattr(b, "text"))
                                    if txt: oai_msgs.append({"role": "assistant", "content": txt})
                                else:
                                    oai_msgs.append({"role": "assistant", "content": str(m["content"])[:3000]})
                        oai_funcs = _tools_to_openai_functions()
                        for _oai_round in range(MAX_ROUNDS):
                            oai_resp = await oi.chat.completions.create(
                                model="gpt-4o", max_tokens=max_tokens, temperature=0.3,
                                messages=oai_msgs, tools=oai_funcs
                            )
                            # Cost tracking (OpenAI)
                            if _COST_TRACK and hasattr(oai_resp, "usage") and oai_resp.usage:
                                try: track_cost_openai(dict(oai_resp.usage), "gpt-4o", user_id)
                                except: pass
                            choice = oai_resp.choices[0]
                            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                                oai_msgs.append(choice.message)
                                for tc in choice.message.tool_calls:
                                    fn = tc.function
                                    args = json.loads(fn.arguments) if fn.arguments else {}
                                    logger.info(f"OpenAI tool: {fn.name}({json.dumps(args, ensure_ascii=False)[:60]})")
                                    tools_used.append(fn.name)
                                    result = await execute_tool(fn.name, args, executors)
                                    oai_msgs.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                            else:
                                final = choice.message.content or ""
                                history.append({"role": "assistant", "content": final})
                                logger.info(f"OpenAI fallback: {len(tools_used)} tools, {time.time()-t0:.1f}s, user={user_id}")
                                if len(tools_used) >= 3:
                                    try:
                                        from memory_db import save_memory_with_facts
                                        _summary = f"Session {time.strftime('%Y-%m-%d %H:%M')}: User asked '{user_text[:60]}', used tools: {', '.join(set(tools_used))} [OpenAI]"
                                        await save_memory_with_facts("session_log", _summary, user_id)
                                    except Exception:
                                        pass
                                
                                # Trace + self-check (OpenAI path)
                                if _PLANNER:
                                    try:
                                        _intent = classify_intent(user_text)
                                        save_trace({"msg_id": str(int(time.time()*1000)), "user_text": user_text, "intent_type": _intent["type"], "compound": _intent["compound"], "model": "openai-fallback", "tools_used": list(set(tools_used)), "tools_count": len(tools_used), "self_check_ok": True, "final_status": "ok", "response_len": len(final), "elapsed_ms": round((time.time()-t0)*1000, 1), "user_id": user_id})
                                    except Exception:
                                        pass
                                return final
                        return "OpenAI fallback: max rounds"
                    except Exception as oe:
                        logger.error(f"OpenAI fallback failed: {oe}")
                        return f"خطأ (Anthropic + OpenAI): {err_str[:60]}"
            logger.error(f"chat_v7 LLM error: {e}")
            return f"خطأ: {e}"
        
        if resp.stop_reason == "tool_use":
            tool_blocks = []
            for block in resp.content:
                if block.type == "tool_use":
                    logger.info(f"chat_v7 tool: {block.name}({json.dumps(block.input, ensure_ascii=False)[:80]})")
                    tools_used.append(block.name)
                    tool_blocks.append((block.name, block.input, block.id))
            if _TOOL_CACHE and len(tool_blocks) > 0:
                tool_results = await execute_tools_parallel(tool_blocks, execute_tool, executors)
            else:
                tool_results = []
                for name, args, tid in tool_blocks:
                    result = await execute_tool(name, args, executors)
                    tool_results.append({"type": "tool_result", "tool_use_id": tid, "content": result})
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content": tool_results})
        
        elif resp.stop_reason == "end_turn":
            parts = [b.text for b in resp.content if hasattr(b, "text")]
            final = "\n".join(parts)
            # V7: Strip any accidental JSON wrapping
            if final.strip().startswith("{") and '"response"' in final:
                try:
                    parsed = json.loads(final.strip().strip("`").replace("json\n","").replace("json",""))
                    if "response" in parsed:
                        final = parsed["response"]
                except (json.JSONDecodeError, KeyError):
                    pass
            # Save to conversation history
            history.append({"role": "assistant", "content": final})
            logger.info(f"chat_v7: {len(tools_used)} tools, {time.time()-t0:.1f}s, {len(final)} chars, user={user_id}")
            # Auto-save session context if complex interaction (3+ tools)
            if len(tools_used) >= 3:
                try:
                    from memory_db import save_memory_with_facts
                    _summary = f"Session {time.strftime('%Y-%m-%d %H:%M')}: User asked '{user_text[:60]}', used tools: {', '.join(set(tools_used))}"
                    await save_memory_with_facts("session_log", _summary, user_id)
                    logger.info(f"Session summary saved: {len(tools_used)} tools")
                except Exception as _se:
                    logger.debug(f"Session save skip: {_se}")
            # Self-check + Tool outcome memory
            if _SELF_CHECK:
                try:
                    save_tool_outcomes(user_text, tools_used, tool_results)
                    save_session_summary(user_text, final, tools_used, user_id)
                    _chk = validate_answer(final, user_text, tools_used, tool_results)
                    if not _chk["ok"] and _chk["action"] == "retry" and model != MODEL_MAP["opus"]:
                        logger.warning(f"Self-check retry->Opus: {_chk.get('issues',[])}") 
                        model = MODEL_MAP["opus"]
                        messages = messages[:-1]  # remove last assistant response
                        if _COST_TRACK:
                            try: track_cost(resp.usage, MODEL_MAP["sonnet"], user_id, source="sonnet_attempt")
                            except: pass
                        continue  # retry with Opus
                except Exception as _sce:
                    logger.debug(f"Self-check skip: {_sce}")
            
            # Trace logging
            if _PLANNER:
                try:
                    _intent = classify_intent(user_text)
                    save_trace({"msg_id": str(int(time.time()*1000)), "user_text": user_text, "intent_type": _intent["type"], "compound": _intent["compound"], "model": model or "", "tools_used": list(set(tools_used)), "tools_count": len(tools_used), "self_check_ok": True, "final_status": "ok", "response_len": len(final), "elapsed_ms": round((time.time()-t0)*1000, 1), "user_id": user_id})
                except Exception as _te:
                    logger.warning(f"Trace save error: {_te}")
            # Corrections Learning Loop — detect user corrections
            if _CORRECTIONS:
                try:
                    _prev_ai = history[-2]['content'] if len(history) >= 2 else ''
                    _corr = _process_correction(user_text, _prev_ai)
                    if _corr:
                        logger.info(f"Correction detected: {_corr.get('wrong','')} → {_corr.get('right','')}")
                except Exception:
                    pass
            return final
        else:
            parts = [b.text for b in resp.content if hasattr(b, "text")]
            # Corrections Learning Loop — detect corrections (text-only path)
            if _CORRECTIONS:
                try:
                    _prev_ai = history[-2]["content"] if len(history) >= 2 else ""
                    _corr = _process_correction(user_text, _prev_ai)
                    if _corr:
                        logger.info(f"Correction detected (text path): {_corr.get('wrong','')} -> {_corr.get('right','')}")
                except Exception:
                    pass
            return "\n".join(parts) if parts else "ما قدرت أكمل"
    
    return "وصلت الحد الأقصى — جرب سؤال أبسط"


def clear_chat_v7_history(user_id: str = None):
    """Clear conversation history for a user or all users."""
    if user_id:
        _conversations.pop(user_id, None)
    else:
        _conversations.clear()


async def handle_chat_v7_stream(user_text, system_prompt, client, executors,
                                 tg_send_fn=None, tg_edit_fn=None, chat_id=None,
                                 model=None, max_tokens=4096, user_id="default"):
    """V7 with TG progressive reveal — shows response as it builds, handles tools between rounds."""
    import time as _time
    t0 = _time.time()

    # Shared context preparation (same as non-stream handler)
    if model is None:
        system_prompt, user_text, model = await _prepare_chat_context(user_text, system_prompt, user_id)
    else:
        system_prompt, user_text, _ = await _prepare_chat_context(user_text, system_prompt, user_id)

    async with _get_user_lock(user_id):
        history = _conversations[user_id]
        history.append({"role": "user", "content": user_text})
        messages = list(history)
    tools_used = []
    msg_id = None

    for round_num in range(MAX_ROUNDS):
        try:
            resp = await client.messages.create(
                model=model, max_tokens=max_tokens, system=system_prompt,
                messages=messages, tools=TOOLS, temperature=0.3
            )
            # Cost tracking (stream)
            if _COST_TRACK:
                try: track_cost(resp.usage, model, user_id, "stream")
                except: pass
        except Exception as e:
            logger.error(f"chat_v7_stream error: {e}")
            return f"\u062e\u0637\u0623: {e}"

        if resp.stop_reason == "tool_use":
            tool_blocks = []
            for block in resp.content:
                if block.type == "tool_use":
                    logger.info(f"v7stream tool: {block.name}")
                    tools_used.append(block.name)
                    tool_blocks.append((block.name, block.input, block.id))
            if _TOOL_CACHE and len(tool_blocks) > 0:
                tool_results = await execute_tools_parallel(tool_blocks, execute_tool, executors)
            else:
                tool_results = []
                for name, args, tid in tool_blocks:
                    result = await execute_tool(name, args, executors)
                    tool_results.append({"type": "tool_result", "tool_use_id": tid, "content": result})
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content": tool_results})
            continue

        if resp.stop_reason == "end_turn":
            parts = [b.text for b in resp.content if hasattr(b, "text")]
            final = "\n".join(parts)

            # Strip accidental JSON
            if final.strip().startswith("{") and '"response"' in final:
                try:
                    parsed = json.loads(final.strip().strip("`").replace("json\n",""))
                    if "response" in parsed:
                        final = parsed["response"]
                except Exception:
                    pass

            # Progressive reveal on TG
            if tg_send_fn and tg_edit_fn and chat_id and len(final) > 80:
                try:
                    chunk = max(60, len(final) // 4)
                    msg_id = await tg_send_fn(chat_id, final[:chunk] + " \u270d\ufe0f")
                    if msg_id:
                        import asyncio as _aio
                        for i in range(2, 5):
                            end = min(chunk * i, len(final))
                            if end >= len(final):
                                break
                            await _aio.sleep(0.4)
                            await tg_edit_fn(chat_id, msg_id, final[:end] + " \u270d\ufe0f")
                        await _aio.sleep(0.2)
                        await tg_edit_fn(chat_id, msg_id, final)
                except Exception as e:
                    logger.warning(f"v7stream TG edit err: {e}")

            history.append({"role": "assistant", "content": final})

            # Auto-save session context if complex interaction (3+ tools)
            if len(tools_used) >= 3:
                try:
                    from memory_db import save_memory_with_facts
                    _summary = f"Session {time.strftime('%Y-%m-%d %H:%M')}: User asked '{user_text[:60]}', used tools: {', '.join(set(tools_used))}"
                    await save_memory_with_facts("session_log", _summary, user_id)
                except Exception:
                    pass

            # Corrections detection
            if _CORRECTIONS:
                try:
                    _prev_ai = history[-2]['content'] if len(history) >= 2 else ''
                    _corr = _process_correction(user_text, _prev_ai)
                    if _corr:
                        logger.info(f"Correction detected (stream): {_corr.get('wrong','')} -> {_corr.get('right','')}")
                except Exception:
                    pass

            # Trace logging
            if _PLANNER:
                try:
                    _intent = classify_intent(user_text)
                    save_trace({"msg_id": str(int(time.time()*1000)), "user_text": user_text,
                                "intent_type": _intent["type"], "compound": _intent["compound"],
                                "model": model or "", "tools_used": list(set(tools_used)),
                                "tools_count": len(tools_used), "self_check_ok": True,
                                "final_status": "ok", "response_len": len(final),
                                "elapsed_ms": round((_time.time()-t0)*1000, 1), "user_id": user_id})
                except Exception:
                    pass

            elapsed = _time.time() - t0
            logger.info(f"v7stream: {len(tools_used)} tools, {elapsed:.1f}s, {len(final)}ch, u={user_id}")
            return final

        parts = [b.text for b in resp.content if hasattr(b, "text")]
        final = "\n".join(parts) if parts else "\u0645\u0627 \u0642\u062f\u0631\u062a \u0623\u0643\u0645\u0644"
        history.append({"role": "assistant", "content": final})
        return final

    return "\u0648\u0635\u0644\u062a \u0627\u0644\u062d\u062f \u0627\u0644\u0623\u0642\u0635\u0649"
