"""Milvus Vector Service — 向量数据库全功能集成。

功能：
- Milvus 客户端连接管理（支持 gRPC）
- Collection 生命周期管理（创建、加载、释放、删除）
- 向量插入 / Upsert
- 向量相似度搜索（支持 Top-K、过滤条件）
- 文档删除
- 健康检查 + 自动回退

当 MILVUS_ENABLED=False 或连接失败时，自动回退到关键词搜索。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.logging_config import get_logger
from app.services.knowledge.embedding_service import EmbeddingService

logger = get_logger(__name__)

# Milvus 相关导入
_milvus_available = False
try:
    from pymilvus import (
        connections,
        Collection,
        CollectionSchema,
        FieldSchema,
        DataType,
        utility,
    )
    _milvus_available = True
except ImportError:
    logger.warning("[VectorService] pymilvus not installed. Falling back to keyword search.")


class VectorService:
    """Milvus 向量搜索服务 — 生产级实现。

    架构：
        User Query → Embedding → Milvus.search() → Top-K 结果

    Usage:
        svc = VectorService()
        results = svc.search("USB timeout", top_k=5)
        # results = [{"id": 1, "score": 0.92, "content": "..."}, ...]
    """

    _COLLECTION_NAME = settings.MILVUS_COLLECTION or "knowledge_docs"
    _VECTOR_DIM = settings.MILVUS_DIM or 1536

    def __init__(self):
        self._connected = False
        self._collection: Optional[Any] = None  # pymilvus.Collection
        self._embedding = EmbeddingService()
        self._connect()

    # ==================================================================
    # Connection Management
    # ==================================================================

    def _connect(self) -> bool:
        """连接到 Milvus 服务器。"""
        if not settings.MILVUS_ENABLED:
            logger.info("[VectorService] Milvus disabled by config, using keyword fallback")
            self._connected = False
            return False

        if not _milvus_available:
            logger.warning("[VectorService] pymilvus not installed")
            self._connected = False
            return False

        try:
            # 构建连接参数
            conn_params: Dict[str, Any] = {
                "alias": "default",
                "host": settings.MILVUS_HOST,
                "port": str(settings.MILVUS_PORT),
            }

            if settings.MILVUS_USER and settings.MILVUS_PASSWORD:
                conn_params["user"] = settings.MILVUS_USER
                conn_params["password"] = settings.MILVUS_PASSWORD

            connections.connect(**conn_params)
            self._connected = True
            logger.info(
                "[VectorService] Connected to Milvus at %s:%s",
                settings.MILVUS_HOST, settings.MILVUS_PORT,
            )

            # 确保 collection 存在
            self._ensure_collection()
            return True

        except Exception as exc:
            logger.warning("[VectorService] Cannot connect to Milvus: %s. Falling back to keyword.", exc)
            self._connected = False
            return False

    def _ensure_collection(self) -> None:
        """确保 collection 存在，不存在则创建。"""
        if not self._connected:
            return

        try:
            if utility.has_collection(self._COLLECTION_NAME):
                self._collection = Collection(self._COLLECTION_NAME)
                self._collection.load()
                logger.info("[VectorService] Collection '%s' loaded", self._COLLECTION_NAME)
                return

            # 创建新的 collection
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=False),
                FieldSchema(name="doc_id", dtype=DataType.INT64),
                FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=2000),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self._VECTOR_DIM),
            ]
            schema = CollectionSchema(fields, description="Knowledge document embeddings")

            self._collection = Collection(self._COLLECTION_NAME, schema)
            self._collection.load()

            # 创建 IVF_FLAT 索引（适合中等规模数据）
            index_params = {
                "metric_type": "IP",  # Inner Product (余弦相似度的代理)
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128},
            }
            self._collection.create_index("embedding", index_params)
            logger.info("[VectorService] Collection '%s' created with index", self._COLLECTION_NAME)

        except Exception as exc:
            logger.error("[VectorService] Failed to ensure collection: %s", exc)
            self._connected = False

    # ==================================================================
    # Public API
    # ==================================================================

    def search(
        self,
        query: str,
        top_k: int = 5,
        collection: Optional[str] = None,
        filter_expr: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """向量相似度搜索。

        Args:
            query: 搜索查询文本
            top_k: 返回的最相关结果数
            collection: Milvus collection 名称
            filter_expr: 标量过滤表达式（如 "doc_id > 100"）

        Returns:
            [{"id": doc_id, "score": similarity, "content": "...", "doc_id": int}, ...]
        """
        if not query or not query.strip():
            return []

        # 如果 Milvus 不可用，返回空列表（调用方会回退到关键词搜索）
        if not self.available:
            logger.debug("[VectorService] Milvus unavailable, returning empty (caller will fallback)")
            return []

        try:
            # 1. 生成查询嵌入向量
            start_time = time.time()
            query_embedding = self._embedding.embed(query)
            embed_time = time.time() - start_time

            # 2. 执行向量搜索
            search_params = {"metric_type": "IP", "params": {"nprobe": 16}}

            results = self._collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                expr=filter_expr,
                output_fields=["doc_id", "content"],
            )

            search_time = time.time() - start_time - embed_time
            logger.info(
                "[VectorService] Search completed: embed=%.2fs search=%.2fs hits=%d",
                embed_time, search_time, len(results[0]) if results else 0,
            )

            if not results or not results[0]:
                return []

            # 3. 格式化结果
            return [
                {
                    "id": hit.entity.get("doc_id", 0),
                    "score": float(hit.score),
                    "content": hit.entity.get("content", ""),
                }
                for hit in results[0]
            ]

        except Exception as exc:
            logger.error("[VectorService] Search error: %s", exc)
            return []

    def index_document(
        self,
        doc_id: int,
        content: str,
        chunk_size: int = 500,
        overlap: int = 50,
    ) -> int:
        """索引一个文档（分块嵌入后插入 Milvus）。

        Args:
            doc_id: 文档 ID
            content: 文档内容
            chunk_size: 分块大小
            overlap: 块间重叠

        Returns:
            索引的向量数量（chunk 数量）
        """
        if not self.available:
            logger.debug("[VectorService] Milvus unavailable, skip indexing doc %d", doc_id)
            return 0

        if not content or not content.strip():
            return 0

        try:
            # 1. 删除旧向量（如果存在）
            self.delete_document(doc_id)

            # 2. 分块 + 嵌入
            chunks = self._embedding._chunk_text(content, chunk_size, overlap)
            if not chunks:
                return 0

            embeddings = self._embedding.embed_batch(chunks)

            # 3. 构建插入数据
            # 使用 (doc_id, chunk_index) 组合作为主键
            insert_ids = []
            insert_doc_ids = []
            insert_contents = []
            insert_embeddings = []

            for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                # 生成唯一主键：doc_id * 10000 + chunk_index
                pk = doc_id * 10000 + i
                insert_ids.append(pk)
                insert_doc_ids.append(doc_id)
                insert_contents.append(chunk[:2000])
                insert_embeddings.append(emb)

            # 4. 插入 Milvus
            entities = [insert_ids, insert_doc_ids, insert_contents, insert_embeddings]
            self._collection.insert(entities)
            self._collection.flush()

            logger.info(
                "[VectorService] Indexed doc %d: %d chunks",
                doc_id, len(chunks),
            )
            return len(chunks)

        except Exception as exc:
            logger.error("[VectorService] Index document %d failed: %s", doc_id, exc)
            return 0

    def index_documents_batch(
        self,
        docs: List[Tuple[int, str]],
        chunk_size: int = 500,
        overlap: int = 50,
    ) -> int:
        """批量索引文档。

        Args:
            docs: [(doc_id, content), ...]
            chunk_size: 分块大小
            overlap: 块间重叠

        Returns:
            总索引向量数
        """
        total = 0
        for doc_id, content in docs:
            total += self.index_document(doc_id, content, chunk_size, overlap)
        return total

    def delete_document(self, doc_id: int) -> bool:
        """删除文档的所有向量。

        Args:
            doc_id: 文档 ID

        Returns:
            是否成功删除
        """
        if not self.available:
            return False

        try:
            expr = f"doc_id == {doc_id}"
            self._collection.delete(expr)
            self._collection.flush()
            logger.info("[VectorService] Deleted vectors for doc %d", doc_id)
            return True

        except Exception as exc:
            logger.error("[VectorService] Delete doc %d failed: %s", doc_id, exc)
            return False

    def health_check(self) -> bool:
        """健康检查 — Milvus 连接状态。"""
        if not self._connected:
            return False

        try:
            utility.list_collections()
            return True
        except Exception:
            self._connected = False
            return False

    def reconnect(self) -> bool:
        """尝试重新连接 Milvus。"""
        logger.info("[VectorService] Attempting reconnect...")
        return self._connect()

    # ==================================================================
    # Properties
    # ==================================================================

    @property
    def available(self) -> bool:
        """Milvus 是否可用。"""
        if not settings.MILVUS_ENABLED:
            return False
        if not self._connected:
            return False
        return self.health_check()

    @property
    def collection_name(self) -> str:
        return self._COLLECTION_NAME

    @property
    def collection_info(self) -> Optional[Dict[str, Any]]:
        """获取 Collection 信息。"""
        if not self._collection:
            return None
        try:
            return {
                "name": self._collection.name,
                "num_entities": self._collection.num_entities,
                "schema": str(self._collection.schema),
            }
        except Exception:
            return None


# ==================================================================
# Singleton
# ==================================================================

_vector_service_instance: Optional[VectorService] = None


def get_vector_service() -> VectorService:
    """获取 VectorService 单例。"""
    global _vector_service_instance
    if _vector_service_instance is None:
        _vector_service_instance = VectorService()
    return _vector_service_instance
