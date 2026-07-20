from app.services.provider_registry import ProviderRegistry


def test_provider_registry_uses_mock_by_default():
    registry = ProviderRegistry()
    provider = registry.get_provider()
    assert provider.name == "mock"


def test_provider_registry_supports_deepseek_override():
    registry = ProviderRegistry()
    provider = registry.get_provider("deepseek")
    assert provider.name == "deepseek"


def test_provider_registry_available_providers():
    registry = ProviderRegistry()
    available = registry.available_providers
    assert "mock" in available
    assert "deepseek" in available
