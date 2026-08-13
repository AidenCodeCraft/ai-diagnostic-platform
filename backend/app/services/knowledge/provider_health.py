"""Provider 健康度追踪 — 智能路由的基础设施。

记录每个 Provider 的：
  - 最近 N 次调用的延迟
  - 成功率（成功次数 / 总次数）
  - 最后健康检查时间

基于健康度评分实现智能路由：
  - 优先选择健康度高 + 延迟低的 Provider
  - 对故障 Provider 自动降权

Usage:
    tracker = get_provider_health_tracker()

    # 记录调用
    start = time.time()
    try:
        result = provider.chat(messages)
        tracker.record_success("deepseek", (time.time() - start) * 1000)
    except Exception as e:
        tracker.record_failure("deepseek", str(e))

    # 获取最佳 Provider
    best = tracker.get_best_provider(["deepseek", "openai_compatible"])

    # 获取监控数据
    stats = tracker.get_all_stats()
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class ProviderStats:
    """单个 Provider 的运行时统计。"""

    name: str
    total_calls: int = 0
    success_calls: int = 0
    fail_calls: int = 0
    # 最近 20 次调用的延迟（毫秒）
    recent_latencies: deque = field(default_factory=lambda: deque(maxlen=20))
    last_call_time: float = 0.0
    last_error: str = ""
    last_error_time: float = 0.0

    @property
    def success_rate(self) -> float:
        """成功率 (0.0 ~ 1.0)。"""
        if self.total_calls == 0:
            return 1.0
        return self.success_calls / self.total_calls

    @property
    def avg_latency_ms(self) -> float:
        """最近 N 次调用的平均延迟（毫秒）。"""
        if not self.recent_latencies:
            return 0.0
        return sum(self.recent_latencies) / len(self.recent_latencies)

    @property
    def health_score(self) -> float:
        """综合健康度评分 (0.0 ~ 1.0)。

        计算公式: 0.7 × 成功率 + 0.3 × 延迟因子
          - 成功率权重 70%
          - 延迟因子: 延迟越低越好，3000ms 以上为 0
        """
        latency_factor = max(0.0, 1.0 - self.avg_latency_ms / 3000.0)
        return 0.7 * self.success_rate + 0.3 * latency_factor

    def record_success(self, latency_ms: float) -> None:
        """记录一次成功调用。

        Args:
            latency_ms: 调用延迟（毫秒）
        """
        self.total_calls += 1
        self.success_calls += 1
        self.recent_latencies.append(latency_ms)
        self.last_call_time = time.time()

    def record_failure(self, error: str) -> None:
        """记录一次失败调用。

        Args:
            error: 错误信息
        """
        self.total_calls += 1
        self.fail_calls += 1
        self.last_error = error
        self.last_error_time = time.time()
        self.last_call_time = time.time()


# ---------------------------------------------------------------------------
# 健康度追踪器
# ---------------------------------------------------------------------------


class ProviderHealthTracker:
    """Provider 健康度全局追踪器（线程安全）。

    设计要点：
      - 使用 threading.Lock 保证线程安全
      - 滑动窗口限制 20 条延迟记录（内存可控）
      - get_best_provider 排除严重故障的 Provider
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stats: Dict[str, ProviderStats] = {}

    def get_stats(self, name: str) -> ProviderStats:
        """获取指定 Provider 的统计信息（线程安全）。

        如果 Provider 未被记录过，自动创建默认统计对象。

        Args:
            name: Provider 名称

        Returns:
            Provider 统计信息
        """
        with self._lock:
            if name not in self._stats:
                self._stats[name] = ProviderStats(name=name)
            return self._stats[name]

    def record_success(self, name: str, latency_ms: float) -> None:
        """记录一次成功调用。

        Args:
            name: Provider 名称
            latency_ms: 调用延迟（毫秒）
        """
        with self._lock:
            self.get_stats(name).record_success(latency_ms)

    def record_failure(self, name: str, error: str) -> None:
        """记录一次失败调用。

        Args:
            name: Provider 名称
            error: 错误信息
        """
        with self._lock:
            self.get_stats(name).record_failure(error)

    def get_best_provider(self, candidates: List[str]) -> Optional[str]:
        """从候选列表中返回健康度最高的 Provider。

        排除条件：
          - 成功率 < 0.5 且至少调用过 3 次（刚启动的不排除）
          - 最近 60 秒内连续失败 3 次以上

        Args:
            candidates: 候选 Provider 名称列表

        Returns:
            最佳 Provider 名称，或 None（候选列表为空）
        """
        if not candidates:
            return None

        best_name = None
        best_score = -1.0
        now = time.time()

        with self._lock:
            for name in candidates:
                stats = self._stats.get(name)
                if stats is None:
                    # 未记录过的 Provider，给默认高分（优先尝试新 Provider）
                    if best_score < 0.9:
                        best_score = 0.9
                        best_name = name
                    continue

                # 排除严重故障的 Provider
                if stats.total_calls >= 3 and stats.success_rate < 0.5:
                    continue

                # 排除最近 60 秒内连续失败的
                if (
                    stats.fail_calls >= 3
                    and stats.last_error_time > 0
                    and (now - stats.last_error_time) < 60
                    and stats.success_calls == 0
                ):
                    continue

                score = stats.health_score
                if score > best_score:
                    best_score = score
                    best_name = name

        return best_name or (candidates[0] if candidates else None)

    def get_all_stats(self) -> Dict[str, Dict]:
        """获取所有 Provider 的统计信息（用于监控面板）。

        Returns:
            {provider_name: {total_calls, success_rate, avg_latency_ms,
                             health_score, last_error}, ...}
        """
        with self._lock:
            return {
                name: {
                    "total_calls": s.total_calls,
                    "success_rate": round(s.success_rate, 3),
                    "avg_latency_ms": round(s.avg_latency_ms, 1),
                    "health_score": round(s.health_score, 3),
                    "last_error": (
                        s.last_error[:100] if s.last_error else ""
                    ),
                }
                for name, s in self._stats.items()
            }

    def reset(self, name: Optional[str] = None) -> None:
        """重置统计信息。

        Args:
            name: 指定 Provider 名称（为 None 则重置全部）
        """
        with self._lock:
            if name:
                self._stats.pop(name, None)
            else:
                self._stats.clear()


# ---------------------------------------------------------------------------
# 模块级单例
# ---------------------------------------------------------------------------

_tracker: Optional[ProviderHealthTracker] = None


def get_provider_health_tracker() -> ProviderHealthTracker:
    """获取 ProviderHealthTracker 全局单例。"""
    global _tracker
    if _tracker is None:
        _tracker = ProviderHealthTracker()
    return _tracker
