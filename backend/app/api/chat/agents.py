"""Agent execution API."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.services import AgentService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/run/{log_id}")
def run_agent(log_id: int, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """Execute the diagnostic agent on a log file."""
    try:
        return AgentService(db).run(log_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
