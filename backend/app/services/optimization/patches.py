"""Embedding 服务优化补丁 — 添加缓存支持 + 限流保护。

将优化模块集成到 embedding_service 中，主要改动：
1. 嵌入结果缓存（LRU + TTL）
2. 批量嵌入限流
3. 性能计时
"""

from __future__ import annotations

from typing import List, Optional

from app.services.knowledge.embedding_service import EmbeddingService as _BaseEmbedding
from app.services.optimization.cache_manager import EmbeddingCache
from app.services.optimization.connection_pool import (
    embedding_throttle,
    get_timer,
    time_operation,
)
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class OptimizedEmbeddingService(_BaseEmbedding):
    """带缓存优化的 Embedding 服务。

    优化措施：
    1. 嵌入缓存：同一文本 1 小时内不重复计算
    2. 限流保护：防止并发请求 overrun
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._result_cache = EmbeddingCache(
            max_size=5000,
            ttl_seconds=3600,
        )

    def embed(self, text: str) -> List[float]:
        """缓存增强的单文本嵌入。"""
        if not text or not text.strip():
            return self._zero_vector()

        # 先查缓存
        cached = self._result_cache.get_embedding(text)
        if cached is not None:
            return cached

        # 限流检查
        if not embedding_throttle.acquire():
            logger.warning("[OptimizedEmbedding] Throttled: %s...", text[:50])
            return self._pseudo_embed(text)  # 降级为伪嵌入

        with time_operation("embedding.single"):
            result = super().embed(text)

        # 写入缓存
        self._result_cache.set_embedding(text, result)
        return result

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """缓存增强的批量嵌入。"""
        if not texts:
            return []

        results = []
        uncached_texts = []
        uncached_indices = []

        # 检查每个文本的缓存
        for i, text in enumerate(texts):
            if not text or not text.strip():
                results.append(self._zero_vector())
                continue

            cached = self._result_cache.get_embedding(text)
            if cached is not None:
                results.append(cached)
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)

        if uncached_texts:
            with time_operation("embedding.batch"):
                new_embeddings = super().embed_batch(uncached_texts)

            # 写入缓存 + 填充结果
            for idx, (text, emb) in enumerate(zip(uncached_texts, new_embeddings)):
                self._result_cache.set_embedding(text, emb)
                # 按原始顺序插入
                original_idx = uncached_indices[idx]
                if original_idx >= len(results):
                    results.extend([None] * (original_idx - len(results) + 1))
                results[original_idx] = emb

        return results

    def clear_cache(self) -> None:
        super().clear_cache()
        self._result_cache.clear()

    @property
    def cache_stats(self):
        return self._result_cache.stats


# Monkey-patch: 在运行时替换 EmbeddingService 为优化版
_patch_applied = False


def apply_optimizations():
    """应用 Embedding 优化补丁。"""
    global _patch_applied
    if _patch_applied:
        return

    import app.services.knowledge.embedding_service as mod
    mod.EmbeddingService = OptimizedEmbeddingService
    _patch_applied = True
    logger.info("[Optimization] EmbeddingService 已替换为 OptimizedEmbeddingService")
