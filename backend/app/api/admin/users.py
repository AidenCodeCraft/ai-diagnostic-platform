"""User management API — CRUD with search and pagination (admin only)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import (
    require_admin, require_admin_user, require_developer, require_developer_user,
)
from app.database import session as session_module
from app.models import (
    ApiKey, ChatImageUpload, ChatSession, ClientLogEntry, GoldenSample, Log,
    Organization, OrganizationMember, Project, SampleReview, User,
)
from app.schemas import UserCreate, UserResponse, UserListResponse
from app.services import AuthService
from app.services.system.audit_log import record_operation

logger = logging.getLogger(__name__)


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])


WEAK_PASSWORDS = {
    "password", "123456", "12345678", "qwerty", "abc123",
    "password123", "admin123", "letmein", "welcome", "monkey",
    "dragon", "master", "123456789", "football", "iloveyou",
    "trustno1", "sunshine", "princess", "123123", "admin",
}


@router.post("", response_model=UserResponse, status_code=201)
def create_user(
    body: UserCreate,
    request: Request,
    db: Session = Depends(get_db_session),
    operator: User = Depends(require_admin_user),
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
    record_operation(
        db, operator, "user.create", target_type="user", target_id=user.id,
        detail={"username": user.username, "role": user.role}, request=request,
    )
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
    request: Request,
    db: Session = Depends(get_db_session),
    operator: User = Depends(require_admin_user),
) -> Any:
    """Update user fields."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    updatable_fields = ("role", "is_active", "organization", "organization_id")
    for field in updatable_fields:
        if field in body:
            setattr(user, field, body[field])

    # 支持密码修改：编辑模式下若传入新密码，则更新密码哈希
    if "password" in body and body["password"]:
        pw = str(body["password"])
        pw_lower = pw.lower()
        if pw_lower in WEAK_PASSWORDS:
            raise HTTPException(status_code=400, detail="密码过于简单，请使用更复杂的密码")
        if user.username.lower() in pw_lower or pw_lower in user.username.lower():
            raise HTTPException(status_code=400, detail="密码不能与用户名相同")
        if len(pw) < 12:
            raise HTTPException(status_code=400, detail="密码至少12位")
        user.password_hash = AuthService._hash_password(pw)  # type: ignore[assignment]

    db.commit()
    db.refresh(user)
    record_operation(
        db, operator, "user.update", target_type="user", target_id=user.id,
        detail={
            "username": user.username,
            "fields": sorted(body.keys()),
            "role": user.role,
            "is_active": user.is_active,
            "password_changed": bool(body.get("password")),
        },
        request=request,
    )
    return user


@router.delete("/{user_id}", status_code=204, dependencies=[Depends(require_developer)])
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
    operator: User = Depends(require_developer_user),
):
    """Delete a user. Only developer role can perform this action."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == operator.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")

    username = user.username
    try:
        # 先清理/解除引用再删用户。历史迁移里的外键没有 ON DELETE 规则，
        # 直接 delete 会触发 ForeignKeyViolation → 500（线上 client_log_entries
        # 是实际触发点）。这里显式处理，避免依赖各环境约束是否带级联。
        db.execute(delete(ApiKey).where(ApiKey.user_id == user_id))
        db.execute(delete(OrganizationMember).where(OrganizationMember.user_id == user_id))
        db.execute(update(ChatSession).where(ChatSession.user_id == user_id).values(user_id=None))
        db.execute(update(ChatImageUpload).where(ChatImageUpload.user_id == user_id).values(user_id=None))
        db.execute(update(Log).where(Log.upload_user_id == user_id).values(upload_user_id=None))
        db.execute(update(ClientLogEntry).where(ClientLogEntry.user_id == user_id).values(user_id=None))
        db.execute(update(Organization).where(Organization.owner_id == user_id).values(owner_id=None))
        db.execute(update(Project).where(Project.owner_id == user_id).values(owner_id=None))
        db.execute(update(GoldenSample).where(GoldenSample.submitted_by == user_id).values(submitted_by=None))
        db.execute(update(GoldenSample).where(GoldenSample.approved_by == user_id).values(approved_by=None))
        db.execute(update(SampleReview).where(SampleReview.actor_id == user_id).values(actor_id=None))
        db.delete(user)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("[users] delete user %s blocked by FK: %s", user_id, exc)
        raise HTTPException(
            status_code=409, detail="该用户仍被其他数据引用，无法删除",
        ) from exc

    record_operation(
        db, operator, "user.delete", target_type="user", target_id=user_id,
        detail={"username": username}, request=request,
    )
    return None
