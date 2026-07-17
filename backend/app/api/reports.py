from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.services.report_service import ReportService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
def list_reports(db: Session = Depends(get_db_session)) -> List[Dict[str, Any]]:
    return ReportService(db).list_reports()


@router.get("/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    try:
        return ReportService(db).get_report(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{log_id}")
def create_report(log_id: int, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    try:
        return ReportService(db).generate_report(log_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
