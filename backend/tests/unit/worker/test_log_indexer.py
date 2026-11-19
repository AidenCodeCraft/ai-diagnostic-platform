"""日志证据块聚合测试（P2：chunk_type=error/template）。"""

from app.services.diagnostics.log_indexer import (
    LogChunkIndexer,
    build_log_chunks,
    is_error_line,
)
from app.services.knowledge.vector_service import CHUNK_TYPE_ERROR, CHUNK_TYPE_TEMPLATE


def _rec(ts, text, module="NET"):
    return {"ts": ts, "module": module, "text": text, "masked": text}


def test_error_detection():
    assert is_error_line("[NET] register failed, ret=-1")
    assert is_error_line("[APP] 连接超时")
    assert not is_error_line("[APP] boot ok")


def test_same_template_in_bucket_is_aggregated():
    records = [
        _rec("2026-08-02 14:22:00", "[NET] register failed ret=-1"),
        _rec("2026-08-02 14:22:09", "[NET] register failed ret=-2"),
        _rec("2026-08-02 14:22:40", "[NET] register failed ret=-3"),
    ]
    chunks = build_log_chunks(records)

    assert len(chunks) == 1
    assert chunks[0].chunk_type == CHUNK_TYPE_ERROR
    assert "出现 3 次" in chunks[0].content
    assert chunks[0].ts == "2026-08-02 14:22:00"


def test_single_normal_line_is_dropped():
    chunks = build_log_chunks([_rec("2026-08-02 10:00:00", "[APP] boot ok")])
    assert chunks == [], "一次性正常日志没有诊断价值，不该入向量库"


def test_repeated_normal_template_becomes_template_chunk():
    records = [_rec("2026-08-02 10:00:0%d" % i, "[APP] Volume:27, 20, 20") for i in range(3)]
    chunks = build_log_chunks(records)

    assert len(chunks) == 1
    assert chunks[0].chunk_type == CHUNK_TYPE_TEMPLATE


def test_different_buckets_are_separate_chunks():
    records = [
        _rec("2026-08-02 10:00:10", "[NET] register failed"),
        _rec("2026-08-02 10:05:10", "[NET] register failed"),
    ]
    chunks = build_log_chunks(records)

    assert len(chunks) == 2
    assert {c.ts for c in chunks} == {"2026-08-02 10:00:00", "2026-08-02 10:05:00"}


def test_error_chunks_sorted_first():
    records = [_rec("2026-08-02 10:00:0%d" % i, "[APP] Volume:27") for i in range(3)]
    records.append(_rec("2026-08-02 10:00:30", "[NET] register failed"))

    chunks = build_log_chunks(records)

    assert chunks[0].chunk_type == CHUNK_TYPE_ERROR


def test_chunk_cap_is_enforced():
    records = []
    for minute in range(10):
        for i in range(2):
            records.append(_rec(f"2026-08-02 10:{minute:02d}:0{i}", f"[NET] err code {minute} timeout"))
    chunks = build_log_chunks(records, max_chunks=3)
    assert len(chunks) == 3


class FakeVectorService:
    def __init__(self):
        self.deleted = []
        self.indexed = []

    def delete_by_expr(self, expr):
        self.deleted.append(expr)
        return True

    def index_log_chunks(self, log_id, chunks):
        self.indexed.append((log_id, chunks))
        return len(chunks)


def test_index_log_is_idempotent_and_tagged():
    service = FakeVectorService()
    indexer = LogChunkIndexer(vector_service=service)
    records = [_rec("2026-08-02 14:22:00", "[NET] register failed")]

    result = indexer.index_log(7, records)

    assert service.deleted == ['source == "log:7"'], "重新索引必须先清旧块"
    log_id, chunks = service.indexed[0]
    assert log_id == 7
    assert chunks[0]["chunk_type"] == CHUNK_TYPE_ERROR
    assert chunks[0]["ts"] == "2026-08-02 14:22:00"
    assert result["indexed"] == 1
    assert result["error_chunks"] == 1


def test_index_log_with_no_chunks_skips_writes():
    service = FakeVectorService()
    indexer = LogChunkIndexer(vector_service=service)

    result = indexer.index_log(7, [])

    assert result["indexed"] == 0
    assert service.deleted == []
    assert service.indexed == []
