from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Type

from app.core.config import settings
from app.services.providers.base import BaseProvider
from app.services.providers.deepseek_provider import DeepSeekProvider
from app.services.providers.mock_provider import MockProvider

# 与 admin API 使用完全相同的配置文件路径（backend/data/raw/system_config.json）
# admin API:  backend/app/api/admin/__init__.py → ../../.. → backend/data/raw/
# 本文件:    backend/app/services/knowledge/ → ../../.. → backend/data/raw/
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(_BASE_DIR, "..", "..", "..", "data", "raw", "system_config.json")


def _load_admin_config() -> Dict[str, Any]:
    """Load the full admin system_config.json."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _get_model_config(model_name: str) -> Optional[Dict[str, Any]]:
    """Look up a specific model's config from the admin models list."""
    cfg = _load_admin_config()
    models: List[Dict[str, Any]] = cfg.get("llm", {}).get("models", [])
    for m in models:
        if m.get("model") == model_name:
            return m
    return None


class ProviderRegistry:
    """Registry of available LLM providers with model-name routing.

    Resolution order (per get_provider call):
    1. Exact match in PROVIDER_MAP (canonical provider names)
    2. Look up in admin config models list → use the model's `provider` field
    3. Prefix match (e.g. "deepseek-*" → DeepSeekProvider)
    4. Fallback to MockProvider

    Adding a model in the admin panel is automatically picked up
    by step 2 — no code changes needed.
    """

    # Canonical provider names → provider classes
    PROVIDER_MAP: Dict[str, Type[BaseProvider]] = {
        "mock": MockProvider,
        "deepseek": DeepSeekProvider,
    }

    def __init__(self) -> None:
        self.providers = dict(self.PROVIDER_MAP)

    def get_provider(self, provider_or_model: Optional[str] = None) -> BaseProvider:
        """Return a provider instance for the given name/model.

        Reads per-model config (api_key, base_url, etc.) from the
        admin system_config.json when available.
        """
        selected = provider_or_model or settings.LLM_PROVIDER

        # 1. Exact canonical name match
        provider_cls = self.providers.get(selected)
        if provider_cls:
            return self._instantiate(provider_cls)

        # 2. Admin config models list lookup — fully dynamic
        model_cfg = _get_model_config(selected)
        if model_cfg:
            provider_name = model_cfg.get("provider", "")
            provider_cls = self.providers.get(provider_name)
            if provider_cls:
                return self._instantiate(provider_cls, model_cfg=model_cfg)
            # provider field points to an unknown provider → try prefix
            return self._resolve_by_prefix(selected, model_cfg)

        # 3. Prefix heuristic
        return self._resolve_by_prefix(selected)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_by_prefix(
        self, selected: str, model_cfg: Optional[Dict[str, Any]] = None,
    ) -> BaseProvider:
        """Fallback routing by model name prefix."""
        if selected.startswith("deepseek"):
            return self._instantiate(DeepSeekProvider, model_cfg=model_cfg, model=selected)
        # Unknown → safe fallback
        return self._instantiate(MockProvider, model=selected)

    def _instantiate(
        self,
        provider_cls: Type[BaseProvider],
        model_cfg: Optional[Dict[str, Any]] = None,
        **extra_kwargs: Any,
    ) -> BaseProvider:
        """Instantiate a provider, merging admin config overrides.

        Priority: model-specific config > top-level llm config > defaults.
        """
        cfg = _load_admin_config().get("llm", {})

        kwargs: Dict[str, Any] = {}
        kwargs.setdefault("timeout", 60.0)

        # API key: model-specific → top-level → env var
        api_key = ""
        if model_cfg and model_cfg.get("api_key"):
            api_key = model_cfg["api_key"]
        elif cfg.get("api_key"):
            api_key = cfg["api_key"]
        if api_key:
            kwargs["api_key"] = api_key

        # Base URL: model-specific → top-level → default
        base_url = ""
        if model_cfg and model_cfg.get("base_url"):
            base_url = model_cfg["base_url"]
        elif cfg.get("base_url"):
            base_url = cfg["base_url"]
        if base_url:
            kwargs["base_url"] = base_url

        # Model name: explicit extra_kwargs > model_cfg > top-level config
        if extra_kwargs.get("model"):
            kwargs["model"] = extra_kwargs["model"]
        elif model_cfg and model_cfg.get("model"):
            kwargs["model"] = model_cfg["model"]
        elif cfg.get("model"):
            kwargs["model"] = cfg["model"]

        return provider_cls(**kwargs) if kwargs else provider_cls()

    def register(self, name: str, provider_cls: Type[BaseProvider]) -> None:
        self.providers[name] = provider_cls

    @property
    def available_providers(self) -> list[str]:
        return list(self.providers.keys())
