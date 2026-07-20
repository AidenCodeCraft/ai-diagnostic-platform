"""Unit tests for the Agent Framework core (Commit 008)."""
from __future__ import annotations

import pytest

from app.agents.core.tool import Tool, ToolRegistry, ToolResult
from app.agents.core.state import AgentState, AgentStateMachine
from app.agents.core.agent import BaseAgent, AgentResult
from app.agents.tools.builtin import (
    ParseLogTool,
    RuleCheckTool,
    LLMAnalyzeTool,
    GenerateReportTool,
    create_default_registry,
)
from app.agents.planner.simple_planner import SimplePlanner


# ------------------------------------------------------------------
# ToolResult
# ------------------------------------------------------------------


def test_tool_result_success():
    result = ToolResult(success=True, data={"key": "value"})
    assert result.success is True
    assert result.data == {"key": "value"}
    assert result.error is None


def test_tool_result_failure():
    result = ToolResult(success=False, error="something went wrong")
    assert result.success is False
    assert result.error == "something went wrong"


# ------------------------------------------------------------------
# Tool / ToolRegistry
# ------------------------------------------------------------------


class _DummyTool(Tool):
    name = "dummy"
    description = "A test tool"

    def execute(self, **kwargs):
        return ToolResult(success=True, data=kwargs)


def test_tool_registry_register_and_get():
    registry = ToolRegistry()
    registry.register(_DummyTool())
    assert "dummy" in registry
    assert registry.get("dummy") is not None
    assert registry.get("nonexistent") is None


def test_tool_registry_execute():
    registry = ToolRegistry()
    registry.register(_DummyTool())
    result = registry.execute("dummy", foo="bar")
    assert result.success
    assert result.data == {"foo": "bar"}


def test_tool_registry_execute_nonexistent():
    registry = ToolRegistry()
    result = registry.execute("nonexistent")
    assert result.success is False
    assert "not found" in result.error


def test_tool_registry_list_specs():
    registry = ToolRegistry()
    registry.register(_DummyTool())
    specs = registry.list_specs()
    assert len(specs) == 1
    assert specs[0]["name"] == "dummy"


def test_tool_to_spec():
    tool = ParseLogTool()
    spec = tool.to_spec()
    assert spec["name"] == "parse_log"
    assert "description" in spec


# ------------------------------------------------------------------
# AgentStateMachine
# ------------------------------------------------------------------


def test_state_machine_initial_state():
    sm = AgentStateMachine()
    assert sm.state == AgentState.CREATED
    assert sm.is_active() is True


def test_state_machine_valid_transitions():
    sm = AgentStateMachine()
    sm.transition_to(AgentState.PLANNING)
    assert sm.state == AgentState.PLANNING
    sm.transition_to(AgentState.PLAN_READY)
    assert sm.state == AgentState.PLAN_READY


def test_state_machine_completed_is_terminal():
    sm = AgentStateMachine()
    sm.transition_to(AgentState.PLANNING)
    sm.transition_to(AgentState.PLAN_READY)
    sm.transition_to(AgentState.EXECUTING)
    sm.transition_to(AgentState.COMPLETED)
    assert sm.is_terminal() is True
    assert sm.is_active() is False


def test_state_machine_invalid_transition_raises():
    sm = AgentStateMachine()
    with pytest.raises(ValueError, match="Invalid state transition"):
        sm.transition_to(AgentState.COMPLETED)  # CREATED -> COMPLETED not allowed


def test_state_machine_failed_can_retry():
    sm = AgentStateMachine()
    sm.transition_to(AgentState.FAILED)
    assert sm.is_terminal() is True
    sm.transition_to(AgentState.PLANNING)  # allowed retry
    assert sm.state == AgentState.PLANNING


# ------------------------------------------------------------------
# AgentResult
# ------------------------------------------------------------------


def test_agent_result_success():
    result = AgentResult(state=AgentState.COMPLETED, summary="done")
    assert result.success is True
    assert result.summary == "done"


def test_agent_result_failure():
    result = AgentResult(state=AgentState.FAILED, error="boom")
    assert result.success is False
    assert result.error == "boom"


# ------------------------------------------------------------------
# BaseAgent
# ------------------------------------------------------------------


class _TestAgent(BaseAgent):
    name = "test_agent"

    def plan(self, **context):
        return ["dummy", "dummy"]

    def validate(self, result):
        return result.get("dummy_result") is not None


def test_base_agent_executes_plan():
    registry = ToolRegistry()
    registry.register(_DummyTool())

    agent = _TestAgent(tool_registry=registry)
    result = agent.run(task="test")

    assert result.success is True
    assert len(result.steps) == 2
    for step in result.steps:
        assert step["status"] == "completed"


def test_base_agent_fails_on_tool_error():
    class _FailingTool(Tool):
        name = "failer"
        description = "Always fails"

        def execute(self, **kwargs):
            return ToolResult(success=False, error="always fails")

    registry = ToolRegistry()
    registry.register(_FailingTool())

    agent = _TestAgent(tool_registry=registry)
    agent.plan = lambda **ctx: ["failer", "failer"]

    result = agent.run()
    assert result.state == AgentState.FAILED


def test_base_agent_plan_result():
    registry = ToolRegistry()
    registry.register(_DummyTool())

    agent = _TestAgent(tool_registry=registry)
    result = agent.run()

    assert result.success is True
    assert len(result.tool_plan) == 2
    assert result.tool_plan[0]["name"] == "dummy"
    assert result.tool_plan[0]["status"] == "planned"


# ------------------------------------------------------------------
# SimplePlanner
# ------------------------------------------------------------------


def test_simple_planner_returns_default_plan():
    planner = SimplePlanner()
    plan = planner.build_plan(log_id=1)
    assert plan == ["parse_log", "rule_check", "llm_analyze", "generate_report"]


# ------------------------------------------------------------------
# Built-in tools
# ------------------------------------------------------------------


def test_parse_log_tool_missing_path():
    tool = ParseLogTool()
    result = tool.execute()
    assert result.success is False
    assert "log_file_path" in result.error


def test_rule_check_tool_empty_events():
    tool = RuleCheckTool()
    result = tool.execute(parse_log_result={"events": []})
    assert result.success is True
    assert result.data["count"] == 0


def test_create_default_registry():
    registry = create_default_registry()
    assert "parse_log" in registry
    assert "rule_check" in registry
    assert "llm_analyze" in registry
    assert "generate_report" in registry
    assert len(registry.tool_names) == 4
