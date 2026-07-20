"""Unified tool interface and registry for the Agent framework."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ToolResult:
    """Result of executing a tool."""

    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class Tool(ABC):
    """Abstract base for all agent tools.

    Each tool has a name, description (for LLM function-calling),
    and an execute() method that performs the actual work.
    """

    name: str = "base_tool"
    description: str = "Base tool — override in subclass."

    def to_spec(self) -> Dict[str, Any]:
        """Return tool specification for LLM function calling."""
        return {
            "name": self.name,
            "description": self.description,
        }

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with given parameters."""


class ToolRegistry:
    """Registry of available tools, keyed by name."""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def execute(self, name: str, **kwargs: Any) -> ToolResult:
        tool = self.get(name)
        if not tool:
            return ToolResult(success=False, error=f"Tool not found: {name}")
        return tool.execute(**kwargs)

    def list_specs(self) -> List[Dict[str, Any]]:
        return [tool.to_spec() for tool in self._tools.values()]

    @property
    def tool_names(self) -> List[str]:
        return list(self._tools.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._tools
