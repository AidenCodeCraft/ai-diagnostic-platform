"""Generic OpenAI-compatible provider — supports any OpenAI API-compatible endpoint.

Works with: Qwen, Llama, GPT, local vLLM/Ollama, and any other API
that exposes a /v1/chat/completions endpoint.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

import httpx

from app.services.prompts.diagnostic_prompt import DiagnosticPrompt
from app.services.providers.base import BaseProvider


class OpenAICompatibleProvider(BaseProvider):
    """Generic provider for any OpenAI-compatible chat API.

    Config via environment variables or constructor arguments:
        PROVIDER_NAME_API_KEY — API key
        PROVIDER_NAME_BASE_URL — API endpoint
        PROVIDER_NAME_MODEL — model name

    Example for Qwen:
        QWEN_API_KEY=sk-xxx
        QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
        QWEN_MODEL=qwen-plus
    """

    name = "openai-compatible"
    default_model = "default"

    def __init__(
        self,
        name: str = "openai",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self._provider_name = name
        self.name = name
        self.default_model = model or "default"
        self.api_key = api_key or os.getenv(f"{name.upper()}_API_KEY", "")
        self.base_url = base_url or os.getenv(f"{name.upper()}_BASE_URL", "https://api.openai.com/v1/chat/completions")
        self.model = model or os.getenv(f"{name.upper()}_MODEL", "default")
        self.timeout = timeout
        self.max_retries = max_retries

    def generate_summary(
        self, log_content: str, events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        error_count = len([e for e in events if e.get("is_error")])
        if not self.api_key:
            return self._fallback(events, error_count, f"{self._provider_name} API key not configured.", 0.4)

        prompt = DiagnosticPrompt.build(log_content, events)
        for attempt in range(1, self.max_retries + 1):
            try:
                raw = self._call_api(prompt)
                parsed = self._parse_json(raw)
                if parsed:
                    return self._build_response(parsed, events, error_count)
            except httpx.TimeoutException:
                if attempt == self.max_retries:
                    return self._fallback(events, error_count, f"{self._provider_name} timeout", 0.35)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500 and attempt < self.max_retries:
                    continue
                return self._fallback(events, error_count, f"HTTP {exc.response.status_code}", 0.3)
            except Exception:
                if attempt == self.max_retries:
                    return self._fallback(events, error_count, f"{self._provider_name} unreachable", 0.35)
        return self._fallback(events, error_count, "Unexpected", 0.3)

    def health_check(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------
    # Internals (same as DeepSeekProvider pattern)
    # ------------------------------------------------------------------

    def _call_api(self, prompt: str) -> str:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 2048},
            )
            resp.raise_for_status()
            return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()

    @staticmethod
    def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        for pattern in [r"```(?:json)?\s*(\{.*?\})\s*```", r"\{.*\}"]:
            m = re.search(pattern, raw, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1) if "```" in pattern else m.group(0))
                except json.JSONDecodeError:
                    pass
        return None

    def _build_response(self, parsed: Dict, events: List, error_count: int) -> Dict[str, Any]:
        confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.7) or 0.7)))
        next_steps = parsed.get("next_steps", [])
        if isinstance(next_steps, str):
            next_steps = [next_steps]
        return {
            "model": self._provider_name,
            "summary": str(parsed.get("summary", f"Analysis of {error_count} errors.")),
            "confidence": confidence,
            "root_cause": str(parsed.get("root_cause", "Unknown.")),
            "next_steps": [str(s) for s in next_steps],
            "event_count": len(events),
            "error_count": error_count,
        }

    @staticmethod
    def _fallback(events: List, error_count: int, msg: str, confidence: float) -> Dict[str, Any]:
        return {
            "model": "fallback",
            "summary": msg,
            "confidence": confidence,
            "root_cause": "Remote analysis unavailable.",
            "next_steps": ["Review error events manually.", "Check device hardware and drivers."],
            "event_count": len(events),
            "error_count": error_count,
        }
