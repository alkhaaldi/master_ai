"""
Tool Registry — central catalog of all callable capabilities.
Gated by ff.is_enabled("tool_registry").

Usage:
    registry = ToolRegistry(ff)
    registry.register("lights_control", fn, category="home", description="...")
    tool = registry.get("lights_control")
    result = await registry.call("lights_control", entity_id="light.living")
"""
import time
import asyncio
import logging
from typing import Callable, Any, Optional

logger = logging.getLogger("tool_registry")


class ToolEntry:
    """Tool with 3-layer validation: validateInput -> checkPermission -> execute (Tier1 #5)."""
    __slots__ = (
        "name", "fn", "category", "description", "requires",
        "call_count", "last_called", "avg_ms",
        "validate_fn", "permission_fn", "is_read_only", "is_destructive",
    )

    def __init__(self, name: str, fn: Callable, category: str = "general",
                 description: str = "", requires: list[str] = None,
                 validate_fn: Callable = None, permission_fn: Callable = None,
                 is_read_only: bool = False, is_destructive: bool = False):
        self.name = name
        self.fn = fn
        self.category = category
        self.description = description
        self.requires = requires or []
        self.validate_fn = validate_fn       # Layer 1: input validation
        self.permission_fn = permission_fn   # Layer 2: permission check
        self.is_read_only = is_read_only
        self.is_destructive = is_destructive
        self.call_count = 0
        self.last_called = None
        self.avg_ms = 0.0

    def to_dict(self, include_stats: bool = True) -> dict:
        d = {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "requires": self.requires,
        }
        if include_stats:
            d["call_count"] = self.call_count
            d["last_called"] = self.last_called
            d["avg_ms"] = round(self.avg_ms, 1)
        return d


class ToolRegistry:
    """Central catalog of tools. Supports discovery, health-aware routing, and stats."""

    def __init__(self, ff=None, health_hub=None, hooks=None):
        self._tools: dict[str, ToolEntry] = {}
        self._ff = ff
        self._health = health_hub
        self._hooks = hooks

    def _is_enabled(self) -> bool:
        if self._ff:
            return self._ff.is_enabled("tool_registry")
        return True

    def register(self, name: str, fn: Callable, category: str = "general",
                 description: str = "", requires: list[str] = None,
                 validate_fn: Callable = None, permission_fn: Callable = None,
                 is_read_only: bool = False, is_destructive: bool = False):
        """Register a tool with optional validation and permission layers."""
        self._tools[name] = ToolEntry(
            name, fn, category, description, requires,
            validate_fn=validate_fn, permission_fn=permission_fn,
            is_read_only=is_read_only, is_destructive=is_destructive,
        )
        logger.debug("Tool registered: %s [%s]", name, category)

    def get(self, name: str) -> Optional[ToolEntry]:
        return self._tools.get(name)

    def list_tools(self, category: str = None) -> list[dict]:
        """List all tools, optionally filtered by category."""
        tools = self._tools.values()
        if category:
            tools = [t for t in tools if t.category == category]
        return [t.to_dict() for t in sorted(tools, key=lambda t: (t.category, t.name))]

    def categories(self) -> list[str]:
        return sorted(set(t.category for t in self._tools.values()))

    def is_available(self, name: str) -> bool:
        """Check if a tool's dependencies are healthy."""
        tool = self._tools.get(name)
        if not tool:
            return False
        if not tool.requires:
            return True
        if not self._health:
            return True
        return all(self._health.is_up(dep) for dep in tool.requires)

    async def call(self, name: str, **kwargs) -> Any:
        """Call a tool with 3-layer validation (Tier1 #5):
        Layer 1: validateInput (structural checks)
        Layer 2: checkPermission (authorization + health)
        Layer 3: execute (actual call)
        """
        if not self._is_enabled():
            raise RuntimeError("tool_registry disabled")
        tool = self._tools.get(name)
        if not tool:
            raise KeyError(f"Unknown tool: {name}")

        # ── Layer 1: Validate Input ──
        if tool.validate_fn:
            err = tool.validate_fn(**kwargs)
            if err:
                raise ValueError(f"Tool '{name}' input validation failed: {err}")

        # ── Layer 2: Check Permission (health + custom) ──
        if not self.is_available(name):
            unavail = [d for d in tool.requires if self._health and not self._health.is_up(d)]
            raise RuntimeError(f"Tool '{name}' unavailable — deps down: {unavail}")
        if tool.permission_fn:
            allowed = tool.permission_fn(**kwargs)
            if not allowed:
                raise PermissionError(f"Tool '{name}' permission denied")

        # ── Layer 3: Execute ──
        t0 = time.time()
        try:
            if asyncio.iscoroutinefunction(tool.fn):
                result = await tool.fn(**kwargs)
            else:
                result = tool.fn(**kwargs)
            elapsed = (time.time() - t0) * 1000
            tool.call_count += 1
            tool.last_called = time.strftime("%Y-%m-%dT%H:%M:%S")
            tool.avg_ms = (tool.avg_ms * (tool.call_count - 1) + elapsed) / tool.call_count

            if self._hooks:
                self._hooks.fire_sync("tool_executed", name=name, duration_ms=round(elapsed, 1))

            return result
        except Exception as e:
            if self._hooks:
                self._hooks.fire_sync("tool_executed", name=name, error=str(e))
            raise

    def get_stats(self) -> dict:
        return {
            "enabled": self._is_enabled(),
            "total_tools": len(self._tools),
            "categories": self.categories(),
            "tools": self.list_tools(),
        }

    def find(self, query: str) -> list[dict]:
        """Search tools by name or description keyword."""
        q = query.lower()
        return [
            t.to_dict()
            for t in self._tools.values()
            if q in t.name.lower() or q in t.description.lower() or q in t.category.lower()
        ]
