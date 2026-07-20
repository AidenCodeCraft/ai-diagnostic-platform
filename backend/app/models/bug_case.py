from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.database.base import Base


class BugCase(Base):
    __tablename__ = "bug_cases"

    id = Column(Integer, primary_key=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    module = Column(String(100), nullable=True)
    severity = Column(String(20), default="medium")  # critical / high / medium / low
    root_cause = Column(Text, nullable=True)
    solution = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    log_id = Column(Integer, ForeignKey("logs.id"), nullable=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
