"""章节级向量库 schema 与切分测试（不依赖真实 Milvus）。"""

from types import SimpleNamespace

import pytest

from app.services.knowledge.vector_service import (
    COLLECTION_SCHEMA_VERSION,
    MAX_CHUNKS_PER_DOC,
    MAX_CONTENT_LENGTH,
    REQUIRED_FIELDS,
    VectorService,
    build_collection_fields,
    build_index_params,
    build_search_params,
)


def test_index_params_are_hnsw_cosine():
    params = build_index_params()
    assert params["metric_type"] == "COSINE"
    assert params["index_type"] == "HNSW"
    assert params["params"]["M"] == 32
    assert params["params"]["efConstruction"] == 256


def test_search_params_match_index_metric():
    index = build_index_params()
    search = build_search_params()
    assert search["metric_type"] == index["metric_type"] == "COSINE"
    assert search["params"]["ef"] <= index["params"]["efConstruction"]


def test_collection_fields_cover_required_and_support_sections():
    fields = build_collection_fields(1024)
    names = [field.name for field in fields]
    for required in REQUIRED_FIELDS:
        assert required in names

    by_name = {field.name: field for field in fields}
    assert by_name["embedding"].params["dim"] == 1024
    assert by_name["content"].params["max_length"] == MAX_CONTENT_LENGTH >= 8192
    assert COLLECTION_SCHEMA_VERSION == "v3"
    # 同集合混放知识章节与日志证据块，靠 chunk_type 过滤，字段必须存在
    assert by_name["chunk_type"].params["max_length"] >= 16
    assert by_name["source"].params["max_length"] >= 64


def _service_with_collection(field_names, dim_field=1024, indexes=None):
    service = object.__new__(VectorService)
    service._collection = SimpleNamespace(
        schema=SimpleNamespace(fields=[SimpleNamespace(name=n) for n in field_names]),
        indexes=indexes or [],
    )
    service._dim = 1024
    if dim_field is not None:
        service._read_collection_dim = lambda: dim_field  # type: ignore[assignment]
    else:
        service._read_collection_dim = lambda: None  # type: ignore[assignment]
    service._COLLECTION_NAME = "knowledge_sections_v2"
    return service


def test_validate_schema_accepts_matching_collection():
    service = _service_with_collection(REQUIRED_FIELDS)
    assert service._validate_schema() is None


def test_validate_schema_rejects_legacy_document_level_collection():
    """旧版只有 id/doc_id/content/embedding —— 必须报错要求重建，而不是硬用。"""
    service = _service_with_collection(("id", "doc_id", "content", "embedding"))
    problem = service._validate_schema()
    assert problem is not None
    assert "重建集合" in problem


def test_validate_schema_rejects_dimension_mismatch():
    service = _service_with_collection(REQUIRED_FIELDS, dim_field=512)
    problem = service._validate_schema()
    assert problem is not None
    assert "512" in problem and "1024" in problem


def test_validate_schema_rejects_wrong_metric():
    service = _service_with_collection(
        REQUIRED_FIELDS,
        indexes=[SimpleNamespace(params={"metric_type": "IP"})],
    )
    problem = service._validate_schema()
    assert problem is not None
    assert "IP" in problem


def test_build_chunks_splits_sections_and_prefixes_title():
    content = "# 现象\nGPS 不上报\n\n## 排查步骤\n1. 检查天线\n2. 检查固件版本\n"
    title, chunks = VectorService._build_chunks(1, content, doc_title="L10 GPS 排查")

    assert title == "L10 GPS 排查"
    assert len(chunks) == 2
    assert chunks[0]["section"] == "现象"
    assert chunks[0]["index_text"].startswith("L10 GPS 排查")
    assert "排查步骤" in chunks[1]["section"]
    assert all(chunk["content_hash"] for chunk in chunks)


def test_build_chunks_falls_back_to_first_line_as_title():
    _, chunks = VectorService._build_chunks(2, "无标题的说明文档正文内容。")
    assert len(chunks) == 1
    assert chunks[0]["title"].startswith("无标题")
    assert chunks[0]["section"] == ""


def test_chunks_hash_is_stable():
    content = "## 一节\n内容 A\n"
    _, first = VectorService._build_chunks(3, content)
    _, second = VectorService._build_chunks(3, content)
    assert first[0]["content_hash"] == second[0]["content_hash"]


def test_primary_key_scheme_allows_plenty_of_chunks():
    """主键 = doc_id * MAX_CHUNKS_PER_DOC + i；上限必须够章节级切分用。"""
    assert MAX_CHUNKS_PER_DOC >= 10000
    assert (2 * MAX_CHUNKS_PER_DOC + 5) % MAX_CHUNKS_PER_DOC == 5
