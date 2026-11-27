"""对话界面截图记录（Chat-Image-Recognition-Design §4）。

一次上传一行；识别文本是"一次性现场证据"，只用于当次诊断，
不进知识库、不进向量集合。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)

from app.database.base import Base

IMAGE_STATUSES = ("pending", "recognizing", "succeeded", "failed")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChatImageUpload(Base):
    __tablename__ = "chat_images"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    filename = Column(String(255), nullable=True)
    storage_ref = Column(String(512), nullable=True)
    mime = Column(String(64), nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    sha256 = Column(String(64), nullable=True, index=True)

    status = Column(String(16), nullable=False, default="pending", index=True)
    recognize_path = Column(String(16), nullable=True)
    extracted_text = Column(Text, nullable=True)
    usage = Column(JSON, nullable=True)
    error_message = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=_utcnow, index=True)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


__all__ = ["ChatImageUpload", "IMAGE_STATUSES"]
