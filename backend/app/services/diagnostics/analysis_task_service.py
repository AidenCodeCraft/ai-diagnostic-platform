from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models import Analysis, Log
from app.services.infrastructure.llm_service import LLMService
from app.services.diagnostics.log_service import LogService
from app.services.diagnostics.parser_service import LogParserService

logger = get_logger(__name__)


class AnalysisTaskService:
    """Unified service for managing analysis task lifecycle.

    Merges AnalysisService + AnalysisResultService into a single,
    coherent service with proper status tracking.
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Create / Start
    # ------------------------------------------------------------------

    def create_analysis(self, log_id: int, model: Optional[str] = None) -> Analysis:
        """Create a new analysis task for a given log."""
        log = self._get_log(log_id)
        logger.info("Creating analysis: log_id=%d model=%s", log_id, model or "mock")

        analysis = Analysis(
            log_id=log.id,
            status="pending",
            model=model or "mock",
        )
        self.db.add(analysis)
        self.db.commit()
        self.db.refresh(analysis)
        return analysis

    def run_analysis(self, log_id: int, model: Optional[str] = None) -> Dict[str, Any]:
        """Create and execute an analysis task end-to-end.

        Flow: pending → running → completed|failed
        """
        # Create or reuse existing analysis
        analysis = self.db.query(Analysis).filter(
            Analysis.log_id == log_id
        ).order_by(Analysis.created_at.desc()).first()

        if analysis is None:
            analysis = self.create_analysis(log_id, model)

        # Set status to running
        analysis.status = "running"
        self.db.commit()
        self.db.refresh(analysis)

        try:
            result = self._execute_analysis(analysis)
            analysis.status = "completed"
            self.db.commit()
            self.db.refresh(analysis)
            result["status"] = analysis.status
            return result
        except Exception as exc:
            analysis.status = "failed"
            analysis.error_message = str(exc)
            self.db.commit()
            raise

    def _execute_analysis(self, analysis: Analysis) -> Dict[str, Any]:
        """Core analysis: verify → pipeline(parse → rules → RAG → LLM) → persist."""
        log = self._get_log(analysis.log_id)

        from pathlib import Path
        file_path = Path(log.file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Log file not found: {log.file_path}")

        if log.status in ("uploaded", "parsing", "parsed"):
            log.status = "analyzing"
            self.db.commit()

        # Run full diagnostic pipeline (Rule Engine + RAG + LLM)
        from app.services.diagnostics.diagnosis_pipeline import DiagnosisPipeline
        pipeline = DiagnosisPipeline(self.db, model=analysis.model)
        result = pipeline.run(str(file_path), user_query="")

        # Persist
        analysis.result = json.dumps(result)
        analysis.summary = result.get("summary", "")
        analysis.root_cause = result.get("root_cause", "")
        analysis.confidence = float(result.get("confidence", 0.5) or 0.5)
        next_steps = result.get("next_steps", [])
        analysis.next_steps = json.dumps(self._normalize_next_steps(next_steps))
        analysis.model = str(analysis.model or "diagnosis-pipeline")

        self.db.commit()
        self.db.refresh(analysis)

        return {
            "id": analysis.id,
            "log_id": analysis.log_id,
            "status": analysis.status,
            "summary": analysis.summary,
            "root_cause": analysis.root_cause,
            "confidence": analysis.confidence,
            "next_steps": self._normalize_next_steps(analysis.next_steps),
            "model": analysis.model,
            "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        }

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_analysis(self, analysis_id: int) -> Analysis:
        analysis = self.db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if not analysis:
            raise ValueError("analysis not found")
        return analysis

    def get_analysis_by_log(self, log_id: int) -> Analysis:
        analysis = self.db.query(Analysis).filter(Analysis.log_id == log_id).first()
        if not analysis:
            raise ValueError("analysis not found")
        return analysis

    def list_analyses(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        query = self.db.query(Analysis)
        if status:
            query = query.filter(Analysis.status == status)

        total = query.count()
        items = (
            query.order_by(Analysis.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_result(self, analysis_id: int) -> Dict[str, Any]:
        """Return structured analysis result."""
        analysis = self.get_analysis(analysis_id)
        return {
            "id": analysis.id,
            "log_id": analysis.log_id,
            "status": analysis.status,
            "summary": analysis.summary or "",
            "root_cause": analysis.root_cause or "",
            "confidence": analysis.confidence or 0.0,
            "next_steps": self._normalize_next_steps(analysis.next_steps),
            "model": analysis.model or "mock",
            "error_message": analysis.error_message,
            "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
            "updated_at": analysis.updated_at.isoformat() if analysis.updated_at else None,
        }

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_analysis(self, analysis_id: int) -> None:
        analysis = self.get_analysis(analysis_id)
        self.db.delete(analysis)
        self.db.commit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_log(self, log_id: int) -> Log:
        log = self.db.query(Log).filter(Log.id == log_id).first()
        if not log:
            raise ValueError("log not found")
        return log

    @staticmethod
    def _normalize_payload(payload: Any) -> Dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str):
            stripped = payload.strip()
            if not stripped:
                return {}
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return {"summary": stripped}
        return {"summary": str(payload)}

    @staticmethod
    def _normalize_next_steps(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except json.JSONDecodeError:
                pass
            return [stripped]
        return []
