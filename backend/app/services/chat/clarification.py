"""意图澄清 — 当用户描述宽泛或缺失关键槽位时，生成结构化反问。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models import KnowledgeDocument, KnowledgeDocumentMeta

logger = get_logger(__name__)

# 槽位定义：slot → 特征点 key 候选
SLOT_DEFS = [
    {
        "slot": "device",
        "label": "设备型号",
        "feature_keys": ("设备类型", "设备", "型号", "device"),
        "hint": "用于匹配同类案例",
    },
    {
        "slot": "city",
        "label": "现场城市",
        "feature_keys": ("城市", "city"),
        "hint": "用于匹配同现场案例",
    },
    {
        "slot": "version",
        "label": "版本",
        "feature_keys": ("版本", "version"),
        "hint": "用于匹配同版本案例",
    },
]

MAX_QUESTIONS = 2


@dataclass
class ClarificationQuestion:
    slot: str
    label: str
    options: List[str] = field(default_factory=list)
    hint: str = ""

    def to_dict(self) -> dict:
        return {
            "slot": self.slot,
            "label": self.label,
            "options": self.options,
            "hint": self.hint,
        }


class ClarificationService:
    """基于知识库特征点生成「需要补充哪些信息」的反问。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def slot_options(self) -> Dict[str, List[str]]:
        """从知识库 meta.features 汇总各槽位候选值。"""
        try:
            rows = (
                self.db.query(KnowledgeDocumentMeta.features)
                .join(KnowledgeDocument, KnowledgeDocumentMeta.doc_id == KnowledgeDocument.id)
                .filter(KnowledgeDocument.status == "active")
                .all()
            )
        except Exception as exc:
            logger.debug("[Clarification] slot_options failed: %s", exc)
            return {}
        collected: Dict[str, List[str]] = {}
        for (features,) in rows:
            if not isinstance(features, dict):
                continue
            for spec in SLOT_DEFS:
                for key in spec["feature_keys"]:
                    value = features.get(key)
                    if isinstance(value, str) and value.strip():
                        collected.setdefault(spec["slot"], []).append(value.strip())
        return {slot: list(dict.fromkeys(values)) for slot, values in collected.items()}

    def analyze(self, query: str) -> List[ClarificationQuestion]:
        """返回需要补充的槽位问题；无需澄清时返回空列表。"""
        text = (query or "").strip()
        if not text:
            return []
        options = self.slot_options()
        questions: List[ClarificationQuestion] = []
        for spec in SLOT_DEFS:
            values = options.get(spec["slot"], [])
            if len(values) < 2:
                continue
            if self._mentioned(text, values):
                continue
            questions.append(ClarificationQuestion(
                slot=spec["slot"],
                label=spec["label"],
                options=values[:8],
                hint=spec["hint"],
            ))
            if len(questions) >= MAX_QUESTIONS:
                break
        return questions

    @staticmethod
    def _mentioned(text: str, values: List[str]) -> bool:
        lower = text.lower()
        return any(value.lower() in lower for value in values)


def build_clarification_reply(questions: List[ClarificationQuestion]) -> str:
    """把澄清问题渲染成一段面向用户的引导文本。"""
    lines = ["为了更准确地定位问题，请补充以下信息："]
    for question in questions:
        options = "、".join(question.options) if question.options else ""
        hint = f"（{question.hint}）" if question.hint else ""
        line = f"- **{question.label}**{hint}"
        if options:
            line += f"：可选 {options}"
        lines.append(line)
    lines.append("补充后我会继续分析。")
    return "\n".join(lines)
