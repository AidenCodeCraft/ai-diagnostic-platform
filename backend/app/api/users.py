"""User management API — list and update users (admin only)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.models.user import User
from app.schemas.user import UserResponse


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=List[UserResponse])
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    role: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db_session),
) -> Any:
    """List all users with optional filters."""
    query = db.query(User)

    if role:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    total = query.count()
    users = (
        query.order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return users


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    body: Dict[str, Any],
    db: Session = Depends(get_db_session),
) -> Any:
    """Update user role, active status, or organization."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    updatable_fields = ("role", "is_active", "organization_id")
    for field in updatable_fields:
        if field in body:
            setattr(user, field, body[field])

    db.commit()
    db.refresh(user)
    return user
