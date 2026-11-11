"""意图澄清：基于知识库特征点的槽位化反问。"""

from app.services.chat.clarification import ClarificationService
from app.services.knowledge.knowledge_service import KnowledgeService
from app.services.knowledge.document_meta_service import KnowledgeDocumentMetaService


def _seed_features(db_session):
    """准备带设备/城市特征点的知识条目。"""
    svc = KnowledgeService(db_session)
    meta_svc = KnowledgeDocumentMetaService(db_session)

    doc1 = svc.create({"title": "案例一", "content": "内容一", "doc_type": "case"})
    meta_svc.upsert(doc1.id, {
        "template_key": "case",
        "quality_score": 50,
        "features": {"设备类型": "D3C", "城市": "潜江"},
    })
    doc2 = svc.create({"title": "案例二", "content": "内容二", "doc_type": "case"})
    meta_svc.upsert(doc2.id, {
        "template_key": "case",
        "quality_score": 50,
        "features": {"设备类型": "L13C", "城市": "武汉"},
    })


class TestClarificationService:
    def test_asks_missing_slots(self, db_session):
        _seed_features(db_session)
        questions = ClarificationService(db_session).analyze("设备不上传视频 异常")
        assert questions
        slots = {q.slot for q in questions}
        assert "device" in slots
        device = next(q for q in questions if q.slot == "device")
        assert "D3C" in device.options
        assert "L13C" in device.options

    def test_no_question_when_slots_mentioned(self, db_session):
        _seed_features(db_session)
        assert ClarificationService(db_session).analyze("潜江 D3C 设备不上传视频 异常") == []

    def test_no_question_without_options(self, db_session):
        # 知识库没有特征点时不应反问
        assert ClarificationService(db_session).analyze("设备不上传视频 异常") == []
