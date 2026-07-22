from __future__ import annotations

import logging
from typing import Any, Dict

from app.services.knowledge.provider_registry import ProviderRegistry

logger = logging.getLogger(__name__)


class LLMService:
    """Facade that routes LLM summaries through a configurable provider.

    Handles provider selection, graceful degradation on failure,
    and unified response normalization.
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = model

    def generate_summary(
        self,
        log_content: str,
        events: list[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate diagnostic summary via the configured LLM provider."""
        try:
            provider = ProviderRegistry().get_provider(self.model)
            result = provider.generate_summary(log_content, events)
            return result
        except Exception as exc:
            logger.warning("LLM provider failed, returning fallback: %s", exc)
            error_count = len([e for e in events if e.get("is_error")])
            return {
                "model": self.model or "unknown",
                "summary": f"AI 分析服务暂时不可用（{exc}）。请检查 LLM 配置后重试。",
                "confidence": 0.0,
                "root_cause": "远程分析服务异常，无法完成自动诊断。",
                "next_steps": [
                    "请检查管理后台的 LLM 配置（API Key 和 Base URL 是否正确）",
                    f"检测到 {error_count} 个错误事件，可尝试手动排查",
                    "确认网络连接正常，能访问 LLM 服务端点",
                ],
                "event_count": len(events),
                "error_count": error_count,
            }
