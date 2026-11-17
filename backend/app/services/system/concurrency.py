"""并发提问闸门：限制同时进行的 AI 提问数（≈最大同时在线人数）。

管理后台「系统参数」中的 max_online_users 决定闸门容量；
超限时新的提问请求被拒绝（HTTP 429 / SSE error 事件），已在流式输出中的请求不受影响。
"""
from __future__ import annotations

import threading


class ConcurrencyGate:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inflight = 0

    @property
    def inflight(self) -> int:
        with self._lock:
            return self._inflight

    def acquire(self, limit: int) -> bool:
        """占用一个并发名额。limit <= 0 表示不限制。满员时返回 False。"""
        with self._lock:
            if limit > 0 and self._inflight >= limit:
                return False
            self._inflight += 1
            return True

    def release(self) -> None:
        with self._lock:
            self._inflight = max(0, self._inflight - 1)


# 进程内全局闸门（chat 流式/非流式提问共用）
chat_gate = ConcurrencyGate()
