"""Knowledge document service — CRUD, search, and future RAG integration."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_config import get_logger
from app.models import KnowledgeDocument, KnowledgeDocumentMeta
from app.services.knowledge.templates import guess_section_key

logger = get_logger(__name__)

# 向量索引后台线程池：保存知识时不必等待 Milvus 连接/embedding/insert/flush
_INDEX_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="kb-index")

# 章节级 BM25 索引缓存：按语料签名复用，避免每次检索重建全量索引
_SECTION_INDEX_LOCK = __import__("threading").Lock()
_SECTION_INDEX: Any = None
_SECTION_INDEX_SIGNATURE: Optional[str] = None


def _get_section_index(signature: str, chunks: List[Any], index_cls: Any) -> Any:
    """返回按语料签名缓存的 BM25 索引（语料不变则复用）。"""
    global _SECTION_INDEX, _SECTION_INDEX_SIGNATURE
    with _SECTION_INDEX_LOCK:
        if _SECTION_INDEX is None or _SECTION_INDEX_SIGNATURE != signature:
            index = index_cls()
            index.ensure(chunks, signature)
            _SECTION_INDEX = index
            _SECTION_INDEX_SIGNATURE = signature
        return _SECTION_INDEX


def reset_section_index_cache() -> None:
    """测试用：清空 BM25 缓存。"""
    global _SECTION_INDEX, _SECTION_INDEX_SIGNATURE
    with _SECTION_INDEX_LOCK:
        _SECTION_INDEX = None
        _SECTION_INDEX_SIGNATURE = None


def _index_document_in_background(doc_id: int) -> None:
    from app.database import session as session_module
    from app.services.knowledge.document_indexer import DocumentIndexer

    db = session_module.create_session()
    try:
        DocumentIndexer(db).index_document(doc_id)
    except Exception as exc:  # noqa: BLE001 - 后台任务仅记录日志
        logger.warning("[KnowledgeService] background index failed for doc %s: %s", doc_id, exc)
    finally:
        db.close()


def _remove_index_in_background(doc_id: int) -> None:
    try:
        from app.services.knowledge.vector_service import get_vector_service

        get_vector_service().delete_document(doc_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[KnowledgeService] background index remove failed for doc %s: %s", doc_id, exc)


def dedupe_by_content_hash(chunks: List[Any]) -> List[Any]:
    """跨文档同内容去重：同一 hash 只保留排名最靠前的一条。

    同一段知识在多个文档里各存一份时（FAQ 与专题文档常见），
    重复条目会互相挤位，还让「命中哪个文档」变成随机结果。
    """
    seen: set = set()
    unique: List[Any] = []
    for chunk in chunks:
        digest = getattr(chunk, "content_hash", "") or ""
        if digest:
            if digest in seen:
                continue
            seen.add(digest)
        unique.append(chunk)
    return unique


def dedupe_triples_by_content_hash(rows: List[Any]) -> List[Any]:
    """对 (chunk, normalized, raw) 序列按 content_hash 去重，保留排名靠前的一条。"""
    seen: set = set()
    unique: List[Any] = []
    for chunk, normalized, raw in rows:
        digest = getattr(chunk, "content_hash", "") or ""
        if digest:
            if digest in seen:
                continue
            seen.add(digest)
        unique.append((chunk, normalized, raw))
    return unique


def dedupe_pairs_by_content_hash(pairs: List[Any]) -> List[Any]:
    """对 (chunk, score) 序列按 content_hash 去重，保留排名靠前的一条。"""
    seen: set = set()
    unique: List[Any] = []
    for chunk, score in pairs:
        digest = getattr(chunk, "content_hash", "") or ""
        if digest:
            if digest in seen:
                continue
            seen.add(digest)
        unique.append((chunk, score))
    return unique


class KnowledgeService:
    """Service for managing knowledge documents with keyword-based search."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Vector index sync（Milvus 启用时随 CRUD 自动维护）
    # ------------------------------------------------------------------

    def _sync_index(self, doc_id: int, content: str) -> None:
        """同步文档向量索引；失败不影响主流程。

        默认异步：保存知识后由后台线程完成 Milvus 索引，避免请求阻塞。
        设置 KNOWLEDGE_INDEX_ASYNC=false 可恢复同步行为。
        """
        try:
            from app.core.config import settings
            if not settings.MILVUS_ENABLED:
                return
            if getattr(settings, "KNOWLEDGE_INDEX_ASYNC", True):
                _INDEX_EXECUTOR.submit(_index_document_in_background, doc_id)
                return
            from app.services.knowledge.document_indexer import DocumentIndexer
            DocumentIndexer(self.db).index_document(doc_id, content=content)
        except Exception as exc:  # noqa: BLE001 - 索引失败不阻断 CRUD
            logger.warning("[KnowledgeService] index sync failed for doc %s: %s", doc_id, exc)

    def reindex(self, doc_id: int, content: Optional[str] = None) -> None:
        """显式重建文档向量索引（内容被外部修改后调用）。"""
        if content is None:
            doc = self.get(doc_id)
            content = str(doc.content or "")
        self._sync_index(doc_id, content)

    def _remove_index(self, doc_id: int) -> None:
        """删除文档向量索引；失败不影响主流程。"""
        try:
            from app.core.config import settings
            if not settings.MILVUS_ENABLED:
                return
            if getattr(settings, "KNOWLEDGE_INDEX_ASYNC", True):
                _INDEX_EXECUTOR.submit(_remove_index_in_background, doc_id)
                return
            from app.services.knowledge.vector_service import get_vector_service
            get_vector_service().delete_document(doc_id)
        except Exception as exc:  # noqa: BLE001 - 索引失败不阻断 CRUD
            logger.warning("[KnowledgeService] index remove failed for doc %s: %s", doc_id, exc)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_project_filter(query, project_id: Optional[int]):
        """项目过滤：仅返回指定项目 + 全局（project_id 为空）的文档。"""
        if project_id is None:
            return query
        return query.filter(or_(
            KnowledgeDocument.project_id == project_id,
            KnowledgeDocument.project_id.is_(None),
        ))

    def _attach_quality(self, docs: List[KnowledgeDocument]) -> None:
        """把 meta.quality_score 附加到文档对象上（供列表/详情展示）。"""
        if not docs:
            return
        ids = [int(d.id) for d in docs]
        metas = (
            self.db.query(KnowledgeDocumentMeta)
            .filter(KnowledgeDocumentMeta.doc_id.in_(ids))
            .all()
        )
        quality_map = {int(m.doc_id): m.quality_score for m in metas}
        for doc in docs:
            setattr(doc, "quality_score", quality_map.get(int(doc.id)))

    def create(
        self, data: Dict[str, Any], auto_index: bool = True,
    ) -> KnowledgeDocument:
        doc = KnowledgeDocument(
            title=data["title"],
            content=data["content"],
            category=data.get("category"),
            source=data.get("source"),
            doc_type=data.get("doc_type", "manual"),
            parent_id=data.get("parent_id"),
            project_id=data.get("project_id"),
            status=data.get("status") or "active",
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        if auto_index:
            self._sync_index(int(doc.id), str(doc.content or ""))
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
        self._attach_quality([doc])
        return doc

    def list(
        self,
        page: int = 1,
        page_size: int = 20,
        category: Optional[str] = None,
        doc_type: Optional[str] = None,
        status: Optional[str] = None,
        parent_id: Optional[int] = None,
        project_id: Optional[int] = None,
        sort_order: str = "updated_desc",
    ) -> Dict[str, Any]:
        query = self.db.query(KnowledgeDocument)
        query = self._apply_project_filter(query, project_id)

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
        if sort_order == "updated_asc":
            ordering = (KnowledgeDocument.updated_at.asc(), KnowledgeDocument.id.asc())
        else:
            ordering = (KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id.desc())
        items = (
            query.order_by(*ordering)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        self._attach_quality(items)

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
        project_id: Optional[int] = None,
        sections: bool = False,
        include_drafts: bool = False,
        return_sections: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """章节级混合检索：BM25 + 向量，按 RRF 融合。

        - 统一在「章节」粒度检索与融合：BM25 索引、向量写入、snippet 展示同一切分；
        - 分数只由名次决定（RRF），不比 BM25 与向量的原始分（量纲不可比）；
        - `sections=False` 按文档去重（管理端列表用），`True` 保留每个命中章节
          （对话回答用，模型需要精确到节）。

        这是此前「整篇文档建索引 + 章节提权」的替代实现：提权规则已删除，
        命中粒度本身就是修正。

        `include_drafts=True` 时草稿也参与召回（降权 8%），用于 AI 问答：
        知识库里常有尚未发布的准确条目，完全排除会让回答只能命中旧文档。
        `return_sections` 为旧调用方保留的别名（等价于 sections=True）。
        """
        if return_sections is not None:
            sections = bool(return_sections)
        empty = {"items": [], "total": 0, "page": page, "page_size": page_size}
        if not (query_text or "").strip():
            return empty

        try:
            from app.services.knowledge.section_search import (
                SectionBM25Index,
                build_section_chunks,
                corpus_signature,
                rank_sections,
            )

            docs_query = self.db.query(KnowledgeDocument)
            if include_drafts:
                docs_query = docs_query.filter(
                    KnowledgeDocument.status.in_(["active", "draft"]),
                )
            else:
                docs_query = docs_query.filter(KnowledgeDocument.status == "active")
            docs_query = self._apply_project_filter(docs_query, project_id)
            docs = docs_query.order_by(KnowledgeDocument.updated_at.desc()).limit(1000).all()
            if not docs:
                return empty

            chunks = build_section_chunks(docs)
            if not chunks:
                items = self._keyword_search_bm25(query_text, page_size, project_id=project_id)
                return {
                    "items": items[:page_size], "total": len(items),
                    "page": page, "page_size": page_size,
                }

            bm25_index = _get_section_index(corpus_signature(docs), chunks, SectionBM25Index)
            dense_hits = self._dense_hits(query_text, top_k=max(page_size * 3, 30))
            ranked = rank_sections(
                chunks, query=query_text, dense_hits=dense_hits, bm25_index=bm25_index,
                rrf_k=int(getattr(settings, "RRF_K", 60) or 60),
                weights=[
                    float(getattr(settings, "RRF_WEIGHT_SPARSE", 1.0) or 1.0),
                    float(getattr(settings, "RRF_WEIGHT_DENSE", 1.0) or 1.0),
                ],
                with_raw=True,
            )

            if not ranked:
                items = self._keyword_search_bm25(query_text, page_size, project_id=project_id)
                return {
                    "items": items[:page_size], "total": len(items),
                    "page": page, "page_size": page_size,
                }

            doc_map = {int(doc.id): doc for doc in docs}
            items: List[Dict[str, Any]] = []
            seen_docs: set = set()
            # 跨文档同内容去重：同一段知识在 FAQ 与专题文档里各存一份时，
            # 两条都进候选只会互相挤位，还让「命中哪个文档」变成随机结果
            ranked = dedupe_triples_by_content_hash(ranked)
            # 标题/结构提权：纯 RRF 只看词频，长文档里「日志搜索」这类泛词
            # 会把真正对题的短章节压下去（如「查看设备是否有进出站」）。
            # 归一化分保留 RRF 的主体排序，再用章节标题重合度做轻量校正。
            boosted = []
            for chunk, score, raw_score in ranked:
                doc = doc_map.get(chunk.doc_id)
                if doc is None:
                    continue
                section_score = float(score) * self._section_boost(
                    query_text, str(doc.title or ""), chunk.section, chunk.content,
                ) + self._section_bonus(query_text, chunk.section, chunk.content)
                boosted.append((chunk, section_score, raw_score))
            ranked = sorted(boosted, key=lambda row: row[1], reverse=True)
            # 提权是相对校正，不应把分数推出 0~1：按最高分归一化，
            # 既保留排序差异，也让前端相关度条/阈值判断仍有意义。
            peak = max((float(row[1]) for row in ranked), default=0.0)
            scale = peak if peak > 0 else 1.0
            ranked = [(chunk, float(score) / scale, raw_score) for chunk, score, raw_score in ranked]
            for chunk, score, raw_score in ranked:
                doc = doc_map.get(chunk.doc_id)
                if doc is None:
                    continue
                if not sections:
                    if chunk.doc_id in seen_docs:
                        continue
                    seen_docs.add(chunk.doc_id)
                # 草稿可参与，但同等条件下明显让位给正式文档
                display_score = float(score) * (0.92 if doc.status != "active" else 1.0)
                items.append({
                    "id": doc.id,
                    "title": doc.title,
                    "category": doc.category,
                    "doc_type": doc.doc_type,
                    "source": doc.source,
                    "section": chunk.section,
                    "key": chunk.key,
                    "relevance_score": round(display_score, 4),
                    # 原始 RRF 分：跨层可比，排序调优用这个
                    "fusion_score": round(float(raw_score), 6),
                    "snippet": (
                        f"## {chunk.section}\n\n{chunk.content}"[:1000]
                        if sections else self._extract_snippet(
                            str(doc.content), query_text,
                        )
                    ),
                })
                if len(items) >= page_size:
                    break

            return {"items": items, "total": len(items), "page": page, "page_size": page_size}
        except Exception as exc:  # noqa: BLE001 - 检索失败退回关键词，不让问答崩
            logger.error(
                "[KnowledgeService] 章节检索失败，已退回关键词检索（会显著降低召回，"
                "通常是代码缺陷而非数据问题）: %s", exc,
                exc_info=True,
            )
            items = self._keyword_search_bm25(query_text, page_size, project_id=project_id)
            return {
                "items": items[:page_size], "total": len(items),
                "page": page, "page_size": page_size,
            }

    @staticmethod
    def _dense_hits(query_text: str, top_k: int) -> List[Dict[str, Any]]:
        """向量一路的章节命中；Milvus 不可用时不参与融合（不报错）。"""
        try:
            from app.services.knowledge.vector_service import get_vector_service

            service = get_vector_service()
            if not getattr(service, "available", False):
                return []
            return service.search(query_text, top_k=top_k)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[KnowledgeService] dense search unavailable: %s", exc)
            return []

    def search_by_title(
        self,
        query_text: str,
        page: int = 1,
        page_size: int = 20,
        project_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """按文件名搜索 — 仅匹配标题（含文件夹），不做全文/向量检索。"""
        pattern = f"%{(query_text or '').strip()}%"
        query = self.db.query(KnowledgeDocument).filter(
            KnowledgeDocument.status == "active",
            KnowledgeDocument.title.ilike(pattern),
        )
        query = self._apply_project_filter(query, project_id)
        total = query.count()
        items = (
            query.order_by(
                KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id.desc()
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        self._attach_quality(items)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def keyword_search(
        self,
        query_text: str,
        limit: int = 5,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """纯关键词搜索 — 使用 BM25 替换旧的 ILIKE 回退"""
        return self._keyword_search_bm25(query_text, limit, project_id=project_id)

    def _keyword_search_bm25(
        self, query_text: str, limit: int = 5, project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """BM25 关键词检索 — 替换旧的 ILIKE 短语+分词回退。

        使用 BM25 算法做精确关键词匹配，比 SQL ILIKE 更快更准。
        """
        if not query_text.strip():
            return []

        try:
            # 获取所有活跃文档
            docs_query = (
                self.db.query(KnowledgeDocument)
                .filter(KnowledgeDocument.status == "active")
            )
            docs_query = self._apply_project_filter(docs_query, project_id)
            docs = docs_query.order_by(KnowledgeDocument.updated_at.desc()).limit(1000).all()
            if not docs:
                return []

            from app.services.knowledge.retrievers import BM25Retriever
            bm25 = BM25Retriever()
            bm25.index([
                (int(doc.id), f"{doc.title or ''}\n{doc.content or ''}")
                for doc in docs
            ])

            results = bm25.retrieve(query_text, top_k=limit)
            doc_map = {int(d.id): d for d in docs}

            items = []
            for r in results:
                doc = doc_map.get(r.chunk.doc_id)
                if doc:
                    items.append({
                        "id": doc.id,
                        "title": doc.title,
                        "category": doc.category,
                        "doc_type": doc.doc_type,
                        "source": doc.source,
                        "relevance_score": round(r.score, 2),
                        "snippet": self._extract_snippet(
                            str(doc.content), query_text,
                        ),
                    })
            return items or self._keyword_search_phrase(query_text, limit, project_id=project_id)
        except Exception as e:
            logger = __import__("app.core.logging_config", fromlist=["get_logger"]).get_logger(__name__)
            logger.debug("[KnowledgeService] BM25 search failed, falling back to ILIKE: %s", e)
            # 最终回退到旧的 ILIKE
            return self._keyword_search_phrase(query_text, limit, project_id=project_id) or []

    def _keyword_search_phrase(
        self, query_text: str, limit: int, project_id: Optional[int] = None,
    ) -> list:
        """Exact phrase ILIKE search."""
        if not query_text.strip():
            return []
        pattern = f"%{query_text}%"
        query = self.db.query(KnowledgeDocument).filter(
            KnowledgeDocument.status == "active",
            or_(
                KnowledgeDocument.title.ilike(pattern),
                KnowledgeDocument.content.ilike(pattern),
            ),
        )
        query = self._apply_project_filter(query, project_id)
        docs = (
            query
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

        Chinese: extract meaningful n-grams with sub-string priority.
        English: split by whitespace and punctuation.

        改进：对于中文长词（如"启迪云控平台"），生成：
          1. 完整词 "启迪云控平台"
          2. 剥离后缀 "启迪云控"
          3. 核心 n-grams "启迪云控"、"云控平台"
        确保简称也能匹配到包含完整名称的文档。
        """
        tokens: set[str] = set()

        # 常见中文后缀（可剥离以提高召回率）
        _CN_SUFFIXES = {"平台", "系统", "设备", "模块", "服务", "终端",
                         "服务器", "客户端", "管理端", "网关", "控制器"}

        # Extract Chinese phrases
        cn_chars = re.findall(r"[\u4e00-\u9fff]+", query_text)
        for phrase in cn_chars:
            if len(phrase) >= 2:
                tokens.add(phrase)  # full Chinese phrase

                # 剥离后缀生成简称（如"启迪云控平台" → "启迪云控"）
                for suffix in _CN_SUFFIXES:
                    if phrase.endswith(suffix) and len(phrase) > len(suffix):
                        short = phrase[:-len(suffix)]
                        if len(short) >= 2:
                            tokens.add(short)
                        break  # 只剥离一个后缀

                # 滑动窗口 2-4 字 n-gram（不重叠提取，减少碎片）
                if len(phrase) >= 2:
                    for w in [2, 3, 4]:
                        for i in range(len(phrase) - w + 1):
                            tokens.add(phrase[i:i + w])

        # Extract English/technical tokens
        en_tokens = re.findall(r"[A-Za-z0-9_]{2,}", query_text)
        for t in en_tokens:
            tokens.add(t)

        # Filter common stop words
        stop_words = {"的", "了", "在", "是", "我", "有", "和", "就", "不",
                       "人", "都", "一", "个", "上", "也", "很", "到", "说",
                       "要", "去", "你", "会", "着", "没有", "看", "好", "自己",
                       "什么", "怎么", "为什么", "怎么样", "如何", "哪", "哪些"}
        tokens = {t for t in tokens if t.lower() not in stop_words and len(t) >= 2}

        # Sort: longer tokens first (more specific), 剥离后缀的简称优先
        return sorted(tokens, key=len, reverse=True)

    @staticmethod
    def _token_relevance(doc: KnowledgeDocument, tokens: list[str]) -> float:
        """Score based on how many tokens match in title vs content.

        评分改进：
        1. 含数字的 token（如 "1078"、"CJT1078"）命中时 3 倍权重
        2. 长 token（≥4 字）命中时 2 倍权重（更具体的匹配）
        3. **子串匹配奖励**：如果搜索词是文档标题/内容的子串，
           说明搜索词被完整包含，给予额外加分
        4. title 命中权重 0.4，content 命中权重 0.15
        """
        title_lower = (doc.title or "").lower()
        content_lower = (doc.content or "").lower()
        if not tokens:
            return 0

        def _weight(token: str) -> float:
            w = 1.0
            if re.search(r"\d", token):
                w *= 3.0  # 含数字的强区分度 token
            if len(token) >= 4:
                w *= 2.0  # 长 token 更具体
            return w

        total_weight = sum(_weight(t) for t in tokens)
        title_hits = 0.0
        content_hits = 0.0

        for t in tokens:
            w = _weight(t)
            t_lower = t.lower()

            # 标题匹配
            if t_lower in title_lower:
                title_hits += w
                # 子串匹配奖励：如果搜索词是标题的子串（如"启迪云控"是"启迪云控平台"的子串）
                # 说明搜索词被完整包含，是高质量匹配
                if len(t) >= 2 and t_lower in title_lower:
                    title_hits += w * 0.5

            # 内容匹配
            if t_lower in content_lower:
                content_hits += w
                # 同理：子串匹配奖励
                if len(t) >= 2:
                    content_hits += w * 0.25

        return min(1.0, (title_hits * 0.4 + content_hits * 0.15) / max(1.0, total_weight))

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self, doc_id: int, data: Dict[str, Any], auto_index: bool = True,
    ) -> KnowledgeDocument:
        doc = self.get(doc_id)
        for field in ("title", "content", "category", "source", "doc_type", "project_id", "status", "is_pinned"):
            if field in data and data[field] is not None:
                setattr(doc, field, data[field])
        self.db.commit()
        self.db.refresh(doc)
        if auto_index:
            self._sync_index(int(doc.id), str(doc.content or ""))
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
        self._remove_index(doc_id)

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
            self._remove_index(int(child.id))  # type: ignore[arg-type]

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
    def _query_fragments(text: str, sizes: tuple = (2, 3, 4)) -> set:
        """抽取查询中的中文 n-gram，用于章节标题重合度计算。"""
        cn = re.sub(r"[^\u4e00-\u9fff]", "", text or "")
        fragments = set()
        for size in sizes:
            for i in range(len(cn) - size + 1):
                fragments.add(cn[i:i + size])
        return fragments

    @classmethod
    def _section_boost(cls, query: str, title: str, heading: str, body: str) -> float:
        """章节结构提权（乘性）。

        三个信号：
          1. 章节标题的 n-gram 出现在问题里（标题覆盖率）
          2. 问题在问「搜索/关键字」且章节含关键字清单
          3. 文档标题直接出现在问题中
        """
        q = (query or "").lower()
        boost = 1.0

        clean_heading = re.sub(r"^[\d.\s#、]+", "", (heading or "")).lower()
        if clean_heading:
            # 长片段（3~4 字）更能代表实体；2 字片段噪声大，只给低权重
            long_hits = sum(
                1 for frag in cls._query_fragments(clean_heading, sizes=(3, 4))
                if frag in q
            )
            short_hits = sum(
                1 for frag in cls._query_fragments(clean_heading, sizes=(2,))
                if frag in q
            )
            boost += min(2.0, long_hits * 0.8 + short_hits * 0.2)

        if title and title.lower() in q:
            boost += 1.0

        return boost

    @classmethod
    def _section_bonus(cls, query: str, heading: str, body: str) -> float:
        """结构加分（加性）。

        针对「日志里搜什么 / 用什么关键字」这类问题：同时满足
        「章节含关键字清单」且「章节标题命中问题实体」时给强加分。
        加性而非乘性——否则 BM25 基分低的正确章节永远追不上泛词章节。
        """
        q = (query or "").lower()
        if not any(
            word in q
            for word in ("搜索什么", "搜什么", "搜索哪些", "关键字", "日志搜索", "怎么搜")
        ):
            return 0.0

        bonus = 0.0
        if (
            "关键字" in (heading or "")
            or "关键字" in (body or "")
            or "可搜索" in (body or "")
        ):
            bonus += 0.6

        clean_heading = re.sub(r"^[\d.\s#、]+", "", (heading or "")).lower()
        if clean_heading and any(
            frag in q for frag in cls._query_fragments(clean_heading, sizes=(3, 4))
        ):
            bonus += 0.8
        return bonus

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
    def _extract_snippet_info(content: str, query: str, window: int = 300) -> Dict[str, Any]:
        """提取含关键词的片段，并返回所属章节与行号范围。"""
        base = {"snippet": "", "section_title": "", "section_key": "", "start_line": 0, "end_line": 0}
        if not content or not query:
            return {**base, "snippet": (content or "")[:window]}

        idx = content.lower().find(query.lower())
        if idx == -1:
            for token in re.findall(r"[A-Za-z]*\d+[A-Za-z]*", query):
                idx = content.lower().find(token.lower())
                if idx != -1:
                    break
        if idx == -1:
            return {**base, "snippet": content[:300]}

        located = KnowledgeService._locate_markdown_section(content, idx)
        if located:
            return {**base, **located}

        start = max(0, idx - window // 2)
        end = min(len(content), idx + window // 2)
        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        return {**base, "snippet": snippet}

    @staticmethod
    def _locate_markdown_section(content: str, keyword_idx: int) -> Optional[Dict[str, Any]]:
        """定位关键词所属的 Markdown 章节，返回片段、章节标题与行号范围。"""
        if keyword_idx < 0 or keyword_idx >= len(content):
            return None
        heading_pattern = re.compile(r"(?m)^(\#{1,6})\s+(.+?)\s*$")
        before = content[:keyword_idx]
        headings = list(heading_pattern.finditer(before))
        if not headings:
            return None
        last = headings[-1]
        level = len(last.group(1))
        title = last.group(2).strip()
        section_start = last.start()
        after = content[keyword_idx:]
        next_heading = None
        for m in heading_pattern.finditer(after):
            if len(m.group(1)) <= level:
                next_heading = m
                break
        section_end = keyword_idx + next_heading.start() if next_heading else len(content)
        section_text = content[section_start:section_end].strip()
        if len(section_text) > 1500:
            return None
        start_line = content.count("\n", 0, section_start) + 1
        end_line = content.count("\n", 0, section_end) + 1
        prefix = "..." if section_start > 0 else ""
        suffix = "..." if section_end < len(content) else ""
        return {
            "snippet": prefix + section_text + suffix,
            "section_title": title,
            "section_key": guess_section_key(title),
            "start_line": start_line,
            "end_line": end_line,
        }

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
