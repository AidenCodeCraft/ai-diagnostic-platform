"""对话链路中的槽位闸门（附日志提问）。"""

from app.services.chat.chat_service import ChatService


def _service(db_session):
    service = ChatService(db_session, model="mock")
    session = service.create_session(title="槽位闸门", model="mock")
    return service, session


def test_missing_slots_returns_clarification_without_llm(db_session):
    service, session = _service(db_session)

    result = service.send_message(session.id, "设备黑屏了", log_analysis={"summary": "attached"})

    reply = result["reply"]
    assert "还需要你补充" in reply
    assert "城市" in reply and "时间点（北京时间）" in reply

    session = service.get_session(session.id)
    pending = (session.context or {}).get("pending_slots") or {}
    assert pending.get("phenomenon")  # 已抽到的槽位予以保留


def test_slots_merge_across_turns(db_session):
    service, session = _service(db_session)

    service.send_message(session.id, "设备黑屏了", log_analysis={"summary": "attached"})
    result = service.send_message(
        session.id, "深圳的 L10，2026-08-02 14:22", log_analysis={"summary": "attached"},
    )

    session = service.get_session(session.id)
    context = session.context or {}
    assert context.get("pending_slots") in ({}, None)
    slots = context.get("active_slots") or {}
    assert slots.get("city") == "深圳"
    assert slots.get("device") == "L10"
    assert slots.get("time") == "2026-08-02 14:22"
    # 齐全后正常进入回答流程，不再追问
    assert "还需要你补充" not in result["reply"]


def test_no_gate_without_attachment(db_session):
    """不带日志的普通提问不触发闸门（纯知识库问答不受影响）。"""
    service, session = _service(db_session)

    result = service.send_message(session.id, "设备黑屏了")

    assert "还需要你补充" not in result["reply"]
    session = service.get_session(session.id)
    assert "active_slots" not in (session.context or {})
