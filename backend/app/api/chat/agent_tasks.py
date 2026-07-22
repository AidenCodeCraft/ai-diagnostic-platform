"""Agent task query API."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.services import AgentTaskService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/agents/tasks", tags=["agent-tasks"])


@router.get("")
def list_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """List agent tasks with optional filtering and pagination."""
    return AgentTaskService(db).list_tasks(page=page, page_size=page_size, status=status)


@router.get("/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """Get a single agent task by task_id."""
    try:
        return AgentTaskService(db).get_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, db: Session = Depends(get_db_session)):
    """Delete an agent task record."""
    try:
        AgentTaskService(db).delete_task(task_id)
        return Response(status_code=204)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
