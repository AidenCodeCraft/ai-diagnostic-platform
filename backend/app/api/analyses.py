from fastapi import APIRouter, HTTPException

from app.database import session as session_module
from app.services.analysis_service import AnalysisService
from sqlalchemy.orm import Session
from fastapi import Depends


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.post("/{log_id}/run")
def run_analysis(log_id: int, db: Session = Depends(get_db_session)):
    try:
        return AnalysisService(db).run_analysis(log_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
