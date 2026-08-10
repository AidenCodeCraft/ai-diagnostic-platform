import importlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import session as session_module


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))

    import app.core.config as config_module
    import app.main as main_module

    config_module.settings.DATABASE_URL = "sqlite:///:memory:"
    config_module.settings.UPLOAD_DIR = str(tmp_path / "uploads")

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    session_module.engine = engine
    session_module.SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    session_module.init_db()

    importlib.reload(main_module)

    with TestClient(main_module.app) as test_client:
        yield test_client


def test_parse_flow_returns_events_for_uploaded_log(client):
    upload_response = client.post(
        "/api/v1/logs/upload",
        files={"file": ("boot.log", b"2024-10-01 10:20:30 ERROR usb: device timeout while reading descriptor\n", "text/plain")},
        data={"description": "boot issue"},
    )

    assert upload_response.status_code == 200
    log_id = upload_response.json()["id"]

    parse_response = client.post(f"/api/v1/logs/{log_id}/parse")
    assert parse_response.status_code == 200
    parse_payload = parse_response.json()
    assert parse_payload["status"] == "completed"
    assert parse_payload["event_count"] == 1
    assert len(parse_payload["suggestions"]) >= 1

    events_response = client.get(f"/api/v1/logs/{log_id}/events")
    assert events_response.status_code == 200
    payload = events_response.json()
    assert len(payload) == 1
    assert payload[0]["module"] == "usb"
    assert payload[0]["classification"] == "timeout"

    status_response = client.get(f"/api/v1/logs/{log_id}/parse-status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "parsed"
