from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.services import ParsingService


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


@router.get("/{log_id}/events/query")
def query_log_events(
    log_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    level: Optional[str] = Query(default=None),
    module: Optional[str] = Query(default=None),
    is_error: Optional[bool] = Query(default=None),
    keyword: Optional[str] = Query(default=None, max_length=200),
    source_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """分页/过滤查询已持久化的解析事件（需先 POST /logs/{id}/parse）。"""
    try:
        return ParsingService(db).query_events(
            log_id,
            page=page,
            page_size=page_size,
            level=level,
            module=module,
            is_error=is_error,
            keyword=keyword,
            source_type=source_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
