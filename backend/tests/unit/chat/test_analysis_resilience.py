"""分析韧性改造的回归测试：消息状态、幂等建任务、刷新恢复接口。"""

from app.models import Analysis, ChatSession, Log


def _new_session(client) -> int:
    resp = client.post("/api/v1/chat-sessions", json={"title": "resilience"})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def test_message_status_and_error_persist(client):
    sid = _new_session(client)
    created = client.post(
        f"/api/v1/chat-sessions/{sid}/messages",
        json={
            "role": "assistant",
            "content": "",
            "status": "failed",
            "error_message": "分析任务创建失败",
            "log_id": 42,
        },
    )
    assert created.status_code in (200, 201), created.text
    body = created.json()
    assert body["status"] == "failed"
    assert body["error_message"] == "分析任务创建失败"
    assert body["log_id"] == 42

    messages = client.get(f"/api/v1/chat-sessions/{sid}/messages").json()
    assert messages[-1]["status"] == "failed"
    assert messages[-1]["log_id"] == 42

    updated = client.put(
        f"/api/v1/chat-sessions/{sid}/messages/{body['id']}",
        json={"status": "ok", "error_message": None, "content": "done"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "ok"
    assert updated.json()["error_message"] is None


def test_session_analysis_endpoint_empty(client):
    sid = _new_session(client)
    resp = client.get(f"/api/v1/chat-sessions/{sid}/analysis")
    assert resp.status_code == 200
    assert resp.json() == {"analysis": None}


def test_run_analysis_async_is_idempotent_by_request_id(db_session, monkeypatch):
    from app.services.diagnostics.analysis_task_service import AnalysisTaskService

    # 不真正跑分析线程
    monkeypatch.setattr(AnalysisTaskService, "_execute_async", lambda self, *a, **k: None)

    log = Log(filename="idem.log", file_path="/tmp/idem.log", size=10, status="uploaded")
    db_session.add(log)
    db_session.commit()

    service = AnalysisTaskService(db_session)
    first = service.run_analysis_async(log.id, model="mock", request_id="req-idem-1")
    second = service.run_analysis_async(log.id, model="mock", request_id="req-idem-1")
    assert first["id"] == second["id"]

    row = db_session.query(Analysis).filter(Analysis.id == first["id"]).first()
    assert row is not None and row.request_id == "req-idem-1"


def test_run_analysis_async_binds_session_log(db_session, monkeypatch):
    from app.services.diagnostics.analysis_task_service import AnalysisTaskService

    monkeypatch.setattr(AnalysisTaskService, "_execute_async", lambda self, *a, **k: None)

    log = Log(filename="bind.log", file_path="/tmp/bind.log", size=10, status="uploaded")
    session = ChatSession(title="bind")
    db_session.add_all([log, session])
    db_session.commit()

    service = AnalysisTaskService(db_session)
    result = service.run_analysis_async(
        log.id, model="mock", request_id="req-bind-1", session_id=session.id,
    )
    db_session.refresh(session)
    assert result["log_id"] == log.id
    assert session.log_id == log.id
