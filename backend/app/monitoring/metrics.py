"""Prometheus 指标采集 — FastAPI 中间件集成。

导出指标：
- http_requests_total: 请求计数器（含 status/method/path）
- http_request_duration_seconds: 请求延迟直方图
- http_ratelimit_rejected_total: 限流拒绝计数器
- http_requests_in_progress: 当前进行中的请求数
- db_query_duration_seconds: 数据库查询延迟
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

# 不强制依赖 prometheus_client，可用 mock 模式
try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        generate_latest,
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False


class MetricsRegistry:
    """指标注册表 — 在 prometheus_client 不可用时提供 no-op。"""

    def __init__(self):
        if _PROMETHEUS_AVAILABLE:
            self._registry = CollectorRegistry()

            self.http_requests_total = Counter(
                "http_requests_total",
                "Total HTTP requests",
                ["method", "path", "status"],
                registry=self._registry,
            )
            self.http_request_duration = Histogram(
                "http_request_duration_seconds",
                "HTTP request duration",
                ["method", "path"],
                buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
                registry=self._registry,
            )
            self.http_requests_in_progress = Gauge(
                "http_requests_in_progress",
                "Currently in-progress HTTP requests",
                ["method"],
                registry=self._registry,
            )
            self.rate_limit_rejected = Counter(
                "http_ratelimit_rejected_total",
                "Total rate-limited requests rejected",
                ["path"],
                registry=self._registry,
            )
            self.db_query_duration = Histogram(
                "db_query_duration_seconds",
                "Database query duration",
                ["operation"],
                buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
                registry=self._registry,
            )
        else:
            self._registry = None
            self.http_requests_total = _NoopCounter()
            self.http_request_duration = _NoopHistogram()
            self.http_requests_in_progress = _NoopGauge()
            self.rate_limit_rejected = _NoopCounter()
            self.db_query_duration = _NoopHistogram()

    def generate(self) -> bytes:
        if self._registry and _PROMETHEUS_AVAILABLE:
            return generate_latest(self._registry)
        return b"# Prometheus metrics disabled (prometheus-client not installed)\n"

    @property
    def content_type(self) -> str:
        return CONTENT_TYPE_LATEST if _PROMETHEUS_AVAILABLE else "text/plain"


# ── No-op 替代品 ─────────────────────────────────────────

class _NoopCounter:
    def labels(self, **kwargs): return self
    def inc(self, amount=1): pass


class _NoopHistogram:
    def labels(self, **kwargs): return self
    def observe(self, amount): pass


class _NoopGauge:
    def labels(self, **kwargs): return self
    def inc(self, amount=1): pass
    def dec(self, amount=1): pass
    def set(self, value): pass


# ── 全局指标实例 ─────────────────────────────────────────

metrics = MetricsRegistry()


# ── FastAPI 中间件 ───────────────────────────────────────

class MetricsMiddleware(BaseHTTPMiddleware):
    """HTTP 指标采集中间件。

    自动记录：
    - 请求计数（按 method/path/status）
    - 请求延迟分布（直方图）
    - 当前请求数（Gauge）
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        method = request.method
        path = request.url.path

        metrics.http_requests_in_progress.labels(method=method).inc()
        start_time = time.time()

        try:
            response = await call_next(request)
            status = str(response.status_code)
            metrics.http_requests_total.labels(
                method=method, path=path, status=status,
            ).inc()
            return response
        except Exception:
            metrics.http_requests_total.labels(
                method=method, path=path, status="500",
            ).inc()
            raise
        finally:
            duration = time.time() - start_time
            metrics.http_request_duration.labels(
                method=method, path=path,
            ).observe(duration)
            metrics.http_requests_in_progress.labels(method=method).dec()


# ── Metrics 端点 ─────────────────────────────────────────

def setup_metrics(app: FastAPI, metrics_path: str = "/metrics"):
    """在 FastAPI 应用中注册 Prometheus 指标端点。

    Usage:
        from app.monitoring.metrics import setup_metrics
        setup_metrics(app)
    """
    # 注册指标中间件
    app.add_middleware(MetricsMiddleware)

    from fastapi.responses import Response as FastAPIResponse

    @app.get(metrics_path, include_in_schema=False)
    async def prometheus_metrics():
        """Prometheus metrics endpoint (不会被 metrics 中间件计入)。"""
        return FastAPIResponse(
            content=metrics.generate(),
            media_type=metrics.content_type,
        )

    import logging
    logger = logging.getLogger(__name__)
    logger.info("[Metrics] Prometheus endpoint registered at %s", metrics_path)


# ── 数据库计时器 ─────────────────────────────────────────

class DBTimer:
    """数据库查询计时器 — 上下文管理器。

    Usage:
        with DBTimer("knowledge_search"):
            results = knowledge.search(query)
    """

    def __init__(self, operation: str):
        self.operation = operation
        self.start = 0.0

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        duration = time.time() - self.start
        metrics.db_query_duration.labels(operation=self.operation).observe(duration)
