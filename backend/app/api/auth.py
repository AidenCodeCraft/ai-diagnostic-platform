"""Authentication API — login, verify, with MAC-based brute-force protection."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.schemas.user import TokenResponse, UserLogin
from app.services.auth_service import AuthService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/auth", tags=["auth"])


def _get_client_mac(request: Request) -> str:
    mac = request.headers.get("X-Client-MAC", "").strip()
    if mac:
        return mac
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


@router.get("/verify")
def verify_token(
    request: Request,
    db: Session = Depends(get_db_session),
):
    """Verify JWT token validity. Returns 401 if invalid or expired."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    token = auth[7:]
    user_id = AuthService(db).verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {"valid": True, "user_id": user_id}


@router.post("/login", response_model=TokenResponse)
def login(
    body: UserLogin,
    request: Request,
    db: Session = Depends(get_db_session),
):
    """Login and receive a JWT access token."""
    mac = _get_client_mac(request)
    try:
        return AuthService(db).login(
            username=body.username,
            password=body.password,
            mac_address=mac,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
