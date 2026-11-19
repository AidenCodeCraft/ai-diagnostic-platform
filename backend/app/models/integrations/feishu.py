"""飞书集成数据模型（S1）。

只落"事件"和"图片记录"两张表：
  - feishu_events：事件幂等（飞书会重投，重复处理会重复扣识别费用）
  - feishu_attachments：一张图片一行，识别状态与结果都挂在这里
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,

    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from app.database.base import Base

EVENT_STATUSES = ("received", "processed", "ignored", "failed")
ATTACHMENT_STATUSES = ("pending", "downloading", "recognizing", "succeeded", "failed")
RECOGNIZE_PATHS = ("ocr", "vision", "ocr+vision")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FeishuEvent(Base):
    """飞书事件（幂等键 = event_id）。"""

    __tablename__ = "feishu_events"

    id = Column(Integer, primary_key=True)
    event_id = Column(String(64), nullable=False, unique=True, index=True)
    event_type = Column(String(64), nullable=True)
    message_id = Column(String(64), nullable=True, index=True)
    chat_id = Column(String(64), nullable=True)
    sender_id = Column(String(64), nullable=True)
    message_type = Column(String(32), nullable=True)
    status = Column(String(16), nullable=False, default="received")
    error_message = Column(String(500), nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_utcnow, index=True)


class FeishuAttachment(Base):
    """飞书消息中的一张图片（识别状态机）。"""

    __tablename__ = "feishu_attachments"
    __table_args__ = (
        UniqueConstraint("message_id", "image_key", name="uq_feishu_attachment_message_image"),
    )

    id = Column(Integer, primary_key=True)
    tenant_key = Column(String(64), nullable=True, index=True)
    message_id = Column(String(64), nullable=False)
    image_key = Column(String(128), nullable=False)
    chat_id = Column(String(64), nullable=True)
    sender_id = Column(String(64), nullable=True)

    storage_ref = Column(String(512), nullable=True)   # minio://bucket/key（S2 写入）
    mime = Column(String(64), nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    sha256 = Column(String(64), nullable=True, index=True)

    status = Column(String(16), nullable=False, default="pending", index=True)
    recognize_path = Column(String(16), nullable=True)  # ocr | vision | ocr+vision
    extracted_text = Column(Text, nullable=True)
    usage = Column(JSON, nullable=True)
    error_message = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=_utcnow, index=True)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


__all__ = ["FeishuEvent", "FeishuAttachment", "EVENT_STATUSES", "ATTACHMENT_STATUSES", "RECOGNIZE_PATHS"]
