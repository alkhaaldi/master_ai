"""Patch server.py + tg_session.py for Phase 5: Context Compaction."""
import sys, os, shutil

changes = 0

# ═══ Part A: tg_session.py — expand MAX_CONTEXT, add compaction ═══

with open("tg_session.py", "r") as f:
    tg_content = f.read()

# 1. Expand MAX_CONTEXT from 5 to 20
if "MAX_CONTEXT = 5" in tg_content:
    tg_content = tg_content.replace("MAX_CONTEXT = 5", "MAX_CONTEXT = 20  # expanded for compaction (Phase 5)", 1)
    print("A1. Expanded MAX_CONTEXT to 20")
    changes += 1
else:
    print("A1. MAX_CONTEXT already changed")

# 2. Add compaction in append_context when > 12 messages
old_append = '''def tg_session_append_context(user_id: str, role: str, text: str):
    try:
        sess = tg_session_get(user_id)
        ctx = sess["context_window"] if sess else []
        short = text[:200]
        ctx.append({"role": role, "text": short, "ts": _now_iso()})
        if len(ctx) > MAX_CONTEXT:
            ctx = ctx[-MAX_CONTEXT:]
        tg_session_upsert(user_id, context_window=ctx)
    except Exception as e:
        logger.error(f"session_append error: {e}")'''

new_append = '''def tg_session_append_context(user_id: str, role: str, text: str):
    try:
        sess = tg_session_get(user_id)
        ctx = sess["context_window"] if sess else []
        short = text[:200]
        ctx.append({"role": role, "text": short, "ts": _now_iso()})
        if len(ctx) > MAX_CONTEXT:
            ctx = ctx[-MAX_CONTEXT:]
        tg_session_upsert(user_id, context_window=ctx)
    except Exception as e:
        logger.error(f"session_append error: {e}")


def tg_session_get_compacted(user_id: str, last_message: str = "") -> list:
    """Get context window, compacted if >12 messages. Returns list of dicts."""
    try:
        from feature_flags import FeatureFlags
        import os
        _db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "life.db")
        _ff = FeatureFlags(_db)
        if not _ff.is_enabled("chat_compaction"):
            sess = tg_session_get(user_id)
            return sess["context_window"] if sess else []
        sess = tg_session_get(user_id)
        ctx = sess["context_window"] if sess else []
        if len(ctx) <= 12:
            return ctx
        # Compact
        try:
            from context_compactor import ContextCompactor
            compactor = ContextCompactor(_db)
            return compactor.compact(ctx, last_message=last_message, conversation_id=user_id)
        except Exception as e:
            logger.warning(f"Compaction failed, fallback to last 10: {e}")
            return ctx[-10:]
    except Exception as e:
        logger.error(f"get_compacted error: {e}")
        sess = tg_session_get(user_id)
        return (sess["context_window"] if sess else [])[-10:]'''

if "tg_session_get_compacted" not in tg_content:
    tg_content = tg_content.replace(old_append, new_append, 1)
    print("A2. Added tg_session_get_compacted")
    changes += 1
else:
    print("A2. get_compacted already exists")

with open("/tmp/tg_session_patched.py", "w") as f:
    f.write(tg_content)
os.remove("tg_session.py")
shutil.move("/tmp/tg_session_patched.py", "tg_session.py")
print("A. tg_session.py saved")

# ═══ Part B: server.py — use compacted context ═══

with open("server.py", "r") as f:
    srv_content = f.read()

# 3. Add import for tg_session_get_compacted
if "tg_session_get_compacted" not in srv_content:
    srv_content = srv_content.replace(
        "from tg_session import tg_session_get, tg_session_upsert, tg_session_append_context, tg_session_reset, detect_followup",
        "from tg_session import tg_session_get, tg_session_upsert, tg_session_append_context, tg_session_reset, detect_followup, tg_session_get_compacted",
        1,
    )
    print("B1. Added tg_session_get_compacted import")
    changes += 1
else:
    print("B1. Import already exists")

# 4. Replace context injection to use compacted version
old_inject = '''    if TG_SESSION_OK:
        try:
            _sess = tg_session_get(str(chat_id))
            if _sess and _sess.get("context_window"):
                for _cm in _sess["context_window"][-4:]:  # last 4 context items
                    memory_add_short_term(_cm.get("role","user"), _cm.get("text",""))
        except Exception:
            pass
    memory_add_short_term("user", f"[Telegram/{user_name}] {text}")'''

new_inject = '''    if TG_SESSION_OK:
        try:
            _ctx_msgs = tg_session_get_compacted(str(chat_id), last_message=text)
            for _cm in _ctx_msgs[-6:]:
                if _cm.get("_compacted"):
                    memory_add_short_term("system", _cm.get("text", ""))
                else:
                    memory_add_short_term(_cm.get("role","user"), _cm.get("text",""))
        except Exception:
            pass
    memory_add_short_term("user", f"[Telegram/{user_name}] {text}")'''

if "tg_session_get_compacted(str(chat_id)" not in srv_content:
    if old_inject in srv_content:
        srv_content = srv_content.replace(old_inject, new_inject, 1)
        print("B2. Replaced context injection with compacted version")
        changes += 1
    else:
        print("B2. WARNING: injection pattern not found (may differ)")
else:
    print("B2. Compacted injection already exists")

# 5. Add context_compactor cleanup to KAIROS (optional, piggyback on existing cleanup)
if "context_compactor" not in srv_content and "compactor.cleanup" not in srv_content:
    # We'll skip this — KAIROS already has cleanup cycle, and context_compactor
    # has its own cleanup method. We can call it from kairos later.
    print("B3. Skipped (compactor cleanup via kairos future integration)")

with open("/tmp/server_patched.py", "w") as f:
    f.write(srv_content)
os.remove("server.py")
shutil.move("/tmp/server_patched.py", "server.py")
print("B. server.py saved")

print(f"\nDone ({changes} changes). Run: python -m py_compile server.py tg_session.py context_compactor.py")
