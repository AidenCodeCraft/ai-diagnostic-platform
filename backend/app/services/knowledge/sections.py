"""Markdown 章节切分 — 供检索层按章节建立索引。

背景：整篇文档做 BM25 时，长文档（如 FAQ 汇总）会被长度归一化严重稀释，
即使其中某一节完全对题也排不进前列。按章节切分后，检索命中粒度与
「用户问的是哪个知识点」一致。
"""

from __future__ import annotations

import re
from typing import List, Tuple

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)

# 单节超过该长度时按段落继续切窗，避免超长章节再次稀释 BM25
MAX_SECTION_CHARS = 1200
_WINDOW_CHARS = 1000


def _split_long_section(heading: str, body: str) -> List[Tuple[str, str]]:
    if len(body) <= MAX_SECTION_CHARS:
        return [(heading, body)]

    chunks: List[str] = []
    buf = ""
    for para in re.split(r"\n{2,}", body):
        para = para.strip()
        if not para:
            continue
        if buf and len(buf) + len(para) + 2 > _WINDOW_CHARS:
            chunks.append(buf)
            buf = para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf:
        chunks.append(buf)
    return [(heading, chunk) for chunk in chunks] or [(heading, body[:MAX_SECTION_CHARS])]


def split_markdown_sections(content: str) -> List[Tuple[str, str]]:
    """按 `#` 标题切分文档，返回 [(heading, body), ...]。

    - 标题前的引导内容作为 heading="" 的一节保留
    - 超长小节按空行切窗，每窗继承同一个 heading
    - 无标题文档返回单节，保证仍可检索
    """
    text = content or ""
    if not text.strip():
        return [("", "")]

    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return _split_long_section("", text.strip())

    sections: List[Tuple[str, str]] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        sections.extend(_split_long_section("", preamble))

    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        heading = match.group(2).strip()
        body = text[match.end():end].strip()
        sections.extend(_split_long_section(heading, body))

    return sections or [("", text.strip())]
