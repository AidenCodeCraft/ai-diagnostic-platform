from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseProvider(ABC):
    """Abstract base for LLM provider implementations.

    Each provider (DeepSeek, Qwen, Llama, Mock) must implement generate_summary.
    """

    name: str = "base"
    default_model: str = "default"

    @abstractmethod
    def generate_summary(
        self,
        log_content: str,
        events: list[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate a diagnostic summary from parsed log events.

        Returns a dict with keys: summary, confidence, root_cause, next_steps, model.
        """

    def health_check(self) -> bool:
        """Return True if the provider is reachable and configured."""
        return True
