"""连接池优化 — 数据库连接复用 + 请求限流 + 背压控制。

优化目标：
- 减少数据库连接创建/销毁开销
- 防止突发请求击垮后端服务
- 优雅处理慢请求
"""

from __future__ import annotations

import threading
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class RequestThrottle:
    """请求限流器 — 令牌桶算法。

    防止突发请求耗尽后端资源。
    """

    def __init__(self, max_requests: int = 100, per_seconds: float = 1.0):
        self._max_tokens = max_requests
        self._rate = max_requests / per_seconds  # tokens per second
        self._tokens = float(max_requests)
        self._lock = threading.RLock()
        self._last_refill = time.time()

    def acquire(self) -> bool:
        """尝试获取一个令牌。成功返回 True，否则返回 False。"""
        with self._lock:
            now = time.time()
            elapsed = now - self._last_refill

            # 补充令牌
            self._tokens = min(self._max_tokens, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True

            return False

    @property
    def available_tokens(self) -> float:
        with self._lock:
            return self._tokens


def throttle(max_requests: int = 100, per_seconds: float = 1.0):
    """限流装饰器。

    Usage:
        @throttle(max_requests=50, per_seconds=1.0)
        def heavy_handler():
            ...
    """
    limiter = RequestThrottle(max_requests, per_seconds)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not limiter.acquire():
                from fastapi import HTTPException
                raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
            return func(*args, **kwargs)
        return wrapper
    return decorator


class TimedOperation:
    """耗时操作计时器 — 用于性能监控。"""

    def __init__(self):
        self._records: Dict[str, list] = {}

    def record(self, operation: str, duration_ms: float) -> None:
        if operation not in self._records:
            self._records[operation] = []
        self._records[operation].append(duration_ms)

    def stats(self) -> Dict[str, Dict[str, float]]:
        result = {}
        for op, times in self._records.items():
            if times:
                result[op] = {
                    "count": len(times),
                    "avg_ms": sum(times) / len(times),
                    "max_ms": max(times),
                    "min_ms": min(times),
                    "p95_ms": sorted(times)[int(len(times) * 0.95)] if len(times) >= 20 else None,
                }
        return result

    def reset(self) -> None:
        self._records.clear()


class ContextTimer:
    """上下文管理器 — 自动计时并记录。"""

    def __init__(self, operation_name: str, timer: TimedOperation):
        self._name = operation_name
        self._timer = timer
        self._start = 0.0

    def __enter__(self):
        self._start = time.time()
        return self

    def __exit__(self, *args):
        elapsed = (time.time() - self._start) * 1000
        self._timer.record(self._name, elapsed)


# Global instances
_global_timer = TimedOperation()
embedding_throttle = RequestThrottle(max_requests=30, per_seconds=1.0)
knowledge_search_throttle = RequestThrottle(max_requests=50, per_seconds=1.0)


def get_timer() -> TimedOperation:
    return _global_timer


def time_operation(operation_name: str) -> ContextTimer:
    return ContextTimer(operation_name, _global_timer)
