"""Knowledge Base API — CRUD and search for knowledge documents."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.schemas.knowledge import (
    KnowledgeCreate,
    KnowledgeResponse,
    KnowledgeUpdate,
    KnowledgeListResponse,
    KnowledgeSearchResult,
)
from app.services.knowledge_service import KnowledgeService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ------------------------------------------------------------------
# Create
# ------------------------------------------------------------------


@router.post("", response_model=KnowledgeResponse, status_code=201)
def create_document(
    body: KnowledgeCreate,
    db: Session = Depends(get_db_session),
) -> Any:
    """Create a new knowledge document."""
    return KnowledgeService(db).create(body.model_dump())


# ------------------------------------------------------------------
# Queries
# ------------------------------------------------------------------


@router.get("", response_model=KnowledgeListResponse)
def list_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category: Optional[str] = Query(default=None),
    doc_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """List knowledge documents with optional filters."""
    return KnowledgeService(db).list(
        page=page,
        page_size=page_size,
        category=category,
        doc_type=doc_type,
        status=status,
    )


@router.get("/search")
def search_documents(
    q: str = Query(..., min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """Search knowledge documents by keyword."""
    return KnowledgeService(db).search(query_text=q, page=page, page_size=page_size)


@router.get("/categories")
def list_categories(
    db: Session = Depends(get_db_session),
) -> List[str]:
    """List all active document categories."""
    return KnowledgeService(db).list_categories()


@router.get("/{doc_id}", response_model=KnowledgeResponse)
def get_document(
    doc_id: int,
    db: Session = Depends(get_db_session),
) -> Any:
    """Get a single knowledge document by ID."""
    try:
        return KnowledgeService(db).get(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ------------------------------------------------------------------
# Update
# ------------------------------------------------------------------


@router.put("/{doc_id}", response_model=KnowledgeResponse)
def update_document(
    doc_id: int,
    body: KnowledgeUpdate,
    db: Session = Depends(get_db_session),
) -> Any:
    """Update a knowledge document."""
    try:
        return KnowledgeService(db).update(doc_id, body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------


@router.delete("/{doc_id}", status_code=204)
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db_session),
):
    """Delete a knowledge document."""
    try:
        KnowledgeService(db).delete(doc_id)
        return Response(status_code=204)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
