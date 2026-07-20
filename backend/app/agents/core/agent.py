"""Base Agent class and execution engine."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.agents.core.state import AgentState, AgentStateMachine
from app.agents.core.tool import ToolRegistry


@dataclass
class AgentResult:
    """Result of a complete agent execution."""

    state: AgentState
    summary: str = ""
    steps: List[Dict[str, Any]] = field(default_factory=list)
    tool_plan: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.state == AgentState.COMPLETED


class BaseAgent(ABC):
    """Abstract base for diagnostic agents.

    Subclasses define the planning strategy and tool usage for
    specific diagnostic scenarios (e.g. log analysis, bug triage).
    """

    name: str = "base_agent"
    description: str = "Base agent — override in subclass."

    def __init__(self, tool_registry: Optional[ToolRegistry] = None) -> None:
        self.tools = tool_registry or ToolRegistry()
        self.state_machine = AgentStateMachine()
        self._execution_steps: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self, **context: Any) -> AgentResult:
        """Execute the agent workflow end-to-end."""
        self.state_machine = AgentStateMachine()

        try:
            # 1. Plan
            self.state_machine.transition_to(AgentState.PLANNING)
            plan = self.plan(**context)
            self.state_machine.transition_to(AgentState.PLAN_READY)

            # 2. Execute
            self.state_machine.transition_to(AgentState.EXECUTING)
            result = self._execute_plan(plan, **context)

            # 3. Validate
            self.state_machine.transition_to(AgentState.VALIDATING)
            if self.validate(result):
                self.state_machine.transition_to(AgentState.COMPLETED)
            else:
                self.state_machine.transition_to(AgentState.FAILED)
                return AgentResult(
                    state=AgentState.FAILED,
                    error="Validation failed",
                    steps=self._execution_steps,
                )

            return AgentResult(
                state=self.state_machine.state,
                summary=self._build_summary(result),
                steps=self._execution_steps,
                tool_plan=self._build_tool_plan(plan),
            )

        except Exception as exc:
            self.state_machine.transition_to(AgentState.FAILED)
            return AgentResult(
                state=AgentState.FAILED,
                error=str(exc),
                steps=self._execution_steps,
            )

    # ------------------------------------------------------------------
    # Abstract
    # ------------------------------------------------------------------

    @abstractmethod
    def plan(self, **context: Any) -> List[str]:
        """Generate an ordered list of tool names to execute."""

    def validate(self, result: Dict[str, Any]) -> bool:
        """Validate the result of tool execution. Override for custom logic."""
        return True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _execute_plan(self, plan: List[str], **context: Any) -> Dict[str, Any]:
        """Execute each tool in the plan sequentially."""
        results: Dict[str, Any] = {}
        ctx = dict(context)

        for step_idx, tool_name in enumerate(plan):
            step_result = {"step": step_idx + 1, "tool": tool_name, "status": "started"}

            try:
                result = self.tools.execute(tool_name, **ctx)
                if result.success:
                    ctx[tool_name + "_result"] = result.data
                    step_result["status"] = "completed"
                    step_result["output"] = str(result.data)[:500]
                else:
                    step_result["status"] = "failed"
                    step_result["error"] = result.error
            except Exception as exc:
                step_result["status"] = "failed"
                step_result["error"] = str(exc)

            self._execution_steps.append(step_result)

        return ctx

    def _build_summary(self, result: Dict[str, Any]) -> str:
        completed = sum(1 for s in self._execution_steps if s.get("status") == "completed")
        total = len(self._execution_steps)
        return f"Agent execution completed: {completed}/{total} steps succeeded."

    @staticmethod
    def _build_tool_plan(plan: List[str]) -> List[Dict[str, Any]]:
        return [{"name": name, "status": "planned"} for name in plan]
