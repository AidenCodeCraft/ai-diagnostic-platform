"""知识库向量回填 — 章节级集合重建后的重索引流程。

场景：集合 schema/维度变更（例如 512 维整篇文档 → 1024 维章节级）后，
旧向量不可复用，必须全量回填。本模块只负责「遍历 + 索引 + 统计 + 守卫」，
CLI 在 scripts/reindex_knowledge.py。

守卫（缺一不可，否则回填出来的是垃圾）：
  1. 向量服务可用（Milvus 连通、集合 schema 与配置一致）；
  2. 当前 embedder 是语义模型（HashingEmbedder 直接拒绝）；
  3. embedding 维度与集合维度一致；
  4. 文档内容非空。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models import KnowledgeDocument

logger = get_logger(__name__)


class ReindexError(RuntimeError):
    """回填前置条件不满足。"""


@dataclass
class ReindexStats:
    total_docs: int = 0
    indexed_docs: int = 0
    empty_docs: int = 0
    skipped_folders: int = 0
    total_chunks: int = 0
    failed: List[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "total_docs": self.total_docs,
            "indexed_docs": self.indexed_docs,
            "empty_docs": self.empty_docs,
            "skipped_folders": self.skipped_folders,
            "total_chunks": self.total_chunks,
            "failed_docs": len(self.failed),
        }


def check_environment(vector_service: Any = None, embedder: Any = None) -> dict:
    """回填前自检；不满足直接抛 ReindexError（宁可失败也不写入垃圾向量）。"""
    if vector_service is None or embedder is None:
        from app.services.knowledge.embedding import get_embedder
        from app.services.knowledge.vector_service import get_vector_service

        vector_service = vector_service or get_vector_service()
        embedder = embedder or get_embedder()

    provider = getattr(embedder, "provider_name", type(embedder).__name__)
    if str(provider).startswith("Hashing"):
        raise ReindexError(
            "当前 embedding 是哈希兜底（非语义向量），回填没有意义。"
            "请先安装 sentence-transformers / 配置 EMBEDDING_API_URL，并设置 EMBEDDING_HASH_FALLBACK=false。"
        )

    schema_error = getattr(vector_service, "schema_error", None)
    if schema_error:
        raise ReindexError(f"向量集合与配置不兼容：{schema_error}")

    if not getattr(vector_service, "available", False):
        raise ReindexError(
            "向量服务不可用（Milvus 未连通或未启用）。检查 MILVUS_ENABLED / MILVUS_HOST / 集合是否存在。"
        )

    embed_dim = int(getattr(embedder, "dimension", 0) or 0)
    vec_dim = int(getattr(vector_service, "dimension", 0) or 0)
    if embed_dim and vec_dim and embed_dim != vec_dim:
        raise ReindexError(
            f"embedding 维度 {embed_dim} 与集合维度 {vec_dim} 不一致，请重建集合或对齐 EMBEDDING_DIM/MILVUS_DIM。"
        )

    return {
        "provider": provider,
        "dimension": embed_dim or vec_dim,
        "collection": getattr(vector_service, "collection_name", ""),
    }


def run_reindex(
    db: Session,
    *,
    start_id: int = 0,
    limit: Optional[int] = None,
    dry_run: bool = False,
    indexer: Any = None,
    progress: Optional[Callable[[ReindexStats], None]] = None,
) -> ReindexStats:
    """遍历知识文档并逐篇重建章节级向量。

    Args:
        db: 数据库会话
        start_id: 从该文档 ID 之后开始（断点续跑）
        limit: 最多处理文档数
        dry_run: 只统计，不写入
        indexer: 注入的索引器（默认 DocumentIndexer）
        progress: 每篇回调（用于打印进度）
    """
    stats = ReindexStats()

    # 与检索侧保持同一可见集合：检索只看 active，回填也只回填 active，
    # 否则会出现「向量库里有、BM25 没索引」的文档，语义那一路直接失效
    # 目录节点（doc_type=folder）没有正文，只用于组织树；回填时先剔除，
    # 否则它们全部落进 empty_docs，掩盖「真的正文为空」的坏数据。
    query = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.status == "active")
        .filter(or_(KnowledgeDocument.doc_type.is_(None), KnowledgeDocument.doc_type != "folder"))
        .filter(KnowledgeDocument.id > start_id)
        .order_by(KnowledgeDocument.id.asc())
    )
    if limit:
        query = query.limit(limit)
    docs = query.all()
    stats.total_docs = len(docs)
    stats.skipped_folders = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.status == "active")
        .filter(KnowledgeDocument.doc_type == "folder")
        .count()
    )

    if indexer is None:
        if not dry_run:
            from app.services.knowledge.document_indexer import DocumentIndexer

            indexer = DocumentIndexer(db)

    for doc in docs:
        content = str(doc.content or "")
        if not content.strip():
            stats.empty_docs += 1
            continue

        if dry_run:
            stats.indexed_docs += 1
            if progress:
                progress(stats)
            continue

        try:
            chunks = indexer.index_document(doc.id, content=content)
        except Exception as exc:  # noqa: BLE001 - 单篇失败不影响整体
            logger.error("[Reindex] doc %d failed: %s", doc.id, exc)
            stats.failed.append({"doc_id": doc.id, "error": str(exc)})
            continue

        if chunks:
            stats.indexed_docs += 1
            stats.total_chunks += int(chunks)
        else:
            stats.empty_docs += 1
        if progress:
            progress(stats)

    return stats
