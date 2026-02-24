"""
Task Tracker Database Module
Part of Master AI v4.0
Manages tasks SQLite database for Abu Khalifa's personal task management
"""
import sqlite3
import aiosqlite
import os
from datetime import datetime

TASKS_DB = "/home/pi/master_ai/data/tasks.db"

def init_tasks_db():
    os.makedirs(os.path.dirname(TASKS_DB), exist_ok=True)
    conn = sqlite3.connect(TASKS_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL DEFAULT 'personal',
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            priority TEXT NOT NULL DEFAULT 'medium',
            status TEXT NOT NULL DEFAULT 'pending',
            due_date TEXT,
            tags TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            notes TEXT DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            details TEXT DEFAULT '',
            timestamp TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )
    """)
    conn.commit()
    conn.close()


async def add_task(category, title, description="", priority="medium", due_date=None, tags=""):
    now = datetime.utcnow().isoformat() + "Z"
    async with aiosqlite.connect(TASKS_DB) as db:
        cursor = await db.execute(
            """INSERT INTO tasks (category, title, description, priority, status, due_date, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
            (category, title, description, priority, due_date, tags, now, now)
        )
        task_id = cursor.lastrowid
        await db.execute(
            "INSERT INTO task_log (task_id, action, details, timestamp) VALUES (?, 'created', ?, ?)",
            (task_id, f"Task created: {title}", now)
        )
        await db.commit()
        return task_id

async def get_tasks(category=None, status=None, priority=None, limit=50):
    async with aiosqlite.connect(TASKS_DB) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if status:
            query += " AND status = ?"
            params.append(status)
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        query += " ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END, updated_at DESC LIMIT ?"
        params.append(limit)
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def get_task(task_id):
    async with aiosqlite.connect(TASKS_DB) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
        if row:
            # Get log
            log_cursor = await db.execute(
                "SELECT * FROM task_log WHERE task_id = ? ORDER BY timestamp DESC", (task_id,))
            logs = await log_cursor.fetchall()
            result = dict(row)
            result["history"] = [dict(l) for l in logs]
            return result
        return None

async def update_task(task_id, **kwargs):
    now = datetime.utcnow().isoformat() + "Z"
    async with aiosqlite.connect(TASKS_DB) as db:
        # Check task exists
        cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        existing = await cursor.fetchone()
        if not existing:
            return None

        allowed = ["category", "title", "description", "priority", "status", "due_date", "tags", "notes"]
        updates = []
        params = []
        changes = []
        for key, value in kwargs.items():
            if key in allowed and value is not None:
                updates.append(f"{key} = ?")
                params.append(value)
                changes.append(f"{key} -> {value}")

        if not updates:
            return {"error": "no valid fields to update"}

        # If status changed to done, set completed_at
        if "status" in kwargs and kwargs["status"] == "done":
            updates.append("completed_at = ?")
            params.append(now)

        updates.append("updated_at = ?")
        params.append(now)
        params.append(task_id)

        await db.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)
        await db.execute(
            "INSERT INTO task_log (task_id, action, details, timestamp) VALUES (?, 'updated', ?, ?)",
            (task_id, "; ".join(changes), now)
        )
        await db.commit()
        return {"updated": True, "changes": changes}

async def add_note(task_id, note):
    now = datetime.utcnow().isoformat() + "Z"
    async with aiosqlite.connect(TASKS_DB) as db:
        cursor = await db.execute("SELECT notes FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        existing_notes = row[0] or ""
        new_notes = f"{existing_notes}\n[{now}] {note}".strip()
        await db.execute("UPDATE tasks SET notes = ?, updated_at = ? WHERE id = ?", (new_notes, now, task_id))
        await db.execute(
            "INSERT INTO task_log (task_id, action, details, timestamp) VALUES (?, 'note_added', ?, ?)",
            (task_id, note, now)
        )
        await db.commit()
        return {"added": True}

async def delete_task(task_id):
    async with aiosqlite.connect(TASKS_DB) as db:
        cursor = await db.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
        if not await cursor.fetchone():
            return None
        await db.execute("DELETE FROM task_log WHERE task_id = ?", (task_id,))
        await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await db.commit()
        return {"deleted": True}

async def get_summary():
    async with aiosqlite.connect(TASKS_DB) as db:
        # By status
        cursor = await db.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
        by_status = {r[0]: r[1] async for r in cursor}

        # By category
        cursor = await db.execute("SELECT category, COUNT(*) FROM tasks WHERE status != 'done' AND status != 'cancelled' GROUP BY category")
        by_category = {r[0]: r[1] async for r in cursor}

        # By priority (active only)
        cursor = await db.execute("SELECT priority, COUNT(*) FROM tasks WHERE status != 'done' AND status != 'cancelled' GROUP BY priority")
        by_priority = {r[0]: r[1] async for r in cursor}

        # Total
        cursor = await db.execute("SELECT COUNT(*) FROM tasks")
        total = (await cursor.fetchone())[0]

        # Active
        cursor = await db.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('pending', 'in_progress')")
        active = (await cursor.fetchone())[0]

        # Critical/High pending
        cursor = await db.execute("SELECT id, category, title, priority FROM tasks WHERE priority IN ('critical', 'high') AND status IN ('pending', 'in_progress') ORDER BY CASE priority WHEN 'critical' THEN 0 ELSE 1 END")
        urgent = [{"id": r[0], "category": r[1], "title": r[2], "priority": r[3]} async for r in cursor]

        return {
            "total": total,
            "active": active,
            "by_status": by_status,
            "by_category": by_category,
            "by_priority": by_priority,
            "urgent_tasks": urgent
        }


# ============================================================
#  KNOWLEDGE BASE
# ============================================================

async def add_knowledge(category, topic, content, tags=""):
    now = datetime.utcnow().isoformat() + "Z"
    async with aiosqlite.connect(TASKS_DB) as db:
        cursor = await db.execute(
            "INSERT INTO knowledge (category, topic, content, tags, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (category, topic, content, tags, now, now)
        )
        kid = cursor.lastrowid
        await db.commit()
        return kid

async def get_knowledge(category=None, topic=None, tags=None, search=None, limit=20):
    async with aiosqlite.connect(TASKS_DB) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM knowledge WHERE 1=1"
        params = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if topic:
            query += " AND topic LIKE ?"
            params.append(f"%{topic}%")
        if tags:
            query += " AND tags LIKE ?"
            params.append(f"%{tags}%")
        if search:
            query += " AND (content LIKE ? OR topic LIKE ?)"
            params.append(f"%{search}%")
            params.append(f"%{search}%")
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def get_knowledge_item(kid):
    async with aiosqlite.connect(TASKS_DB) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM knowledge WHERE id = ?", (kid,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def update_knowledge(kid, **kwargs):
    now = datetime.utcnow().isoformat() + "Z"
    async with aiosqlite.connect(TASKS_DB) as db:
        cursor = await db.execute("SELECT id FROM knowledge WHERE id = ?", (kid,))
        if not await cursor.fetchone():
            return None
        allowed = ["category", "topic", "content", "tags"]
        updates = []
        params = []
        for key, value in kwargs.items():
            if key in allowed and value is not None:
                updates.append(f"{key} = ?")
                params.append(value)
        if not updates:
            return {"error": "no valid fields"}
        updates.append("updated_at = ?")
        params.append(now)
        params.append(kid)
        await db.execute(f"UPDATE knowledge SET {', '.join(updates)} WHERE id = ?", params)
        await db.commit()
        return {"updated": True}

async def delete_knowledge(kid):
    async with aiosqlite.connect(TASKS_DB) as db:
        cursor = await db.execute("SELECT id FROM knowledge WHERE id = ?", (kid,))
        if not await cursor.fetchone():
            return None
        await db.execute("DELETE FROM knowledge WHERE id = ?", (kid,))
        await db.commit()
        return {"deleted": True}


# ============================================================
#  SESSION LOG
# ============================================================

async def add_session_log(session_date, summary, changes_made="", decisions="", blockers="", next_steps=""):
    now = datetime.utcnow().isoformat() + "Z"
    async with aiosqlite.connect(TASKS_DB) as db:
        cursor = await db.execute(
            """INSERT INTO session_log (session_date, summary, changes_made, decisions, blockers, next_steps, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_date, summary, changes_made, decisions, blockers, next_steps, now)
        )
        await db.commit()
        return cursor.lastrowid

async def get_session_logs(limit=10):
    async with aiosqlite.connect(TASKS_DB) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM session_log ORDER BY id DESC LIMIT ?", (limit,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def get_latest_session():
    async with aiosqlite.connect(TASKS_DB) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM session_log ORDER BY id DESC LIMIT 1")
        row = await cursor.fetchone()
        return dict(row) if row else None
