"""Supervisor Agent 端到端边界测试 — 路由、并行执行、状态同步、异常处理。"""

from __future__ import annotations

import pytest

from app.agents.core.tool import Tool, ToolRegistry, ToolResult
from app.agents.core.state import AgentState
from app.agents.supervisor.supervisor_agent import (
    SupervisorAgent,
    RouteStrategy,
    AgentExecutionContext,
)


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def registry():
    reg = ToolRegistry()
    return reg


@pytest.fixture
def supervisor(registry):
    return SupervisorAgent(
        tool_registry=registry,
        db=None,
        route_strategy=RouteStrategy.KEYWORD,
        parallel_enabled=False,
    )


# ═══════════════════════════════════════════════════════════
# Route Strategy: Keyword
# ═══════════════════════════════════════════════════════════

def test_keyword_route_usb():
    sup = SupervisorAgent(route_strategy=RouteStrategy.KEYWORD, parallel_enabled=False)
    plan = sup.plan(user_query="USB设备无法枚举", log_content="xhci timeout error")
    assert "usb_agent" in plan


def test_keyword_route_bluetooth():
    sup = SupervisorAgent(route_strategy=RouteStrategy.KEYWORD, parallel_enabled=False)
    plan = sup.plan(user_query="蓝牙配对失败 hci error", log_content="")
    assert "bluetooth_agent" in plan


def test_keyword_route_network():
    sup = SupervisorAgent(route_strategy=RouteStrategy.KEYWORD, parallel_enabled=False)
    plan = sup.plan(user_query="WiFi DHCP timeout", log_content="")
    assert "network_agent" in plan


def test_keyword_route_kernel():
    sup = SupervisorAgent(route_strategy=RouteStrategy.KEYWORD, parallel_enabled=False)
    plan = sup.plan(user_query="kernel panic oops", log_content="")
    assert "kernel_agent" in plan


def test_keyword_route_multi_agent():
    sup = SupervisorAgent(route_strategy=RouteStrategy.KEYWORD, parallel_enabled=False)
    plan = sup.plan(user_query="USB断开导致kernel panic", log_content="xhci timeout\nkernel panic")
    assert "usb_agent" in plan
    assert "kernel_agent" in plan


def test_keyword_route_fallback_to_general():
    sup = SupervisorAgent(route_strategy=RouteStrategy.KEYWORD, parallel_enabled=False)
    plan = sup.plan(user_query="不知道什么问题", log_content="")
    assert "general_diagnostic_agent" in plan


def test_keyword_route_empty_query():
    sup = SupervisorAgent(route_strategy=RouteStrategy.KEYWORD, parallel_enabled=False)
    plan = sup.plan(user_query="", log_content="")
    assert "general_diagnostic_agent" in plan


# ═══════════════════════════════════════════════════════════
# Route Strategy: LLM parsing
# ═══════════════════════════════════════════════════════════

def test_parse_llm_routing_json_array():
    sup = SupervisorAgent(route_strategy=RouteStrategy.LLM, parallel_enabled=False)
    response = '["usb_agent", "kernel_agent"]'
    result = sup._parse_llm_routing_response(response)
    assert result == ["usb_agent", "kernel_agent"]


def test_parse_llm_routing_with_markdown():
    sup = SupervisorAgent(route_strategy=RouteStrategy.LLM, parallel_enabled=False)
    response = '```json\n["bluetooth_agent"]\n```'
    result = sup._parse_llm_routing_response(response)
    assert result == ["bluetooth_agent"]


def test_parse_llm_routing_invalid_json():
    sup = SupervisorAgent(route_strategy=RouteStrategy.LLM, parallel_enabled=False)
    response = "我认为应该使用 usb_agent 和 network_agent"
    result = sup._parse_llm_routing_response(response)
    assert "usb_agent" in result
    assert "network_agent" in result


def test_parse_llm_routing_no_match():
    sup = SupervisorAgent(route_strategy=RouteStrategy.LLM, parallel_enabled=False)
    response = "无法确定问题类型"
    result = sup._parse_llm_routing_response(response)
    assert result == ["general_diagnostic_agent"]


def test_parse_llm_routing_empty():
    sup = SupervisorAgent(route_strategy=RouteStrategy.LLM, parallel_enabled=False)
    response = "[]"
    result = sup._parse_llm_routing_response(response)
    # 空列表的解析结果为 []，plan() 方在调用层回退到 general
    assert result == [] or result == ["general_diagnostic_agent"]


# ═══════════════════════════════════════════════════════════
# Sequential Execution
# ═══════════════════════════════════════════════════════════

def test_execute_single_agent_sequential(supervisor):
    ctx = AgentExecutionContext({
        "user_query": "USB timeout",
        "log_content": "xhci timeout at port 1",
        "events": [],
    })
    result = supervisor._execute_single_agent("usb_agent", ctx)
    assert result["agent"] == "usb_agent"
    assert result["status"] in ("completed", "failed")


def test_execute_unknown_agent(supervisor):
    ctx = AgentExecutionContext({"user_query": "test", "log_content": "", "events": []})
    result = supervisor._execute_single_agent("nonexistent_agent", ctx)
    assert result["status"] == "not_implemented"


def test_execute_agents_sequential(supervisor):
    ctx = AgentExecutionContext({
        "user_query": "USB timeout",
        "log_content": "xhci error",
        "events": [],
    })
    results = supervisor._execute_agents_sequential(["usb_agent", "general_diagnostic_agent"], ctx)
    assert len(results) == 2
    assert all(r["agent"] in ["usb_agent", "general_diagnostic_agent"] for r in results)


# ═══════════════════════════════════════════════════════════
# Parallel Execution (边界测试)
# ═══════════════════════════════════════════════════════════

def test_parallel_execution_enabled():
    sup = SupervisorAgent(route_strategy=RouteStrategy.KEYWORD, parallel_enabled=True)
    ctx = AgentExecutionContext({
        "user_query": "USB断开",
        "log_content": "",
        "events": [],
    })
    results = sup._execute_agents_parallel(["usb_agent", "network_agent"], ctx)
    assert len(results) == 2
    agents = {r["agent"] for r in results}
    assert agents == {"usb_agent", "network_agent"}


def test_parallel_execution_empty_plan():
    sup = SupervisorAgent(parallel_enabled=True)
    ctx = AgentExecutionContext({"user_query": "", "log_content": "", "events": []})
    # 空计划应安全处理
    try:
        results = sup._execute_agents_parallel([], ctx)
        assert results == []
    except ValueError:
        # 某些实现可能不接受空列表
        pass


def test_parallel_execution_single_agent():
    sup = SupervisorAgent(parallel_enabled=True)
    ctx = AgentExecutionContext({
        "user_query": "kernel panic",
        "log_content": "",
        "events": [],
    })
    results = sup._execute_agents_parallel(["kernel_agent"], ctx)
    assert len(results) == 1
    assert results[0]["agent"] == "kernel_agent"


# ═══════════════════════════════════════════════════════════
# AgentExecutionContext
# ═══════════════════════════════════════════════════════════

def test_exec_ctx_initial_state():
    ctx = AgentExecutionContext({"key": "value"})
    assert ctx.get("key") == "value"
    assert ctx.get("missing", "default") == "default"
    assert len(ctx.completed_agents) == 0
    assert len(ctx.failed_agents) == 0


def test_exec_ctx_record_completed():
    ctx = AgentExecutionContext({})
    from app.agents.core.agent import AgentResult
    ctx.record_agent_done("test_agent", AgentResult(state=AgentState.COMPLETED, summary="ok"))
    assert "test_agent" in ctx.completed_agents
    assert ctx.get_agent_state("test_agent") == AgentState.COMPLETED


def test_exec_ctx_record_failed():
    ctx = AgentExecutionContext({})
    from app.agents.core.agent import AgentResult
    ctx.record_agent_done("test_agent", AgentResult(state=AgentState.FAILED, error="error"))
    assert "test_agent" in ctx.failed_agents
    assert ctx.get_agent_state("test_agent") == AgentState.FAILED


def test_exec_ctx_all_states():
    ctx = AgentExecutionContext({})
    ctx.record_agent_start("agent_a")
    assert ctx.get_agent_state("agent_a") == AgentState.EXECUTING
    states = ctx.all_agent_states
    assert "agent_a" in states


def test_exec_ctx_get_nonexistent_result():
    ctx = AgentExecutionContext({})
    assert ctx.get_agent_result("nonexistent") is None


# ═══════════════════════════════════════════════════════════
# Health Check
# ═══════════════════════════════════════════════════════════

def test_supervisor_health_check(supervisor):
    health = supervisor.health_check()
    assert health["supervisor"] == "healthy"
    assert "agents" in health
    assert health["total"] > 0
    assert health["healthy_count"] > 0


# ═══════════════════════════════════════════════════════════
# Specialized Agent: USBAgent Run
# ═══════════════════════════════════════════════════════════

def test_usb_agent_run_with_events():
    from app.agents.specialized.usb_agent import USBAgent
    agent = USBAgent()
    result = agent.run(
        user_query="USB 超时",
        log_content="xhci: Command timeout\nusb 1-1: device not accepting address",
        events=[
            {"message": "xhci: Command timeout", "is_error": True, "level": "ERROR"},
            {"message": "usb 1-1: device not accepting address", "is_error": True, "level": "ERROR"},
        ],
    )
    assert result is not None
    assert result.state in (AgentState.COMPLETED, AgentState.FAILED)
    assert isinstance(result.summary, str)


def test_usb_agent_run_empty_events():
    from app.agents.specialized.usb_agent import USBAgent
    agent = USBAgent()
    result = agent.run(user_query="", log_content="", events=[])
    assert result is not None
    assert "未检测到" in result.summary or result.success


# ═══════════════════════════════════════════════════════════
# Specialized Agent: KernelAgent Run
# ═══════════════════════════════════════════════════════════

def test_kernel_agent_run_with_panic():
    from app.agents.specialized.kernel_agent import KernelAgent
    agent = KernelAgent()
    result = agent.run(
        user_query="kernel panic",
        log_content="Kernel panic - not syncing: Fatal exception\nCall trace:\n...",
        events=[
            {"message": "Kernel panic - not syncing", "is_error": True, "level": "CRITICAL"},
            {"message": "Call trace:", "is_error": True},
        ],
    )
    assert result is not None
    assert isinstance(result.summary, str)


def test_kernel_agent_run_no_events():
    from app.agents.specialized.kernel_agent import KernelAgent
    agent = KernelAgent()
    result = agent.run(user_query="", log_content="", events=[])
    assert result is not None
    assert "未检测到" in result.summary or result.success


# ═══════════════════════════════════════════════════════════
# Specialized Agent: GeneralDiagnosticAgent
# ═══════════════════════════════════════════════════════════

def test_general_agent_run():
    from app.agents.specialized.general_agent import GeneralDiagnosticAgent
    agent = GeneralDiagnosticAgent()
    result = agent.run(
        user_query="设备启动慢",
        log_content="init: starting service\nsystemd: timeout",
        events=[
            {"message": "systemd: timeout waiting for device", "is_error": True, "level": "ERROR", "module": "systemd"},
            {"message": "init: starting service", "is_error": False, "level": "INFO", "module": "init"},
        ],
    )
    assert result is not None
    assert result.success


# ═══════════════════════════════════════════════════════════
# ReportGenerator
# ═══════════════════════════════════════════════════════════

def test_report_generator_run():
    from app.agents.specialized.report_generator import ReportGenerator
    agent = ReportGenerator()
    result = agent.run(
        agent_results=[
            {"agent": "usb_agent", "status": "completed",
             "summary": "检测到 USB 超时问题", "metadata": {"issues_found": 2}},
            {"agent": "kernel_agent", "status": "completed",
             "summary": "检测到 kernel panic", "metadata": {"issues_found": 1}},
        ],
        user_query="USB timeout 导致 kernel panic",
    )
    assert result is not None
    assert result.success
    assert "诊断报告" in result.summary


def test_report_generator_empty_results():
    from app.agents.specialized.report_generator import ReportGenerator
    agent = ReportGenerator()
    result = agent.run(agent_results=[], user_query="test")
    assert result is not None
    assert result.success


def test_report_generator_mixed_results():
    from app.agents.specialized.report_generator import ReportGenerator
    agent = ReportGenerator()
    result = agent.run(
        agent_results=[
            {"agent": "usb_agent", "status": "completed",
             "summary": "USB OK", "metadata": {"issues_found": 0}},
            {"agent": "bluetooth_agent", "status": "failed", "error": "timeout"},
            {"agent": "nonexistent", "status": "not_implemented"},
        ],
        user_query="test",
    )
    assert result is not None
    assert result.success
