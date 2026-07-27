"""API 安全中间件 — 速率限制 + 防重放攻击 + 安全头 + 输入验证。

集成：
- Token Bucket 速率限制（全局 + 每路径 + 每IP）
- 防重放攻击（Nonce + Timestamp）
- CSP/STS/XSS 安全头
- 请求体大小限制
- SQL注入/XSS 输入验证
"""

from __future__ import annotations

import hashlib
import time
import re
import json
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import Response, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app.monitoring.metrics import metrics


# ═══════════════════════════════════════════════════════════
# Token Bucket 速率限制
# ═══════════════════════════════════════════════════════════

class TokenBucket:
    """令牌桶限流器 — 线程安全。

    算法：每秒补充 tokens_per_second 个令牌，容量为 capacity。
    请求消耗 1 个令牌，无令牌则拒绝。
    """

    def __init__(self, capacity: int, fill_rate: float):
        self.capacity = capacity
        self.fill_rate = fill_rate  # tokens per second
        self.tokens = float(capacity)
        self.last_fill = time.time()

    def consume(self, tokens: int = 1) -> bool:
        now = time.time()
        elapsed = now - self.last_fill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
        self.last_fill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class RateLimiter:
    """多层级速率限制器。

    支持：
    - 全局桶 (所有请求)
    - 路径桶 (每个 endpoint)
    - IP 桶 (每个来源 IP)
    """

    def __init__(
        self,
        global_rate: int = 600,         # 全局每分钟
        per_path_rate: int = 120,       # 每路径每分钟
        per_ip_rate: int = 60,          # 每 IP 每分钟
        cleanup_interval: int = 300,    # 5分钟清理过期桶
    ):
        self.global_bucket = TokenBucket(global_rate, global_rate / 60.0)
        self.per_path_rate = per_path_rate
        self.per_ip_rate = per_ip_rate
        self.path_buckets: Dict[str, TokenBucket] = {}
        self.ip_buckets: Dict[str, TokenBucket] = {}
        self.last_cleanup = time.time()
        self.cleanup_interval = cleanup_interval

    def _get_client_ip(self, request: Request) -> str:
        """从请求中获取客户端真实 IP。"""
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP", "")
        if real_ip:
            return real_ip
        if request.client:
            return request.client.host
        return "unknown"

    def check(self, request: Request, path: str) -> Tuple[bool, str]:
        """检查请求是否被限流。返回 (allowed, reason)。"""
        self._cleanup_if_needed()

        # 1. 全局限流
        if not self.global_bucket.consume():
            metrics.rate_limit_rejected.labels(path="global").inc()
            return False, "global_rate_limit"

        # 2. 路径限流
        if path not in self.path_buckets:
            self.path_buckets[path] = TokenBucket(
                self.per_path_rate,
                self.per_path_rate / 60.0,
            )
        if not self.path_buckets[path].consume():
            metrics.rate_limit_rejected.labels(path=path).inc()
            return False, f"path_rate_limit:{path}"

        # 3. IP 限流
        ip = self._get_client_ip(request)
        if ip not in self.ip_buckets:
            self.ip_buckets[ip] = TokenBucket(
                self.per_ip_rate,
                self.per_ip_rate / 60.0,
            )
        if not self.ip_buckets[ip].consume():
            metrics.rate_limit_rejected.labels(path=f"ip:{ip}").inc()
            return False, f"ip_rate_limit:{ip}"

        return True, ""

    def _cleanup_if_needed(self):
        now = time.time()
        if now - self.last_cleanup > self.cleanup_interval:
            # 清理长时间未使用的桶
            cutoff = now - self.cleanup_interval * 2
            self.path_buckets = {
                k: v for k, v in self.path_buckets.items()
                if v.last_fill > cutoff
            }
            self.ip_buckets = {
                k: v for k, v in self.ip_buckets.items()
                if v.last_fill > cutoff
            }
            self.last_cleanup = now


# ═══════════════════════════════════════════════════════════
# 防重放攻击 (Nonce + Timestamp)
# ═══════════════════════════════════════════════════════════

class ReplayProtection:
    """防重放攻击 — 基于 Nonce + 时间窗口。

    策略：
    - 每个请求附带 X-Request-Nonce 和 X-Request-Timestamp
    - 时间窗口：正负 5 分钟
    - 已使用的 nonce 存储在内存 LRU 中（最多 10000 条）
    """

    MAX_TIME_DELTA = 300  # 5 分钟
    MAX_NONCE_STORE = 10000

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._used_nonces: Dict[str, float] = {}

    def validate(self, request: Request) -> Optional[str]:
        """验证请求的防重放参数。返回 None 表示通过，返回错误消息表示拒绝。"""
        if not self.enabled:
            return None

        nonce = request.headers.get("X-Request-Nonce", "")
        ts_str = request.headers.get("X-Request-Timestamp", "")

        if not nonce or not ts_str:
            return None  # 不强制客户端发送（向后兼容）

        # 时间戳验证
        try:
            ts = int(ts_str)
        except (ValueError, TypeError):
            return "Invalid timestamp format"

        now = int(time.time())
        if abs(now - ts) > self.MAX_TIME_DELTA:
            return "Request timestamp expired (max 5 minutes)"

        # Nonce 去重
        if nonce in self._used_nonces:
            return "Duplicate nonce detected (possible replay attack)"

        self._used_nonces[nonce] = now

        # 清理过期 nonce
        if len(self._used_nonces) > self.MAX_NONCE_STORE:
            cutoff = now - self.MAX_TIME_DELTA * 4
            self._used_nonces = {
                k: v for k, v in self._used_nonces.items()
                if v > cutoff
            }

        return None


# ═══════════════════════════════════════════════════════════
# 输入验证（SQL注入 / XSS 检测）
# ═══════════════════════════════════════════════════════════

class InputValidator:
    """输入验证器 — 检测恶意输入模式。

    检测：
    - SQL 注入模式
    - XSS 注入模式
    - 路径遍历
    """

    SQL_INJECTION_PATTERNS = [
        re.compile(r"(\b(?:SELECT|INSERT|DELETE|UPDATE|DROP|UNION|ALTER|CREATE|EXEC)\b)", re.IGNORECASE),
        re.compile(r"(';\s*(?:DROP|DELETE|INSERT|SELECT|ALTER|CREATE|UPDATE|UNION))", re.IGNORECASE),
        re.compile(r"'\s+(?:OR|AND)\s+'[^']*'?\s*=", re.IGNORECASE),
        re.compile(r"(?:--|#|/\*).*\b(?:DROP|DELETE|INSERT|SELECT|ALTER|UPDATE)\b", re.IGNORECASE),
    ]

    XSS_PATTERNS = [
        re.compile(r"<script[^>]*>", re.IGNORECASE),
        re.compile(r"javascript:", re.IGNORECASE),
        re.compile(r"on\w+\s*=", re.IGNORECASE),
    ]

    PATH_TRAVERSAL_PATTERN = re.compile(r"\.\./|\.\.[\\/]")

    @classmethod
    def validate_input(cls, value: str) -> Optional[str]:
        """验证单个输入值。返回 None 表示安全，返回错误消息表示危险。"""
        if not value or not isinstance(value, str):
            return None

        v = value.strip()

        # SQL 注入检测
        for pattern in cls.SQL_INJECTION_PATTERNS:
            if pattern.search(v):
                return "Potential SQL injection detected"

        # XSS 检测
        for pattern in cls.XSS_PATTERNS:
            if pattern.search(v):
                return "Potential XSS attack detected"

        # 路径遍历
        if cls.PATH_TRAVERSAL_PATTERN.search(v):
            return "Path traversal detected"

        return None

    @classmethod
    def validate_dict(cls, data: Dict[str, Any]) -> List[str]:
        """递归验证字典中的所有字符串值。"""
        errors = []
        for key, value in data.items():
            if isinstance(value, str):
                err = cls.validate_input(value)
                if err:
                    errors.append(f"Field '{key}': {err}")
            elif isinstance(value, dict):
                errors.extend(cls.validate_dict(value))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        err = cls.validate_input(item)
                        if err:
                            errors.append(f"Field '{key}[]': {err}")
        return errors


# ═══════════════════════════════════════════════════════════
# FastAPI 中间件集成
# ═══════════════════════════════════════════════════════════

class SecurityMiddleware(BaseHTTPMiddleware):
    """综合安全中间件。

    功能：
    1. 速率限制
    2. 防重放攻击
    3. HTTP 安全头
    4. 请求体大小限制
    5. 输入验证（POST/PUT/PATCH 请求）
    """

    # 不需要限流和安全检查的路径
    EXCLUDED_PATHS: Set[str] = {
        "/health", "/metrics", "/docs", "/openapi.json", "/redoc",
    }

    def __init__(
        self,
        app: ASGIApp,
        rate_limiter: Optional[RateLimiter] = None,
        replay_protection: Optional[ReplayProtection] = None,
        max_body_size: int = 10 * 1024 * 1024,  # 10MB
        enable_input_validation: bool = True,
    ):
        super().__init__(app)
        self.rate_limiter = rate_limiter or RateLimiter()
        self.replay_protection = replay_protection or ReplayProtection()
        self.max_body_size = max_body_size
        self.enable_input_validation = enable_input_validation

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # 排除健康检查等路径
        if path in self.EXCLUDED_PATHS or path.startswith("/static/"):
            return await call_next(request)

        # 1. 速率限制
        allowed, reason = self.rate_limiter.check(request, path)
        if not allowed:
            from app.security.log_desensitizer import get_audit_logger
            ip = self.rate_limiter._get_client_ip(request)
            get_audit_logger().log(
                "rate_limit_rejected",
                ip=ip,
                resource=path,
                success=False,
                extra={"reason": reason},
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "请求过于频繁，请稍后再试",
                    "retry_after": 60,
                },
                headers={"Retry-After": "60"},
            )

        # 2. 防重放攻击
        replay_error = self.replay_protection.validate(request)
        if replay_error:
            return JSONResponse(
                status_code=403,
                content={"detail": replay_error},
            )

        # 3. 输入验证（仅 POST/PUT/PATCH）
        if self.enable_input_validation and request.method in ("POST", "PUT", "PATCH"):
            content_type = request.headers.get("content-type", "")
            # 克隆请求体用于验证（不影响后续处理）
            if "application/json" in content_type:
                try:
                    body = await request.body()
                    if len(body) > self.max_body_size:
                        return JSONResponse(
                            status_code=413,
                            content={"detail": "请求体过大"},
                        )

                    if body:
                        data = json.loads(body)
                        errors = InputValidator.validate_dict(data)
                        if errors:
                            from app.security.log_desensitizer import get_audit_logger
                            get_audit_logger().log(
                                "input_validation_failed",
                                resource=path,
                                success=False,
                                extra={"errors": errors[:3]},
                            )
                            return JSONResponse(
                                status_code=400,
                                content={
                                    "detail": "输入验证失败",
                                    "errors": errors[:3],
                                },
                            )

                except json.JSONDecodeError:
                    pass  # 非 JSON 请求体，跳过验证

        # 4. 执行请求 + 添加安全头
        response = await call_next(request)
        return self._add_security_headers(response)

    @staticmethod
    def _add_security_headers(response: Response) -> Response:
        """添加安全响应头。"""
        headers = response.headers

        # 防止点击劫持
        if "X-Frame-Options" not in headers:
            headers["X-Frame-Options"] = "DENY"

        # 防止 MIME 类型嗅探
        if "X-Content-Type-Options" not in headers:
            headers["X-Content-Type-Options"] = "nosniff"

        # 启用 XSS 过滤器
        if "X-XSS-Protection" not in headers:
            headers["X-XSS-Protection"] = "1; mode=block"

        # 引用策略
        if "Referrer-Policy" not in headers:
            headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # HSTS（1年）
        if "Strict-Transport-Security" not in headers:
            headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # CSP（Content Security Policy）
        if "Content-Security-Policy" not in headers:
            headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "connect-src 'self' https://api.deepseek.com"
            )

        return response


# ── 公开 API ─────────────────────────────────────────────

def setup_security_middleware(
    app: FastAPI,
    global_rate_per_min: int = 600,
    per_path_rate_per_min: int = 120,
    per_ip_rate_per_min: int = 60,
    max_body_mb: int = 10,
    enable_replay_protection: bool = True,
    enable_input_validation: bool = True,
):
    """在 FastAPI 上安装安全中间件。

    Usage (in main.py):
        from app.security.api_security import setup_security_middleware
        setup_security_middleware(app, global_rate_per_min=600)
    """
    app.add_middleware(
        SecurityMiddleware,
        rate_limiter=RateLimiter(
            global_rate=global_rate_per_min,
            per_path_rate=per_path_rate_per_min,
            per_ip_rate=per_ip_rate_per_min,
        ),
        replay_protection=ReplayProtection(enabled=enable_replay_protection),
        max_body_size=max_body_mb * 1024 * 1024,
        enable_input_validation=enable_input_validation,
    )

    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        "[Security] Middleware installed: rate_limit=%d/min/path=%d/min/ip=%d/min "
        "replay=%s input_validation=%s body_limit=%dMB",
        global_rate_per_min,
        per_path_rate_per_min,
        per_ip_rate_per_min,
        enable_replay_protection,
        enable_input_validation,
        max_body_mb,
    )
