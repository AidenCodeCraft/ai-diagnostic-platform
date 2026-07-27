"""诊断报告生成 Agent — 汇总各专业 Agent 结果并生成综合报告。

职责：
- 接收 supervisor 聚合的各 Agent 诊断结果
- 综合交叉分析
- 生成结构化诊断报告
- 提供修复优先级排序
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agents.core.agent import BaseAgent, AgentResult
from app.agents.core.state import AgentState
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class ReportGenerator(BaseAgent):
    """诊断报告生成 Agent。

    功能：
    - 汇总多 Agent 诊断结果
    - 交叉验证（不同 Agent 的诊断是否有冲突）
    - 生成优先级排序的修复建议
    - 输出 Markdown 格式的综合报告
    """

    name = "report_generator"
    description = "Aggregates results from multiple specialized agents and generates a comprehensive diagnostic report with prioritized recommendations."

    def plan(self, **context: Any) -> List[str]:
        return [
            "collect_agent_results",
            "cross_validate",
            "priority_sort",
            "format_report",
        ]

    def run(self, **context: Any) -> AgentResult:
        try:
            self.state_machine.transition_to(AgentState.PLANNING)

            agent_results = context.get("agent_results", [])
            user_query = context.get("user_query", "")

            self.state_machine.transition_to(AgentState.PLAN_READY)
            self.state_machine.transition_to(AgentState.EXECUTING)

            # 收集所有 Agent 的诊断结果
            findings = self._collect_findings(agent_results)

            self.state_machine.transition_to(AgentState.REASONING)

            # 交叉验证
            cross_validation = self._cross_validate(findings)

            # 优先级排序
            prioritized = self._prioritize(findings)

            self.state_machine.transition_to(AgentState.VALIDATING)
            self.state_machine.transition_to(AgentState.COMPLETED)

            report = self._format_report(
                user_query,
                agent_results,
                findings,
                cross_validation,
                prioritized,
            )

            return AgentResult(
                state=self.state_machine.state,
                summary=report,
                steps=[{
                    "agent": self.name,
                    "agent_count": len(agent_results),
                    "total_findings": len(findings),
                    "cross_validated": len(cross_validation.get("conflicts", [])),
                    "prioritized_suggestions": len(prioritized),
                }],
                metadata={
                    "agent_type": "report_generator",
                    "agents_contributed": len(agent_results),
                    "total_findings": len(findings),
                },
            )

        except Exception as exc:
            self.state_machine.transition_to(AgentState.FAILED)
            logger.error(f"[ReportGenerator] Failed: {exc}")
            return AgentResult(state=AgentState.FAILED, error=str(exc))

    def _collect_findings(self, agent_results: list) -> list:
        """从各 Agent 结果中收集诊断发现。"""
        findings = []
        for result in agent_results:
            if isinstance(result, dict):
                agent_name = result.get("agent", "unknown")
                status = result.get("status", "")

                if status == "completed":
                    # 从 summary 中解析关键发现
                    summary = result.get("summary", "")
                    findings.append({
                        "agent": agent_name,
                        "status": "completed",
                        "summary": summary,
                        "metadata": result.get("metadata", {}),
                    })
                elif status == "failed":
                    findings.append({
                        "agent": agent_name,
                        "status": "failed",
                        "error": result.get("error", "Unknown error"),
                    })
                else:
                    findings.append({
                        "agent": agent_name,
                        "status": status,
                        "summary": result.get("summary", ""),
                    })
        return findings

    def _cross_validate(self, findings: list) -> Dict[str, Any]:
        """交叉验证各 Agent 的诊断结果。

        检测：
        - 不同 Agent 是否对同一问题得出一致结论
        - 是否有矛盾的诊断
        """
        conflicts = []
        consistent = []

        # 简化实现：比较各 Agent 的严重度判断
        completed_findings = [f for f in findings if f.get("status") == "completed"]

        if len(completed_findings) > 1:
            # 提取各 Agent 的置信度
            confidences = {}
            for f in completed_findings:
                metadata = f.get("metadata", {})
                issues_found = metadata.get("issues_found", 0)
                agent_name = f.get("agent", "unknown")
                confidences[agent_name] = issues_found

            # 如果有多个 Agent 发现高置信度问题，标记为一致
            high_confidence = {
                name: count for name, count in confidences.items()
                if count > 0
            }
            if len(high_confidence) > 1:
                consistent.append({
                    "type": "multi_agent_agreement",
                    "agents": list(high_confidence.keys()),
                    "message": "多个专业 Agent 在各自的领域内均发现问题，建议进行综合排查",
                })

        return {
            "conflicts": conflicts,
            "consistent": consistent,
            "all_agents_agree": len(conflicts) == 0,
        }

    def _prioritize(self, findings: list) -> list:
        """基于严重度和影响范围对诊断发现进行优先级排序。"""
        priority_map = {
            "kernel_agent": 10,  # 内核问题最严重
            "usb_agent": 5,
            "bluetooth_agent": 4,
            "network_agent": 6,
            "general_diagnostic_agent": 2,
        }

        scored = []
        for f in findings:
            if f.get("status") != "completed":
                continue

            agent = f.get("agent", "")
            metadata = f.get("metadata", {})

            base_priority = priority_map.get(agent, 3)
            issues_found = metadata.get("issues_found", 0)

            score = base_priority + issues_found * 2

            scored.append({
                "agent": agent,
                "priority_score": score,
                "summary": (f.get("summary", "") or "")[:200],
                "issues_found": issues_found,
            })

        return sorted(scored, key=lambda x: x["priority_score"], reverse=True)

    def _format_report(
        self,
        user_query: str,
        agent_results: list,
        findings: list,
        cross_validation: dict,
        prioritized: list,
    ) -> str:
        """格式化综合诊断报告。"""
        total = len(agent_results)
        completed = len([f for f in findings if f.get("status") == "completed"])
        failed = len([f for f in findings if f.get("status") == "failed"])

        lines = [
            "# 综合诊断报告",
            "",
        ]

        if user_query:
            lines.append(f"> **用户问题**: {user_query}")
            lines.append("")

        # 执行摘要
        lines.append("## 执行摘要")
        lines.append("")
        lines.append(f"- 参与诊断的专业 Agent: {total}")
        lines.append(f"- 成功完成诊断: {completed}")
        lines.append(f"- 诊断失败: {failed}")
        lines.append("")

        # 各 Agent 诊断结果
        if completed > 0:
            lines.append("## 各子系统诊断详情")
            lines.append("")
            for f in findings:
                if f.get("status") == "completed":
                    agent_name = f.get("agent", "unknown")
                    lines.append(f"### {agent_name}")
                    summary = f.get("summary", "")
                    if summary:
                        lines.append(summary)
                        lines.append("")

        # 失败 Agent
        if failed > 0:
            lines.append("## 未完成的诊断")
            lines.append("")
            for f in findings:
                if f.get("status") == "failed":
                    lines.append(f"- **{f.get('agent', 'unknown')}**: {f.get('error', '未知错误')}")
            lines.append("")

        # 交叉验证
        if cross_validation.get("consistent"):
            lines.append("## 交叉验证")
            lines.append("")
            for item in cross_validation["consistent"]:
                lines.append(f"- ✅ {item['message']}")
            for item in cross_validation.get("conflicts", []):
                lines.append(f"- ⚠️ {item.get('message', '')}")

        # 优先级修建议
        if prioritized:
            lines.append("## 修复优先级建议")
            lines.append("")
            lines.append("| 优先级 | Agent | 问题数 | 建议 |")
            lines.append("|--------|-------|--------|------|")
            for i, p in enumerate(prioritized[:5], 1):
                lines.append(
                    f"| {i} | {p['agent']} | {p['issues_found']} | "
                    f"{p['summary'][:80]}... |"
                )
            lines.append("")

        # 总体建议
        lines.append("## 总体建议")
        lines.append("")
        if completed > 0:
            lines.append("1. 优先处理内核级别和严重度最高的诊断发现")
            lines.append("2. 交叉验证各 Agent 的诊断结果，避免单一诊断误判")
            lines.append("3. 建议在实际设备上复现问题并收集更多日志")
        else:
            lines.append("当前无 Agent 完成诊断，建议检查系统状态或提供更多诊断数据。")

        return "\n".join(lines)

    def validate(self, result: Dict[str, Any]) -> bool:
        return True
