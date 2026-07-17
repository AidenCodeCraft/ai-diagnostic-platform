from app.services.provider_registry import ProviderRegistry


def test_provider_registry_uses_mock_by_default():
    registry = ProviderRegistry()
    provider = registry.get_provider()
    assert provider.name == "mock"


def test_provider_registry_supports_deepseek_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    registry = ProviderRegistry()
    provider = registry.get_provider()
    assert provider.name == "deepseek"
