"""质量度量相关模型的结构与状态约束测试。"""

from datetime import datetime, timezone

import pytest

from app.database.base import Base
from app.models import (
    EXPECTED_CONCLUSIONS,
    GOLDEN_SAMPLE_STATUSES,
    STATUS_TRANSITIONS,
    GoldenSample,
    RegressionRun,
    RetrievalTrace,
    SampleReview,
)


def test_tables_registered_in_metadata():
    """四张新表必须挂到 Base.metadata，否则 create_all/迁移不会建表。"""
    for table in ("retrieval_traces", "golden_samples", "sample_reviews", "regression_runs"):
        assert table in Base.metadata.tables, f"missing table: {table}"


def test_status_transitions_are_consistent():
    """状态机必须覆盖所有状态，且目标状态合法、不跳级。"""
    for status in GOLDEN_SAMPLE_STATUSES:
        assert status in STATUS_TRANSITIONS, f"no transitions declared for {status}"
    for source, targets in STATUS_TRANSITIONS.items():
        assert source in GOLDEN_SAMPLE_STATUSES
        for target in targets:
            assert target in GOLDEN_SAMPLE_STATUSES, f"{source} -> unknown {target}"

    # 三级审核不可跳级：初审只能到复审，复审只能到终审
    assert STATUS_TRANSITIONS["pending_test"] == ("pending_dev", "rejected")
    assert STATUS_TRANSITIONS["pending_dev"] == ("pending_admin", "rejected")
    assert STATUS_TRANSITIONS["pending_admin"] == ("approved", "rejected")
    # approved 不能被直接编辑回草稿，只能打回重审（回到 pending_test）或标记失效
    assert set(STATUS_TRANSITIONS["approved"]) == {"pending_test", "superseded"}


def test_expected_conclusions_cover_negative_cases():
    """必须有拒答/追问/时间错配三类负样本口径，只测 answered 会偏乐观。"""
    assert set(EXPECTED_CONCLUSIONS) == {"answered", "refused", "ask_slot", "time_mismatch"}


def test_trace_and_sample_roundtrip(db_session):
    trace = RetrievalTrace(
        question="L10 在 2026-08-02 14:22 黑屏，GPS 不上报",
        slots={
            "city": "深圳", "device": "L10", "phenomenon": "黑屏",
            "time_beijing": "2026-08-02 14:22:00", "has_attachment": True,
        },
        kb_candidates={"candidates": [{"pk": "abc", "doc_id": 1, "section": "GPS 排查", "score": 0.82}]},
        log_patterns={"patterns": [{"pattern": "NMEA", "type": "literal", "source_chunk": "abc"}]},
        log_blocks={"time_range": ["2026-08-02 14:22:00", "2026-08-02 14:27:00"], "blocks": []},
        timings={"kb_ms": 820, "locate_ms": 410},
        conclusion="answered",
        pipeline_version="p1",
    )
    db_session.add(trace)
    db_session.commit()

    sample = GoldenSample(
        question=trace.question,
        slots=trace.slots,
        kb_expected=[{"doc_id": 1, "section": "GPS 排查", "pk": "abc"}],
        log_expected={"must_hit_patterns": ["NMEA"]},
        expected_conclusion="answered",
        category="定位异常",
        device_model="L10",
        status="pending_test",
        submitted_by=None,
        trace_id=trace.id,
    )
    db_session.add(sample)
    db_session.commit()

    review = SampleReview(
        sample_id=sample.id, sample_version=1, actor_name="qa01",
        role="test", action="approve", reason="期望章节正确",
    )
    run = RegressionRun(
        run_id="run-1", commit_sha="deadbeef", triggered_by="ci",
        total_samples=1, passed=1, failed=0,
        metrics={"recall_at_5": 1.0}, status="passed",
        started_at=datetime.now(timezone.utc),
    )
    db_session.add_all([review, run])
    db_session.commit()

    assert db_session.query(GoldenSample).count() == 1
    assert db_session.query(SampleReview).count() == 1
    assert db_session.query(RegressionRun).filter_by(run_id="run-1").one().metrics["recall_at_5"] == 1.0

    stored = db_session.query(RetrievalTrace).one()
    assert stored.slots["city"] == "深圳"
    assert stored.log_patterns["patterns"][0]["pattern"] == "NMEA"


def test_sample_version_defaults_to_one(db_session):
    sample = GoldenSample(question="q", expected_conclusion="refused")
    db_session.add(sample)
    db_session.commit()
    db_session.refresh(sample)
    assert sample.sample_version == 1
    assert sample.status == "draft"
