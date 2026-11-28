"""分片上传与版本行证据抽取的回归测试。"""

from app.services.diagnostics.chunked_upload import ChunkedUploadService, ChunkedUploadError
from app.services.diagnostics.diagnosis_pipeline import DiagnosisPipeline


def _log_bytes() -> bytes:
    return (
        "[2026-11-26 11:05:08] [MASTER_Start 0259] pri: 2.6.11.2_L3C_10\n"
        "[2026-11-26 11:05:09] normal line without version\n"
    ).encode("utf-8")


def test_chunked_upload_roundtrip(client):
    data = _log_bytes()
    init = client.post(
        "/api/v1/logs/uploads/init",
        json={"filename": "chunk.log", "size": len(data), "description": "版本"},
    )
    assert init.status_code == 200, init.text
    payload = init.json()
    upload_id = payload["upload_id"]
    assert payload["total_chunks"] == 1

    put = client.put(
        f"/api/v1/logs/uploads/{upload_id}/chunks/0",
        content=data,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert put.status_code == 200, put.text
    assert put.json()["received"] == [0]

    status = client.get(f"/api/v1/logs/uploads/{upload_id}")
    assert status.status_code == 200
    assert status.json()["received_count"] == 1

    done = client.post(f"/api/v1/logs/uploads/{upload_id}/complete")
    assert done.status_code == 200, done.text
    log_id = done.json()["id"]
    assert log_id > 0

    # 完成后分片目录应被清理
    assert client.get(f"/api/v1/logs/uploads/{upload_id}").status_code == 404


def test_chunked_upload_rejects_missing_chunks(client):
    data = _log_bytes()
    init = client.post(
        "/api/v1/logs/uploads/init",
        json={"filename": "missing.log", "size": len(data)},
    )
    upload_id = init.json()["upload_id"]
    resp = client.post(f"/api/v1/logs/uploads/{upload_id}/complete")
    assert resp.status_code == 400
    assert "分片不完整" in resp.json()["detail"]


def test_chunked_upload_init_requires_size(client):
    resp = client.post("/api/v1/logs/uploads/init", json={"filename": "x.log", "size": 0})
    assert resp.status_code == 400


def test_append_version_lines_keeps_master_start():
    pipeline = object.__new__(DiagnosisPipeline)
    lines = [
        "[2026-11-26 11:05:08] [MASTER_Start 0259] pri: 2.6.11.2_L3C_10",
        "[2026-11-26 11:05:09] heartbeat ok",
    ]
    out = pipeline._append_version_lines(
        "## 分析\n旧内容", lines, "这个日志中程序版本是多少？",
    )
    assert "## 版本相关日志行" in out
    assert "2.6.11.2_L3C_10" in out


def test_append_version_lines_skipped_without_version_question():
    pipeline = object.__new__(DiagnosisPipeline)
    out = pipeline._append_version_lines(
        "base", ["[MASTER_Start 0259] pri: 2.6.11.2"], "为什么设备离线？",
    )
    assert out == "base"
