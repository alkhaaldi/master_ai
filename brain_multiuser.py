"""
Brain Multi-User — Phase 5
User profiles, source detection, per-user preferences.
"""
import json, sqlite3, logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("brain.multiuser")

DB_PATH = Path(__file__).parent / "data" / "audit.db"
KNOWLEDGE_PATH = Path(__file__).parent / "knowledge.json"

# Default user profiles (static from knowledge.json)
_user_profiles = {}

def _load_user_profiles():
    """Load user profiles from knowledge.json."""
    global _user_profiles
    try:
        with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _user_profiles = data.get("users", {})
        logger.info(f"Loaded {len(_user_profiles)} user profiles")
    except Exception as e:
        logger.error(f"Failed to load user profiles: {e}")
        _user_profiles = {}

# ═══════════════════════════════════════
# Source detection
# ═══════════════════════════════════════

# Telegram user_id -> profile mapping
TELEGRAM_MAP = {
    6692577800: "bu_khalifa",   # بو خليفة
}

def detect_user(source: str = "api", telegram_user_id: int = None, ha_user: str = None) -> dict:
    """Detect who is making the request and return their profile."""
    if not _user_profiles:
        _load_user_profiles()
    
    user_id = "bu_khalifa"  # default
    
    if source == "telegram" and telegram_user_id:
        user_id = TELEGRAM_MAP.get(telegram_user_id, "bu_khalifa")
    elif source == "ha_dashboard" and ha_user:
        # Map HA usernames to profiles
        ha_map = {
            "aisha-home": "oana",
            "mama-room": "um_salem",
        }
        user_id = ha_map.get(ha_user, "bu_khalifa")
    
    profile = _user_profiles.get(user_id, _get_default_profile())
    profile["user_id"] = user_id
    return profile

def _get_default_profile():
    return {
        "name": "بو خليفة",
        "language": "ar_kw",
        "dialect": "kuwaiti",
        "verbosity": "minimal",
        "role": "owner"
    }

# ═══════════════════════════════════════
# Per-user learning
# ═══════════════════════════════════════

def _ensure_user_tables():
    """Ensure user-related columns exist in memory table."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        # Check if user_id column exists
        cursor = conn.execute("PRAGMA table_info(memory)")
        cols = [row[1] for row in cursor.fetchall()]
        if "user_id" not in cols:
            conn.execute("ALTER TABLE memory ADD COLUMN user_id TEXT DEFAULT 'bu_khalifa'")
            conn.commit()
            logger.info("Added user_id column to memory table")
        conn.close()
    except Exception as e:
        logger.error(f"Error ensuring user tables: {e}")

def get_user_patterns(user_id: str, category: str = None) -> list:
    """Get learned patterns for a specific user."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        if category:
            rows = conn.execute(
                "SELECT content, context, confidence, hit_count FROM memory WHERE user_id=? AND category=? AND active=1 ORDER BY hit_count DESC LIMIT 20",
                (user_id, category)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT category, content, confidence, hit_count FROM memory WHERE user_id=? AND active=1 ORDER BY hit_count DESC LIMIT 50",
                (user_id,)
            ).fetchall()
        conn.close()
        return [{"category": r[0] if not category else category, "content": r[1] if category else r[1], "confidence": r[2], "hits": r[3]} for r in rows]
    except Exception as e:
        logger.error(f"Error getting user patterns: {e}")
        return []

def get_user_response_style(user_id: str) -> dict:
    """Get response style preferences for a user."""
    if not _user_profiles:
        _load_user_profiles()
    
    profile = _user_profiles.get(user_id, _get_default_profile())
    
    return {
        "language": profile.get("language", "ar_kw"),
        "dialect": profile.get("dialect", "kuwaiti"),
        "verbosity": profile.get("verbosity", "minimal"),
        "emoji": profile.get("emoji", True),
    }

def get_multiuser_stats() -> dict:
    """Stats about multi-user system."""
    if not _user_profiles:
        _load_user_profiles()
    
    stats = {
        "profiles_loaded": len(_user_profiles),
        "users": list(_user_profiles.keys()),
    }
    
    try:
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute(
            "SELECT user_id, COUNT(*) as cnt FROM memory WHERE active=1 GROUP BY user_id"
        ).fetchall()
        conn.close()
        stats["memories_per_user"] = {r[0]: r[1] for r in rows}
    except:
        stats["memories_per_user"] = {}
    
    return stats

# Initialize on import
_load_user_profiles()
_ensure_user_tables()
