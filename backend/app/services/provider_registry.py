from __future__ import annotations

import os
from typing import Dict, Type

from app.services.providers.base import BaseProvider
from app.services.providers.deepseek_provider import DeepSeekProvider
from app.services.providers.mock_provider import MockProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self.providers: Dict[str, Type[BaseProvider]] = {
            "mock": MockProvider,
            "deepseek": DeepSeekProvider,
        }

    def get_provider(self, provider_name: str | None = None) -> BaseProvider:
        selected_name = provider_name or os.getenv("LLM_PROVIDER", "mock")
        provider_cls = self.providers.get(selected_name, MockProvider)
        return provider_cls()
