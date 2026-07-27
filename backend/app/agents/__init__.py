"""Agents package — exports core framework and supervisor."""

from app.agents.core.agent import BaseAgent, AgentResult
from app.agents.core.state import AgentState, AgentStateMachine
from app.agents.core.tool import Tool, ToolRegistry, ToolResult
from app.agents.supervisor.supervisor_agent import (
    SupervisorAgent,
    RouteStrategy,
    AgentExecutionContext,
)
from app.agents.tools.builtin import create_default_registry

__all__ = [
    "BaseAgent", "AgentResult",
    "AgentState", "AgentStateMachine",
    "Tool", "ToolRegistry", "ToolResult",
    "SupervisorAgent",
    "RouteStrategy",
    "AgentExecutionContext",
    "create_default_registry",
]
