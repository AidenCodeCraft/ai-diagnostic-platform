"""API Key management."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.services import ApiKeyService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.post("", status_code=201)
def create_key(body: Dict[str, Any], db: Session = Depends(get_db_session)):
    user_id = body.get("user_id")
    name = body.get("name")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    return ApiKeyService(db).create(user_id, name)


@router.get("")
def list_keys(user_id: int = Query(...), db: Session = Depends(get_db_session)):
    return ApiKeyService(db).list(user_id)


@router.delete("/{key_id}", status_code=204)
def revoke_key(key_id: int, db: Session = Depends(get_db_session)):
    try:
        ApiKeyService(db).revoke(key_id)
        return Response(status_code=204)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
