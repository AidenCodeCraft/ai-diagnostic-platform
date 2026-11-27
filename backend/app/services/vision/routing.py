"""OCR / 视觉判定（纯函数，可离线单测）。

判定不调模型：模型判断"该用哪个模型"既慢又不稳定，规则反而是可回归的。
规则来源见 docs/16-Implementation/Chat-Image-Recognition-Design.md §3。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

TIMESTAMP_LINE = re.compile(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]")
MODULE_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.]{2,}\.\.[ ]?\d{4}")

PATH_OCR = "ocr"
PATH_VISION = "vision"
PATH_OCR_VISION = "ocr+vision"


@dataclass
class TextStats:
    text_chars: int = 0
    line_with_ts: int = 0
    module_id_hits: int = 0
    kb_keyword_hits: int = 0

    @property
    def looks_like_log(self) -> bool:
        return self.line_with_ts >= 3 or self.module_id_hits >= 1


def analyze_text(text: str, keywords: Optional[Iterable[str]] = None) -> TextStats:
    content = text or ""
    lines = content.splitlines()
    stats = TextStats(text_chars=len(content))

    for line in lines:
        if TIMESTAMP_LINE.search(line):
            stats.line_with_ts += 1
    stats.module_id_hits = len(MODULE_ID.findall(content))

    if keywords:
        lowered = content.lower()
        stats.kb_keyword_hits = sum(
            1 for word in keywords if word and word.lower() in lowered
        )
    return stats


def decide_path(
    text: str,
    *,
    ocr_failed: bool = False,
    keywords: Optional[Iterable[str]] = None,
) -> str:
    """返回 ocr / vision。"""
    if ocr_failed or not (text or "").strip():
        return PATH_VISION

    stats = analyze_text(text, keywords)
    if stats.looks_like_log:
        return PATH_OCR
    if stats.kb_keyword_hits >= 2 and stats.text_chars >= 500:
        return PATH_OCR
    return PATH_VISION
