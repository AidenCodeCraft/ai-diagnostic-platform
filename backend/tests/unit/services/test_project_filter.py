"""多租户/项目过滤：知识检索、知识列表、日志列表。"""

from app.models import Log
from app.services.diagnostics.log_service import LogService
from app.services.knowledge.knowledge_service import KnowledgeService


def _seed_knowledge(db):
    svc = KnowledgeService(db)
    svc.create({
        "title": "P1 USB", "content": "usb timeout p1 usb", "doc_type": "manual",
        "project_id": 1,
    })
    svc.create({
        "title": "P2 USB", "content": "usb timeout p2 usb", "doc_type": "manual",
        "project_id": 2,
    })
    svc.create({
        "title": "Global USB", "content": "usb timeout global usb", "doc_type": "manual",
    })


class TestKnowledgeProjectFilter:
    def test_search_filters_by_project(self, db_session):
        _seed_knowledge(db_session)
        result = KnowledgeService(db_session).search("usb timeout", project_id=1)
        titles = [item["title"] for item in result["items"]]
        assert "P1 USB" in titles
        assert "Global USB" in titles
        assert "P2 USB" not in titles

    def test_list_filters_by_project(self, db_session):
        _seed_knowledge(db_session)
        result = KnowledgeService(db_session).list(project_id=2)
        titles = [doc.title for doc in result["items"]]
        assert "P2 USB" in titles
        assert "P1 USB" not in titles

    def test_no_project_returns_all(self, db_session):
        _seed_knowledge(db_session)
        result = KnowledgeService(db_session).search("usb timeout")
        titles = [item["title"] for item in result["items"]]
        assert {"P1 USB", "P2 USB", "Global USB"} <= set(titles)


class TestLogProjectFilter:
    def test_list_logs_filters_by_project(self, db_session, tmp_path):
        path = tmp_path / "a.log"
        path.write_text("boot ok", encoding="utf-8")
        db_session.add_all([
            Log(filename="p1.log", file_path=str(path), size=7, project_id=1),
            Log(filename="p2.log", file_path=str(path), size=7, project_id=2),
        ])
        db_session.commit()

        logs = LogService(db_session).list_logs(project_id=1)
        assert len(logs) == 1
        assert logs[0].filename == "p1.log"

        all_logs = LogService(db_session).list_logs()
        assert len(all_logs) == 2
