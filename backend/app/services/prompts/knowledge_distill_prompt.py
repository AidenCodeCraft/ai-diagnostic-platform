"""自进化蒸馏提示词 — 把一次已解决的问答蒸馏为结构化「诊断剧本」。

版本化管理；仅产出候选草案，必须经人工审核后才进入知识库检索。
"""

from __future__ import annotations

from typing import List


class KnowledgeDistillPrompt:
    """构建自进化蒸馏 prompts。"""

    VERSION = "1.0"

    SYSTEM_PROMPT = (
        "你是知识库整理助手。请把一次已解决的技术问答蒸馏为结构化的「诊断剧本」，"
        "用于后续在同类日志中定位问题。只输出合法 JSON，不要输出 JSON 之外的任何内容。\n\n"
        "字段说明：\n"
        "- symptom：现象/问题（中文）\n"
        "- environment：设备/芯片/固件版本（可为空）\n"
        "- log_keywords：日志关键词数组（用于 grep）\n"
        "- log_patterns：日志正则数组（必须可编译的正则表达式）\n"
        "- negative_patterns：排除用正则数组（可为空）\n"
        "- expected：命中后如何判定（如提取 x.y.z 版本号）\n"
        "- root_cause：根因（中文）\n"
        "- solution：解决方案（中文）\n\n"
        "要求：不确定的字段留空字符串或空数组，禁止编造。"
    )

    @classmethod
    def build_messages(cls, question: str, answer: str) -> List[dict]:
        return [
            {"role": "system", "content": cls.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"## 问题\n{question[:2000]}\n\n"
                    f"## 处理结果\n{answer[:4000]}"
                ),
            },
        ]
