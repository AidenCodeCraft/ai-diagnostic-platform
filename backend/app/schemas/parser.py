from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ParsedEventSchema(BaseModel):
    """Pydantic schema for a single parsed log event."""

    raw: str
    message: str = ""
    level: str = "INFO"
    module: str = "system"
    source_type: str = "generic"
    is_error: bool = False
    classification: str = "unknown"
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ParseResult(BaseModel):
    """Schema for a complete multi-line parse result."""

    log_id: Optional[int] = None
    status: str
    source_type: str
    event_count: int
    error_count: int
    warning_count: int
    events: List[ParsedEventSchema]
    error_classifications: Dict[str, int] = Field(default_factory=dict)

    @classmethod
    def from_events(
        cls,
        events: list,
        log_id: Optional[int] = None,
        status: str = "completed",
    ) -> "ParseResult":
        error_events = [e for e in events if e.is_error]
        warning_events = [e for e in events if e.level.upper() in ("WARN", "WARNING")]

        classifications: Dict[str, int] = {}
        for ev in error_events:
            classifications[ev.classification] = classifications.get(ev.classification, 0) + 1

        event_schemas = [
            ParsedEventSchema(
                raw=getattr(e, "raw", ""),
                message=getattr(e, "message", ""),
                level=getattr(e, "level", "INFO"),
                module=getattr(e, "module", "system"),
                source_type=getattr(e, "source_type", "generic"),
                is_error=getattr(e, "is_error", False),
                classification=getattr(e, "classification", "unknown"),
                timestamp=getattr(e, "timestamp", None),
                metadata=getattr(e, "metadata", {}),
            )
            for e in events
        ]

        return cls(
            log_id=log_id,
            status=status,
            source_type=event_schemas[0].source_type if event_schemas else "generic",
            event_count=len(event_schemas),
            error_count=len(error_events),
            warning_count=len(warning_events),
            events=event_schemas,
            error_classifications=classifications,
        )
