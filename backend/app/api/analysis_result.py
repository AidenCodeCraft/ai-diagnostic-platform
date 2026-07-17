from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.services.analysis_result_service import AnalysisResultService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/analysis", tags=["analysis-result"])


@router.post("/{log_id}/llm")
def create_analysis(log_id: int, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    try:
        return AnalysisResultService(db).create_or_update_analysis(log_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{log_id}")
def get_analysis(log_id: int, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    try:
        return AnalysisResultService(db).get_analysis(log_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
