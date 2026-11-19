"""飞书事件解析（S1，纯函数，不碰网络与数据库）。

只关心「谁在哪个会话发了什么类型的消息、里面有哪几张图」：
  - image 消息：content = {"image_key": "img_v3_xxx"}
  - post（富文本）消息：图片嵌在 content 的嵌套结构里，用正则扫描 image_key
  - 其他类型：忽略（S1 只处理图片）
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

IMAGE_KEY_PATTERN = re.compile(r"img_[A-Za-z0-9_\-]+")

MESSAGE_EVENT_TYPES = ("im.message.receive_v1",)
IMAGE_MESSAGE_TYPES = ("image", "post")


@dataclass
class FeishuMessage:
    event_id: str
    event_type: str
    tenant_key: str = ""
    message_id: str = ""
    chat_id: str = ""
    sender_id: str = ""
    message_type: str = ""
    image_keys: List[str] = field(default_factory=list)

    @property
    def has_images(self) -> bool:
        return bool(self.image_keys)


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(content)


def extract_image_keys(content: Any) -> List[str]:
    """从消息 content 中抽取 image_key（image / post 都适用），保持出现顺序并去重。"""
    text = _content_to_text(content)
    seen: List[str] = []
    for match in IMAGE_KEY_PATTERN.findall(text):
        if match not in seen:
            seen.append(match)
    return seen


def parse_event(payload: Dict[str, Any]) -> Optional[FeishuMessage]:
    """解析 v2.0 事件体；不是消息事件时返回 None。"""
    if not isinstance(payload, dict):
        return None

    header = payload.get("header") or {}
    event = payload.get("event") or {}
    event_type = str(header.get("event_type") or payload.get("type") or "")
    event_id = str(header.get("event_id") or payload.get("uuid") or "")

    if event_type not in MESSAGE_EVENT_TYPES:
        return None

    message = event.get("message") or {}
    sender = event.get("sender") or {}
    sender_id = str(
        sender.get("sender_id", {}).get("open_id")
        or sender.get("sender_id", {}).get("user_id")
        or ""
    )

    message_type = str(message.get("message_type") or "")
    content = message.get("content") or ""

    image_keys: List[str] = []
    if message_type in IMAGE_MESSAGE_TYPES:
        image_keys = extract_image_keys(content)

    return FeishuMessage(
        event_id=event_id,
        event_type=event_type,
        tenant_key=str(header.get("tenant_key") or event.get("tenant_key") or ""),
        message_id=str(message.get("message_id") or ""),
        chat_id=str(message.get("chat_id") or ""),
        sender_id=sender_id,
        message_type=message_type,
        image_keys=image_keys,
    )
