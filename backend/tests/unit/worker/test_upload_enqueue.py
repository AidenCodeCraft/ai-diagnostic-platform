"""上传后投递异步预处理链（P2 接线）。"""

import io

import pytest
from fastapi import UploadFile

from app.core.config import settings
from app.services.diagnostics.log_service import LogService
from app.worker import tasks as worker_tasks


def _upload(db_session, content: bytes = b"[2026-08-02 14:20:00] [APP] boot ok\n"):
    file = UploadFile(file=io.BytesIO(content), filename="app.log")
    return LogService(db_session).upload_log(file=file, upload_user_id=1)


@pytest.fixture
def captured(monkeypatch):
    calls = []

    def fake_enqueue(log_id):
        calls.append(log_id)
        return {"task_id": "t", "log_id": str(log_id), "queue": "ingest"}

    monkeypatch.setattr(worker_tasks, "enqueue_pipeline", fake_enqueue)
    return calls


def test_upload_enqueues_ingest_pipeline(db_session, captured, monkeypatch):
    # 测试环境默认关闭异步投递（避免连 broker），这里显式打开验证接线
    monkeypatch.setattr(settings, "CELERY_ASYNC_INGEST", True)

    log = _upload(db_session)

    assert captured == [log.id]


def test_enqueue_failure_does_not_break_upload(db_session, monkeypatch):
    def boom(log_id):
        raise RuntimeError("broker down")

    monkeypatch.setattr(worker_tasks, "enqueue_pipeline", boom)

    log = _upload(db_session)      # 不应抛异常
    assert log.id is not None


def test_async_ingest_can_be_disabled(db_session, captured, monkeypatch):
    monkeypatch.setattr(settings, "CELERY_ASYNC_INGEST", False)

    log = _upload(db_session)

    assert log.id is not None
    assert captured == []


def test_enqueue_pipeline_does_not_retry_on_broker_failure(monkeypatch):
    """broker 连不上时必须立刻失败，不能重试把上传请求拖住。"""
    captured = {}

    class FakeAsyncResult:
        id = "task-1"

    def fake_apply_async(*args, **kwargs):
        captured.update(kwargs)
        return FakeAsyncResult()

    monkeypatch.setattr(worker_tasks.ingest_prepare, "apply_async", fake_apply_async)

    result = worker_tasks.enqueue_pipeline(42)

    assert captured["retry"] is False
    assert captured["queue"] == "ingest"
    assert result["task_id"] == "task-1"


def test_ingest_status_endpoint(client, admin_headers):
    upload = client.post(
        "/api/v1/logs/upload",
        files={"file": ("app.log", b"[2026-08-02 14:20:00] [APP] boot ok\n", "text/plain")},
        headers=admin_headers,
    )
    assert upload.status_code == 200, upload.text
    log_id = upload.json()["id"]

    resp = client.get(f"/api/v1/logs/{log_id}/ingest-status", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["log_id"] == log_id
    assert "stages" in body
    assert body["all_succeeded"] is False
