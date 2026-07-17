from __future__ import annotations

import json
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.models.analysis import Analysis
from app.models.log import Log
from app.services.llm_service import LLMService
from app.services.parsing_service import ParsingService


class AnalysisResultService:
    def __init__(self, db: Session):
        self.db = db

    def _coerce_payload(self, payload: Any) -> Dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str):
            stripped = payload.strip()
            if not stripped:
                return {}
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                try:
                    parsed = eval(stripped, {"__builtins__": {}})
                except Exception:
                    return {"summary": stripped}
            if isinstance(parsed, dict):
                return parsed
            return {"summary": str(parsed)}
        return {"summary": str(payload)}

    def _coerce_next_steps(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return [stripped]
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        return []

    def create_or_update_analysis(self, log_id: int) -> Dict[str, Any]:
        log = self.db.query(Log).filter(Log.id == log_id).first()
        if not log:
            raise ValueError("log not found")

        events = ParsingService(self.db).parse_log(log_id)
        with open(log.file_path, "r", encoding="utf-8", errors="ignore") as handle:
            log_content = handle.read()
        llm_result = LLMService().generate_summary(log_content, events)
        payload = self._coerce_payload(llm_result)

        summary_text = payload.get("summary") or "No summary generated."
        confidence_value = float(payload.get("confidence", 0.8) or 0.8)
        root_cause_text = payload.get("root_cause") or "Unable to determine root cause from the current analysis."
        next_steps_value = self._coerce_next_steps(payload.get("next_steps", []))
        model_name = payload.get("model") or "mock"

        analysis = self.db.query(Analysis).filter(Analysis.log_id == log_id).first()
        if analysis is None:
            analysis = Analysis(log_id=log_id)
            self.db.add(analysis)

        analysis.result = json.dumps(payload)
        analysis.confidence = confidence_value
        analysis.summary = summary_text
        analysis.root_cause = root_cause_text
        analysis.next_steps = json.dumps(next_steps_value)
        analysis.model = str(model_name)

        self.db.commit()
        self.db.refresh(analysis)

        return {
            "id": analysis.id,
            "log_id": analysis.log_id,
            "status": "completed",
            "summary": summary_text,
            "model": model_name,
            "confidence": confidence_value,
            "root_cause": root_cause_text,
            "next_steps": next_steps_value,
            "result": payload,
        }

    def get_analysis(self, log_id: int) -> Dict[str, Any]:
        analysis = self.db.query(Analysis).filter(Analysis.log_id == log_id).first()
        if not analysis:
            raise ValueError("analysis not found")

        payload = self._coerce_payload(analysis.result)
        if analysis.summary:
            payload["summary"] = analysis.summary
        if analysis.root_cause:
            payload["root_cause"] = analysis.root_cause
        if analysis.next_steps:
            payload["next_steps"] = self._coerce_next_steps(analysis.next_steps)
        if analysis.model:
            payload["model"] = analysis.model
        if analysis.confidence is not None:
            payload["confidence"] = analysis.confidence

        return {
            "id": analysis.id,
            "log_id": analysis.log_id,
            "status": "completed",
            "summary": payload.get("summary", ""),
            "confidence": payload.get("confidence", 0.0),
            "root_cause": payload.get("root_cause", ""),
            "next_steps": payload.get("next_steps", []),
            "model": payload.get("model", "mock"),
        }
