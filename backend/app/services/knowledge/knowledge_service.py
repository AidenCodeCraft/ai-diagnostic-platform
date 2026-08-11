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
                doc_map = {int(d.id): d for d in docs}  # type: ignore[arg-type]
                results = []
                for vr in vector_results:
                    doc = doc_map.get(vr["id"])
                    if doc:
                        results.append({
                            "id": doc.id, "title": doc.title,
                            "category": doc.category, "doc_type": doc.doc_type, "source": doc.source,
                            "relevance_score": round(vr.get("score", 0), 2),
                            "snippet": self._extract_snippet(str(doc.content), query_text),
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

    def keyword_search(
        self,
        query_text: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """纯关键词搜索（不做向量检索）——供混合检索调用。

        两阶段：先完整短语匹配，无结果则分词 OR 匹配。
        """
        items = self._keyword_search_phrase(query_text, limit)
        if items:
            return items
        tokens = self._tokenize_query(query_text)
        if tokens:
            return self._keyword_search_tokens(tokens, limit)
        return []

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
                "snippet": self._extract_snippet(str(doc.content), query_text),
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
            .limit(limit * 4)  # 先多取候选，按相关度排序后再截断
            .all()
        )
        # Re-score based on how many tokens matched
        scored = [
            {
                "id": doc.id, "title": doc.title,
                "category": doc.category, "doc_type": doc.doc_type, "source": doc.source,
                "relevance_score": round(self._token_relevance(doc, tokens), 2),
                "snippet": self._extract_snippet(str(doc.content), tokens[0]) if tokens else "",
            }
            for doc in docs
        ]
        scored.sort(key=lambda x: x["relevance_score"], reverse=True)
        return scored[:limit]

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

        # Extract English/technical tokens (ASCII 字母数字，含纯数字如 "1078"、"808")
        # 注意不能用 \w——Python re 的 \w 会匹配中文字符，导致整句被吞成一个 token
        en_tokens = re.findall(r"[A-Za-z0-9_]{2,}", query_text)
        for t in en_tokens:
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
        """Score based on how many tokens match in title vs content.

        含数字的 token（如 "1078"、"CJT1078"）是强区分度关键词，
        命中时给予 3 倍权重，避免被大量中文 n-gram 噪声稀释。
        """
        title_lower = (doc.title or "").lower()
        content_lower = (doc.content or "").lower()
        if not tokens:
            return 0

        def _weight(token: str) -> float:
            return 3.0 if re.search(r"\d", token) else 1.0

        total_weight = sum(_weight(t) for t in tokens)
        title_hits = sum(_weight(t) for t in tokens if t.lower() in title_lower)
        content_hits = sum(_weight(t) for t in tokens if t.lower() in content_lower)
        return min(1.0, (title_hits * 0.4 + content_hits * 0.15) / max(1.0, total_weight))

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
            self._delete_children(int(child.id))  # type: ignore[arg-type]  # 递归删除孙节点
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
            updated_at_raw = d.updated_at  # type: ignore[assignment]
            node = {
                "id": d.id,
                "title": d.title,
                "doc_type": d.doc_type,
                "category": d.category,
                "updated_at": updated_at_raw.isoformat() if updated_at_raw is not None else None,
                "children": [],
            }
            doc_map[int(d.id)] = node  # type: ignore[arg-type]

        for d in docs:
            node = doc_map[int(d.id)]  # type: ignore[arg-type]
            if d.parent_id and int(d.parent_id) in doc_map:  # type: ignore[arg-type]
                doc_map[int(d.parent_id)]["children"].append(node)  # type: ignore[arg-type]
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
        title_raw: Optional[str] = doc.title  # type: ignore[assignment]
        content_raw: Optional[str] = doc.content  # type: ignore[assignment]
        title_hits = title_raw.lower().count(query_lower) if title_raw else 0
        content_hits = content_raw.lower().count(query_lower) if content_raw else 0
        # Title matches weighted 3x vs content
        return min(1.0, (title_hits * 0.3 + content_hits * 0.1))

    @staticmethod
    def _extract_snippet(content: str, query: str, window: int = 300) -> str:
        """提取包含搜索关键词的上下文片段。

        提取策略（按优先级）：
        1. 按 Markdown 章节边界提取：找到关键词所在的 ### / ## / # 小节，
           返回该小节的完整内容（从当前标题到下一个同级或更高级标题）。
           —— 适用于结构化知识库文档，避免表格/解释被截断。
        2. 章节过大（>1500 字符）或无章节结构 → 回退到固定窗口（window）。
        3. 完整匹配失败 → 尝试匹配数字/字母数字 token（如 "1078"、"CJT1078"）。
        4. 所有匹配失败 → 返回开头。
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

        # 策略1：按 Markdown 章节边界提取
        section = KnowledgeService._extract_markdown_section(content, idx)
        if section:
            return section

        # 策略2：固定窗口回退
        start = max(0, idx - window // 2)
        end = min(len(content), idx + window // 2)
        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        return snippet

    @staticmethod
    def _extract_markdown_section(content: str, keyword_idx: int) -> Optional[str]:
        """提取关键词所在的 Markdown 小节完整内容。

        小节定义：从最近的 ### / ## / # 标题行开始，
        到下一个同级或更高级标题（或文档结尾）结束。

        Returns:
            小节完整文本（含标题），或 None（无章节结构/章节过大）。
        """
        if keyword_idx < 0 or keyword_idx >= len(content):
            return None

        # 向前查找最近的标题行（### / ## / #，行首）
        # 标题等级：#=1, ##=2, ###=3，数字越小级别越高
        before = content[:keyword_idx]
        # 匹配行首的 1-3 个 # 后跟空格
        heading_pattern = re.compile(r'(?m)^(\#{1,3})\s+.+$')
        headings = list(heading_pattern.finditer(before))
        if not headings:
            return None  # 前面没有任何标题，不算结构化文档

        last_heading = headings[-1]
        heading_level = len(last_heading.group(1))
        section_start = last_heading.start()

        # 向后查找下一个同级或更高级标题（level <= 当前 level）
        after = content[keyword_idx:]
        next_heading = None
        for m in heading_pattern.finditer(after):
            if len(m.group(1)) <= heading_level:
                next_heading = m
                break

        if next_heading:
            section_end = keyword_idx + next_heading.start()
        else:
            section_end = len(content)

        section = content[section_start:section_end].strip()

        # 章节过大 → 返回 None，让调用方回退到固定窗口
        # （避免把整篇大文档当 snippet 塞进上下文）
        if len(section) > 1500:
            return None

        # 标记边界（若非文档开头/结尾）
        prefix = "..." if section_start > 0 else ""
        suffix = "..." if section_end < len(content) else ""
        return prefix + section + suffix
