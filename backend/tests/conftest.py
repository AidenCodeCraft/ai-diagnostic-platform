"""Shared test fixtures for all test modules."""

import importlib
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import session as session_module


@pytest.fixture(scope="function")
def client(monkeypatch, tmp_path):
    """Create an isolated test client with in-memory SQLite database."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("DEBUG", "true")

    import app.core.config as config_module

    config_module.settings.DATABASE_URL = "sqlite:///:memory:"
    config_module.settings.UPLOAD_DIR = str(tmp_path / "uploads")

    # Force reload session module to pick up new engine
    import app.database.session
    importlib.reload(app.database.session)
    from app.database import session as sm

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    sm.engine = engine
    sm.SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    sm.init_db()

    # Reload main app with fresh state
    import app.main
    importlib.reload(app.main)

    with TestClient(app.main.app) as test_client:
        yield test_client
