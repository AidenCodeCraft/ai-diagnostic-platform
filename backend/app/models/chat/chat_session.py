from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.database.base import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    log_id = Column(Integer, ForeignKey("logs.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)  # 知识检索的项目范围
    model = Column(String(50), nullable=True)
    is_pinned = Column(Boolean, default=False, nullable=False)  # 侧栏置顶
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
    feedback = Column(String(10), nullable=True)  # null / 'like' / 'dislike'
    # 编辑重发的版本历史：[{ content, sources?, thinking? }, ...]（content 始终等于当前版本）
    versions = Column(JSON, nullable=True)
    active_version = Column(Integer, nullable=True)  # versions 中当前展示的下标
    # 提问附带的截图 id 列表（chat_images.id）：历史消息据此回显缩略图
    image_ids = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
