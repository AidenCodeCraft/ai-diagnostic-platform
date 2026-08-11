"""Persistent storage for agent task execution records."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import AgentTask


class AgentTaskService:
    """CRUD service for agent execution task records."""

    def __init__(self, db: Session):
        self.db = db

    def save_task(
        self,
        task_id: str,
        log_id: int,
        status: str,
        state: str,
        steps: List[Dict[str, Any]],
        tool_plan: List[Dict[str, Any]],
        summary: str,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = self.db.query(AgentTask).filter(
            AgentTask.task_id == task_id
        ).first()

        if existing:
            setattr(existing, 'log_id', log_id)
            setattr(existing, 'status', status)
            setattr(existing, 'state', state)
            setattr(existing, 'steps', json.dumps(steps))
            setattr(existing, 'tool_plan', json.dumps(tool_plan))
            setattr(existing, 'summary', summary)
            setattr(existing, 'error_message', error_message)
        else:
            task = AgentTask(
                task_id=task_id,
                log_id=log_id,
                status=status,
                state=state,
                steps=json.dumps(steps),
                tool_plan=json.dumps(tool_plan),
                summary=summary,
                error_message=error_message,
            )
            self.db.add(task)

        self.db.commit()
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> Dict[str, Any]:
        task = self.db.query(AgentTask).filter(
            AgentTask.task_id == task_id
        ).first()
        if not task:
            raise ValueError("task not found")
        return self._to_dict(task)

    def list_tasks(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        query = self.db.query(AgentTask)
        if status:
            query = query.filter(AgentTask.status == status)

        total = query.count()
        items = (
            query.order_by(AgentTask.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return {
            "items": [self._to_dict(t) for t in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def delete_task(self, task_id: str) -> None:
        task = self.db.query(AgentTask).filter(
            AgentTask.task_id == task_id
        ).first()
        if not task:
            raise ValueError("task not found")
        self.db.delete(task)
        self.db.commit()

    @staticmethod
    def _to_dict(task: AgentTask) -> Dict[str, Any]:
        steps_raw = str(task.steps or "[]")
        tool_plan_raw = str(task.tool_plan or "[]")
        created_at_raw = task.created_at  # type: ignore[assignment]
        updated_at_raw = task.updated_at  # type: ignore[assignment]
        return {
            "id": task.id,
            "task_id": task.task_id,
            "log_id": task.log_id,
            "status": task.status,
            "state": task.state,
            "steps": json.loads(steps_raw),
            "tool_plan": json.loads(tool_plan_raw),
            "summary": task.summary,
            "error_message": task.error_message,
            "created_at": created_at_raw.isoformat() if created_at_raw is not None else None,
            "updated_at": updated_at_raw.isoformat() if updated_at_raw is not None else None,
        }
