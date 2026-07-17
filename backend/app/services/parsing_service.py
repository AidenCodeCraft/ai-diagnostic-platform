from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.log import Log
from app.services.parser_service import LogParserService
from app.services.rule_engine import RuleEngine


class ParsingService:
    def __init__(self, db: Session):
        self.db = db
        self.rule_engine = RuleEngine()

    def parse_log(self, log_id: int) -> List[Dict[str, Any]]:
        log = self.db.query(Log).filter(Log.id == log_id).first()
        if not log:
            raise ValueError("log not found")

        parser = LogParserService()
        events = parser.parse_file(log.file_path)
        return [
            {
                "raw": event["raw"],
                "level": event["level"],
                "module": event["module"],
                "message": event["message"],
                "source_type": event["source_type"],
                "is_error": event["is_error"],
                "classification": event["classification"],
            }
            for event in events
        ]

    def parse_log_with_status(self, log_id: int) -> Dict[str, Any]:
        events = self.parse_log(log_id)
        suggestions = self.rule_engine.generate_suggestions(events)
        return {
            "log_id": log_id,
            "status": "completed",
            "event_count": len(events),
            "events": events,
            "suggestions": suggestions,
        }

    def get_parse_status(self, log_id: int) -> Dict[str, Any]:
        events = self.parse_log(log_id)
        return {
            "log_id": log_id,
            "status": "completed",
            "event_count": len(events),
        }
