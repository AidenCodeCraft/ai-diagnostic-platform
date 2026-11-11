"""Markdown 分节解析 — 按标题切分并映射到模板章节键。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from app.services.knowledge.templates import build_alias_map, get_template

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass
class ParsedSection:
    section_key: str
    title: str
    level: int
    start_line: int
    end_line: int
    content: str

    def to_dict(self) -> dict:
        return {
            "section_key": self.section_key,
            "title": self.title,
            "level": self.level,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "content": self.content,
        }


class SectionParser:
    """把 Markdown 内容解析为带行号范围的分节列表。"""

    @staticmethod
    def parse(content: str, doc_type: Optional[str] = None) -> List[ParsedSection]:
        text = content or ""
        lines = text.splitlines()
        if not lines:
            return []

        template = get_template(doc_type)
        alias_map = build_alias_map(template)

        headings: List[tuple] = []
        for idx, line in enumerate(lines):
            match = _HEADING_RE.match(line.strip())
            if match:
                level = len(match.group(1))
                # H1 视为文档标题，不作为内容分节
                if level == 1:
                    continue
                headings.append((idx, level, match.group(2).strip()))

        # 无标题的纯文本：整体作为一个正文分节
        if not headings:
            return [ParsedSection(
                section_key="body",
                title="(正文)",
                level=1,
                start_line=1,
                end_line=max(1, len(lines)),
                content=text.strip(),
            )]

        sections: List[ParsedSection] = []
        for i, (line_idx, level, title) in enumerate(headings):
            end = len(lines) - 1
            for next_idx, next_level, _ in headings[i + 1:]:
                if next_level <= level:
                    end = next_idx - 1
                    break
            body = "\n".join(lines[line_idx + 1:end + 1]).strip()
            section_key = alias_map.get(title) or SectionParser._slug(title)
            sections.append(ParsedSection(
                section_key=section_key,
                title=title,
                level=level,
                start_line=line_idx + 1,
                end_line=end + 1,
                content=body,
            ))
        return sections

    @staticmethod
    def _slug(title: str) -> str:
        slug = re.sub(r"[^\w\u4e00-\u9fff]+", "_", (title or "").strip()).strip("_").lower()
        return slug or "section"
