"""通用诊断 Agent — 处理未分类到特定子系统的问题。

职责：
- 作为 fallback Agent，处理 supervisor 无法明确分类的问题
- 执行通用日志分析和问题归纳
- 提供基础诊断建议
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.agents.core.agent import BaseAgent, AgentResult
from app.agents.core.state import AgentState
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class GeneralDiagnosticAgent(BaseAgent):
    """通用诊断 Agent — 处理未分类问题的兜底方案。

    能力：
    - 通用日志事件统计
    - 错误级别分析
    - 基础诊断建议生成
    """

    name = "general_diagnostic_agent"
    description = "Fallback agent for general diagnostic analysis when no specialized agent is applicable."

    def plan(self, **context: Any) -> List[str]:
        return [
            "collect_events",
            "error_statistics",
            "basic_analysis",
        ]

    def run(self, **context: Any) -> AgentResult:
        try:
            self.state_machine.transition_to(AgentState.PLANNING)

            events = context.get("events", [])
            user_query = context.get("user_query", "")
            log_content = context.get("log_content", "")

            self.state_machine.transition_to(AgentState.PLAN_READY)
            self.state_machine.transition_to(AgentState.EXECUTING)

            # 基础事件统计
            total_events = len(events)
            error_events = [e for e in events if e.get("is_error")]
            warn_events = [e for e in events if e.get("level") == "WARNING"]

            # 按模块分组
            modules = self._group_by_module(events)

            # 提取高频错误
            top_errors = self._extract_top_errors(error_events)

            self.state_machine.transition_to(AgentState.REASONING)

            # 生成建议
            suggestions = self._generate_suggestions(
                total_events, len(error_events), len(warn_events), top_errors,
            )

            self.state_machine.transition_to(AgentState.VALIDATING)
            self.state_machine.transition_to(AgentState.COMPLETED)

            summary = self._build_summary(
                total_events, error_events, warn_events, modules, top_errors, suggestions,
            )

            return AgentResult(
                state=self.state_machine.state,
                summary=summary,
                steps=[{
                    "agent": self.name,
                    "total_events": total_events,
                    "error_count": len(error_events),
                    "warn_count": len(warn_events),
                    "module_count": len(modules),
                    "top_errors": top_errors,
                    "suggestions": suggestions,
                }],
                metadata={
                    "agent_type": "general",
                    "total_events": total_events,
                    "error_count": len(error_events),
                },
            )

        except Exception as exc:
            self.state_machine.transition_to(AgentState.FAILED)
            logger.error(f"[GeneralDiagnosticAgent] Failed: {exc}")
            return AgentResult(state=AgentState.FAILED, error=str(exc))

    @staticmethod
    def _group_by_module(events: list) -> Dict[str, int]:
        """按模块分组统计事件数。"""
        modules: Dict[str, int] = {}
        for e in events:
            module = e.get("module", "unknown") or "unknown"
            modules[module] = modules.get(module, 0) + 1
        return dict(sorted(modules.items(), key=lambda x: x[1], reverse=True)[:10])

    @staticmethod
    def _extract_top_errors(error_events: list, top_n: int = 5) -> list:
        """提取最高频的错误消息。"""
        error_messages: Dict[str, int] = {}
        for e in error_events:
            msg = str(e.get("message", ""))[:100]
            error_messages[msg] = error_messages.get(msg, 0) + 1
        return sorted(error_messages.items(), key=lambda x: x[1], reverse=True)[:top_n]

    @staticmethod
    def _generate_suggestions(
        total: int, error_count: int, warn_count: int, top_errors: list,
    ) -> list:
        """生成通用诊断建议。"""
        suggestions = []

        error_ratio = error_count / max(1, total)
        if error_ratio > 0.5:
            suggestions.append("日志中错误比例过高 (>50%)，建议优先解决最高频的错误类型")
        elif error_ratio > 0.2:
            suggestions.append("日志中存在一定比例的错误，建议持续监控并排查根因")

        if warn_count > error_count * 3:
            suggestions.append("警告事件数量显著多于错误事件，可能存在逐步恶化的问题")

        if top_errors:
            top_msg, top_count = top_errors[0]
            if top_count > 5:
                suggestions.append(f"高频错误：'{top_msg[:60]}...' 出现 {top_count} 次，建议优先排查")

        if not suggestions:
            suggestions.append("建议上传更完整的日志或提供具体的故障现象描述")

        return suggestions

    def _build_summary(
        self, total: int, error_events: list, warn_events: list,
        modules: dict, top_errors: list, suggestions: list,
    ) -> str:
        error_count = len(error_events)
        warn_count = len(warn_events)

        lines = [
            "## 通用诊断分析",
            "",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 总事件数 | {total} |",
            f"| 错误事件 | {error_count} |",
            f"| 警告事件 | {warn_count} |",
            f"| 错误率 | {error_count / max(1, total):.1%} |",
            "",
        ]

        if modules:
            lines.append("### 模块分布（Top 5）")
            for module, count in list(modules.items())[:5]:
                lines.append(f"- {module}: {count} 个事件")

        if top_errors:
            lines.append("")
            lines.append("### 高频错误")
            for msg, count in top_errors[:3]:
                lines.append(f"- [{count}次] {msg[:80]}")

        if suggestions:
            lines.append("")
            lines.append("### 诊断建议")
            for s in suggestions:
                lines.append(f"- {s}")

        return "\n".join(lines)

    def validate(self, result: Dict[str, Any]) -> bool:
        return True
