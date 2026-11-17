from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Generator, List


class BaseProvider(ABC):
    """Abstract base for LLM provider implementations."""

    name: str = "base"
    default_model: str = "default"

    @abstractmethod
    def generate_summary(
        self,
        log_content: str,
        events: list[Dict[str, Any]],
        *,
        prompt_built: bool = False,
    ) -> Dict[str, Any]:
        """Generate a diagnostic summary from parsed log events.

        prompt_built=True 时，log_content 已是调用方构建好的完整诊断
        Prompt（含用户问题/知识库证据/输出要求），不得再二次包装或截断。
        """

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
    ) -> str:
        """Send a multi-turn conversation and return the full reply."""

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
    ) -> Generator[str, None, None]:
        """Generator yielding reply text chunks for SSE streaming.

        Default: yields the full reply as a single chunk.
        Override in providers that support native streaming.
        """
        yield self.chat(messages)

    def health_check(self) -> bool:
        """Return True if the provider is reachable and configured."""
        return True
