"""
Telegram Operations Module - Level 1
Admin hardening, approvals UI, operational commands
"""
import os
import json
import sqlite3
import subprocess
import logging

logger = logging.getLogger("master_ai")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIT_DB = os.path.join(BASE_DIR, "data", "audit.db")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID", "")


def get_admin_chat_id() -> str:
    if ADMIN_TELEGRAM_ID:
        return ADMIN_TELEGRAM_ID
    admin_file = os.path.join(BASE_DIR, "data", "admin_chat_id.txt")
    if os.path.exists(admin_file):
        with open(admin_file, "r") as f:
            return f.read().strip()
    return ""


def is_tg_admin(tg_user_id) -> bool:
    admin_id = get_admin_chat_id()
    if not admin_id:
        return True
    return str(tg_user_id) == str(admin_id)


def get_pending_approvals(limit=10):
    try:
        conn = sqlite3.connect(AUDIT_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT approval_id, action, risk, created_at FROM approval_queue WHERE status='pending' ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_pending_approvals: {e}")
        return []


def process_approval(approval_id, decision):
    try:
        conn = sqlite3.connect(AUDIT_DB)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM approval_queue WHERE approval_id=?", (approval_id,)).fetchone()
        if not row:
            conn.close()
            return "Not found"
        if row["status"] != "pending":
            conn.close()
            return f"Already {row['status']}"
        new_status = "approved" if decision == "approve" else "denied"
        conn.execute(
            "UPDATE approval_queue SET status=?, approved_at=datetime('now','localtime') WHERE approval_id=?",
            (new_status, approval_id)
        )
        conn.commit()
        job_id = row["job_id"]
        if job_id:
            if decision == "approve":
                conn.execute("UPDATE win_jobs SET status='queued' WHERE job_id=?", (job_id,))
            else:
                conn.execute("UPDATE win_jobs SET status='rejected' WHERE job_id=?", (job_id,))
            conn.commit()
        conn.close()
        return f"{new_status.title()}: {approval_id[:6]}"
    except Exception as e:
        logger.error(f"process_approval: {e}")
        return f"Error: {str(e)[:50]}"


def format_approval_buttons(pending):
    buttons = []
    for ap in pending:
        aid = ap["approval_id"]
        risk = ap.get("risk", "?")
        action_raw = ap.get("action", "?")
        try:
            ad = json.loads(action_raw) if isinstance(action_raw, str) else action_raw
            desc = ad.get("action_type", ad.get("type", str(action_raw)[:25]))
        except Exception:
            desc = str(action_raw)[:25]
        buttons.append({"text": f"\u2705 {aid[:6]}|{risk}|{desc[:12]}", "callback_data": f"appr:{aid}:1"})
        buttons.append({"text": f"\u274c {aid[:6]}", "callback_data": f"appr:{aid}:0"})
    return buttons


def run_backup():
    script = os.path.join(BASE_DIR, "scripts", "backup_now.sh")
    if not os.path.exists(script):
        return False, "backup_now.sh not found"
    try:
        result = subprocess.run(
            ["/bin/bash", script],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return True, result.stdout[:400]
        return False, f"rc={result.returncode} {result.stderr[:200]}"
    except Exception as e:
        return False, str(e)
