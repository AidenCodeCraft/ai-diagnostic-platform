"""知识库校验 — 必填章节、正则、信息量、质量分。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.services.knowledge.section_parser import ParsedSection
from app.services.knowledge.templates import (
    LEVEL_RECOMMENDED,
    LEVEL_REQUIRED,
    get_template,
)

ERROR = "error"
WARN = "warn"


@dataclass
class Issue:
    code: str
    level: str
    message: str
    section_key: str = ""

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "level": self.level,
            "message": self.message,
            "section_key": self.section_key,
        }


@dataclass
class ValidationResult:
    issues: List[Issue] = field(default_factory=list)
    quality_score: float = 0.0
    status_hint: str = "active"

    @property
    def has_errors(self) -> bool:
        return any(i.level == ERROR for i in self.issues)


class Validator:
    """按模板校验分节与诊断剧本草稿。"""

    def validate(
        self,
        doc_type: Optional[str],
        sections: List[ParsedSection],
        profile_draft: Dict[str, object],
        image_count: int = 0,
        feedback_ratio: Optional[float] = None,
    ) -> ValidationResult:
        template = get_template(doc_type)
        by_key = {s.section_key: s for s in sections}
        if template is None:
            # 自由文档（note / manual / 未知类型）：仅做基础校验，不强制模板
            has_content = any((s.content or "").strip() for s in sections)
            issues = [] if has_content else [Issue("EMPTY_CONTENT", WARN, "内容为空")]
            return ValidationResult(
                issues=issues,
                quality_score=40.0 if has_content else 0.0,
                status_hint="active",
            )

        # 纯文本 / 无章节内容：不强制模板（前端可先「一键格式化」），仅提示
        structured = any(s.level == 2 for s in sections)
        if not structured:
            has_content = any((s.content or "").strip() for s in sections)
            return ValidationResult(
                issues=[Issue("UNSTRUCTURED_CONTENT", WARN, "内容未按模板分节，建议先使用「一键格式化」")],
                quality_score=40.0 if has_content else 0.0,
                status_hint="active",
            )

        issues: List[Issue] = []
        required = [s for s in template.sections if s.level == LEVEL_REQUIRED]
        recommended = [s for s in template.sections if s.level == LEVEL_RECOMMENDED]

        for spec in required:
            sec = by_key.get(spec.key)
            if sec is None:
                issues.append(Issue("MISSING_REQUIRED_SECTION", ERROR, f"缺少必填章节：{spec.title}", spec.key))
            elif not (sec.content or "").strip():
                issues.append(Issue("EMPTY_REQUIRED_SECTION", ERROR, f"必填章节为空：{spec.title}", spec.key))

        for spec in recommended:
            sec = by_key.get(spec.key)
            if sec is None or not (sec.content or "").strip():
                issues.append(Issue("MISSING_RECOMMENDED_SECTION", WARN, f"建议补充章节：{spec.title}", spec.key))

        patterns = [str(p) for p in (profile_draft.get("log_patterns") or [])]
        invalid = [p for p in patterns if not self._valid_regex(p)]
        if invalid:
            issues.append(Issue("INVALID_REGEX", ERROR, "正则无法编译：" + "；".join(invalid), "log_signature"))

        log_present = bool(profile_draft.get("log_keywords") or profile_draft.get("log_patterns"))
        if doc_type == "case" and not log_present:
            issues.append(Issue("NO_LOG_SIGNATURE", WARN, "缺少日志特征，该条目将无法参与日志定位", "log_signature"))

        low_info = [
            spec.title for spec in required
            if by_key.get(spec.key) and len((by_key[spec.key].content or "").strip()) < 10
        ]
        if low_info:
            issues.append(Issue("LOW_INFO", WARN, "信息量不足：" + "、".join(low_info)))

        quality = self._quality(template, by_key, profile_draft, doc_type, image_count, feedback_ratio)
        status_hint = "draft" if any(i.level == ERROR for i in issues) else "active"
        return ValidationResult(issues=issues, quality_score=quality, status_hint=status_hint)

    @staticmethod
    def _valid_regex(pattern: str) -> bool:
        try:
            re.compile(pattern)
            return True
        except re.error:
            return False

    def _quality(
        self,
        template,
        by_key: Dict[str, ParsedSection],
        profile_draft: Dict[str, object],
        doc_type: Optional[str],
        image_count: int,
        feedback_ratio: Optional[float],
    ) -> float:
        required = [s for s in template.sections if s.level == LEVEL_REQUIRED]
        if required:
            present = sum(
                1 for spec in required
                if by_key.get(spec.key) and (by_key[spec.key].content or "").strip()
            )
            structure = 40.0 * present / len(required)
        else:
            structure = 40.0

        log_present = bool(profile_draft.get("log_keywords") or profile_draft.get("log_patterns"))
        if doc_type in ("code_logic", "knowledge"):
            log_score = 20.0
        else:
            log_score = 20.0 if log_present else 0.0

        patterns = [str(p) for p in (profile_draft.get("log_patterns") or [])]
        if doc_type in ("code_logic", "knowledge"):
            regex_score = 10.0
        elif not patterns:
            regex_score = 10.0 if doc_type == "faq" else 0.0
        else:
            regex_score = 10.0 if all(self._valid_regex(p) for p in patterns) else 0.0

        info_score = 10.0
        for spec in required:
            sec = by_key.get(spec.key)
            if sec is None or len((sec.content or "").strip()) < 20:
                info_score = 0.0
                break

        image_score = 10.0 if image_count > 0 else 0.0
        feedback_score = 10.0 * (
            max(0.0, min(1.0, feedback_ratio)) if feedback_ratio is not None else 0.0
        )

        return round(
            structure + log_score + regex_score + info_score + image_score + feedback_score,
            1,
        )
