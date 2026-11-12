"""知识库种子脚本。"""

from app.models import KnowledgeDocument, KnowledgeDocumentMeta, KnowledgeSection
from scripts.seed_knowledge import SAMPLE_DOCS, seed


class TestSeedKnowledge:
    def test_seed_creates_sample_documents(self, db_session):
        stats = seed(db_session)
        assert stats["created"] == len(SAMPLE_DOCS)
        assert stats["skipped"] == 0
        total = db_session.query(KnowledgeDocument).count()
        assert total == len(SAMPLE_DOCS)

    def test_seed_is_idempotent(self, db_session):
        seed(db_session)
        stats = seed(db_session)
        assert stats == {"created": 0, "skipped": len(SAMPLE_DOCS), "deleted": 0}

    def test_seed_writes_sections_and_meta(self, db_session):
        seed(db_session)
        case = (
            db_session.query(KnowledgeDocument)
            .filter(KnowledgeDocument.doc_type == "case")
            .first()
        )
        assert case is not None
        sections = (
            db_session.query(KnowledgeSection)
            .filter(KnowledgeSection.doc_id == case.id)
            .count()
        )
        assert sections > 0
        meta = (
            db_session.query(KnowledgeDocumentMeta)
            .filter(KnowledgeDocumentMeta.doc_id == case.id)
            .first()
        )
        assert meta is not None
        assert meta.template_key == "case"

    def test_seed_reset_rebuilds(self, db_session):
        seed(db_session)
        stats = seed(db_session, reset=True)
        assert stats["deleted"] == len(SAMPLE_DOCS)
        assert stats["created"] == len(SAMPLE_DOCS)
        assert db_session.query(KnowledgeDocument).count() == len(SAMPLE_DOCS)
