"""Shared test fixtures for all test modules.

Provides:
- client: FastAPI TestClient with in-memory SQLite (for API tests)
- db_session: direct SQLAlchemy session (for unit tests that need DB)
- monkeypatch for environment variables
"""

import importlib
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _setup_in_memory_db(tmp_path):
    """Create an in-memory SQLite database and configure the session module."""
    # Force in-memory SQLite
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["UPLOAD_DIR"] = str(tmp_path / "uploads")
    os.environ["DEBUG"] = "true"
    os.environ["MILVUS_ENABLED"] = "false"  # 测试时禁用 Milvus

    import app.core.config as config_module
    config_module.settings.DATABASE_URL = "sqlite:///:memory:"
    config_module.settings.UPLOAD_DIR = str(tmp_path / "uploads")
    config_module.settings.MILVUS_ENABLED = False

    # Reload session module
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

    return sm.SessionLocal


@pytest.fixture(scope="function")
def client(tmp_path):
    """Create an isolated test client with in-memory SQLite database."""
    _ = _setup_in_memory_db(tmp_path)

    # Reload main app with fresh state
    import app.main
    importlib.reload(app.main)

    with TestClient(app.main.app) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def db_session(tmp_path):
    """Direct SQLAlchemy session for unit tests that need DB access."""
    SessionLocal = _setup_in_memory_db(tmp_path)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

