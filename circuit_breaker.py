"""
Reusable Circuit Breaker — Tier1 Pattern #3 from Claude Code Source Analysis.

Usage:
    cb = CircuitBreaker("bridge", failure_threshold=3, cooldown_seconds=60)
    if cb.allow_request():
        try:
            result = await do_request()
            cb.record_success()
        except Exception:
            cb.record_failure()
    else:
        # Use cached/degraded response
        ...
"""
import time
import logging

logger = logging.getLogger("circuit_breaker")


class CircuitBreaker:
    """Track consecutive failures; auto-open after threshold; auto-close after cooldown."""

    __slots__ = (
        "name", "failure_threshold", "cooldown_seconds",
        "_failure_count", "_last_failure_time", "_state",
    )

    def __init__(self, name: str, failure_threshold: int = 3, cooldown_seconds: int = 60):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._state = "closed"  # closed=OK, open=blocked

    @property
    def state(self) -> str:
        # Auto-reset if cooldown expired
        if self._state == "open" and (time.time() - self._last_failure_time) >= self.cooldown_seconds:
            self._state = "closed"
            self._failure_count = 0
            logger.info("[%s] circuit breaker reset after cooldown", self.name)
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def allow_request(self) -> bool:
        """Return True if requests are allowed (circuit closed or cooldown expired)."""
        return self.state == "closed"

    def record_success(self):
        """Reset failure count on success."""
        if self._failure_count > 0:
            logger.info("[%s] circuit breaker recovered (was at %d failures)", self.name, self._failure_count)
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self):
        """Increment failure count; open circuit if threshold reached."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold and self._state == "closed":
            self._state = "open"
            logger.warning("[%s] circuit breaker OPEN after %d consecutive failures", self.name, self._failure_count)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "failures": self._failure_count,
            "threshold": self.failure_threshold,
            "cooldown": self.cooldown_seconds,
        }
