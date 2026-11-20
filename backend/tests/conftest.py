"""Shared test fixtures for all test modules.

Provides:
- client: FastAPI TestClient with in-memory SQLite (for API tests)
- db_session: direct SQLAlchemy session (for unit tests that need DB)
- monkeypatch for environment variables
"""

import importlib
import os

# 测试环境强制使用确定性哈希嵌入：避免下载 BGE 模型导致离线/CI 阻塞
os.environ.setdefault("EMBEDDING_PROVIDER", "hash")
os.environ.setdefault("EMBEDDING_HASH_FALLBACK", "true")
# 测试环境不连 broker：上传时才不会因 Redis 不可用而重试等待（会拖慢整条测试套件）
os.environ.setdefault("CELERY_ASYNC_INGEST", "false")
# 测试不加载精排模型：装上 sentence-transformers 后 bge-reranker 真的会被加载，
# 每个用例多等几十秒且与断言语义无关
os.environ.setdefault("RERANKER_ENABLED", "false")

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


@pytest.fixture(autouse=True)
def _auto_auth_testclient(monkeypatch):
    """为所有 TestClient 自动注入默认 admin 登录态。

    大量既有集成测试在本地定义了自己的 client fixture 且未携带 token；
    统一在 TestClient.__enter__ 时登录 admin 并写入 Authorization。
    需要验证未登录行为的用例请使用 anon_client（会移除该请求头）。
    """
    original_enter = TestClient.__enter__

    def enter(self):
        result = original_enter(self)
        try:
            login = self.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "admin123"},
            )
            if login.status_code == 200:
                self.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        except Exception:  # noqa: BLE001 - 无 auth 路由的测试忽略
            pass
        return result

    monkeypatch.setattr(TestClient, "__enter__", enter)
    yield


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
def anon_client(tmp_path):
    """未登录的测试客户端（用于 401 边界用例）。"""
    _ = _setup_in_memory_db(tmp_path)

    import app.main
    importlib.reload(app.main)

    with TestClient(app.main.app) as test_client:
        if "Authorization" in test_client.headers:
            del test_client.headers["Authorization"]
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


@pytest.fixture(scope="function")
def admin_headers(client):
    """Default seeded admin (admin/admin123) JWT headers."""
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="function")
def engineer_headers(client):
    """Default seeded engineer (non-admin) JWT headers."""
    resp = client.post("/api/v1/auth/login", json={"username": "engineer", "password": "engineer123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}

