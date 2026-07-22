"""Rule Engine — YAML-based diagnostic rules with inline defaults."""

from __future__ import annotations

from typing import Dict, List, Optional, Union

from app.services.parser.base import ParsedEvent

# 内置规则库 — 后续可从 YAML 文件或数据库加载
_BUILTIN_RULES = [
    {"name": "usb-timeout", "match": "timeout", "suggestion": "检查 USB 线缆、连接器与供电。"},
    {"name": "usb-descriptor", "match": "descriptor_error", "suggestion": "USB 设备描述符读取失败，检查 PHY 与驱动。"},
    {"name": "usb-enumeration", "match": "enumeration_failure", "suggestion": "USB 枚举失败，检查 HUB 与设备供电。"},
    {"name": "filesystem-failure", "match": "filesystem", "suggestion": "检查存储挂载状态与文件系统日志。"},
    {"name": "oom-killer", "match": "oom", "suggestion": "内存不足，检查进程内存使用与 swap 配置。"},
    {"name": "kernel-panic", "match": "panic", "suggestion": "内核崩溃，捕获完整堆栈，检查近期驱动变更。"},
    {"name": "memory-corruption", "match": "memory", "suggestion": "可能内存损坏，运行 memtest 检查。"},
    {"name": "io-error", "match": "io_error", "suggestion": "I/O 错误，检查磁盘健康状态与线缆。"},
    {"name": "hci-timeout", "match": "hci_timeout", "suggestion": "HCI 超时，检查蓝牙芯片与固件。"},
    {"name": "firmware-error", "match": "firmware_error", "suggestion": "固件错误，尝试重新烧录或更新固件。"},
    {"name": "connection-error", "match": "connection_error", "suggestion": "连接错误，检查信号强度与天线。"},
    {"name": "link-error", "match": "link_error", "suggestion": "链路错误，检查物理层与协议栈。"},
    {"name": "transport-error", "match": "transport_error", "suggestion": "传输层错误，检查总线驱动。"},
    {"name": "over-current", "match": "over_current", "suggestion": "过流保护触发，检查外设供电。"},
    {"name": "failure", "match": "failure", "suggestion": "通用故障，检查相关模块日志。"},
]


class RuleEngine:
    """Rule-based diagnostic suggestions for parsed events.

    Accepts either ParsedEvent objects or plain dicts.
    Rules are loaded from built-in defaults; future versions will
    support YAML file and database-based rule management.
    """

    def __init__(self, rules: Optional[List[Dict[str, object]]] = None) -> None:
        self.rules = rules or _BUILTIN_RULES

    def generate_suggestions(
        self,
        events: List[Union[ParsedEvent, Dict[str, object]]],
    ) -> List[Dict[str, object]]:
        suggestions: List[Dict[str, object]] = []
        seen = set()
        for event in events:
            classification = self._get_classification(event).lower()
            module = self._get_module(event)
            for rule in self.rules:
                if str(rule["match"]).lower() in classification:
                    key = str(rule["name"])
                    if key not in seen:
                        seen.add(key)
                        suggestions.append({
                            "rule": rule["name"],
                            "message": str(rule["suggestion"]),
                            "module": str(module or "system"),
                        })
                    break
        return suggestions

    def add_rule(self, name: str, match: str, suggestion: str) -> None:
        self.rules.append({"name": name, "match": match, "suggestion": suggestion})

    def remove_rule(self, name: str) -> bool:
        before = len(self.rules)
        self.rules = [r for r in self.rules if str(r["name"]) != name]
        return len(self.rules) < before

    def list_rules(self) -> List[Dict[str, object]]:
        return list(self.rules)

    @staticmethod
    def _get_classification(event: Union[ParsedEvent, Dict[str, object]]) -> str:
        if isinstance(event, ParsedEvent):
            return event.classification or ""
        return str(event.get("classification", ""))

    @staticmethod
    def _get_module(event: Union[ParsedEvent, Dict[str, object]]) -> object:
        if isinstance(event, ParsedEvent):
            return event.module
        return event.get("module")
