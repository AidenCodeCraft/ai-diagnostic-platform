"""已解析日志删除回归测试（log_events 外键 / 对象删除顺序）。

历史 P1 bug（task-2 发现）：`log_events.log_id` 外键没有 ON DELETE CASCADE，
`LogService.delete_log()` 未先删事件就直接删 Log → commit 抛 `ForeignKeyViolation`
（API 500）；且旧实现先删 MinIO 对象再 commit，导致“对象已删、logs 记录残留、
file_path 悬空”。

修复后的契约：
1. `delete_log()` 先删该 log 的 `log_events` 行，再删 `logs` 行，同一事务提交；
2. DB 事务成功后才删对象/文件；对象删除失败只告警、不阻断；
3. DB 事务失败时不删对象（避免不一致）。
"""

import pytest

import app.services.diagnostics.log_service as log_service_module
from app.models import Log, LogEvent
from app.services.diagnostics.log_service import LogService

LOG_TEXT = """[    0.000000] usb 1-1: new high-speed USB device number 2 using xhci_hcd
[    0.100000] usb 1-1: device descriptor read/64, error -71
[    0.200000] usb 1-1: device not accepting address 2, error -71
[    0.300000] system boot complete
"""


def _make_parsed_log(db_session, tmp_path) -> tuple[Log, object]:
    """构造一条已解析日志 + 3 条 log_events 行（本地文件回退路径）。"""
    path = tmp_path / "kernel.log"
    path.write_text(LOG_TEXT, encoding="utf-8")
    log = Log(
        filename="kernel.log",
        file_path=str(path),
        size=path.stat().st_size,
        status="parsed",
    )
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)

    db_session.add_all([
        LogEvent(log_id=log.id, line_no=1, level="INFO", module="kernel", message="line1"),
        LogEvent(log_id=log.id, line_no=2, level="ERROR", module="usb", message="line2", is_error=True),
        LogEvent(log_id=log.id, line_no=3, level="INFO", module="system", message="line3"),
    ])
    db_session.commit()
    return log, path


class _RecordingStorage:
    """记录对象删除调用；可选抛错。"""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail = False

    def delete(self, reference: str) -> None:
        self.calls.append(str(reference))
        if self.fail:
            raise RuntimeError("object storage unavailable")


# ----------------------------------------------------------------------
# Service 层
# ----------------------------------------------------------------------


class TestDeleteParsedLogService:
    def test_delete_parsed_log_removes_events_and_record(self, db_session, tmp_path):
        log, path = _make_parsed_log(db_session, tmp_path)
        log_id = log.id
        assert db_session.query(LogEvent).filter(LogEvent.log_id == log_id).count() == 3

        LogService(db_session).delete_log(log_id)

        assert db_session.query(Log).filter(Log.id == log_id).count() == 0
        assert db_session.query(LogEvent).filter(LogEvent.log_id == log_id).count() == 0
        assert not path.exists(), "本地回退路径应随日志一起删除"

    def test_delete_unparsed_log_still_works(self, db_session, tmp_path):
        path = tmp_path / "raw.log"
        path.write_text("raw log line\n", encoding="utf-8")
        log = Log(filename="raw.log", file_path=str(path), size=14, status="uploaded")
        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)
        log_id = log.id

        LogService(db_session).delete_log(log_id)

        assert db_session.query(Log).filter(Log.id == log_id).count() == 0
        assert not path.exists()

    def test_delete_missing_log_raises(self, db_session):
        with pytest.raises(ValueError):
            LogService(db_session).delete_log(99999)

    def test_storage_delete_failure_does_not_block_db_delete(self, db_session, tmp_path, monkeypatch):
        storage = _RecordingStorage()
        storage.fail = True
        monkeypatch.setattr(log_service_module, "LogStorage", lambda: storage)

        log, path = _make_parsed_log(db_session, tmp_path)
        log_id = log.id

        LogService(db_session).delete_log(log_id)  # 不应抛异常（对象删除失败只告警）

        assert storage.calls == [str(path)]
        assert db_session.query(Log).filter(Log.id == log_id).count() == 0
        assert db_session.query(LogEvent).filter(LogEvent.log_id == log_id).count() == 0

    def test_db_failure_skips_object_deletion(self, db_session, tmp_path, monkeypatch):
        """DB commit 失败时不得先删对象（否则记录悬空/日志不可再解析）。"""
        from sqlalchemy.orm import Session

        storage = _RecordingStorage()
        monkeypatch.setattr(log_service_module, "LogStorage", lambda: storage)

        log, path = _make_parsed_log(db_session, tmp_path)
        log_id = log.id

        def broken_commit(self):  # noqa: ANN001 - 模拟 DB 故障
            raise RuntimeError("db commit failed")

        monkeypatch.setattr(Session, "commit", broken_commit)

        with pytest.raises(RuntimeError):
            LogService(db_session).delete_log(log_id)

        assert storage.calls == [], "对象删除必须发生在 DB commit 成功之后"
        assert path.exists(), "DB 失败时本地文件不应被删除"


# ----------------------------------------------------------------------
# API 层（TestClient + 内存 SQLite，不依赖外部服务）
# ----------------------------------------------------------------------


class TestDeleteParsedLogApi:
    def test_delete_parsed_log_returns_204_and_clears_events(self, client):
        upload = client.post(
            "/api/v1/logs/upload",
            files={"file": ("kernel.log", LOG_TEXT.encode("utf-8"), "text/plain")},
        )
        assert upload.status_code == 200, upload.text
        log_id = upload.json()["id"]

        parsed = client.post(f"/api/v1/logs/{log_id}/parse")
        assert parsed.status_code == 200, parsed.text
        assert parsed.json()["event_count"] > 0

        from app.database import session as session_module

        db = session_module.create_session()
        try:
            assert db.query(LogEvent).filter(LogEvent.log_id == log_id).count() > 0
        finally:
            db.close()

        response = client.delete(f"/api/v1/logs/{log_id}")
        assert response.status_code == 204, response.text

        assert client.get(f"/api/v1/logs/{log_id}").status_code == 404
        assert client.get(f"/api/v1/logs/{log_id}/events/query").status_code == 404

        db = session_module.create_session()
        try:
            assert db.query(Log).filter(Log.id == log_id).count() == 0
            assert db.query(LogEvent).filter(LogEvent.log_id == log_id).count() == 0
        finally:
            db.close()

    def test_delete_unparsed_log_via_api(self, client):
        upload = client.post(
            "/api/v1/logs/upload",
            files={"file": ("raw.log", b"raw line\n", "text/plain")},
        )
        assert upload.status_code == 200, upload.text
        log_id = upload.json()["id"]
        assert client.delete(f"/api/v1/logs/{log_id}").status_code == 204
        assert client.get(f"/api/v1/logs/{log_id}").status_code == 404
