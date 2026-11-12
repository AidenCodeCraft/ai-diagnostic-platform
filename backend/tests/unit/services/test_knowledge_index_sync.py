"""知识库 CRUD 触发向量索引同步。"""

from app.services.knowledge.knowledge_service import KnowledgeService


class TestKnowledgeIndexSync:
    def test_create_triggers_sync(self, db_session, monkeypatch):
        calls = []
        monkeypatch.setattr(
            KnowledgeService, "_sync_index",
            lambda self, doc_id, content: calls.append(("sync", doc_id, content)),
        )
        doc = KnowledgeService(db_session).create({
            "title": "索引同步", "content": "设备不上传视频", "doc_type": "case",
        })
        assert calls
        assert calls[0][0] == "sync"
        assert calls[0][1] == doc.id

    def test_update_triggers_sync(self, db_session, monkeypatch):
        svc = KnowledgeService(db_session)
        doc = svc.create({"title": "t", "content": "c", "doc_type": "manual"})
        calls = []
        monkeypatch.setattr(
            KnowledgeService, "_sync_index",
            lambda self, doc_id, content: calls.append((doc_id, content)),
        )
        svc.update(doc.id, {"content": "新内容"})
        assert calls and calls[0][0] == doc.id
        assert calls[0][1] == "新内容"

    def test_delete_triggers_index_removal(self, db_session, monkeypatch):
        svc = KnowledgeService(db_session)
        doc = svc.create({"title": "t", "content": "c", "doc_type": "manual"})
        removed = []
        monkeypatch.setattr(
            KnowledgeService, "_remove_index",
            lambda self, doc_id: removed.append(doc_id),
        )
        svc.delete(doc.id)
        assert removed == [doc.id]

    def test_reindex_uses_stored_content(self, db_session, monkeypatch):
        svc = KnowledgeService(db_session)
        doc = svc.create({"title": "t", "content": "原始内容", "doc_type": "manual"})
        calls = []
        monkeypatch.setattr(
            KnowledgeService, "_sync_index",
            lambda self, doc_id, content: calls.append((doc_id, content)),
        )
        svc.reindex(doc.id)
        assert calls == [(doc.id, "原始内容")]
