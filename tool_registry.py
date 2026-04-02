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
    __slots__ = ("name", "fn", "category", "description", "requires", "call_count", "last_called", "avg_ms")

    def __init__(self, name: str, fn: Callable, category: str = "general",
                 description: str = "", requires: list[str] = None):
        self.name = name
        self.fn = fn
        self.category = category
        self.description = description
        self.requires = requires or []  # e.g. ["home_assistant", "bridge"]
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
                 description: str = "", requires: list[str] = None):
        """Register a tool."""
        self._tools[name] = ToolEntry(name, fn, category, description, requires)
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
        """Call a tool by name. Tracks stats, fires hooks, checks health."""
        if not self._is_enabled():
            raise RuntimeError("tool_registry disabled")
        tool = self._tools.get(name)
        if not tool:
            raise KeyError(f"Unknown tool: {name}")

        # Health check
        if not self.is_available(name):
            unavail = [d for d in tool.requires if self._health and not self._health.is_up(d)]
            raise RuntimeError(f"Tool '{name}' unavailable — deps down: {unavail}")

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
