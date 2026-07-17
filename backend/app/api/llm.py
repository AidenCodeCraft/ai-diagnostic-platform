from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.services.analysis_result_service import AnalysisResultService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/analysis", tags=["llm"])


@router.post("/{log_id}/llm")
def generate_llm_summary(log_id: int, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    return AnalysisResultService(db).create_or_update_analysis(log_id)
