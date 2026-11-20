"""Markdown 章节切分 — 检索层唯一的切分口径。

背景：整篇文档做 BM25/向量时，长文档（如 FAQ 汇总）会被长度归一化严重稀释，
即使某一节完全对题也排不进前列。按章节切分后，检索命中粒度与「用户问的是
哪个知识点」一致；BM25 索引、向量写入、snippet 展示必须用同一套切分，
否则两路召回的分对不上（这也是此前 BM25 提权规则做歪的根因）。
"""

from __future__ import annotations

import hashlib
import re
from typing import List, Tuple

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)

# 单节超过该长度时按段落继续切窗，避免超长章节再次稀释 BM25
MAX_SECTION_CHARS = 1200
_WINDOW_CHARS = 1000

# 少于该长度的章节不单独成块（多为占位/单行标题）；再短的正文仍有价值时
# 会与相邻段落合并进同一个章节窗（见 _split_long_section）
MIN_SECTION_CHARS = 12

# 低于该长度的子标题碎片（如「现象」「分析」「关键字」）合并进上一个章节：
# 它们单独成块时 BM25 分虚高、会挤掉真正对题的完整章节（真实案例：
# 「进出站日志中搜索什么」被《线路》的「关键字」碎片顶掉）。
MERGE_TINY_SECTION_CHARS = 80

# 章节名保留父级路径的层数上限（太长的路径反而看不清）
MAX_PATH_DEPTH = 3

# 目录/前言这类「导航与声明」内容不该进入检索：它们命中率高但对诊断无用，
# 还会挤掉真正对题的章节（FAQ 类文档尤其明显）。
DROPPED_HEADINGS = (
    "目录", "表目录", "图目录", "contents", "table of contents", "索引",
    "前言", "序言", "导读", "关于本文", "关于本文档",
    "修订记录", "变更记录", "更新记录", "免责声明", "版权声明",
)

# 目录行：`- [标题](#anchor)` 或 `标题……12`
_TOC_ENTRY_RE = re.compile(r"^\s*(?:[-*+]\s+)?(?:\[[^\]]*\]\(#[^)]*\)|.{0,80}?(?:\.{3,}|…{2,}|·{3,})\s*\d+\s*$)")


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


def is_navigation_heading(heading: str) -> bool:
    """标题是否属于目录/前言/声明类（不参与检索）。"""
    normalized = (heading or "").strip().lower()
    if not normalized:
        return False
    return any(normalized == key or normalized.startswith(key) for key in DROPPED_HEADINGS)


def looks_like_toc(body: str) -> bool:
    """正文是否像目录（多行「标题……页码」或锚点链接）。"""
    lines = [line for line in (body or "").splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    hits = sum(1 for line in lines if _TOC_ENTRY_RE.match(line))
    return hits >= max(3, int(len(lines) * 0.6))


def merge_tiny_sections(
    sections: List[Tuple[str, str]], min_chars: int = MERGE_TINY_SECTION_CHARS,
) -> List[Tuple[str, str]]:
    """把过短的章节碎片并入上一个章节（保持顺序与标题）。"""
    merged: List[Tuple[str, str]] = []
    for heading, body in sections:
        text = (body or "").strip()
        if merged and len(text) < min_chars:
            prev_heading, prev_body = merged[-1]
            extra = f"### {heading}\n{text}".strip() if heading else text
            merged[-1] = (prev_heading, f"{prev_body}\n\n{extra}".strip())
            continue
        merged.append((heading, text))
    return merged


def join_heading_path(stack: List[Tuple[int, str]], title: str) -> str:
    """把父级标题链拼成「父 > 子」，让碎片标题仍然带着主题。

    为什么必须带父级：文档里「关键字」「现象」「分析」这类子标题会重复出现，
    只保留叶子名时，召回结果无法判断它属于哪个知识点，
    人也无法据此判断「命中的是不是那一节」。
    """
    parents = [name for _level, name in stack][-(MAX_PATH_DEPTH - 1):]
    parts = [part for part in (*parents, title) if part]
    return " > ".join(parts)


def split_markdown_sections(
    content: str, *, drop_navigation: bool = True, merge_tiny: bool = False,
    with_path: bool = True,
) -> List[Tuple[str, str]]:
    """按 `#` 标题切分文档，返回 [(heading, body), ...]。

    - 标题前的引导内容作为 heading="" 的一节保留
    - 超长小节按空行切窗，每窗继承同一个 heading
    - 无标题文档返回单节，保证仍可检索
    - drop_navigation=True 时丢弃目录/前言/声明类章节（可用参数关闭以便排查）
    - merge_tiny=True 时把「现象/分析/关键字」这类超短子标题并入上一节
      （默认关闭：黄金集实测 merge 后 recall@5 0.952→0.905、MRR 0.921→0.786，明确更差）
    - with_path=True（默认）时章节名带父级路径：`5. 进出站 > 关键字`
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

    stack: List[Tuple[int, str]] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        level = len(match.group(1))
        heading = match.group(2).strip()
        body = text[match.end():end].strip()

        if drop_navigation and (is_navigation_heading(heading) or looks_like_toc(body)):
            continue

        while stack and stack[-1][0] >= level:
            stack.pop()
        label = join_heading_path(stack, heading) if with_path else heading
        stack.append((level, heading))
        sections.extend(_split_long_section(label, body))

    if merge_tiny:
        sections = merge_tiny_sections(sections)

    return sections or [("", text.strip())]


def section_key(doc_id: int, section: str, chunk_no: int) -> str:
    """章节块的稳定标识（与向量库主键、BM25 命中同一口径）。"""
    return f"{doc_id}:{section or ''}:{chunk_no}"


def content_hash(title: str, heading: str, body: str) -> str:
    return hashlib.sha1(f"{title}\n{heading}\n{body}".encode("utf-8")).hexdigest()
