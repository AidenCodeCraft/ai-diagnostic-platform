"""Embedding 层：provider 选择、哈希兜底、维度对齐。"""

import math

from app.services.core.config import EmbeddingConfig
from app.services.knowledge.embedding import (
    EmbeddingService,
    HashingEmbedder,
)


class TestHashingEmbedder:
    def test_dimension_from_config(self):
        embedder = HashingEmbedder(EmbeddingConfig(dimension=64))
        assert embedder.dimension == 64

    def test_embedding_is_deterministic_and_normalized(self):
        embedder = HashingEmbedder(EmbeddingConfig(dimension=64))
        first = embedder.embed("USB timeout 超时问题")
        second = embedder.embed("USB timeout 超时问题")
        assert first == second
        norm = math.sqrt(sum(v * v for v in first))
        assert abs(norm - 1.0) < 1e-6

    def test_different_texts_differ(self):
        embedder = HashingEmbedder(EmbeddingConfig(dimension=64))
        assert embedder.embed("USB timeout") != embedder.embed("蓝牙连接失败")

    def test_empty_text_returns_zero_vector(self):
        embedder = HashingEmbedder(EmbeddingConfig(dimension=32))
        vec = embedder.embed("")
        assert len(vec) == 32
        assert all(v == 0.0 for v in vec)


class TestEmbeddingServiceSelection:
    def test_hash_provider_explicit(self):
        service = EmbeddingService(EmbeddingConfig(provider="hash", dimension=128))
        assert service.provider_name == "HashingEmbedder"
        assert service.dimension == 128
        assert len(service.embed("设备日志")) == 128
        assert service.health_check() is True

    def test_hash_provider_batch(self):
        service = EmbeddingService(EmbeddingConfig(provider="hash", dimension=32))
        vectors = service.embed_batch(["a", "b", ""])
        assert len(vectors) == 3
        assert all(len(v) == 32 for v in vectors)
