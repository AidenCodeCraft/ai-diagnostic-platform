import os

from app.services.providers.deepseek_provider import DeepSeekProvider


def test_deepseek_provider_uses_env_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    provider = DeepSeekProvider()
    assert provider.api_key == "test-key"


def test_deepseek_provider_returns_fallback_without_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    provider = DeepSeekProvider()
    result = provider.generate_summary("usb timeout", [{"is_error": True, "module": "usb"}])
    assert result["model"] == "deepseek"
    assert "not configured" in result["summary"].lower()
