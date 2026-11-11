"""知识文档的元信息与分节持久化。"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models import KnowledgeDocumentMeta, KnowledgeSection
from app.services.knowledge.section_parser import ParsedSection

logger = get_logger(__name__)


class KnowledgeSectionService:
    """文档分节的读写。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, doc_id: int) -> List[KnowledgeSection]:
        return (
            self.db.query(KnowledgeSection)
            .filter(KnowledgeSection.doc_id == doc_id)
            .order_by(KnowledgeSection.position.asc(), KnowledgeSection.start_line.asc())
            .all()
        )

    def get(self, doc_id: int, section_key: str) -> Optional[KnowledgeSection]:
        return (
            self.db.query(KnowledgeSection)
            .filter(
                KnowledgeSection.doc_id == doc_id,
                KnowledgeSection.section_key == section_key,
            )
            .first()
        )

    def replace(self, doc_id: int, sections: List[ParsedSection]) -> List[KnowledgeSection]:
        """用解析结果替换文档的全部分节。"""
        self.db.query(KnowledgeSection).filter(KnowledgeSection.doc_id == doc_id).delete()
        rows: List[KnowledgeSection] = []
        for position, sec in enumerate(sections):
            row = KnowledgeSection(
                doc_id=doc_id,
                section_key=sec.section_key,
                title=sec.title,
                level=sec.level,
                start_line=sec.start_line,
                end_line=sec.end_line,
                content=sec.content,
                position=position,
            )
            self.db.add(row)
            rows.append(row)
        self.db.commit()
        return rows

    @staticmethod
    def to_dict(row: KnowledgeSection) -> Dict[str, Any]:
        return {
            "id": row.id,
            "doc_id": row.doc_id,
            "section_key": row.section_key,
            "title": row.title,
            "level": row.level,
            "start_line": row.start_line,
            "end_line": row.end_line,
            "content": row.content,
        }


class KnowledgeDocumentMetaService:
    """文档元信息（模板、质量分、内容哈希、特征点）的读写。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, doc_id: int) -> Optional[KnowledgeDocumentMeta]:
        return (
            self.db.query(KnowledgeDocumentMeta)
            .filter(KnowledgeDocumentMeta.doc_id == doc_id)
            .first()
        )

    def upsert(self, doc_id: int, data: Dict[str, Any]) -> KnowledgeDocumentMeta:
        meta = self.get(doc_id)
        if meta is None:
            meta = KnowledgeDocumentMeta(doc_id=doc_id)
            self.db.add(meta)

        for field in ("template_key", "content_hash"):
            if field in data and data[field] is not None:
                setattr(meta, field, str(data[field]))

        if "quality_score" in data and data["quality_score"] is not None:
            meta.quality_score = float(data["quality_score"])

        if "features" in data and data["features"] is not None:
            meta.features = data["features"]

        meta.normalized_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(meta)
        return meta

    @staticmethod
    def compute_hash(content: str) -> str:
        return hashlib.sha256((content or "").encode("utf-8")).hexdigest()
