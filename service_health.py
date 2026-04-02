"""
Service Health Hub — single source of truth for all service statuses.
Reads FROM existing circuit breakers, does NOT replace them.
"""
import time
import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger("service_health")


class ServiceStatus:
    __slots__ = ("name", "is_available", "last_checked", "consecutive_failures", "reason", "details")

    def __init__(self, name: str):
        self.name = name
        self.is_available = True
        self.last_checked = 0.0
        self.consecutive_failures = 0
        self.reason = ""
        self.details = {}

    def mark_up(self, details: dict = None):
        self.is_available = True
        self.consecutive_failures = 0
        self.reason = ""
        self.last_checked = time.time()
        if details:
            self.details = details

    def mark_down(self, reason: str, details: dict = None):
        self.is_available = False
        self.consecutive_failures += 1
        self.reason = reason
        self.last_checked = time.time()
        if details:
            self.details = details

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": "up" if self.is_available else "down",
            "last_checked": datetime.fromtimestamp(self.last_checked, tz=timezone.utc).isoformat() if self.last_checked else None,
            "consecutive_failures": self.consecutive_failures,
            "reason": self.reason,
            "details": self.details,
        }


class ServiceHealthHub:
    """Central health registry. Call check_all() periodically or read passive marks."""

    SERVICE_NAMES = [
        "bridge", "home_assistant", "telegram",
        "llm_anthropic",
        "news_boursa", "news_gemini",
        "daily_snapshot",
    ]

    def __init__(self, db_path: str = None, hooks=None):
        self._services: dict[str, ServiceStatus] = {}
        self._db_path = db_path
        self._hooks = hooks
        for name in self.SERVICE_NAMES:
            self._services[name] = ServiceStatus(name)

    def set_hooks(self, hooks):
        """Wire hooks after construction (avoids circular init)."""
        self._hooks = hooks

    # ── Passive marks (called by existing code) ──────────
    def mark_up(self, name: str, details: dict = None):
        svc = self._services.get(name)
        if not svc:
            svc = ServiceStatus(name)
            self._services[name] = svc
        was_down = not svc.is_available
        svc.mark_up(details)
        if was_down and self._hooks:
            self._hooks.fire_sync("service_up", name=name)

    def mark_down(self, name: str, reason: str, details: dict = None):
        svc = self._services.get(name)
        if not svc:
            svc = ServiceStatus(name)
            self._services[name] = svc
        was_up = svc.is_available
        svc.mark_down(reason, details)
        if was_up and self._hooks:
            self._hooks.fire_sync("service_down", name=name, reason=reason)

    def is_up(self, name: str) -> bool:
        svc = self._services.get(name)
        return svc.is_available if svc else False

    # ── Active checks (read from existing circuit breakers) ──
    def sync_circuit_breakers(self, cb_ha=None, cb_llm=None, cb_tg=None):
        """Read state from server.py's CircuitBreaker globals."""
        for name, cb in [("home_assistant", cb_ha), ("llm_anthropic", cb_llm), ("telegram", cb_tg)]:
            if cb is None:
                continue
            st = cb.status() if hasattr(cb, "status") else {}
            if cb.state == "closed":
                self.mark_up(name, details=st)
            else:
                self.mark_down(name, reason=f"circuit {cb.state} (failures={cb.failures})", details=st)

    def sync_bridge(self, bridge_status: dict):
        """Read state from bridge_client.get_status()."""
        if bridge_status.get("online"):
            self.mark_up("bridge", details=bridge_status)
        else:
            self.mark_down("bridge",
                           reason=f"offline (failures={bridge_status.get('failure_count', '?')})",
                           details=bridge_status)

    def sync_news(self, last_boursa: str = None, last_gemini: str = None):
        """Check news freshness from module-level timestamps."""
        now = datetime.now(timezone.utc)
        # Boursa: stale if > 15 min
        if last_boursa:
            try:
                ts = datetime.fromisoformat(last_boursa.replace("Z", "+00:00"))
                age_min = (now - ts).total_seconds() / 60
                if age_min < 15:
                    self.mark_up("news_boursa", details={"last_refresh": last_boursa, "age_min": round(age_min, 1)})
                else:
                    self.mark_down("news_boursa", reason=f"stale ({round(age_min)}m)", details={"last_refresh": last_boursa})
            except Exception:
                self.mark_down("news_boursa", reason="bad timestamp")
        else:
            self.mark_down("news_boursa", reason="never refreshed")

        # Gemini: stale if > 60 min
        if last_gemini:
            try:
                ts = datetime.fromisoformat(last_gemini.replace("Z", "+00:00"))
                age_min = (now - ts).total_seconds() / 60
                if age_min < 60:
                    self.mark_up("news_gemini", details={"last_refresh": last_gemini, "age_min": round(age_min, 1)})
                else:
                    self.mark_down("news_gemini", reason=f"stale ({round(age_min)}m)", details={"last_refresh": last_gemini})
            except Exception:
                self.mark_down("news_gemini", reason="bad timestamp")
        else:
            self.mark_down("news_gemini", reason="never refreshed")

    def sync_daily_snapshot(self, db_path: str = None):
        """Check if daily snapshot data is fresh (< 24h)."""
        _db = db_path or self._db_path
        if not _db:
            return
        try:
            conn = sqlite3.connect(_db, timeout=3)
            row = conn.execute("SELECT MAX(updated_at) FROM stock_radar_daily").fetchone()
            conn.close()
            if row and row[0]:
                ts = datetime.fromisoformat(row[0].replace("Z", "+00:00")) if "Z" in row[0] else datetime.fromisoformat(row[0])
                now = datetime.now(timezone.utc)
                if ts.tzinfo is None:
                    from datetime import timezone as tz
                    ts = ts.replace(tzinfo=tz.utc)
                age_h = (now - ts).total_seconds() / 3600
                if age_h < 24:
                    self.mark_up("daily_snapshot", details={"last_update": row[0], "age_hours": round(age_h, 1)})
                else:
                    self.mark_down("daily_snapshot", reason=f"stale ({round(age_h, 1)}h)", details={"last_update": row[0]})
            else:
                self.mark_down("daily_snapshot", reason="no data")
        except Exception as e:
            self.mark_down("daily_snapshot", reason=str(e))

    # ── Aggregate ────────────────────────────────────────
    def check_all(self, cb_ha=None, cb_llm=None, cb_tg=None,
                  bridge_status: dict = None,
                  last_boursa: str = None, last_gemini: str = None) -> dict:
        """Run all sync checks and return full status."""
        self.sync_circuit_breakers(cb_ha, cb_llm, cb_tg)
        if bridge_status:
            self.sync_bridge(bridge_status)
        self.sync_news(last_boursa, last_gemini)
        self.sync_daily_snapshot()
        return self.get_summary()

    def get_summary(self) -> dict:
        services = {name: svc.to_dict() for name, svc in self._services.items()}
        up_count = sum(1 for s in self._services.values() if s.is_available)
        total = len(self._services)
        down_list = [s.name for s in self._services.values() if not s.is_available]
        return {
            "services": services,
            "summary": {
                "total": total,
                "up": up_count,
                "down": total - up_count,
                "all_healthy": up_count == total,
                "down_services": down_list,
            },
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
