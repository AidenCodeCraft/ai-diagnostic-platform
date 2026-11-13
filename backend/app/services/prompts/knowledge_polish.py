"""知识库 AI 润色提示词 — 在不改变原意/关键信息的前提下按模板规范化。

版本化管理；只输出 Markdown 正文。
"""

from __future__ import annotations

from typing import List


class KnowledgePolishPrompt:
    """构建「用户草稿 → 模板化 Markdown」的润色 prompts。"""

    VERSION = "1.0"

    SYSTEM_PROMPT = (
        "你是知识库格式规范化助手。你的任务是把用户草稿整理为符合指定文档模板的 Markdown。\n"
        "硬性要求：\n"
        "1. 不改变原意、不新增用户未提供的事实、不删减关键技术信息；\n"
        "2. 型号、版本号、命令、报错码、数字等关键信息必须原样保留，不得改写；\n"
        "3. 按模板章节顺序组织内容，可补充分节标题、条目化排版和简短衔接说明；\n"
        "4. 如果草稿包含多条并列内容（多个问题/多个知识点/多条说明），"
        "请为每条内容开头统一添加序号（1.、2.、3.），确保润色结果按序号清晰分隔；\n"
        "5. 不编造技术结论；不确定的内容保持原样或标注“待确认”；\n"
        "6. 只输出 Markdown 正文，不要代码围栏、不要解释、不要额外对话。"
    )

    @classmethod
    def build_messages(
        cls,
        content: str,
        doc_type_name: str,
        guide: str,
        skeleton: str = "",
    ) -> List[dict]:
        parts = [
            f"## 文档类型\n{doc_type_name}\n",
            f"## 格式要求\n{guide}\n",
        ]
        if skeleton.strip():
            parts.append(
                f"## 模板骨架（仅示意结构，不要原样输出占位符）\n{skeleton.strip()}\n"
            )
        parts.append(f"## 用户草稿\n{content[:8000]}\n")
        parts.append("请输出润色并规范化后的完整 Markdown。")
        return [
            {"role": "system", "content": cls.SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(parts)},
        ]
