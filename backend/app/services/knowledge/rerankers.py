"""排序层 — Cross-Encoder Reranker + MMR 多样性控制。

硬依赖: sentence-transformers (BGE-Reranker 模型)

精排策略：
  粗排: HybridRetriever RRF 融合 → Top-20
  精排: Cross-Encoder (BGE-Reranker) → Top-5
  多样性: MMR 去重
"""

from __future__ import annotations
import logging
from typing import List, Optional, Tuple

from app.services.core.interfaces import IReranker
from app.services.core.config import RerankerConfig

logger = logging.getLogger(__name__)

# 启动依赖检查
_reranker_available = False
try:
    from sentence_transformers import CrossEncoder  # noqa: F401
    _reranker_available = True
except ImportError:
    pass


class CrossEncoderReranker(IReranker):
    """Cross-Encoder 精排器 — BGE-Reranker 模型。

    模型: BAAI/bge-reranker-base (278M, CPU ~200ms)
    """

    name = "cross_encoder"

    def __init__(self, config: Optional[RerankerConfig] = None):
        if not _reranker_available:
            raise RuntimeError(
                "Reranker 需要 sentence-transformers，请执行: pip install sentence-transformers"
            )
        self.config = config or RerankerConfig()
        self._model = None
        self._init_model()

    def rerank(
        self, query: str, documents: List[str], top_k: int = 5,
    ) -> List[Tuple[int, float]]:
        if not documents:
            return []
        pairs = [(query, doc) for doc in documents]
        try:
            scores = self._model.predict(pairs)
            ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
            return [(idx, float(score)) for idx, score in ranked[:top_k]]
        except Exception as e:
            logger.warning("[Reranker] Prediction failed: %s", e)
            return [(i, 0.0) for i in range(min(top_k, len(documents)))]

    def health_check(self) -> bool:
        return self._model is not None

    def _init_model(self) -> None:
        from sentence_transformers import CrossEncoder
        logger.info("[Reranker] Loading model: %s", self.config.model_name)
        self._model = CrossEncoder(self.config.model_name, device=self.config.device)
        logger.info("[Reranker] Model loaded")


def mmr_diversify(
    query_vec: List[float],
    doc_vecs: List[List[float]],
    lambda_param: float = 0.7,
    top_k: int = 5,
) -> List[int]:
    """最大边际相关性 (MMR) — 保持相关性的同时最大化多样性。

    MMR(d) = λ·sim(d,q) - (1-λ)·max_{d_j∈S} sim(d, d_j)
    """
    import numpy as np

    if not doc_vecs or len(doc_vecs) <= 1:
        return list(range(min(top_k, len(doc_vecs))))

    qv = np.array(query_vec)
    dvs = np.array(doc_vecs)
    q_norm = np.linalg.norm(qv) + 1e-8
    d_norms = np.linalg.norm(dvs, axis=1) + 1e-8
    sim_to_q = np.dot(dvs, qv) / (d_norms * q_norm)

    selected: List[int] = []
    remaining = list(range(len(doc_vecs)))

    while len(selected) < top_k and remaining:
        if not selected:
            best = int(np.argmax(sim_to_q[remaining]))
            selected.append(remaining.pop(best))
        else:
            sel_vecs = dvs[selected]
            sel_norms = np.linalg.norm(sel_vecs, axis=1) + 1e-8
            mmr_scores = []
            for idx in remaining:
                rel = sim_to_q[idx]
                sim_to_sel = np.dot(dvs[idx], sel_vecs.T) / (d_norms[idx] * sel_norms)
                mmr_scores.append(lambda_param * rel - (1 - lambda_param) * np.max(sim_to_sel))
            selected.append(remaining.pop(int(np.argmax(mmr_scores))))

    return selected
