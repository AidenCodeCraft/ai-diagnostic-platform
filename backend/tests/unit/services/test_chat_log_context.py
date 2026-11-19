"""会话绑定日志时，日志上下文应能回退到 Log.file_path。"""

from app.models import Log
from app.services.chat.chat_service import ChatService
from app.services.diagnostics.log_timeline import scan_bytes

LOG = "\n".join([
    "[2026-08-02 14:19:58]  [APP] pri:  heartbeat ok",
    "[2026-08-02 14:20:00]  [NL668_4G] pri:  AT+CGDCONT? empty",
]) + "\n"


def test_log_context_falls_back_to_session_log_reference(db_session, tmp_path, monkeypatch):
    path = tmp_path / "app.log"
    path.write_bytes(LOG.encode("utf-8"))

    log = Log(filename="app.log", file_path=str(path), status="parsed")
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)

    service = ChatService(db_session, model="mock")
    session = service.create_session(title="引用回退", log_id=log.id, model="mock")
    service.update_session(session.id, context={
        "active_slots": {"time": "2026-08-02 14:20", "city": "深圳", "device": "L10",
                         "phenomenon": "不上报", "attachment": True},
        "last_analysis": {"timeline": scan_bytes(LOG.encode("utf-8")).to_dict()},
    })

    context = service._build_log_context(session.id)

    assert context is not None
    assert context["data"], "应读到日志片段"
    assert b"AT+CGDCONT" in context["data"]


def test_log_context_is_none_without_log_or_time(db_session):
    service = ChatService(db_session, model="mock")
    session = service.create_session(title="无日志", model="mock")
    assert service._build_log_context(session.id) is None
