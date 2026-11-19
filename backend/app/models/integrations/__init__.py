"""集成域模型（飞书等）。"""

from app.models.integrations.feishu import FeishuAttachment, FeishuEvent

__all__ = ["FeishuEvent", "FeishuAttachment"]
