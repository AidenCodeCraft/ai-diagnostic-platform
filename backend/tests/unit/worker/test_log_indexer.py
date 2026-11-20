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


def test_build_log_chunks_batches_template_ids(monkeypatch):
    """模板 id 必须批量生成：逐行调用会逐行抢模板库文件锁（100MB 卡十几分钟）。"""
    import app.services.diagnostics.log_indexer as indexer
    import app.worker.ingest_service as svc

    calls = {"batch": 0, "single": 0}
    real_batch = svc.template_ids_batch
    real_single = svc.template_id

    def batch_spy(lines):
        calls["batch"] += 1
        return real_batch(lines)

    def single_spy(line, **kw):
        calls["single"] += 1
        return real_single(line, **kw)

    monkeypatch.setattr(svc, "template_source", lambda: "fallback-hash")
    monkeypatch.setattr(indexer, "template_ids_batch", batch_spy)
    monkeypatch.setattr(indexer, "template_id", single_spy, raising=False)

    records = [{"ts": "2026-11-20 08:00:00", "module": "0719", "text": f"connect failed #{i % 3}"} for i in range(50)]
    chunks = indexer.build_log_chunks(records)

    assert calls["single"] == 0, "不应再逐行生成模板 id"
    assert calls["batch"] >= 1
    assert chunks
