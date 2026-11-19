"""对话链路中的时间窗闸门（附日志提问，P1 步骤 3）。"""

from app.services.chat.chat_service import ChatService
from app.services.diagnostics.log_timeline import scan_bytes

LOG = """[2026-08-02 09:00:00]  [APP] pri:  boot ok
[2026-08-02 12:00:05]  [SYS] pri:  watchdog reset triggered
""".encode("utf-8")


def _analysis():
    manifest = scan_bytes(LOG)
    return {
        "summary": "attached",
        "timeline": manifest.to_dict(),
        "error_windows": [{
            "start": "2026-08-02 12:00:05",
            "end": "2026-08-02 12:00:09",
            "count": 2,
            "weight": 3,
            "samples": ["watchdog reset triggered"],
        }],
    }


def _service(db_session):
    service = ChatService(db_session, model="mock")
    session = service.create_session(title="时间窗闸门", model="mock")
    return service, session


def test_time_outside_range_returns_candidates(db_session):
    service, session = _service(db_session)

    result = service.send_message(
        session.id,
        "深圳 L10 设备黑屏，2026-08-03 10:00",
        log_analysis=_analysis(),
    )

    assert "日志覆盖的时间范围" in result["reply"]
    assert result["time_options"], "应给出候选时段"
    assert result["time_options"][-1]["manual"] is True

    context = service.get_session(session.id).context or {}
    assert context.get("asked_time") == "2026-08-03 10:00"
    assert context.get("pending_time_choice")


def test_time_inside_range_continues_normally(db_session):
    service, session = _service(db_session)

    result = service.send_message(
        session.id,
        "深圳 L10 设备黑屏，2026-08-02 10:30",
        log_analysis=_analysis(),
    )

    assert "日志覆盖的时间范围" not in result["reply"]
    assert "time_options" not in result
