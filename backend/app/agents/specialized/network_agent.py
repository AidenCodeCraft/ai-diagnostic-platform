"""Network 专业诊断 Agent — 专注于网络子系统问题诊断。

能力：
- WiFi/以太网连接异常分析
- TCP/IP 协议栈错误
- DHCP 配置问题
- DNS 解析故障
- 网络驱动异常
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.agents.core.agent import BaseAgent, AgentResult
from app.agents.core.state import AgentState
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class NetworkAgent(BaseAgent):
    """网络专业诊断 Agent。"""

    name = "network_agent"
    description = "Specialized agent for diagnosing network issues including WiFi, Ethernet, TCP/IP, DHCP, and DNS problems."

    NET_KNOWLEDGE = {
        "wifi_connect_fail": {
            "patterns": [
                "wifi", "wlan", "assoc fail", "auth fail",
                "deauth", "connect failed", "4-way handshake",
                "连接失败", "认证失败",
            ],
            "common_causes": [
                "WiFi 密码错误或变更",
                "信号强度不足",
                "MAC 地址过滤",
                "加密方式不兼容（WPA2/WPA3 混用）",
                "信道拥塞",
            ],
            "suggestions": [
                "检查 WiFi 密码是否正确",
                "检查信号强度 (RSSI)",
                "确认路由器 MAC 过滤设置",
                "尝试切换 WiFi 频段 (2.4G/5G)",
            ],
        },
        "dhcp_error": {
            "patterns": [
                "dhcp", "no offer", "dhcp discover",
                "dhcp nak", "dhcp decline", "lease",
                "无法获取IP",
            ],
            "common_causes": [
                "DHCP 服务器未响应",
                "IP 地址池耗尽",
                "网络交换机/VLAN 配置问题",
                "设备 MAC 地址冲突",
            ],
            "suggestions": [
                "检查 DHCP 服务器状态",
                "检查 IP 地址池是否充足",
                "尝试静态 IP 配置作为临时方案",
            ],
        },
        "dns_error": {
            "patterns": [
                "dns", "name resolution", "host unknown",
                "nxdomain", "resolve", "nslookup",
                "域名解析", "DNS",
            ],
            "common_causes": [
                "DNS 服务器不可达",
                "DNS 缓存过期",
                "域名配置错误",
                "DNS over HTTPS 配置问题",
            ],
            "suggestions": [
                "ping 检查 DNS 服务器可达性",
                "尝试更换 DNS 服务器 (如 8.8.8.8)",
                "刷新 DNS 缓存",
            ],
        },
        "tcp_error": {
            "patterns": [
                "tcp", "connection refused", "connection reset",
                "syn", "ack", "rst", "time_wait",
                "connection timeout",
            ],
            "common_causes": [
                "目标端口未开放",
                "防火墙拦截",
                "TCP 窗口过大导致拥塞",
                "MTU 分片问题",
            ],
            "suggestions": [
                "检查目标端口是否开放",
                "检查防火墙规则",
                "检查 MTU 配置 (建议 ≤ 1500)",
            ],
        },
    }

    def plan(self, **context: Any) -> List[str]:
        return [
            "parse_net_events",
            "classify_net_issue",
            "rule_check_net",
            "net_root_cause_analysis",
        ]

    def run(self, **context: Any) -> AgentResult:
        try:
            self.state_machine.transition_to(AgentState.PLANNING)

            events = context.get("events", [])
            user_query = context.get("user_query", "")
            log_content = context.get("log_content", "")

            net_events = self._filter_net_events(log_content, events)
            self.state_machine.transition_to(AgentState.PLAN_READY)

            self.state_machine.transition_to(AgentState.EXECUTING)
            classifications = self._classify_net_problems(net_events, user_query)

            self.state_machine.transition_to(AgentState.REASONING)
            diagnosis = self._reason_net_diagnosis(classifications, net_events)

            self.state_machine.transition_to(AgentState.VALIDATING)
            self.state_machine.transition_to(
                AgentState.COMPLETED if self.validate(diagnosis) else AgentState.FAILED
            )

            if self.state_machine.state != AgentState.COMPLETED:
                return AgentResult(state=AgentState.FAILED, error="Network diagnosis validation failed")

            summary = self._build_net_summary(diagnosis, classifications)
            return AgentResult(
                state=self.state_machine.state,
                summary=summary,
                steps=[{
                    "agent": self.name,
                    "net_events_count": len(net_events),
                    "classifications": classifications,
                    "diagnosis": diagnosis,
                }],
                metadata={
                    "agent_type": "network_specialist",
                    "issues_found": len(classifications),
                },
            )

        except Exception as exc:
            self.state_machine.transition_to(AgentState.FAILED)
            logger.error(f"[NetworkAgent] Failed: {exc}")
            return AgentResult(state=AgentState.FAILED, error=str(exc))

    def _filter_net_events(self, _log_content: str, events: list) -> list:
        net_keywords = [
            "wifi", "wlan", "ethernet", "network", "tcp", "udp",
            "ipv4", "ipv6", "dhcp", "dns", "arp", "icmp",
            "mac", "phy", "mii", "mdio",
        ]
        return [
            e for e in events
            if any(kw in str(e.get("message", "")).lower() for kw in net_keywords)
        ]

    def _classify_net_problems(
        self, net_events: list, _user_query: str,
    ) -> List[Dict[str, Any]]:
        combined = " ".join(
            str(e.get("message", "")) for e in net_events
        ).lower()

        classifications = []
        for issue_type, config in self.NET_KNOWLEDGE.items():
            matched = [p for p in config["patterns"] if p.lower() in combined]
            if matched:
                severity = {
                    "wifi_connect_fail": 3,
                    "dhcp_error": 4,
                    "dns_error": 3,
                    "tcp_error": 4,
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

    def _reason_net_diagnosis(
        self, classifications: list, net_events: list,
    ) -> Dict[str, Any]:
        if not classifications:
            return {
                "root_cause": "未检测到网络相关问题",
                "confidence": 0.5 if net_events else 0.9,
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

    def _build_net_summary(
        self, diagnosis: Dict[str, Any], classifications: list,
    ) -> str:
        if not classifications:
            return "## 网络诊断结果\n\n未检测到网络相关问题。\n"

        lines = [
            "## 网络子系统诊断",
            "",
            f"**检测到 {len(classifications)} 个网络问题**",
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
