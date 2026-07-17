from __future__ import annotations

from typing import Any, Dict

from app.services.provider_registry import ProviderRegistry


class LLMService:
    """Facade that routes LLM summaries through a configurable provider."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model

    def generate_summary(self, log_content: str, events: list[Dict[str, Any]]) -> Dict[str, Any]:
        provider = ProviderRegistry().get_provider(self.model)
        return provider.generate_summary(log_content, events)
