"""
plan_engine.py - Stateful Plans for Master AI
Phase 3C: Short-lived plans that persist across messages
Plans have triggers (time/state/event) and execute via chat_v7 tools
"""
import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta

log = logging.getLogger("plan_engine")

DB_PATH = "data/audit.db"
MAX_ACTIVE_PLANS = 10

def _db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def ensure_table():
    c = _db()
    c.execute("""CREATE TABLE IF NOT EXISTS plans (
        plan_id TEXT PRIMARY KEY,
        goal TEXT NOT NULL,
        steps TEXT DEFAULT '[]',
        triggers TEXT DEFAULT '[]',
        status TEXT DEFAULT 'active',
        created_at TEXT,
        last_run TEXT,
        next_check TEXT,
        run_count INTEGER DEFAULT 0,
        max_runs INTEGER DEFAULT 0,
        result_log TEXT DEFAULT '[]',
        meta TEXT DEFAULT '{}'
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_plans_status ON plans (status)")
    c.commit()
    c.close()
    log.info("[PlanEngine] Table ensured")

def add_plan(goal, steps=None, triggers=None, max_runs=0, meta=None):
    c = _db()
    active = c.execute("SELECT COUNT(*) FROM plans WHERE status='active'").fetchone()[0]
    if active >= MAX_ACTIVE_PLANS:
        c.close()
        return None, f"Max {MAX_ACTIVE_PLANS} active plans"
    plan_id = f"plan_{int(time.time())}"
    now = datetime.utcnow().isoformat()
    c.execute(
        "INSERT INTO plans (plan_id, goal, steps, triggers, status, created_at, max_runs, meta) VALUES (?,?,?,?,?,?,?,?)",
        (plan_id, goal, json.dumps(steps or []), json.dumps(triggers or []),
         "active", now, max_runs, json.dumps(meta or {}))
    )
    c.commit()
    c.close()
    log.info(f"[PlanEngine] Added: {plan_id} - {goal}")
    return plan_id, "ok"

def list_plans(status="active"):
    c = _db()
    rows = c.execute(
        "SELECT plan_id, goal, status, created_at, last_run, run_count, max_runs FROM plans WHERE status=? ORDER BY created_at DESC",
        (status,)
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]

def get_plan(plan_id):
    c = _db()
    r = c.execute("SELECT * FROM plans WHERE plan_id=?", (plan_id,)).fetchone()
    c.close()
    return dict(r) if r else None

def pause_plan(plan_id):
    c = _db()
    c.execute("UPDATE plans SET status='paused' WHERE plan_id=? AND status='active'", (plan_id,))
    changed = c.total_changes
    c.commit()
    c.close()
    return changed > 0

def resume_plan(plan_id):
    c = _db()
    c.execute("UPDATE plans SET status='active' WHERE plan_id=? AND status='paused'", (plan_id,))
    changed = c.total_changes
    c.commit()
    c.close()
    return changed > 0

def complete_plan(plan_id, result=""):
    c = _db()
    c.execute("UPDATE plans SET status='completed', meta=json_set(COALESCE(meta,'{}'), '$.result', ?) WHERE plan_id=?",
              (result, plan_id))
    c.commit()
    c.close()

def delete_plan(plan_id):
    c = _db()
    c.execute("DELETE FROM plans WHERE plan_id=?", (plan_id,))
    c.commit()
    c.close()

def record_run(plan_id, result_text):
    c = _db()
    now = datetime.utcnow().isoformat()
    plan = c.execute("SELECT run_count, max_runs, result_log FROM plans WHERE plan_id=?", (plan_id,)).fetchone()
    if not plan:
        c.close()
        return
    new_count = plan["run_count"] + 1
    logs = json.loads(plan["result_log"] or "[]")
    logs.append({"time": now, "result": result_text[:200]})
    logs = logs[-20:]  # keep last 20
    updates = {"last_run": now, "run_count": new_count, "result_log": json.dumps(logs)}
    # Auto-complete if max_runs reached
    if plan["max_runs"] > 0 and new_count >= plan["max_runs"]:
        updates["status"] = "completed"
    c.execute(
        "UPDATE plans SET last_run=?, run_count=?, result_log=?, status=COALESCE(?, status) WHERE plan_id=?",
        (updates["last_run"], updates["run_count"], updates["result_log"],
         updates.get("status"), plan_id)
    )
    c.commit()
    c.close()

def check_time_trigger(trigger):
    """Check if a time trigger should fire now."""
    t = trigger.get("type")
    if t != "time":
        return False
    # Cron-like: {"type":"time", "hour":22, "minute":0}
    now = datetime.now()
    hour = trigger.get("hour")
    minute = trigger.get("minute", 0)
    if hour is not None and now.hour == hour and abs(now.minute - minute) <= 2:
        return True
    # Interval: {"type":"time", "interval_minutes": 60}
    interval = trigger.get("interval_minutes")
    if interval:
        return False  # interval checked in get_due_plans with last_run
    return False

def check_state_trigger(trigger, ha_states):
    """Check if a state trigger matches current HA state."""
    if trigger.get("type") != "state":
        return False
    entity = trigger.get("entity_id", "")
    expected = trigger.get("state")
    for s in ha_states:
        if s.get("entity_id") == entity:
            if expected and s.get("state") == expected:
                return True
    return False

def get_due_plans(ha_states=None):
    """Return active plans whose triggers match now."""
    conn = _db()
    active = conn.execute("SELECT * FROM plans WHERE status='active'").fetchall()
    conn.close()
    due = []
    now = datetime.utcnow()
    for p in active:
        triggers = json.loads(p["triggers"] or "[]")
        if not triggers:
            continue
        last_run = p["last_run"]
        for t in triggers:
            if t.get("type") == "time":
                interval = t.get("interval_minutes")
                if interval:
                    # Check if enough time passed since last run
                    if last_run:
                        try:
                            lr = datetime.fromisoformat(last_run)
                            elapsed = (now - lr).total_seconds() / 60
                            if elapsed < interval:
                                continue
                        except Exception:
                            pass
                    due.append(dict(p))
                    break
                elif check_time_trigger(t):
                    # Fixed time trigger (hour/minute)
                    if last_run:
                        try:
                            lr = datetime.fromisoformat(last_run)
                            if (now - lr).total_seconds() < 300:
                                continue  # skip if ran less than 5 min ago
                        except Exception:
                            pass
                    due.append(dict(p))
                    break
            if t.get("type") == "state" and ha_states and check_state_trigger(t, ha_states):
                due.append(dict(p))
                break
    return due

def format_plans_list(plans):
    """Format plans for TG display."""
    if not plans:
        return "\u2705 \u0645\u0627 \u0641\u064a\u0647 \u062e\u0637\u0637 \u0646\u0634\u0637\u0629"
    lines = ["\U0001f4cb *\u0627\u0644\u062e\u0637\u0637 \u0627\u0644\u0646\u0634\u0637\u0629:*", ""]
    status_emoji = {"active": "\u25b6\ufe0f", "paused": "\u23f8\ufe0f", "completed": "\u2705", "failed": "\u274c"}
    for p in plans:
        emoji = status_emoji.get(p["status"], "\u2753")
        runs = f" ({p['run_count']}x)" if p["run_count"] > 0 else ""
        lines.append(f"{emoji} {p['plan_id']}: {p['goal']}{runs}")
    return "\n".join(lines)

def get_stats():
    c = _db()
    total = c.execute("SELECT COUNT(*) FROM plans").fetchone()[0]
    active = c.execute("SELECT COUNT(*) FROM plans WHERE status='active'").fetchone()[0]
    completed = c.execute("SELECT COUNT(*) FROM plans WHERE status='completed'").fetchone()[0]
    paused = c.execute("SELECT COUNT(*) FROM plans WHERE status='paused'").fetchone()[0]
    c.close()
    return {"total": total, "active": active, "completed": completed, "paused": paused}

def init():
    ensure_table()
    log.info("[PlanEngine] Initialized")
