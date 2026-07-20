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


def test_agent_run_returns_state_and_tool_plan(client):
    upload_response = client.post(
        "/api/v1/logs/upload",
        files={"file": ("kernel.log", b"kernel: [ 123.456789] usb 1-1: device not responding\n", "text/plain")},
        data={"description": "usb issue"},
    )
    assert upload_response.status_code == 200
    log_id = upload_response.json()["id"]

    response = client.post(f"/api/v1/agents/run/{log_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"planning", "completed"}
    assert payload["state"] in {"CREATED", "PLANNING", "EXECUTING", "COMPLETED"}
    assert payload["tool_plan"]
