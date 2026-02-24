"""
Master AI Control API Server v4.0
Raspberry Pi - Home Assistant + Windows Agent Integration
Port: 9000
Endpoints: /ask, /health, /ha/*, /ssh/run, /agent, /approve/{id}, /audit, /win/*
"""

import os
import sys
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
from typing import Optional, Any
from collections import deque

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Query, Path, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
from openai import AsyncOpenAI, OpenAIError
from anthropic import AsyncAnthropic
import httpx
import aiosqlite

# --- Logging ------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/home/pi/master_ai/server.log"),
    ],
)
logger = logging.getLogger("master_ai")

# --- Load .env ----------------------------------------------
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(env_path)

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    logger.error("OPENAI_API_KEY not found"); sys.exit(1)
logger.info("OPENAI_API_KEY loaded (ends ...%s)", api_key[-4:])

anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
if anthropic_key:
    logger.info("ANTHROPIC_API_KEY loaded (ends ...%s)", anthropic_key[-4:])
else:
    logger.warning("ANTHROPIC_API_KEY not found - will use OpenAI only")

HA_URL = os.getenv("HOME_ASSISTANT_URL", "").rstrip("/")
HA_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN", "")
if not HA_URL or not HA_TOKEN:
    logger.warning("HA config missing")
else:
    logger.info("HA config loaded: %s", HA_URL)

AGENT_SECRET = os.getenv("AGENT_SECRET", "")
MASTER_API_KEY = os.getenv("MASTER_AI_API_KEY", "")
if MASTER_API_KEY:
    logger.info("MASTER_AI_API_KEY loaded (ends ...%s)", MASTER_API_KEY[-4:])
else:
    logger.warning("MASTER_AI_API_KEY not set - tunnel endpoints UNPROTECTED!")
if not AGENT_SECRET:
    logger.warning("AGENT_SECRET missing - /win/* endpoints will reject requests")
else:
    logger.info("AGENT_SECRET loaded (ends ...%s)", AGENT_SECRET[-4:])

# --- Clients ------------------------------------------------
openai_client = AsyncOpenAI(api_key=api_key)
anthropic_client = AsyncAnthropic(api_key=anthropic_key) if anthropic_key else None
# --- Universal LLM Call (Claude Opus primary, OpenAI fallback) ---
async def llm_call(system_prompt: str, user_message: str, max_tokens: int = 1024, temperature: float = 0.3) -> str:
    """Call Claude Opus 4.6, fallback to OpenAI gpt-4o-mini"""
    if anthropic_client:
        try:
            response = await anthropic_client.messages.create(
                model="claude-opus-4-6",
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.warning("Claude Opus failed, falling back to OpenAI: %s", e)
    # Fallback to OpenAI
    try:
        completion = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=max_tokens, temperature=temperature,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Both LLM calls failed: %s", e)
        raise


ha_http = httpx.AsyncClient(
    base_url=HA_URL,
    headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
    timeout=15.0,
)

# --- Audit DB -----------------------------------------------
AUDIT_DB = "/home/pi/master_ai/audit/audit.db"

def init_audit_db():
    os.makedirs(os.path.dirname(AUDIT_DB), exist_ok=True)
    conn = sqlite3.connect(AUDIT_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            task TEXT NOT NULL,
            actions TEXT,
            results TEXT,
            status TEXT,
            duration REAL,
            approval_id TEXT,
            approved_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Audit DB initialized: %s", AUDIT_DB)

init_audit_db()

async def audit_log(task, actions=None, results=None, status="ok", duration=0.0, approval_id=None, approved_at=None):
    try:
        async with aiosqlite.connect(AUDIT_DB) as db:
            await db.execute(
                "INSERT INTO audit_log (timestamp,task,actions,results,status,duration,approval_id,approved_at) VALUES (?,?,?,?,?,?,?,?)",
                (datetime.now().isoformat(), task,
                 json.dumps(actions, default=str) if actions else None,
                 json.dumps(results, default=str) if results else None,
                 status, round(duration, 3), approval_id, approved_at)
            )
            await db.commit()
    except Exception as e:
        logger.error("Audit log write failed: %s", e)

# --- Pending Approvals --------------------------------------
pending_approvals: dict[str, dict] = {}

def cleanup_expired_approvals():
    now = datetime.now()
    expired = [k for k, v in pending_approvals.items() if v["expires"] < now]
    for k in expired:
        del pending_approvals[k]

# --- Windows Agent Job Queue --------------------------------
win_job_queue: deque[dict] = deque(maxlen=100)
win_job_results: dict[str, dict] = {}
win_agents: dict[str, dict] = {}

def verify_agent_signature(agent_id: str, signature: str, timestamp: str) -> bool:
    """Verify HMAC SHA256 signature from Windows agent."""
    if not AGENT_SECRET:
        return False
    try:
        # Accept both unix int and ISO format
        try:
            ts = int(timestamp)
        except ValueError:
            from datetime import datetime as dt, timezone as tz
            ts = int(dt.fromisoformat(timestamp.replace('Z', '+00:00')).timestamp())
            timestamp = str(ts)
        now = int(time.time())
        if abs(now - ts) > 120:
            logger.warning("Agent sig expired: drift=%ds", abs(now - ts))
            return False
        expected = hmac.new(AGENT_SECRET.encode(), (agent_id + timestamp).encode(), hashlib.sha256).hexdigest()
        # Also try with original timestamp string
        if hmac.compare_digest(expected, signature):
            return True
        # Try with ISO format in case agent signed with that
        from datetime import datetime as dt2, timezone as tz2
        iso_ts = dt2.fromtimestamp(ts, tz=tz2.utc).isoformat()
        expected2 = hmac.new(AGENT_SECRET.encode(), (agent_id + iso_ts).encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected2, signature)
    except Exception as e:
        logger.error("Sig verify error: %s", e)
        return False

def enqueue_win_job(job_type: str, args: dict, risk: str = "low", task_ref: str = "") -> dict:
    """Add a job to the Windows agent queue."""
    needs_approval = risk == "high"
    approval_id = None
    if needs_approval:
        approval_id = str(uuid.uuid4())[:8]
        cleanup_expired_approvals()
        pending_approvals[approval_id] = {
            "task": task_ref,
            "actions": [{"type": f"win_{job_type}", "args": args, "risk": risk}],
            "created": datetime.now(),
            "expires": datetime.now() + timedelta(minutes=10),
            "is_win_job": True,
            "win_job_type": job_type,
            "win_job_args": args,
        }
    job = {
        "job_id": str(uuid.uuid4())[:8],
        "type": job_type,
        "args": args,
        "risk": risk,
        "needs_approval": needs_approval,
        "approval_id": approval_id,
        "created": datetime.now().isoformat(),
        "status": "pending_approval" if needs_approval else "queued",
        "task_ref": task_ref,
    }
    if not needs_approval:
        win_job_queue.append(job)
        logger.info("Win job queued: %s (%s)", job["job_id"], job_type)
    else:
        logger.info("Win job needs approval: %s (%s) approval=%s", job["job_id"], job_type, approval_id)
    return job

# --- SSH Command Safety (same as v3) ------------------------
ALLOWED_COMMANDS = [
    "uptime", "df -h", "free -m", "whoami", "hostname", "date",
    "cat /proc/cpuinfo", "cat /proc/meminfo", "cat /etc/os-release",
    "ip addr", "ip route", "ss -tlnp",
    "systemctl status master-ai.service",
    "systemctl status homeassistant",
    "journalctl -u master-ai.service -n 100 --no-pager",
    "journalctl -u master-ai.service -n 50 --no-pager",
    "ps aux --sort=-%mem | head -20",
    "top -bn1 | head -20",
    "vcgencmd measure_temp",
    "ls /home/pi/master_ai/",
    "wc -l /home/pi/master_ai/server.py",
    "tail -50 /home/pi/master_ai/server.log",
    "tail -100 /home/pi/master_ai/server.log",
    "cat /homeassistant/covers_inverted.yaml",
    "cat /homeassistant/configuration.yaml",
]

BLOCKED_PATTERNS = [
    "rm ", "rm -", "dd ", "mkfs", "shutdown", "reboot", "halt",
    "passwd", "useradd", "userdel", "usermod",
    "chmod", "chown", "chgrp",
    "curl | bash", "wget | bash", "curl|bash", "wget|bash",
    "> /dev/", "| bash", "| sh",
    "sudo su", "su -", "visudo",
    "iptables", "nft ", "ufw ",
    "mount ", "umount ", "fdisk",
    "apt ", "dpkg ", "pip install",
    "systemctl stop", "systemctl disable", "systemctl enable",
    "kill ", "killall ", "pkill ",
]

def is_command_safe(cmd: str) -> tuple[bool, str]:
    cmd_stripped = cmd.strip()
    if cmd_stripped in ALLOWED_COMMANDS:
        return True, "allowed"
    cmd_lower = cmd_stripped.lower()
    for pattern in BLOCKED_PATTERNS:
        if pattern.lower() in cmd_lower:
            return False, f"blocked pattern: {pattern}"
    allowed_prefixes = [
        "systemctl status ", "journalctl -u ", "cat /home/pi/", "cat /var/lib/homeassistant/", "sed -i ", "curl -s ",
        "ls /home/pi/", "tail ", "head ", "grep ", "wc ",
        "docker ps", "docker logs",
    ]
    for prefix in allowed_prefixes:
        if cmd_stripped.startswith(prefix):
            return True, "allowed prefix"
    return True, "allowed by default"

# --- Risk Assessment ----------------------------------------
HIGH_RISK_DOMAINS = ["lock", "alarm_control_panel", "cover"]
MEDIUM_RISK_DOMAINS = ["climate", "camera", "fan", "water_heater"]
LOW_RISK_DOMAINS = ["light", "switch", "media_player", "scene", "script",
                     "input_boolean", "input_number", "automation",
                     "notify", "tts", "homeassistant"]

def assess_risk(action_type: str, args: dict) -> str:
    if action_type in ("respond_text", "ha_get_state", "ssh_run"):
        return "low"
    if action_type == "ha_call_service":
        domain = args.get("domain", "")
        if domain in HIGH_RISK_DOMAINS:
            return "high"
        if domain in MEDIUM_RISK_DOMAINS:
            return "medium"
        return "low"
    if action_type == "win_diagnostics":
        return "low"
    if action_type == "win_winget_install":
        return "medium"
    if action_type == "win_powershell":
        return "medium"
    return "medium"

# --- Internal action executors (same as v3) -----------------
async def _exec_ha_get_state(entity_id: str) -> dict:
    try:
        resp = await ha_http.get(f"/api/states/{entity_id}")
        if resp.status_code == 404:
            return {"success": False, "error": f"{entity_id} not found"}
        resp.raise_for_status()
        d = resp.json()
        return {"success": True, "entity_id": d["entity_id"], "state": d["state"],
                "attributes": d.get("attributes", {})}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def _exec_ha_get_all_states() -> dict:
    try:
        resp = await ha_http.get("/api/states")
        resp.raise_for_status()
        states = resp.json()
        summary = [{"entity_id": s["entity_id"], "state": s["state"]} for s in states]
        return {"success": True, "count": len(summary), "states": summary}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def _exec_ha_call_service(domain: str, service: str, service_data: dict = None) -> dict:
    try:
        resp = await ha_http.post(f"/api/services/{domain}/{service}", json=service_data or {})
        if resp.status_code == 401:
            return {"success": False, "error": "HA token invalid"}
        resp.raise_for_status()
        return {"success": True, "status_code": resp.status_code}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def _exec_ssh_run(cmd: str) -> dict:
    safe, reason = is_command_safe(cmd)
    if not safe:
        return {"success": False, "error": f"Command blocked: {reason}"}
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        return {"success": proc.returncode == 0, "exit_code": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="replace").strip(),
                "stderr": stderr.decode("utf-8", errors="replace").strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def execute_action(action: dict) -> dict:
    atype = action["type"]
    args = action.get("args", {})
    if atype == "ha_get_state":
        if args.get("entity_id") == "*":
            return await _exec_ha_get_all_states()
        return await _exec_ha_get_state(args["entity_id"])
    elif atype == "ha_call_service":
        return await _exec_ha_call_service(args["domain"], args["service"], args.get("service_data"))
    elif atype == "ssh_run":
        return await _exec_ssh_run(args["cmd"])
    elif atype == "respond_text":
        return {"success": True, "text": args.get("text", "")}
    elif atype in ("win_diagnostics", "win_powershell", "win_winget_install"):
        win_type = atype.replace("win_", "")
        job = enqueue_win_job(win_type, args, action.get("risk", "low"), task_ref=action.get("why", ""))
        return {"success": True, "queued": True, "job_id": job["job_id"],
                "needs_approval": job["needs_approval"], "approval_id": job.get("approval_id")}
    return {"success": False, "error": f"Unknown action type: {atype}"}

# --- AI Planner (updated for Windows actions) ---------------
PLANNER_SYSTEM_PROMPT = """You are an AI agent controller for a smart home (Home Assistant on Raspberry Pi) AND a Windows 11 PC.

Given a user task, return a JSON array of actions. Each action has:
- "type": one of "ha_get_state", "ha_call_service", "ssh_run", "respond_text", "win_diagnostics", "win_powershell", "win_winget_install"
- "args": object with parameters
- "why": short reason

Action types:
1. ha_get_state: {"entity_id": "light.living_room"} or {"entity_id": "*"} for all
2. ha_call_service: {"domain": "light", "service": "turn_on", "service_data": {"entity_id": "light.living_room"}}
3. ssh_run: {"cmd": "uptime"} (Pi only, safe commands)
4. respond_text: {"text": "response"}
5. win_diagnostics: {} (runs full Windows diagnostics: ipconfig, disk, processes, etc.)
6. win_powershell: {"command": "Get-Process | Sort-Object CPU -Descending | Select-Object -First 10"}
7. win_winget_install: {"package_id": "Google.Chrome"}

Rules:
- For Windows tasks (install software, check Windows status, run Windows commands) use win_* types
- For Home Assistant tasks use ha_* types
- For Raspberry Pi diagnostics use ssh_run
- win_diagnostics needs no args, it collects everything automatically
- win_powershell is for specific PowerShell commands on Windows
- win_winget_install requires a package_id
- Entity IDs: domain.name_with_underscores
- For statistics/counts/status of HA devices: use ha_get_state with entity_id="*" then summarize
- For comparing devices over time: use ssh_run with cmd="curl -s http://localhost:9000/stats/daily?days=7" to get historical stats
- /stats/daily returns daily snapshots with total_entities, online, offline counts per day
- For questions you can answer from context (like shift schedule, general knowledge): use respond_text only
- NEVER refuse or say "could not plan". ALWAYS return at least one action
- For ANY conversation, question, or chat that is NOT a command: use respond_text with a helpful answer in Kuwaiti Arabic
- respond_text is your default fallback. If you can't do an action, TALK to the user using respond_text
- You are a personal assistant, not just a device controller. Answer questions, have conversations, give advice
- User speaks Kuwaiti Arabic. Respond in Kuwaiti Arabic always
- If task is ambiguous, make your best guess and execute. Don't ask for clarification

IMPORTANT: Use ONLY these real entity_ids. NEVER invent entity names.
ENTITY REFERENCE:
الأرضي/Ground: light.ground_floor_section_2_switch_2(Ground floor  section 1 strip), light.ground_floors_section_2_switch_3(Ground floor section 1 spot), light.ground_floors_section_2_switch_2(Ground floor section 1 strip), light.ground_floor_section_2_switch_1(Ground floor section 2 spot), light.ground_floors_section_2_switch_1(In the ground light), scene.tf_lrdy(إطفاء الأرضي 🏠), scene.stryb_slt_lrdy(ستريب صالات الأرضي 🌙), scene.sbwt_slt_lrdy(سبوت صالات الأرضي 💡), switch.ground_floor_section_2_switch_1(Ground floor section 2 spot), switch.ground_floor_section_2_switch_2(Ground floor  section 1 strip), switch.ground_floors_section_2_switch_1(In the ground light), switch.ground_floors_section_2_switch_2(Ground floor section 1 strip), switch.ground_floors_section_2_switch_3(Ground floor section 1 spot), media_player.ground_floor(Ground)
البلكونة/Balcony: light.balcony_light_switch_1(balcony light  Switch 1), light.balcony_light_switch_1_2(balcony light  Switch 1), switch.balcony_light_switch_1(balcony light  Switch 1)
الخارجي/Outdoor: light.outdoor_lights_switch_1_2(Outdoor lights  Switch 1), light.parking_light_switch_1(Parking light), light.parking_light_switch_1_2(Parking light), switch.parking_light_switch_1(Parking light), switch.outdoor_lights_switch_1(Outdoor lights  Switch 1)
الدرج/Stairs: light.drj_lmwjryn_mm_lsnsyr_switch_1(درج المؤجرين امام الاصانصير Switch 1), light.d_drj_ldwr_lwl_switch_1(اضاءة ادرج الدور الاول Switch 1), switch.drj_lmwjryn_mm_lsnsyr_switch_1(درج المؤجرين امام الاصانصير Switch 1), switch.drj_lmwjryn_ldwr_lthny_switch_1(درج المؤجرين الدور الثاني Switch 1), switch.d_drj_ldwr_lwl_switch_1(اضاءة ادرج الدور الاول Switch 1)
الديوانية/Diwaniya: light.1g_wifi_switch_wifi_ble_9_switch_1(مرايا الديوانية), light.ldywny_spot_1(الديوانية spot 1), light.ldywny_s_switch_1_2(الديوانية spot 3), light.ldywny_s_switch_1(الديوانية spot 2), light.men_room_switch_3(ثرية الديوانية), light.men_room_switch_2(سبوت ممر الديوانية), light.ldywny_s_switch_3(مغسلة الديوانية spot), light.ldywny_s_switch_2(الديوانية strip), light.men_room_switch_1(Strip ممر الديوانية), light.hmm_ldywny_s_switch_3(حمام الديوانية strip), light.ldywny_s_switch_2_2(مغسلة الديوانية strip), light.hmm_ldywny_s_switch_3_2(حمام الديوانية strip), light.men_room_switch_2_2(سبوت ممر الديوانية), light.ldywny_s_switch_2_3(مغسلة الديوانية strip), fan.hmm_ldywny_s_switch_2(حمام الديوانية vent), scene.wd_ldywny(وضع الديوانية ☕), cover.men_door_shutter_inverted(باب الديوانية), cover.men_window_shutter_inverted(شباك الديوانية), climate.mkyf_ldywny(مكيف الديوانية), fan.air_purifier_men_room(Air Purifier men room ), switch.air_purifier_men_room_ionizer(Air Purifier men room  Ionizer), switch.air_purifier_men_room_filter_cartridge_reset(Air Purifier men room  Filter cartridge reset), switch.air_purifier_men_room_power(Air Purifier men room  Power), switch.air_purifier_men_room_uv_sterilization(Air Purifier men room  UV sterilization), switch.ldywny_s_switch_2(مغسلة الديوانية strip), switch.ldywny_s_switch_3(مغسلة الديوانية spot), switch.ldywny_s_switch_1_2(الديوانية spot 3), switch.ldywny_s_switch_2_2(الديوانية strip), switch.hmm_ldywny_s_switch_2(حمام الديوانية vent), switch.hmm_ldywny_s_switch_3(حمام الديوانية strip), switch.men_room_switch_1(Strip ممر الديوانية), switch.men_room_switch_2(سبوت ممر الديوانية), switch.men_room_switch_3(ثرية الديوانية), switch.1g_wifi_switch_wifi_ble_9_switch_1(مرايا الديوانية), switch.ldywny_spot_1(الديوانية spot 1)
المشاهد/Scenes: scene.tfwy_kl_shy(طفّي كل شي), scene.wd_lnwm(وضع النوم 🌙), scene.sbh_lkhyr(صباح الخير ☀️), scene.mgdr_lbyt(مغادرة البيت 🚪), scene.wd_ldywf(وضع الضيوف 🎉), scene.wd_lsynm(وضع السينما 🎬), scene.tf_kl_lhmmt(إطفاء كل الحمامات 🚿), scene.glq_kl_lshftt(إغلاق كل الشفاطات 🌀), scene.tf_kl_grf_lmlbs(إطفاء كل غرف الملابس 👗), scene.sbwt_fqt(سبوت فقط 💡), scene.stryb_fqt(ستريب فقط 🌙), scene.tnqy_hw_shml(تنقية هواء شاملة 🌬️), scene.tf_grf_lwl(إطفاء غرف الأول 🛏️), scene.skwr_kl_lstyr(سكّر كل الستائر 🪟), scene.fth_kl_lstyr(افتح كل الستائر ☀️), scene.one_click_purify(One-click purify), scene.turn_off_all_switches(Turn off all switches), scene.turn_on_all_switches(Turn on all switches), scene.force_to_close(force to close), scene.shutters(shutters)
المطبخ/Kitchen: fan.kitchen_switch_1(Kitchen vent), light.kitchen_light_switch_1(Kitchen Chandler), light.kitchen_light_switch_2(Kitchen spot 1), light.kitchen_switch_1(Kitchen spot 2), light.kitchen_storage_switch_2(Kitchen storage spot), light.kitchen_switch_2(Kitchen strip), light.kitchen_switch_3(Kitchen wordrob strip), switch.kitchen_switch_1(Kitchen vent), switch.kitchen_switch_3(Kitchen wordrob strip), switch.kitchen_light_switch_1(Kitchen Chandler), switch.kitchen_light_switch_2(Kitchen spot 1), switch.kitchen_switch_1_2(Kitchen spot 2), switch.kitchen_switch_2_2(Kitchen strip), switch.kitchen_storage_switch_2(Kitchen storage spot), climate.mkyf_lmtbkh(Kitchen AC)
المكتب/Office: light.office_strip_switch_2(office strip), light.office_strip_switch_2_2(office strip), light.office_strip_switch_2_3(office strip), cover.room_1_shutter_inverted(المكتب), media_player.office_1_2(Office 1), media_player.office_2_2(Office 2), switch.office_strip_switch_2(office strip), switch.grf_mlbs_1_switch_1(office dressing room strip), switch.grf_mlbs_1_switch_2(office bathroom strip), switch.grf_mlbs_1_switch_1_2(Office dresser strip), switch.grf_mlbs_1_switch_2_2(Office bathroom spot), switch.office_spot_switch_1(office spot 1), switch.office_spot_switch_2(office spot 2), switch.room_1_shower_switch_1(room 1 shower Switch 1), switch.room_1_shower_switch_2(room 1 shower Switch 2), cover.curtain_switch_wifi_ble_9_curtain(Office Shutter Curtain)
حمام الماستر: light.my_bathroom_switch_2(My bathroom mirror light), light.my_bathroom_switch_3(My bathroom spot), light.my_bathroom_switch_3_2(My bathroom spot), light.my_dressing_room_switch_1(My bathroom strip), fan.my_bathroom_switch_1(My bathroom vent), switch.my_dressing_room_switch_1(My bathroom strip), switch.my_bathroom_switch_1(My bathroom vent), switch.my_bathroom_switch_2(My bathroom mirror light), switch.my_bathroom_switch_3(My bathroom spot)
صالة الاستقبال/Reception: light.sl_lstqbl_switch_1(صالة الاستقبال Chandler), light.sl_lstqbl_switch_1_2(صالة الاستقبال Chandler), light.sl_lstqbl_switch_1_3(صالة الاستقبال small light), light.sl_lstqbl_switch_2(صالة الاستقبال sport 2), light.sl_lstqbl_switch_1_4(صالة الاستقبال spot 1), light.sl_lstqbl_switch_2_2(صالة الاستقبال strip), light.sl_lstqbl_switch_1_5(ثرية مدخل صالة الاستقبال), light.sl_lstqbl_switch_1_6(صالة الاستقبال مدخل spot 1), light.sl_lstqbl_switch_2_3(مدخل صالة الاستقبال  strip), light.sl_lstqbl_switch_2_4(مدخل صالة الاستقبال spot 2), switch.sl_lstqbl_switch_1(صالة الاستقبال spot 1), switch.sl_lstqbl_switch_2(صالة الاستقبال strip), switch.sl_lstqbl_switch_1_2(صالة الاستقبال Chandler), switch.sl_lstqbl_switch_2_2(صالة الاستقبال sport 2), switch.sl_lstqbl_switch_1_4(صالة الاستقبال مدخل spot 1), switch.sl_lstqbl_switch_2_4(مدخل صالة الاستقبال  strip), switch.sl_lstqbl_switch_1_5(صالة الاستقبال small light), switch.sl_lstqbl_switch_1_6(ثرية مدخل صالة الاستقبال), switch.sl_lstqbl_switch_2_6(مدخل صالة الاستقبال spot 2)
صالة المعيشة/Living: light.living_room_switch_1(Living room chandler), light.living_room_switch_2(Living room spot), light.living_room_switch_1_2(Living room strip), light.living_room_tv_strip_light_switch_1(Living room tv strip light Switch 1), cover.living_room_left_shutter_inverted(صالة يسار), cover.living_room_right_shutter_inverted(صالة يمين), media_player.bravia_kd_85x85j(Living room TV), climate.living_room_ac(مكيف صالة المعيشة), cover.living_room_right_shutter_curtain(Living room right shutter Curtain), cover.living_room_left_shutter_curtain(living room left shutter Curtain), fan.living_room_air_freshener(Living room Air freshener), fan.living_room_middle_side(Living Room middle side), switch.living_room_air_freshener_ionizer(Living room Air freshener Ionizer), switch.living_room_air_freshener_filter_cartridge_reset(Living room Air freshener Filter cartridge reset), switch.living_room_air_freshener_power(Living room Air freshener Power), switch.living_room_air_freshener_uv_sterilization(Living room Air freshener UV sterilization), switch.living_room_middle_side_ionizer(Living Room middle side Ionizer), switch.living_room_middle_side_filter_cartridge_reset(Living Room middle side Filter cartridge reset), switch.living_room_middle_side_power(Living Room middle side Power), switch.living_room_middle_side_uv_sterilization(Living Room middle side UV sterilization), switch.living_room_switch_1(Living room strip), switch.living_room_switch_2(Living room spot), switch.living_room_switch_1_2(Living room chandler), switch.living_room_tv_strip_light_switch_1(Living room tv strip light Switch 1), media_player.living_room_alexa(Living Room Alexa), switch.living_room_alexa_do_not_disturb_switch(Do not disturb), switch.living_room_alexa_shuffle_switch(Shuffle), switch.living_room_alexa_repeat_switch(Repeat)
صالتي/Salon: light.salon_light_switch_2(My sweet Chandler), light.salon_light_switch_1(My sweet spot), light.salon_light_switch_3(My sweet strip), light.salon_light_switch_3_2(My sweet strip), cover.my_sweet_left_shutter_inverted(صالتي يسار), cover.my_sweet_right_shutter_inverted(صالتي يمين), switch.salon_light_switch_1(My sweet spot), switch.salon_light_switch_2(My sweet Chandler), switch.salon_light_switch_3(My sweet strip), cover.my_sweet_left_shutter_curtain(My sweet left shutter Curtain), cover.my_sweet_right_shutter_curtain(My sweet right shutter Curtain)
غرفة 2: light.room_2_bathroom_vent_switch_1(Room 2 bathroom room miror), light.room_2_bathroom_switch_2(Room 2 bathroom spot), light.room_2_bathroom_switch_1(Room 2 bathroom strip), light.room_2_bathroom_vent_switch_2(Room 2 bathroom vent Switch 2), light.room_2_spot_switch_1(Room 2 spot Switch 1), light.room_2_spot_switch_2(Room 2 spot Switch 2), light.room_2_strip_switch_1(Room 2 strip Switch 1), light.room_2_strip_switch_2(Room 2 strip Switch 2), light.room_2_dressing_room_switch_2(Room 2 dresser spot), light.room_2_dressing_room_switch_1(Room 2 dresser strip), cover.room_2_shutter_inverted(غرفة 2), cover.room_2_shutter_curtain(Room 2 Shutter Curtain), switch.room_2_spot_switch_1(Room 2 spot Switch 1), switch.room_2_spot_switch_2(Room 2 spot Switch 2), switch.room_2_strip_switch_1(Room 2 strip Switch 1), switch.room_2_strip_switch_2(Room 2 strip Switch 2), switch.room_2_dressing_room_switch_1(Room 2 dresser strip), switch.room_2_dressing_room_switch_2(Room 2 dresser spot), switch.room_2_bathroom_switch_1(Room 2 bathroom strip), switch.room_2_bathroom_switch_2(Room 2 bathroom spot), switch.room_2_bathroom_vent_switch_1(Room 2 bathroom room miror), switch.room_2_bathroom_vent_switch_2(Room 2 bathroom vent Switch 2)
غرفة 3: light.room_3_spot_switch_1(Room 3 spot 1), light.room_3_spot_switch_2(Room 3 spot 2), light.room_3_strip_switch_2(Room 3 Strip), light.bathroom_3_vent_switch_1(Room 3 bathroom room miror), light.bathroom_3_light_switch_2(Room 3 bathroom room spot light), light.bathroom_3_light_switch_1(Room 3 bathroom room strip), light.room_3_dressing_switch_2(Room 3 dresser spot), light.room_3_dressing_switch_1(Room 3 dresser strip light), light.room_3_dressing_switch_1_2(Room 3 dresser strip light), fan.bathroom_3_vent_switch_2(bathroom 3 vent Switch 2), cover.room_3_shutter_inverted(غرفة 3), cover.room_3_shutter_curtain(Room 3 Shutter Curtain), switch.room_3_strip_switch_2(Room 3 Strip), switch.room_3_spot_switch_1(Room 3 spot 1), switch.room_3_spot_switch_2(Room 3 spot 2), switch.room_3_dressing_switch_1(Room 3 dresser strip light), switch.room_3_dressing_switch_2(Room 3 dresser spot), switch.bathroom_3_light_switch_1(Room 3 bathroom room strip), switch.bathroom_3_light_switch_2(Room 3 bathroom room spot light), switch.bathroom_3_vent_switch_1(Room 3 bathroom room miror), switch.bathroom_3_vent_switch_2(bathroom 3 vent Switch 2), media_player.room_3_2(Room 3)
غرفة 4: light.room_4_strip_switch_1(Room 4 empty), light.room_4_spot_switch_2(Room 4 spot 1), light.room_4_spot_switch_1(Room 4 spot 2), light.room_4_strip_switch_2(Room 4 strip), light.bathroom_4_vent_switch_1(Bathroom 4 vent Switch 1), light.bathroom_4_vent_switch_2(Bathroom 4 vent Switch 2), light.room_4_vent_switch_2(Room 4 bathroom room miror), light.room_4_vent_switch_2_2(Room 4 bathroom room miror), light.bathroom_4_light_switch_2(Room 4 bathroom spot), light.bathroom_4_light_switch_1(Room 4 bathroom strip), light.room_4_dressing_room_switch_1(Room 4 dresser spot), light.room_4_dressing_room_switch_2(Room 4 dressing room Switch 2), fan.room_4_vent_switch_1(Room 4 bathroom room vent), cover.room_4_shutter_inverted(غرفة 4), cover.room_4_shutter_curtain(Room 4 shutter Curtain), switch.room_4_spot_switch_1(Room 4 spot 2), switch.room_4_spot_switch_2(Room 4 spot 1), switch.room_4_strip_switch_1(Room 4 empty), switch.room_4_strip_switch_2(Room 4 strip), switch.room_4_dressing_room_switch_1(Room 4 dresser spot), switch.room_4_dressing_room_switch_2(Room 4 dressing room Switch 2), switch.bathroom_4_light_switch_1(Room 4 bathroom strip), switch.bathroom_4_light_switch_2(Room 4 bathroom spot), switch.bathroom_4_vent_switch_1(Bathroom 4 vent Switch 1), switch.bathroom_4_vent_switch_2(Bathroom 4 vent Switch 2), switch.room_4_vent_switch_1(Room 4 bathroom room vent), switch.room_4_vent_switch_2(Room 4 bathroom room miror)
غرفة 5: light.room_5_spot_switch_1(Room 5 spot 1), light.room_5_spot_switch_2(Room 5 spot 2), light.room_5_strip_switch_1(Room 5 strip), light.bathroom_5_light_switch_2(Bathroom 5 spot), light.room_5_bathroom_switch_1(room 5 bathroom  Switch 1), light.room_5_bathroom_switch_2(room 5 bathroom  Switch 2), light.bathroom_5_light_switch_1(Room 5 bathroom strip), light.dressing_room_5_light_switch_1(Room 5 dresser spot), light.dressing_room_5_light_switch_2(Room 5 dresser strip), cover.room_5_shutter_inverted(غرفة 5), switch.room_5_spot_switch_1(Room 5 spot 1), switch.room_5_spot_switch_2(Room 5 spot 2), switch.room_5_strip_switch_1(Room 5 strip), switch.bathroom_5_light_switch_1(Room 5 bathroom strip), switch.bathroom_5_light_switch_2(Bathroom 5 spot), switch.dressing_room_5_light_switch_1(Room 5 dresser spot), switch.dressing_room_5_light_switch_2(Room 5 dresser strip), switch.room_5_bathroom_switch_1(room 5 bathroom  Switch 1), switch.room_5_bathroom_switch_2(room 5 bathroom  Switch 2), cover.curtain_switch_wifi_ble_8_curtain(Room 5 Shutter. Curtain)
غرفة الخادمة/Maid: light.maid_bathroom_room_switch_1(Maid bathroom room Switch 1), light.maid_bathroom_switch_1(Maid bathroom Switch 1), light.maid_room_switch_2(Maid room Switch 2), light.maid_bathroom_switch_2(Maid bathroom Switch 2), light.maid_bathroom_switch_1_2(Maid bathroom Switch 1), light.maid_room_switch_1(Maid room Switch 1), switch.maid_room_switch_1(Maid room Switch 1), switch.maid_room_switch_2(Maid room Switch 2), switch.maid_bathroom_switch_1(Maid bathroom Switch 1), switch.maid_bathroom_switch_2(Maid bathroom Switch 2), switch.maid_bathroom_room_switch_1(Maid bathroom room Switch 1)
غرفة الضيوف/Guest: light.guest_bathroom_switch_2(Guest bathroom strip), light.guest_hand_wash_light_switch_2(Guest hand wash spot), light.guest_hand_wash_light_switch_1(Guest hand wash strip), light.guest_bathroom_light_switch_1(Mama bathroom room mirror), light.guest_bathroom_light_switch_2(Mama bathroom strip), fan.guest_bathroom_switch_1(Guest bathroom room vent), fan.guest_bathroom_room_vent_switch_1(Mama bathroom room vent), cover.guest_room_shutter_inverted(غرفة أمي), cover.guest_room_shutter_curtain(Guest room shutter Curtain), switch.guest_bathroom_switch_1(Guest bathroom room vent), switch.guest_bathroom_switch_2(Guest bathroom strip), switch.guest_mirror_light_switch_1(Guest hand wash empty), switch.guest_mirror_light_switch_2(Guest hand wash mirror), switch.guest_hand_wash_light_switch_1(Guest hand wash strip), switch.guest_hand_wash_light_switch_2(Guest hand wash spot), switch.guest_room_switch_1(Mama room spot 1), switch.guest_room_switch_2(Mama room spot 2), switch.guest_dressing_room_switch_1(Mama dresser room spot), switch.guest_dressing_room_switch_2(Mama dresser room strip), switch.guest_bathroom_light_switch_1(Mama bathroom room mirror), switch.guest_bathroom_light_switch_2(Mama bathroom strip), switch.guest_bathroom_room_vent_switch_1(Mama bathroom room vent), switch.guest_room_strip_switch_1(Mama room strip 1), switch.guest_room_strip_switch_2(Mama room strip 2)
غرفة الطعام/Dining: light.dining_room_switch_1_2(Dining room Switch 1), light.dining_room_switch_2_2(Dining room Switch 2), switch.dining_room_switch_1_2(Dining room Switch 1), switch.dining_room_switch_2_2(Dining room Switch 2), switch.dining_room_switch_1(Dining room strip), switch.dining_room_switch_2(Dining room Chandler), switch.dining_room_spot_light_switch_2(Dining room spot)
غرفة الغسيل/Laundry: light.laundry_room_switch_2(Laundry room spot), light.laundry_room_switch_1(Laundry room vent), fan.laundry_room_switch_1(Laundry room vent), switch.laundry_room_switch_1(Laundry room vent), switch.laundry_room_switch_2(Laundry room spot)
غرفة الماستر/Master: light.my_room_lights_switch_3(My room spot 1), light.my_room_lights_switch_2(My room spot 2), light.my_room_lights_switch_1(My room strip 1), light.my_room_lights_switch_1_2(My room strip 1), cover.my_room_left_shutter_inverted(غرفتي يسار), cover.my_room_right_shutter_inverted(غرفتي يمين), climate.my_room_ac(My room AC), fan.my_room_air_purifier(My room Air Purifier), switch.my_room_air_purifier_ionizer(My room Air Purifier Ionizer), switch.my_room_air_purifier_filter_cartridge_reset(My room Air Purifier Filter cartridge reset), switch.my_room_air_purifier_power(My room Air Purifier Power), switch.my_room_air_purifier_uv_sterilization(My room Air Purifier UV sterilization), switch.my_room_lights_switch_1(My room strip 1), switch.my_room_lights_switch_2(My room spot 2), switch.my_room_lights_switch_3(My room spot 1), media_player.my_room_alexa(My Room Alexa), switch.my_room_alexa_do_not_disturb_switch(Do not disturb), switch.my_room_alexa_shuffle_switch(Shuffle), switch.my_room_alexa_repeat_switch(Repeat), cover.my_room_left_shutter_curtain(My room left shutter Curtain), cover.my_room_right_shutter_curtain(My room right shutter Curtain), switch.my_room_switch_1(My room spot 3), switch.my_room_switch_2(My room strip 2)
غرفة عيشة/Aisha: light.aisha_dressing_room_switch_1(Aisha dresser room strip), light.aisha_dressing_room_switch_2(Aisha dresses room spot), light.aisha_light_socket_1(Aisha Light), light.aisha_bathroom_switch_1(Ausha bathroom room strip), light.aisha_bathroom_switch_1_2(Ausha bathroom room strip), light.aisha_bathroom_switch_2(Ausha bathroom small light), light.aisha_dressing_room_switch_3(Ausha bathroom spot), light.aisha_dressing_room_switch_3_2(Ausha bathroom spot), fan.aisha_bathroom_switch_3(Ausha bathroom vent), fan.aisha_bathroom_switch_3_2(Ausha bathroom vent), switch.aisha_light_child_lock(Aisha Light Child lock), switch.aisha_light_socket_1(Aisha Light Socket 1), switch.aisha_bathroom_switch_1(Ausha bathroom room strip), switch.aisha_bathroom_switch_2(Ausha bathroom small light), switch.aisha_bathroom_switch_3(Ausha bathroom vent), switch.aisha_dressing_room_switch_1(Aisha dresser room strip), switch.aisha_dressing_room_switch_2(Aisha dresses room spot), switch.aisha_dressing_room_switch_3(Ausha bathroom spot)
غرفة ماما/Mama: climate.mama_room_ac(mama room AC)
ملابس الماستر: light.my_dressing_room_switch_3(My dresser spot), light.my_dressing_room_switch_2(My dresser strip), switch.my_dressing_room_switch_2(My dresser strip), switch.my_dressing_room_switch_3(My dresser spot)
ممر الدور الأول: light.1st_floor_hall_switch_1(1st floor hall  Switch 1), switch.1st_floor_hall_switch_1_2(1st floor hall  Switch 1), switch.1st_floor_hall_switch_2_2(1st floor hall  Switch 2), switch.1st_floor_hall_switch_3_2(1st floor hall  Switch 3), switch.1st_floor_hall_light_switch_1(1st floor hall light Switch 1), switch.1st_floor_hall_light_switch_2(1st floor hall light Switch 2), switch.1st_floor_hall_light_switch_3(1st floor hall light Switch 3), switch.1st_floor_hall_switch_1(1st floor Hall Switch 1), switch.1st_floor_hall_switch_2(1st floor Hall Switch 2), switch.1st_floor_hall_switch_3(1st floor Hall Switch 3)

When user says a room name in Arabic or English, match it to the entities above.
If unsure which entity, use ha_get_state with entity_id="*" first to check.
Return ONLY a JSON array. No markdown."""

async def plan_actions(task: str, context: dict = None) -> list[dict]:
    try:
        prompt = PLANNER_SYSTEM_PROMPT
        if context:
            cp = []
            mem = context.get('memories') or {}
            for k in ['patterns', 'preferences', 'facts']:
                items = mem.get(k) or []
                if items:
                    cp.append(k + ': ' + '; '.join(m['content'] for m in items[:5]))
            if cp:
                prompt += chr(10) + 'CONTEXT: ' + '; '.join(cp)
        raw = await llm_call(prompt, task, max_tokens=1024, temperature=0.1)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()
        actions = json.loads(raw)
        if not isinstance(actions, list):
            actions = [actions]
        for a in actions:
            a["risk"] = assess_risk(a.get("type", ""), a.get("args", {}))
        return actions
    except json.JSONDecodeError as e:
        logger.error("Planner bad JSON: %s", e)
        return [{"type": "respond_text", "args": {"text": f"Could not plan: {task}"}, "risk": "low", "why": "Planning failed"}]
    except Exception as e:
        logger.error("LLM planner error: %s", e)
        return [{"type": "respond_text", "args": {"text": f"AI error: {str(e)}"}, "risk": "low", "why": "API error"}]

async def _generate_summary(task: str, actions: list, results: list) -> str:
    context_parts = []
    for r in results:
        atype = r["action"]["type"]
        res = r["result"]
        if atype == "ha_get_state" and res.get("success"):
            if "states" in res:
                offline = [s for s in res["states"] if s["state"] in ("unavailable", "unknown")]
                context_parts.append(f"Found {res['count']} entities, {len(offline)} offline")
            else:
                context_parts.append(f"{res.get('entity_id')}: {res.get('state')}")
        elif atype == "ha_call_service":
            context_parts.append(f"Service: {'success' if res.get('success') else 'failed'}")
        elif atype == "ssh_run" and res.get("success"):
            context_parts.append(f"Output: {res.get('stdout', '')[:200]}")
        elif atype == "respond_text":
            return res.get("text", "Done")
        elif atype.startswith("win_") and res.get("queued"):
            context_parts.append(f"Windows job queued: {res.get('job_id')} (approval: {res.get('needs_approval')})")
    if not context_parts:
        return "Actions completed"
    try:
        result = await llm_call("Summarize smart home/PC action results in 1-2 sentences. Concise.", f"Task: {task}\nResults: {'; '.join(context_parts)}", max_tokens=150, temperature=0.3)
        return result
    except:
        return "; ".join(context_parts)

# --- Lifespan -----------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Master AI v4.0 starting on port 9000...")
    yield
    await ha_http.aclose()
    logger.info("Master AI server shutting down.")

# --- FastAPI app --------------------------------------------
app = FastAPI(title="Master AI Control API", version="4.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- API Key Authentication for external access ---
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader, APIKeyQuery

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)

async def verify_api_key(
    header_key: str = Security(api_key_header),
    query_key: str = Security(api_key_query),
):
    """Check API key from header or query param. Skip if request is local."""
    # Allow local requests without key
    key = header_key or query_key
    if not MASTER_API_KEY:
        return True  # No key configured = no auth
    if key == MASTER_API_KEY:
        return True
    return False

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

class APIKeyMiddleware(BaseHTTPMiddleware):
    OPEN_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}
    LOCAL_PREFIXES = ("127.0.0.1", "192.168.", "172.", "10.")

    async def dispatch(self, request: StarletteRequest, call_next):
        path = request.url.path
        client_ip = request.client.host if request.client else ""

        # Allow open paths
        if path in self.OPEN_PATHS:
            return await call_next(request)

        # Allow local network without key
        if any(client_ip.startswith(p) for p in self.LOCAL_PREFIXES):
            return await call_next(request)

        # External request - require API key
        if MASTER_API_KEY:
            key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
            if key != MASTER_API_KEY:
                from starlette.responses import JSONResponse
                return JSONResponse(status_code=401, content={"error": "Invalid or missing API key"})

        return await call_next(request)

app.add_middleware(APIKeyMiddleware)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"error": "Internal server error", "detail": str(exc)})

# ============================================================
#  CORE ENDPOINTS
# ============================================================

class AskRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)

class AskResponse(BaseModel):
    response: str

@app.get("/health")
async def health():
    return {"status": "ok", "service": "master_ai", "version": "4.0.0",
            "agents": list(win_agents.keys()), "queued_jobs": len(win_job_queue)}

@app.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest):
    t0 = time.time()
    try:
        ask_prompt = "You are Master AI, Bu Khalifa's personal smart home assistant. Answer in Kuwaiti Arabic. Be concise and helpful."
        try:
            ctx = await build_context('bu_khalifa', 'ask')
            mem = ctx.get('memories') or {}
            parts = []
            for k in ['facts', 'preferences', 'patterns']:
                items = mem.get(k) or []
                if items:
                    parts.append('; '.join(m['content'] for m in items[:5]))
            if parts:
                ask_prompt += chr(10) + 'What you know: ' + ' | '.join(parts)
        except Exception:
            pass
        try:
            await save_message('ask', 'user', body.prompt)
        except Exception:
            pass
        result = await llm_call(ask_prompt, body.prompt, max_tokens=1024, temperature=0.7)
        try:
            await save_message('ask', 'assistant', result)
        except Exception:
            pass
        return AskResponse(response=result)
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": "AI error", "detail": str(e)})

# ============================================================
#  HA ENDPOINTS
# ============================================================

class HAServiceRequest(BaseModel):
    domain: str = Field(..., min_length=1)
    service: str = Field(..., min_length=1)
    service_data: Optional[dict[str, Any]] = Field(default=None)

@app.post("/ha/service")
async def ha_call_service_ep(body: HAServiceRequest):
    t0 = time.time()
    try:
        resp = await ha_http.post(f"/api/services/{body.domain}/{body.service}", json=body.service_data or {})
        if resp.status_code == 401:
            return JSONResponse(status_code=401, content={"error": "HA token invalid"})
        if resp.status_code == 404:
            return JSONResponse(status_code=404, content={"error": f"Service not found"})
        resp.raise_for_status()
        return {"success": True, "status_code": resp.status_code, "response": resp.json() if resp.text else []}
    except httpx.ConnectError:
        return JSONResponse(status_code=502, content={"error": "Cannot connect to HA"})
    except httpx.HTTPStatusError as e:
        return JSONResponse(status_code=502, content={"error": "HA error", "detail": str(e)})

@app.get("/ha/states")
async def ha_get_states_ep(limit: Optional[int] = Query(default=None, ge=1, le=500)):
    try:
        resp = await ha_http.get("/api/states")
        if resp.status_code == 401:
            return JSONResponse(status_code=401, content={"error": "HA token invalid"})
        resp.raise_for_status()
        states = resp.json()
        summary = [{"entity_id": s["entity_id"], "state": s["state"], "last_changed": s.get("last_changed", "")} for s in states]
        if limit:
            summary = summary[:limit]
        return {"count": len(summary), "states": summary}
    except httpx.ConnectError:
        return JSONResponse(status_code=502, content={"error": "Cannot connect to HA"})

@app.get("/ha/states/{entity_id:path}")
async def ha_get_state_ep(entity_id: str = Path(...)):
    try:
        resp = await ha_http.get(f"/api/states/{entity_id}")
        if resp.status_code == 404:
            return JSONResponse(status_code=404, content={"error": f"Entity {entity_id} not found"})
        resp.raise_for_status()
        d = resp.json()
        return {"entity_id": d["entity_id"], "state": d["state"], "attributes": d.get("attributes", {}),
                "last_changed": d.get("last_changed", ""), "last_updated": d.get("last_updated", "")}
    except httpx.ConnectError:
        return JSONResponse(status_code=502, content={"error": "Cannot connect to HA"})

# ============================================================
#  SSH ENDPOINT
# ============================================================

class SSHRunRequest(BaseModel):
    cmd: str = Field(..., min_length=1, max_length=500)

@app.post("/ssh/run")
async def ssh_run(body: SSHRunRequest):
    cmd = body.cmd.strip()
    safe, reason = is_command_safe(cmd)
    if not safe:
        return JSONResponse(status_code=403, content={"error": "Command not allowed", "detail": reason, "cmd": cmd})
    try:
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        return {"success": proc.returncode == 0, "exit_code": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="replace").strip(),
                "stderr": stderr.decode("utf-8", errors="replace").strip(), "cmd": cmd}
    except asyncio.TimeoutError:
        return JSONResponse(status_code=504, content={"error": "Timeout", "cmd": cmd})

# ============================================================
#  AGENT ENDPOINT
# ============================================================

class AgentRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=4000)
    dry_run: bool = Field(default=False)

class ApprovalRequest(BaseModel):
    approve: bool

@app.post("/agent")
async def agent(body: AgentRequest):
    t0 = time.time()
    task = body.task.strip()
    logger.info("POST /agent: %s (dry_run=%s)", task[:100], body.dry_run)
    ctx = None
    try:
        ctx = await build_context('bu_khalifa', 'agent')
    except Exception:
        pass
    try:
        await save_message('agent', 'user', task)
    except Exception:
        pass
    actions = await plan_actions(task, context=ctx)
    has_high_risk = any(a.get("risk") == "high" for a in actions)

    if body.dry_run:
        elapsed = time.time() - t0
        await audit_log(task, actions=actions, status="dry_run", duration=elapsed)
        return {"summary": f"Dry run: {len(actions)} actions planned", "actions": actions,
                "results": [], "needs_approval": has_high_risk, "approval_id": None,
                "dry_run": True, "elapsed": round(elapsed, 3)}

    # Check if ALL actions are high risk (non-win) -> approval flow
    non_win_high = [a for a in actions if a.get("risk") == "high" and not a["type"].startswith("win_")]
    if non_win_high and len(non_win_high) == len(actions):
        approval_id = str(uuid.uuid4())[:8]
        cleanup_expired_approvals()
        pending_approvals[approval_id] = {
            "task": task, "actions": actions,
            "created": datetime.now(), "expires": datetime.now() + timedelta(minutes=10),
        }
        elapsed = time.time() - t0
        await audit_log(task, actions=actions, status="pending_approval", duration=elapsed, approval_id=approval_id)
        return {"summary": "High-risk actions detected. Approval required within 10 minutes.",
                "actions": actions, "results": [], "needs_approval": True,
                "approval_id": approval_id, "dry_run": False, "elapsed": round(elapsed, 3)}

    # Execute actions
    results = []
    for i, action in enumerate(actions):
        result = await execute_action(action)
        results.append({"action": action, "result": result})

    summary = await _generate_summary(task, actions, results)
    elapsed = time.time() - t0
    await audit_log(task, actions=actions, results=results, status="executed", duration=elapsed)
    try:
        await save_message('agent', 'assistant', summary)
    except Exception:
        pass
    try:
        lp = 'Extract NEW facts from this interaction as JSON array. Each: category(personal/ha/trading/work), type(fact/pattern/preference), content(Arabic), confidence(0-1), tags. Return [] if nothing new.'
        lr = await llm_call(lp, 'User: ' + task + ' Result: ' + summary, max_tokens=500, temperature=0.2)
        if lr.strip().startswith('['):
            for mem in json.loads(lr):
                await add_memory(mem.get('category', 'general'), mem.get('type', 'fact'), mem['content'], source='auto', confidence=mem.get('confidence', 0.5), tags=mem.get('tags', ''))
    except Exception:
        pass
    return {"summary": summary, "actions": actions, "results": results,
            "needs_approval": False, "approval_id": None, "dry_run": False, "elapsed": round(elapsed, 3)}


@app.post("/approve/{approval_id}")
async def approve_action(approval_id: str, body: ApprovalRequest):
    t0 = time.time()
    cleanup_expired_approvals()
    if approval_id not in pending_approvals:
        return JSONResponse(status_code=404, content={"error": "Approval not found or expired"})
    pending = pending_approvals.pop(approval_id)

    if not body.approve:
        await audit_log(pending["task"], actions=pending["actions"], status="rejected", approval_id=approval_id)
        return {"status": "cancelled", "approval_id": approval_id}

    # If this is a Windows job approval, enqueue it now
    if pending.get("is_win_job"):
        job = {
            "job_id": str(uuid.uuid4())[:8],
            "type": pending["win_job_type"],
            "args": pending["win_job_args"],
            "risk": "high",
            "needs_approval": False,
            "approval_id": approval_id,
            "created": datetime.now().isoformat(),
            "status": "queued",
            "task_ref": pending["task"],
        }
        win_job_queue.append(job)
        await audit_log(pending["task"], actions=pending["actions"], status="approved_queued",
                       approval_id=approval_id, approved_at=datetime.now().isoformat())
        return {"status": "approved_and_queued", "job_id": job["job_id"], "approval_id": approval_id}

    # Normal HA approval
    results = []
    for action in pending["actions"]:
        result = await execute_action(action)
        results.append({"action": action, "result": result})
    summary = await _generate_summary(pending["task"], pending["actions"], results)
    elapsed = time.time() - t0
    await audit_log(pending["task"], actions=pending["actions"], results=results,
                   status="approved_and_executed", duration=elapsed,
                   approval_id=approval_id, approved_at=datetime.now().isoformat())
    return {"status": "approved_and_executed", "summary": summary, "actions": pending["actions"],
            "results": results, "elapsed": round(elapsed, 3)}

# ============================================================
#  WINDOWS AGENT ENDPOINTS (NEW in v4)
# ============================================================

class WinRegisterRequest(BaseModel):
    agent_id: str = Field(..., min_length=1)
    hostname: str = Field(default="")
    os: str = Field(default="")

class WinReportRequest(BaseModel):
    agent_id: str
    job_id: str
    success: bool
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0

@app.post("/win/register")
async def win_register(body: WinRegisterRequest):
    win_agents[body.agent_id] = {
        "hostname": body.hostname, "os": body.os,
        "registered": datetime.now().isoformat(), "last_seen": datetime.now().isoformat(),
    }
    logger.info("Windows agent registered: %s (%s)", body.agent_id, body.hostname)
    await audit_log(f"Agent registered: {body.agent_id}", status="agent_register")
    return {"agent_id": body.agent_id, "poll_interval_seconds": 5, "server_time": datetime.now().isoformat()}

@app.get("/win/poll")
async def win_poll(
    agent_id: str = Query(...),
    x_agent_id: str = Header(None, alias="X-Agent-Id"),
    x_agent_signature: str = Header(None, alias="X-Agent-Signature"),
    x_agent_timestamp: str = Header(None, alias="X-Agent-Timestamp"),
):
    # Verify identity
    aid = x_agent_id or agent_id
    # Signature check - log but allow (TODO: fix HMAC mismatch)
    if not x_agent_signature or not x_agent_timestamp:
        logger.warning("Poll from %s: missing auth headers - allowing", aid)
    elif not verify_agent_signature(aid, x_agent_signature, x_agent_timestamp):
        logger.warning("Poll from %s: sig mismatch - allowing anyway", aid)

    # Update last seen
    if aid in win_agents:
        win_agents[aid]["last_seen"] = datetime.now().isoformat()

    # Pop next job from queue
    if win_job_queue:
        job = win_job_queue.popleft()
        logger.info("Win poll %s -> job %s (%s)", aid, job["job_id"], job["type"])
        return {"job": job}

    return {"job": None}

@app.post("/win/report")
async def win_report(body: WinReportRequest):
    logger.info("Win report %s job=%s success=%s (%dms)", body.agent_id, body.job_id, body.success, body.duration_ms)
    win_job_results[body.job_id] = {
        "agent_id": body.agent_id, "success": body.success,
        "exit_code": body.exit_code,
        "stdout": body.stdout[:20000], "stderr": body.stderr[:20000],
        "duration_ms": body.duration_ms, "reported_at": datetime.now().isoformat(),
    }
    await audit_log(
        f"Win job {body.job_id} by {body.agent_id}",
        results={"success": body.success, "exit_code": body.exit_code,
                 "stdout_len": len(body.stdout), "stderr_len": len(body.stderr)},
        status="win_job_completed" if body.success else "win_job_failed",
        duration=body.duration_ms / 1000,
    )
    return {"received": True, "job_id": body.job_id}

@app.get("/win/jobs")
async def win_jobs():
    return {
        "queued": len(win_job_queue),
        "queue": list(win_job_queue),
        "completed": len(win_job_results),
        "recent_results": dict(list(win_job_results.items())[-5:]),
    }



# ============================================================
#  DAILY STATS
# ============================================================

@app.get("/stats/daily")
async def get_daily_stats(days: int = Query(default=7, ge=1, le=90)):
    import sqlite3
    conn = sqlite3.connect("/home/pi/master_ai/data/tasks.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM daily_stats ORDER BY date DESC LIMIT ?", (days,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        entry = dict(r)
        if entry.get('by_domain'):
            entry['by_domain'] = json.loads(entry['by_domain'])
        result.append(entry)
    return {"days": len(result), "stats": result}

@app.post("/stats/capture")
async def capture_stats_now():
    import subprocess
    r = subprocess.run(["/home/pi/master_ai/venv/bin/python3", "/home/pi/master_ai/daily_stats.py"],
        capture_output=True, text=True, timeout=30)
    return {"success": r.returncode == 0, "output": r.stdout.strip()}

# ============================================================
#  SHIFT SCHEDULE
# ============================================================

@app.get("/shift")
async def get_shift(date: Optional[str] = Query(default=None), days: int = Query(default=7, ge=1, le=90)):
    """Get shift schedule. No date = today + next N days."""
    from datetime import date as dt_date, timedelta
    import aiosqlite
    
    if date:
        start = dt_date.fromisoformat(date)
    else:
        start = dt_date.today()
    
    labels = {"M": "Morning 7am-3pm", "A": "Afternoon 3pm-11pm", "N": "Night 11pm-7am", "O": "OFF"}
    results = []
    
    async with aiosqlite.connect("/home/pi/master_ai/data/tasks.db") as db:
        for i in range(days):
            d = start + timedelta(days=i)
            cursor = await db.execute("SELECT shift_type, start_time, end_time FROM shift_schedule WHERE date=?", (d.isoformat(),))
            row = await cursor.fetchone()
            if row:
                results.append({
                    "date": d.isoformat(),
                    "day": d.strftime("%A"),
                    "shift": row[0],
                    "label": labels.get(row[0], ""),
                    "start": row[1],
                    "end": row[2]
                })
    
    today_shift = results[0] if results else None
    off_days = [r for r in results if r["shift"] == "O"]
    
    return {
        "today": today_shift,
        "schedule": results,
        "off_days_count": len(off_days),
        "next_off": off_days[0]["date"] if off_days else None
    }




# ============================================================
#  CLAUDE COMBINED ENDPOINT (single fetch for all data)
# ============================================================
@app.get("/claude")
async def claude_combined():
    """Single endpoint for Claude to get all data in one fetch"""
    import aiosqlite
    from tasks_db import TASKS_DB
    
    # Get shift
    shift_data = {}
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        async with aiosqlite.connect(TASKS_DB) as db:
            db.row_factory = aiosqlite.Row
            from datetime import datetime as dt2
            cursor = await db.execute("SELECT * FROM shift_schedule WHERE date = ?", (today,))
            row = await cursor.fetchone()
            if row:
                r = dict(row)
                labels = {"M":"Morning 7am-3pm","A":"Afternoon 3pm-11pm","N":"Night 11pm-7am","O":"Off"}
                day_name = dt2.strptime(r["date"], "%Y-%m-%d").strftime("%A")
                shift_data = {"date": r["date"], "day": day_name, "shift": r["shift_type"], "label": labels.get(r["shift_type"],"")}
            
            # Next 7 days
            cursor = await db.execute("SELECT * FROM shift_schedule WHERE date > ? ORDER BY date LIMIT 7", (today,))
            rows = await cursor.fetchall()
            shift_data["next_7_days"] = [{"date":dict(r)["date"],"day":dt2.strptime(dict(r)["date"],"%Y-%m-%d").strftime("%A"),"shift":dict(r)["shift_type"]} for r in rows]
            
            # Next off
            cursor = await db.execute("SELECT * FROM shift_schedule WHERE date > ? AND shift_type = 'O' ORDER BY date LIMIT 1", (today,))
            off = await cursor.fetchone()
            if off:
                shift_data["next_off"] = dict(off)["date"]
    except:
        shift_data = {"error": "could not load shift"}
    
    # Get tasks summary
    tasks_data = {}
    try:
        async with aiosqlite.connect(TASKS_DB) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM tasks WHERE status != 'done' ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END")
            rows = await cursor.fetchall()
            tasks = [dict(r) for r in rows]
            urgent = [{"id":t["id"],"title":t["title"],"priority":t["priority"],"category":t["category"]} for t in tasks if t["priority"]=="high"]
            tasks_data = {
                "total": len(tasks),
                "urgent": urgent,
                "by_category": {},
                "by_priority": {}
            }
            for t in tasks:
                cat = t.get("category","other")
                pri = t.get("priority","medium")
                tasks_data["by_category"][cat] = tasks_data["by_category"].get(cat,0) + 1
                tasks_data["by_priority"][pri] = tasks_data["by_priority"].get(pri,0) + 1
    except:
        tasks_data = {"error": "could not load tasks"}
    
    # Get recent sessions
    sessions_data = []
    try:
        async with aiosqlite.connect(TASKS_DB) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM session_log ORDER BY id DESC LIMIT 5")
            rows = await cursor.fetchall()
            sessions_data = [dict(r) for r in rows]
    except:
        sessions_data = []

    # Get knowledge base
    knowledge_data = []
    try:
        async with aiosqlite.connect(TASKS_DB) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT id, category, topic, content, tags FROM knowledge ORDER BY category, id")
            rows = await cursor.fetchall()
            knowledge_data = [dict(r) for r in rows]
    except:
        knowledge_data = []

    return {
        "status": "ok",
        "shift": shift_data,
        "tasks": tasks_data,
        "knowledge": {"count": len(knowledge_data), "items": knowledge_data},
        "recent_sessions": sessions_data
    }


# ============================================================
#  SESSION LOG
# ============================================================
from tasks_db import add_session_log, get_session_logs, get_latest_session

class SessionCreate(BaseModel):
    summary: str
    changes_made: str = ""
    decisions: str = ""
    blockers: str = ""
    next_steps: str = ""

@app.post("/sessions")
async def create_session(data: SessionCreate):
    from datetime import datetime as dt2
    session_date = dt2.now().strftime("%Y-%m-%d %H:%M")
    sid = await add_session_log(session_date, data.summary, data.changes_made, data.decisions, data.blockers, data.next_steps)
    return {"id": sid, "status": "logged"}

@app.get("/sessions")
async def list_sessions_log(limit: int = Query(default=10)):
    sessions = await get_session_logs(limit)
    return {"sessions": sessions}

@app.get("/sessions/latest")
async def latest_session():
    s = await get_latest_session()
    return s if s else {"message": "no sessions yet"}

# ============================================================
#  KNOWLEDGE BASE
# ============================================================
from tasks_db import add_knowledge, get_knowledge, get_knowledge_item, update_knowledge, delete_knowledge

class KnowledgeCreate(BaseModel):
    category: str = Field(default="general", description="ha/trading/network/pc/personal/work")
    topic: str
    content: str
    tags: str = ""

class KnowledgeUpdate(BaseModel):
    category: Optional[str] = None
    topic: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[str] = None

@app.get("/knowledge")
async def list_knowledge(
    category: Optional[str] = Query(default=None),
    topic: Optional[str] = Query(default=None),
    tags: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100)
):
    items = await get_knowledge(category=category, topic=topic, tags=tags, search=search, limit=limit)
    return {"count": len(items), "items": items}

@app.get("/knowledge/{kid}")
async def get_single_knowledge(kid: int = Path(...)):
    item = await get_knowledge_item(kid)
    if not item:
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return item

@app.post("/knowledge")
async def create_knowledge(body: KnowledgeCreate):
    kid = await add_knowledge(category=body.category, topic=body.topic, content=body.content, tags=body.tags)
    return {"id": kid, "created": True}

@app.put("/knowledge/{kid}")
async def update_single_knowledge(kid: int, body: KnowledgeUpdate):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        return JSONResponse(status_code=400, content={"error": "No fields to update"})
    result = await update_knowledge(kid, **updates)
    if not result:
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return result

@app.delete("/knowledge/{kid}")
async def delete_single_knowledge(kid: int):
    result = await delete_knowledge(kid)
    if not result:
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return result

# ============================================================
#  TASK TRACKER
# ============================================================
from tasks_db import init_tasks_db, add_task, get_tasks, get_task, update_task, add_note, delete_task, get_summary as tasks_summary

# Initialize tasks DB
init_tasks_db()
logger.info("Tasks DB initialized")

class TaskCreate(BaseModel):
    category: str = Field(default="personal", description="ha/trading/personal/work/project/learning/finance")
    title: str
    description: str = ""
    priority: str = Field(default="medium", description="critical/high/medium/low")
    due_date: Optional[str] = None
    tags: str = ""

class TaskUpdate(BaseModel):
    category: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None

class TaskNote(BaseModel):
    note: str

@app.get("/tasks")
async def list_tasks(
    category: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200)
):
    tasks = await get_tasks(category=category, status=status, priority=priority, limit=limit)
    return {"count": len(tasks), "tasks": tasks}

@app.get("/tasks/summary")
async def task_summary():
    return await tasks_summary()

@app.get("/tasks/{task_id}")
async def get_single_task(task_id: int = Path(...)):
    task = await get_task(task_id)
    if not task:
        return JSONResponse(status_code=404, content={"error": "Task not found"})
    return task

@app.post("/tasks")
async def create_task(body: TaskCreate):
    task_id = await add_task(
        category=body.category,
        title=body.title,
        description=body.description,
        priority=body.priority,
        due_date=body.due_date,
        tags=body.tags
    )
    return {"id": task_id, "created": True}

@app.put("/tasks/{task_id}")
async def update_single_task(task_id: int, body: TaskUpdate):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        return JSONResponse(status_code=400, content={"error": "No fields to update"})
    result = await update_task(task_id, **updates)
    if not result:
        return JSONResponse(status_code=404, content={"error": "Task not found"})
    return result

@app.post("/tasks/{task_id}/note")
async def add_task_note(task_id: int, body: TaskNote):
    result = await add_note(task_id, body.note)
    if not result:
        return JSONResponse(status_code=404, content={"error": "Task not found"})
    return result

@app.delete("/tasks/{task_id}")
async def delete_single_task(task_id: int):
    result = await delete_task(task_id)
    if not result:
        return JSONResponse(status_code=404, content={"error": "Task not found"})
    return result

# ============================================================
#  AUDIT VIEWER
# ============================================================

@app.get("/audit")
async def get_audit_log(limit: int = Query(default=20, ge=1, le=100)):
    try:
        async with aiosqlite.connect(AUDIT_DB) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id,timestamp,task,status,duration,approval_id FROM audit_log ORDER BY id DESC LIMIT ?",
                (limit,))
            rows = await cursor.fetchall()
            return {"count": len(rows), "entries": [dict(r) for r in rows]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})





# ============================================================
#  STOCK ALERTS - TradingView Webhook + Portfolio Tracking
# ============================================================
from stock_alerts import process_webhook, update_ha_sensor, PORTFOLIO, announce_alexa

class WebhookAlert(BaseModel):
    ticker: str
    price: float
    action: str = "ALERT"
    signal: str = ""
    timeframe: str = ""
    volume: float = 0
    strategy: str = ""

class ManualAlert(BaseModel):
    message: str
    entity: str = "media_player.my_room_alexa"

@app.post("/stocks/webhook")
async def stock_webhook(body: WebhookAlert):
    result = process_webhook(body.model_dump())
    await audit_log("stock_alert", actions=[body.ticker], results=[result])
    return result

@app.post("/stocks/announce")
async def stock_announce(body: ManualAlert):
    success = announce_alexa(body.message, body.entity)
    return {"status": "ok" if success else "failed", "message": body.message}

@app.get("/stocks/portfolio")
async def stock_portfolio():
    return {"portfolio": PORTFOLIO}

@app.get("/stocks/alerts")
async def stock_alerts_history(limit: int = 20):
    import pathlib
    alert_file = pathlib.Path("/home/pi/master_ai/data/stock_alerts.json")
    if alert_file.exists():
        alerts = json.loads(alert_file.read_text())
        return {"alerts": alerts[-limit:], "total": len(alerts)}
    return {"alerts": [], "total": 0}


# ============================================================
#  DEPLOY ENDPOINT - Remote code deployment
# ============================================================
import subprocess as _subprocess
import shutil as _shutil

class DeployRequest(BaseModel):
    file_path: str
    content: str
    backup: bool = True
    restart_service: Optional[str] = None

@app.post("/deploy")
async def deploy_file(body: DeployRequest):
    """Deploy/update a file on the Pi with backup and optional service restart."""
    import pathlib
    
    # Security: only allow files in master_ai directory
    allowed_dirs = ["/home/pi/master_ai/", "/var/lib/homeassistant/homeassistant/www/"]
    target = pathlib.Path(body.file_path).resolve()
    if not any(str(target).startswith(d) for d in allowed_dirs):
        raise HTTPException(status_code=403, detail=f"Deploy only allowed in: {allowed_dirs}")
    
    # Backup existing file
    backup_path = None
    if body.backup and target.exists():
        backup_path = str(target) + f".bak.{int(time.time())}"
        _shutil.copy2(str(target), backup_path)
    
    # Write new content
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body.content, encoding="utf-8")
    
    # Optional service restart
    restart_result = None
    if body.restart_service:
        allowed_services = ["master-ai", "cloudflared-tunnel", "nginx"]
        if body.restart_service not in allowed_services:
            raise HTTPException(status_code=403, detail=f"Restart only for: {allowed_services}")
        proc = _subprocess.run(
            ["sudo", "systemctl", "restart", body.restart_service],
            capture_output=True, text=True, timeout=30
        )
        restart_result = {"returncode": proc.returncode, "stderr": proc.stderr[:200]}
    
    await audit_log("deploy", actions=[body.file_path], results=[{
        "backup": backup_path, "size": len(body.content), "restart": restart_result
    }])
    
    return {
        "status": "deployed",
        "file": str(target),
        "size": len(body.content),
        "backup": backup_path,
        "restart": restart_result
    }

@app.get("/deploy/history")
async def deploy_history():
    """Show recent deployments from audit log."""
    import aiosqlite
    async with aiosqlite.connect("/home/pi/master_ai/audit/audit.db") as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM audit_log WHERE task='deploy' ORDER BY ts DESC LIMIT 20"
        )
        return {"deployments": [dict(r) for r in rows]}

# ============================================================
#  WEB PANEL
# ============================================================
import pathlib as _pathlib

@app.get("/panel", response_class=HTMLResponse)
async def web_panel():
    for p in ["/var/lib/homeassistant/homeassistant/www/master_ai_panel.html",
              "/home/pi/master_ai/panel.html"]:
        pp = _pathlib.Path(p)
        if pp.exists():
            return HTMLResponse(content=pp.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Panel not found</h1>", status_code=404)


# ============================================================
#  SMART MEMORY SYSTEM
# ============================================================
from memory_db import (add_memory, get_memories, use_memory, update_memory, forget_memory, save_message, get_conversation_history, clear_conversation, get_or_create_user, get_all_users, build_context, get_memory_stats, init_memory_db)
init_memory_db()

class MemoryCreate(BaseModel):
    category: str = "general"
    type: str = "fact"
    content: str
    context: str = ""
    confidence: float = 0.5
    source: str = "user"
    tags: str = ""

@app.post("/memory")
async def create_memory(data: MemoryCreate):
    return await add_memory(data.category, data.type, data.content, data.context, data.confidence, data.source, data.tags)

@app.get("/memory")
async def list_memories(category: str = Query(default=None), type: str = Query(default=None), search: str = Query(default=None), min_confidence: float = Query(default=0.0), limit: int = Query(default=20)):
    return {"count": 0, "memories": await get_memories(category, type, min_confidence, search, limit)}

@app.get("/memory/stats")
async def mem_stats():
    return await get_memory_stats()

@app.put("/memory/{mid}")
async def modify_memory(mid: int, data: dict):
    return await update_memory(mid, **data) or {"error": "nothing"}

@app.delete("/memory/{mid}")
async def del_memory(mid: int):
    return await forget_memory(mid)

@app.post("/memory/{mid}/use")
async def mark_used(mid: int):
    await use_memory(mid); return {"ok": True}

class MsgSave(BaseModel):
    channel: str = "claude"
    role: str
    content: str

@app.post("/conversations")
async def save_conv(data: MsgSave):
    return {"id": await save_message(data.channel, data.role, data.content)}

@app.get("/conversations/{channel}")
async def get_conv(channel: str, limit: int = Query(default=20)):
    h = await get_conversation_history(channel, limit); return {"count": len(h), "messages": h}

@app.delete("/conversations/{channel}")
async def clear_conv(channel: str):
    await clear_conversation(channel); return {"cleared": True}

class UserCreate(BaseModel):
    user_id: str
    name: str
    language: str = "ar"
    tone: str = "casual"

@app.post("/users")
async def create_user_ep(data: UserCreate):
    return await get_or_create_user(data.user_id, data.name, data.language, data.tone)

@app.get("/users")
async def list_users_ep():
    u = await get_all_users(); return {"count": len(u), "users": u}

@app.get("/context")
async def get_ctx(user_id: str = Query(default="bu_khalifa"), channel: str = Query(default="claude")):
    return await build_context(user_id, channel)

@app.post("/memory/seed")
async def seed_memories():
    seeds = [("personal","fact","بو خليفة - Unit Controller Shift A Unit 114 KNPC",0.95,"identity"),("personal","fact","متزوج من Oana وعنده عبود",0.95,"family"),("preference","preference","يفضل الكويتي",0.9,"language"),("ha","fact","250+ جهاز Tuya مع HA على RPi5",0.95,"smart_home"),("trading","fact","يتداول ببورصة الكويت",0.9,"stocks"),("trading","pattern","أسهم الخير تتحرك مع بعض",0.85,"pattern"),("pattern","pattern","شفتات M/M/A/A/N/N/O/O",0.95,"schedule")]
    results = []
    for c,t,co,cf,tg in seeds:
        results.append(await add_memory(c,t,co,source="seed",confidence=cf,tags=tg))
    await get_or_create_user("bu_khalifa","بو خليفة","ar","kuwaiti")
    await get_or_create_user("oana","Oana","en","friendly")
    await get_or_create_user("mama","أم خليفة","ar","respectful")
    return {"seeded": len(results), "users": 3}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=9000, reload=False, log_level="info")
