def test_upload_log_creates_record_and_saves_file(client, tmp_path):
    response = client.post(
        "/api/v1/logs/upload",
        files={"file": ("boot.log", b"kernel panic\n", "text/plain")},
        data={"project_id": "1", "device": "SS528", "version": "1.0.0", "description": "startup failure"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "uploaded"
    assert payload["filename"] == "boot.log"
    assert payload["id"] is not None

    saved_files = list((tmp_path / "uploads").rglob("*"))
    assert any(path.is_file() and path.read_bytes() == b"kernel panic\n" for path in saved_files)


def test_list_logs_returns_uploaded_entries(client):
    client.post(
        "/api/v1/logs/upload",
        files={"file": ("boot.log", b"kernel panic\n", "text/plain")},
        data={"description": "startup failure"},
    )
    response = client.get("/api/v1/logs")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["filename"] == "boot.log"
