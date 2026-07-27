"""Kernel 专业诊断 Agent — 专注于内核级问题诊断。

能力：
- Kernel Panic/Oops 分析
- 内存异常检测
- 驱动崩溃诊断
- 中断异常分析
- 调度延迟检测
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agents.core.agent import BaseAgent, AgentResult
from app.agents.core.state import AgentState
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class KernelAgent(BaseAgent):
    """内核专业诊断 Agent。

    专注于诊断：
    - Kernel Panic / Oops
    - 内存越界 / 泄漏
    - 驱动加载失败
    - 中断风暴
    - 死锁 / 自旋锁超时
    """

    name = "kernel_agent"
    description = "Specialized agent for diagnosing kernel-level issues including panics, Oops, memory corruption, and driver crashes."

    KERNEL_KNOWLEDGE = {
        "kernel_panic": {
            "patterns": [
                "kernel panic", "end kernel panic", "not syncing",
                "oops", "bug: unable to handle", "kernel bug",
                "内核崩溃", "内核异常",
            ],
            "common_causes": [
                "内核模块加载错误",
                "硬件故障（内存/CPU）",
                "内核版本与驱动不兼容",
                "内核栈溢出",
                "中断上下文错误",
            ],
            "suggestions": [
                "查看 panic 调用栈确定触发点",
                "检查是否最近更新了内核或驱动",
                "运行内存测试工具",
                "尝试使用之前正常的内核版本",
            ],
        },
        "memory_error": {
            "patterns": [
                "out of memory", "oom", "memory leak",
                "vmalloc", "kmalloc", "alloc fail",
                "page fault", "segfault", "memory corruption",
                "内存不足", "内存溢出", "内存泄漏",
            ],
            "common_causes": [
                "内存物理损坏",
                "内存泄漏（kmalloc 无 kfree）",
                "虚拟内存耗尽",
                "DMA 缓冲区越界",
            ],
            "suggestions": [
                "使用 memtest 检测硬件内存",
                "检查 kmemleak 报告",
                "分析 /proc/meminfo 和 slabinfo",
            ],
        },
        "driver_error": {
            "patterns": [
                "driver", "module", "probe failed",
                "initcall", "modprobe", "insmod",
                "驱动加载", "驱动崩溃",
            ],
            "common_causes": [
                "驱动与内核版本不匹配",
                "缺少固件文件",
                "硬件设备不存在",
                "驱动依赖关系错误",
            ],
            "suggestions": [
                "检查驱动与内核版本兼容性",
                "验证固件文件路径和完整性",
                "查看 dmesg 中的驱动加载错误详情",
            ],
        },
        "interrupt_error": {
            "patterns": [
                "irq", "interrupt", "nobody cared",
                "中断风暴", "irq storm",
                "hrtimer", "soft lockup", "hard lockup",
            ],
            "common_causes": [
                "中断处理函数执行时间过长",
                "中断未正确清除",
                "共享中断冲突",
                "高精度定时器异常",
            ],
            "suggestions": [
                "检查 /proc/interrupts 中断计数",
                "优化中断处理程序（缩短 top-half）",
                "检查共享中断线上的设备",
            ],
        },
    }

    def plan(self, **context: Any) -> List[str]:
        return [
            "parse_kernel_events",
            "classify_kernel_issue",
            "rule_check_kernel",
            "kernel_root_cause_analysis",
        ]

    def run(self, **context: Any) -> AgentResult:
        try:
            self.state_machine.transition_to(AgentState.PLANNING)

            events = context.get("events", [])
            user_query = context.get("user_query", "")
            log_content = context.get("log_content", "")

            kernel_events = self._filter_kernel_events(log_content, events)
            self.state_machine.transition_to(AgentState.PLAN_READY)

            self.state_machine.transition_to(AgentState.EXECUTING)
            classifications = self._classify_kernel_problems(kernel_events, user_query)

            self.state_machine.transition_to(AgentState.REASONING)
            diagnosis = self._reason_kernel_diagnosis(classifications, kernel_events)

            self.state_machine.transition_to(AgentState.VALIDATING)
            self.state_machine.transition_to(
                AgentState.COMPLETED if self.validate(diagnosis) else AgentState.FAILED
            )

            if self.state_machine.state != AgentState.COMPLETED:
                return AgentResult(state=AgentState.FAILED, error="Kernel diagnosis validation failed")

            summary = self._build_kernel_summary(diagnosis, classifications)
            return AgentResult(
                state=self.state_machine.state,
                summary=summary,
                steps=[{
                    "agent": self.name,
                    "kernel_events_count": len(kernel_events),
                    "classifications": classifications,
                    "diagnosis": diagnosis,
                }],
                metadata={
                    "agent_type": "kernel_specialist",
                    "issues_found": len(classifications),
                },
            )

        except Exception as exc:
            self.state_machine.transition_to(AgentState.FAILED)
            logger.error(f"[KernelAgent] Failed: {exc}")
            return AgentResult(state=AgentState.FAILED, error=str(exc))

    def _filter_kernel_events(self, log_content: str, events: list) -> list:
        kernel_keywords = [
            "kernel", "panic", "oops", "bug:", "segfault",
            "mm", "vfs", "syscall", "oops:", "warn_on",
            "lockdep", "rcu", "sched", "oom", "killed",
            "interrupt", "irq", "timer", "softlockup",
        ]
        return [
            e for e in events
            if any(kw in str(e.get("message", "")).lower() for kw in kernel_keywords)
        ]

    def _classify_kernel_problems(
        self, kernel_events: list, user_query: str,
    ) -> List[Dict[str, Any]]:
        combined = " ".join(
            str(e.get("message", "")) for e in kernel_events
        ).lower()

        classifications = []
        for issue_type, config in self.KERNEL_KNOWLEDGE.items():
            matched = [p for p in config["patterns"] if p.lower() in combined]
            if matched:
                severity = {
                    "kernel_panic": 5,
                    "memory_error": 4,
                    "driver_error": 3,
                    "interrupt_error": 4,
                }.get(issue_type, 2)

                classifications.append({
                    "type": issue_type,
                    "matched_patterns": matched,
                    "common_causes": config["common_causes"],
                    "suggestions": config["suggestions"],
                    "severity": severity,
                    "confidence": min(0.95, 0.5 + len(matched) * 0.15),
                })

        return sorted(classifications, key=lambda c: c["severity"], reverse=True)

    def _reason_kernel_diagnosis(
        self, classifications: list, kernel_events: list,
    ) -> Dict[str, Any]:
        if not classifications:
            if kernel_events:
                return {
                    "root_cause": "检测到内核事件但需要更深入的人工分析",
                    "confidence": 0.3,
                }
            return {
                "root_cause": "未检测到内核异常事件",
                "confidence": 0.9,
            }

        primary = classifications[0]

        # 如果检测到 kernel panic，提升严重度
        matched_patterns = primary.get("matched_patterns", [])
        is_panic = any("panic" in p.lower() or "oops" in p.lower() for p in matched_patterns)

        return {
            "primary_issue": primary["type"],
            "root_cause": ", ".join(primary["common_causes"][:2]),
            "confidence": min(0.98, primary["confidence"] + (0.1 if is_panic else 0)),
            "suggestions": primary["suggestions"][:3],
            "all_issues": [
                {"type": c["type"], "severity": c["severity"] if not is_panic else 5,
                 "confidence": c["confidence"]}
                for c in classifications
            ],
        }

    def _build_kernel_summary(
        self, diagnosis: Dict[str, Any], classifications: list,
    ) -> str:
        if not classifications:
            return "## 内核诊断结果\n\n未检测到内核级别异常。\n"

        lines = [
            "## 内核诊断",
            "",
            f"**检测到 {len(classifications)} 个内核问题**",
            "",
        ]
        for i, cls in enumerate(classifications, 1):
            icon = "🔴" if cls["severity"] >= 4 else "🟡"
            lines.append(f"{icon} **问题 {i}: {cls['type']}** (置信度: {cls['confidence']:.0%})")
            lines.append(f"  - 可能原因: {cls['common_causes'][0]}")
            lines.append(f"  - 建议: {cls['suggestions'][0]}")
            lines.append("")

        if diagnosis.get("root_cause"):
            lines.append(f"**综合分析**: {diagnosis['root_cause']}")

        return "\n".join(lines)

    def validate(self, result: Dict[str, Any]) -> bool:
        return result.get("confidence", 0) >= 0
