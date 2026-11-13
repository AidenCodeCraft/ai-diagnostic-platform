from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Log, LogEvent
from app.schemas import ParseResult
from app.services.diagnostics.log_service import LogService
from app.services.diagnostics.log_storage import LogStorage
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
        """Parse a stored log by ID and return structured events.

        优先读取已持久化的事件（避免每次重新解析/重复下载 MinIO 对象）；
        传 force_source 或尚未解析时回退到实时解析。
        """
        log = self._get_log(log_id)

        if not force_source:
            stored = (
                self.db.query(LogEvent)
                .filter(LogEvent.log_id == log_id)
                .order_by(LogEvent.line_no.asc())
                .all()
            )
            if stored:
                return [self._event_to_dict(row) for row in stored]

        local_path = LogStorage().materialize(str(log.file_path))
        events = self._parser.parse_file(str(local_path), force_source=force_source)
        return events

    def parse_log_structured(self, log_id: int, force_source: Optional[str] = None) -> ParseResult:
        """Parse a stored log and return a structured ParseResult."""
        log = self._get_log(log_id)

        local_path = LogStorage().materialize(str(log.file_path))
        raw_events = self._parser.parse_structured(str(local_path), force_source=force_source)
        return ParseResult.from_events(raw_events, log_id=log_id, status="completed")

    # ------------------------------------------------------------------
    # Parse with rule suggestions
    # ------------------------------------------------------------------

    def parse_log_with_status(self, log_id: int) -> Dict[str, Any]:
        """Parse log, run rule engine, return events + suggestions."""
        log = self._get_log(log_id)
        self._transition_status(log, "parsing")

        try:
            local_path = LogStorage().materialize(str(log.file_path))
            raw_events = self._parser.parse_structured(str(local_path))
            result = ParseResult.from_events(raw_events, log_id=log_id, status="completed")
            suggestions = self.rule_engine.generate_suggestions(raw_events)

            self._persist_events(log_id, raw_events)
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
    # Event persistence / queries
    # ------------------------------------------------------------------

    def _persist_events(self, log_id: int, events: List[Any]) -> int:
        """全量替换该日志的解析事件（重复解析时幂等）。"""
        self.db.query(LogEvent).filter(LogEvent.log_id == log_id).delete()
        rows = []
        for event in events:
            rows.append(LogEvent(
                log_id=log_id,
                line_no=int(getattr(event, "line_no", 0) or 0),
                timestamp=getattr(event, "timestamp", None),
                level=str(getattr(event, "level", "INFO") or "INFO"),
                module=str(getattr(event, "module", "system") or "system"),
                source_type=str(getattr(event, "source_type", "generic") or "generic"),
                is_error=bool(getattr(event, "is_error", False)),
                classification=str(getattr(event, "classification", "unknown") or "unknown"),
                message=str(getattr(event, "message", "") or "")[:4000],
                raw=str(getattr(event, "raw", "") or "")[:8000],
            ))
        if rows:
            self.db.add_all(rows)
        self.db.commit()
        return len(rows)

    def query_events(
        self,
        log_id: int,
        page: int = 1,
        page_size: int = 50,
        level: Optional[str] = None,
        module: Optional[str] = None,
        is_error: Optional[bool] = None,
        keyword: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分页 + 过滤查询已持久化的解析事件。"""
        self._get_log(log_id)
        query = self.db.query(LogEvent).filter(LogEvent.log_id == log_id)

        if level:
            query = query.filter(LogEvent.level == level.upper())
        if module:
            query = query.filter(LogEvent.module == module)
        if is_error is not None:
            query = query.filter(LogEvent.is_error.is_(is_error))
        if source_type:
            query = query.filter(LogEvent.source_type == source_type)
        if keyword:
            pattern = f"%{keyword}%"
            query = query.filter(or_(
                LogEvent.message.ilike(pattern),
                LogEvent.raw.ilike(pattern),
            ))

        total = query.count()
        rows = (
            query.order_by(LogEvent.line_no.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {
            "items": [self._event_to_dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    def _event_to_dict(row: LogEvent) -> Dict[str, Any]:
        return {
            "id": row.id,
            "log_id": row.log_id,
            "line_no": row.line_no,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "level": row.level,
            "module": row.module,
            "source_type": row.source_type,
            "is_error": row.is_error,
            "classification": row.classification,
            "message": row.message,
            "raw": row.raw,
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
            LogService(self.db).update_status(int(log.id), status)  # type: ignore[arg-type]
        except ValueError:
            pass  # Allow transitions that may already be in target state
