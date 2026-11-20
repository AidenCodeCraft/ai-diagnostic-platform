"""P3 观测指标测试（只读数据库，不连 broker / Milvus）。"""

from datetime import datetime, timedelta, timezone

from app.models import AgentTask, RetrievalTrace
from app.services.diagnostics.pipeline_metrics import PipelineMetrics


def _task(db, task_id, stage, status, error=None, age_seconds=0):
    task = AgentTask(
        task_id=task_id,
        log_id=1,
        status=status,
        state=stage,
        error_message=error,
        updated_at=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
    )
    db.add(task)
    db.commit()
    return task


def test_ingest_stats_counts_and_failures(db_session):
    _task(db_session, "1:parse:0", "parse", "succeeded")
    _task(db_session, "1:parse:1", "parse", "succeeded")
    _task(db_session, "1:template:0", "template", "failed", error="boom")
    _task(db_session, "1:compress:0", "compress", "running", age_seconds=120)

    stats = PipelineMetrics(db_session).ingest_stats()

    assert stats["total"] == 4
    assert stats["by_status"]["succeeded"] == 2
    assert stats["by_stage"]["parse"]["succeeded"] == 2
    assert stats["healthy"] is False
    assert stats["failed"][0]["error"] == "boom"
    assert stats["running_oldest_seconds"] >= 100


def test_ingest_stats_healthy_when_no_failures(db_session):
    _task(db_session, "1:parse:0", "parse", "succeeded")
    stats = PipelineMetrics(db_session).ingest_stats()
    assert stats["healthy"] is True
    assert stats["failed"] == []


def _trace(db, question, total_ms, candidates, conclusion):
    trace = RetrievalTrace(
        question=question,
        timings={"total_ms": total_ms, "kb_ms": total_ms / 2},
        kb_candidates={"candidates": candidates},
        conclusion=conclusion,
    )
    db.add(trace)
    db.commit()
    return trace


def test_retrieval_stats_zero_hit_and_latency(db_session):
    _trace(db_session, "q1", 100, [{"section": "现象"}], "answered")
    _trace(db_session, "q2", 200, [{"section": "现象"}], "answered")
    _trace(db_session, "q3", 900, [], "no_kb_entry")
    _trace(db_session, "q4", 300, [], "ask_slot")

    stats = PipelineMetrics(db_session).retrieval_stats(window_hours=24)

    assert stats["count"] == 4
    assert stats["zero_hit_rate"] == 0.5
    assert stats["latency_ms"]["p50"] is not None
    assert stats["latency_ms"]["max"] == 900
    assert stats["conclusions"]["answered"] == 2


def test_retrieval_stats_empty_window_is_none_not_zero(db_session):
    stats = PipelineMetrics(db_session).retrieval_stats()
    assert stats["count"] == 0
    assert stats["zero_hit_rate"] is None
    assert stats["latency_ms"]["p50"] is None


def test_retrieval_stats_respects_window(db_session):
    old = RetrievalTrace(
        question="old",
        timings={"total_ms": 50},
        kb_candidates={"candidates": [{"section": "x"}]},
        conclusion="answered",
        created_at=datetime.now(timezone.utc) - timedelta(hours=48),
    )
    db_session.add(old)
    db_session.commit()

    assert PipelineMetrics(db_session).retrieval_stats(window_hours=24)["count"] == 0
    assert PipelineMetrics(db_session).retrieval_stats(window_hours=72)["count"] == 1


class FakeEmbedder:
    provider_name = "BGEEmbedder"
    dimension = 1024


class FakeService:
    collection_name = "knowledge_chunks_v3"
    available = True
    schema_error = None
    _collection = None


def test_vector_health_reports_semantic_provider(db_session, monkeypatch):
    import app.services.knowledge.embedding as embedding_module

    monkeypatch.setattr(embedding_module, "get_embedder", lambda: FakeEmbedder())

    health = PipelineMetrics(db_session, vector_service=FakeService()).vector_health()

    assert health["embedding_provider"] == "BGEEmbedder"
    assert health["embedding_dimension"] == 1024
    assert health["is_semantic"] is True
    assert health["collection"] == "knowledge_chunks_v3"
    assert health["schema_error"] is None


def test_vector_health_flags_hashing_provider(db_session, monkeypatch):
    import app.services.knowledge.embedding as embedding_module

    class HashEmbedder:
        provider_name = "HashingEmbedder"
        dimension = 512

    monkeypatch.setattr(embedding_module, "get_embedder", lambda: HashEmbedder())

    health = PipelineMetrics(db_session, vector_service=FakeService()).vector_health()
    assert health["is_semantic"] is False


def test_pipeline_health_endpoint(client, admin_headers):
    resp = client.get("/api/v1/logs/pipeline/health", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) >= {"ingest", "retrieval", "vector", "generated_at"}
    assert body["ingest"]["total"] >= 0


def test_image_cost_stats_sums_usage(db_session):
    from app.models import ChatImageUpload

    db_session.add_all([
        ChatImageUpload(
            filename="a.png", status="succeeded", recognize_path="ocr",
            usage={"ocr_pages": 2},
        ),
        ChatImageUpload(
            filename="b.png", status="succeeded", recognize_path="ocr+vision",
            usage={"ocr_pages": 1, "vision_usage": {"prompt_tokens": 1300, "completion_tokens": 300}},
        ),
        ChatImageUpload(filename="c.png", status="failed"),
    ])
    db_session.commit()

    stats = PipelineMetrics(db_session).image_cost_stats(window_hours=24)

    assert stats["images"] == 3
    assert stats["by_status"]["succeeded"] == 2
    assert stats["ocr_pages"] == 3
    assert stats["vision_input_tokens"] == 1300
    assert stats["vision_output_tokens"] == 300
    # 3 页 OCR + 1300 输入 + 300 输出
    expected = 3 * 0.0015 + 1300 * 2 / 1e6 + 300 * 8 / 1e6
    assert abs(stats["estimated_cost_yuan"] - round(expected, 4)) < 1e-6


def test_image_cost_stats_handles_empty_usage(db_session):
    from app.models import ChatImageUpload

    db_session.add(ChatImageUpload(filename="x.png", status="pending", usage=None))
    db_session.commit()

    stats = PipelineMetrics(db_session).image_cost_stats()
    assert stats["images"] == 1
    assert stats["estimated_cost_yuan"] == 0


def test_snapshot_includes_image_cost(client, admin_headers):
    body = client.get("/api/v1/logs/pipeline/health", headers=admin_headers).json()
    assert "image_cost" in body
    assert "estimated_cost_yuan" in body["image_cost"]
