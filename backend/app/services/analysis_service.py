from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.analysis import Analysis
from app.models.log import Log
from app.services.parser_service import LogParserService


class AnalysisService:
    def __init__(self, db: Session):
        self.db = db

    def run_analysis(self, log_id: int) -> Dict[str, Any]:
        log = self.db.query(Log).filter(Log.id == log_id).first()
        if not log:
            raise ValueError("log not found")

        parser = LogParserService()
        events = parser.parse_file(log.file_path)
        error_events = [event for event in events if event["is_error"]]

        result = {
            "event_count": len(events),
            "errors": error_events,
            "summary": f"Parsed {len(events)} events from {log.filename}",
        }

        analysis = Analysis(
            log_id=log.id,
            result=str(result),
            confidence=max(0.4, min(0.95, 0.4 + 0.1 * len(error_events))),
        )
        self.db.add(analysis)
        self.db.commit()
        self.db.refresh(analysis)

        return {
            "id": analysis.id,
            "log_id": analysis.log_id,
            "result": result,
            "confidence": analysis.confidence,
        }
