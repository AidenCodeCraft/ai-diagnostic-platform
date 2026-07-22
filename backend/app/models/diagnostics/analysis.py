from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.database.base import Base


ANALYSIS_STATUS_TRANSITIONS = {
    "pending": {"running"},
    "running": {"completed", "failed"},
    "completed": {"running"},
    "failed": {"running"},
}


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True)
    log_id = Column(Integer, ForeignKey("logs.id"), nullable=False)
    status = Column(String(50), default="pending")
    result = Column(Text)
    confidence = Column(Float)
    summary = Column(Text)
    root_cause = Column(Text)
    next_steps = Column(Text)
    model = Column(String(100))
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def can_transition_to(self, target_status: str) -> bool:
        allowed = ANALYSIS_STATUS_TRANSITIONS.get(self.status, set())
        return target_status in allowed
