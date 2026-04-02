"""
Hooks — async event system for before/after key operations.
Gated by ff.is_enabled("hooks").

Usage:
    hooks = HookRegistry("data/life.db")
    hooks.on("service_down", my_handler)
    await hooks.fire("service_down", service="bridge", reason="offline")
"""
import asyncio
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Callable, Any

logger = logging.getLogger("hooks")


class HookRegistry:
    """Central event bus. Handlers are async callables registered per event name."""

    # Well-known events
    EVENTS = [
        "service_down",      # service went down (name, reason)
        "service_up",        # service recovered (name)
        "alert_sent",        # KAIROS sent an alert (msg)
        "tg_message_in",     # Telegram message received (chat_id, text)
        "tg_message_out",    # Telegram message sent (chat_id, text)
        "flag_toggled",      # Feature flag changed (name, enabled)
        "llm_call_start",    # LLM call starting (model, prompt_len)
        "llm_call_end",      # LLM call finished (model, duration, tokens)
        "tool_executed",     # Tool was called (name, args, result_len)
        "daily_summary",     # Daily summary generated
        # Trading events (Layer 2)
        "after_signal",      # Radar detected a new signal (symbol, signal_type, price, score)
        "before_trade_alert",# Before sending trade alert to TG (symbol, action, confidence)
        "after_daily_refresh",# Daily snapshot refreshed (ok_count, err_count)
    ]

    def __init__(self, db_path: str = None, ff=None):
        self._handlers: dict[str, list[Callable]] = {}
        self._db_path = db_path
        self._ff = ff
        self._fire_count = 0
        self._error_count = 0
        if db_path:
            self._init_db()

    def _conn(self):
        return sqlite3.connect(self._db_path, timeout=5)

    def _init_db(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS hook_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                event TEXT NOT NULL,
                handler TEXT,
                status TEXT DEFAULT 'ok',
                detail TEXT
            )""")
            c.commit()

    def _is_enabled(self) -> bool:
        if self._ff:
            return self._ff.is_enabled("hooks")
        return True

    def on(self, event: str, handler: Callable):
        """Register a handler for an event."""
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)
        logger.debug("Hook registered: %s -> %s", event, handler.__name__)

    def off(self, event: str, handler: Callable = None):
        """Unregister a handler. If handler is None, remove all for event."""
        if handler is None:
            self._handlers.pop(event, None)
        elif event in self._handlers:
            self._handlers[event] = [h for h in self._handlers[event] if h != handler]

    async def fire(self, event: str, **kwargs) -> list[Any]:
        """Fire an event. Returns list of handler results. Errors are logged, not raised."""
        if not self._is_enabled():
            return []
        handlers = self._handlers.get(event, [])
        if not handlers:
            return []

        self._fire_count += 1
        results = []
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(**kwargs)
                else:
                    result = handler(**kwargs)
                results.append(result)
                self._log_event(event, handler.__name__, "ok")
            except Exception as e:
                self._error_count += 1
                logger.error("Hook %s.%s error: %s", event, handler.__name__, e)
                self._log_event(event, handler.__name__, "error", str(e))
                results.append(None)
        return results

    def fire_sync(self, event: str, **kwargs):
        """Fire event from sync context (schedules on event loop)."""
        if not self._is_enabled():
            return
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.fire(event, **kwargs))
            else:
                loop.run_until_complete(self.fire(event, **kwargs))
        except RuntimeError:
            pass  # no event loop

    def _log_event(self, event: str, handler: str, status: str, detail: str = None):
        if not self._db_path:
            return
        try:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO hook_log (event, handler, status, detail) VALUES (?, ?, ?, ?)",
                    (event, handler, status, detail),
                )
                c.commit()
        except Exception:
            pass

    def get_log(self, limit: int = 50, event: str = None) -> list[dict]:
        if not self._db_path:
            return []
        with self._conn() as c:
            if event:
                rows = c.execute(
                    "SELECT timestamp, event, handler, status, detail FROM hook_log WHERE event=? ORDER BY id DESC LIMIT ?",
                    (event, limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT timestamp, event, handler, status, detail FROM hook_log ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [{"timestamp": r[0], "event": r[1], "handler": r[2], "status": r[3], "detail": r[4]} for r in rows]

    def get_stats(self) -> dict:
        registered = {ev: len(hs) for ev, hs in self._handlers.items() if hs}
        return {
            "enabled": self._is_enabled(),
            "events_fired": self._fire_count,
            "errors": self._error_count,
            "registered_handlers": registered,
            "total_handlers": sum(len(hs) for hs in self._handlers.values()),
            "known_events": self.EVENTS,
        }

    def cleanup(self, days: int = 7):
        if not self._db_path:
            return
        try:
            with self._conn() as c:
                c.execute("DELETE FROM hook_log WHERE timestamp < datetime('now', ?)", (f"-{days} days",))
                c.commit()
        except Exception:
            pass
