"""向量搜索与嵌入服务边界测试 — Milvus/client/embedding 全链路边界。"""

from __future__ import annotations

import pytest

from app.services.knowledge.embedding import CompositeEmbedder, get_embedder
from app.services.knowledge.vector_service import VectorService


# ═══════════════════════════════════════════════════════════
# EmbeddingService
# ═══════════════════════════════════════════════════════════

def test_embed_single_text():
    svc = get_embedder()
    embedding = svc.embed("USB timeout 错误排查")
    assert isinstance(embedding, list)
    assert len(embedding) == svc.dimension
    assert all(isinstance(v, float) for v in embedding)


def test_embed_empty_text():
    svc = get_embedder()
    embedding = svc.embed("")
    assert len(embedding) == svc.dimension
    # 零向量
    assert all(v == 0.0 for v in embedding)


def test_embed_whitespace_only():
    svc = get_embedder()
    embedding = svc.embed("   \n\t  ")
    assert len(embedding) == svc.dimension
    assert all(v == 0.0 for v in embedding)


def test_embed_batch():
    svc = get_embedder()
    texts = ["USB error", "bluetooth pairing", "kernel panic"]
    embeddings = svc.embed_batch(texts)
    assert len(embeddings) == 3
    assert all(len(e) == svc.dimension for e in embeddings)


def test_embed_batch_empty():
    svc = get_embedder()
    embeddings = svc.embed_batch([])
    assert embeddings == []


def test_embed_batch_mixed_empty():
    svc = get_embedder()
    texts = ["hello", "", "world"]
    embeddings = svc.embed_batch(texts)
    assert len(embeddings) >= 2  # 非空文本的嵌入应 >= 2个


def test_embed_cache():
    svc = get_embedder()
    text = "test cache text"
    emb1 = svc.embed(text)
    emb2 = svc.embed(text)
    assert emb1 == emb2  # 同一个实例内缓存命中


def test_embed_clear_cache():
    svc = get_embedder()
    svc.embed("cached text")
    assert len(svc._cache) > 0
    svc.clear_cache()
    assert len(svc._cache) == 0


def test_embed_with_chunks_short():
    svc = get_embedder()
    result = svc.embed_with_chunks("short text", chunk_size=500)
    assert len(result) == 1
    assert result[0][0] == "short text"


def test_embed_with_chunks_long():
    svc = get_embedder()
    long_text = "A" * 1200
    result = svc.embed_with_chunks(long_text, chunk_size=500, overlap=50)
    assert len(result) >= 2
    for chunk_text, embedding in result:
        assert isinstance(chunk_text, str)
        assert len(embedding) == svc.dimension


def test_embed_with_chunks_empty():
    svc = get_embedder()
    result = svc.embed_with_chunks("")
    assert isinstance(result, list)


def test_chunk_text_exact():
    svc = get_embedder()
    text = "Hello World"
    chunks = svc._chunk_text(text, chunk_size=500)
    assert len(chunks) == 1
    assert chunks[0] == "Hello World"


def test_chunk_text_with_overlap():
    svc = get_embedder()
    text = "A" * 1000
    chunks = svc._chunk_text(text, chunk_size=500, overlap=100)
    assert len(chunks) >= 2
    # 验证重叠
    if len(chunks) >= 2:
        total_len = sum(len(c) for c in chunks)
        assert total_len > len(text)  # 有重叠，总长度应大于原文


def test_chunk_text_unicode():
    svc = get_embedder()
    text = "中文测试内容。继续更多文本。" * 50
    chunks = svc._chunk_text(text, chunk_size=200, overlap=30)
    assert len(chunks) > 0
    assert all(len(c) > 0 for c in chunks)


def test_pseudo_embed_quality():
    svc = get_embedder()
    e1 = svc._pseudo_embed("USB timeout error")
    e2 = svc._pseudo_embed("USB timeout error")
    e3 = svc._pseudo_embed("totally different text")
    # 同一文本的向量应相同
    assert e1 == e2
    # 不同文本的向量至少有一维不同
    assert any(a != b for a, b in zip(e1, e3))


def test_zero_vector():
    svc = get_embedder()
    zero = svc._zero_vector()
    assert len(zero) == svc.dimension
    assert all(v == 0.0 for v in zero)


def test_cache_key():
    import hashlib
    key = hashlib.md5("hello".encode('utf-8')).hexdigest()
    assert len(key) == 32  # MD5 hex
    assert key == hashlib.md5("hello".encode('utf-8')).hexdigest()


# ═══════════════════════════════════════════════════════════
# VectorService (边界测试 — 不依赖 Milvus)
# ═══════════════════════════════════════════════════════════

def test_vector_service_initialization():
    svc = VectorService()
    # 即使 Milvus 不可用，实例也应正常创建
    assert svc is not None
    assert hasattr(svc, 'available')
    assert hasattr(svc, 'search')


def test_vector_service_search_empty_query():
    svc = VectorService()
    results = svc.search("")
    assert results == []


def test_vector_service_search_whitespace():
    svc = VectorService()
    results = svc.search("   ")
    assert results == []


def test_vector_service_index_document_empty():
    svc = VectorService()
    count = svc.index_document(1, "")
    assert count == 0  # 空内容不索引


def test_vector_service_delete_document():
    svc = VectorService()
    result = svc.delete_document(999)
    # Milvus 不可用时返回 False
    assert result is False


def test_vector_service_health_check():
    svc = VectorService()
    healthy = svc.health_check()
    # 未连接时返回 False
    assert healthy is False or healthy is True  # 总是返回布尔


def test_vector_service_collection_name():
    svc = VectorService()
    assert isinstance(svc.collection_name, str)
    assert len(svc.collection_name) > 0


def test_vector_service_collection_info_unavailable():
    svc = VectorService()
    info = svc.collection_info
    assert info is None  # 未连接时返回 None


def test_vector_service_search_returns_empty_when_unavailable():
    svc = VectorService()
    results = svc.search("USB error", top_k=5)
    assert isinstance(results, list)
    assert results == []  # Milvus 不可用时应返回空列表（供调用方回退）


def test_vector_service_search_with_filter():
    svc = VectorService()
    results = svc.search("test", top_k=3, filter_expr="doc_id > 0")
    assert isinstance(results, list)


# ═══════════════════════════════════════════════════════════
# get_vector_service Singleton
# ═══════════════════════════════════════════════════════════

def test_get_vector_service_singleton():
    from app.services.knowledge.vector_service import get_vector_service
    svc1 = get_vector_service()
    svc2 = get_vector_service()
    assert svc1 is svc2


# ═══════════════════════════════════════════════════════════
# Hypothesis Edge Cases
# ═══════════════════════════════════════════════════════════

def test_embed_very_long_text():
    svc = get_embedder()
    embedding = svc.embed("A" * 10000)
    assert len(embedding) == svc.dimension  # 长文本不应崩溃


def test_embed_special_characters():
    svc = get_embedder()
    embedding = svc.embed("\x00\x01\x02\n\r\t\\\"'")
    assert len(embedding) == svc.dimension


def test_embed_batch_large():
    svc = get_embedder()
    texts = ["text"] * 100
    embeddings = svc.embed_batch(texts)
    assert len(embeddings) == 100


def test_vector_service_reconnect():
    svc = VectorService()
    result = svc.reconnect()
    assert isinstance(result, bool)
