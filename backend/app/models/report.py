from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.database.base import Base


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    log_id = Column(Integer, ForeignKey("logs.id"), nullable=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id"), nullable=True)
    title = Column(String(300), nullable=True)
    content = Column(Text)              # JSON blob with full report data
    format = Column(String(20), default="json")  # json, markdown, html, pdf
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
