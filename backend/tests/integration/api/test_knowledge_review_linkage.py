"""知识自进化审核 ↔ 黄金集的联动（API 层）。

验证两件事：
  1. 知识候选审核上线后，依赖该文档的 approved 黄金样本被标记 needs_recheck；
  2. 知识审核接口本身需要管理员权限（此前未挂鉴权）。
"""

from app.database import session as session_module
from app.models import KnowledgeDiagnosisProfile, KnowledgeDocument

BASE = "/api/v1/quality/golden-samples"
REVIEW = "/api/v1/admin/knowledge/profiles"


def _seed_draft_candidate():
    db = session_module.create_session()
    try:
        doc = KnowledgeDocument(title="L10 GPS 候选", content="## 现象\nGPS 不上报\n", status="draft")
        db.add(doc)
        db.commit()
        db.refresh(doc)
        profile = KnowledgeDiagnosisProfile(
            doc_id=doc.id, symptom="GPS 不上报", status="draft",
            source="ai_candidate", log_keywords=["NMEA"], confidence=0.4,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return doc.id, profile.id
    finally:
        db.close()


def test_approve_candidate_flags_dependent_sample(client, admin_headers):
    doc_id, profile_id = _seed_draft_candidate()

    created = client.post(
        BASE,
        json={
            "question": "L10 GPS 不上报怎么办",
            "kb_expected": [{"doc_id": doc_id, "section": "现象", "pk": f"{doc_id}:现象"}],
            "expected_conclusion": "answered",
            "category": "定位异常",
            "device_model": "L10",
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    sample = created.json()
    assert sample["status"] == "approved"

    approved = client.post(f"{REVIEW}/{profile_id}/approve", headers=admin_headers)
    assert approved.status_code == 200, approved.text

    after = client.get(f"{BASE}/{sample['id']}", headers=admin_headers)
    assert after.status_code == 200
    assert after.json()["status"] == "needs_recheck"

    # 待复核样本不进入 CI 导出
    exported = client.get(f"{BASE}/export", headers=admin_headers)
    assert exported.json()["total"] == 0


def test_knowledge_review_requires_admin(client, engineer_headers):
    resp = client.get(f"{REVIEW}/drafts", headers=engineer_headers)
    assert resp.status_code == 403
