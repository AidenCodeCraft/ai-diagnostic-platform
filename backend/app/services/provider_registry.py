from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Type

from app.core.config import settings
from app.services.providers.base import BaseProvider
from app.services.providers.deepseek_provider import DeepSeekProvider
from app.services.providers.mock_provider import MockProvider

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw", "system_config.json")


def _load_admin_llm_config() -> Dict[str, Any]:
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f).get("llm", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


class ProviderRegistry:
    """Registry of available LLM providers."""

    def __init__(self) -> None:
        self.providers: Dict[str, Type[BaseProvider]] = {
            "mock": MockProvider,
            "deepseek": DeepSeekProvider,
        }

    def get_provider(self, provider_name: Optional[str] = None) -> BaseProvider:
        """Return a provider instance, reading config from admin settings file."""
        selected = provider_name or settings.LLM_PROVIDER
        provider_cls = self.providers.get(selected, MockProvider)

        # Check admin-saved config for overrides
        cfg = _load_admin_llm_config()
        kwargs: Dict[str, Any] = {}
        if cfg.get("api_key"):
            kwargs["api_key"] = cfg["api_key"]
        if cfg.get("base_url"):
            url = cfg["base_url"]
            # Auto-append /v1/chat/completions if missing
            if "/chat/completions" not in url:
                url = url.rstrip("/") + "/v1/chat/completions"
            kwargs["base_url"] = url
        if cfg.get("model"):
            kwargs["model"] = cfg["model"]

        return provider_cls(**kwargs) if kwargs else provider_cls()

    def register(self, name: str, provider_cls: Type[BaseProvider]) -> None:
        self.providers[name] = provider_cls

    @property
    def available_providers(self) -> list[str]:
        return list(self.providers.keys())
