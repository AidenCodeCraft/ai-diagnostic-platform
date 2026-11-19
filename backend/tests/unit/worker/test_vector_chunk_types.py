"""向量库 chunk_type 隔离测试（不需要真实 Milvus）。"""

import pytest

from app.services.knowledge import vector_service as vs


class FakeEmbedder:
    def __init__(self, dim=8):
        self.dim = dim

    def embed(self, text):
        return [0.1] * self.dim

    def embed_batch(self, texts):
        return [[0.1] * self.dim for _ in texts]


class FakeCollection:
    def __init__(self):
        self.inserted = []
        self.deleted = []
        self.search_calls = []

    def insert(self, columns):
        self.inserted.append(columns)

    def flush(self):
        pass

    def delete(self, expr):
        self.deleted.append(expr)

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return [[]]


def build_service(monkeypatch, dim=8):
    monkeypatch.setattr(
        vs.VectorService, "available", property(lambda self: True), raising=False,
    )
    service = object.__new__(vs.VectorService)
    service._collection = FakeCollection()
    service._embedding = FakeEmbedder(dim)
    service._dim = dim
    service._connected = True
    service._schema_error = None
    service._COLLECTION_NAME = "test_chunks"
    return service


def test_compose_filter_adds_chunk_type_clause():
    assert vs.VectorService._compose_filter(None, ["section"]) == 'chunk_type in ["section"]'
    assert (
        vs.VectorService._compose_filter("doc_id > 10", ["section"])
        == '(doc_id > 10) and (chunk_type in ["section"])'
    )
    assert vs.VectorService._compose_filter("doc_id > 10", None) == "doc_id > 10"


def test_search_filters_knowledge_chunks_by_default(monkeypatch):
    service = build_service(monkeypatch)

    service.search("USB 超时", top_k=3, chunk_types=list(vs.KNOWLEDGE_CHUNK_TYPES))

    expr = service._collection.search_calls[0]["expr"]
    assert 'chunk_type in ["section"]' in expr


def test_search_without_chunk_types_has_no_filter(monkeypatch):
    service = build_service(monkeypatch)

    service.search("USB 超时", top_k=3)

    assert service._collection.search_calls[0]["expr"] is None


def test_index_document_tags_section_chunks(monkeypatch):
    service = build_service(monkeypatch)

    count = service.index_document(
        doc_id=5, content="# 4G 注册失败\n\n## 现象\n没网\n\n## 处理\n重插卡", title="4G 注册",
    )
    assert count >= 2

    columns = service._collection.inserted[-1]
    chunk_types, sources, timestamps = columns[7], columns[8], columns[9]
    assert set(chunk_types) == {"section"}
    assert set(sources) == {"knowledge"}
    assert set(timestamps) == {""}


def test_index_log_chunks_uses_negative_ids_and_tags(monkeypatch):
    service = build_service(monkeypatch)
    chunks = [
        {
            "chunk_type": vs.CHUNK_TYPE_ERROR,
            "ts": "2026-08-02 14:22:00",
            "title": "NET 2026-08-02 14:22:00",
            "section": "d1 ×3",
            "content": "[2026-08-02 14:22:00] NET 出现 3 次\nregister failed",
            "index_text": "NET\nregister failed",
            "content_hash": "d1:2026-08-02 14:22:00:NET",
        }
    ]

    count = service.index_log_chunks(log_id=7, chunks=chunks)

    assert count == 1
    columns = service._collection.inserted[-1]
    ids, doc_ids = columns[0], columns[1]
    assert ids == [-(7 * vs.MAX_CHUNKS_PER_DOC)], "日志块主键必须为负，避免与知识文档冲突"
    assert doc_ids == [0]
    assert columns[7] == [vs.CHUNK_TYPE_ERROR]
    assert columns[8] == ["log:7"]
    assert columns[9] == ["2026-08-02 14:22:00"]


def test_delete_by_expr_passes_expression(monkeypatch):
    service = build_service(monkeypatch)

    assert service.delete_by_expr('source == "log:7"') is True
    assert service._collection.deleted == ['source == "log:7"']


def test_schema_requires_chunk_type_fields():
    for name in ("chunk_type", "source", "ts"):
        assert name in vs.REQUIRED_FIELDS
    assert vs.COLLECTION_SCHEMA_VERSION == "v3"
