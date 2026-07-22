"""Agent service — orchestrates diagnostic workflows using the Agent Framework."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.agents.core.agent import AgentResult, BaseAgent
from app.agents.core.state import AgentState
from app.agents.planner.simple_planner import SimplePlanner
from app.agents.tools.builtin import create_default_registry
from app.agents.core.tool import ToolRegistry
from app.models import Log
from app.services.chat.agent_task_service import AgentTaskService


class DiagnosticAgent(BaseAgent):
    """Agent that executes a full diagnostic workflow on a log file."""

    name = "diagnostic_agent"
    description = "Parses device logs, runs rule checks, calls LLM, and generates reports."

    def __init__(self, tool_registry: ToolRegistry | None = None) -> None:
        super().__init__(tool_registry or create_default_registry())
        self.planner = SimplePlanner()

    def plan(self, **context: Any) -> List[str]:
        log_id = context.pop("log_id", 0)
        return self.planner.build_plan(log_id, **context)


class AgentService:
    """Service layer for running diagnostic agents and persisting results."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def run(self, log_id: int) -> Dict[str, Any]:
        """Execute the diagnostic agent on a log file."""
        log = self.db.query(Log).filter(Log.id == log_id).first()
        if not log:
            raise ValueError("log not found")

        # Build context
        with open(log.file_path, "r", encoding="utf-8", errors="ignore") as f:
            log_content = f.read()

        context = {
            "log_id": log_id,
            "log_file_path": log.file_path,
            "log_filename": log.filename,
            "log_content": log_content,
            "db_session": self.db,
        }

        # Run agent
        agent = DiagnosticAgent()
        result = agent.run(**context)

        # Persist
        task_id = str(uuid.uuid4())
        task_service = AgentTaskService(self.db)

        task_service.save_task(
            task_id=task_id,
            log_id=log_id,
            status="completed" if result.success else "failed",
            state=result.state.value,
            steps=result.steps,
            tool_plan=result.tool_plan,
            summary=result.summary,
            error_message=result.error,
        )

        return {
            "task_id": task_id,
            "log_id": log_id,
            "status": "completed" if result.success else "failed",
            "state": result.state.value,
            "steps": result.steps,
            "tool_plan": result.tool_plan,
            "summary": result.summary,
            "error": result.error,
        }
