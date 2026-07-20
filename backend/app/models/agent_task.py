from sqlalchemy import Column, Integer, String, Text, ForeignKey

from app.database.base import Base


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id = Column(Integer, primary_key=True)
    task_id = Column(String(100), nullable=False, unique=True)
    log_id = Column(Integer, ForeignKey("logs.id"), nullable=False)
    status = Column(String(50), nullable=False)
    state = Column(String(50), nullable=False)
    steps = Column(Text, nullable=True)
    tool_plan = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
