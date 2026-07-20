from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

import httpx

from app.services.prompts.diagnostic_prompt import DiagnosticPrompt
from app.services.providers.base import BaseProvider


class DeepSeekProvider(BaseProvider):
    """LLM provider for DeepSeek Chat API (https://api.deepseek.com).

    Requires DEEPSEEK_API_KEY environment variable.
    Falls back to local analysis if the key is missing or the request fails.
    """

    name = "deepseek"
    default_model = "deepseek-chat"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = base_url or os.getenv(
            "DEEPSEEK_BASE_URL",
            "https://api.deepseek.com/v1/chat/completions",
        )
        self.model = model or os.getenv("DEEPSEEK_MODEL", self.default_model)
        self.timeout = timeout
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_summary(
        self,
        log_content: str,
        events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate a diagnostic summary via DeepSeek API.

        Falls back gracefully if API key is missing or request fails.
        """
        error_count = len([e for e in events if e.get("is_error")])

        if not self.api_key:
            return self._fallback_response(
                events, error_count,
                "DeepSeek API key not configured — using local analysis.",
                0.4,
            )

        prompt = DiagnosticPrompt.build(log_content, events)

        for attempt in range(1, self.max_retries + 1):
            try:
                raw_content = self._call_api(prompt)
                parsed = self._parse_response(raw_content)
                if parsed:
                    return self._build_response(parsed, events, error_count)
            except httpx.TimeoutException:
                if attempt == self.max_retries:
                    return self._fallback_response(
                        events, error_count,
                        f"DeepSeek API timeout after {self.max_retries} retries.",
                        0.35,
                    )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500 and attempt < self.max_retries:
                    continue
                return self._fallback_response(
                    events, error_count,
                    f"DeepSeek API error: HTTP {exc.response.status_code}",
                    0.3,
                )
            except Exception:
                if attempt == self.max_retries:
                    return self._fallback_response(
                        events, error_count,
                        "DeepSeek API unreachable — using local analysis.",
                        0.35,
                    )

        return self._fallback_response(events, error_count, "Unexpected fallback.", 0.3)

    def health_check(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _call_api(self, prompt: str) -> str:
        """Send request to DeepSeek and return the raw response content."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a diagnostic assistant. Output ONLY valid JSON.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 2048,
                },
            )
            response.raise_for_status()
            payload = response.json()
            content = (
                payload.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            return content.strip()

    def _parse_response(self, raw: str) -> Dict[str, Any] | None:
        """Extract JSON from the LLM response (may contain markdown fences)."""
        if not raw:
            return None

        # Try direct JSON parse
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Try extracting from ```json ... ``` blocks
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # Try extracting any { ... } block
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _build_response(
        self,
        parsed: Dict[str, Any],
        events: List[Dict[str, Any]],
        error_count: int,
    ) -> Dict[str, Any]:
        """Construct a normalized response from parsed LLM output."""
        confidence = self._safe_float(parsed.get("confidence"), 0.7)
        next_steps = self._safe_list(parsed.get("next_steps", []))

        return {
            "model": self.name,
            "summary": str(parsed.get("summary", f"DeepSeek analyzed {error_count} error event(s).")),
            "confidence": max(0.0, min(1.0, confidence)),
            "root_cause": str(parsed.get("root_cause", "Root cause not determined.")),
            "next_steps": next_steps,
            "event_count": len(events),
            "error_count": error_count,
        }

    @staticmethod
    def _fallback_response(
        events: List[Dict[str, Any]],
        error_count: int,
        message: str,
        confidence: float,
    ) -> Dict[str, Any]:
        """Return a safe fallback when the provider is unavailable."""
        return {
            "model": "deepseek",
            "summary": message,
            "confidence": confidence,
            "root_cause": "Unable to perform remote analysis.",
            "next_steps": [
                "Review error events manually for patterns.",
                "Check device hardware state and driver logs.",
                "Verify API key configuration for cloud-based analysis.",
            ],
            "event_count": len(events),
            "error_count": error_count,
        }

    @staticmethod
    def _safe_float(value: Any, default: float = 0.5) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_list(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            return [value]
        return []
