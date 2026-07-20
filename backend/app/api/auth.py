"""Authentication API — register, login, token refresh."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.schemas.user import TokenResponse, UserLogin, UserRegister, UserResponse
from app.services.auth_service import AuthService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=201)
def register(
    body: UserRegister,
    db: Session = Depends(get_db_session),
):
    """Register a new user account."""
    try:
        return AuthService(db).register(
            username=body.username,
            password=body.password,
            email=body.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login", response_model=TokenResponse)
def login(
    body: UserLogin,
    db: Session = Depends(get_db_session),
):
    """Login and receive a JWT access token."""
    try:
        return AuthService(db).login(
            username=body.username,
            password=body.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
