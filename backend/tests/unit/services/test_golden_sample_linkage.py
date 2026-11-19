"""知识条目变更 → 黄金集联动测试。

背景：知识自进化审核（/admin/knowledge/profiles）上线候选会改变检索语料，
已 approved 的黄金样本期望可能失效。联动规则：
  - 上线后把「kb_expected 引用了该文档」的 approved 样本标记 needs_recheck；
  - 标记后不再参与回归导出（避免知识库改对了反而变红）；
  - 管理员复核确认后可直接回到 approved（内容未改，不走审核链）。
"""

import pytest

from app.models import GoldenSample, KnowledgeDiagnosisProfile, KnowledgeDocument, SampleReview, User
from app.services.quality import GoldenSampleError, GoldenSampleService


@pytest.fixture
def admin(db_session):
    user = User(username="admin_link", role="admin")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def doc_with_profile(db_session):
    doc = KnowledgeDocument(
        title="L10 GPS 不上报排查", content="## 现象\nGPS 不上报\n", status="draft",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    profile = KnowledgeDiagnosisProfile(
        doc_id=doc.id, symptom="GPS 不上报", status="draft", source="ai_candidate",
        log_keywords=["NMEA"], log_patterns=["GPS"], confidence=0.4,
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return doc, profile


def _approved_sample(db_session, admin, doc_id):
    service = GoldenSampleService(db_session)
    return service.create(
        question=f"引用文档 {doc_id} 的问题",
        actor_id=admin.id, actor_role="admin", actor_name=admin.username,
        kb_expected=[{"doc_id": doc_id, "section": "现象", "pk": f"{doc_id}:现象"}],
    )


def test_approving_candidate_flags_dependent_samples(db_session, admin, doc_with_profile):
    doc, profile = doc_with_profile
    sample = _approved_sample(db_session, admin, doc.id)
    other = GoldenSampleService(db_session).create(
        question="引用别的文档的问题",
        actor_id=admin.id, actor_role="admin", actor_name=admin.username,
        kb_expected=[{"doc_id": 9999, "section": "无关", "pk": "9999:无关"}],
    )
    assert sample.status == "approved"

    # 知识上线由 API 层触发联动（见 integration 用例），这里验证联动语义本身
    affected = GoldenSampleService(db_session).flag_documents_changed(
        [doc.id], reason="知识条目上线", actor_name="system:test",
    )
    assert affected == 1

    db_session.refresh(sample)
    db_session.refresh(other)
    assert sample.status == "needs_recheck"
    assert other.status == "approved"          # 不相关样本不受影响

    audit = (
        db_session.query(SampleReview)
        .filter(SampleReview.sample_id == sample.id)
        .order_by(SampleReview.id.asc())
        .all()
    )
    assert [a.action for a in audit] == ["submit", "recheck"]
    assert "知识条目上线" in (audit[-1].reason or "")


def test_needs_recheck_samples_are_excluded_from_export(db_session, admin, doc_with_profile):
    doc, _ = doc_with_profile
    sample = _approved_sample(db_session, admin, doc.id)
    service = GoldenSampleService(db_session)
    service.flag_documents_changed([doc.id], reason="知识条目改版")

    assert [row["id"] for row in service.export_approved()] == []

    confirmed = service.confirm_still_valid(
        sample.id, actor_id=admin.id, actor_role="admin", actor_name=admin.username,
        reason="期望章节仍准确",
    )
    assert confirmed.status == "approved"
    assert [row["id"] for row in service.export_approved()] == [sample.id]


def test_confirm_requires_admin_and_matching_status(db_session, admin, doc_with_profile):
    doc, _ = doc_with_profile
    sample = _approved_sample(db_session, admin, doc.id)
    service = GoldenSampleService(db_session)

    with pytest.raises(GoldenSampleError) as exc:
        service.confirm_still_valid(sample.id, actor_id=1, actor_role="developer")
    assert exc.value.status_code == 403

    with pytest.raises(GoldenSampleError):
        # 样本还处于 approved，不是待复核
        service.confirm_still_valid(sample.id, actor_id=admin.id, actor_role="admin")


def test_flag_without_doc_ids_is_noop(db_session):
    assert GoldenSampleService(db_session).flag_documents_changed([], reason="x") == 0
