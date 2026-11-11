"""知识库规范化 — 把自由内容整理成模板结构（确定性、幂等）。

职责：
  1. 清理空白/空行，标题层级归一（H1 标题、H2 章节、H3 子节）
  2. 按模板顺序重排 H2 章节（未知章节保留在后）
  3. 解析「特征点」（key: value）与「日志特征」（关键词/正则/排除正则）
  4. 生成诊断剧本草稿；日志特征缺失时抽取候选关键词
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.services.knowledge.section_parser import ParsedSection, SectionParser
from app.services.knowledge.templates import build_alias_map, get_template

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^[-*+]\s+(.+)$")

_KEYWORD_HEADINGS = ("关键词", "关键字", "关键词列表")
_PATTERN_HEADINGS = ("正则", "正则表达式", "匹配正则")
_NEGATIVE_HEADINGS = ("排除正则", "排除", "负向正则")


@dataclass
class NormalizeResult:
    normalized_content: str = ""
    sections: List[ParsedSection] = field(default_factory=list)
    profile_draft: Dict[str, object] = field(default_factory=dict)
    features: Dict[str, str] = field(default_factory=dict)
    suggested_keywords: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


class Normalizer:
    """确定性规范化（同一内容多次规范化结果一致）。"""

    def normalize(self, content: str, doc_type: Optional[str] = None) -> NormalizeResult:
        template = get_template(doc_type)
        lines = self._clean(content)

        title_line: Optional[str] = None
        body_lines = list(lines)
        if body_lines and body_lines[0].startswith("# ") and not body_lines[0].startswith("## "):
            title_line = body_lines[0]
            body_lines = body_lines[1:]

        blocks = self._split_h2_blocks(body_lines)
        if template is not None and not template.free_form and blocks:
            blocks = self._reorder(blocks, template)

        body = self._join_blocks(blocks)
        if title_line:
            body = title_line + "\n\n" + body
        body = re.sub(r"\n{3,}", "\n\n", body).strip()

        sections = SectionParser.parse(body, doc_type)
        by_key = {s.section_key: s for s in sections}

        features = self._extract_features(self._section_content(by_key, "features"))
        log = self._parse_log_signature(self._section_content(by_key, "log_signature"))
        profile = self._build_profile(doc_type, by_key, features, log)
        suggested: List[str] = []
        if doc_type == "case" and not (log["log_keywords"] or log["log_patterns"]):
            suggested = self._suggest_keywords(by_key)

        return NormalizeResult(
            normalized_content=body,
            sections=sections,
            profile_draft=profile,
            features=features,
            suggested_keywords=suggested,
        )

    # ------------------------------------------------------------------
    # 清理与分块
    # ------------------------------------------------------------------

    @staticmethod
    def _clean(content: str) -> List[str]:
        raw = (content or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = [ln.rstrip() for ln in raw.split("\n")]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        out: List[str] = []
        blank = False
        for ln in lines:
            if not ln.strip():
                if blank:
                    continue
                blank = True
                out.append("")
            else:
                blank = False
                out.append(ln)
        return out

    @staticmethod
    def _split_h2_blocks(lines: List[str]) -> List[Dict[str, object]]:
        blocks: List[Dict[str, object]] = []
        current: Dict[str, object] = {"title": "", "lines": [], "order": 0}
        order = 0
        for line in lines:
            match = _HEADING_RE.match(line.strip())
            if match and len(match.group(1)) == 2:
                if current["title"] or any(str(x).strip() for x in current["lines"]):
                    blocks.append(current)
                current = {"title": match.group(2).strip(), "lines": [line], "order": order}
                order += 1
            else:
                current["lines"].append(line)
        if current["title"] or any(str(x).strip() for x in current["lines"]):
            blocks.append(current)
        return blocks

    @staticmethod
    def _reorder(blocks: List[Dict[str, object]], template) -> List[Dict[str, object]]:
        alias_map = build_alias_map(template)
        order = {spec.key: i for i, spec in enumerate(template.sections)}

        def sort_key(block: Dict[str, object]):
            title = str(block.get("title") or "")
            key = alias_map.get(title)
            if key is not None and key in order:
                return (order[key], int(block["order"]))
            return (len(order) + 1, int(block["order"]))

        return sorted(blocks, key=sort_key)

    @staticmethod
    def _join_blocks(blocks: List[Dict[str, object]]) -> str:
        parts = []
        for block in blocks:
            text = "\n".join(str(x) for x in block["lines"]).strip()
            if text:
                parts.append(text)
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # 特征点 / 日志特征 / 剧本
    # ------------------------------------------------------------------

    @staticmethod
    def _section_content(by_key: Dict[str, ParsedSection], key: str) -> str:
        section = by_key.get(key)
        return (section.content or "").strip() if section else ""

    @staticmethod
    def _extract_features(text: str) -> Dict[str, str]:
        features: Dict[str, str] = {}
        for line in (text or "").splitlines():
            line = re.sub(r"^\s*[-*+]\s+", "", line).strip()
            match = re.match(r"^([^:：]{1,20})\s*[:：]\s*(.+?)\s*$", line)
            if match:
                key = match.group(1).strip()
                value = match.group(2).strip()
                if key and value:
                    features[key] = value
        return features

    @staticmethod
    def _parse_log_signature(text: str) -> Dict[str, List[str]]:
        keywords: List[str] = []
        patterns: List[str] = []
        negatives: List[str] = []
        current = "keywords"
        for line in (text or "").splitlines():
            stripped = line.strip()
            heading = _HEADING_RE.match(stripped)
            if heading:
                title = heading.group(2).strip()
                if title in _KEYWORD_HEADINGS:
                    current = "keywords"
                elif title in _PATTERN_HEADINGS:
                    current = "patterns"
                elif title in _NEGATIVE_HEADINGS:
                    current = "negative"
                continue
            bullet = _BULLET_RE.match(stripped)
            if bullet:
                item = bullet.group(1).strip()
                if not item:
                    continue
                if current == "patterns":
                    patterns.append(item)
                elif current == "negative":
                    negatives.append(item)
                else:
                    keywords.append(item)
        return {"log_keywords": keywords, "log_patterns": patterns, "negative_patterns": negatives}

    def _build_profile(
        self,
        doc_type: Optional[str],
        by_key: Dict[str, ParsedSection],
        features: Dict[str, str],
        log: Dict[str, List[str]],
    ) -> Dict[str, object]:
        profile: Dict[str, object] = {
            "symptom": "",
            "environment": "",
            "log_keywords": list(log["log_keywords"]),
            "log_patterns": list(log["log_patterns"]),
            "negative_patterns": list(log["negative_patterns"]),
            "expected": "",
            "root_cause": "",
            "solution": "",
        }
        if doc_type == "case":
            profile["symptom"] = self._section_content(by_key, "symptom")
            profile["root_cause"] = self._section_content(by_key, "root_cause")
            profile["solution"] = self._section_content(by_key, "solution")
            feature_text = self._section_content(by_key, "features")
            profile["environment"] = feature_text or "; ".join(
                f"{k}: {v}" for k, v in features.items()
            )
        elif doc_type == "faq":
            analysis = self._section_content(by_key, "analysis")
            profile["symptom"] = self._section_content(by_key, "symptom")
            profile["root_cause"] = analysis
            profile["solution"] = analysis
            keyword_text = self._section_content(by_key, "keywords")
            if keyword_text:
                profile["log_keywords"] = self._parse_keyword_list(keyword_text)
        return profile

    @staticmethod
    def _parse_keyword_list(text: str) -> List[str]:
        items: List[str] = []
        for line in text.splitlines():
            line = re.sub(r"^\s*[-*+]\s+", "", line).strip()
            if not line:
                continue
            for part in re.split(r"[,，;；、\s]+", line):
                part = part.strip()
                if part:
                    items.append(part)
        return list(dict.fromkeys(items))

    def _suggest_keywords(self, by_key: Dict[str, ParsedSection]) -> List[str]:
        text = " ".join([
            self._section_content(by_key, "symptom"),
            self._section_content(by_key, "root_cause"),
        ])
        candidates = re.findall(r"[A-Za-z]*\d+[A-Za-z]*", text)
        candidates += re.findall(r"[“\"'‘]([^”\"'’\n]{2,20})[”\"'’]", text)
        result: List[str] = []
        for item in candidates:
            item = item.strip()
            if len(item) >= 2 and item not in result:
                result.append(item)
        return result[:10]
