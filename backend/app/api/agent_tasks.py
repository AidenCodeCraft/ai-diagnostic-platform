from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.services.agent_task_service import AgentTaskService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/agents", tags=["agent-tasks"])


@router.get("/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    try:
        return AgentTaskService(db).get_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
