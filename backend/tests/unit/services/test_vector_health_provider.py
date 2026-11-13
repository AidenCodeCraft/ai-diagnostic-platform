"""GET /api/v1/vector/health 的 embedding_provider 返回值测试（不依赖外部服务）。

覆盖 §7-6 遗留项：旧实现返回包装类名 ``EmbeddingService``，
修复后应返回真实激活的 provider 名（HashingEmbedder / BGEEmbedder / APIEmbedder），
即使用 ``EmbeddingService.provider_name``。

直接调用路由函数 ``vector_health()``，monkeypatch ``get_vector_service`` /
``get_embedder``，不连接 Milvus、不加载模型。
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.api.knowledge import vector as vector_api


# ----------------------------------------------------------------------
# 测试替身
# ----------------------------------------------------------------------

class _FakeVectorService:
    """满足 vector_health() 读取需求的 VectorService 替身。"""

    def __init__(self) -> None:
        self.available = True
        self._connected = True
        self.collection_info: Dict[str, Any] = {
            "name": "knowledge_docs",
            "num_entities": 3,
        }


class _FakeEmbedder:
    """仅暴露 provider_name/dimension 的 EmbeddingService 替身。"""

    def __init__(self, provider_name: str, dimension: int = 512) -> None:
        self.provider_name = provider_name
        self.dimension = dimension


# ----------------------------------------------------------------------
# 测试
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "provider_name",
    ["HashingEmbedder", "BGEEmbedder", "APIEmbedder"],
)
def test_vector_health_returns_real_provider_name(monkeypatch, provider_name: str) -> None:
    """健康检查应返回真实 provider 名，而不是包装类名 EmbeddingService。"""
    monkeypatch.setattr(vector_api, "get_vector_service", lambda: _FakeVectorService())
    monkeypatch.setattr(
        vector_api, "get_embedder", lambda: _FakeEmbedder(provider_name)
    )

    body = vector_api.vector_health()

    assert body["milvus_available"] is True
    assert body["milvus_enabled"] is True
    assert body["collection"] == {"name": "knowledge_docs", "num_entities": 3}
    assert body["embedding_provider"] == provider_name
    assert body["embedding_provider"] != "EmbeddingService"


def test_vector_health_exception_path_returns_error(monkeypatch) -> None:
    """health 依赖异常时应返回 error 字段（保持原有异常分支行为）。"""

    def _broken_vector_service() -> None:
        raise RuntimeError("Milvus 不可用（模拟）")

    monkeypatch.setattr(vector_api, "get_vector_service", _broken_vector_service)

    body = vector_api.vector_health()

    assert body["milvus_available"] is False
    assert body["milvus_enabled"] is False
    assert "error" in body
    assert "Milvus 不可用" in body["error"]


def test_vector_health_embedder_exception_returns_error(monkeypatch) -> None:
    """embedder provider 读取异常时也应走 error 分支，而不是抛 500。"""
    monkeypatch.setattr(vector_api, "get_vector_service", lambda: _FakeVectorService())

    def _broken_embedder() -> None:
        raise ImportError("Embedding 依赖缺失（模拟）")

    monkeypatch.setattr(vector_api, "get_embedder", _broken_embedder)

    body = vector_api.vector_health()

    assert body["milvus_available"] is False
    assert "error" in body
