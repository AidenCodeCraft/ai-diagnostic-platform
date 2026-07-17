from __future__ import annotations

import os
from typing import Any, Dict

import httpx

from app.services.prompts.diagnostic_prompt import DiagnosticPrompt
from app.services.providers.base import BaseProvider


class DeepSeekProvider(BaseProvider):
    name = "deepseek"

    def __init__(self) -> None:
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = "https://api.deepseek.com/v1/chat/completions"

    def generate_summary(self, log_content: str, events: list[Dict[str, Any]]) -> Dict[str, Any]:
        error_count = len([event for event in events if event.get("is_error")])
        if not self.api_key:
            return {
                "model": self.name,
                "summary": "DeepSeek API key is not configured. Fallback to local analysis.",
                "confidence": 0.4,
                "root_cause": "Unable to determine without provider access.",
                "next_steps": ["Check the device log for timing or hardware-specific faults."],
                "event_count": len(events),
                "error_count": error_count,
            }

        prompt = DiagnosticPrompt.build(log_content, events)

        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
                summary = content.strip() or f"DeepSeek reported {error_count} error event(s)."
        except Exception:
            summary = "DeepSeek request failed. Falling back to local analysis."

        return {
            "model": self.name,
            "summary": summary,
            "confidence": 0.7,
            "root_cause": "DeepSeek analysis requires provider response parsing.",
            "next_steps": ["Inspect the device log and hardware state for the reported issue."],
            "event_count": len(events),
            "error_count": error_count,
        }
