"""黄金集 API 集成测试 —— 标注 → 按角色审核 → 导出。"""

from app.database import session as session_module
from app.models import User
from app.services import AuthService

BASE = "/api/v1/quality/golden-samples"


def _headers_for(role: str, username: str):
    """在测试库里建一个指定角色的用户并签发 token（client fixture 已初始化库）。"""
    db = session_module.create_session()
    try:
        user = User(username=username, role=role, is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        token = AuthService(db)._create_token(user)
        return {"Authorization": f"Bearer {token}"}, user.id
    finally:
        db.close()


def _create(client, headers, **overrides):
    payload = {
        "question": "L10 在 2026-08-02 14:22 黑屏，GPS 不上报",
        "slots": {
            "city": "深圳", "device": "L10", "phenomenon": "黑屏",
            "time_beijing": "2026-08-02 14:22:00", "has_attachment": True,
        },
        "kb_expected": [{"doc_id": 1, "section": "显示异常排查", "pk": "abc"}],
        "expected_conclusion": "answered",
        "category": "黑屏",
        "device_model": "L10",
    }
    payload.update(overrides)
    return client.post(BASE, json=payload, headers=headers)


def test_full_review_flow_over_api(client):
    dev_headers, _ = _headers_for("developer", "dev_api")
    admin_headers, _ = _headers_for("admin", "admin_api")
    engineer_headers, _ = _headers_for("engineer", "qa_api")

    created = _create(client, engineer_headers)
    assert created.status_code == 201, created.text
    sample = created.json()
    sample_id = sample["id"]
    assert sample["status"] == "in_review"
    assert sample["review_chain"] == ["developer", "admin"]
    assert sample["next_reviewer"] == "developer"

    # 研发不能抢先审（链首是 developer，此时 admin 无权）
    jump = client.post(f"{BASE}/{sample_id}/review", json={"approve": True}, headers=admin_headers)
    assert jump.status_code == 403

    first = client.post(f"{BASE}/{sample_id}/review", json={"approve": True}, headers=dev_headers)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "in_review"
    assert first.json()["review_step"] == 1
    assert first.json()["next_reviewer"] == "admin"

    second = client.post(f"{BASE}/{sample_id}/review", json={"approve": True}, headers=admin_headers)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "approved"
    assert second.json()["approved_by"] is not None

    exported = client.get(f"{BASE}/export", headers=admin_headers)
    assert exported.status_code == 200
    assert [row["id"] for row in exported.json()["items"]] == [sample_id]

    trail = client.get(f"{BASE}/{sample_id}/reviews", headers=admin_headers)
    assert [row["action"] for row in trail.json()["items"]] == ["submit", "approve", "approve"]


def test_admin_submission_is_approved_immediately(client):
    admin_headers, _ = _headers_for("admin", "admin_direct")

    created = _create(client, admin_headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "approved"
    assert body["review_chain"] == []
    assert body["next_reviewer"] is None


def test_reject_requires_reason_over_api(client):
    dev_headers, _ = _headers_for("developer", "dev_reject")
    engineer_headers, _ = _headers_for("engineer", "qa_reject")

    sample_id = _create(client, engineer_headers).json()["id"]

    bad = client.post(f"{BASE}/{sample_id}/review", json={"approve": False}, headers=dev_headers)
    assert bad.status_code == 400

    rejected = client.post(
        f"{BASE}/{sample_id}/review",
        json={"approve": False, "reason": "期望章节不是这一节"},
        headers=dev_headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


def test_pending_queue_returns_only_my_turn(client):
    dev_headers, _ = _headers_for("developer", "dev_queue")
    engineer_headers, _ = _headers_for("engineer", "qa_queue")

    sample_id = _create(client, engineer_headers).json()["id"]

    dev_pending = client.get(f"{BASE}/pending", headers=dev_headers)
    assert dev_pending.status_code == 200
    assert [row["id"] for row in dev_pending.json()["items"]] == [sample_id]

    engineer_pending = client.get(f"{BASE}/pending", headers=engineer_headers)
    # 测试角色的待审是「用户提交」的样本，测试自己提交的不该出现在自己队列里
    assert all(row["next_reviewer"] == "engineer" for row in engineer_pending.json()["items"])


def test_unauthenticated_is_rejected(anon_client):
    resp = anon_client.get(BASE)
    assert resp.status_code == 401
