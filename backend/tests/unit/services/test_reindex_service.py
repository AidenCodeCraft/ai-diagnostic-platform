"""回填流程测试 —— 前置守卫 + 遍历统计 + 单篇失败隔离。"""

from types import SimpleNamespace

import pytest

from app.models import KnowledgeDocument
from app.services.knowledge.reindex_service import (
    ReindexError,
    check_environment,
    run_reindex,
)


def _ok_vector_service(dim=1024):
    return SimpleNamespace(
        available=True,
        dimension=dim,
        schema_error=None,
        collection_name="knowledge_sections_v2",
    )


def _ok_embedder(dim=1024):
    return SimpleNamespace(provider_name="BGEEmbedder", dimension=dim)


class RecordingIndexer:
    def __init__(self, chunks_per_doc=2, fail_ids=()):
        self.calls = []
        self.chunks_per_doc = chunks_per_doc
        self.fail_ids = set(fail_ids)

    def index_document(self, doc_id, content=None):
        self.calls.append(doc_id)
        if doc_id in self.fail_ids:
            raise RuntimeError("boom")
        return self.chunks_per_doc


def test_check_environment_accepts_semantic_setup():
    env = check_environment(_ok_vector_service(), _ok_embedder())
    assert env["provider"] == "BGEEmbedder"
    assert env["dimension"] == 1024
    assert env["collection"] == "knowledge_sections_v2"


def test_check_environment_rejects_hash_embedder():
    with pytest.raises(ReindexError) as exc:
        check_environment(_ok_vector_service(), SimpleNamespace(provider_name="HashingEmbedder", dimension=512))
    assert "哈希兜底" in str(exc.value)


def test_check_environment_rejects_schema_mismatch():
    svc = _ok_vector_service()
    svc.schema_error = "向量维度 512 与配置 MILVUS_DIM=1024 不一致"
    with pytest.raises(ReindexError) as exc:
        check_environment(svc, _ok_embedder())
    assert "不兼容" in str(exc.value)


def test_check_environment_rejects_dimension_mismatch():
    with pytest.raises(ReindexError) as exc:
        check_environment(_ok_vector_service(dim=512), _ok_embedder(dim=1024))
    assert "维度" in str(exc.value)


def test_check_environment_rejects_unavailable_service():
    svc = _ok_vector_service()
    svc.available = False
    with pytest.raises(ReindexError):
        check_environment(svc, _ok_embedder())


@pytest.fixture
def docs(db_session):
    rows = [
        KnowledgeDocument(title="GPS 排查", content="# 现象\nGPS 不上报\n", status="active"),
        KnowledgeDocument(title="空文档", content="   ", status="active"),
        KnowledgeDocument(title="电源排查", content="## 供电\n检查电压\n", status="active"),
    ]
    db_session.add_all(rows)
    db_session.commit()
    for row in rows:
        db_session.refresh(row)
    return rows


def test_run_reindex_indexes_documents_and_skips_empty(db_session, docs):
    indexer = RecordingIndexer(chunks_per_doc=3)

    stats = run_reindex(db_session, indexer=indexer)

    assert stats.total_docs == 3
    assert stats.indexed_docs == 2
    assert stats.empty_docs == 1
    assert stats.total_chunks == 6
    assert stats.failed == []
    failed_ids = {row.id for row in docs if not str(row.content).strip()}
    assert set(indexer.calls).isdisjoint(failed_ids)


def test_run_reindex_records_single_document_failure(db_session, docs):
    bad_doc_id = docs[0].id
    indexer = RecordingIndexer(fail_ids={bad_doc_id})

    stats = run_reindex(db_session, indexer=indexer)

    assert stats.indexed_docs == 1
    assert len(stats.failed) == 1
    assert stats.failed[0]["doc_id"] == bad_doc_id
    assert "boom" in stats.failed[0]["error"]


def test_run_reindex_respects_start_id_and_limit(db_session, docs):
    indexer = RecordingIndexer()
    first, _, third = docs

    stats = run_reindex(db_session, start_id=first.id, limit=1, indexer=indexer)

    assert stats.total_docs == 1
    assert indexer.calls == []


def test_dry_run_does_not_write(db_session, docs):
    stats = run_reindex(db_session, dry_run=True)

    assert stats.total_docs == 3
    assert stats.indexed_docs == 2  # 非空文档计数
    assert stats.total_chunks == 0
