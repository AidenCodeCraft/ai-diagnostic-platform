"""Authentication API — login, register, verify, with MAC-based brute-force protection."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.models import User
from app.schemas import TokenResponse, UserLogin, UserCreate
from app.services import AuthService


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


@router.post("/register", response_model=TokenResponse)
def register(
    body: UserCreate,
    db: Session = Depends(get_db_session),
):
    """Register a new user and receive a JWT access token."""
    try:
        return AuthService(db).register(
            username=body.username,
            password=body.password,
            role=body.role if hasattr(body, 'role') else 'user',
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


def _require_user(request: Request, db: Session) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user_id = AuthService(db).verify_token(auth[7:])
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.get("/preferences")
def get_preferences(request: Request, db: Session = Depends(get_db_session)):
    """当前登录用户的主题偏好（每个用户独立配置）。"""
    user = _require_user(request, db)
    return {"theme": user.theme}


@router.put("/preferences")
def update_preferences(
    body: Dict[str, Any], request: Request, db: Session = Depends(get_db_session)
):
    """保存当前登录用户的主题偏好：light / dark / system。"""
    theme = body.get("theme")
    if theme not in ("light", "dark", "system"):
        raise HTTPException(status_code=400, detail="theme must be light / dark / system")
    user = _require_user(request, db)
    user.theme = theme
    db.commit()
    return {"theme": user.theme}
