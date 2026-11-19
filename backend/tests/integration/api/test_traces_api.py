"""对话链路落检索轨迹 + 轨迹查询 API。"""

from app.models import RetrievalTrace
from app.services.chat.chat_service import ChatService


def test_send_message_writes_retrieval_trace(db_session):
    service = ChatService(db_session, model="mock")
    session = service.create_session(title="轨迹测试", model="mock")

    service.send_message(session.id, "设备黑屏了怎么办")

    traces = db_session.query(RetrievalTrace).filter_by(session_id=session.id).all()
    assert len(traces) == 1
    trace = traces[0]
    assert trace.question == "设备黑屏了怎么办"
    assert trace.conclusion in ("answered", "refused", "ask_slot", "no_kb_entry")
    assert trace.kb_candidates is not None


def test_traces_api_filters_by_session(client, admin_headers):
    from app.database import session as session_module
    from app.services.quality.trace_service import record_trace

    db = session_module.create_session()
    try:
        trace = record_trace(db, session_id=4242, question="轨迹查询测试")
        trace_id = trace.id
    finally:
        db.close()

    resp = client.get("/api/v1/quality/traces?session_id=4242", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 1
    assert any(item["id"] == trace_id for item in body["items"])

    one = client.get(f"/api/v1/quality/traces/{trace_id}", headers=admin_headers)
    assert one.status_code == 200
    assert one.json()["question"] == "轨迹查询测试"


def test_traces_api_requires_auth(anon_client):
    assert anon_client.get("/api/v1/quality/traces").status_code == 401
