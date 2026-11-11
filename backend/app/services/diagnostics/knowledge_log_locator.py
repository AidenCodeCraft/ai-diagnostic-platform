"""知识驱动的日志定位器 — 用知识条目的「诊断剧本」在日志中定位证据。

输入：诊断剧本（KnowledgeDiagnosisProfile）+ 日志行
输出：DetectionResult（verdict = hit / partial / miss + 命中行号与片段）

判定语义：
  - hit     ：命中 log_patterns（强证据）
  - partial ：仅命中 log_keywords（弱证据）
  - miss    ：均未命中
负模式（negative_patterns）命中的行会被排除。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from app.core.logging_config import get_logger
from app.models import KnowledgeDiagnosisProfile

logger = get_logger(__name__)

MAX_MATCHED_LINES = 20
MAX_LINE_TEXT = 300


@dataclass
class MatchedLine:
    line_no: int
    text: str
    via: str  # "pattern" | "keyword"

    def to_dict(self) -> dict:
        return {"line_no": self.line_no, "text": self.text, "via": self.via}


@dataclass
class DetectionResult:
    doc_id: int
    title: str
    supported: bool = False
    verdict: str = "miss"  # hit / partial / miss
    matched_lines: List[MatchedLine] = field(default_factory=list)
    keyword_hits: int = 0
    pattern_hits: int = 0
    expected: str = ""
    root_cause: str = ""
    solution: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "supported": self.supported,
            "verdict": self.verdict,
            "matched_lines": [m.to_dict() for m in self.matched_lines],
            "keyword_hits": self.keyword_hits,
            "pattern_hits": self.pattern_hits,
            "expected": self.expected,
            "root_cause": self.root_cause,
            "solution": self.solution,
            "confidence": self.confidence,
        }


class KnowledgeLogLocator:
    """用诊断剧本在日志中定位证据。"""

    def locate(
        self,
        profile: Optional[KnowledgeDiagnosisProfile],
        doc_title: str,
        lines: List[str],
        user_query: str = "",
    ) -> DetectionResult:
        """执行一次定位。profile 为 None 时返回 supported=False 的空结果。"""
        result = DetectionResult(
            doc_id=int(profile.doc_id) if profile is not None and profile.doc_id is not None else 0,
            title=doc_title or "",
        )
        if profile is None:
            return result

        patterns = self._compile_patterns(profile.log_patterns)
        negatives = self._compile_patterns(profile.negative_patterns)
        keywords = [str(k).strip() for k in (profile.log_keywords or []) if str(k).strip()]

        result.supported = bool(patterns or keywords)
        result.expected = str(profile.expected or "")
        result.root_cause = str(profile.root_cause or "")
        result.solution = str(profile.solution or "")
        result.confidence = float(profile.confidence or 0.0)

        if not result.supported:
            return result

        matched: dict[int, MatchedLine] = {}
        for idx, line in enumerate(lines, start=1):
            text = line.strip()
            if not text:
                continue

            via: Optional[str] = None
            for regex in patterns:
                if regex.search(line):
                    via = "pattern"
                    break
            if via is None and keywords:
                lower = line.lower()
                if any(k.lower() in lower for k in keywords):
                    via = "keyword"
            if via is None:
                continue

            # 负数模式命中 → 排除该行
            if any(neg.search(line) for neg in negatives):
                continue

            if len(matched) >= MAX_MATCHED_LINES:
                break
            matched[idx] = MatchedLine(line_no=idx, text=text[:MAX_LINE_TEXT], via=via)

        result.matched_lines = list(matched.values())
        result.pattern_hits = sum(1 for m in result.matched_lines if m.via == "pattern")
        result.keyword_hits = sum(1 for m in result.matched_lines if m.via == "keyword")
        if result.pattern_hits > 0:
            result.verdict = "hit"
        elif result.keyword_hits > 0:
            result.verdict = "partial"
        else:
            result.verdict = "miss"

        logger.info(
            "[Locator] doc=%d title=%.30s supported=%s verdict=%s matched=%d",
            result.doc_id, result.title, result.supported, result.verdict, len(result.matched_lines),
        )
        return result

    @staticmethod
    def _compile_patterns(raw) -> List[re.Pattern]:
        compiled: List[re.Pattern] = []
        for pattern in raw or []:
            pattern = str(pattern).strip()
            if not pattern:
                continue
            try:
                compiled.append(re.compile(pattern))
            except re.error as exc:
                logger.warning("[Locator] invalid regex %r: %s", pattern, exc)
        return compiled
