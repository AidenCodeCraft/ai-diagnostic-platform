from __future__ import annotations

import json
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.agent_task import AgentTask


class AgentTaskService:
    def __init__(self, db: Session):
        self.db = db

    def save_task(self, task_id: str, log_id: int, status: str, state: str, steps: List[str], tool_plan: List[Dict[str, Any]], summary: str) -> Dict[str, Any]:
        task = self.db.query(AgentTask).filter(AgentTask.task_id == task_id).first()
        if task is None:
            task = AgentTask(
                task_id=task_id,
                log_id=log_id,
                status=status,
                state=state,
                steps=json.dumps(steps),
                tool_plan=json.dumps(tool_plan),
                summary=summary,
            )
            self.db.add(task)
        else:
            task.log_id = log_id
            task.status = status
            task.state = state
            task.steps = json.dumps(steps)
            task.tool_plan = json.dumps(tool_plan)
            task.summary = summary

        self.db.commit()
        self.db.refresh(task)
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> Dict[str, Any]:
        task = self.db.query(AgentTask).filter(AgentTask.task_id == task_id).first()
        if not task:
            raise ValueError("task not found")
        return {
            "task_id": task.task_id,
            "log_id": task.log_id,
            "status": task.status,
            "state": task.state,
            "steps": json.loads(task.steps or "[]"),
            "tool_plan": json.loads(task.tool_plan or "[]"),
            "summary": task.summary,
        }
