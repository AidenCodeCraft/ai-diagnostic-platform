"""Knowledge document service — CRUD, search, and future RAG integration."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgeDocument


class KnowledgeService:
    """Service for managing knowledge documents with keyword-based search."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, data: Dict[str, Any]) -> KnowledgeDocument:
        doc = KnowledgeDocument(
            title=data["title"],
            content=data["content"],
            category=data.get("category"),
            source=data.get("source"),
            doc_type=data.get("doc_type", "manual"),
            project_id=data.get("project_id"),
            status="active",
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, doc_id: int) -> KnowledgeDocument:
        doc = self.db.query(KnowledgeDocument).filter(
            KnowledgeDocument.id == doc_id
        ).first()
        if not doc:
            raise ValueError("knowledge document not found")
        return doc

    def list(
        self,
        page: int = 1,
        page_size: int = 20,
        category: Optional[str] = None,
        doc_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        query = self.db.query(KnowledgeDocument)

        if category:
            query = query.filter(KnowledgeDocument.category == category)
        if doc_type:
            query = query.filter(KnowledgeDocument.doc_type == doc_type)
        if status:
            query = query.filter(KnowledgeDocument.status == status)
        else:
            query = query.filter(KnowledgeDocument.status == "active")

        total = query.count()
        items = (
            query.order_by(KnowledgeDocument.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def search(
        self,
        query_text: str,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """Hybrid search: tries vector search first, falls back to keyword.

        Vector search via Milvus (production) or FAISS (development).
        Keyword search via SQL ILIKE as final fallback.
        """
        # Try vector search first
        from app.services.vector_service import VectorService
        vector = VectorService()
        vector_results = vector.search(query_text, top_k=page_size)

        if vector_results:
            doc_ids = [r["id"] for r in vector_results]
            docs = self.db.query(KnowledgeDocument).filter(
                KnowledgeDocument.id.in_(doc_ids),
                KnowledgeDocument.status == "active",
            ).all()
            doc_map = {d.id: d for d in docs}
            results = []
            for vr in vector_results:
                doc = doc_map.get(vr["id"])
                if doc:
                    results.append({
                        "id": doc.id, "title": doc.title,
                        "category": doc.category, "doc_type": doc.doc_type,
                        "relevance_score": round(vr.get("score", 0), 2),
                        "snippet": self._extract_snippet(doc.content, query_text),
                    })
            return {"items": results, "total": len(results), "page": page, "page_size": page_size}

        # Fallback to keyword search
        pattern = f"%{query_text}%"
        base_query = self.db.query(KnowledgeDocument).filter(
            KnowledgeDocument.status == "active",
            or_(
                KnowledgeDocument.title.ilike(pattern),
                KnowledgeDocument.content.ilike(pattern),
            ),
        )
        total = base_query.count()
        items = base_query.order_by(KnowledgeDocument.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        results = []
        for doc in items:
            score = self._relevance_score(doc, query_text)
            results.append({
                "id": doc.id, "title": doc.title,
                "category": doc.category, "doc_type": doc.doc_type,
                "relevance_score": round(score, 2),
                "snippet": self._extract_snippet(doc.content, query_text),
            })
        return {"items": results, "total": total, "page": page, "page_size": page_size}

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, doc_id: int, data: Dict[str, Any]) -> KnowledgeDocument:
        doc = self.get(doc_id)
        for field in ("title", "content", "category", "source", "doc_type", "project_id", "status"):
            if field in data and data[field] is not None:
                setattr(doc, field, data[field])
        self.db.commit()
        self.db.refresh(doc)
        return doc

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, doc_id: int) -> None:
        doc = self.get(doc_id)
        self.db.delete(doc)
        self.db.commit()

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------

    def list_categories(self) -> List[str]:
        rows = (
            self.db.query(KnowledgeDocument.category)
            .filter(KnowledgeDocument.status == "active")
            .filter(KnowledgeDocument.category.isnot(None))
            .distinct()
            .all()
        )
        return sorted([r[0] for r in rows if r[0]])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _relevance_score(doc: KnowledgeDocument, query: str) -> float:
        query_lower = query.lower()
        title_hits = doc.title.lower().count(query_lower) if doc.title else 0
        content_hits = doc.content.lower().count(query_lower) if doc.content else 0
        # Title matches weighted 3x vs content
        return min(1.0, (title_hits * 0.3 + content_hits * 0.1))

    @staticmethod
    def _extract_snippet(content: str, query: str, window: int = 80) -> str:
        if not content or not query:
            return content[:200] if content else ""
        idx = content.lower().find(query.lower())
        if idx == -1:
            return content[:200]
        start = max(0, idx - window // 2)
        end = min(len(content), idx + len(query) + window // 2)
        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        return snippet
