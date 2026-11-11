"""知识库「诊断剧本」服务 — 结构化诊断信息的 CRUD 与自进化候选审核。

职责：
  1. profile 的读取 / 新建 / 更新（与知识条目 1:1）
  2. 字段归一化（list 字段兼容 list 或换行/逗号分隔字符串）
  3. 自进化候选：list_drafts / approve / reject
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models import KnowledgeDiagnosisProfile, KnowledgeDocument

logger = get_logger(__name__)

# 允许的字段
_PROFILE_TEXT_FIELDS = (
    "symptom", "environment", "expected", "root_cause", "solution",
)
_PROFILE_LIST_FIELDS = ("log_keywords", "log_patterns", "negative_patterns")
_VALID_STATUS = {"draft", "active", "archived"}
_VALID_SOURCE = {"manual", "ai_candidate"}


def _normalize_list(value: Any) -> List[str]:
    """把 list / 换行或逗号分隔字符串 / None 归一化为去空 list。"""
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.replace("，", ",").replace("\r", "\n").split("\n")
        items: List[str] = []
        for chunk in parts:
            for sub in chunk.split(","):
                sub = sub.strip()
                if sub:
                    items.append(sub)
        return items
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


class KnowledgeProfileService:
    """知识库诊断剧本服务。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get(self, doc_id: int) -> Optional[KnowledgeDiagnosisProfile]:
        return (
            self.db.query(KnowledgeDiagnosisProfile)
            .filter(KnowledgeDiagnosisProfile.doc_id == doc_id)
            .first()
        )

    def get_by_id(self, profile_id: int) -> KnowledgeDiagnosisProfile:
        profile = (
            self.db.query(KnowledgeDiagnosisProfile)
            .filter(KnowledgeDiagnosisProfile.id == profile_id)
            .first()
        )
        if not profile:
            raise ValueError("diagnosis profile not found")
        return profile

    def list_drafts(self) -> List[KnowledgeDiagnosisProfile]:
        return (
            self.db.query(KnowledgeDiagnosisProfile)
            .filter(KnowledgeDiagnosisProfile.status == "draft")
            .order_by(KnowledgeDiagnosisProfile.created_at.desc())
            .all()
        )

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def upsert(self, doc_id: int, data: Dict[str, Any]) -> KnowledgeDiagnosisProfile:
        """新建或更新某知识条目的诊断剧本。"""
        doc = (
            self.db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.id == doc_id)
            .first()
        )
        if not doc:
            raise ValueError("knowledge document not found")

        profile = self.get(doc_id)
        if profile is None:
            profile = KnowledgeDiagnosisProfile(doc_id=doc_id)
            self.db.add(profile)

        for field in _PROFILE_TEXT_FIELDS:
            if field in data and data[field] is not None:
                setattr(profile, field, str(data[field]).strip())

        for field in _PROFILE_LIST_FIELDS:
            if field in data and data[field] is not None:
                setattr(profile, field, _normalize_list(data[field]))

        if data.get("confidence") is not None:
            try:
                confidence = float(data["confidence"])
            except (TypeError, ValueError):
                confidence = 0.8
            profile.confidence = max(0.0, min(1.0, confidence))

        if data.get("status"):
            status = str(data["status"]).strip()
            profile.status = status if status in _VALID_STATUS else "active"

        if data.get("source"):
            source = str(data["source"]).strip()
            profile.source = source if source in _VALID_SOURCE else "manual"

        # 首次创建时补齐默认值
        if getattr(profile, "status", None) is None:
            profile.status = "active"
        if getattr(profile, "source", None) is None:
            profile.source = "manual"
        if getattr(profile, "confidence", None) is None:
            profile.confidence = 0.8

        self.db.commit()
        self.db.refresh(profile)
        logger.info("[ProfileService] upserted doc=%d profile=%s", doc_id, profile.id)
        return profile

    # ------------------------------------------------------------------
    # 自进化候选审核
    # ------------------------------------------------------------------

    def approve(self, profile_id: int) -> KnowledgeDiagnosisProfile:
        profile = self.get_by_id(profile_id)
        profile.status = "active"
        profile.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def reject(self, profile_id: int) -> None:
        profile = self.get_by_id(profile_id)
        self.db.delete(profile)
        self.db.commit()

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    @staticmethod
    def to_dict(profile: KnowledgeDiagnosisProfile) -> Dict[str, Any]:
        return {
            "id": profile.id,
            "doc_id": profile.doc_id,
            "symptom": profile.symptom,
            "environment": profile.environment,
            "log_keywords": profile.log_keywords or [],
            "log_patterns": profile.log_patterns or [],
            "negative_patterns": profile.negative_patterns or [],
            "expected": profile.expected,
            "root_cause": profile.root_cause,
            "solution": profile.solution,
            "confidence": profile.confidence if profile.confidence is not None else 0.8,
            "status": profile.status or "active",
            "source": profile.source or "manual",
        }
