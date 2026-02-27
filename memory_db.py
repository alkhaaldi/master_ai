# -*- coding: utf-8 -*-
"""Smart Memory System for Master AI v4.0"""
import aiosqlite, json
from datetime import datetime
TASKS_DB = "/home/pi/master_ai/data/audit.db"  # consolidated from tasks.db

def init_memory_db():
    import sqlite3
    conn = sqlite3.connect(TASKS_DB)
    conn.execute("CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT DEFAULT 'general', type TEXT DEFAULT 'fact', content TEXT NOT NULL, context TEXT DEFAULT '', confidence REAL DEFAULT 0.5, source TEXT DEFAULT 'auto', tags TEXT DEFAULT '', last_used TEXT, use_count INTEGER DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, active INTEGER DEFAULT 1)")
    conn.execute("CREATE TABLE IF NOT EXISTS conversations (id INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT DEFAULT 'claude', role TEXT NOT NULL, content TEXT NOT NULL, metadata TEXT DEFAULT '{}', timestamp TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS user_profiles (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL, language TEXT DEFAULT 'ar', tone TEXT DEFAULT 'casual', permissions TEXT DEFAULT '{}', preferences TEXT DEFAULT '{}', last_interaction TEXT, created_at TEXT NOT NULL)")
    conn.commit()
    conn.close()

async def add_memory(category, type_, content, context="", confidence=0.5, source="auto", tags=""):
    now = datetime.utcnow().isoformat() + "Z"
    async with aiosqlite.connect(TASKS_DB) as db:
        cur = await db.execute("SELECT id, confidence FROM memory WHERE content = ? AND active = 1", (content,))
        ex = await cur.fetchone()
        if ex:
            nc = min(1.0, ex[1] + 0.1)
            await db.execute("UPDATE memory SET confidence=?, use_count=use_count+1, updated_at=? WHERE id=?", (nc, now, ex[0]))
            await db.commit()
            return {"id": ex[0], "action": "reinforced", "confidence": nc}
        cur = await db.execute("INSERT INTO memory (category,type,content,context,confidence,source,tags,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)", (category, type_, content, context, confidence, source, tags, now, now))
        await db.commit()
        return {"id": cur.lastrowid, "action": "created", "confidence": confidence}

async def get_memories(category=None, type_=None, min_confidence=0.0, search=None, limit=20):
    async with aiosqlite.connect(TASKS_DB) as db:
        db.row_factory = aiosqlite.Row
        q = "SELECT * FROM memory WHERE active=1"; p = []
        if category: q += " AND category=?"; p.append(category)
        if type_: q += " AND type=?"; p.append(type_)
        if min_confidence > 0: q += " AND confidence>=?"; p.append(min_confidence)
        if search: q += " AND (content LIKE ? OR tags LIKE ?)"; p.extend(["%"+search+"%"]*2)
        q += " ORDER BY confidence DESC, use_count DESC LIMIT ?"; p.append(limit)
        cur = await db.execute(q, p)
        return [dict(r) for r in await cur.fetchall()]

async def use_memory(mid):
    now = datetime.utcnow().isoformat() + "Z"
    async with aiosqlite.connect(TASKS_DB) as db:
        await db.execute("UPDATE memory SET use_count=use_count+1, last_used=?, updated_at=? WHERE id=?", (now, now, mid))
        await db.commit()

async def update_memory(mid, **kw):
    now = datetime.utcnow().isoformat() + "Z"
    ok = {k:v for k,v in kw.items() if k in {"content","context","confidence","category","type","tags","active"}}
    if not ok: return None
    ok["updated_at"] = now
    s = ", ".join(f"{k}=?" for k in ok)
    async with aiosqlite.connect(TASKS_DB) as db:
        await db.execute(f"UPDATE memory SET {s} WHERE id=?", list(ok.values())+[mid])
        await db.commit()
        return {"updated": True}

async def forget_memory(mid):
    now = datetime.utcnow().isoformat() + "Z"
    async with aiosqlite.connect(TASKS_DB) as db:
        await db.execute("UPDATE memory SET active=0, updated_at=? WHERE id=?", (now, mid))
        await db.commit()
        return {"forgotten": True}

async def save_message(channel, role, content, metadata=None):
    now = datetime.utcnow().isoformat() + "Z"
    async with aiosqlite.connect(TASKS_DB) as db:
        cur = await db.execute("INSERT INTO conversations (channel,role,content,metadata,timestamp) VALUES (?,?,?,?,?)", (channel, role, content, json.dumps(metadata or {}), now))
        await db.commit()
        return cur.lastrowid

async def get_conversation_history(channel="claude", limit=20):
    async with aiosqlite.connect(TASKS_DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM conversations WHERE channel=? ORDER BY id DESC LIMIT ?", (channel, limit))
        return [dict(r) for r in reversed(await cur.fetchall())]

async def clear_conversation(channel="claude"):
    async with aiosqlite.connect(TASKS_DB) as db:
        await db.execute("DELETE FROM conversations WHERE channel=?", (channel,))
        await db.commit()

async def get_or_create_user(user_id, name="", language="ar", tone="casual"):
    now = datetime.utcnow().isoformat() + "Z"
    async with aiosqlite.connect(TASKS_DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM user_profiles WHERE user_id=?", (user_id,))
        u = await cur.fetchone()
        if u:
            await db.execute("UPDATE user_profiles SET last_interaction=? WHERE user_id=?", (now, user_id))
            await db.commit()
            return dict(u)
        await db.execute("INSERT INTO user_profiles (user_id,name,language,tone,permissions,preferences,last_interaction,created_at) VALUES (?,?,?,?,?,?,?,?)", (user_id, name, language, tone, '{}', '{}', now, now))
        await db.commit()
        return {"user_id": user_id, "name": name}

async def get_all_users():
    async with aiosqlite.connect(TASKS_DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM user_profiles ORDER BY last_interaction DESC")
        return [dict(r) for r in await cur.fetchall()]

async def build_context(user_id="bu_khalifa", channel="claude"):
    from tasks_db import get_summary, get_latest_session, get_knowledge
    ctx = {"timestamp": datetime.utcnow().isoformat()+"Z"}
    try: ctx["user"] = await get_or_create_user(user_id)
    except: ctx["user"] = {"user_id": user_id}
    try: ctx["tasks"] = await get_summary()
    except: ctx["tasks"] = {}
    try:
        mem = await get_memories(min_confidence=0.3, limit=30)
        ctx["memories"] = {"patterns": [m for m in mem if m["type"]=="pattern"], "preferences": [m for m in mem if m["type"]=="preference"], "facts": [m for m in mem if m["type"]=="fact"], "total": len(mem)}
    except: ctx["memories"] = {"total": 0}
    try: ctx["recent_conversation"] = await get_conversation_history(channel, 10)
    except: ctx["recent_conversation"] = []
    try: ctx["last_session"] = await get_latest_session()
    except: ctx["last_session"] = None
    return ctx

async def get_memory_stats():
    async with aiosqlite.connect(TASKS_DB) as db:
        s = {}
        cur = await db.execute("SELECT COUNT(*) FROM memory WHERE active=1"); s["total"] = (await cur.fetchone())[0]
        cur = await db.execute("SELECT type, COUNT(*) FROM memory WHERE active=1 GROUP BY type"); s["by_type"] = {r[0]:r[1] async for r in cur}
        cur = await db.execute("SELECT category, COUNT(*) FROM memory WHERE active=1 GROUP BY category"); s["by_category"] = {r[0]:r[1] async for r in cur}
        cur = await db.execute("SELECT COUNT(*) FROM user_profiles"); s["users"] = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM conversations"); s["messages"] = (await cur.fetchone())[0]
        return s
