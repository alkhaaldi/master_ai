"""
Master AI Brain v4.0 — Facade
Re-exports all brain functions from sub-modules.
server.py imports from here — no changes needed.
"""
import logging

logger = logging.getLogger("brain")

# ═══════════════════════════════════════
# Core: prompts, aliases, entity resolution
# ═══════════════════════════════════════
try:
    from brain_core import (
        reload,
        resolve_aliases,
        build_system_prompt,
        build_user_message,
        build_room_index,
        get_brain_stats as _core_stats,
    )
    CORE_OK = True
    logger.info("brain_core loaded")
except Exception as e:
    CORE_OK = False
    logger.error(f"brain_core FAILED: {e}")

# ═══════════════════════════════════════
# Learning: patterns, memory, decay
# ═══════════════════════════════════════
try:
    from brain_learning import (
        learn_from_result,
        _get_relevant_patterns,
        _detect_user_correction,
        _apply_confidence_decay,
        _ensure_memory_table,
        _learning_stats,
    )
    LEARNING_OK = True
    logger.info("brain_learning loaded")
except Exception as e:
    LEARNING_OK = False
    logger.error(f"brain_learning FAILED: {e}")
    async def learn_from_result(*a, **kw): pass
    def _learning_stats(): return {}

# ═══════════════════════════════════════
# Personality: quick responses, response prompts
# ═══════════════════════════════════════
try:
    from brain_personality import (
        get_quick_response,
        build_response_prompt,
    )
    PERSONALITY_OK = True
    logger.info("brain_personality loaded")
except Exception as e:
    PERSONALITY_OK = False
    logger.error(f"brain_personality FAILED: {e}")
    def get_quick_response(*a, **kw): return None
    def build_response_prompt(): return "Summarize the results for the user."

# ═══════════════════════════════════════
# Proactive: alerts, daily briefing
# ═══════════════════════════════════════
try:
    from brain_proactive import (
        proactive_loop,
        get_proactive_stats,
        _ensure_alerts_table,
    )
    PROACTIVE_OK = True
    logger.info("brain_proactive loaded")
except Exception as e:
    PROACTIVE_OK = False
    logger.error(f"brain_proactive FAILED: {e}")
    async def proactive_loop(): pass
    def get_proactive_stats(): return {"enabled": False, "error": "module not loaded"}

# ═══════════════════════════════════════
# Observability: diagnostics, backups (Phase 4.5)
# ═══════════════════════════════════════
try:
    from brain_observability import (
        get_system_diag,
        run_backup,
        backup_loop,
        record_error,
        errors_last_hour,
    )
    OBSERVABILITY_OK = True
    logger.info("brain_observability loaded")
except Exception as e:
    OBSERVABILITY_OK = False
    logger.error(f"brain_observability FAILED: {e}")
    def get_system_diag(**kw): return {"error": "module not loaded"}
    def run_backup(): return {"error": "module not loaded"}
    async def backup_loop(): pass
    def record_error(*a): pass

# ═══════════════════════════════════════
# Multi-User: profiles, source detection (Phase 5)
# ═══════════════════════════════════════
try:
    from brain_multiuser import (
        detect_user,
        get_user_response_style,
        get_user_patterns,
        get_multiuser_stats,
    )
    MULTIUSER_OK = True
    logger.info("brain_multiuser loaded")
except Exception as e:
    MULTIUSER_OK = False
    logger.error(f"brain_multiuser FAILED: {e}")
    def detect_user(**kw): return {"user_id": "bu_khalifa", "name": "بو خليفة", "language": "ar_kw"}
    def get_multiuser_stats(): return {"error": "module not loaded"}

# ═══════════════════════════════════════
# Analytics: feedback, request logging (Phase 6)
# ═══════════════════════════════════════
try:
    from brain_analytics import (
        record_feedback,
        log_request,
        get_analytics,
    )
    ANALYTICS_OK = True
    logger.info("brain_analytics loaded")
except Exception as e:
    ANALYTICS_OK = False
    logger.error(f"brain_analytics FAILED: {e}")
    def record_feedback(*a, **kw): return False
    def log_request(*a, **kw): pass
    def get_analytics(**kw): return {"error": "module not loaded"}


# ═══════════════════════════════════════
# Combined stats (called by server.py)
# ═══════════════════════════════════════
def get_brain_stats():
    """Combined stats from all modules."""
    stats = {}
    if CORE_OK:
        stats = _core_stats()
    stats["modules"] = {
        "core": "ok" if CORE_OK else "failed",
        "learning": "ok" if LEARNING_OK else "failed",
        "personality": "ok" if PERSONALITY_OK else "failed",
        "proactive": "ok" if PROACTIVE_OK else "failed",
        "observability": "ok" if OBSERVABILITY_OK else "failed",
        "multiuser": "ok" if MULTIUSER_OK else "failed",
        "analytics": "ok" if ANALYTICS_OK else "failed",
    }
    if PROACTIVE_OK:
        stats["proactive"] = get_proactive_stats()
    if MULTIUSER_OK:
        stats["multiuser"] = get_multiuser_stats()
    return stats
