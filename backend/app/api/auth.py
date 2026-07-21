"""Authentication API — login with MAC-based brute-force protection."""

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
    """Extract client MAC address from request headers or fallback to IP.

    Priority:
    1. X-Client-MAC header (set by local network proxy/gateway)
    2. X-Forwarded-For first IP as MAC substitute (for environments without MAC)
    3. request.client.host as fallback
    """
    # Try explicit MAC header first
    mac = request.headers.get("X-Client-MAC", "").strip()
    if mac:
        return mac

    # Fallback: use IP as identifier (Docker/reverse-proxy can't get real MAC)
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if forwarded:
        return forwarded

    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=TokenResponse)
def login(
    body: UserLogin,
    request: Request,
    db: Session = Depends(get_db_session),
):
    """Login and receive a JWT access token.

    Login is protected by MAC-based brute-force protection:
    - First 5 failed attempts → 20 min lock
    - After unlock, 1 attempt → fail → 1 hour lock (cycles indefinitely)
    """
    mac = _get_client_mac(request)
    try:
        return AuthService(db).login(
            username=body.username,
            password=body.password,
            mac_address=mac,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
