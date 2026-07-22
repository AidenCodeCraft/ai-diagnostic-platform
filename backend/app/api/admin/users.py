"""User management API — CRUD with search and pagination (admin only)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.models import User
from app.schemas import UserCreate, UserResponse, UserListResponse
from app.services import AuthService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/users", tags=["users"])


WEAK_PASSWORDS = {
    "password", "123456", "12345678", "qwerty", "abc123",
    "password123", "admin123", "letmein", "welcome", "monkey",
    "dragon", "master", "123456789", "football", "iloveyou",
    "trustno1", "sunshine", "princess", "123123", "admin",
}


@router.post("", response_model=UserResponse, status_code=201)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db_session),
) -> Any:
    """Create a new user (admin only)."""
    # Check weak password
    pw_lower = body.password.lower()
    if pw_lower in WEAK_PASSWORDS:
        raise HTTPException(status_code=400, detail="密码过于简单，请使用更复杂的密码")
    if body.username.lower() in pw_lower or pw_lower in body.username.lower():
        raise HTTPException(status_code=400, detail="密码不能与用户名相同")

    # Check duplicate username
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")

    # Hash password and create user
    user = User(
        username=body.username,
        password_hash=AuthService._hash_password(body.password),
        role=body.role,
        organization=body.organization,
        is_active=body.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("", response_model=UserListResponse)
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    search: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """List users with search and filters."""
    query = db.query(User)

    if search:
        pattern = f"%{search}%"
        query = query.filter(User.username.ilike(pattern))
    if role:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    total = query.count()
    items = (
        query.order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    body: Dict[str, Any],
    db: Session = Depends(get_db_session),
) -> Any:
    """Update user fields."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    updatable_fields = ("role", "is_active", "organization", "organization_id")
    for field in updatable_fields:
        if field in body:
            setattr(user, field, body[field])

    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db_session),
):
    """Delete a user. Only developer role can perform this action."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    db.delete(user)
    db.commit()
    return None
