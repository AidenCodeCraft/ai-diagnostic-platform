"""Tests for Knowledge Base management (Commit 009)."""
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


def test_create_knowledge_document(client):
    resp = client.post(
        "/api/v1/knowledge",
        json={
            "title": "USB Timeout Troubleshooting",
            "content": "Common USB timeout causes include cable faults, PHY issues, and power problems.",
            "category": "usb",
            "doc_type": "faq",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "USB Timeout Troubleshooting"
    assert data["category"] == "usb"
    assert data["doc_type"] == "faq"
    assert data["status"] == "active"
    assert data["id"]


def test_create_knowledge_document_defaults(client):
    resp = client.post(
        "/api/v1/knowledge",
        json={"title": "Basic Doc", "content": "Some content"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["doc_type"] == "manual"
    assert data["status"] == "active"


# ------------------------------------------------------------------
# Get
# ------------------------------------------------------------------


def test_get_document(client):
    create = client.post(
        "/api/v1/knowledge",
        json={"title": "Test Doc", "content": "content here"},
    )
    doc_id = create.json()["id"]

    resp = client.get(f"/api/v1/knowledge/{doc_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Test Doc"


def test_get_document_404(client):
    resp = client.get("/api/v1/knowledge/99999")
    assert resp.status_code == 404


# ------------------------------------------------------------------
# List
# ------------------------------------------------------------------


def test_list_documents_empty(client):
    resp = client.get("/api/v1/knowledge")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["total"] == 0


def test_list_documents(client):
    for i in range(3):
        client.post(
            "/api/v1/knowledge",
            json={"title": f"Doc {i}", "content": f"Content {i}", "category": "usb"},
        )

    resp = client.get("/api/v1/knowledge")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 3
    assert data["total"] == 3


def test_list_documents_filter_by_category(client):
    client.post(
        "/api/v1/knowledge",
        json={"title": "USB Doc", "content": "usb content", "category": "usb"},
    )
    client.post(
        "/api/v1/knowledge",
        json={"title": "Bluetooth Doc", "content": "bt content", "category": "bluetooth"},
    )

    resp = client.get("/api/v1/knowledge?category=usb")
    assert resp.json()["total"] == 1

    resp = client.get("/api/v1/knowledge?category=bluetooth")
    assert resp.json()["total"] == 1


def test_list_documents_filter_by_type(client):
    client.post(
        "/api/v1/knowledge",
        json={"title": "FAQ", "content": "x", "doc_type": "faq"},
    )
    client.post(
        "/api/v1/knowledge",
        json={"title": "Manual", "content": "y", "doc_type": "manual"},
    )

    resp = client.get("/api/v1/knowledge?doc_type=faq")
    assert resp.json()["total"] == 1


def test_list_documents_pagination(client):
    for i in range(5):
        client.post(
            "/api/v1/knowledge",
            json={"title": f"Doc {i}", "content": f"Content {i}"},
        )

    resp = client.get("/api/v1/knowledge?page=1&page_size=2")
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5

    resp = client.get("/api/v1/knowledge?page=3&page_size=2")
    assert len(resp.json()["items"]) == 1


# ------------------------------------------------------------------
# Update
# ------------------------------------------------------------------


def test_update_document(client):
    create = client.post(
        "/api/v1/knowledge",
        json={"title": "Old", "content": "old content", "category": "usb"},
    )
    doc_id = create.json()["id"]

    resp = client.put(
        f"/api/v1/knowledge/{doc_id}",
        json={"title": "New Title", "category": "bluetooth"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "New Title"
    assert data["category"] == "bluetooth"
    assert data["content"] == "old content"  # unchanged


def test_update_document_status(client):
    create = client.post(
        "/api/v1/knowledge",
        json={"title": "Doc", "content": "content"},
    )
    doc_id = create.json()["id"]

    resp = client.put(
        f"/api/v1/knowledge/{doc_id}",
        json={"status": "archived"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


def test_update_document_404(client):
    resp = client.put("/api/v1/knowledge/99999", json={"title": "Nope"})
    assert resp.status_code == 404


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------


def test_delete_document(client):
    create = client.post(
        "/api/v1/knowledge",
        json={"title": "To Delete", "content": "bye"},
    )
    doc_id = create.json()["id"]

    resp = client.delete(f"/api/v1/knowledge/{doc_id}")
    assert resp.status_code == 204

    get_resp = client.get(f"/api/v1/knowledge/{doc_id}")
    assert get_resp.status_code == 404


def test_delete_document_404(client):
    resp = client.delete("/api/v1/knowledge/99999")
    assert resp.status_code == 404


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------


def test_search_by_keyword(client):
    client.post(
        "/api/v1/knowledge",
        json={"title": "USB Timeout Guide", "content": "How to fix USB timeout errors on embedded devices."},
    )
    client.post(
        "/api/v1/knowledge",
        json={"title": "Bluetooth Pairing", "content": "Steps for Bluetooth pairing troubleshooting."},
    )

    resp = client.get("/api/v1/knowledge/search?q=usb")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert "usb" in data["items"][0]["title"].lower() or "usb" in data["items"][0]["snippet"].lower()


def test_search_no_results(client):
    resp = client.get("/api/v1/knowledge/search?q=nonexistent_term_xyz")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_search_result_has_snippet_and_score(client):
    client.post(
        "/api/v1/knowledge",
        json={"title": "Test", "content": "This document is about USB timeout problems."},
    )

    resp = client.get("/api/v1/knowledge/search?q=USB")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert "relevance_score" in item
    assert "snippet" in item
    assert item["relevance_score"] > 0


# ------------------------------------------------------------------
# Categories
# ------------------------------------------------------------------


def test_list_categories(client):
    client.post(
        "/api/v1/knowledge",
        json={"title": "D1", "content": "x", "category": "usb"},
    )
    client.post(
        "/api/v1/knowledge",
        json={"title": "D2", "content": "y", "category": "bluetooth"},
    )
    client.post(
        "/api/v1/knowledge",
        json={"title": "D3", "content": "z", "category": "usb"},  # duplicate
    )

    resp = client.get("/api/v1/knowledge/categories")
    assert resp.status_code == 200
    cats = resp.json()
    assert sorted(cats) == ["bluetooth", "usb"]
