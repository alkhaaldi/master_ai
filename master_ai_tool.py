"""
MasterAITool — Typed tool definitions with autonomy flags (Tier2 #11).

Each command gets declared properties that the system uses for
autonomy scoring, error handling, and resource management.

Builds on Tier1 #5 (tool_registry.py 3-layer validation).

Usage:
    from master_ai_tool import MasterAITool, ToolCategory, TOOL_DEFS

    tool = TOOL_DEFS.get("report")
    ok, reason = tool.can_execute({"bridge_online": False})
    if ok:
        result = await tool.handler(...)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from enum import Enum

logger = logging.getLogger("master_ai_tool")


class ToolCategory(Enum):
    QUERY = "query"          # Read-only lookups
    ANALYSIS = "analysis"    # Compute-intensive analysis
    ACTION = "action"        # Modifies state
    SYSTEM = "system"        # System management


@dataclass
class MasterAITool:
    """Tool definition with properties for autonomy and resource management."""

    name: str
    description: str
    category: ToolCategory = ToolCategory.QUERY

    # Flags (fail-closed defaults, same as Claude Code)
    is_read_only: bool = False
    is_destructive: bool = False
    requires_bridge: bool = False
    requires_llm: bool = False

    # Resource limits
    max_result_chars: int = 4000
    timeout_seconds: int = 60

    # Autonomy scoring
    autonomy_cost: int = 10

    # Handler (set during registration)
    handler: Optional[Callable] = None

    @property
    def computed_autonomy_cost(self) -> int:
        cost = self.autonomy_cost
        if self.is_destructive:
            cost = max(cost, 50)
        if self.requires_llm:
            cost += 10
        if not self.is_read_only:
            cost += 5
        return cost

    def can_execute(self, context: dict) -> tuple:
        """Pre-flight check: can this tool run right now?"""
        if self.requires_bridge and not context.get("bridge_online", False):
            return False, "البريدج مو متصل"
        if self.requires_llm and not context.get("llm_available", True):
            return False, "خدمة الذكاء الاصطناعي غير متاحة"
        return True, ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "is_read_only": self.is_read_only,
            "is_destructive": self.is_destructive,
            "requires_bridge": self.requires_bridge,
            "requires_llm": self.requires_llm,
            "autonomy_cost": self.computed_autonomy_cost,
            "timeout_seconds": self.timeout_seconds,
        }


# Tool catalog — declare ALL commands with their properties
TOOL_DEFS: dict[str, MasterAITool] = {}


def register_tool(tool: MasterAITool):
    """Decorator-compatible tool registration."""
    def decorator(func):
        tool.handler = func
        TOOL_DEFS[tool.name] = tool
        return func
    return decorator


def define_tools():
    """Define all known tools. Called once at startup."""
    defs = [
        MasterAITool(name="status", description="System status check",
                     category=ToolCategory.QUERY, is_read_only=True, autonomy_cost=3),
        MasterAITool(name="report", description="Morning/status report",
                     category=ToolCategory.QUERY, is_read_only=True, autonomy_cost=5),
        MasterAITool(name="lights", description="Light status",
                     category=ToolCategory.QUERY, is_read_only=True, autonomy_cost=3),
        MasterAITool(name="covers", description="Cover/shutter status",
                     category=ToolCategory.QUERY, is_read_only=True, autonomy_cost=3),
        MasterAITool(name="weather", description="Weather report",
                     category=ToolCategory.QUERY, is_read_only=True, autonomy_cost=3),
        MasterAITool(name="locks", description="Door lock status",
                     category=ToolCategory.QUERY, is_read_only=True, autonomy_cost=3),
        MasterAITool(name="radar", description="Stock radar status",
                     category=ToolCategory.ANALYSIS, is_read_only=True,
                     requires_bridge=True, autonomy_cost=15, timeout_seconds=120),
        MasterAITool(name="فرص", description="Golden opportunities scanner",
                     category=ToolCategory.ANALYSIS, is_read_only=True,
                     requires_bridge=True, autonomy_cost=15, timeout_seconds=120),
        MasterAITool(name="تقييم", description="Signal review/evaluation",
                     category=ToolCategory.ANALYSIS, is_read_only=True,
                     requires_bridge=True, autonomy_cost=15),
        MasterAITool(name="موجة", description="Elliott Wave analysis",
                     category=ToolCategory.ANALYSIS, is_read_only=True,
                     requires_bridge=True, requires_llm=True,
                     autonomy_cost=25, timeout_seconds=90),
        MasterAITool(name="scene", description="Activate HA scene",
                     category=ToolCategory.ACTION, is_destructive=False, autonomy_cost=20),
        MasterAITool(name="restart", description="Restart Master AI server",
                     category=ToolCategory.SYSTEM, is_destructive=True, autonomy_cost=80),
    ]
    for d in defs:
        TOOL_DEFS[d.name] = d


# Auto-define on import
define_tools()
