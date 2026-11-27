"""把「知识库关键字 + 日志时间窗」组合成可引用证据（P1 步骤 4 收口）。

输出两部分：
  - `text`：拼进回答上下文的证据块（带行号/命中模式/样例行），供模型引用；
  - `summary`：给人看的结论句（全部未命中 / 部分命中 / 无可用关键点三态）。

这一层不做检索也不做日志读取，只负责组合，便于单测与复用（追问、复盘、回归）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from app.services.chat.log_locator import LocateResult, locate_bytes
from app.services.chat.log_patterns import (
    LogPattern,
    describe_partial_hits,
    describe_zero_hits,
    extract_patterns,
)

MAX_EVIDENCE_BLOCKS = 10


@dataclass
class LogEvidence:
    patterns: List[LogPattern] = field(default_factory=list)
    result: Optional[LocateResult] = None
    text: str = ""
    summary: str = ""

    @property
    def has_hits(self) -> bool:
        return bool(self.result and self.result.has_hits)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patterns": [pattern.to_dict() for pattern in self.patterns],
            "locate": self.result.to_dict() if self.result else None,
            "summary": self.summary,
        }


def _render_blocks(result: LocateResult, window_label: str) -> str:
    if not result.blocks:
        return ""
    header = f"## 日志命中{f'（{window_label}）' if window_label else ''}"
    lines = [header]
    for index, block in enumerate(result.blocks[:MAX_EVIDENCE_BLOCKS], start=1):
        patterns = "、".join(block.patterns[:4]) or "—"
        lines.append(
            f"{index}. 行 {block.line_start}-{block.line_end}"
            f"（命中 {block.hits} 条：{patterns}）"
        )
        for sample in block.samples[:2]:
            lines.append(f"   {sample}")
    return "\n".join(lines)


def build_log_evidence(
    items: Sequence[Dict[str, Any]],
    log_bytes: Optional[bytes],
    *,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    question: str = "",
    window_label: str = "",
    encoding: str = "utf-8",
) -> LogEvidence:
    """从知识库召回 + 日志内容生成证据块。

    Args:
        items: 知识库检索结果（含 snippet/section/key）
        log_bytes: 时间窗对应的日志内容；None 表示本轮没有日志
        start/end: 时间窗（用于在日志内二次过滤）
        question: 用户问题（用于给问题里的词降权）
    """
    patterns = extract_patterns(items, question=question)
    if not patterns:
        return LogEvidence(
            patterns=[],
            result=None,
            text="",
            summary=describe_zero_hits([], window_label=window_label),
        )

    if not log_bytes:
        return LogEvidence(
            patterns=patterns,
            result=None,
            text="",
            summary="本轮没有可用的日志内容，无法按关键点定位；请确认附件是否已上传成功。",
        )

    result = locate_bytes(
        log_bytes, patterns, encoding=encoding, start=start, end=end,
    )

    if not result.has_hits:
        return LogEvidence(
            patterns=patterns,
            result=result,
            text="",
            summary=describe_zero_hits(patterns, window_label=window_label),
        )

    summary = describe_partial_hits(patterns, result.pattern_hits, window_label=window_label)
    if not summary:
        distinct = len({p for block in result.blocks for p in block.patterns})
        summary = f"共 {len(result.blocks)} 个命中块，覆盖 {distinct} 类关键点。"

    return LogEvidence(
        patterns=patterns,
        result=result,
        text=_render_blocks(result, window_label),
        summary=summary,
    )
