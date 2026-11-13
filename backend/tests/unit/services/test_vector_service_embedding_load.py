"""VectorService._ensure_embedding() 后台加载状态管理测试（不依赖 Milvus / 模型下载）。

覆盖 §7-7 遗留项（P2）修复：
- 超时只影响「本次调用」；后台线程完成后，下一次调用应返回 True 并回填 `_embedding`（不再永久 latch）；
- 加载线程只启动一次并复用（并发调用共享同一线程）；
- 加载失败后允许后续重试（尝试计数递增）；
- 等待超时来自 `settings.EMBEDDING_LOAD_TIMEOUT`（可 monkeypatch 加速），不再硬编码。

构造对象用 `object.__new__(VectorService)` 并手动初始化加载状态，避免 `__init__`
连接真实 Milvus 或加载真实 BGE 模型。
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

import pytest

from app.core.config import settings
from app.services.knowledge import vector_service as vector_service_module
from app.services.knowledge.vector_service import VectorService


# ----------------------------------------------------------------------
# 辅助
# ----------------------------------------------------------------------

class _FakeEmbedder:
    """最小 embedder 替身。"""

    dimension = 512

    def embed(self, text: str):  # noqa: ANN001 - 测试替身
        return [0.0] * self.dimension


def _make_service() -> VectorService:
    """只初始化 embedding 加载状态，不走 Milvus/模型加载。"""
    svc = object.__new__(VectorService)
    svc._embedding = None
    svc._embedding_lock = threading.Lock()
    svc._embedding_load_thread = None
    svc._embedding_load_attempts = 0
    svc._embedding_last_error = None
    return svc


def _fake_loader(delay: float, result: Any) -> Callable[[], Any]:
    """返回一个『先睡 delay 秒再返回 result』的 get_embedder 替身。"""

    def _load():
        time.sleep(delay)
        return result

    return _load


def _join_background(svc: VectorService, timeout: float = 5.0) -> threading.Thread:
    thread = svc._embedding_load_thread
    assert thread is not None, "应已启动后台加载线程"
    thread.join(timeout)
    assert not thread.is_alive(), "后台加载线程未在期望时间内结束"
    return thread


# ----------------------------------------------------------------------
# 测试
# ----------------------------------------------------------------------

def test_hardcoded_timeout_constant_removed(monkeypatch):
    """硬编码 _EMBEDDING_LOAD_TIMEOUT 已移除，改读 settings.EMBEDDING_LOAD_TIMEOUT。"""
    assert not hasattr(VectorService, "_EMBEDDING_LOAD_TIMEOUT")

    monkeypatch.setattr(settings, "EMBEDDING_LOAD_TIMEOUT", 12.5)
    svc = _make_service()
    assert svc._embedding_load_timeout() == pytest.approx(12.5)

    # 非法值走保守默认 30s
    monkeypatch.setattr(settings, "EMBEDDING_LOAD_TIMEOUT", "invalid")
    assert svc._embedding_load_timeout() == pytest.approx(30.0)


def test_timeout_returns_false_then_next_call_backfills(monkeypatch):
    """（a）首次超时返回 False；后台线程完成后，下一次调用返回 True 且 _embedding 回填。"""
    fake = _FakeEmbedder()
    monkeypatch.setattr(vector_service_module, "get_embedder", _fake_loader(0.2, fake))
    monkeypatch.setattr(settings, "EMBEDDING_LOAD_TIMEOUT", 0.05)

    svc = _make_service()
    assert svc._ensure_embedding() is False
    assert svc._embedding is None  # 本次调用已回退，但线程仍在跑

    _join_background(svc)  # 等后台加载完成（模拟后续请求到来前）

    assert svc._ensure_embedding() is True
    assert svc._embedding is fake
    assert svc._embedding_load_attempts == 1  # 没有重复启动加载线程


def test_failure_allows_retry_with_count_increment(monkeypatch):
    """（b）加载失败返回 False；下一次调用重新尝试并成功（计数递增，不永久卡死）。"""
    calls = {"n": 0}
    fake = _FakeEmbedder()

    def flaky_load():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("模拟 BGE 首次加载失败")
        return fake

    monkeypatch.setattr(vector_service_module, "get_embedder", flaky_load)
    monkeypatch.setattr(settings, "EMBEDDING_LOAD_TIMEOUT", 2.0)

    svc = _make_service()
    assert svc._ensure_embedding() is False
    assert svc._embedding_load_attempts == 1
    assert isinstance(svc._embedding_last_error, RuntimeError)

    # 失败后允许重试：第二次尝试应重新启动线程并成功
    assert svc._ensure_embedding() is True
    assert svc._embedding is fake
    assert svc._embedding_load_attempts == 2
    assert calls["n"] == 2
    assert svc._embedding_last_error is None  # 重试成功前已重置


def test_timeout_comes_from_settings_and_returns_early(monkeypatch):
    """（c）等待时长取自 settings.EMBEDDING_LOAD_TIMEOUT（慢加载 0.5s，超时 0.05s 应快速返回）。"""
    fake = _FakeEmbedder()
    monkeypatch.setattr(vector_service_module, "get_embedder", _fake_loader(0.5, fake))
    monkeypatch.setattr(settings, "EMBEDDING_LOAD_TIMEOUT", 0.05)

    svc = _make_service()
    started = time.monotonic()
    assert svc._ensure_embedding() is False
    elapsed = time.monotonic() - started

    # 不应等满 0.5s 的慢加载（留足 Windows 定时器抖动余量）
    assert elapsed < 0.4, f"等待了 {elapsed:.3f}s，未按 settings 超时提前返回"

    # 第二次调用继续复用同一线程（仍超时返回 False），随后线程完成可回填
    thread = svc._embedding_load_thread
    assert svc._ensure_embedding() is False
    assert svc._embedding_load_thread is thread

    _join_background(svc)
    assert svc._ensure_embedding() is True
    assert svc._embedding is fake


def test_background_thread_started_once_and_reused(monkeypatch):
    """并发/连续调用共享同一个后台加载线程，get_embedder 只被调用一次。"""
    calls = {"n": 0}
    fake = _FakeEmbedder()

    def slow_load():
        calls["n"] += 1
        time.sleep(0.3)
        return fake

    monkeypatch.setattr(vector_service_module, "get_embedder", slow_load)
    monkeypatch.setattr(settings, "EMBEDDING_LOAD_TIMEOUT", 0.02)

    svc = _make_service()
    results = []

    def call() -> None:
        results.append(svc._ensure_embedding())

    callers = [threading.Thread(target=call) for _ in range(4)]
    for t in callers:
        t.start()
    for t in callers:
        t.join(5.0)

    assert results == [False, False, False, False]
    assert calls["n"] == 1, f"后台加载线程被重复启动（get_embedder 调用了 {calls['n']} 次）"
    assert svc._embedding_load_attempts == 1

    _join_background(svc)
    assert svc._ensure_embedding() is True
    assert svc._embedding is fake
