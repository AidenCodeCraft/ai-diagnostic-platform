"""Shared FastAPI dependencies — database session, auth, pagination.

Import this module instead of defining `get_db_session()` in every API file.
"""

from __future__ import annotations

from typing import Generator, Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import session as session_module
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
