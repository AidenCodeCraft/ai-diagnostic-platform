from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.database.base import Base


LOG_STATUS_TRANSITIONS = {
    "uploaded": {"parsing", "deleted"},
    "parsing": {"parsed", "parse_failed", "deleted"},
    "parsed": {"analyzing", "deleted"},
    "analyzing": {"analyzed", "analysis_failed", "deleted"},
    "analyzed": {"deleted"},
    "parse_failed": {"deleted"},
    "analysis_failed": {"deleted"},
    "deleted": set(),
}


class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    size = Column(Integer, nullable=True)
    status = Column(String(50), default="uploaded")
    project_id = Column(Integer, ForeignKey("projects.id"))
    upload_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    device = Column(String(100), nullable=True)
    version = Column(String(50), nullable=True)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def can_transition_to(self, target_status: str) -> bool:
        allowed = LOG_STATUS_TRANSITIONS.get(self.status, set())
        return target_status in allowed
