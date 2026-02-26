"""
Master AI Brain v2.0 — Facade
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
        _learn_worker,
    )
    LEARNING_OK = True
    logger.info("brain_learning loaded")
except Exception as e:
    LEARNING_OK = False
    logger.error(f"brain_learning FAILED: {e}")

# ═══════════════════════════════════════
# Personality: templates, response prompt
# ═══════════════════════════════════════
try:
    from brain_personality import (
        get_quick_response,
        build_response_prompt,
        reload_policy,
        get_policy,
    )
    PERSONALITY_OK = True
    logger.info("brain_personality loaded")
except Exception as e:
    PERSONALITY_OK = False
    logger.error(f"brain_personality FAILED: {e}")


def get_brain_stats():
    """Combined stats from all modules."""
    stats = {}
    if CORE_OK:
        stats = _core_stats()
    stats["modules"] = {
        "core": "ok" if CORE_OK else "failed",
        "learning": "ok" if LEARNING_OK else "failed",
        "personality": "ok" if PERSONALITY_OK else "failed",
    }
    return stats
