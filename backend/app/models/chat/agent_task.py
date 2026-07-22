from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.database.base import Base


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id = Column(Integer, primary_key=True)
    task_id = Column(String(100), nullable=False, unique=True)
    log_id = Column(Integer, ForeignKey("logs.id"), nullable=False)
    status = Column(String(50), nullable=False, default="CREATED")
    state = Column(String(50), nullable=False, default="CREATED")
    steps = Column(Text, nullable=True)
    tool_plan = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
