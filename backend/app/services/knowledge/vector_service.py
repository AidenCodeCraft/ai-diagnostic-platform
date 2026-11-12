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

import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.logging_config import get_logger
from app.services.knowledge.embedding import get_embedder

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
    _EMBEDDING_LOAD_TIMEOUT = 10.0

    def __init__(self):
        self._connected = False
        self._collection: Optional[Any] = None  # pymilvus.Collection
        self._embedding = None
        self._embedding_load_started = False
        self._dim = int(getattr(settings, "MILVUS_DIM", 512) or 512)
        self._connect()
        if self._connected:
            self._ensure_embedding()
            if self._embedding is not None:
                self._dim = int(self._embedding.dimension)
            self._ensure_collection()

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
            return True

        except Exception as exc:
            logger.warning("[VectorService] Cannot connect to Milvus: %s. Falling back to keyword.", exc)
            self._connected = False
            return False

    def _ensure_embedding(self) -> bool:
        """Load the embedding service with a hard timeout.

        BGE/SentenceTransformer may download model weights on first use.  We
        must not let a slow or unreachable model download block the streaming
        chat endpoint indefinitely.  On timeout this VectorService instance
        keeps keyword fallback for the current request; a background thread may
        finish loading the shared embedder for later requests.
        """
        if self._embedding is not None:
            return True
        if self._embedding_load_started:
            return False

        self._embedding_load_started = True
        result: Dict[str, Any] = {}

        def _load() -> None:
            try:
                result["embedder"] = get_embedder()
            except Exception as exc:  # noqa: BLE001 - keep fallback alive
                result["error"] = exc

        thread = threading.Thread(target=_load, daemon=True)
        thread.start()
        thread.join(self._EMBEDDING_LOAD_TIMEOUT)

        if thread.is_alive():
            logger.error(
                "[VectorService] Embedding model load exceeded %.1fs; "
                "using keyword fallback for this request",
                self._EMBEDDING_LOAD_TIMEOUT,
            )
            return False

        if "embedder" in result:
            self._embedding = result["embedder"]
            return True

        logger.error(
            "[VectorService] Embedding model load failed: %s",
            result.get("error"),
        )
        return False

    def _ensure_collection(self) -> None:
        """确保 collection 存在、有向量索引且已加载。

        注意顺序：Milvus 2.4+ 禁止在 embedding 字段没有索引时 load collection
        （报 `code=700 index not found`），因此必须「建/取 collection →
        确保索引存在 → load」，旧实现先 load 再 create_index 会永久失败。
        对历史上「已创建但无索引」的 collection 会自动补建索引（自愈）。
        """
        if not self._connected:
            return

        try:
            if utility.has_collection(self._COLLECTION_NAME):
                self._collection = Collection(self._COLLECTION_NAME)
                existing_dim = self._read_collection_dim()
                if existing_dim:
                    self._dim = existing_dim
                logger.info(
                    "[VectorService] Collection '%s' exists (dim=%d), ensuring index",
                    self._COLLECTION_NAME, self._dim,
                )
            else:
                # 创建新的 collection
                fields = [
                    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=False),
                    FieldSchema(name="doc_id", dtype=DataType.INT64),
                    FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=2000),
                    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self._dim),
                ]
                schema = CollectionSchema(fields, description="Knowledge document embeddings")
                self._collection = Collection(self._COLLECTION_NAME, schema)
                logger.info(
                    "[VectorService] Collection '%s' created (dim=%d)",
                    self._COLLECTION_NAME, self._dim,
                )

            # 必须先建索引，后 load（Milvus 2.4+ 不允许无索引 load）
            self._ensure_vector_index()
            self._collection.load()
            logger.info(
                "[VectorService] Collection '%s' loaded (dim=%d)",
                self._COLLECTION_NAME, self._dim,
            )

        except Exception as exc:
            logger.error("[VectorService] Failed to ensure collection: %s", exc)
            self._connected = False

    def _ensure_vector_index(self) -> bool:
        """确保 embedding 字段存在向量索引（幂等）。

        Returns:
            是否本次新建了索引。
        """
        if self._collection is None:
            return False

        # 索引已存在则直接返回
        try:
            for index in self._collection.indexes:
                field_name = getattr(index, "field_name", None)
                if field_name is None:
                    field_name = (getattr(index, "params", None) or {}).get("field_name")
                if field_name == "embedding":
                    return False
        except Exception as exc:  # noqa: BLE001 - 读不到索引列表时尝试补建
            logger.warning("[VectorService] Read collection indexes failed: %s", exc)

        # 创建 IVF_FLAT 索引（适合中等规模数据）
        index_params = {
            "metric_type": "IP",  # Inner Product (余弦相似度的代理)
            "index_type": "IVF_FLAT",
            "params": {"nlist": 128},
        }
        self._collection.create_index("embedding", index_params)
        logger.info(
            "[VectorService] Created IVF_FLAT/IP index for collection '%s'",
            self._COLLECTION_NAME,
        )
        return True

    def _read_collection_dim(self) -> Optional[int]:
        """读取已有 collection 的 embedding 维度。"""
        try:
            for field in self._collection.schema.fields:
                if field.name == "embedding":
                    return int(field.params.get("dim", 0)) or None
        except Exception:  # noqa: BLE001 - 读取失败时保留配置维度
            return None
        return None

    # ==================================================================
    # Public API
    # ==================================================================

    def search(
        self,
        query: str,
        top_k: int = 5,
        _collection: Optional[str] = None,  # reserved for future multi-collection support
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
            if self._collection is None:
                return []
            if self._embedding is None:
                logger.warning("[VectorService] Embedding service unavailable, returning empty")
                return []

            # 1. 生成查询嵌入向量
            start_time = time.time()
            query_embedding = self._embedding.embed(query)
            embed_time = time.time() - start_time
            if len(query_embedding) != self._dim:
                logger.error(
                    "[VectorService] Query embedding dim mismatch: got %d, expected %d; "
                    "please align EMBEDDING_DIM/MILVUS_DIM",
                    len(query_embedding), self._dim,
                )
                return []

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
            # 注意：pymilvus 2.5.x 的 Hit.get(field_name) 不接受 default 参数
            #（旧代码 hit.entity.get("doc_id", 0) 会抛 TypeError 导致 search 永远返回空）。
            return [
                {
                    "id": int(hit.entity.get("doc_id") or 0),
                    "score": float(hit.score),
                    "content": hit.entity.get("content") or "",
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
            if self._collection is None:
                return 0
            if self._embedding is None:
                logger.warning("[VectorService] Embedding service unavailable, skipping index")
                return 0

            # 1. 删除旧向量（如果存在）
            self.delete_document(doc_id)

            # 2. 分块 + 嵌入
            chunks = self._embedding._chunk_text(content, chunk_size, overlap)
            if not chunks:
                return 0

            embeddings = self._embedding.embed_batch(chunks)
            if embeddings and len(embeddings[0]) != self._dim:
                logger.error(
                    "[VectorService] Embedding dim mismatch: got %d, expected %d; "
                    "please align EMBEDDING_DIM/MILVUS_DIM or recreate the collection",
                    len(embeddings[0]), self._dim,
                )
                return 0

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

        if self._collection is None:
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
        if self._collection is None or self._embedding is None:
            return False
        return self.health_check()

    @property
    def collection_name(self) -> str:
        return self._COLLECTION_NAME

    @property
    def dimension(self) -> int:
        return self._dim

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
