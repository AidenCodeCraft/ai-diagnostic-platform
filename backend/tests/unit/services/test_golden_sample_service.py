"""黄金集服务测试 —— 提交 / 审核 / 打回 / 修改重审 / 失效 / 导出。"""

import pytest

from app.models import GoldenSample, SampleReview, User
from app.services.quality import GoldenSampleError, GoldenSampleService


@pytest.fixture
def actors(db_session):
    users = {
        "dev": User(username="dev1", role="developer"),
        "qa": User(username="qa1", role="engineer"),
        "admin": User(username="admin1", role="admin"),
        "biz": User(username="biz1", role="user"),
    }
    db_session.add_all(users.values())
    db_session.commit()
    for user in users.values():
        db_session.refresh(user)
    return users


def _create(service, actors, role_key, **overrides):
    actor = actors[role_key]
    payload = dict(
        question="L10 在 2026-08-02 14:22 黑屏",
        actor_id=actor.id,
        actor_role=actor.role,
        actor_name=actor.username,
        category="黑屏",
        device_model="L10",
        kb_expected=[{"doc_id": 1, "section": "显示异常排查", "pk": "abc"}],
    )
    payload.update(overrides)
    return service.create(**payload)


def test_admin_submission_takes_effect_immediately(db_session, actors):
    service = GoldenSampleService(db_session)
    sample = _create(service, actors, "admin")

    assert sample.status == "approved"
    assert sample.review_chain == []
    assert sample.approved_by == actors["admin"].id
    audit = db_session.query(SampleReview).filter_by(sample_id=sample.id).all()
    assert [a.action for a in audit] == ["submit"]


def test_engineer_submission_requires_developer_then_admin(db_session, actors):
    service = GoldenSampleService(db_session)
    sample = _create(service, actors, "qa")
    assert sample.status == "in_review"
    assert sample.review_chain == ["developer", "admin"]

    sample = service.review(
        sample.id, actor_id=actors["dev"].id, actor_role="developer",
        actor_name="dev1", approve=True,
    )
    assert (sample.status, sample.review_step) == ("in_review", 1)

    sample = service.review(
        sample.id, actor_id=actors["admin"].id, actor_role="admin",
        actor_name="admin1", approve=True,
    )
    assert (sample.status, sample.review_step) == ("approved", 2)
    assert sample.approved_by == actors["admin"].id
    assert sample.approved_at is not None


def test_user_submission_needs_three_levels(db_session, actors):
    service = GoldenSampleService(db_session)
    sample = _create(service, actors, "biz")
    assert sample.review_chain == ["engineer", "developer", "admin"]

    for key, role in (("qa", "engineer"), ("dev", "developer"), ("admin", "admin")):
        sample = service.review(
            sample.id, actor_id=actors[key].id, actor_role=role,
            actor_name=actors[key].username, approve=True,
        )
    assert sample.status == "approved"


def test_admin_cannot_jump_the_queue(db_session, actors):
    service = GoldenSampleService(db_session)
    sample = _create(service, actors, "qa")   # 链首是 developer

    with pytest.raises(GoldenSampleError) as exc:
        service.review(
            sample.id, actor_id=actors["admin"].id, actor_role="admin",
            approve=True,
        )
    assert exc.value.status_code == 403
    assert "developer" in str(exc.value)


def test_submitter_cannot_review_own_sample(db_session, actors):
    service = GoldenSampleService(db_session)
    dev = actors["dev"]
    sample = GoldenSample(
        question="自审尝试", expected_conclusion="answered",
        status="in_review", review_chain=["developer"], review_step=0,
        submitted_by=dev.id,
    )
    db_session.add(sample)
    db_session.commit()

    with pytest.raises(GoldenSampleError) as exc:
        service.review(
            sample.id, actor_id=dev.id, actor_role="developer", approve=True,
        )
    assert exc.value.status_code == 403
    assert "自己" in str(exc.value)


def test_reject_requires_reason_and_resets_on_resubmit(db_session, actors):
    service = GoldenSampleService(db_session)
    sample = _create(service, actors, "qa")

    with pytest.raises(GoldenSampleError):
        service.review(
            sample.id, actor_id=actors["dev"].id, actor_role="developer",
            approve=False, reason="  ",
        )

    sample = service.review(
        sample.id, actor_id=actors["dev"].id, actor_role="developer",
        approve=False, reason="期望章节不匹配",
    )
    assert sample.status == "rejected"

    sample = service.submit_sample(
        sample.id, actor_id=actors["qa"].id, actor_role="engineer",
    )
    assert (sample.status, sample.review_step) == ("in_review", 0)


def test_editing_admin_sample_keeps_it_approved(db_session, actors):
    """管理员提交的样本没有审核链，改动后仍直接生效，但版本 +1 并留痕。"""
    service = GoldenSampleService(db_session)
    sample = _create(service, actors, "admin")
    assert sample.status == "approved"

    sample = service.update(
        sample.id, actor_id=actors["admin"].id, actor_role="admin",
        actor_name="admin1", category="显示异常",
    )
    assert sample.status == "approved"
    assert sample.review_step == 0
    assert sample.sample_version == 2
    actions = [
        r.action for r in db_session.query(SampleReview).filter_by(sample_id=sample.id).all()
    ]
    assert actions == ["submit", "revise"]


def test_editing_approved_reviewed_sample_sends_it_back(db_session, actors):
    """走过审核的 approved 样本被改动 → 必须回到链路第 0 步重审。"""
    service = GoldenSampleService(db_session)
    sample = _create(service, actors, "qa")
    sample = service.review(sample.id, actor_id=actors["dev"].id, actor_role="developer", approve=True)
    sample = service.review(sample.id, actor_id=actors["admin"].id, actor_role="admin", approve=True)
    assert sample.status == "approved"

    sample = service.update(
        sample.id, actor_id=actors["qa"].id, actor_role="engineer",
        note="补充现象描述",
    )
    assert (sample.status, sample.review_step) == ("in_review", 0)
    assert sample.approved_by is None
    assert sample.approved_at is None


def test_editing_by_others_is_rejected(db_session, actors):
    service = GoldenSampleService(db_session)
    sample = _create(service, actors, "qa")

    with pytest.raises(GoldenSampleError) as exc:
        service.update(
            sample.id, actor_id=actors["biz"].id, actor_role="user",
            category="越权修改",
        )
    assert exc.value.status_code == 403


def test_edit_invalidates_partial_approval(db_session, actors):
    service = GoldenSampleService(db_session)
    sample = _create(service, actors, "qa")
    sample = service.review(
        sample.id, actor_id=actors["dev"].id, actor_role="developer", approve=True,
    )
    assert (sample.status, sample.review_step) == ("in_review", 1)

    sample = service.update(
        sample.id, actor_id=actors["qa"].id, actor_role="engineer",
        kb_expected=[{"doc_id": 2, "section": "电源排查", "pk": "def"}],
    )
    assert (sample.status, sample.review_step) == ("in_review", 0)


def test_supersede_requires_admin_and_reason(db_session, actors):
    service = GoldenSampleService(db_session)
    sample = _create(service, actors, "admin")

    with pytest.raises(GoldenSampleError) as exc:
        service.supersede(
            sample.id, actor_id=actors["dev"].id, actor_role="developer",
            reason="文档改版",
        )
    assert exc.value.status_code == 403

    with pytest.raises(GoldenSampleError):
        service.supersede(
            sample.id, actor_id=actors["admin"].id, actor_role="admin", reason="",
        )

    sample = service.supersede(
        sample.id, actor_id=actors["admin"].id, actor_role="admin",
        reason="文档已改版",
    )
    assert sample.status == "superseded"


def test_pending_queue_follows_review_step(db_session, actors):
    service = GoldenSampleService(db_session)
    biz_sample = _create(service, actors, "biz")     # 链首 engineer
    qa_sample = _create(service, actors, "qa")       # 链首 developer

    qa_queue = service.pending_for("engineer")
    assert [s.id for s in qa_queue["items"]] == [biz_sample.id]

    dev_queue = service.pending_for("developer")
    assert [s.id for s in dev_queue["items"]] == [qa_sample.id]

    assert service.pending_for("admin")["total"] == 0


def test_only_approved_samples_are_exported(db_session, actors):
    service = GoldenSampleService(db_session)
    approved = _create(service, actors, "admin")
    _create(service, actors, "qa")

    exported = service.export_approved()
    assert [row["id"] for row in exported] == [approved.id]
    assert exported[0]["expected_conclusion"] == "answered"
    assert "status" not in exported[0]


def test_invalid_expected_conclusion_is_rejected(db_session, actors):
    service = GoldenSampleService(db_session)
    with pytest.raises(GoldenSampleError):
        _create(service, actors, "qa", expected_conclusion="maybe")
