"""检索轨迹落库测试 —— 必须记录成功、失败绝不外抛。"""

import pytest

from app.models import RetrievalTrace
from app.services.quality.trace_service import (
    CONCLUSION_ANSWERED,
    CONCLUSION_ASK_SLOT,
    CONCLUSION_REFUSED,
    record_trace,
    resolve_conclusion,
)


def test_record_trace_persists_candidates(db_session):
    trace = record_trace(
        db_session,
        session_id=None,
        question="L10 黑屏怎么办",
        references=[
            {"id": 7, "title": "显示异常排查", "section": "黑屏", "score": 0.82, "key": "7:黑屏"},
            {"id": 8, "title": "电源排查", "section": "供电", "score": 0.41},
        ],
        conclusion=CONCLUSION_ANSWERED,
        timings={"kb_ms": 120},
    )
    assert trace is not None

    stored = db_session.query(RetrievalTrace).one()
    assert stored.question == "L10 黑屏怎么办"
    assert [c["doc_id"] for c in stored.kb_candidates["candidates"]] == [7, 8]
    assert stored.kb_candidates["candidates"][0]["section"] == "黑屏"
    assert stored.conclusion == CONCLUSION_ANSWERED
    assert stored.timings["kb_ms"] == 120
    assert stored.pipeline_version


def test_record_trace_never_raises(db_session, monkeypatch):
    def boom(_self):
        raise RuntimeError("disk full")

    monkeypatch.setattr(type(db_session), "commit", boom, raising=False)
    assert record_trace(db_session, session_id=None, question="x") is None


@pytest.mark.parametrize(
    "direct_reply,clarification,expected",
    [
        (None, None, CONCLUSION_ANSWERED),
        (None, [], CONCLUSION_ANSWERED),
        ("请补充设备型号", [{"slot": "device"}], CONCLUSION_ASK_SLOT),
        ("无法回答该问题", [], CONCLUSION_REFUSED),
    ],
)
def test_resolve_conclusion(direct_reply, clarification, expected):
    assert resolve_conclusion(direct_reply, clarification) == expected
