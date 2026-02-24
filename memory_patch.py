
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
