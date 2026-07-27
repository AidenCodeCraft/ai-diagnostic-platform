"""Supervisor Agent — 多 Agent 协调者（增强版）。

职责：
- LLM 辅助路由：使用 LLM 分析用户问题，自动选择合适的专业 Agent
- 关键字回退路由：LLM 不可用时退回关键词匹配
- 并行执行：支持并行调用独立的专业 Agent
- 状态同步：统一追踪各 Agent 执行状态
- 结果汇总：综合各 Agent 分析结果，生成诊断报告

架构：
    User Query
        │
        ▼
    ┌─────────────────┐
    │  Supervisor Agent │  ← 分析问题 → 路由到专业 Agent
    │  (Router + Sync)  │
    └──────┬──────────┘
           │
    ┌──────┼──────┬──────────┬──────────┐
    ▼      ▼       ▼          ▼          ▼
   USB    BT    Network   Kernel    General
   Agent  Agent  Agent    Agent     Agent
           │
    ┌──────┴──────┐
    ▼             ▼
   汇总     Report Generator
"""

from __future__ import annotations

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.agents.core.agent import BaseAgent, AgentResult
from app.agents.core.tool import ToolRegistry
from app.agents.core.state import AgentState
from app.agents.specialized.usb_agent import USBAgent
from app.agents.specialized.bluetooth_agent import BluetoothAgent
from app.agents.specialized.network_agent import NetworkAgent
from app.agents.specialized.kernel_agent import KernelAgent
from app.agents.specialized.general_agent import GeneralDiagnosticAgent
from app.agents.specialized.report_generator import ReportGenerator
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class RouteStrategy(str, Enum):
    """路由策略枚举。"""
    LLM = "llm"       # LLM 智能路由
    KEYWORD = "keyword"  # 关键字匹配路由
    HYBRID = "hybrid"    # LLM + 关键字混合路由（LLM 优先，失败回退到关键字）


class AgentExecutionContext:
    """Agent 执行上下文 — 状态同步容器。

    追踪：
    - 各 Agent 的启动/完成/失败状态
    - 执行顺序和依赖关系
    - 中间结果共享
    """

    def __init__(self, context: Dict[str, Any]):
        self._context = dict(context)
        self._agent_states: Dict[str, AgentState] = {}
        self._agent_results: Dict[str, AgentResult] = {}
        self._completed: Set[str] = set()
        self._failed: Set[str] = set()

    def get(self, key: str, default: Any = None) -> Any:
        return self._context.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._context[key] = value

    def update(self, mapping: Dict[str, Any]) -> None:
        self._context.update(mapping)

    def record_agent_start(self, agent_name: str) -> None:
        self._agent_states[agent_name] = AgentState.EXECUTING

    def record_agent_done(self, agent_name: str, result: AgentResult) -> None:
        self._agent_results[agent_name] = result
        if result.success:
            self._completed.add(agent_name)
            self._agent_states[agent_name] = AgentState.COMPLETED
        else:
            self._failed.add(agent_name)
            self._agent_states[agent_name] = AgentState.FAILED

    def get_agent_state(self, agent_name: str) -> Optional[AgentState]:
        return self._agent_states.get(agent_name)

    def get_agent_result(self, agent_name: str) -> Optional[AgentResult]:
        return self._agent_results.get(agent_name)

    @property
    def completed_agents(self) -> Set[str]:
        return self._completed.copy()

    @property
    def failed_agents(self) -> Set[str]:
        return self._failed.copy()

    @property
    def all_agent_states(self) -> Dict[str, AgentState]:
        return dict(self._agent_states)


class SupervisorAgent(BaseAgent):
    """Supervisor Agent — 多 Agent 系统总调度器。

    核心能力：
    1. LLM 辅助路由：调用 LLM 分析问题语义，智能选择专业 Agent
    2. 关键字回退：LLM 不可用时确保系统仍可运行
    3. 并行执行：独立 Agent 并行运行提高效率
    4. 状态同步：AgentExecutionContext 追踪全局状态
    5. 结果汇总：ReportGenerator 生成综合报告
    """

    name = "supervisor_agent"
    description = "Coordinates multiple specialized agents with LLM-assisted routing and parallel execution."

    # 关键词路由表（当 LLM 不可用时的回退方案）
    KEYWORD_ROUTE_MAP = {
        "usb": {
            "agent": "usb_agent",
            "keywords": [
                "usb", "设备枚举", "device enumeration", "hub", "端口", "port",
                "xhci", "ehci", "ohci", "device descriptor", "endpoint",
            ],
        },
        "bluetooth": {
            "agent": "bluetooth_agent",
            "keywords": [
                "bluetooth", "蓝牙", "bt", "hci", "rfcomm", "l2cap",
                "ble", "a2dp", "gatt", "配对",
            ],
        },
        "network": {
            "agent": "network_agent",
            "keywords": [
                "wifi", "网络", "network", "以太网", "ethernet", "tcp",
                "连接超时", "dhcp", "dns", "wlan", "ipv4", "ipv6",
            ],
        },
        "kernel": {
            "agent": "kernel_agent",
            "keywords": [
                "kernel panic", "内核崩溃", "oops", "segfault", "内存溢出",
                "lockup", "deadlock", "中断", "interrupt",
            ],
        },
    }

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        db: Optional[Session] = None,
        route_strategy: RouteStrategy = RouteStrategy.HYBRID,
        parallel_enabled: bool = True,
    ):
        super().__init__(tool_registry)
        self.db = db
        self.route_strategy = route_strategy
        self.parallel_enabled = parallel_enabled
        self.specialized_agents: Dict[str, BaseAgent] = {}
        self._init_specialized_agents()

    def _init_specialized_agents(self):
        """初始化所有专业 Agent 实例。"""
        self.specialized_agents = {
            "usb_agent": USBAgent(self.tools),
            "bluetooth_agent": BluetoothAgent(self.tools),
            "network_agent": NetworkAgent(self.tools),
            "kernel_agent": KernelAgent(self.tools),
            "general_diagnostic_agent": GeneralDiagnosticAgent(self.tools),
            "report_generator": ReportGenerator(self.tools),
        }
        logger.info(
            "[SupervisorAgent] Initialized %d specialized agents: %s",
            len(self.specialized_agents),
            list(self.specialized_agents.keys()),
        )

    # ==================================================================
    # Public API — Route & Plan
    # ==================================================================

    def plan(self, **context: Any) -> List[str]:
        """分析问题并决定调用哪些 Agent。

        路由策略：
        - HYBRID（默认）: LLM 分析优先，失败回退到关键字匹配
        - LLM: 仅使用 LLM 分析
        - KEYWORD: 仅使用关键字匹配
        """
        user_query = context.get("user_query", "")
        log_content = context.get("log_content", "")

        if self.route_strategy == RouteStrategy.KEYWORD:
            return self._route_by_keyword(user_query, log_content)

        if self.route_strategy == RouteStrategy.LLM:
            return self._route_by_llm(user_query, log_content)

        # HYBRID: LLM 优先，失败回退到关键字
        try:
            plan = self._route_by_llm(user_query, log_content)
            if plan:
                return plan
        except Exception as exc:
            logger.warning("[SupervisorAgent] LLM routing failed, fallback to keyword: %s", exc)

        return self._route_by_keyword(user_query, log_content)

    def route_and_plan(self, **context: Any) -> Tuple[List[str], str]:
        """路由并返回计划 + 使用的策略。

        Returns:
            (agent_names, strategy_used)
        """
        user_query = context.get("user_query", "")
        log_content = context.get("log_content", "")

        if self.route_strategy in (RouteStrategy.LLM, RouteStrategy.HYBRID):
            try:
                plan = self._route_by_llm(user_query, log_content)
                if plan:
                    return plan, "llm"
            except Exception:
                pass

        plan = self._route_by_keyword(user_query, log_content)
        return plan, "keyword"

    # ==================================================================
    # Route Strategy: LLM
    # ==================================================================

    def _route_by_llm(self, query: str, log_content: str) -> List[str]:
        """使用 LLM 分析问题语义，智能路由到专业 Agent。

        如果 LLM 不可用（provider 未配置等），抛出异常由调用方回退。
        """
        if not query.strip() and not log_content.strip():
            return []

        try:
            from app.services.knowledge.provider_registry import ProviderRegistry

            provider = ProviderRegistry().get_provider("deepseek")
            prompt = self._build_routing_prompt(query, log_content)
            response = provider.chat([{"role": "user", "content": prompt}])

            return self._parse_llm_routing_response(response)

        except Exception as exc:
            logger.error("[SupervisorAgent] LLM routing error: %s", exc)
            raise

    def _build_routing_prompt(self, query: str, log_content: str) -> str:
        """构建 LLM 路由分析 prompt。"""
        return f"""你是一个诊断问题分类专家。请分析以下用户问题和日志内容，判断需要哪些专业诊断 Agent 参与分析。

可用的 Agent:
- usb_agent: USB 子系统（枚举、超时、断连、PHY）
- bluetooth_agent: 蓝牙子系统（配对、HCI、RFCOMM、固件）
- network_agent: 网络子系统（WiFi、TCP/IP、DHCP、DNS）
- kernel_agent: 内核级别（Panic、Oops、内存、驱动）
- general_diagnostic_agent: 通用兜底（无明确子系统）

分类规则:
1. 分析用户问题描述和日志中的关键词
2. 选择最相关的 Agent（可以多个）
3. 如果无法确定，使用 general_diagnostic_agent

请只输出 JSON 数组格式的 Agent 名称，不要有其他内容：
例如: ["usb_agent", "kernel_agent"]
如果无法确定: ["general_diagnostic_agent"]

用户问题: {query if query else "（无）"}

日志片段（前 2000 字符）:
{log_content[:2000] if log_content else "（无日志）"}"""

    @staticmethod
    def _parse_llm_routing_response(response: str) -> List[str]:
        """解析 LLM 路由响应，提取 Agent 名称列表。"""
        import json

        # 尝试提取 JSON 数组
        response = response.strip()

        # 移除可能的 markdown 包裹
        response = re.sub(r"^```(?:json)?\s*", "", response)
        response = re.sub(r"\s*```$", "", response)

        try:
            parsed = json.loads(response)
            if isinstance(parsed, list):
                return [a for a in parsed if isinstance(a, str)]
        except json.JSONDecodeError:
            pass

        # 回退：正则匹配已知 agent 名称
        known_agents = [
            "usb_agent", "bluetooth_agent", "network_agent",
            "kernel_agent", "general_diagnostic_agent",
        ]
        found = [a for a in known_agents if a in response.lower()]
        return found if found else ["general_diagnostic_agent"]

    # ==================================================================
    # Route Strategy: Keyword (Fallback)
    # ==================================================================

    def _route_by_keyword(self, query: str, log_content: str) -> List[str]:
        """关键字匹配路由 — 当 LLM 不可用时的回退方案。"""
        combined = (query + " " + log_content[:1000]).lower()
        agent_plan = []

        for _, config in self.KEYWORD_ROUTE_MAP.items():
            agent_name = config["agent"]
            if any(kw in combined for kw in config["keywords"]):
                agent_plan.append(agent_name)

        if not agent_plan:
            agent_plan.append("general_diagnostic_agent")

        logger.info(
            "[SupervisorAgent] Keyword routing: %s (query: %s...)",
            agent_plan, query[:80],
        )
        return agent_plan

    # ==================================================================
    # Public API — Run
    # ==================================================================

    def run(self, **context: Any) -> AgentResult:
        """执行 Supervisor 工作流。

        流程:
        1. PLAN: 路由 → 选择 Agent
        2. EXECUTE: 并行/串行执行 Agent
        3. AGGREGATE: 汇总结果
        4. REPORT: 生成综合报告
        """
        exec_ctx = AgentExecutionContext(context)

        try:
            # Phase 1: 路由规划
            self.state_machine.transition_to(AgentState.PLANNING)

            route_plan, strategy_used = self.route_and_plan(
                user_query=context.get("user_query", ""),
                log_content=context.get("log_content", ""),
            )
            logger.info("[SupervisorAgent] Route plan (%s): %s", strategy_used, route_plan)

            self.state_machine.transition_to(AgentState.PLAN_READY)

            # Phase 2: 执行 Agent（并行或串行）
            self.state_machine.transition_to(AgentState.EXECUTING)

            # 分离普通 Agent 和 report_generator
            work_agents = [a for a in route_plan if a != "report_generator"]

            if self.parallel_enabled and len(work_agents) > 1:
                agent_results = self._execute_agents_parallel(work_agents, exec_ctx)
            else:
                agent_results = self._execute_agents_sequential(work_agents, exec_ctx)

            # Phase 3: 汇总 + 报告
            self.state_machine.transition_to(AgentState.REASONING)

            report = self._generate_report(agent_results, exec_ctx, strategy_used)

            self.state_machine.transition_to(AgentState.VALIDATING)
            self.state_machine.transition_to(AgentState.COMPLETED)

            return AgentResult(
                state=self.state_machine.state,
                summary=report,
                steps=agent_results,
                metadata={
                    "agent_count": len(route_plan),
                    "route_strategy": strategy_used,
                    "success_count": len(exec_ctx.completed_agents),
                    "fail_count": len(exec_ctx.failed_agents),
                    "parallel_mode": self.parallel_enabled and len(work_agents) > 1,
                },
            )

        except Exception as exc:
            self.state_machine.transition_to(AgentState.FAILED)
            logger.error("[SupervisorAgent] Execution failed: %s", exc)
            return AgentResult(state=AgentState.FAILED, error=str(exc))

    # ==================================================================
    # Agent Execution — Sequential
    # ==================================================================

    def _execute_agents_sequential(
        self,
        agent_names: List[str],
        exec_ctx: AgentExecutionContext,
    ) -> List[Dict[str, Any]]:
        """串行执行 Agent — 按顺序逐个运行。"""
        results = []

        for agent_name in agent_names:
            results.append(
                self._execute_single_agent(agent_name, exec_ctx)
            )

        return results

    def _execute_single_agent(
        self,
        agent_name: str,
        exec_ctx: AgentExecutionContext,
    ) -> Dict[str, Any]:
        """执行单个 Agent 并记录状态。"""
        exec_ctx.record_agent_start(agent_name)
        logger.info("[SupervisorAgent] Executing: %s", agent_name)

        if agent_name in self.specialized_agents:
            agent = self.specialized_agents[agent_name]
            try:
                result = agent.run(
                    user_query=exec_ctx.get("user_query", ""),
                    log_content=exec_ctx.get("log_content", ""),
                    events=exec_ctx.get("events", []),
                )
                exec_ctx.record_agent_done(agent_name, result)

                return {
                    "agent": agent_name,
                    "status": "completed" if result.success else "failed",
                    "summary": result.summary,
                    "error": result.error,
                    "metadata": result.metadata,
                }
            except Exception as exc:
                exec_ctx.record_agent_done(
                    agent_name,
                    AgentResult(state=AgentState.FAILED, error=str(exc)),
                )
                return {
                    "agent": agent_name,
                    "status": "failed",
                    "error": str(exc),
                }
        else:
            # Agent 未注册或未知
            exec_ctx.record_agent_done(
                agent_name,
                AgentResult(state=AgentState.FAILED, error=f"Agent not found: {agent_name}"),
            )
            return {
                "agent": agent_name,
                "status": "not_implemented",
                "summary": f"{agent_name} is not yet implemented.",
            }

    # ==================================================================
    # Agent Execution — Parallel
    # ==================================================================

    def _execute_agents_parallel(
        self,
        agent_names: List[str],
        exec_ctx: AgentExecutionContext,
    ) -> List[Dict[str, Any]]:
        """并行执行 Agent — 使用 ThreadPoolExecutor。

        注意：
        - 仅并行化独立的 Agent（无相互依赖）
        - 如果 Agent 之间有依赖，应使用串行执行
        """
        results: List[Dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=min(len(agent_names), 4)) as executor:
            future_map = {
                executor.submit(self._execute_single_agent, name, exec_ctx): name
                for name in agent_names
            }

            for future in as_completed(future_map):
                agent_name = future_map[future]
                try:
                    result = future.result(timeout=120)  # 单个 Agent 最多 2 分钟
                    results.append(result)
                except Exception as exc:
                    logger.error("[SupervisorAgent] Agent %s timeout/exception: %s", agent_name, exc)
                    exec_ctx.record_agent_done(
                        agent_name,
                        AgentResult(state=AgentState.FAILED, error=str(exc)),
                    )
                    results.append({
                        "agent": agent_name,
                        "status": "failed",
                        "error": str(exc),
                    })

        # 保持原始顺序
        order_map = {name: i for i, name in enumerate(agent_names)}
        results.sort(key=lambda r: order_map.get(r["agent"], 999))

        return results

    # ==================================================================
    # Report Generation
    # ==================================================================

    def _generate_report(
        self,
        agent_results: List[Dict[str, Any]],
        exec_ctx: AgentExecutionContext,
        route_strategy: str,
    ) -> str:
        """生成综合诊断报告。"""
        # 使用 ReportGenerator 生成结构化报告
        report_agent = self.specialized_agents.get("report_generator")
        if report_agent:
            try:
                report_result = report_agent.run(
                    agent_results=agent_results,
                    user_query=exec_ctx.get("user_query", ""),
                    route_strategy=route_strategy,
                )
                if report_result.success:
                    return report_result.summary
            except Exception as exc:
                logger.warning("[SupervisorAgent] Report generation failed: %s", exc)

        # 回退：简单汇总
        return self._simple_aggregate(agent_results, route_strategy)

    def _simple_aggregate(
        self,
        results: List[Dict[str, Any]],
        route_strategy: str,
    ) -> str:
        """简单汇总（当 ReportGenerator 不可用时）。"""
        completed = [r for r in results if r["status"] == "completed"]
        failed = [r for r in results if r["status"] == "failed"]

        lines = [
            "# 综合诊断报告",
            "",
            f"**路由策略**: {route_strategy}",
            f"**执行的 Agent**: {len(results)} (成功: {len(completed)}, 失败: {len(failed)})",
            "",
        ]

        if completed:
            lines.append("## 诊断详情")
            for r in completed:
                lines.append(f"### {r['agent']}")
                lines.append(r.get("summary", "无详情"))
                lines.append("")

        if failed:
            lines.append("## 失败的诊断")
            for r in failed:
                lines.append(f"- **{r['agent']}**: {r.get('error', '未知错误')}")

        return "\n".join(lines)

    # ==================================================================
    # Health Check
    # ==================================================================

    def health_check(self) -> Dict[str, Any]:
        """健康检查 — 验证所有注册的 Agent 可用。"""
        status = {"supervisor": "healthy", "agents": {}}

        for name, agent in self.specialized_agents.items():
            try:
                plan = agent.plan()
                status["agents"][name] = "healthy" if plan else "degraded"
            except Exception as exc:
                status["agents"][name] = f"unhealthy: {exc}"

        status["total"] = len(self.specialized_agents)
        status["healthy_count"] = sum(
            1 for v in status["agents"].values() if v == "healthy"
        )
        return status
