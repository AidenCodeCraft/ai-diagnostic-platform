from app.services.providers.deepseek_provider import DeepSeekProvider


def test_structured_output_is_supported_for_empty_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    provider = DeepSeekProvider()
    result = provider.generate_summary("usb timeout", [{"is_error": True, "module": "usb"}])

    assert result["model"] == "deepseek"
    assert result["summary"]
    assert result["confidence"] >= 0.0
    assert result["root_cause"]
    assert result["next_steps"]
