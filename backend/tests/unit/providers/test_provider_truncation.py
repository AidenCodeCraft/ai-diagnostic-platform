"""LLM 输出上限解析：避免写死 4096 导致回答被截断。"""

from app.services.providers.deepseek_provider import DeepSeekProvider


def test_resolve_max_tokens_from_admin_config():
    cfg = {"models": [{"model": "deepseek-v4-flash", "max_tokens": 16000}]}
    assert DeepSeekProvider._resolve_max_tokens("deepseek-v4-flash", cfg) == 16000


def test_resolve_max_tokens_falls_back_to_default():
    assert DeepSeekProvider._resolve_max_tokens("unknown-model", {"models": []}) == 8192


def test_resolve_max_tokens_ignores_invalid_values():
    cfg = {"models": [{"model": "m", "max_tokens": "abc"}]}
    assert DeepSeekProvider._resolve_max_tokens("m", cfg) == 8192
