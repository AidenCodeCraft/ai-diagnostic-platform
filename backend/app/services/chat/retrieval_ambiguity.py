"""检索歧义判定 — 多个章节得分接近时，先问用户指的是哪一个。

纯函数，便于单测；不依赖数据库/LLM。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

# 次优/最优得分比达到该值即视为「无法确定」
DEFAULT_RATIO = 0.85
# 低于该得分视为弱相关，不参与澄清
DEFAULT_MIN_SCORE = 0.15


@dataclass
class AmbiguousCandidate:
    doc_id: Any
    title: str
    section: str
    score: float
    status: str = "active"

    def option_label(self) -> str:
        label = f"{self.title} · {self.section}" if self.section else self.title
        return f"{label}（草稿）" if self.status == "draft" else label


def find_ambiguous_candidates(
    candidates: Sequence[Dict[str, Any]],
    query: str,
    *,
    ratio: float = DEFAULT_RATIO,
    min_score: float = DEFAULT_MIN_SCORE,
    max_options: int = 4,
) -> List[AmbiguousCandidate]:
    """返回需要用户确认的候选；无需澄清时返回空列表。

    触发条件（同时满足）：
      1. 至少两个候选得分 >= min_score
      2. 前两名来自不同文档
      3. 次优/最优得分比 >= ratio（分数接近）
      4. 用户问题里尚未直接点名第一名（标题或章节）
    """
    normalized: List[AmbiguousCandidate] = []
    seen = set()
    for raw in candidates or []:
        try:
            score = float(raw.get("score", 0) or 0)
        except (TypeError, ValueError):
            continue
        if score < min_score:
            continue
        section = str(raw.get("section") or "").strip()
        title = str(raw.get("title") or "").strip() or "未命名文档"
        key = (raw.get("doc_id"), section)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(AmbiguousCandidate(
            doc_id=raw.get("doc_id"),
            title=title,
            section=section,
            score=score,
            status=str(raw.get("status") or "active"),
        ))

    if len(normalized) < 2:
        return []

    normalized.sort(key=lambda c: c.score, reverse=True)

    # 同一文档只保留最佳章节：避免同一份 FAQ 的多个小节占满选项
    per_doc: List[AmbiguousCandidate] = []
    seen_docs = set()
    for candidate in normalized:
        if candidate.doc_id in seen_docs:
            continue
        seen_docs.add(candidate.doc_id)
        per_doc.append(candidate)

    if len(per_doc) < 2:
        return []

    top, second = per_doc[0], per_doc[1]

    if top.doc_id == second.doc_id:
        return []
    if top.score <= 0 or second.score / top.score < ratio:
        return []

    q = (query or "").strip().lower()
    if q:
        if top.section and top.section.lower() in q:
            return []
        if top.title and top.title.lower() in q:
            return []

    return per_doc[:max_options]
