from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text

from app.database.base import Base


class ClientLogEntry(Base):
    """Frontend client-side log entry stored on the server."""

    __tablename__ = "client_log_entries"

    id = Column(String(64), primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    level = Column(Integer, nullable=False, index=True)  # 0=OFF, 1=ERROR, 2=WARN, 3=INFO, 4=DEBUG, 5=TRACE
    category = Column(String(32), nullable=False, index=True)  # api | user | system | business
    message = Column(Text, nullable=False)
    context = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
