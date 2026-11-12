"""解析事件持久化与过滤查询。"""

from app.models import Log, LogEvent
from app.services.diagnostics.parsing_service import ParsingService

LOG_TEXT = """[    0.000000] usb 1-1: new high-speed USB device number 2 using xhci_hcd
[    0.100000] usb 1-1: device descriptor read/64, error -71
[    0.200000] usb 1-1: device not accepting address 2, error -71
[    0.300000] EXT4-fs (sda1): error count since last fsck
[    0.400000] system boot complete
"""


def _make_log(db_session, tmp_path) -> Log:
    path = tmp_path / "kernel.log"
    path.write_text(LOG_TEXT, encoding="utf-8")
    log = Log(filename="kernel.log", file_path=str(path), size=path.stat().st_size, status="uploaded")
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)
    return log


class TestLogEventPersistence:
    def test_parse_persists_events(self, db_session, tmp_path):
        log = _make_log(db_session, tmp_path)
        result = ParsingService(db_session).parse_log_with_status(log.id)
        total = (
            db_session.query(LogEvent)
            .filter(LogEvent.log_id == log.id)
            .count()
        )
        assert total == result["event_count"] > 0

    def test_query_filters_and_pagination(self, db_session, tmp_path):
        log = _make_log(db_session, tmp_path)
        service = ParsingService(db_session)
        service.parse_log_with_status(log.id)

        page = service.query_events(log.id, page=1, page_size=2)
        assert len(page["items"]) <= 2
        assert page["total"] > 0

        errors = service.query_events(log.id, is_error=True)
        assert errors["total"] > 0
        assert all(item["is_error"] for item in errors["items"])

        keyword = service.query_events(log.id, keyword="descriptor")
        assert keyword["total"] >= 1
        assert all("descriptor" in (item["raw"] or "").lower() for item in keyword["items"])

    def test_reparse_is_idempotent(self, db_session, tmp_path):
        log = _make_log(db_session, tmp_path)
        service = ParsingService(db_session)
        service.parse_log_with_status(log.id)
        first = db_session.query(LogEvent).filter(LogEvent.log_id == log.id).count()
        service.parse_log_with_status(log.id)
        second = db_session.query(LogEvent).filter(LogEvent.log_id == log.id).count()
        assert first == second > 0

    def test_query_missing_log_raises(self, db_session):
        try:
            ParsingService(db_session).query_events(999999)
        except ValueError as exc:
            assert "log not found" in str(exc)
        else:
            raise AssertionError("expected ValueError")
