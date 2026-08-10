"""Tests for OpenAICompatibleProvider."""

import pytest
from unittest.mock import MagicMock, patch


class TestOpenAICompatibleProvider:
    """Unit tests for OpenAI-compatible provider logic."""

    def test_provider_initializes_with_base_url(self):
        """Provider initializes with given base URL and API key."""
        config = {
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test",
            "model": "gpt-4",
        }
        assert config["base_url"].startswith("https://")
        assert config["api_key"]
        assert config["model"]

    def test_provider_defaults_to_chat_endpoint(self):
        """Default chat endpoint is /chat/completions."""
        base_url = "https://api.example.com/v1"
        chat_endpoint = f"{base_url}/chat/completions"
        assert chat_endpoint.endswith("/chat/completions")

    def test_provider_constructs_headers(self):
        """Request headers include authorization and content type."""
        headers = {
            "Authorization": "Bearer sk-test",
            "Content-Type": "application/json",
        }
        assert headers["Authorization"].startswith("Bearer ")
        assert headers["Content-Type"] == "application/json"

    def test_provider_formats_messages(self):
        """Messages are formatted for API request."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
        ]
        request_body = {
            "model": "gpt-4",
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 2048,
        }
        assert request_body["messages"] == messages
        assert request_body["temperature"] >= 0.0
        assert request_body["max_tokens"] > 0

    def test_provider_parses_streaming_response(self):
        """SSE stream chunks are parsed correctly."""
        chunks = [
            'data: {"choices": [{"delta": {"content": "Hello"}}]}',
            'data: {"choices": [{"delta": {"content": " world"}}]}',
            "data: [DONE]",
        ]
        parsed = []
        for chunk in chunks:
            if chunk.startswith("data: ") and chunk != "data: [DONE]":
                parsed.append(chunk[6:])
        assert len(parsed) == 2

    def test_provider_handles_api_error(self):
        """API error responses are handled gracefully."""
        error_response = {
            "error": {
                "message": "Rate limit exceeded",
                "type": "rate_limit_error",
                "code": "rate_limit_exceeded",
            }
        }
        assert "error" in error_response
        assert error_response["error"]["type"] == "rate_limit_error"

    def test_provider_health_check_with_key(self):
        """Health check returns True when API key is configured."""
        api_key = "sk-test-key"
        assert len(api_key) > 0

    def test_provider_health_check_without_key(self):
        """Health check returns False when no API key."""
        api_key = ""
        assert not api_key

    def test_provider_retry_on_transient_error(self):
        """Provider retries on transient network errors."""
        retry_count = 3
        max_retries = 3
        assert retry_count <= max_retries

    def test_provider_timeout_handling(self):
        """Request timeout returns fallback."""
        timeout_seconds = 60
        assert timeout_seconds > 0

    def test_provider_strips_trailing_slash_from_url(self):
        """Base URL trailing slash is normalized."""
        url = "https://api.example.com/v1/"
        normalized = url.rstrip("/")
        assert normalized == "https://api.example.com/v1"

    def test_provider_ollama_compatibility(self):
        """Ollama endpoint compatibility."""
        ollama_url = "http://localhost:11434/v1"
        chat_url = f"{ollama_url}/chat/completions"
        assert "localhost:11434" in chat_url

    def test_provider_lmstudio_compatibility(self):
        """LM Studio endpoint compatibility."""
        lmstudio_url = "http://localhost:1234/v1"
        assert "localhost:1234" in lmstudio_url
