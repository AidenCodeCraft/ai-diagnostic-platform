from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import Log
from app.schemas import ParseResult, ParsedEventSchema
from app.services.diagnostics.log_service import LogService
from app.services.diagnostics.parser_service import LogParserService
from app.services.system.rule_engine import RuleEngine


class ParsingService:
    """Service that orchestrates parsing, rule matching, and status tracking."""

    def __init__(self, db: Session):
        self.db = db
        self.rule_engine = RuleEngine()
        self._parser = LogParserService()

    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------

    def parse_log(self, log_id: int, force_source: Optional[str] = None) -> List[Dict[str, Any]]:
        """Parse a stored log by ID and return structured events."""
        log = self._get_log(log_id)

        events = self._parser.parse_file(log.file_path, force_source=force_source)
        return events

    def parse_log_structured(self, log_id: int, force_source: Optional[str] = None) -> ParseResult:
        """Parse a stored log and return a structured ParseResult."""
        log = self._get_log(log_id)

        raw_events = self._parser.parse_structured(log.file_path, force_source=force_source)
        return ParseResult.from_events(raw_events, log_id=log_id, status="completed")

    # ------------------------------------------------------------------
    # Parse with rule suggestions
    # ------------------------------------------------------------------

    def parse_log_with_status(self, log_id: int) -> Dict[str, Any]:
        """Parse log, run rule engine, return events + suggestions."""
        log = self._get_log(log_id)
        self._transition_status(log, "parsing")

        try:
            raw_events = self._parser.parse_structured(log.file_path)
            result = ParseResult.from_events(raw_events, log_id=log_id, status="completed")
            suggestions = self.rule_engine.generate_suggestions(raw_events)

            self._transition_status(log, "parsed")

            return {
                "log_id": log_id,
                "status": "completed",
                "source_type": result.source_type,
                "event_count": result.event_count,
                "error_count": result.error_count,
                "warning_count": result.warning_count,
                "error_classifications": result.error_classifications,
                "events": [e.model_dump() for e in result.events],
                "suggestions": suggestions,
            }
        except Exception:
            self._transition_status(log, "parse_failed")
            raise

    def get_parse_status(self, log_id: int) -> Dict[str, Any]:
        """Return current parse status for a log."""
        log = self._get_log(log_id)
        return {
            "log_id": log_id,
            "status": log.status,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_log(self, log_id: int) -> Log:
        log = self.db.query(Log).filter(Log.id == log_id).first()
        if not log:
            raise ValueError("log not found")
        return log

    def _transition_status(self, log: Log, status: str) -> None:
        """Update the log status using the status machine."""
        try:
            LogService(self.db).update_status(log.id, status)
        except ValueError:
            pass  # Allow transitions that may already be in target state
