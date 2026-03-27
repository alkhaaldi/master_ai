# CLAUDE.md — Master AI Project Instructions
# Claude Code reads this file automatically at the start of every session.

## Project Overview
Master AI is a personal AI assistant running on Raspberry Pi 5, built with FastAPI.
- **Owner:** Salem (بو خليفة) — Unit Controller, KNPC Unit 114 (Hydrocracker)
- **Version:** Check `/health` or `/system/context` — never assume
- **Port:** 9000 | **Tunnel:** https://ai.salem-home.com | **Local:** 192.168.109.123:9000
- **Architecture:** Single-file FastAPI (server.py) + helper modules
- **LLM:** Anthropic native tool_use via chat_v7.py (18 tools)
- **Fast path:** quick_query.py intercepts zero-LLM patterns

## First Step — Every Session
1. Read this file (automatic)
2. Check live state: `curl -s http://localhost:9000/health`
3. If you need full context: `curl -s -H 'X-API-Key: KEY' http://localhost:9000/system/context`
4. Do NOT search previous conversations unless explicitly asked
5. Do NOT assume versions, schema, or component states
6. Read `_tools/OPERATIONAL_ACCESS_MATRIX.md` if the task involves development

## API Authentication
- **GET endpoints:** `X-API-Key` header
- **POST /ssh/run:** `X-API-Key` + `Authorization: Bearer` (same key)
- **/health:** no auth
- **API Key location on RPi:** `~/.master_ai_key`
- **HA Token on RPi:** `~/.ha_token`
- **NEVER** paste keys in chat output or commit them to git

## Directory Structure
```
/var/lib/homeassistant/share/master_ai/   (symlink from /home/pi/master_ai/)
├── server.py          (~7943 lines, main FastAPI)
├── chat_v7.py         (~795 lines, LLM handler)
├── stock_radar.py     (~858 lines, stock radar)
├── quick_query.py     (~646 lines, zero-LLM fast path)
├── tg_intent_router.py (~1144 lines, Telegram routing)
├── _tools/            (dev toolkit — ALWAYS USE THESE)
│   ├── patchers/apply_text_patch.py   ← Python file editing
│   ├── quick_check.py                 ← 12-point health check
│   ├── smoke_test.py                  ← radar field validation
│   ├── db_sanity.py                   ← DB table verification
│   ├── restart_master_ai.sh           ← safe restart (git-aware)
│   ├── OPERATIONAL_ACCESS_MATRIX.md   ← which tool for which task
│   └── ADDING_NEW_DASHBOARD_FIELDS.md ← field addition checklist
├── _archive/          (archived/deprecated code)
├── audit/             (audit databases)
├── data/              (data files)
├── logs/              (log files)
├── venv/              (Python virtual environment)
└── 72 .py modules total
```

## ⚠️ CRITICAL RULES — Never Break These

### Rule 1: Python File Editing — Patch System ONLY
**Every** edit to Python files inside `master_ai/` MUST use:
```bash
cd /var/lib/homeassistant/share/master_ai
python3 _tools/patchers/apply_text_patch.py server.py --old "EXACT_OLD_TEXT" --new "NEW_TEXT" --backup
```
- **NEVER** use `append` on Python files
- **NEVER** do direct file writes (`echo`, `cat >`, `tee`) to Python files
- **NEVER** use heredoc for Python content
- The patch system creates backups and validates syntax

### Rule 2: Post-Change Validation — Always, In Order
After ANY Python change, run these in sequence:
```bash
cd /var/lib/homeassistant/share/master_ai
python3 _tools/quick_check.py          # syntax + service + endpoints + git
python3 _tools/smoke_test.py           # radar fields verification
python3 _tools/db_sanity.py            # DB tables (if DB-related change)
bash _tools/restart_master_ai.sh       # only if restart needed
```

### Rule 3: Git Before Restart
**Always** `git add -A && git commit -m "description"` before any restart or service kill.

### Rule 4: Minimal & Backward-Compatible
- Changes must be **minimal** — no rewrites unless explicitly asked
- Changes must be **backward-compatible** — don't break existing endpoints
- Don't bury errors silently — always log or return a reason

### Rule 5: Dashboard Is NOT Source of Truth
- Dashboard/Chrome is for **visual review only**
- Source of truth: API responses, DB, logs, sensor states

## Operational Access Matrix (Quick Reference)

| Task | Tool | Notes |
|------|------|-------|
| Python files in `master_ai/` | `apply_text_patch.py` | Always. No exceptions. |
| HA YAML / config files | Direct edit or script | Small edits = direct, large = script |
| DB queries / checks | `sqlite3` or `python3` | Use `db_sanity.py` for radar |
| Logs | `journalctl`, `tail` | |
| Git operations | `git` commands | Always commit before restart |
| Service restart | `_tools/restart_master_ai.sh` | |
| API / endpoint tests | `curl` or `quick_check.py` | |
| Radar field verification | `_tools/smoke_test.py` | |

### Prohibited Actions
- `append` on Python files (corrupts indentation)
- Heavy operations inside request handlers (causes timeout)
- Editing dashboard YAML before verifying endpoint works
- `copy/paste` deployment — always git deploy
- Modifying server.py without reading `/system/context` first

## Dashboard Field Addition — Mandatory Checklist
When adding any new field visible in the HA dashboard:
1. **Endpoint first** — Add field to the correct endpoint in server.py
2. **Test JSON** — `curl` the endpoint, verify field appears with correct type
3. **configuration.yaml** — Add to `json_attributes` in the REST sensor
4. **Sensor check** — Verify in HA Developer Tools → States
5. **Dashboard YAML** — Only NOW update the dashboard card
6. **Visual check** — Open in browser, test empty/error states

Full reference: `_tools/ADDING_NEW_DASHBOARD_FIELDS.md`

## Home Assistant Integration

### Dashboard
- **YAML location:** `/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml`
- **8 pages**, all native HA cards only
- **Allowed cards:** vertical-stack, grid, markdown, button (with card_mod)
- **BANNED cards:** custom:stack-in-card, custom:mushroom-*, custom:button-card, custom:layout-card

### Pages
1. **Home** (master-ai) — Hero + Priority Cards + Top 3 Stocks + Actions + Nav
2. **Trading** (sub-radar) — Market Pulse + Decision Board + Daily Context + 30m + Watchlist
3. **Calendar** (sub-calendar-tasks) — Events + Tasks + Shift
4. **Home Control** (sub-home) — Lights/AC/Covers + Temperature + Rooms
5. **Assistant** (sub-assistant) — Memory + Cost + Requests + Git
6. **System** (sub-system-health) — CPU/RAM/Disk/Temp + Git
7. **Email** (sub-email) — Email list + priority badges
8. **News** (sub-news) — News digest

### Sensors (in configuration.yaml)
- `sensor.master_ai_dashboard` — REST `/dashboard` every 60s (~35 attributes)
- `sensor.master_ai_extended` — REST `/dashboard/extended` every 120s (~24 attributes)
- `sensor.master_ai_radar` — REST `/dashboard/radar` every 120s (dedicated, ~4.7KB)
- Template sensors: ac_house_avg_temperature, ac_active_units_count, ac_hottest_room, ac_coldest_room

### Arabic Text in YAML — Encoding Rule
Arabic in dashboard YAML must be written via proper UTF-8 file write.
**BANNED:** Python `\uXXXX` escapes in YAML, SSH echo/heredoc for Arabic content.
**Workflow:** Write file → copy via Samba → apply via rebuild script.

### Entity Naming Rules
- **Fan domain:** شفاط (exhaust) ≠ منقي (purifier) ≠ معطر (freshener). NEVER say مروحة.
- **Fixed entities (never rename):**
  - نور الباركينج = `light.parking_light_switch_1` (one switch only)
  - نور سلم المؤجرين = `light.drj_lmwjryn_ldwr_lthny_switch_1` + `light.drj_lmwjryn_mm_lsnsyr_switch_1`
- **Always verify entity IDs** before using them — don't assume

## Dashboard Design Philosophy
Every dashboard page is a **Control Surface**, not a formatted report:
1. **Pulse/Hero** — Most important state RIGHT NOW
2. **Decision/Summary Cards** — Top 1-3 actionable items
3. **Detail Sections** — Organized, limited details
4. **Footer/Diagnostics** — Secondary info

**Rules:**
- Most important info visible within **3 seconds**
- No markdown dumps or long text walls
- No burying key info in text blocks
- Top 3-5 items shown first, rest in lighter detail section
- Visual hierarchy > information quantity

## Priority Engine (PE)
- `build_priority_engine()` in server.py — cross-domain priority ranking
- 5 domains: trading, calendar/tasks, home, email, system
- Top 3 priorities with diversity rule (max 2 per domain)
- Assistant Surface Layer (A1): action reframing with 12 templates
- Temporal Intelligence (A2): time-aware weighting by time_mode
- Change Tracking: new/resolved/escalated diffs between cycles
- All PE functions prefixed `_pe_` in server.py
- All Assistant Surface functions prefixed `_as_` in server.py

## Trading & KSE Context
- Market: Kuwait Stock Exchange (KSE)
- Never assume user's current positions — prices change constantly
- Pine Script: **code only**, no HTML. Simple > complex. TradingView > Python backtest.
- Strategies: CLEANING V3 (SSA+VWAP+Trail=117%), SENERGY V5 (HH+HL+RSI↑+Trail=104%), INOVEST V5 (HMA-Kalman+Trail)
- Position sizing: small TF Trail@4%/1.5%/SL3%, daily Trail@12%/2%/SL4%
- Radar architecture: 30m = trigger/event, 1D = daily context/trusted review
- Analysis framework: Advanced Elliott Wave (Neo Wave + Fibonacci + Hurst Cycles)

## Databases
- **Schema version:** Check `/system/context`
- **audit.db:** ~30 tables (audit_log, traces, cost tracking, etc.)
- **life.db:** ~9 tables (calendar_events, tasks, etc.)
- **radar.db, kse_data.db, daily_snapshots.db:** Trading data
- Verify with: `python3 _tools/db_sanity.py`

## Service Management
```bash
# Check status
sudo systemctl status master-ai.service

# Safe restart (handles git commit)
bash _tools/restart_master_ai.sh

# View recent logs
journalctl -u master-ai.service -n 50 --no-pager

# Git status
cd /var/lib/homeassistant/share/master_ai && git log --oneline -5
```

## Network
- RPi: 192.168.109.123 (user: pi)
- HA: same RPi, port 8123
- Router: 192.168.108.1 (BE800)
- NVR: 192.168.108.44
- Network: /22 subnet

## Language & Communication
- Salem communicates primarily in **Kuwaiti Arabic dialect**
- When mixing Arabic + English: English words on **separate line** from Arabic text
- Respond in the same language the user uses

## Shift Schedule
- AABBCCDD rotation (morning/afternoon/night/off)
- Epoch: 2024-01-04
- Tool available: `get_shift` in chat_v7.py

## Decision Template — Use Before Every Development Task
```
### Decision
- Task:
- File type:
- Tool choice:
- Why:
- Fallback if it fails:

### Plan
- Files to modify:
- Execution method:
- Validation method:
```

## Post-Task Checklist
After completing any task, always report:
1. Files modified (with paths)
2. Validation results (quick_check, smoke_test output)
3. Final outcome (success/partial/failed)
4. Any follow-up needed
