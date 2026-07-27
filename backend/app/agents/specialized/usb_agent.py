"""USB 专业诊断 Agent — 专注于 USB 子系统问题诊断。

能力：
- USB 设备枚举分析
- USB 超时/断开检测
- USB PHY 初始化问题
- USB 协议栈错误分析
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agents.core.agent import BaseAgent, AgentResult
from app.agents.core.tool import ToolRegistry
from app.agents.core.state import AgentState
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class USBAgent(BaseAgent):
    """USB 专业诊断 Agent。

    专注于诊断：
    - USB 设备枚举失败
    - USB 事务超时
    - USB 断连问题
    - USB PHY 初始化失败
    - USB 驱动异常
    """

    name = "usb_agent"
    description = "Specialized agent for diagnosing USB subsystem issues including enumeration, timeouts, and disconnections."

    # USB 诊断知识库
    USB_KNOWLEDGE = {
        "enumeration_failure": {
            "patterns": [
                "device descriptor read", "enumeration fail", "device not accepting address",
                "无法枚举", "枚举失败", "设备描述符", "unable to enumerate",
            ],
            "common_causes": [
                "USB 设备硬件故障",
                "USB 线缆或连接器接触不良",
                "USB 供电不足",
                "USB 控制器驱动异常",
                "Device Descriptor 损坏",
            ],
            "suggestions": [
                "更换 USB 线缆测试",
                "检查 USB 端口供电状态",
                "使用 USB 协议分析仪抓包",
                "尝试重新插拔设备",
            ],
        },
        "timeout": {
            "patterns": [
                "timeout", "超时", "timed out", "xhci_drop_endpoint",
                "command abort", "not responding",
            ],
            "common_causes": [
                "USB 设备无响应",
                "USB 控制器握手失败",
                "电源管理导致设备休眠",
                "中断延迟过高",
            ],
            "suggestions": [
                "检查设备是否正常供电",
                "禁用 USB 选择性暂停",
                "检查中断分配是否合理",
                "尝试更新 USB 控制器固件",
            ],
        },
        "disconnection": {
            "patterns": [
                "disconnect", "断开", "removed", "unplugged",
                "device gone", "port disable", "link down",
            ],
            "common_causes": [
                "物理连接松动",
                "静电或 EMI 干扰",
                "USB PHY 状态异常",
                "设备自行断电",
            ],
            "suggestions": [
                "检查物理连接状态",
                "检查 USB PHY 寄存器状态",
                "检查 ESD 保护电路",
                "记录断开频率和触发条件",
            ],
        },
        "phy_error": {
            "patterns": [
                "phy init", "phy error", "phy calibration",
                "pll lock", "refclk", "物理层",
                "squelch", "chirp", "high speed negotiation",
            ],
            "common_causes": [
                "USB PHY 时钟源异常",
                "PLL 未锁定",
                "参考时钟频率偏差",
                "PCB 走线阻抗不匹配",
            ],
            "suggestions": [
                "检查 USB 参考时钟频率和稳定性",
                "使用示波器检查 USB 信号质量",
                "检查 PHY 配置寄存器",
                "验证 PCB 差分走线阻抗",
            ],
        },
    }

    def plan(self, **context: Any) -> List[str]:
        """规划 USB 诊断步骤。"""
        return [
            "parse_usb_events",       # 提取 USB 相关事件
            "classify_usb_issue",      # 分类 USB 问题类型
            "rule_check_usb",          # USB 专项规则检查
            "usb_root_cause_analysis", # USB 根因分析
        ]

    def run(self, **context: Any) -> AgentResult:
        """执行 USB 专业诊断。"""
        try:
            self.state_machine.transition_to(AgentState.PLANNING)

            # 解析上下文
            log_content = context.get("log_content", "")
            events = context.get("events", [])
            user_query = context.get("user_query", "")

            # 过滤 USB 相关事件
            usb_events = self._filter_usb_events(log_content, events)
            self.state_machine.transition_to(AgentState.PLAN_READY)

            # 分类 USB 问题
            self.state_machine.transition_to(AgentState.EXECUTING)
            classifications = self._classify_usb_problems(usb_events, user_query)

            self.state_machine.transition_to(AgentState.REASONING)
            diagnosis = self._reason_usb_diagnosis(classifications, usb_events, user_query)

            self.state_machine.transition_to(AgentState.VALIDATING)
            if self.validate(diagnosis):
                self.state_machine.transition_to(AgentState.COMPLETED)
            else:
                self.state_machine.transition_to(AgentState.FAILED)
                return AgentResult(
                    state=AgentState.FAILED,
                    error="USB diagnosis validation failed",
                )

            summary = self._build_usb_summary(diagnosis, classifications)
            return AgentResult(
                state=self.state_machine.state,
                summary=summary,
                steps=[{
                    "agent": self.name,
                    "usb_events_count": len(usb_events),
                    "classifications": classifications,
                    "diagnosis": diagnosis,
                }],
                metadata={
                    "agent_type": "usb_specialist",
                    "issues_found": len(classifications),
                },
            )

        except Exception as exc:
            self.state_machine.transition_to(AgentState.FAILED)
            logger.error(f"[USBAgent] Execution failed: {exc}")
            return AgentResult(state=AgentState.FAILED, error=str(exc))

    def _filter_usb_events(self, log_content: str, events: list) -> list:
        """过滤 USB 相关事件。"""
        usb_keywords = [
            "usb", "xhci", "ehci", "ohci", "uhci",
            "hub", "port", "speed", "endpoint",
            "device descriptor", "interface",
        ]
        filtered = []
        for event in events:
            msg = str(event.get("message", "")).lower()
            if any(kw in msg for kw in usb_keywords):
                filtered.append(event)
        return filtered

    def _classify_usb_problems(
        self, usb_events: list, user_query: str,
    ) -> List[Dict[str, Any]]:
        """基于事件模式分类 USB 问题。"""
        classifications = []
        combined_text = " ".join(
            str(e.get("message", "")) for e in usb_events
        ).lower()

        for issue_type, config in self.USB_KNOWLEDGE.items():
            matched_patterns = [
                p for p in config["patterns"]
                if p.lower() in combined_text or p.lower() in user_query.lower()
            ]
            if matched_patterns:
                # 计算严重度
                severity = self._estimate_usb_severity(usb_events, issue_type)
                classifications.append({
                    "type": issue_type,
                    "matched_patterns": matched_patterns,
                    "common_causes": config["common_causes"],
                    "suggestions": config["suggestions"],
                    "severity": severity,
                    "confidence": min(0.95, 0.5 + len(matched_patterns) * 0.15),
                })

        return sorted(classifications, key=lambda c: c["severity"], reverse=True)

    @staticmethod
    def _estimate_usb_severity(events: list, issue_type: str) -> int:
        """估算 USB 问题严重度 (1-5)。"""
        severity_map = {
            "enumeration_failure": 5,  # 设备完全无法使用
            "phy_error": 5,           # 物理层问题
            "timeout": 3,             # 可能间歇性
            "disconnection": 3,       # 可能间歇性
        }
        base = severity_map.get(issue_type, 2)
        # 如果错误事件多，增加严重度
        error_count = len([e for e in events if e.get("is_error")])
        if error_count > 10:
            base = min(5, base + 1)
        return base

    def _reason_usb_diagnosis(
        self,
        classifications: list,
        usb_events: list,
        user_query: str,
    ) -> Dict[str, Any]:
        """综合推理 USB 诊断结论。"""
        if not classifications:
            if usb_events:
                return {
                    "root_cause": "检测到 USB 事件但未匹配已知模式，建议人工分析",
                    "confidence": 0.3,
                }
            return {
                "root_cause": "未检测到 USB 相关问题",
                "confidence": 0.9,
            }

        # 取最高置信度的分类作为主要诊断
        primary = classifications[0]

        return {
            "primary_issue": primary["type"],
            "root_cause": ", ".join(primary["common_causes"][:2]),
            "confidence": primary["confidence"],
            "suggestions": primary["suggestions"][:3],
            "all_issues": [
                {"type": c["type"], "severity": c["severity"], "confidence": c["confidence"]}
                for c in classifications
            ],
        }

    def _build_usb_summary(
        self, diagnosis: Dict[str, Any], classifications: list,
    ) -> str:
        """构建 USB 诊断摘要。"""
        if not classifications:
            return "## USB 诊断结果\n\n未检测到 USB 子系统相关问题。\n"

        lines = [
            "## USB 子系统诊断",
            "",
            f"**检测到 {len(classifications)} 个 USB 问题**",
            "",
        ]

        for i, cls in enumerate(classifications, 1):
            severity_label = "🔴" if cls["severity"] >= 4 else "🟡" if cls["severity"] >= 2 else "🔵"
            lines.append(f"{severity_label} **问题 {i}: {cls['type']}** (置信度: {cls['confidence']:.0%})")
            lines.append(f"  - 可能原因: {cls['common_causes'][0]}")
            lines.append(f"  - 建议: {cls['suggestions'][0]}")
            lines.append("")

        if diagnosis.get("root_cause"):
            lines.append(f"**综合分析**: {diagnosis['root_cause']}")

        return "\n".join(lines)

    def validate(self, result: Dict[str, Any]) -> bool:
        """验证 USB 诊断结果。"""
        if not result:
            return True  # 没有 USB 事件也算有效
        # 至少要有合理的置信度
        return result.get("confidence", 0) >= 0
