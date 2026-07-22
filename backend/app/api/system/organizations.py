"""Organization API — multi-tenant management."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.services import OrganizationService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", status_code=201)
def create_org(body: Dict[str, Any], db: Session = Depends(get_db_session)):
    name = body.get("name", "").strip()
    owner_id = body.get("owner_id")
    if not name or not owner_id:
        raise HTTPException(status_code=400, detail="name and owner_id are required")
    return OrganizationService(db).create(name, owner_id)


@router.get("")
def list_orgs(db: Session = Depends(get_db_session)):
    return OrganizationService(db).list()


@router.get("/{org_id}")
def get_org(org_id: int, db: Session = Depends(get_db_session)):
    try:
        return OrganizationService(db).get(org_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{org_id}/members", status_code=201)
def add_member(org_id: int, body: Dict[str, Any], db: Session = Depends(get_db_session)):
    user_id = body.get("user_id")
    role = body.get("role", "engineer")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    return OrganizationService(db).add_member(org_id, user_id, role)


@router.get("/{org_id}/members")
def list_members(org_id: int, db: Session = Depends(get_db_session)):
    return OrganizationService(db).get_members(org_id)
