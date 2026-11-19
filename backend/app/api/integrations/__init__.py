"""集成域 API（飞书等）。"""

from app.api.integrations.feishu import router as feishu_router

__all__ = ["feishu_router"]
