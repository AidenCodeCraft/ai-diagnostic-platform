from __future__ import annotations

from typing import Dict, Type

from app.core.config import settings
from app.services.providers.base import BaseProvider
from app.services.providers.deepseek_provider import DeepSeekProvider
from app.services.providers.mock_provider import MockProvider


class ProviderRegistry:
    """Registry of available LLM providers with automatic selection."""

    def __init__(self) -> None:
        self.providers: Dict[str, Type[BaseProvider]] = {
            "mock": MockProvider,
            "deepseek": DeepSeekProvider,
        }

    def get_provider(self, provider_name: str | None = None) -> BaseProvider:
        """Return a provider instance by name, or the configured default."""
        selected = provider_name or settings.LLM_PROVIDER
        provider_cls = self.providers.get(selected, MockProvider)
        return provider_cls()

    def register(self, name: str, provider_cls: Type[BaseProvider]) -> None:
        """Register a new provider type."""
        self.providers[name] = provider_cls

    @property
    def available_providers(self) -> list[str]:
        return list(self.providers.keys())
