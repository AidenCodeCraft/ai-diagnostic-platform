from __future__ import annotations

from typing import Dict, Optional, Type

from app.core.config import settings
from app.services.providers.base import BaseProvider
from app.services.providers.deepseek_provider import DeepSeekProvider
from app.services.providers.mock_provider import MockProvider
from app.services.providers.openai_compatible_provider import OpenAICompatibleProvider


class ProviderRegistry:
    """Registry of available LLM providers with dynamic registration.

    Supports built-in (Mock, DeepSeek) and OpenAI-compatible (Qwen, Llama, GPT)
    providers registered at runtime via register().
    """

    def __init__(self) -> None:
        self.providers: Dict[str, Type[BaseProvider]] = {
            "mock": MockProvider,
            "deepseek": DeepSeekProvider,
        }

    def get_provider(self, provider_name: Optional[str] = None) -> BaseProvider:
        """Return a provider instance by name, or the configured default."""
        selected = provider_name or settings.LLM_PROVIDER
        provider_cls = self.providers.get(selected, MockProvider)
        return provider_cls()

    def register(self, name: str, provider_cls: Type[BaseProvider]) -> None:
        """Register a new provider type."""
        self.providers[name] = provider_cls

    def register_openai_compatible(self, name: str) -> None:
        """Register an OpenAI-compatible provider by name (e.g. 'qwen', 'llama')."""

        def factory(**kwargs):
            return OpenAICompatibleProvider(name=name, **kwargs)

        factory.__name__ = f"{name.capitalize()}Provider"
        self.providers[name] = factory

    @property
    def available_providers(self) -> list[str]:
        return list(self.providers.keys())
