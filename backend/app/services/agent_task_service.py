"""Persistent storage for agent task execution records."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.agent_task import AgentTask


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
            existing.log_id = log_id
            existing.status = status
            existing.state = state
            existing.steps = json.dumps(steps)
            existing.tool_plan = json.dumps(tool_plan)
            existing.summary = summary
            existing.error_message = error_message
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
        return {
            "id": task.id,
            "task_id": task.task_id,
            "log_id": task.log_id,
            "status": task.status,
            "state": task.state,
            "steps": json.loads(task.steps or "[]"),
            "tool_plan": json.loads(task.tool_plan or "[]"),
            "summary": task.summary,
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }
