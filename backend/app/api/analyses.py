from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.schemas.analysis import AnalysisResponse, AnalysisListResponse
from app.services.analysis_task_service import AnalysisTaskService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/analyses", tags=["analyses"])


# ------------------------------------------------------------------
# Create / Run
# ------------------------------------------------------------------


@router.post("", response_model=AnalysisResponse, status_code=201)
def create_analysis(
    log_id: int = Query(...),
    model: Optional[str] = Query(default=None),
    db: Session = Depends(get_db_session),
) -> Any:
    """Create a new analysis task."""
    try:
        return AnalysisTaskService(db).create_analysis(log_id, model=model)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/run", response_model=Dict[str, Any])
def run_analysis(
    log_id: int = Query(...),
    model: Optional[str] = Query(default=None),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """Create and execute an analysis task for the given log."""
    try:
        return AnalysisTaskService(db).run_analysis(log_id, model=model)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ------------------------------------------------------------------
# Queries
# ------------------------------------------------------------------


@router.get("", response_model=AnalysisListResponse)
def list_analyses(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """List analysis tasks with optional status filter and pagination."""
    return AnalysisTaskService(db).list_analyses(
        page=page,
        page_size=page_size,
        status=status,
    )


@router.get("/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(
    analysis_id: int,
    db: Session = Depends(get_db_session),
) -> Any:
    """Get a single analysis task by ID."""
    try:
        return AnalysisTaskService(db).get_analysis(analysis_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{analysis_id}/result", response_model=Dict[str, Any])
def get_analysis_result(
    analysis_id: int,
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """Get the full result of an analysis task."""
    try:
        return AnalysisTaskService(db).get_result(analysis_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------


@router.delete("/{analysis_id}", status_code=204)
def delete_analysis(
    analysis_id: int,
    db: Session = Depends(get_db_session),
) -> None:
    """Delete an analysis task."""
    try:
        AnalysisTaskService(db).delete_analysis(analysis_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
