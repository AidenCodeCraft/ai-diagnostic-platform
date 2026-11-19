"""从知识库命中章节抽取日志匹配模式（P1 步骤 4 前半）。

原则（D7）：关键字**只来自知识库命中章节的正文**，不维护独立的错误关键字清单。
因此每条模式都必须能在来源文本里找到原文，抽不出就说「知识库没给可匹配的点」，
不允许模型凭空补词。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

# 类型优先级：越靠前越「可确定命中」，排序时优先
TYPE_PRIORITY = {
    "at_cmd": 0,
    "param": 1,
    "module": 2,
    "code": 3,
    "literal": 4,
    "phrase": 5,
}

MAX_PATTERNS = 24
MIN_LITERAL_CHARS = 3          # 英文/数字类字面量的最小长度
MIN_PHRASE_CHARS = 2           # 中文短语最小长度

_AT_CMD_RE = re.compile(r"\bAT\+[A-Z0-9]{2,}\b", re.IGNORECASE)
_PARAM_RE = re.compile(r"\b(?:P|s)_[A-Za-z0-9_]{2,}\b")
_MODULE_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b")
_CODE_RE = re.compile(r"\b\d{3,4}\b")
_LITERAL_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9+.#-]{2,}\b")
_QUOTED_RE = re.compile(r"[`「『\"]([^`」』\"]{2,30})[`」』\"]")
_HEADING_SPLIT_RE = re.compile(r"[\s，,。:：、/|()（）\[\]<>《》\-_]+")


@dataclass
class LogPattern:
    pattern: str
    type: str
    source_key: str = ""
    source_section: str = ""
    case_sensitive: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern": self.pattern,
            "type": self.type,
            "source_key": self.source_key,
            "source_section": self.source_section,
            "case_sensitive": self.case_sensitive,
        }

    @property
    def priority(self) -> int:
        return TYPE_PRIORITY.get(self.type, TYPE_PRIORITY["phrase"])


def _add(
    bucket: Dict[str, LogPattern],
    text: str,
    pattern_type: str,
    *,
    source_key: str,
    source_section: str,
) -> None:
    value = (text or "").strip()
    if not value:
        return
    key = value.lower()
    if key in bucket:
        return
    bucket[key] = LogPattern(
        pattern=value,
        type=pattern_type,
        source_key=source_key,
        source_section=source_section,
    )


def extract_patterns(
    items: Sequence[Dict[str, Any]],
    *,
    question: str = "",
    limit: int = MAX_PATTERNS,
) -> List[LogPattern]:
    """从召回的章节中抽取模式。

    Args:
        items: 检索结果（需含 snippet 或 text，以及 key/section）
        question: 用户问题，用于给「已在问题里出现」的词降权（它们往往不是日志词）
        limit: 最多返回多少条

    Returns:
        去重并按类型优先级排序的模式列表；为空表示知识库没有可匹配的点。
    """
    bucket: Dict[str, LogPattern] = {}
    question_lower = (question or "").lower()

    for item in items or []:
        source_key = str(item.get("key") or item.get("id") or "")
        section = str(item.get("section") or "")
        text = str(item.get("snippet") or item.get("text") or "")
        heading = section or str(item.get("title") or "")

        # 1) AT 指令：可确定命中
        for match in _AT_CMD_RE.finditer(text):
            _add(bucket, match.group(0), "at_cmd", source_key=source_key, source_section=section)
        # 2) 参数名 / 模块名
        for match in _PARAM_RE.finditer(text):
            _add(bucket, match.group(0), "param", source_key=source_key, source_section=section)
        for match in _MODULE_RE.finditer(text):
            _add(bucket, match.group(0), "module", source_key=source_key, source_section=section)
        # 3) 章节标题里的短语（标题通常就是「要搜什么」）
        for token in _HEADING_SPLIT_RE.split(heading):
            token = token.strip()
            if len(token) >= MIN_PHRASE_CHARS:
                _add(bucket, token, "phrase", source_key=source_key, source_section=section)
        # 4) 引号/反引号里的原文短语
        for match in _QUOTED_RE.finditer(text):
            inner = match.group(1).strip()
            if inner:
                _add(bucket, inner, "literal", source_key=source_key, source_section=section)
        # 5) 英文/数字字面量 + 编号
        for match in _LITERAL_RE.finditer(text):
            token = match.group(0)
            if len(token) >= MIN_LITERAL_CHARS and token.lower() not in question_lower:
                _add(bucket, token, "literal", source_key=source_key, source_section=section)
        for match in _CODE_RE.finditer(text):
            _add(bucket, match.group(0), "code", source_key=source_key, source_section=section)

    patterns = list(bucket.values())
    patterns.sort(key=lambda p: (p.priority, -len(p.pattern)))
    return patterns[:limit]


def patterns_to_dicts(patterns: Iterable[LogPattern]) -> List[Dict[str, Any]]:
    return [pattern.to_dict() for pattern in patterns]


def describe_zero_hits(patterns: Sequence[LogPattern], *, window_label: str = "") -> str:
    """全部未命中时的结论文本（必须说「关键点未命中」，不是「未找到」）。"""
    if not patterns:
        return "知识库里没有可用于匹配日志的关键点，建议补充对应文档后再查。"
    names = "、".join(sorted({p.pattern for p in patterns})[:8])
    prefix = f"{window_label} " if window_label else ""
    return f"{prefix}日志中没有出现知识库所列的关键点（{names}），可能是时段不对或该问题不在这份日志里。"


def describe_partial_hits(
    patterns: Sequence[LogPattern], hits: Dict[str, int], *, window_label: str = "",
) -> str:
    """部分命中时，末尾标注哪些关键点没有痕迹。"""
    missing = [p.pattern for p in patterns if not hits.get(p.pattern.lower())]
    if not missing:
        return ""
    prefix = f"{window_label} " if window_label else ""
    return f"{prefix}以下关键点在日志中未出现：{'、'.join(sorted(set(missing))[:8])}。"
