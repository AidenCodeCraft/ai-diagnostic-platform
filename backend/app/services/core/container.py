"""依赖注入容器 — 轻量级服务定位器。

管理所有 RAG 组件的生命周期和依赖关系。
支持运行时热替换（A/B 测试）。
"""

from __future__ import annotations
from typing import Any, Dict, Optional

from app.services.core.config import RAGConfig, DEFAULT_CONFIG


class ServiceContainer:
    _instance: Optional["ServiceContainer"] = None

    def __init__(self, config: Optional[RAGConfig] = None):
        self.config = config or DEFAULT_CONFIG
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, callable] = {}

    @classmethod
    def instance(cls) -> "ServiceContainer":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, name: str, service: Any) -> None:
        self._services[name] = service

    def register_factory(self, name: str, factory: callable) -> None:
        self._factories[name] = factory

    def resolve(self, name: str) -> Any:
        if name in self._services:
            return self._services[name]
        if name in self._factories:
            service = self._factories[name]()
            self._services[name] = service
            return service
        raise KeyError(f"Service '{name}' not registered")

    def replace(self, name: str, service: Any) -> None:
        self._services[name] = service

    def reset(self) -> None:
        self._services.clear()
