"""任务状态与幂等（P2 步骤 1）。

复用 `agent_tasks` 表：task_id 用 `{log_id}:{stage}:{chunk_no}` 作为幂等键。
规则：
  - 同一任务已 succeeded → 直接跳过（重跑不重复写入）；
  - failed → 允许重试，attempts 累加，超过上限拒绝（交人工）；
  - 状态只有 pending → running → succeeded/failed，不允许回退。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models import AgentTask

logger = get_logger(__name__)

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

MAX_ATTEMPTS = 3


def task_key(log_id: int, stage: str, chunk_no: int = 0) -> str:
    return f"{log_id}:{stage}:{chunk_no}"


def _load_steps(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _dump_steps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


class TaskStateStore:
    """任务状态读写（幂等 claim + 状态机）。"""

    def __init__(self, db: Session):
        self.db = db

    def get(self, log_id: int, stage: str, chunk_no: int = 0) -> Optional[AgentTask]:
        return (
            self.db.query(AgentTask)
            .filter(AgentTask.task_id == task_key(log_id, stage, chunk_no))
            .first()
        )

    def claim(self, *, log_id: int, stage: str, chunk_no: int = 0) -> Dict[str, Any]:
        """尝试占用任务。

        Returns:
            {"task": AgentTask | None, "claimed": bool, "reason": str}
        """
        task = self.get(log_id, stage, chunk_no)
        if task is not None:
            if task.status == STATUS_SUCCEEDED:
                return {"task": task, "claimed": False, "reason": "already-succeeded"}
            steps = _load_steps(task.steps)
            attempts = int(steps.get("attempts") or 0)
            if attempts >= MAX_ATTEMPTS:
                return {"task": task, "claimed": False, "reason": "attempts-exhausted"}
            steps["attempts"] = attempts + 1
            task.steps = _dump_steps(steps)
            task.status = STATUS_RUNNING
            task.state = stage
            task.updated_at = datetime.now(timezone.utc)
        else:
            task = AgentTask(
                task_id=task_key(log_id, stage, chunk_no),
                log_id=log_id,
                status=STATUS_RUNNING,
                state=stage,
                steps=_dump_steps({"attempts": 1}),
            )
            self.db.add(task)

        self.db.commit()
        self.db.refresh(task)
        return {"task": task, "claimed": True, "reason": "ok"}

    def finish(
        self,
        task: AgentTask,
        *,
        status: str = STATUS_SUCCEEDED,
        summary: Optional[str] = None,
        error: Optional[str] = None,
    ) -> AgentTask:
        task.status = status
        task.summary = summary or task.summary
        task.error_message = error
        task.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(task)
        return task

    def summary(self, log_id: int) -> Dict[str, Any]:
        """整条链的进度汇总（供 finalize 判断与前端展示）。"""
        rows = (
            self.db.query(AgentTask)
            .filter(AgentTask.task_id.like(f"{log_id}:%"))
            .all()
        )
        stages: Dict[str, Dict[str, int]] = {}
        for row in rows:
            stage = str(row.state or "unknown")
            bucket = stages.setdefault(stage, {"total": 0, "succeeded": 0, "failed": 0, "running": 0})
            bucket["total"] += 1
            if row.status == STATUS_SUCCEEDED:
                bucket["succeeded"] += 1
            elif row.status == STATUS_FAILED:
                bucket["failed"] += 1
            elif row.status == STATUS_RUNNING:
                bucket["running"] += 1
        return {
            "log_id": log_id,
            "stages": stages,
            "tasks": len(rows),
            "all_succeeded": bool(rows) and all(row.status == STATUS_SUCCEEDED for row in rows),
            "failed_tasks": [row.task_id for row in rows if row.status == STATUS_FAILED],
        }

    def list_tasks(self, log_id: int) -> List[AgentTask]:
        return (
            self.db.query(AgentTask)
            .filter(AgentTask.task_id.like(f"{log_id}:%"))
            .order_by(AgentTask.id.asc())
            .all()
        )
