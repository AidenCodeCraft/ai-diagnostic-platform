"""Bluetooth 专业诊断 Agent — 专注于蓝牙子系统问题诊断。

能力：
- 蓝牙连接异常分析
- HCI 层错误检测
- RFCOMM/L2CAP 协议分析
- 蓝牙固件崩溃诊断
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agents.core.agent import BaseAgent, AgentResult
from app.agents.core.state import AgentState
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class BluetoothAgent(BaseAgent):
    """蓝牙专业诊断 Agent。

    专注于诊断：
    - 蓝牙扫描/配对失败
    - 蓝牙断连
    - HCI 命令超时
    - 固件崩溃
    - 射频干扰
    """

    name = "bluetooth_agent"
    description = "Specialized agent for diagnosing Bluetooth issues including pairing failures, disconnections, and HCI errors."

    BT_KNOWLEDGE = {
        "pairing_failure": {
            "patterns": [
                "pairing failed", "authentication fail", "pin missing",
                "key missing", "link key", "ssp fail", "配对失败",
                "认证失败", "配对码",
            ],
            "common_causes": [
                "蓝牙配对模式不匹配",
                "设备已绑定但密钥过期",
                "蓝牙版本不兼容",
                "BT MAC 地址冲突",
            ],
            "suggestions": [
                "清除设备绑定列表后重新配对",
                "确认双方蓝牙版本兼容",
                "检查蓝牙 MAC 地址是否唯一",
            ],
        },
        "hci_error": {
            "patterns": [
                "hci", "command disallowed", "hardware failure",
                "controller busy", "hci timeout",
            ],
            "common_causes": [
                "蓝牙控制器固件异常",
                "HCI 传输层错误（UART/USB）",
                "蓝牙控制器过热",
            ],
            "suggestions": [
                "重置蓝牙控制器",
                "检查 HCI 传输接口状态",
                "更新蓝牙固件",
            ],
        },
        "rfcomm_error": {
            "patterns": [
                "rfcomm", "l2cap", "connection refused",
                "psm", "channel", "sdp",
            ],
            "common_causes": [
                "RFCOMM 通道未正确建立",
                "L2CAP 连接参数配置错误",
                "SDP 服务发现失败",
                "MTU 配置不匹配",
            ],
            "suggestions": [
                "检查 SDP 服务注册状态",
                "确认 L2CAP MTU 配置",
                "验证 RFCOMM channel 分配",
            ],
        },
        "firmware_crash": {
            "patterns": [
                "firmware crash", "fw crash", "uploading firmware",
                "btusb", "hci0 command", "firmware loading",
                "固件崩溃",
            ],
            "common_causes": [
                "蓝牙固件版本不兼容",
                "固件文件损坏",
                "蓝牙芯片硬件故障",
            ],
            "suggestions": [
                "重新刷写蓝牙固件",
                "检查固件文件完整性",
                "验证蓝牙芯片型号与固件匹配",
            ],
        },
    }

    def plan(self, **context: Any) -> List[str]:
        return [
            "parse_bt_events",
            "classify_bt_issue",
            "rule_check_bt",
            "bt_root_cause_analysis",
        ]

    def run(self, **context: Any) -> AgentResult:
        try:
            self.state_machine.transition_to(AgentState.PLANNING)

            log_content = context.get("log_content", "")
            events = context.get("events", [])
            user_query = context.get("user_query", "")

            bt_events = self._filter_bt_events(log_content, events)
            self.state_machine.transition_to(AgentState.PLAN_READY)

            self.state_machine.transition_to(AgentState.EXECUTING)
            classifications = self._classify_bt_problems(bt_events, user_query)

            self.state_machine.transition_to(AgentState.REASONING)
            diagnosis = self._reason_bt_diagnosis(classifications, bt_events)

            self.state_machine.transition_to(AgentState.VALIDATING)
            self.state_machine.transition_to(
                AgentState.COMPLETED if self.validate(diagnosis) else AgentState.FAILED
            )

            if not self.state_machine.state == AgentState.COMPLETED:
                return AgentResult(state=AgentState.FAILED, error="BT diagnosis validation failed")

            summary = self._build_bt_summary(diagnosis, classifications)
            return AgentResult(
                state=self.state_machine.state,
                summary=summary,
                steps=[{
                    "agent": self.name,
                    "bt_events_count": len(bt_events),
                    "classifications": classifications,
                    "diagnosis": diagnosis,
                }],
                metadata={
                    "agent_type": "bluetooth_specialist",
                    "issues_found": len(classifications),
                },
            )

        except Exception as exc:
            self.state_machine.transition_to(AgentState.FAILED)
            logger.error(f"[BluetoothAgent] Failed: {exc}")
            return AgentResult(state=AgentState.FAILED, error=str(exc))

    def _filter_bt_events(self, log_content: str, events: list) -> list:
        bt_keywords = [
            "bluetooth", "bt", "hci", "rfcomm", "l2cap",
            "sdp", "rfcomm", "hsp", "hfp", "a2dp", "ble",
            "gap", "gatt", "att", "acl", "sco",
        ]
        return [
            e for e in events
            if any(kw in str(e.get("message", "")).lower() for kw in bt_keywords)
        ]

    def _classify_bt_problems(
        self, bt_events: list, user_query: str,
    ) -> List[Dict[str, Any]]:
        combined = " ".join(
            str(e.get("message", "")) for e in bt_events
        ).lower()

        classifications = []
        for issue_type, config in self.BT_KNOWLEDGE.items():
            matched = [p for p in config["patterns"] if p.lower() in combined]
            if matched:
                severity = {
                    "pairing_failure": 3,
                    "hci_error": 4,
                    "rfcomm_error": 3,
                    "firmware_crash": 5,
                }.get(issue_type, 2)

                classifications.append({
                    "type": issue_type,
                    "matched_patterns": matched,
                    "common_causes": config["common_causes"],
                    "suggestions": config["suggestions"],
                    "severity": severity,
                    "confidence": min(0.9, 0.5 + len(matched) * 0.13),
                })

        return sorted(classifications, key=lambda c: c["severity"], reverse=True)

    def _reason_bt_diagnosis(
        self, classifications: list, bt_events: list,
    ) -> Dict[str, Any]:
        if not classifications:
            return {
                "root_cause": "未检测到蓝牙相关已知问题模式",
                "confidence": 0.5 if bt_events else 0.9,
            }

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

    def _build_bt_summary(
        self, diagnosis: Dict[str, Any], classifications: list,
    ) -> str:
        if not classifications:
            return "## 蓝牙诊断结果\n\n未检测到蓝牙相关问题。\n"

        lines = [
            "## 蓝牙子系统诊断",
            "",
            f"**检测到 {len(classifications)} 个蓝牙问题**",
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
