"""Tests for the Log Management Service (Commit 004)."""


# ------------------------------------------------------------------
# Upload
# ------------------------------------------------------------------


def test_upload_log_saves_file_and_returns_metadata(client):
    response = client.post(
        "/api/v1/logs/upload",
        files={
            "file": (
                "test.log",
                b"kernel: ERROR usb 1-1: device timeout\n",
                "text/plain",
            )
        },
        data={"description": "usb issue", "device": "SS928"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"]
    assert payload["filename"] == "test.log"
    assert payload["status"] == "uploaded"
    assert payload["device"] == "SS928"
    assert payload["size"] is not None
    assert payload["size"] > 0


def test_upload_log_deduplicates_filenames(client):
    content = b"log line\n"
    for _ in range(3):
        response = client.post(
            "/api/v1/logs/upload",
            files={"file": ("same.log", content, "text/plain")},
        )
        assert response.status_code == 200

    list_resp = client.get("/api/v1/logs")
    logs = list_resp.json()
    assert len(logs) == 3
    paths = {log["file_path"] for log in logs}
    assert len(paths) == 3


# ------------------------------------------------------------------
# List & Get
# ------------------------------------------------------------------


def test_list_logs_returns_empty_when_no_logs(client):
    response = client.get("/api/v1/logs")
    assert response.status_code == 200
    assert response.json() == []


def test_list_logs_returns_all_logs_ordered_by_date(client):
    client.post("/api/v1/logs/upload", files={"file": ("first.log", b"aaa", "text/plain")})
    client.post("/api/v1/logs/upload", files={"file": ("second.log", b"bbb", "text/plain")})
    response = client.get("/api/v1/logs")
    data = response.json()
    assert len(data) == 2
    assert data[0]["filename"] == "second.log"


def test_get_log_returns_single_record(client):
    upload = client.post("/api/v1/logs/upload", files={"file": ("single.log", b"data", "text/plain")})
    log_id = upload.json()["id"]
    response = client.get(f"/api/v1/logs/{log_id}")
    assert response.status_code == 200
    assert response.json()["id"] == log_id


def test_get_log_returns_404_for_missing(client):
    response = client.get("/api/v1/logs/99999")
    assert response.status_code == 404


# ------------------------------------------------------------------
# Update
# ------------------------------------------------------------------


def test_update_log_metadata(client):
    upload = client.post("/api/v1/logs/upload", files={"file": ("update.log", b"data", "text/plain")})
    log_id = upload.json()["id"]
    response = client.put(f"/api/v1/logs/{log_id}", json={"device": "updated_device", "version": "2.0"})
    assert response.status_code == 200
    assert response.json()["device"] == "updated_device"


def test_update_log_status_valid_transition(client):
    upload = client.post("/api/v1/logs/upload", files={"file": ("status.log", b"data", "text/plain")})
    log_id = upload.json()["id"]
    response = client.put(f"/api/v1/logs/{log_id}", json={"status": "parsing"})
    assert response.status_code == 200
    assert response.json()["status"] == "parsing"


def test_update_log_status_invalid_transition_is_rejected(client):
    upload = client.post("/api/v1/logs/upload", files={"file": ("invalid.log", b"data", "text/plain")})
    log_id = upload.json()["id"]
    response = client.put(f"/api/v1/logs/{log_id}", json={"status": "analyzed"})
    assert response.status_code == 404


def test_update_log_404_for_missing(client):
    response = client.put("/api/v1/logs/99999", json={"device": "nope"})
    assert response.status_code == 404


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------


def test_delete_log_removes_record(client):
    upload = client.post("/api/v1/logs/upload", files={"file": ("delete.log", b"data", "text/plain")})
    log_id = upload.json()["id"]
    response = client.delete(f"/api/v1/logs/{log_id}")
    assert response.status_code == 204
    get_resp = client.get(f"/api/v1/logs/{log_id}")
    assert get_resp.status_code == 404


def test_delete_log_404_for_missing(client):
    response = client.delete("/api/v1/logs/99999")
    assert response.status_code == 404


# ------------------------------------------------------------------
# Status machine
# ------------------------------------------------------------------


def test_full_status_lifecycle(client):
    upload = client.post("/api/v1/logs/upload", files={"file": ("lifecycle.log", b"errors here\n", "text/plain")})
    log_id = upload.json()["id"]
    steps = [("parsing", 200), ("parsed", 200), ("analyzing", 200), ("analyzed", 200)]
    for status, expected_code in steps:
        resp = client.put(f"/api/v1/logs/{log_id}", json={"status": status})
        assert resp.status_code == expected_code
        assert resp.json()["status"] == status
    resp = client.delete(f"/api/v1/logs/{log_id}")
    assert resp.status_code == 204
