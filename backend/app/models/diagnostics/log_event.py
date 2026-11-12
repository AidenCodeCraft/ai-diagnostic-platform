from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.database.base import Base


class LogEvent(Base):
    """持久化的日志解析事件（支持分页 / 过滤查询）。"""

    __tablename__ = "log_events"

    id = Column(Integer, primary_key=True)
    log_id = Column(Integer, ForeignKey("logs.id"), nullable=False, index=True)
    line_no = Column(Integer, nullable=False, default=0)
    timestamp = Column(DateTime, nullable=True)
    level = Column(String(20), default="INFO")
    module = Column(String(100), default="system")
    source_type = Column(String(50), default="generic")
    is_error = Column(Boolean, default=False)
    classification = Column(String(100), default="unknown")
    message = Column(Text)
    raw = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
