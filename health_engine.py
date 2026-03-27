"""
health_engine.py - Health Habits Tracker (Phase 5)
Tables in life.db: health_logs
TG commands: /health_log, /health_summary, /health_streak
LLM tools: health_log_entry, health_get_summary
Quick query: "كم نمت" / "وزني" / "رياضة"
"""

import os
import sqlite3
import json
import logging
import re
from datetime import datetime, date, timedelta

logger = logging.getLogger("health_engine")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "life.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS health_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    log_type    TEXT NOT NULL,  -- sleep | exercise | weight | water | note
    value       REAL,
    unit        TEXT,           -- hours | kg | km | min | steps | cups
    note        TEXT,
    log_date    DATE NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_health_type_date ON health_logs(log_type, log_date);
"""

# ── DB ────────────────────────────────────────────────────
def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c

def init_schema():
    db = _conn()
    db.executescript(_SCHEMA)
    db.commit()
    db.close()
    logger.info("health_engine: schema ready")

# ── CRUD ──────────────────────────────────────────────────
def log_entry(log_type, value, unit=None, note=None, log_date=None):
    """Add a health log entry."""
    if log_date is None:
        log_date = date.today().isoformat()
    if unit is None:
        unit = {"sleep": "hours", "exercise": "min", "weight": "kg",
                "water": "cups"}.get(log_type, "")
    db = _conn()
    db.execute(
        "INSERT INTO health_logs (log_type, value, unit, note, log_date) VALUES (?,?,?,?,?)",
        (log_type, value, unit, note, log_date)
    )
    db.commit()
    db.close()

    emoji = {"sleep": "\U0001f634", "exercise": "\U0001f3c3", "weight": "\u2696\ufe0f",
             "water": "\U0001f4a7"}.get(log_type, "\u2705")
    unit_ar = {"hours": "\u0633\u0627\u0639\u0629", "kg": "\u0643\u064a\u0644\u0648",
               "min": "\u062f\u0642\u064a\u0642\u0629", "km": "\u0643\u064a\u0644\u0648\u0645\u062a\u0631",
               "steps": "\u062e\u0637\u0648\u0629", "cups": "\u0643\u0648\u0628"}.get(unit, unit or "")
    return f"{emoji} \u062a\u0645 \u062a\u0633\u062c\u064a\u0644 {log_type}: {value} {unit_ar}"


def get_summary(days=7):
    """Get health summary for last N days."""
    since = (date.today() - timedelta(days=days)).isoformat()
    db = _conn()
    rows = db.execute(
        "SELECT log_type, value, unit, note, log_date FROM health_logs "
        "WHERE log_date >= ? ORDER BY log_date DESC", (since,)
    ).fetchall()
    db.close()

    summary = {"sleep": [], "exercise": [], "weight": [], "water": [], "note": []}
    for r in rows:
        summary.setdefault(r["log_type"], []).append(dict(r))

    return _format_summary(summary, days)


def _format_summary(summary, days):
    lines = [f"\U0001f4ca \u0645\u0644\u062e\u0635 \u0627\u0644\u0635\u062d\u0629 ({days} \u064a\u0648\u0645)"]
    lines.append("")

    # Sleep
    sleeps = summary.get("sleep", [])
    if sleeps:
        vals = [s["value"] for s in sleeps]
        avg = sum(vals) / len(vals)
        lines.append(f"\U0001f634 \u0627\u0644\u0646\u0648\u0645: {len(sleeps)} \u062a\u0633\u062c\u064a\u0644 | \u0645\u0639\u062f\u0644 {avg:.1f} \u0633\u0627\u0639\u0629")
    else:
        lines.append(f"\U0001f634 \u0627\u0644\u0646\u0648\u0645: \u0644\u0627 \u062a\u0633\u062c\u064a\u0644\u0627\u062a")

    # Exercise
    exs = summary.get("exercise", [])
    if exs:
        total = sum(e["value"] for e in exs)
        lines.append(f"\U0001f3c3 \u0627\u0644\u0631\u064a\u0627\u0636\u0629: {len(exs)} \u062c\u0644\u0633\u0629 | \u0645\u062c\u0645\u0648\u0639 {total:.0f} \u062f\u0642\u064a\u0642\u0629")
    else:
        lines.append(f"\U0001f3c3 \u0627\u0644\u0631\u064a\u0627\u0636\u0629: \u0644\u0627 \u062a\u0633\u062c\u064a\u0644\u0627\u062a")

    # Weight
    ws = summary.get("weight", [])
    if ws:
        latest = ws[0]
        first = ws[-1]
        diff = latest["value"] - first["value"]
        sign = "+" if diff > 0 else ""
        lines.append(f"\u2696\ufe0f \u0627\u0644\u0648\u0632\u0646: {latest['value']:.1f} \u0643\u064a\u0644\u0648 ({sign}{diff:.1f})")
    else:
        lines.append(f"\u2696\ufe0f \u0627\u0644\u0648\u0632\u0646: \u0644\u0627 \u062a\u0633\u062c\u064a\u0644\u0627\u062a")

    # Water
    waters = summary.get("water", [])
    if waters:
        avg_w = sum(w["value"] for w in waters) / len(waters)
        lines.append(f"\U0001f4a7 \u0627\u0644\u0645\u0627\u0621: \u0645\u0639\u062f\u0644 {avg_w:.1f} \u0643\u0648\u0628/\u064a\u0648\u0645")

    return chr(10).join(lines)


def get_streaks():
    """Calculate current streaks for each type."""
    db = _conn()
    today = date.today()
    result = {}

    for lt in ("sleep", "exercise", "weight"):
        dates = db.execute(
            "SELECT DISTINCT log_date FROM health_logs WHERE log_type=? ORDER BY log_date DESC",
            (lt,)
        ).fetchall()
        streak = 0
        check_date = today
        date_set = {d["log_date"] for d in dates}
        while check_date.isoformat() in date_set:
            streak += 1
            check_date -= timedelta(days=1)
        result[lt] = streak

    db.close()
    return result


def format_streaks():
    streaks = get_streaks()
    emoji = {"sleep": "\U0001f634", "exercise": "\U0001f3c3", "weight": "\u2696\ufe0f"}
    name_ar = {"sleep": "\u0627\u0644\u0646\u0648\u0645", "exercise": "\u0627\u0644\u0631\u064a\u0627\u0636\u0629", "weight": "\u0627\u0644\u0648\u0632\u0646"}
    lines = ["\U0001f525 \u0627\u0644\u0633\u0644\u0633\u0644\u0629 \u0627\u0644\u062d\u0627\u0644\u064a\u0629"]
    for k, v in streaks.items():
        lines.append(f"{emoji.get(k,'')} {name_ar.get(k, k)}: {v} \u064a\u0648\u0645 \u0645\u062a\u0648\u0627\u0635\u0644")
    return chr(10).join(lines)


# ── Parse ─────────────────────────────────────────────────
def parse_health_input(text):
    """Parse Arabic/English health input.
    Examples: 'نمت 6 ساعات', 'مشيت 30 دقيقة', 'وزني 85', 'water 8'
    """
    text = text.strip().lower()

    # Sleep patterns
    m = re.search(r'(?:\u0646\u0645\u062a|\u0646\u0648\u0645|sleep)\s*([\d.]+)', text)
    if m:
        return ("sleep", float(m.group(1)), "hours", None)

    # Exercise patterns
    m = re.search(r'(?:\u0645\u0634\u064a\u062a|\u0631\u064a\u0627\u0636\u0629|\u062a\u0645\u0631\u064a\u0646|exercise|walk|run|gym)\s*([\d.]+)', text)
    if m:
        val = float(m.group(1))
        unit = "min"
        if "\u0643\u064a\u0644\u0648" in text or "km" in text:
            unit = "km"
        elif "\u062e\u0637\u0648" in text or "step" in text:
            unit = "steps"
        return ("exercise", val, unit, None)

    # Weight patterns
    m = re.search(r'(?:\u0648\u0632\u0646|\u0648\u0632\u0646\u064a|weight)\s*([\d.]+)', text)
    if m:
        return ("weight", float(m.group(1)), "kg", None)

    # Water patterns
    m = re.search(r'(?:\u0645\u0627\u0621|\u0645\u0648\u064a\u0629|water)\s*([\d.]+)', text)
    if m:
        return ("water", float(m.group(1)), "cups", None)

    return None


# ── TG Handlers ───────────────────────────────────────────
def handle_health_log(args_text):
    """/health_log نمت 7 ساعات"""
    if not args_text or not args_text.strip():
        return ("\u0627\u0644\u0627\u0633\u062a\u062e\u062f\u0627\u0645:\n"
                "/health_log \u0646\u0645\u062a 7\n"
                "/health_log \u0645\u0634\u064a\u062a 30\n"
                "/health_log \u0648\u0632\u0646\u064a 85\n"
                "/health_log water 8")

    parsed = parse_health_input(args_text)
    if not parsed:
        return "\u26a0\ufe0f \u0645\u0627 \u0641\u0647\u0645\u062a. \u0627\u0633\u062a\u062e\u062f\u0645: \u0646\u0645\u062a X / \u0645\u0634\u064a\u062a X / \u0648\u0632\u0646\u064a X / water X"

    log_type, value, unit, note = parsed
    return log_entry(log_type, value, unit, note)


def handle_health_summary(args_text=None):
    """/health_summary [7|14|30]"""
    days = 7
    if args_text and args_text.strip().isdigit():
        days = int(args_text.strip())
    return get_summary(days)


def handle_health_streak():
    """/health_streak"""
    return format_streaks()


# ── Quick Query Handlers ──────────────────────────────────
def quick_health_summary():
    return get_summary(7)

def quick_health_today():
    return get_summary(1)


# ── LLM Tool Handlers ────────────────────────────────────
def llm_tool_health_log(log_type, value, unit=None, note=None, log_date=None):
    """LLM tool: log health entry."""
    return {"ok": True, "text": log_entry(log_type, value, unit, note, log_date)}


def llm_tool_health_summary(days=7):
    """LLM tool: get health summary."""
    return {"ok": True, "text": get_summary(days)}


def get_morning_health_text():
    from datetime import date, timedelta
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    db = _conn()
    rows = db.execute("SELECT log_type, value, unit FROM health_logs WHERE log_date=?", (yesterday,)).fetchall()
    db.close()
    if not rows:
        return ""
    parts = []
    for r in rows:
        emoji = {"sleep":"😴","exercise":"🏃","weight":"⚖️","water":"💧"}.get(r["log_type"],"")
        parts.append(f"{emoji}{r['value']}{r['unit'] or ''}")
    streaks = get_streaks()
    sp = [f"{k}:{v}d" for k,v in streaks.items() if v > 0]
    ss = f" | 🔥{','.join(sp)}" if sp else ""
    return f"💪 الصحة أمس: {' '.join(parts)}{ss}"
