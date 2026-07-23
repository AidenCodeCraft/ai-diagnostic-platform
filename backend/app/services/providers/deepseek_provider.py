from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Generator, List

import httpx

from app.services.prompts.diagnostic_prompt import DiagnosticPrompt
from app.services.providers.base import BaseProvider


def _load_admin_llm_config() -> Dict[str, str]:
    """Read LLM config from the admin panel's system_config.json.

    Returns empty dict if file doesn't exist or is malformed.
    """
    config_path = Path("data") / "raw" / "system_config.json"
    try:
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
            return data.get("llm", {})
    except (json.JSONDecodeError, OSError):
        pass
    return {}


class DeepSeekProvider(BaseProvider):
    """LLM provider for DeepSeek Chat API (https://api.deepseek.com).

    API key lookup order:
    1. Explicit constructor arg
    2. DEEPSEEK_API_KEY environment variable
    3. Admin panel system_config.json (saved via 管理后台 → 系统配置)
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
        # Merge: explicit arg → env var → admin panel saved config
        file_cfg = _load_admin_llm_config()
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "") or file_cfg.get("api_key", "")
        self.base_url = base_url or os.getenv(
            "DEEPSEEK_BASE_URL",
            file_cfg.get("base_url") or "https://api.deepseek.com/v1/chat/completions",
        )
        self.model = model or os.getenv("DEEPSEEK_MODEL", file_cfg.get("model") or self.default_model)
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
                "DeepSeek API Key 未配置，请在管理后台填写后重试。",
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
                        f"DeepSeek API 超时（已重试 {self.max_retries} 次），请检查网络连接。",
                        0.35,
                    )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500 and attempt < self.max_retries:
                    continue
                return self._fallback_response(
                    events, error_count,
                    f"DeepSeek API 错误（HTTP {exc.response.status_code}）",
                    0.3,
                )
            except Exception:
                if attempt == self.max_retries:
                    return self._fallback_response(
                        events, error_count,
                        "DeepSeek API 无法连接，请检查 Base URL 和网络。",
                        0.35,
                    )

        return self._fallback_response(events, error_count, "未知错误，分析异常终止。", 0.3)

    def chat(self, messages: List[Dict[str, str]]) -> str:
        """Multi-turn chat via DeepSeek API."""
        if not self.api_key:
            return "[DeepSeek API key not configured]"
        try:
            return self._call_api_messages(messages)
        except Exception:
            return "[DeepSeek API unavailable]"

    def chat_stream(self, messages: List[Dict[str, str]]) -> Generator[str | Dict[str, str], None, None]:
        """Stream chat via DeepSeek SSE."""
        if not self.api_key:
            yield (
                "## ⚠️ DeepSeek API Key 未配置\n\n"
                "请在管理后台 → 系统配置 → LLM 配置中填写 DeepSeek API Key。"
            )
            return
        try:
            yield from self._call_api_stream(messages)
        except Exception as exc:
            yield (
                f"## DeepSeek API 连接失败\n\n"
                f"**错误：** {exc}\n\n"
                f"可能原因：\n"
                f"1. Docker 容器无法访问外网（检查 DNS/代理设置）\n"
                f"2. API Key 无效或已过期\n"
                f"3. Base URL 配置错误（当前：{self._api_url}）"
            )

    def health_check(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @property
    def _api_url(self) -> str:
        """Construct the full chat/completions endpoint URL."""
        url = self.base_url.rstrip("/")
        if not url.endswith("/v1/chat/completions"):
            url += "/v1/chat/completions"
        return url

    def _call_api_stream(self, messages: List[Dict[str, str]]) -> Generator[str, None, None]:
        """Stream tokens from DeepSeek API."""
        with httpx.Client(timeout=60.0) as client:
            with client.stream(
                "POST",
                self._api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 4096,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            return
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            # Reasoning-capable DeepSeek models return their
                            # thinking separately from the answer.  Preserve
                            # that boundary so callers never display the
                            # answer itself as a fabricated "thought process".
                            reasoning = delta.get("reasoning_content", "")
                            if reasoning:
                                yield {"reasoning": reasoning}
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            pass

    def _call_api_messages(self, messages: List[Dict[str, str]]) -> str:
        """Send arbitrary messages to DeepSeek and return the raw response content."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                self._api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 4096,
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

    def _call_api(self, prompt: str) -> str:
        """Send request to DeepSeek and return the raw response content."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                self._api_url,
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
                    "max_tokens": 4096,
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
            "root_cause": "远程分析服务不可用，无法完成自动诊断。",
            "next_steps": [
                "手动检查日志中的错误事件规律",
                "检查设备硬件状态和驱动日志",
                f"当前日志共检测到 {error_count} 个错误事件",
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
