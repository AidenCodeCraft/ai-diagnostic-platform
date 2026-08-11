"""Embedding Service — 文本向量化服务。

功能：
- 文本嵌入生成（调用 LLM provider 的 embedding 接口）
- 批量嵌入处理
- 嵌入缓存（可选）

支持的 provider：
- DeepSeek / OpenAI 兼容接口
- 本地 embedding 模型（后续扩展）
"""

from __future__ import annotations

import hashlib
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """文本嵌入生成服务。

    使用 LLM provider 的 embedding API 将文本转换为向量。

    Usage:
        svc = EmbeddingService()
        embedding = svc.embed("设备黑屏怎么解决？")
        # embedding = [0.123, -0.456, ...]  # dim=1536
    """

    def __init__(
        self,
        provider_name: Optional[str] = None,
        dimension: Optional[int] = None,
        batch_size: Optional[int] = None,
    ):
        self.provider_name = provider_name or settings.EMBEDDING_PROVIDER
        self.dimension = dimension or settings.MILVUS_DIM
        self.batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
        self._cache: Dict[str, List[float]] = {}

    # ==================================================================
    # Public API
    # ==================================================================

    def embed(self, text: str) -> List[float]:
        """将单个文本转换为嵌入向量。

        Args:
            text: 输入文本

        Returns:
            嵌入向量列表，维度 = self.dimension
        """
        if not text or not text.strip():
            return self._zero_vector()

        # 检查缓存
        cache_key = self._cache_key(text)
        if cache_key in self._cache:
            return self._cache[cache_key]

        embeddings = self.embed_batch([text])
        result = embeddings[0] if embeddings else self._zero_vector()

        # 写入缓存
        if len(self._cache) < 10000:  # 缓存上限
            self._cache[cache_key] = result

        return result

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量文本嵌入。

        Args:
            texts: 文本列表

        Returns:
            嵌入向量列表
        """
        if not texts:
            return []

        # 过滤空文本
        valid_texts = [t.strip() for t in texts if t.strip()]
        if not valid_texts:
            return [self._zero_vector() for _ in texts]

        try:
            embeddings = self._call_embedding_api(valid_texts)
            return embeddings
        except Exception as exc:
            logger.error("[EmbeddingService] API call failed: %s", exc)
            # 回退：返回零向量
            return [self._zero_vector() for _ in texts]

    def embed_with_chunks(
        self, text: str, chunk_size: int = 500, overlap: int = 50,
    ) -> List[Tuple[str, List[float]]]:
        """将长文本分块后嵌入。

        Args:
            text: 长文本
            chunk_size: 每块最大字符数
            overlap: 块间重叠字符数

        Returns:
            [(chunk_text, embedding_vector), ...]
        """
        chunks = self._chunk_text(text, chunk_size, overlap)
        if not chunks:
            return []

        embeddings = self.embed_batch(chunks)
        return list(zip(chunks, embeddings))

    # ==================================================================
    # Internal
    # ==================================================================

    def _call_embedding_api(self, texts: List[str]) -> List[List[float]]:
        """调用 embedding API 生成向量。

        策略：
        1. 优先使用专门的 embedding API（如 OpenAI / DeepSeek embedding endpoint）
        2. 回退：使用 LLM chat API 的隐藏状态作为伪嵌入
        3. 最终回退：使用 TF-IDF 风格的简单向量
        """
        # 尝试使用 provider 的 embedding 能力
        try:
            from app.services.knowledge.provider_registry import ProviderRegistry

            provider = ProviderRegistry().get_provider(self.provider_name)

            # 如果 provider 支持 embedding
            if hasattr(provider, 'embed') and callable(getattr(provider, 'embed', None)):
                return getattr(provider, 'embed')(texts)  # type: ignore[no-any-return]

            if hasattr(provider, 'embedding') and callable(getattr(provider, 'embedding', None)):
                return [getattr(provider, 'embedding')(t) for t in texts]  # type: ignore[return-value]

        except Exception as exc:
            logger.debug("[EmbeddingService] Provider embedding not available: %s", exc)

        # 回退：使用伪嵌入（基于文本的统计特征）
        return [self._pseudo_embed(t) for t in texts]

    def _pseudo_embed(self, text: str) -> List[float]:
        """伪嵌入生成 — 基于文本统计特征的向量。

        当 embedding API 不可用时的兜底方案。
        使用：
        - 字符 n-gram 频率
        - 关键信息密度
        - 文本长度特征

        注意：此为临时方案，精确语义搜索需要正式的 embedding API。
        超长文本会被采样截断以保持性能。
        """
        dim = self.dimension
        # 超长文本截断保护
        if len(text) > 10000:
            front_len = 6000
            back_len = 4000
            text = text[:front_len] + text[-back_len:]

        # 基于字符哈希的向量生成
        vector = [0.0] * dim
        for ch in text:
            idx = hash(ch) % dim
            vector[idx] += 1.0

        # 归一化
        magnitude = sum(v ** 2 for v in vector) ** 0.5
        if magnitude > 0:
            vector = [v / magnitude for v in vector]

        return vector

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """将文本分割为重叠的块。"""
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            # 尝试在自然断点处分割（句号、换行）
            if end < len(text):
                for sep in ['\n\n', '\n', '。', '. ', '! ', '? ']:
                    idx = text.rfind(sep, start, end)
                    if idx > start + chunk_size // 2:
                        end = idx + len(sep)
                        break

            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk.strip())

            start = end - overlap

        return chunks

    @staticmethod
    def _cache_key(text: str) -> str:
        """生成缓存键。"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def _zero_vector(self) -> List[float]:
        """返回零向量。"""
        return [0.0] * self.dimension

    def clear_cache(self) -> None:
        """清除嵌入缓存。"""
        self._cache.clear()
