"""Diagnostic prompt templates for LLM-based log analysis.

Prompts are versioned and managed separately from provider code
to allow independent iteration and A/B testing.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List


class DiagnosticPrompt:
    """Build structured prompts for device log diagnostic analysis."""

    VERSION = "2.0"

    SYSTEM_PROMPT = (
        "你是一名资深的嵌入式系统与设备诊断工程师。"
        "你的任务是根据用户上传的设备日志，找出根本原因，并给出可执行的排查建议。\n\n"
        "规则：\n"
        "1. 仅根据日志中实际存在的数据得出结论，不得凭空捏造。\n"
        "2. 所有输出内容必须使用中文。\n"
        "3. 给出合理的置信度评分。\n"
        "4. 给出具体、可操作的排查步骤（避免泛泛而谈）。\n"
        "5. 只输出合法的 JSON，不要包含 JSON 之外的任何说明文字。\n"
    )

    OUTPUT_SCHEMA = {
        "summary": "用中文简要总结日志中发现了什么（1-3句话）。",
        "confidence": "介于 0.0 到 1.0 之间的浮点数，表示诊断置信度。",
        "root_cause": "根据日志证据给出的最可能的根本原因（中文）。",
        "next_steps": "2-5 条具体的、可操作的排查步骤（中文列表）。",
    }

    @classmethod
    def build(cls, log_content: str, events: List[Dict[str, Any]]) -> str:
        error_events = [e for e in events if e.get("is_error")]
        error_summary = cls._build_error_summary(error_events)

        return (
            f"{cls.SYSTEM_PROMPT}\n\n"
            f"--- 日志分析任务 ---\n\n"
            f"解析事件总数: {len(events)}，其中错误事件: {len(error_events)}\n\n"
            f"错误概览:\n{error_summary}\n\n"
            f"原始日志内容:\n{log_content[:8000]}\n\n"
            f"---\n"
            f"请返回以下格式的 JSON 对象:\n"
            f"{json.dumps(cls.OUTPUT_SCHEMA, indent=2, ensure_ascii=False)}\n\n"
            f"只输出 JSON 对象本身，不要包含其他内容。"
        )

    @classmethod
    def _build_error_summary(cls, error_events: List[Dict[str, Any]]) -> str:
        if not error_events:
            return "No error events detected."

        # Group by classification
        grouped: Dict[str, List[str]] = {}
        for ev in error_events:
            cls_name = ev.get("classification", "unknown")
            module = ev.get("module", "system")
            grouped.setdefault(cls_name, []).append(module)

        lines = []
        for classification, modules in grouped.items():
            unique_modules = list(dict.fromkeys(modules))
            lines.append(
                f"  - {classification} ({len(modules)} occurrences, modules: {', '.join(unique_modules[:3])})"
            )
        return "\n".join(lines)
