# Master AI Transformation Plan — From Dashboard to Personal Assistant
> Generated: 2026-03-21 | Execute on RPi via Claude Code
> Goal: Transform Master AI from a monitoring dashboard into an active personal assistant

---

## IMPORTANT: Read Before Starting
```bash
cat CLAUDE.md
cat _tools/OPERATIONAL_ACCESS_MATRIX.md
```

## PRE-FLIGHT
```bash
sudo cp /var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml \
        /var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml.bak_v12
git add -A && git commit -m "backup: pre-transformation"
```

---

## PHASE 1: Kill Dead Code (clean the house first)

### 1A. Remove dead TG commands from server.py
Scan `tg_handle_command()` function and identify commands that reference non-existent functions or empty handlers.

These commands are likely dead (verify each before removing):
- `/habits` — check if habits handler exists
- `/patterns` — check if patterns handler exists  
- `/timeline` — check if timeline handler exists
- `/guardian` — check if guardian handler exists
- `/approvals` — check if approvals handler exists
- `/occasions` — check if occasions handler exists
- `/scenes`, `/scenes1`, `/scenes2`, `/scenes_all` — check if scenes handlers exist
- `/find` — check if find handler exists
- `/corrections` — check if correction handler exists
- `/learn` — check if learn handler exists

**Method:**
```bash
# For each suspect command, check if the handler function exists:
grep -n 'def.*habits\|async def.*habits' server.py *.py
# If nothing meaningful found → the command is dead
```

**For each dead command:** Don't delete — comment out with `# DISABLED: unused` prefix and a date. This way we can restore if needed.

**Validation:**
```bash
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
```

### 1B. Fix audit logging — 97% "unknown" route_type
The audit_log table has 1222 entries but 1188 are `route_type = "unknown"`.

**Find the audit logging code:**
```bash
grep -n 'route_type\|audit_log\|INSERT.*audit' server.py | head -20
```

**Fix:** Ensure every request path sets `route_type` properly:
- TG commands → `route_type = "tg_command"`
- Dashboard API → `route_type = "dashboard_api"`
- SSH → `route_type = "ssh"`
- LLM chat → `route_type = "llm_chat"`
- Quick query → `route_type = "quick_query"`
- Health/status → `route_type = "health"`

**Also fix cost tracking:**
```bash
grep -n 'cost_today\|cost_total\|duration_ms' server.py | head -20
```
The current cost calculation estimates from `duration_ms` which is meaningless. Instead:
- Track actual `input_tokens` and `output_tokens` from Anthropic API responses
- Calculate cost: `(input_tokens * 0.003 + output_tokens * 0.015) / 1000` for Sonnet
- Store in audit_log as `input_tokens`, `output_tokens`, `cost_usd`

### 1C. Create expenses table (it doesn't exist!)
```bash
sqlite3 /var/lib/homeassistant/share/master_ai/data/life.db ".tables" | grep expense
```
If missing, the /add_expense and /expenses commands crash silently. Either:
- Create the table and wire it properly, OR
- Disable those commands with `# DISABLED` comments

**If creating:**
```sql
CREATE TABLE IF NOT EXISTS expense_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    currency TEXT DEFAULT 'KWD',
    category TEXT,
    description TEXT,
    date TEXT DEFAULT (date('now')),
    created_at TEXT DEFAULT (datetime('now'))
);
```

### 1D. Fix structured memory
```bash
sqlite3 /var/lib/homeassistant/share/master_ai/data/structured_memory.db ".tables"
sqlite3 /var/lib/homeassistant/share/master_ai/data/structured_memory.db "SELECT COUNT(*) FROM facts" 2>/dev/null
```
If facts table is gone, recreate it. Check `chat_v7.py` memory tools to see what schema they expect.

**Validation after Phase 1:**
```bash
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
bash _tools/restart_master_ai.sh
# Test a few commands
curl -s -X POST -H "Content-Type: application/json" \
  -H "X-API-Key: $(cat ~/.master_ai_key)" \
  -H "Authorization: Bearer $(cat ~/.master_ai_key)" \
  http://localhost:9000/dashboard/cmd -d '{"command":"/stats"}'
git add -A && git commit -m "phase1: clean dead code, fix audit logging, fix expenses table, fix structured memory"
```

---

## PHASE 2: Email → Action Pipeline

### 2A. Auto-create tasks from KNPC logbook emails
When a logbook email arrives (subject contains "logbook" or "Controller logbook"), auto-create a task:
- Title: "راجع logbook: [date] [shift]"
- Priority: high (1)
- Category: work
- Due: today + 4 hours

**Implementation:**
Find the email processing code:
```bash
grep -n 'def.*inbox\|def.*email\|def.*process_email' server.py tg_email.py inbox_engine.py | head -20
```

Add a function `_auto_create_tasks_from_emails()` that:
1. Runs after email fetch
2. Checks each new high-priority email
3. If subject matches logbook pattern → create task via task_engine
4. If subject matches meeting invite → create task "Prepare for: [meeting name]"
5. Stores processed email IDs to avoid duplicates

**Wire into the email fetch cycle** (wherever inbox is refreshed).

### 2B. Add "convert to task" logic in Priority Engine
When PE detects `email_high > 0`, the action should include a task creation suggestion:
```python
"action_label": "راجع البريد أو حوّله لمهمة"
```

**Validation:**
```bash
# Send a test: does a logbook email generate a task?
curl -s -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000/dashboard/extended | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print('Tasks:', len(d.get('tasks_list',[])))"
```

---

## PHASE 3: Trade Auto-Logging

### 3A. Wire TradingView webhook → journal
The TradingView webhook bridge already exists (`tradingview_bridge.py`). Check:
```bash
grep -n 'webhook\|tradingview\|tv_' server.py | head -20
ls -la tradingview_bridge.py 2>/dev/null
```

**Goal:** When a TradingView alert fires (buy/sell signal), auto-log it in the trades table.

Find the webhook handler:
```bash
grep -n 'webhook\|@app.*webhook' server.py | head -10
```

Add logic after webhook processing:
```python
# After processing TV webhook signal
if signal_type in ("buy", "sell", "entry", "exit"):
    from journal_engine import record_trade
    record_trade(
        symbol=signal["symbol"],
        action=signal_type,
        price=signal["price"],
        quantity=signal.get("quantity", 0),
        strategy=signal.get("strategy", "TV Alert"),
        entry_reason=f"TradingView: {signal.get('message', '')}",
        source="tradingview_webhook"
    )
```

### 3B. Verify journal_engine works
```bash
python3 -c "
from journal_engine import record_trade
# Test with a dummy trade
result = record_trade('TEST', 'buy', 100.0, 1000, 'Test Strategy', 'Testing', 'manual')
print('Trade recorded:', result)
"
```

If record_trade doesn't exist or fails, fix it.

### 3C. Daily trade review via TG
Check if `/trade_review` command works:
```bash
grep -n 'trade_review' server.py
```
This should summarize today's trades. If broken, fix it.

**Validation:**
```bash
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
bash _tools/restart_master_ai.sh
git add -A && git commit -m "phase3: wire TV webhook to journal, verify trade auto-logging"
```

---

## PHASE 4: Fix Dashboard Data Quality

### 4A. Fix tool_usage tracking
The System page shows tool_usage but it's empty/wrong.
```bash
grep -n 'tool_usage' server.py | head -10
```
Fix so it properly counts: ha_get_state, ha_call_service, ssh_run, http_request, memory_search, calendar_*, task_* calls.

### 4B. Fix route_type in existing audit entries
```sql
-- Update existing "unknown" entries based on patterns in the request
UPDATE audit_log SET route_type = 'tg_command' WHERE route LIKE '/tg%' AND route_type = 'unknown';
UPDATE audit_log SET route_type = 'dashboard_api' WHERE route LIKE '/dashboard%' AND route_type = 'unknown';
UPDATE audit_log SET route_type = 'health' WHERE route LIKE '/health%' AND route_type = 'unknown';
```

### 4C. Add real token/cost tracking to chat_v7.py
Find where Anthropic API response is received:
```bash
grep -n 'response\|completion\|usage\|tokens' chat_v7.py | head -20
```
Extract `usage.input_tokens` and `usage.output_tokens` from the response. Pass to audit logger.

**Validation:**
```bash
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
bash _tools/restart_master_ai.sh
# Test: send a TG message and check audit_log
sqlite3 data/audit.db "SELECT route_type, COUNT(*) FROM audit_log GROUP BY route_type ORDER BY COUNT(*) DESC"
git add -A && git commit -m "phase4: fix tool_usage, route_type tracking, real cost tracking"
```

---

## PHASE 5: Version Bump + Context Update

### 5A. Bump version
```python
# In server.py, change:
VERSION = "8.0.0"
# To:
VERSION = "8.3.0"
```

### 5B. Update CLAUDE_CONTEXT.md
Add all changes from this transformation:
- Phase 1: dead code cleanup, audit fix, expenses table, memory fix
- Phase 2: email → task pipeline
- Phase 3: trade auto-logging
- Phase 4: data quality fixes
- Version bump to 8.3.0

### 5C. Final validation
```bash
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
python3 _tools/db_sanity.py

# Full endpoint check
for ep in /health /dashboard /dashboard/extended /dashboard/radar; do
  echo "=== $ep ==="
  curl -s -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000$ep | python3 -c "import json,sys; d=json.load(sys.stdin); print('OK -', len(d), 'keys')" 2>/dev/null || echo "FAIL"
done

git add -A && git commit -m "v8.3.0: transformation - active assistant with email→tasks, trade logging, clean code, real metrics"
```

---

## EXECUTION ORDER
```
1. PRE-FLIGHT (backup)
2. PHASE 1: Kill dead code + fix audit + fix expenses + fix memory
3. Test + commit
4. PHASE 2: Email → task pipeline
5. Test + commit
6. PHASE 3: Trade auto-logging
7. Test + commit
8. PHASE 4: Fix data quality
9. Test + commit
10. PHASE 5: Version bump + context update + final validation
11. Final commit
```

## RULES
- server.py changes: ONLY via `_tools/patchers/apply_text_patch.py`
- Test after EACH phase — don't proceed if tests fail
- git commit after each phase
- backward compatible — don't break working features
- Comment out dead code, don't delete it (use `# DISABLED: unused [date]`)
- Log everything — no silent failures
