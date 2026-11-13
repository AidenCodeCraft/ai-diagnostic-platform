"""真实 LLM 端到端测试（默认跳过）。

启用方式（需先配置 DeepSeek API Key）：
    RUN_LIVE_LLM=1 pytest tests/e2e/test_live_llm.py -v

Key 来源：环境变量 DEEPSEEK_API_KEY，或后台「系统配置」写入的 models/api_key。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

RUN_LIVE = os.getenv("RUN_LIVE_LLM", "").strip().lower() in ("1", "true", "yes", "on")


def _has_api_key() -> bool:
    if os.getenv("DEEPSEEK_API_KEY"):
        return True
    config_path = Path(__file__).resolve().parents[2] / "data" / "raw" / "system_config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    llm = config.get("llm", {})
    if llm.get("api_key"):
        return True
    return any(
        isinstance(model, dict) and model.get("api_key")
        for model in llm.get("models", [])
    )


pytestmark = pytest.mark.skipif(
    not (RUN_LIVE and _has_api_key()),
    reason="真实 LLM E2E 默认跳过；设置 RUN_LIVE_LLM=1 且配置 DEEPSEEK_API_KEY（或后台模型配置）后启用",
)


def test_deepseek_chat_roundtrip():
    """真实调用 DeepSeek，验证 Provider → API → 返回文本链路。"""
    from app.services.knowledge.provider_registry import ProviderRegistry

    provider = ProviderRegistry().get_provider("deepseek")
    reply = provider.chat([
        {"role": "user", "content": "只输出两个字符：OK"},
    ])
    assert isinstance(reply, str)
    assert reply.strip()
