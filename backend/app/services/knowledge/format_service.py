"""知识库格式化服务 — 规范化 + 校验的统一入口（不落库）。"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from app.services.knowledge.normalizer import Normalizer
from app.services.knowledge.templates import get_template, list_templates
from app.services.knowledge.validator import Validator

_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")


class KnowledgeFormatService:
    """供前端「AI润色」「分屏预览」与后端入库校验统一复用。"""

    def preview(
        self,
        content: str,
        doc_type: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        result = Normalizer().normalize(content, doc_type)
        image_count = len(_IMAGE_RE.findall(result.normalized_content))
        validation = Validator().validate(
            doc_type, result.sections, result.profile_draft, image_count=image_count,
        )
        template = get_template(doc_type)
        return {
            "title": title or "",
            "doc_type": doc_type,
            "normalized_content": result.normalized_content,
            "sections": [s.to_dict() for s in result.sections],
            "profile_draft": result.profile_draft,
            "features": result.features,
            "suggested_keywords": result.suggested_keywords,
            "notes": result.notes,
            "issues": [i.to_dict() for i in validation.issues],
            "quality_score": validation.quality_score,
            "status_hint": validation.status_hint,
            "template": (
                {
                    "doc_type": template.doc_type,
                    "name": template.name,
                    "free_form": template.free_form,
                    "sections": [
                        {"key": s.key, "title": s.title, "level": s.level}
                        for s in template.sections
                    ],
                }
                if template else None
            ),
        }

    @staticmethod
    def list_templates() -> list:
        return list_templates()
