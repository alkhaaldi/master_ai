"""
Feature Flags v2 — DB-backed, thread-safe, 60s cache.
Env vars override DB values (backward compatible).
"""
import os
import time
import sqlite3
import threading
import logging

logger = logging.getLogger("feature_flags")

_SEED_FLAGS = [
    ("circuit_breakers", 1, "Circuit breakers for external calls"),
    ("timeouts", 1, "Request timeouts"),
    ("speed_templates", 1, "Speed engine templates"),
    ("smart_router_v2", 1, "Smart intent router v2"),
    ("entity_health", 1, "Entity health monitoring"),
    ("kairos", 0, "Background health agent (Phase 3)"),
    ("telegram_queue", 0, "Offline message buffer (Phase 4)"),
    ("chat_compaction", 0, "Chat context compression (Phase 5)"),
    ("hooks", 0, "Event hook system (Phase 6)"),
    ("tool_registry", 0, "Central tool catalog (Phase 6)"),
    # Trading feature flags (Layer 4)
    ("radar_enabled", 1, "Stock radar 128-stock monitoring"),
    ("momentum_alerts", 1, "Strong-moving stock alerts"),
    ("golden_engine", 1, "Golden opportunities matching"),
    ("position_monitor", 1, "Position auto-monitoring"),
    ("daily_refresh", 1, "Daily snapshot auto-refresh"),
    ("market_regime_filter", 1, "Block buys in bearish/choppy market regime"),
    ("liquidity_filter", 1, "Filter illiquid stocks / wide spread (KSE)"),
    ("sector_limits", 1, "Sector exposure limits — max 2 per sector"),
    ("pre_trade_checklist", 1, "Pre-trade checklist gate — all checks must pass"),
    ("risk_engine", 1, "Portfolio risk engine — position sizing + heat"),
]

# Map flag name → env var name (for backward compat)
_ENV_MAP = {
    "circuit_breakers": "FEATURE_CIRCUIT_BREAKERS",
    "timeouts": "FEATURE_TIMEOUTS",
    "speed_templates": "FEATURE_SPEED_TEMPLATES",
    "smart_router_v2": "FEATURE_SMART_ROUTER_V2",
    "entity_health": "FEATURE_ENTITY_HEALTH",
}


class FeatureFlags:
    def __init__(self, db_path: str, cache_ttl: int = 60):
        self._db_path = db_path
        self._cache_ttl = cache_ttl
        self._cache: dict[str, bool] = {}
        self._cache_ts: float = 0
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self._db_path, timeout=5)

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feature_flags (
                    name TEXT PRIMARY KEY,
                    enabled INTEGER DEFAULT 0,
                    description TEXT DEFAULT '',
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            for name, enabled, desc in _SEED_FLAGS:
                conn.execute(
                    "INSERT OR IGNORE INTO feature_flags (name, enabled, description) VALUES (?, ?, ?)",
                    (name, enabled, desc),
                )
            conn.commit()
        self._refresh()

    def _refresh(self):
        with self._lock:
            try:
                with self._conn() as conn:
                    rows = conn.execute("SELECT name, enabled FROM feature_flags").fetchall()
                self._cache = {r[0]: bool(r[1]) for r in rows}
                self._cache_ts = time.time()
            except Exception as e:
                logger.error(f"Feature flags refresh error: {e}")

    def _maybe_refresh(self):
        if time.time() - self._cache_ts > self._cache_ttl:
            self._refresh()

    def is_enabled(self, name: str) -> bool:
        # Env var override (backward compat)
        env_key = _ENV_MAP.get(name)
        if env_key:
            env_val = os.getenv(env_key)
            if env_val is not None:
                return env_val == "1"
        self._maybe_refresh()
        return self._cache.get(name, False)

    def toggle(self, name: str) -> bool:
        """Toggle a flag. Returns the new value."""
        new_val = not self.is_enabled(name)
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO feature_flags (name, enabled, updated_at)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(name) DO UPDATE SET enabled=?, updated_at=datetime('now')""",
                (name, int(new_val), int(new_val)),
            )
            conn.commit()
        self._refresh()
        return new_val

    def get_all(self) -> list[dict]:
        self._maybe_refresh()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT name, enabled, description, updated_at FROM feature_flags ORDER BY name"
            ).fetchall()
        result = []
        for name, enabled, desc, updated in rows:
            env_key = _ENV_MAP.get(name)
            env_override = None
            if env_key:
                env_val = os.getenv(env_key)
                if env_val is not None:
                    env_override = env_val == "1"
            result.append({
                "name": name,
                "enabled": bool(env_override) if env_override is not None else bool(enabled),
                "db_value": bool(enabled),
                "env_override": env_override,
                "description": desc,
                "updated_at": updated,
            })
        return result

    def set_flag(self, name: str, enabled: bool, description: str = None):
        """Explicitly set a flag value."""
        with self._conn() as conn:
            if description is not None:
                conn.execute(
                    """INSERT INTO feature_flags (name, enabled, description, updated_at)
                       VALUES (?, ?, ?, datetime('now'))
                       ON CONFLICT(name) DO UPDATE SET enabled=?, description=?, updated_at=datetime('now')""",
                    (name, int(enabled), description, int(enabled), description),
                )
            else:
                conn.execute(
                    """INSERT INTO feature_flags (name, enabled, updated_at)
                       VALUES (?, ?, datetime('now'))
                       ON CONFLICT(name) DO UPDATE SET enabled=?, updated_at=datetime('now')""",
                    (name, int(enabled), int(enabled)),
                )
            conn.commit()
        self._refresh()
