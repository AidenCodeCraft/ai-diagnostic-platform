import importlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database import session as session_module


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))

    import app.core.config as config_module
    import app.main as main_module

    config_module.settings.DATABASE_URL = "sqlite:///:memory:"
    config_module.settings.UPLOAD_DIR = str(tmp_path / "uploads")

    engine = create_engine("sqlite:///:memory:")
    session_module.engine = engine
    session_module.SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    session_module.init_db()

    importlib.reload(main_module)

    with TestClient(main_module.app) as test_client:
        yield test_client


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
    assert payload["log_id"] is not None

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
