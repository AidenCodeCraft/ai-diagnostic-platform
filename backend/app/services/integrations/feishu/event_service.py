"""飞书事件落库与幂等（S1）。

飞书会重投事件（网络抖动、5 秒未响应），没有 event_id 幂等就会重复下载、
重复识别、重复扣费。这里用 event_id 唯一索引挡住，而不是靠代码判断。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models import FeishuAttachment, FeishuEvent
from app.services.integrations.feishu.events import FeishuMessage, parse_event

logger = get_logger(__name__)


class FeishuEventService:
    def __init__(self, db: Session):
        self.db = db

    def handle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """处理一条已解密的飞书事件体。"""
        message = parse_event(payload)
        if message is None:
            return {"status": "ignored", "reason": "not_message_event"}

        existing = (
            self.db.query(FeishuEvent)
            .filter(FeishuEvent.event_id == message.event_id)
            .first()
        )
        if existing is not None:
            # 重复投递：不重复建记录、不重复投任务
            return {
                "status": "duplicate",
                "event_id": message.event_id,
                "event_status": existing.status,
            }

        event = FeishuEvent(
            event_id=message.event_id,
            event_type=message.event_type,
            message_id=message.message_id,
            chat_id=message.chat_id,
            sender_id=message.sender_id,
            message_type=message.message_type,
            status="received",
            payload=payload,
        )
        self.db.add(event)

        if not message.has_images:
            event.status = "ignored"
            self._commit_or_duplicate(event)
            return {"status": "ignored", "reason": "no_image", "event_id": message.event_id}

        attachments = self._ensure_attachments(message)
        event.status = "processed"
        committed = self._commit_or_duplicate(event)
        if not committed:
            return {"status": "duplicate", "event_id": message.event_id}

        logger.info(
            "[feishu] event %s accepted: message=%s images=%d",
            message.event_id, message.message_id, len(message.image_keys),
        )
        return {
            "status": "accepted",
            "event_id": message.event_id,
            "message_id": message.message_id,
            "attachment_ids": [item.id for item in attachments if item.id],
        }

    def _ensure_attachments(self, message: FeishuMessage) -> List[FeishuAttachment]:
        created: List[FeishuAttachment] = []
        for image_key in message.image_keys:
            existing = (
                self.db.query(FeishuAttachment)
                .filter(
                    FeishuAttachment.message_id == message.message_id,
                    FeishuAttachment.image_key == image_key,
                )
                .first()
            )
            if existing is not None:
                created.append(existing)
                continue
            attachment = FeishuAttachment(
                tenant_key=message.tenant_key or None,
                message_id=message.message_id,
                image_key=image_key,
                chat_id=message.chat_id or None,
                sender_id=message.sender_id or None,
                status="pending",
            )
            self.db.add(attachment)
            created.append(attachment)
        return created

    def _commit_or_duplicate(self, event: FeishuEvent) -> bool:
        """提交；并发重投撞唯一索引时按重复处理，而不是 500。"""
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            logger.info("[feishu] concurrent duplicate event %s ignored", event.event_id)
            return False
        return True

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_attachment(self, attachment_id: int) -> Optional[FeishuAttachment]:
        return (
            self.db.query(FeishuAttachment)
            .filter(FeishuAttachment.id == attachment_id)
            .first()
        )
