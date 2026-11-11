"""知识库模板契约 — 四类内容的标准章节与必填级别。

类型：
  - case        现场问题处理示例（诊断证据来源）
  - faq         FAQ（参考 + 日志关键字定位）
  - code_logic  代码逻辑（判断提问依据 / 纠错）
  - knowledge   基础知识（判断提问依据 / 常识校验）

级别（level）：
  - required     必填，缺失/为空 → 不能 active
  - recommended  建议，缺失 → 提示但不阻断
  - optional     可选
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


LEVEL_REQUIRED = "required"
LEVEL_RECOMMENDED = "recommended"
LEVEL_OPTIONAL = "optional"


@dataclass(frozen=True)
class SectionSpec:
    key: str
    title: str
    level: str = LEVEL_OPTIONAL
    aliases: Tuple[str, ...] = ()


@dataclass(frozen=True)
class KnowledgeTemplate:
    doc_type: str
    name: str
    sections: Tuple[SectionSpec, ...] = ()
    free_form: bool = False


# 通用子节别名（用于「日志特征」下的 ### 关键词/正则/排除正则）
COMMON_SECTION_ALIASES: Dict[str, str] = {
    "关键词": "log_keywords",
    "关键字": "log_keywords",
    "正则": "log_patterns",
    "正则表达式": "log_patterns",
    "排除正则": "negative_patterns",
    "排除": "negative_patterns",
}


TEMPLATES: Dict[str, KnowledgeTemplate] = {
    "case": KnowledgeTemplate(
        doc_type="case",
        name="现场问题处理示例",
        sections=(
            SectionSpec("symptom", "现象", LEVEL_REQUIRED, ("问题现象", "问题描述", "现象描述")),
            SectionSpec("features", "特征点", LEVEL_RECOMMENDED, ("适用环境", "环境", "特征")),
            SectionSpec("root_cause", "原因", LEVEL_REQUIRED, ("根因", "原因分析", "根因分析")),
            SectionSpec("solution", "处理结果", LEVEL_REQUIRED, ("解决方案", "处理方法", "解决方式")),
            SectionSpec("log_signature", "日志特征", LEVEL_RECOMMENDED, ("日志关键字", "日志定位", "日志特征与定位")),
            SectionSpec("related", "关联知识", LEVEL_OPTIONAL, ("关联", "相关知识")),
            SectionSpec("images", "相关图片", LEVEL_OPTIONAL, ("图片", "截图")),
        ),
    ),
    "faq": KnowledgeTemplate(
        doc_type="faq",
        name="FAQ",
        sections=(
            SectionSpec("symptom", "现象", LEVEL_REQUIRED, ("问题现象", "问题描述")),
            SectionSpec("analysis", "分析", LEVEL_REQUIRED, ("原因", "原因分析", "分析过程")),
            SectionSpec("keywords", "关键字", LEVEL_REQUIRED, ("关键词",)),
            SectionSpec("keyword_explain", "关键字解释", LEVEL_REQUIRED, ("关键字解析", "关键词解释", "关键字说明")),
            SectionSpec("examples", "示例", LEVEL_OPTIONAL),
            SectionSpec("author", "作者", LEVEL_OPTIONAL),
        ),
    ),
    "code_logic": KnowledgeTemplate(
        doc_type="code_logic",
        name="代码逻辑",
        free_form=True,
        sections=(
            SectionSpec("log_signature", "日志特征", LEVEL_OPTIONAL, ("日志关键字",)),
            SectionSpec("related", "关联知识", LEVEL_OPTIONAL, ("相关知识",)),
        ),
    ),
    "knowledge": KnowledgeTemplate(
        doc_type="knowledge",
        name="基础知识",
        free_form=True,
        sections=(
            SectionSpec("log_signature", "日志特征", LEVEL_OPTIONAL, ("日志关键字",)),
            SectionSpec("related", "关联知识", LEVEL_OPTIONAL, ("相关知识",)),
        ),
    ),
}


def get_template(doc_type: Optional[str]) -> Optional[KnowledgeTemplate]:
    return TEMPLATES.get((doc_type or "").strip().lower())


def guess_section_key(title: str) -> str:
    """按章节标题猜测其模板键（跨所有模板的别名）。"""
    title = (title or "").strip()
    if not title:
        return ""
    for template in TEMPLATES.values():
        for spec in template.sections:
            if spec.title == title or title in spec.aliases:
                return spec.key
    return COMMON_SECTION_ALIASES.get(title, "")


def build_alias_map(template: Optional[KnowledgeTemplate]) -> Dict[str, str]:
    """标题/别名 → 章节键。"""
    alias_map: Dict[str, str] = {}
    if template is None:
        return dict(COMMON_SECTION_ALIASES)
    for spec in template.sections:
        alias_map[spec.title] = spec.key
        for alias in spec.aliases:
            alias_map[alias] = spec.key
    for title, key in COMMON_SECTION_ALIASES.items():
        alias_map.setdefault(title, key)
    return alias_map


def list_templates() -> List[Dict]:
    """返回全部模板契约（供前端加载）。"""
    return [
        {
            "doc_type": t.doc_type,
            "name": t.name,
            "free_form": t.free_form,
            "sections": [
                {"key": s.key, "title": s.title, "level": s.level, "aliases": list(s.aliases)}
                for s in t.sections
            ],
        }
        for t in TEMPLATES.values()
    ]
