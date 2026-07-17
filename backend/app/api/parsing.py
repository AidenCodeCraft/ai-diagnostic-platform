from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.services.parsing_service import ParsingService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/logs", tags=["parsing"])


@router.post("/{log_id}/parse")
def parse_log(log_id: int, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    try:
        return ParsingService(db).parse_log_with_status(log_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{log_id}/events")
def get_log_events(log_id: int, db: Session = Depends(get_db_session)) -> List[Dict[str, Any]]:
    try:
        return ParsingService(db).parse_log(log_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{log_id}/parse-status")
def get_parse_status(log_id: int, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    try:
        return ParsingService(db).get_parse_status(log_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
