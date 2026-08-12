"""检索层 — BM25 + Milvus + RRF 混合检索。

完全替换旧的 knowledge_service.search() 中的 ILIKE 回退逻辑。
实现 IRetriever 接口，支持 Dense + Sparse 融合检索。

=============================================================================
与旧 KnowledgeService.search() 的集成
=============================================================================
旧的 search() 方法: 向量搜索 → ILIKE短语 → ILIKE分词(三阶段回退)
新的检索策略:    Milvus向量 + BM25关键词 → RRF融合 → 统一排序

本模块在 knowledge_service.search() 的向量搜索失败后，
不再回退到 ILIKE，而是使用 BM25Retriever + RRF 融合。
"""

from __future__ import annotations
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from app.services.core.interfaces import IRetriever, SearchResult, Chunk
from app.services.core.config import RetrievalConfig

logger = logging.getLogger(__name__)


# =========================================================================
# BM25 稀疏检索器
# =========================================================================


class BM25Retriever(IRetriever):
    """BM25 关键词检索器 — Okapi BM25 算法。

    使用 rank-bm25 库（纯 Python）实现。
    安装: pip install rank-bm25
    """

    name = "bm25"

    def __init__(self):
        self._corpus: List[str] = []
        self._doc_ids: List[int] = []
        self._bm25: Any = None
        self._tokenized: List[List[str]] = []

    def index(self, docs: List[Tuple[int, str]]) -> None:
        """索引文档列表。docs: [(doc_id, text), ...]"""
        if not docs:
            return
        self._doc_ids = [d[0] for d in docs]
        self._corpus = [d[1] for d in docs]
        self._tokenized = [self._tokenize(t) for t in self._corpus]
        try:
            from rank_bm25 import BM25Okapi
            self._bm25 = BM25Okapi(self._tokenized)
            logger.info("[BM25] Indexed %d documents", len(docs))
        except ImportError:
            logger.warning("[BM25] rank-bm25 not installed. Install: pip install rank-bm25")

    def retrieve(self, query: str, top_k: int = 20, **kwargs) -> List[SearchResult]:
        if self._bm25 is None:
            return []
        tokenized = self._tokenize(query)
        scores = self._bm25.get_scores(tokenized)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            SearchResult(
                chunk=Chunk(
                    id=f"bm25_{self._doc_ids[idx]}",
                    text=self._corpus[idx][:500],
                    doc_id=self._doc_ids[idx],
                    granularity="document",
                ),
                score=float(score),
                sparse_score=float(score),
            )
            for idx, score in ranked if score > 0
        ]

    def health_check(self) -> bool:
        return self._bm25 is not None

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        tokens: List[str] = []
        en = re.findall(r'[A-Za-z0-9_]{2,}', text)
        tokens.extend(en)
        cn = re.sub(r'[a-zA-Z0-9\s]+', ' ', text)
        for part in re.findall(r'[\u4e00-\u9fff]{2,}', cn):
            tokens.append(part)
            for w in [2, 3, 4]:
                for i in range(len(part) - w + 1):
                    tokens.append(part[i:i + w])
        stop = {'的', '了', '在', '是', '和', '就', '不', '也', '都',
                '我', '你', '他', '有', '这', '那', '吗', '呢', '吧'}
        return [t.lower() for t in tokens if t.lower() not in stop]


# =========================================================================
# Milvus 向量检索器
# =========================================================================


class MilvusRetriever(IRetriever):
    """Milvus 向量语义检索器。

    封装 VectorService，统一为 IRetriever 接口。
    不直接依赖 VectorService 导入（延迟加载避免循环引用）。
    """

    name = "milvus"

    def __init__(self):
        self._svc: Any = None

    def retrieve(self, query: str, top_k: int = 20, **kwargs) -> List[SearchResult]:
        if self._svc is None:
            try:
                from app.services.knowledge.vector_service import VectorService
                self._svc = VectorService()
            except Exception as e:
                logger.warning("[Milvus] Init failed: %s", e)
                return []

        try:
            results = self._svc.search(query, top_k=top_k)
            return [
                SearchResult(
                    chunk=Chunk(
                        id=f"milvus_{r['id']}",
                        text=r.get("content", ""),
                        doc_id=r.get("id", 0),
                        granularity="paragraph",
                    ),
                    score=float(r.get("score", 0)),
                    dense_score=float(r.get("score", 0)),
                )
                for r in results
            ]
        except Exception as e:
            logger.warning("[Milvus] Search failed: %s", e)
            return []

    def health_check(self) -> bool:
        try:
            from app.services.knowledge.vector_service import VectorService
            return VectorService().available
        except Exception:
            return False


# =========================================================================
# RRF 融合
# =========================================================================


class HybridRetriever(IRetriever):
    """混合检索器 — Dense + Sparse RRF 融合。

    RRF (Reciprocal Rank Fusion):
      score(doc) = Σ 1/(k + rank_i(doc))
      其中 k=60

    优势：
      - 不依赖分数的绝对尺度（向量分和BM25分不可比）
      - 对异常值不敏感
      - Elasticsearch 8.x 内置方案
    """

    name = "hybrid"

    def __init__(
        self,
        dense: Optional[IRetriever] = None,
        sparse: Optional[BM25Retriever] = None,
        config: Optional[RetrievalConfig] = None,
    ):
        self._dense = dense or MilvusRetriever()
        self._sparse = sparse
        self.config = config or RetrievalConfig()

    @property
    def bm25(self) -> Optional[BM25Retriever]:
        return self._sparse

    def retrieve(self, query: str, top_k: int = 20, **kwargs) -> List[SearchResult]:
        t0 = time.time()

        # 并行检索
        dense_results = self._dense.retrieve(query, self.config.dense_top_k)
        sparse_results: List[SearchResult] = []
        if self._sparse and self._sparse.health_check():
            sparse_results = self._sparse.retrieve(query, self.config.sparse_top_k)

        # RRF 融合
        fused: Dict[int, SearchResult] = {}
        k = self.config.rrf_k

        for rank, r in enumerate(dense_results):
            doc_id = r.chunk.doc_id
            rrf = 1.0 / (k + rank + 1)
            if doc_id in fused:
                fused[doc_id].score += rrf
                fused[doc_id].dense_score = r.score
            else:
                r.score = rrf
                fused[doc_id] = r

        for rank, r in enumerate(sparse_results):
            doc_id = r.chunk.doc_id
            rrf = 1.0 / (k + rank + 1)
            if doc_id in fused:
                fused[doc_id].score += rrf
                fused[doc_id].sparse_score = r.score
            else:
                r.score = rrf
                r.sparse_score = r.score
                fused[doc_id] = r

        ranked = sorted(fused.values(), key=lambda x: x.score, reverse=True)
        for i, r in enumerate(ranked):
            r.rank_position = i + 1

        elapsed = (time.time() - t0) * 1000
        logger.info(
            "[Hybrid] query=%.40s dense=%d sparse=%d fused=%d final=%d %.0fms",
            query, len(dense_results), len(sparse_results),
            len(fused), len(ranked[:top_k]), elapsed,
        )
        return ranked[:top_k]

    def health_check(self) -> bool:
        return self._dense.health_check()
