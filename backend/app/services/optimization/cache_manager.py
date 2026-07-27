"""缓存管理器 — LRU 缓存 + TTL 过期 + 自动淘汰。

优化目标：
- 减少重复的 embedding 计算
- 减少重复的知识库搜索
- 减少重复的 LLM 调用

Usage:
    cache = CacheManager(max_size=1000, ttl_seconds=300)
    result = cache.get_or_set("key", lambda: expensive_call())
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple


class TTLCache:
    """带 TTL 的 LRU 缓存。"""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值，过期返回 None。"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            timestamp, value = entry
            if time.time() - timestamp > self._ttl:
                del self._cache[key]
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        """设置缓存值。超过 max_size 时淘汰最旧的条目。"""
        with self._lock:
            if len(self._cache) >= self._max_size and key not in self._cache:
                # 淘汰最旧的条目（基于插入时间）
                oldest_key = min(self._cache, key=lambda k: self._cache[k][0])
                del self._cache[oldest_key]
            self._cache[key] = (time.time(), value)

    def get_or_set(self, key: str, factory: Callable[[], Any]) -> Any:
        """获取缓存，未命中/过期时自动生成并缓存。"""
        value = self.get(key)
        if value is not None:
            return value
        value = factory()
        self.set(key, value)
        return value

    def invalidate(self, key: str) -> None:
        """删除指定缓存条目。"""
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        """清空所有缓存。"""
        with self._lock:
            self._cache.clear()

    @property
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / max(1, total),
            }


class EmbeddingCache(TTLCache):
    """Embedding 专用缓存 — 以文本的 MD5 为 key。

    缓存策略：
    - 命中率高的嵌入结果会被复用
    - TTL 较长（1 小时），因为嵌入结果较稳定
    """

    def __init__(self, max_size: int = 5000, ttl_seconds: int = 3600):
        super().__init__(max_size=max_size, ttl_seconds=ttl_seconds)

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def get_embedding(self, text: str) -> Optional[Any]:
        return self.get(self._hash(text))

    def set_embedding(self, text: str, embedding: Any) -> None:
        self.set(self._hash(text), embedding)


class KnowledgeSearchCache(TTLCache):
    """知识库搜索缓存 — 以搜索词的 hash 为 key。

    缓存策略：
    - 相同搜索词短时间内返回缓存结果
    - TTL 较短（5 分钟），因为知识库可能更新
    """

    def __init__(self, max_size: int = 500, ttl_seconds: int = 300):
        super().__init__(max_size=max_size, ttl_seconds=ttl_seconds)

    @staticmethod
    def _build_key(query: str, page_size: int) -> str:
        return hashlib.md5(f"{query}|{page_size}".encode("utf-8")).hexdigest()

    def get_search_result(self, query: str, page_size: int) -> Optional[Any]:
        return self.get(self._build_key(query, page_size))

    def set_search_result(self, query: str, page_size: int, result: Any) -> None:
        self.set(self._build_key(query, page_size), result)
