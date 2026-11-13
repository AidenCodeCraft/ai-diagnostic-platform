"""聊天链路按项目过滤知识检索。"""

from app.services.chat.chat_service import ChatService
from app.services.chat.diagnostic_chat_agent import DiagnosticChatAgent
from app.services.knowledge.knowledge_service import KnowledgeService


def _seed(db):
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


class TestChatProjectFilter:
    def test_agent_limits_knowledge_to_project(self, db_session):
        _seed(db_session)
        agent = DiagnosticChatAgent(db_session, provider_name="mock", project_id=1)
        _, references = agent._retrieve_knowledge("usb timeout", {})
        titles = {ref["title"] for ref in references}
        assert references, "expected retrieval hits"
        assert "P2 USB" not in titles
        assert titles & {"P1 USB", "Global USB"}

    def test_create_session_persists_project(self, db_session):
        session = ChatService(db_session).create_session(title="t", project_id=7)
        assert session.project_id == 7
