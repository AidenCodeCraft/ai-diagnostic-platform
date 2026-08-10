"""Tests for User Authentication (v0.5)."""

from app.services.auth.auth_service import AuthService
from app.database import session as sm


# ------------------------------------------------------------------
# Register
# ------------------------------------------------------------------

def test_register_creates_user(client):
    """POST /auth/register returns token + user info."""
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "Secret123!@#", "role": "engineer"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["username"] == "alice"
    assert data["user"]["role"] == "engineer"
    assert data["user"]["is_active"] is True


def test_register_duplicate_username(client):
    """Duplicate username returns 400."""
    client.post(
        "/api/v1/auth/register",
        json={"username": "bob", "password": "Secret123!@#"},
    )
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": "bob", "password": "Another456!@#"},
    )
    assert resp.status_code in (400, 409)


def test_register_short_password(client):
    """Short password returns 422 validation error."""
    resp = client.post("/api/v1/auth/register", json={"username": "short", "password": "12"})
    assert resp.status_code == 422


# ------------------------------------------------------------------
# Login
# ------------------------------------------------------------------

def test_login_returns_token(client):
    """Login with valid credentials returns token."""
    client.post(
        "/api/v1/auth/register",
        json={"username": "charlie", "password": "MyPassword123!@#"},
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "charlie", "password": "MyPassword123!@#"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == "charlie"


def test_login_wrong_password(client):
    """Wrong password returns 401."""
    client.post(
        "/api/v1/auth/register",
        json={"username": "dave", "password": "Correct123!@#"},
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "dave", "password": "wrong"},
    )
    assert resp.status_code == 401


def test_login_nonexistent_user(client):
    """Login with nonexistent user returns 401."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "ghost", "password": "nope"},
    )
    assert resp.status_code == 401


# ------------------------------------------------------------------
# Token
# ------------------------------------------------------------------

def test_token_is_valid_jwt(client):
    """Issued JWT token can be verified."""
    client.post(
        "/api/v1/auth/register",
        json={"username": "eve", "password": "JwtPass123!@#"},
    )
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "eve", "password": "JwtPass123!@#"},
    )
    token = login_resp.json()["access_token"]

    db = sm.create_session()
    try:
        user_id = AuthService(db).verify_token(token)
        assert user_id is not None
    finally:
        db.close()
