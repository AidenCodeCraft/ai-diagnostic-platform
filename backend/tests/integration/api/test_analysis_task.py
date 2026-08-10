"""Tests for the Analysis Task Service (Commit 006)."""
from __future__ import annotations

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

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_module.engine = engine
    session_module.SessionLocal = sessionmaker(
        bind=engine, autocommit=False, autoflush=False
    )

    session_module.init_db()

    importlib.reload(main_module)

    with TestClient(main_module.app) as test_client:
        yield test_client


# ------------------------------------------------------------------
# Create
# ------------------------------------------------------------------


def test_create_analysis_task(client):
    upload = _upload_log(client, "boot.log")
    log_id = upload["id"]

    resp = client.post(f"/api/v1/analyses?log_id={log_id}")
    assert resp.status_code == 201
    data = resp.json()
    assert data["log_id"] == log_id
    assert data["status"] == "pending"
    assert data["created_at"] is not None


def test_create_analysis_with_model(client):
    upload = _upload_log(client, "boot.log")
    log_id = upload["id"]

    resp = client.post(f"/api/v1/analyses?log_id={log_id}&model=deepseek")
    assert resp.status_code == 201
    assert resp.json()["model"] == "deepseek"


def test_create_analysis_nonexistent_log(client):
    resp = client.post("/api/v1/analyses?log_id=99999")
    assert resp.status_code == 404


# ------------------------------------------------------------------
# Run
# ------------------------------------------------------------------


def test_run_analysis_completes(client):
    upload = _upload_log(client, "kernel.log")
    log_id = upload["id"]

    resp = client.post(f"/api/v1/analyses/run?log_id={log_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["summary"]
    assert data["confidence"] >= 0.0
    assert data["root_cause"]


def test_run_analysis_creates_single_record(client):
    upload = _upload_log(client, "kernel.log")
    log_id = upload["id"]

    # Run twice with same log_id — should reuse the record
    r1 = client.post(f"/api/v1/analyses/run?log_id={log_id}")
    r2 = client.post(f"/api/v1/analyses/run?log_id={log_id}")
    assert r1.status_code == 200
    assert r2.status_code == 200

    # Verify only one analysis exists for this log
    list_resp = client.get("/api/v1/analyses")
    items = list_resp.json()["items"]
    matching = [a for a in items if a["log_id"] == log_id]
    assert len(matching) == 1


# ------------------------------------------------------------------
# List
# ------------------------------------------------------------------


def test_list_analyses_empty(client):
    resp = client.get("/api/v1/analyses")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_list_analyses_with_items(client):
    upload = _upload_log(client, "a.log")
    client.post(f"/api/v1/analyses/run?log_id={upload['id']}")

    resp = client.get("/api/v1/analyses")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["total"] == 1
    assert data["items"][0]["status"] == "completed"


def test_list_analyses_filter_by_status(client):
    upload = _upload_log(client, "a.log")
    client.post(f"/api/v1/analyses?log_id={upload['id']}")  # pending

    # Filter pending
    resp = client.get("/api/v1/analyses?status=pending")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    # Filter completed
    resp = client.get("/api/v1/analyses?status=completed")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_list_analyses_pagination(client):
    for i in range(3):
        upload = _upload_log(client, f"log{i}.log")
        client.post(f"/api/v1/analyses/run?log_id={upload['id']}")

    resp = client.get("/api/v1/analyses?page=1&page_size=2")
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 3

    resp = client.get("/api/v1/analyses?page=2&page_size=2")
    data = resp.json()
    assert len(data["items"]) == 1


# ------------------------------------------------------------------
# Get
# ------------------------------------------------------------------


def test_get_analysis_by_id(client):
    upload = _upload_log(client, "kernel.log")
    run_resp = client.post(f"/api/v1/analyses/run?log_id={upload['id']}")
    analysis_id = run_resp.json()["id"]

    resp = client.get(f"/api/v1/analyses/{analysis_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == analysis_id
    assert resp.json()["status"] == "completed"


def test_get_analysis_result(client):
    upload = _upload_log(client, "kernel.log")
    run_resp = client.post(f"/api/v1/analyses/run?log_id={upload['id']}")
    analysis_id = run_resp.json()["id"]

    resp = client.get(f"/api/v1/analyses/{analysis_id}/result")
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]
    assert data["root_cause"]
    assert data["confidence"] is not None
    assert data["next_steps"] is not None


def test_get_analysis_404(client):
    resp = client.get("/api/v1/analyses/99999")
    assert resp.status_code == 404


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------


def test_delete_analysis(client):
    upload = _upload_log(client, "kernel.log")
    run_resp = client.post(f"/api/v1/analyses/run?log_id={upload['id']}")
    analysis_id = run_resp.json()["id"]

    resp = client.delete(f"/api/v1/analyses/{analysis_id}")
    assert resp.status_code == 204

    # Verify gone
    get_resp = client.get(f"/api/v1/analyses/{analysis_id}")
    assert get_resp.status_code == 404


def test_delete_analysis_404(client):
    resp = client.delete("/api/v1/analyses/99999")
    assert resp.status_code == 404


# ------------------------------------------------------------------
# Status lifecycle
# ------------------------------------------------------------------


def test_analysis_status_lifecycle(client):
    upload = _upload_log(client, "kernel.log")
    log_id = upload["id"]

    # Create → pending
    create_resp = client.post(f"/api/v1/analyses?log_id={log_id}")
    assert create_resp.json()["status"] == "pending"

    # Run → completed
    run_resp = client.post(f"/api/v1/analyses/run?log_id={log_id}")
    assert run_resp.json()["status"] == "completed"

    # Verify via get
    analysis_id = run_resp.json()["id"]
    get_resp = client.get(f"/api/v1/analyses/{analysis_id}")
    assert get_resp.json()["status"] == "completed"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _upload_log(client, filename: str = "test.log") -> dict:
    resp = client.post(
        "/api/v1/logs/upload",
        files={
            "file": (
                filename,
                b"kernel: [ 123.456789] usb 1-1: device not responding\n",
                "text/plain",
            )
        },
        data={"description": "test"},
    )
    assert resp.status_code == 200
    return resp.json()
