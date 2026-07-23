from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text

from app.database.base import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    log_id = Column(Integer, ForeignKey("logs.id"), nullable=True)
    model = Column(String(50), nullable=True)
    context = Column(JSON, nullable=True)  # { last_analysis: {...}, analysis_mode: 'chat'|'diagnose' }
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String(20), nullable=False)  # user / assistant / system
    content = Column(Text, nullable=False)
    sources = Column(JSON, nullable=True)
    thinking = Column(JSON, nullable=True)  # { text: str, elapsed: int }
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
