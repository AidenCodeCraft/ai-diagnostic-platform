"""Shared FastAPI dependencies — database session, auth, pagination.

Import this module instead of defining `get_db_session()` in every API file.
"""

from __future__ import annotations

from typing import Generator, Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.models import User
from app.services import AuthService


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency — yield a database session with automatic cleanup."""
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


def get_current_user_id(
    request: Request,
    db: Session = Depends(get_db_session),
) -> Optional[int]:
    """Extract user ID from JWT Bearer token (best-effort).

    Returns None if no valid token present — endpoints should handle this.
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return AuthService(db).verify_token(auth[7:])
    return None


def require_auth(
    request: Request,
    db: Session = Depends(get_db_session),
) -> int:
    """FastAPI dependency — require valid JWT, raise 401 if missing/invalid."""
    user_id = get_current_user_id(request, db)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def require_role(*roles: str):
    """FastAPI dependency factory — require the current user to have one of `roles`.

    权限判定必须在后端完成：前端路由守卫（requiresAdmin）只是体验层，
    直接调用 API 时不可依赖。
    """

    def dependency(
        user_id: int = Depends(require_auth),
        db: Session = Depends(get_db_session),
    ) -> int:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="Authentication required")
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="需要管理员权限")
        return user_id

    return dependency


# 后台管理：admin / developer 均可
require_admin = require_role("admin", "developer")
# 高危操作：仅 developer（如删除用户）
require_developer = require_role("developer")


def get_current_user(
    user_id: int = Depends(require_auth),
    db: Session = Depends(get_db_session),
) -> User:
    """FastAPI dependency — 返回当前登录用户对象（用于审计记录操作人）。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _require_role_user(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="需要管理员权限")
        return user

    return dependency


require_admin_user = _require_role_user("admin", "developer")
require_developer_user = _require_role_user("developer")
