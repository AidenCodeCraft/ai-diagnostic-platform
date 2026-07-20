"""Diagnostic Report API."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.schemas.report import ReportDetail, ReportListResponse
from app.services.report_service import ReportService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/reports", tags=["reports"])


# ------------------------------------------------------------------
# Generate
# ------------------------------------------------------------------


@router.post("/{log_id}")
def generate_report(
    log_id: int,
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """Generate a diagnostic report from analysis results for a log."""
    try:
        return ReportService(db).generate_report(log_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ------------------------------------------------------------------
# Queries
# ------------------------------------------------------------------


@router.get("", response_model=ReportListResponse)
def list_reports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """List all diagnostic reports with pagination."""
    return ReportService(db).list_reports(page=page, page_size=page_size)


@router.get("/{report_id}", response_model=ReportDetail)
def get_report(
    report_id: int,
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """Get a single report's detail."""
    try:
        return ReportService(db).get_report_detail(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{report_id}/markdown", response_class=PlainTextResponse)
def export_report_markdown(
    report_id: int,
    db: Session = Depends(get_db_session),
) -> str:
    """Export a report as Markdown text."""
    try:
        return ReportService(db).export_markdown(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------


@router.delete("/{report_id}", status_code=204)
def delete_report(
    report_id: int,
    db: Session = Depends(get_db_session),
):
    """Delete a report."""
    try:
        ReportService(db).delete_report(report_id)
        return Response(status_code=204)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
