"""Diagnostic prompt templates for LLM-based log analysis.

Prompts are versioned and managed separately from provider code
to allow independent iteration and A/B testing.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List


class DiagnosticPrompt:
    """Build structured prompts for device log diagnostic analysis."""

    VERSION = "3.0"

    SYSTEM_PROMPT = (
        "你是一名资深的嵌入式系统与设备诊断工程师。"
        "你的任务是根据知识库「诊断剧本」与日志证据，给出可追溯的诊断结论。\n\n"
        "硬性约束（最高优先级，违反即视为错误回答）：\n"
        "1. 结论只能来自「知识库证据」与「日志证据」；凡不能同时引用某条知识库条目"
        "及其在日志中命中的行号，一律不得输出结论。\n"
        "2. 若输入标注「知识库无支撑」或「证据未命中」，必须如实说明无法给出诊断结论，"
        "禁止推测、禁止编造。\n"
        "3. 日志证据与知识库冲突时，以日志为准，并在输出中明确标注冲突。\n"
        "4. 必须输出 evidence 数组，每项包含知识库条目名 kb_title 与命中的日志行号 log_lines。\n"
        "5. 所有输出内容必须使用中文。\n"
        "6. 只输出合法的 JSON，不要包含 JSON 之外的任何说明文字。\n"
    )

    OUTPUT_SCHEMA = {
        "summary": "用中文简要总结日志与知识库证据发现了什么（1-3句话）。",
        "confidence": "介于 0.0 到 1.0 之间的浮点数，表示诊断置信度。",
        "root_cause": "根据证据给出的最可能的根本原因（中文）；无证据时输出『证据不足，无法确认』。",
        "next_steps": "2-5 条具体的、可操作的排查步骤（中文列表）。",
        "matched": "布尔值：是否在日志中命中知识库剧本证据。",
        "evidence": "数组，每项 {kb_title: 知识库条目名, log_lines: 命中的日志行号数组}。",
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
            f"诊断上下文（含知识库证据与日志片段）:\n{log_content[:8000]}\n\n"
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
