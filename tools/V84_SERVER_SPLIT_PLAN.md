# Master AI v8.4 — Server Split + Smart Features
> Generated: 2026-03-21 | Priority-ordered phases for Claude Code
> Current: server.py = 9,691 lines, 119 endpoints, 121 TG commands

---

## PRE-FLIGHT
```bash
cat CLAUDE.md
cat _tools/OPERATIONAL_ACCESS_MATRIX.md
sudo cp /var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml \
        /var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml.bak_v12_post
git add -A && git commit -m "backup: pre-v8.4 server split"
```

---

## PHASE 1: Extract Priority Engine + Assistant Surface → priority_engine.py
> RISK: LOW — these functions are self-contained with clear boundaries
> SIZE: ~1,258 lines (lines 7822-9080 in server.py)
> IMPACT: server.py drops from 9,691 → ~8,433 lines

### What to extract:
All functions that start with `_pe_` or `_as_` or `build_priority` or `build_assistant`:

```bash
grep -n 'def _pe_\|def _as_\|def build_priority\|def build_assistant' server.py
```

These include:
- `_pe_minutes_since()`, `_pe_get_extended_snapshot()`, `_pe_get_radar_snapshot()`
- `_pe_extract_trading()`, `_pe_extract_calendar()`, `_pe_extract_home()`, `_pe_extract_email()`, `_pe_extract_system()`
- `build_priority_engine()`, `_pe_build_empty_state()`, `_pe_make_summary()`
- `_pe_last_state` global, `_pe_compute_changes()`
- `build_assistant_surface()`, `_as_reframe_priority()`, `_as_compute_temporal_context()`, `_as_apply_temporal_weight()`
- `_ACTION_TEMPLATES`, `_TEMPORAL_WEIGHTS`

### Method:
1. **Create `priority_engine.py`** with all the PE/AS functions
2. **Add necessary imports** at the top (datetime, logging, etc.)
3. **Identify dependencies**: these functions call into dashboard data — they receive `dash_data` as parameter, so they're already decoupled
4. **In server.py**: replace the entire PE/AS block with:
   ```python
   from priority_engine import build_priority_engine, build_assistant_surface
   ```
5. **Move `_pe_last_state` global** to priority_engine.py (it's module-level state)

### Step-by-step:
```bash
# 1. Find exact line range
grep -n 'def _pe_\|def _as_\|def build_priority\|def build_assistant\|_ACTION_TEMPLATES\|_TEMPORAL_WEIGHTS\|_pe_last_state' server.py | head -30

# 2. Extract the block to a new file
# Use sed to extract lines, then clean up

# 3. Create priority_engine.py with proper header
# 4. Patch server.py to import from priority_engine instead
# 5. Test
python3 -c "from priority_engine import build_priority_engine, build_assistant_surface; print('OK')"
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
bash _tools/restart_master_ai.sh

# 6. Verify PE still works
curl -s -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000/dashboard | python3 -c "
import json,sys; d=json.load(sys.stdin)
pe = d.get('priority_engine',{})
asf = d.get('assistant_surface',{})
print('PE top:', pe.get('top_priority',{}).get('title','EMPTY'))
print('AS top:', asf.get('top_action',{}).get('headline','EMPTY'))
print('PE count:', len(pe.get('priorities',[])))
"
```

### Validation:
- `python3 _tools/quick_check.py` passes
- `python3 _tools/smoke_test.py` passes
- `/dashboard` returns valid priority_engine and assistant_surface
- No import errors in logs

```bash
git add -A && git commit -m "refactor: extract priority_engine.py (~1258 lines from server.py)"
```

---

## PHASE 2: Extract Dashboard API → dashboard_api.py
> RISK: MEDIUM — endpoints are called by HA sensors, must keep exact same paths
> SIZE: ~600-800 lines (all /dashboard/* endpoints + helper functions)
> IMPACT: server.py drops from ~8,433 → ~7,600 lines

### What to extract:
All `/dashboard/*` endpoints and their helper functions:

```bash
grep -n '@app.*dashboard\|def.*dashboard' server.py | head -20
```

These include:
- `@app.get("/dashboard")` — main dashboard endpoint
- `@app.get("/dashboard/extended")` — extended data endpoint  
- `@app.get("/dashboard/radar")` — radar data endpoint
- `@app.post("/dashboard/cmd")` — command execution
- `@app.get("/dashboard/jobs")` — job tracking
- `_dashboard_jobs` deque
- Helper functions used only by dashboard endpoints

### Method:
1. **Create `dashboard_api.py`** as a FastAPI Router:
   ```python
   from fastapi import APIRouter, Request
   router = APIRouter()
   
   @router.get("/dashboard")
   async def ha_dashboard():
       ...
   ```
2. **In server.py**: replace endpoints with:
   ```python
   from dashboard_api import router as dashboard_router
   app.include_router(dashboard_router)
   ```
3. **Dashboard endpoints call** `build_priority_engine()` and other functions — pass them as dependencies or import from their modules

### CRITICAL: Keep exact same URL paths
HA sensors poll these endpoints every 60-120 seconds. If the paths change, the dashboard breaks.

### Validation:
```bash
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
bash _tools/restart_master_ai.sh

# Test all 3 dashboard endpoints
for ep in /dashboard /dashboard/extended /dashboard/radar; do
  STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000$ep)
  echo "$ep: $STATUS"
done

# Test dashboard/cmd
curl -s -X POST -H "Content-Type: application/json" \
  -H "X-API-Key: $(cat ~/.master_ai_key)" \
  -H "Authorization: Bearer $(cat ~/.master_ai_key)" \
  http://localhost:9000/dashboard/cmd -d '{"command":"/ping"}'
```

```bash
git add -A && git commit -m "refactor: extract dashboard_api.py (~700 lines from server.py)"
```

---

## PHASE 3: Extract TG Command Dispatch → tg_dispatch.py
> RISK: HIGH — this is the largest block and most interconnected
> SIZE: ~1,572 lines (lines 4429-6001, tg_handle_command function)
> IMPACT: server.py drops from ~7,600 → ~6,000 lines
> APPROACH: Extract carefully — this function calls many other modules

### What to extract:
The massive `tg_handle_command()` function (1,572 lines of if/elif chains):

```bash
grep -n 'async def tg_handle_command' server.py
```

### Method:
1. **Create `tg_dispatch.py`** containing `tg_handle_command()` and its direct helpers
2. **Map all dependencies**: this function calls functions from:
   - `tg_email.py` (cmd_inbox, etc.)
   - `tg_stocks.py` (cmd_stocks, cmd_price)
   - `stock_radar.py` (tg_radar_*)
   - `calendar_engine.py` 
   - `task_engine.py`
   - `journal_engine.py`
   - `brain_core.py`
   - `chat_v7.py`
   - And server.py globals/functions
3. **For server.py dependencies**: pass them as parameters or create a shared context module
4. **In server.py**: replace with:
   ```python
   from tg_dispatch import tg_handle_command
   ```

### CRITICAL warnings:
- `tg_handle_command` uses many globals from server.py (RADAR_OK, TG_STOCKS_OK, etc.)
- These flags need to be accessible — either pass as params or create a `globals_registry.py`
- Test EVERY command category after extraction, not just one

### Validation:
```bash
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
bash _tools/restart_master_ai.sh

# Test commands from different categories
for cmd in /ping /shift /status /me /stocks /radar_status; do
  echo "Testing $cmd..."
  curl -s -X POST -H "Content-Type: application/json" \
    -H "X-API-Key: $(cat ~/.master_ai_key)" \
    -H "Authorization: Bearer $(cat ~/.master_ai_key)" \
    http://localhost:9000/dashboard/cmd -d "{\"command\":\"$cmd\"}"
  sleep 2
done

# Check jobs
curl -s -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000/dashboard/jobs | python3 -c "
import json,sys
jobs = json.load(sys.stdin)['jobs']
for j in jobs[-6:]:
    print(f\"{j['command']}: {j['status']}\")
"
```

```bash
git add -A && git commit -m "refactor: extract tg_dispatch.py (~1572 lines from server.py)"
```

---

## PHASE 4: Trade Confirmation via Telegram (خيار 2)
> After split is done, add the smart trade confirmation feature

### What to build:
When a TradingView webhook signal arrives (buy/sell), instead of silently logging:
1. Send a Telegram message to the user with the signal details
2. Include inline keyboard buttons: "شريت ✅" / "تجاهلت ❌"
3. If user confirms → record_trade() in journal with actual entry
4. If user ignores/rejects → log as "signal_only" (not a real trade)

### Implementation:
```bash
grep -n 'def.*webhook\|async def.*webhook' server.py tradingview_bridge.py
```

Find where webhook signals are processed. After the existing auto-log code (Phase 3 of transformation), add:

```python
async def _send_trade_confirmation(signal: dict):
    """Send TG message with inline keyboard for trade confirmation."""
    symbol = signal.get("symbol", "?")
    price = signal.get("price", 0)
    action = signal.get("type", "signal")  # buy/sell
    
    text = (
        f"📡 *إشارة {action}*\n\n"
        f"*{symbol}* @ {price}\n"
        f"الاستراتيجية: {signal.get('strategy', '—')}\n"
        f"الوقت: {signal.get('time', '—')}\n\n"
        f"هل نفذت الصفقة؟"
    )
    
    # Inline keyboard
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "شريت ✅", "callback_data": f"trade_confirm:{symbol}:{price}:{action}"},
                {"text": "تجاهلت ❌", "callback_data": f"trade_skip:{symbol}:{price}:{action}"}
            ]
        ]
    }
    
    # Send via Telegram Bot API
    import httpx
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TG_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown",
                "reply_markup": keyboard
            }
        )
```

Then add a callback query handler:
```python
# In the TG update handler, add callback_query processing
if "callback_query" in update:
    data = update["callback_query"]["data"]
    if data.startswith("trade_confirm:"):
        parts = data.split(":")
        symbol, price, action = parts[1], float(parts[2]), parts[3]
        from journal_engine import record_trade
        record_trade(symbol, action, price, 0, "TV Webhook", "User confirmed via TG", "telegram_confirm")
        # Answer callback
        await answer_callback("✅ تم تسجيل الصفقة")
    elif data.startswith("trade_skip:"):
        await answer_callback("⏭ تم التجاهل")
```

### Validation:
```bash
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
bash _tools/restart_master_ai.sh

# Test: simulate a webhook
curl -s -X POST -H "Content-Type: application/json" \
  http://localhost:9000/webhook/event/... \
  -d '{"type":"buy","symbol":"TEST","price":100,"strategy":"Test"}'
# Check: did TG message arrive with buttons?
```

```bash
git add -A && git commit -m "feat: trade confirmation via TG inline keyboard buttons"
```

---

## PHASE 5: Version Bump + Context Update

### 5A. Bump to v8.4.0
### 5B. Update CLAUDE_CONTEXT.md with:
- server.py new line count (should be ~6,000 after split)
- New modules: priority_engine.py, dashboard_api.py, tg_dispatch.py
- Trade confirmation feature
- Updated architecture section

### 5C. Final validation
```bash
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
python3 _tools/db_sanity.py

for ep in /health /dashboard /dashboard/extended /dashboard/radar; do
  echo "=== $ep ==="
  curl -s -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000$ep | python3 -c "import json,sys; d=json.load(sys.stdin); print('OK -', len(d), 'keys')" 2>/dev/null
done

wc -l server.py  # Should be ~6,000

git add -A && git commit -m "v8.4.0: server split complete + trade confirmation"
```

---

## EXECUTION ORDER
```
Phase 1: Extract priority_engine.py (LOW risk, ~1258 lines) → test → commit
Phase 2: Extract dashboard_api.py (MEDIUM risk, ~700 lines) → test → commit
Phase 3: Extract tg_dispatch.py (HIGH risk, ~1572 lines) → test → commit
Phase 4: Trade confirmation TG buttons → test → commit
Phase 5: Version 8.4.0 + context update → final commit
```

## RULES
- server.py: use `_tools/patchers/apply_text_patch.py` for removing blocks
- New files: create directly (they're new, not editing existing)
- Test after EACH phase — if Phase 2 fails, don't start Phase 3
- git commit after each phase
- Keep exact same API paths — HA sensors depend on them
- Keep exact same function signatures — other modules import from server.py
- If a phase is too risky, stop and report what happened

## SUCCESS CRITERIA
- server.py under 6,500 lines
- All 3 new modules import and work
- All endpoints return same data as before
- TG commands still work
- Dashboard renders correctly
- Trade confirmation sends TG message with buttons
