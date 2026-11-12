"""Rule Engine — JSON 持久化的诊断规则（内置默认 + 可增删）。

规则文件默认位于 `backend/data/rules/diagnostic_rules.json`（可通过 RULES_FILE 覆盖）。
首次运行使用内置规则；任何增删都会把完整规则列表写回文件，重启后保留。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Union

from app.services.parser.base import ParsedEvent

# 内置规则库 — 规则文件不存在时使用
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
    """Rule-based diagnostic suggestions with JSON persistence.

    Accepts either ParsedEvent objects or plain dicts.
    `rules` 参数显式传入时使用内存规则（不读写文件，便于测试）。
    """

    def __init__(
        self,
        rules: Optional[List[Dict[str, object]]] = None,
        storage_path: Optional[str | Path] = None,
    ) -> None:
        self._persist = rules is None
        self._path = Path(storage_path) if storage_path else self._default_path()
        if rules is not None:
            self.rules = list(rules)
        else:
            self.rules = self._load() or [dict(rule) for rule in _BUILTIN_RULES]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @staticmethod
    def _default_path() -> Path:
        try:
            from app.core.config import settings
            raw = getattr(settings, "RULES_FILE", "data/rules/diagnostic_rules.json")
        except Exception:  # noqa: BLE001 - settings 不可用时用默认路径
            raw = "data/rules/diagnostic_rules.json"
        path = Path(raw)
        if not path.is_absolute():
            # backend/app/services/system/rule_engine.py → parents[3] = backend
            path = Path(__file__).resolve().parents[3] / path
        return path

    def _load(self) -> Optional[List[Dict[str, object]]]:
        try:
            if not self._path.is_file():
                return None
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return None
            rules = []
            for item in data:
                if isinstance(item, dict) and item.get("name") and item.get("match"):
                    rules.append({
                        "name": str(item["name"]),
                        "match": str(item["match"]),
                        "suggestion": str(item.get("suggestion", "")),
                    })
            return rules or None
        except (OSError, json.JSONDecodeError):
            return None

    def save(self) -> None:
        """把当前规则列表写入 JSON 文件（原子替换）。"""
        if not self._persist:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self.rules, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self._path)

    def reload(self) -> None:
        """从文件重新加载规则。"""
        loaded = self._load()
        if loaded is not None:
            self.rules = loaded

    # ------------------------------------------------------------------
    # Suggestions
    # ------------------------------------------------------------------

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
        self.save()

    def remove_rule(self, name: str) -> bool:
        before = len(self.rules)
        self.rules = [r for r in self.rules if str(r["name"]) != name]
        if len(self.rules) < before:
            self.save()
            return True
        return False

    def list_rules(self) -> List[Dict[str, object]]:
        return list(self.rules)  # type: ignore[return-value]

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
