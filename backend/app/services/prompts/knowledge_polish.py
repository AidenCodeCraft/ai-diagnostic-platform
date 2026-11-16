"""知识库 AI 润色提示词 — 在不改变原意/关键信息的前提下按模板规范化。

版本化管理；只输出 Markdown 正文。
"""

from __future__ import annotations

from typing import List


class KnowledgePolishPrompt:
    """构建「用户草稿 → 模板化 Markdown」的润色 prompts。"""

    VERSION = "1.1"

    SYSTEM_PROMPT = (
        "你是知识库格式规范化助手。你的任务是把用户草稿整理为符合指定文档模板的 Markdown。\n"
        "硬性要求：\n"
        "1. 不改变原意、不新增用户未提供的事实、不删减关键技术信息；\n"
        "2. 型号、版本号、命令、报错码、数字等关键信息必须原样保留，不得改写；\n"
        "3. 按模板章节顺序组织内容，可补充分节标题、条目化排版和简短衔接说明；\n"
        "4. 如果草稿包含多条并列内容（多个问题/多个知识点/多条说明），"
        "请为每条内容开头统一添加序号（1.、2.、3.），确保润色结果按序号清晰分隔；"
        "已有编号的内容保留原有编号，不要重新编号；\n"
        "5. 不编造技术结论；不确定的内容保持原样或标注“待确认”；\n"
        "6. 只输出 Markdown 正文，不要代码围栏、不要解释、不要额外对话。"
    )

    SELECTION_SYSTEM_PROMPT = (
        "你是知识库文档润色助手。只对给定的文本片段做润色，且必须遵循提供的「格式说明」的格式要求：\n"
        "1. 保持原意、专业术语、型号/版本/数字/命令/报错码完全不变，不新增用户未提供的事实；\n"
        "2. 严格按「格式说明」中的写作与排版要求重新组织片段，常见要求包括："
        "并列的标签/键值对行整理为无序列表（- **标签**：值），多条并列内容统一「1.、2.、3.」编号，"
        "关键信息加粗，涉及日志特征时按关键词/正则的规范表达；\n"
        "3. 选中文本只是文档片段：不要新增 ## 章节标题或分节，不要输出片段之外的内容；"
        "片段自身已有的 Markdown 结构（标题层级、列表、代码块、表格）可以保留，"
        "但标题序号、列表编号必须保持原样，不得重新编号；\n"
        "4. 修正错别字与标点问题，语句应通顺、专业、简洁；\n"
        "5. 不编造技术结论；不确定的内容保持原样或标注“待确认”；\n"
        "6. 除非片段已完全符合格式说明，否则必须按格式说明切实重新组织排版与表达，"
        "不要只做轻微改动或原样返回；\n"
        "7. 只输出润色后的片段，不要代码围栏、不要解释、不要额外对话。"
    )

    @classmethod
    def build_selection_messages(
        cls,
        text: str,
        doc_type_name: str = "",
        guide: str = "",
        skeleton: str = "",
        section_title: str = "",
    ) -> List[dict]:
        parts = [f"## 文档类型\n{doc_type_name or '通用'}\n"]
        if guide.strip():
            parts.append(f"## 格式说明（润色必须遵循的格式要求）\n{guide.strip()}\n")
        if skeleton.strip():
            parts.append(
                f"## 模板结构示例（仅用于判断片段应采用的表达格式，不要原样输出占位符）\n{skeleton.strip()}\n"
            )
        if section_title.strip():
            parts.append(f"## 选中文本所属章节\n{section_title.strip()}\n")
        parts.append(f"## 待润色文本\n{text[:8000]}\n")
        parts.append("请只输出按格式说明润色后的文本片段（保持片段形式，不要新增章节标题）。")
        return [
            {"role": "system", "content": cls.SELECTION_SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(parts)},
        ]

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
        parts.append(f"## 用户草稿\n{content[:30000]}\n")
        parts.append("请输出润色并规范化后的完整 Markdown。")
        return [
            {"role": "system", "content": cls.SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(parts)},
        ]
