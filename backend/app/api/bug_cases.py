"""Bug Case API."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.services.bug_case_service import BugCaseService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/bug-cases", tags=["bug-cases"])


@router.post("", status_code=201)
def create_bug(body: Dict[str, Any], db: Session = Depends(get_db_session)):
    return BugCaseService(db).create(body)


@router.get("")
def list_bugs(page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100), category: Optional[str] = Query(default=None), severity: Optional[str] = Query(default=None), db: Session = Depends(get_db_session)):
    return BugCaseService(db).list(page=page, page_size=page_size, category=category, severity=severity)


@router.get("/search")
def search_bugs(q: str = Query(...), page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db_session)):
    return BugCaseService(db).search(q, page=page, page_size=page_size)


@router.get("/{bug_id}")
def get_bug(bug_id: int, db: Session = Depends(get_db_session)):
    try:
        return BugCaseService(db).get(bug_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{bug_id}")
def update_bug(bug_id: int, body: Dict[str, Any], db: Session = Depends(get_db_session)):
    try:
        return BugCaseService(db).update(bug_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{bug_id}", status_code=204)
def delete_bug(bug_id: int, db: Session = Depends(get_db_session)):
    try:
        BugCaseService(db).delete(bug_id)
        return Response(status_code=204)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
