from __future__ import annotations

import uuid
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.log import Log
from app.services.agent_task_service import AgentTaskService
from app.services.analysis_result_service import AnalysisResultService
from app.services.parsing_service import ParsingService


class ToolManager:
    def build_tool_plan(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {"name": "parse_log", "status": "ready"},
            {"name": "rule_check", "status": "ready"},
            {"name": "generate_analysis", "status": "ready"},
            {"name": "generate_report", "status": "ready"},
        ]


class AgentService:
    def __init__(self, db: Session):
        self.db = db
        self.tool_manager = ToolManager()

    def _build_plan(self, log: Log, events: List[Dict[str, Any]]) -> List[str]:
        return [tool["name"] for tool in self.tool_manager.build_tool_plan(events)]

    def run(self, log_id: int) -> Dict[str, Any]:
        log = self.db.query(Log).filter(Log.id == log_id).first()
        if not log:
            raise ValueError("log not found")

        events = ParsingService(self.db).parse_log(log_id)
        plan = self._build_plan(log, events)
        tool_plan = self.tool_manager.build_tool_plan(events)

        analysis_service = AnalysisResultService(self.db)
        analysis_service.create_or_update_analysis(log_id)

        task_id = str(uuid.uuid4())
        payload = {
            "task_id": task_id,
            "log_id": log_id,
            "status": "completed",
            "state": "COMPLETED",
            "steps": plan,
            "tool_plan": tool_plan,
            "summary": f"Planned and executed diagnostic workflow for {log.filename}",
        }
        AgentTaskService(self.db).save_task(
            task_id=task_id,
            log_id=log_id,
            status=payload["status"],
            state=payload["state"],
            steps=payload["steps"],
            tool_plan=payload["tool_plan"],
            summary=payload["summary"],
        )

        return payload
