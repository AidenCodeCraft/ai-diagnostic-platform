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


def test_llm_service_generates_summary(client):
    upload_response = client.post(
        "/api/v1/logs/upload",
        files={"file": ("kernel.log", b"kernel: [ 123.456789] usb 1-1: device not responding\n", "text/plain")},
        data={"description": "usb issue"},
    )

    assert upload_response.status_code == 200
    log_id = upload_response.json()["id"]

    response = client.post(f"/api/v1/analysis/{log_id}/llm")
    assert response.status_code == 200
    payload = response.json()
    assert payload["log_id"] == log_id
    assert "usb" in payload["summary"].lower()
    assert payload["model"] == "mock"

    persisted_response = client.get(f"/api/v1/analysis/{log_id}")
    assert persisted_response.status_code == 200
    persisted_payload = persisted_response.json()
    assert persisted_payload["log_id"] == log_id
    assert persisted_payload["status"] == "completed"
    assert persisted_payload["summary"].lower().startswith("detected")
