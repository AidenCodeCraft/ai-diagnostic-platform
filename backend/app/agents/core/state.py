"""Agent state machine for tracking execution lifecycle."""

from __future__ import annotations

from enum import Enum
from typing import Dict, Set


class AgentState(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    PLAN_READY = "PLAN_READY"
    EXECUTING = "EXECUTING"
    WAITING_TOOL = "WAITING_TOOL"
    REASONING = "REASONING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# Allowed transitions
STATE_TRANSITIONS: Dict[AgentState, Set[AgentState]] = {
    AgentState.CREATED: {AgentState.PLANNING, AgentState.FAILED},
    AgentState.PLANNING: {AgentState.PLAN_READY, AgentState.FAILED},
    AgentState.PLAN_READY: {AgentState.EXECUTING, AgentState.FAILED},
    AgentState.EXECUTING: {AgentState.WAITING_TOOL, AgentState.REASONING, AgentState.VALIDATING, AgentState.COMPLETED, AgentState.FAILED},
    AgentState.WAITING_TOOL: {AgentState.EXECUTING, AgentState.FAILED},
    AgentState.REASONING: {AgentState.EXECUTING, AgentState.VALIDATING, AgentState.FAILED},
    AgentState.VALIDATING: {AgentState.COMPLETED, AgentState.FAILED},
    AgentState.COMPLETED: set(),
    AgentState.FAILED: {AgentState.PLANNING},  # Allow retry
}

# Terminal states
TERMINAL_STATES: Set[AgentState] = {AgentState.COMPLETED, AgentState.FAILED}


class AgentStateMachine:
    """Manages and validates agent state transitions."""

    def __init__(self, initial: AgentState = AgentState.CREATED) -> None:
        self.state = initial

    def transition_to(self, target: AgentState) -> None:
        allowed = STATE_TRANSITIONS.get(self.state, set())
        if target not in allowed:
            raise ValueError(
                f"Invalid state transition: {self.state.value} -> {target.value}"
            )
        self.state = target

    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def is_active(self) -> bool:
        return not self.is_terminal()
