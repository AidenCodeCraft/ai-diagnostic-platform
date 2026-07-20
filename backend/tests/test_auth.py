"""Tests for User Authentication (v0.5)."""

from app.services.auth_service import AuthService
from app.database import session as sm


# ------------------------------------------------------------------
# Register
# ------------------------------------------------------------------


def test_register_creates_user(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "secret123", "email": "alice@test.com"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "alice"
    assert data["role"] == "engineer"
    assert data["is_active"] is True
    assert "password" not in data


def test_register_duplicate_username(client):
    client.post("/api/v1/auth/register", json={"username": "bob", "password": "pass123"})
    resp = client.post("/api/v1/auth/register", json={"username": "bob", "password": "pass456"})
    assert resp.status_code in (400, 422)


def test_register_short_password(client):
    resp = client.post("/api/v1/auth/register", json={"username": "short", "password": "12"})
    assert resp.status_code == 422


# ------------------------------------------------------------------
# Login
# ------------------------------------------------------------------


def test_login_returns_token(client):
    client.post("/api/v1/auth/register", json={"username": "charlie", "password": "mypassword"})
    resp = client.post("/api/v1/auth/login", json={"username": "charlie", "password": "mypassword"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == "charlie"


def test_login_wrong_password(client):
    client.post("/api/v1/auth/register", json={"username": "dave", "password": "correct"})
    resp = client.post("/api/v1/auth/login", json={"username": "dave", "password": "wrong"})
    assert resp.status_code == 401


def test_login_nonexistent_user(client):
    resp = client.post("/api/v1/auth/login", json={"username": "ghost", "password": "nope"})
    assert resp.status_code == 401


# ------------------------------------------------------------------
# Token
# ------------------------------------------------------------------


def test_token_is_valid_jwt(client):
    client.post("/api/v1/auth/register", json={"username": "eve", "password": "jwtpass"})
    login_resp = client.post("/api/v1/auth/login", json={"username": "eve", "password": "jwtpass"})
    token = login_resp.json()["access_token"]

    db = sm.create_session()
    try:
        user_id = AuthService(db).verify_token(token)
        assert user_id is not None
    finally:
        db.close()
