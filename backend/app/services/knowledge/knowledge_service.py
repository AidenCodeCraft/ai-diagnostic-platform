"""Knowledge document service — CRUD, search, and future RAG integration."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import KnowledgeDocument


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
            parent_id=data.get("parent_id"),
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
        parent_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        query = self.db.query(KnowledgeDocument)

        # 文件夹层级过滤
        if parent_id is not None:
            query = query.filter(KnowledgeDocument.parent_id == parent_id)
        else:
            # 默认只显示根级文档（parent_id IS NULL）
            query = query.filter(KnowledgeDocument.parent_id.is_(None))

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
        """Hybrid search: tries vector search (Milvus) first, falls back to keyword.

        Search pipeline:
        1. Try Milvus vector search (semantic)
        2. If no results, try keyword phrase search (exact match)
        3. If still no results, try token-based search (fuzzy match)

        Keyword search now supports token-based matching:
        first tries exact phrase ILIKE, then falls back to
        individual token OR-matching for better recall.
        """
        # Try vector search first (Milvus)
        try:
            from app.services.knowledge.vector_service import VectorService
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
                            "category": doc.category, "doc_type": doc.doc_type, "source": doc.source,
                            "relevance_score": round(vr.get("score", 0), 2),
                            "snippet": self._extract_snippet(doc.content, query_text),
                        })
                return {"items": results, "total": len(results), "page": page, "page_size": page_size}
        except Exception as exc:
            logger = __import__("app.core.logging_config", fromlist=["get_logger"]).get_logger(__name__)
            logger.debug("[KnowledgeService] Vector search unavailable, falling back to keyword: %s", exc)

        # Fallback: two-phase keyword search
        # Phase 1: exact phrase match
        items = self._keyword_search_phrase(query_text, page_size)
        if items:
            total = len(items)
            paged = items[:page_size]
            return {"items": paged, "total": total, "page": page, "page_size": page_size}

        # Phase 2: token-based OR match (分词回退)
        tokens = self._tokenize_query(query_text)
        if tokens:
            items = self._keyword_search_tokens(tokens, page_size)
            total = len(items)
            paged = items[:page_size]
            return {"items": paged, "total": total, "page": page, "page_size": page_size}

        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    def _keyword_search_phrase(self, query_text: str, limit: int) -> list:
        """Exact phrase ILIKE search."""
        if not query_text.strip():
            return []
        pattern = f"%{query_text}%"
        docs = (
            self.db.query(KnowledgeDocument)
            .filter(
                KnowledgeDocument.status == "active",
                or_(
                    KnowledgeDocument.title.ilike(pattern),
                    KnowledgeDocument.content.ilike(pattern),
                ),
            )
            .order_by(KnowledgeDocument.updated_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": doc.id, "title": doc.title,
                "category": doc.category, "doc_type": doc.doc_type, "source": doc.source,
                "relevance_score": round(self._relevance_score(doc, query_text), 2),
                "snippet": self._extract_snippet(doc.content, query_text),
            }
            for doc in docs
        ]

    def _keyword_search_tokens(self, tokens: list[str], limit: int) -> list:
        """Token-level OR search — each token matched independently."""
        if not tokens:
            return []
        # Build OR conditions: title ILIKE '%token1%' OR title ILIKE '%token2%' ...
        title_conditions = [
            KnowledgeDocument.title.ilike(f"%{t}%") for t in tokens
        ]
        content_conditions = [
            KnowledgeDocument.content.ilike(f"%{t}%") for t in tokens
        ]
        docs = (
            self.db.query(KnowledgeDocument)
            .filter(
                KnowledgeDocument.status == "active",
                or_(or_(*title_conditions), or_(*content_conditions)),
            )
            .order_by(KnowledgeDocument.updated_at.desc())
            .limit(limit)
            .all()
        )
        # Re-score based on how many tokens matched
        query_lower = " ".join(tokens).lower()
        return [
            {
                "id": doc.id, "title": doc.title,
                "category": doc.category, "doc_type": doc.doc_type, "source": doc.source,
                "relevance_score": round(self._token_relevance(doc, tokens), 2),
                "snippet": self._extract_snippet(doc.content, tokens[0]) if tokens else "",
            }
            for doc in docs
        ]

    @staticmethod
    def _tokenize_query(query_text: str) -> list[str]:
        """Split query into meaningful tokens for individual matching.

        Chinese: extract 2-4 character n-grams and full phrases.
        English: split by whitespace and punctuation.
        """
        tokens: set[str] = set()

        # Extract Chinese phrases (2-4 chars) — most meaningful for search
        cn_chars = re.findall(r"[\u4e00-\u9fff]+", query_text)
        for phrase in cn_chars:
            if len(phrase) >= 2:
                tokens.add(phrase)  # full Chinese phrase
                # Also add 2-3 char windows
                if len(phrase) >= 2:
                    for i in range(len(phrase) - 1):
                        tokens.add(phrase[i:i + 2])
                    if len(phrase) >= 3:
                        for i in range(len(phrase) - 2):
                            tokens.add(phrase[i:i + 3])

        # Extract English/technical tokens
        en_tokens = re.findall(r"[a-zA-Z_]\w{1,}", query_text)
        for t in en_tokens:
            if len(t) >= 2:
                tokens.add(t)

        # Filter common stop words
        stop_words = {"的", "了", "在", "是", "我", "有", "和", "就", "不",
                       "人", "都", "一", "个", "上", "也", "很", "到", "说",
                       "要", "去", "你", "会", "着", "没有", "看", "好", "自己"}
        tokens = {t for t in tokens if t.lower() not in stop_words and len(t) >= 2}

        # Sort: longer tokens first (more specific)
        return sorted(tokens, key=len, reverse=True)

    @staticmethod
    def _token_relevance(doc: KnowledgeDocument, tokens: list[str]) -> float:
        """Score based on how many tokens match in title vs content."""
        title_lower = (doc.title or "").lower()
        content_lower = (doc.content or "").lower()
        total_tokens = len(tokens)
        if total_tokens == 0:
            return 0
        title_hits = sum(1 for t in tokens if t.lower() in title_lower)
        content_hits = sum(1 for t in tokens if t.lower() in content_lower)
        return min(1.0, (title_hits * 0.4 + content_hits * 0.15) / max(1, total_tokens))

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, doc_id: int, data: Dict[str, Any]) -> KnowledgeDocument:
        doc = self.get(doc_id)
        for field in ("title", "content", "category", "source", "doc_type", "project_id", "status", "is_pinned"):
            if field in data and data[field] is not None:
                setattr(doc, field, data[field])
        self.db.commit()
        self.db.refresh(doc)
        return doc

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, doc_id: int) -> None:
        """Delete a document and all its descendants recursively.

        Raises ValueError if the document does not exist.
        Handles folders with child documents by deleting children first.
        """
        doc = self.get(doc_id)
        self._delete_children(doc_id)
        self.db.flush()  # 确保子节点删除已写入数据库，避免 FK 约束冲突
        self.db.delete(doc)
        self.db.commit()

    def _delete_children(self, parent_id: int) -> None:
        """Recursively delete all child documents of a given parent."""
        children = (
            self.db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.parent_id == parent_id)
            .all()
        )
        for child in children:
            self._delete_children(child.id)  # 递归删除孙节点
            self.db.delete(child)
            self.db.flush()  # 每个子节点立即 flush，确保递归删除时序正确

    # ------------------------------------------------------------------
    # Tree
    # ------------------------------------------------------------------

    def get_tree(self) -> List[Dict[str, Any]]:
        """Build full folder/document tree from flat records."""
        docs = (
            self.db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.status == "active")
            .order_by(KnowledgeDocument.doc_type.desc(), KnowledgeDocument.updated_at.desc())
            .all()
        )

        doc_map: Dict[int, Dict[str, Any]] = {}
        roots: List[Dict[str, Any]] = []

        for d in docs:
            node = {
                "id": d.id,
                "title": d.title,
                "doc_type": d.doc_type,
                "category": d.category,
                "updated_at": d.updated_at.isoformat() if d.updated_at else None,
                "children": [],
            }
            doc_map[d.id] = node

        for d in docs:
            node = doc_map[d.id]
            if d.parent_id and d.parent_id in doc_map:
                doc_map[d.parent_id]["children"].append(node)
            else:
                roots.append(node)

        return roots

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
    def _extract_snippet(content: str, query: str, window: int = 300) -> str:
        """提取包含搜索关键词的上下文片段。

        优先匹配完整搜索词，如果找不到则尝试匹配搜索词中的
        数字/字母数字 token（如 "1078"、"CJT1078"）。
        """
        if not content or not query:
            return content[:300] if content else ""

        idx = content.lower().find(query.lower())

        # 完整匹配失败 → 尝试匹配数字/字母数字 token
        if idx == -1:
            tokens = re.findall(r'[A-Za-z]*\d+[A-Za-z]*', query)
            for token in tokens:
                idx = content.lower().find(token.lower())
                if idx != -1:
                    break

        # 所有匹配失败 → 返回开头
        if idx == -1:
            return content[:300]

        start = max(0, idx - window // 2)
        end = min(len(content), idx + window // 2)
        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        return snippet
