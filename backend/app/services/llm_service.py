from __future__ import annotations

import logging
from typing import Any, Dict

from app.services.provider_registry import ProviderRegistry

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
                "summary": "Analysis service temporarily unavailable. Review logs manually.",
                "confidence": 0.0,
                "root_cause": "Provider error prevented remote analysis.",
                "next_steps": [
                    "Manually inspect error events in the parsed log.",
                    "Verify LLM provider configuration and connectivity.",
                ],
                "event_count": len(events),
                "error_count": error_count,
            }
