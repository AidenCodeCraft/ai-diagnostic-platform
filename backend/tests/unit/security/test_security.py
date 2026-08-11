"""安全模块边界测试 — 脱敏 + 速率限制 + 防重放 + 输入验证。"""

from __future__ import annotations

import re
import time

from app.security.log_desensitizer import (
    SensitiveDataFilter,
    DesensitizeLevel,
    AuditLogger,
    SENSITIVE_PATTERNS,
)
from app.security.api_security import (
    TokenBucket,
    RateLimiter,
    ReplayProtection,
    InputValidator,
    SecurityMiddleware,
)


# ═══════════════════════════════════════════════════════════
# TokenBucket
# ═══════════════════════════════════════════════════════════

def test_token_bucket_initial():
    bucket = TokenBucket(capacity=10, fill_rate=1.0)
    assert bucket.tokens == 10.0


def test_token_bucket_consume():
    bucket = TokenBucket(capacity=10, fill_rate=10.0)
    # 初始可消费
    assert bucket.consume() is True
    assert bucket.tokens < 10.0


def test_token_bucket_depleted():
    bucket = TokenBucket(capacity=1, fill_rate=0.0)
    assert bucket.consume() is True
    assert bucket.consume() is False


def test_token_bucket_refill():
    bucket = TokenBucket(capacity=5, fill_rate=100.0)
    # 快速消耗
    for _ in range(5):
        assert bucket.consume()
    assert bucket.consume() is False
    time.sleep(0.1)
    # 应该已经补充了
    assert bucket.consume() is True


def test_token_bucket_multi_consume():
    bucket = TokenBucket(capacity=5, fill_rate=0)
    assert bucket.consume(3) is True
    assert bucket.consume(3) is False  # 只剩 2


# ═══════════════════════════════════════════════════════════
# RateLimiter
# ═══════════════════════════════════════════════════════════

def test_rate_limiter_creation():
    rl = RateLimiter(global_rate=100, per_path_rate=20, per_ip_rate=10)
    assert rl.global_bucket.capacity == 100
    assert rl.per_path_rate == 20
    assert rl.per_ip_rate == 10


def test_rate_limiter_get_client_ip():
    rl = RateLimiter()
    from unittest.mock import MagicMock
    request = MagicMock()
    request.headers = {"X-Forwarded-For": "10.0.0.1, 1.2.3.4"}
    assert rl._get_client_ip(request) == "10.0.0.1"


def test_rate_limiter_real_ip():
    rl = RateLimiter()
    from unittest.mock import MagicMock
    request = MagicMock()
    request.headers = {"X-Real-IP": "5.6.7.8"}
    request.client = None
    assert rl._get_client_ip(request) == "5.6.7.8"


def test_rate_limiter_default_ip():
    rl = RateLimiter()
    from unittest.mock import MagicMock
    request = MagicMock()
    request.headers = {}
    request.client.host = "192.168.1.1"
    assert rl._get_client_ip(request) == "192.168.1.1"


# ═══════════════════════════════════════════════════════════
# ReplayProtection
# ═══════════════════════════════════════════════════════════

def test_replay_no_headers():
    rp = ReplayProtection()
    from unittest.mock import MagicMock
    request = MagicMock()
    request.headers = {}
    # 不发送 Nonce/Timestamp 时不应拒绝
    assert rp.validate(request) is None


def test_replay_valid():
    rp = ReplayProtection()
    from unittest.mock import MagicMock
    request = MagicMock()
    request.headers = {
        "X-Request-Nonce": "unique-nonce-123",
        "X-Request-Timestamp": str(int(time.time())),
    }
    assert rp.validate(request) is None


def test_replay_duplicate():
    rp = ReplayProtection()
    from unittest.mock import MagicMock
    request = MagicMock()
    request.headers = {
        "X-Request-Nonce": "duplicate-nonce",
        "X-Request-Timestamp": str(int(time.time())),
    }
    assert rp.validate(request) is None
    second_result = rp.validate(request)
    assert second_result is not None and "duplicate_nonce" not in second_result  # 可能返回错误


def test_replay_expired_timestamp():
    rp = ReplayProtection()
    from unittest.mock import MagicMock
    request = MagicMock()
    request.headers = {
        "X-Request-Nonce": "expired-one",
        "X-Request-Timestamp": str(int(time.time()) - 600),  # 10分钟前
    }
    result = rp.validate(request)
    assert result is not None  # 超过5分钟窗口


def test_replay_disabled():
    rp = ReplayProtection(enabled=False)
    from unittest.mock import MagicMock
    request = MagicMock()
    request.headers = {}
    assert rp.validate(request) is None


# ═══════════════════════════════════════════════════════════
# InputValidator
# ═══════════════════════════════════════════════════════════

def test_valid_input():
    assert InputValidator.validate_input("USB timeout 超时") is None
    assert InputValidator.validate_input("正常输入") is None


def test_sql_injection_detection():
    assert InputValidator.validate_input("'; DROP TABLE users; --") is not None
    assert InputValidator.validate_input("1' OR '1'='1") is not None
    assert InputValidator.validate_input("SELECT * FROM users") is not None


def test_xss_detection():
    assert InputValidator.validate_input("<script>alert('xss')</script>") is not None
    assert InputValidator.validate_input("javascript:void(0)") is not None
    assert InputValidator.validate_input("<img onerror='alert(1)'>") is not None


def test_path_traversal():
    assert InputValidator.validate_input("../../etc/passwd") is not None
    assert InputValidator.validate_input("..\\..\\windows\\system32") is not None


def test_validate_dict():
    errors = InputValidator.validate_dict({
        "query": "normal query",
        "malicious": "<script>xss</script>",
    })
    assert len(errors) > 0
    assert "malicious" in errors[0]


def test_validate_nested_dict():
    errors = InputValidator.validate_dict({
        "user": {"name": "test", "sql": "'; DROP TABLE --"},
    })
    assert len(errors) > 0


# ═══════════════════════════════════════════════════════════
# DesensitizeLevel
# ═══════════════════════════════════════════════════════════

def test_desensitize_level_values():
    assert DesensitizeLevel.STRICT.value == "strict"
    assert DesensitizeLevel.MODERATE.value == "moderate"
    assert DesensitizeLevel.MINIMAL.value == "minimal"


# ═══════════════════════════════════════════════════════════
# SensitiveDataFilter
# ═══════════════════════════════════════════════════════════

def test_filter_api_key():
    f = SensitiveDataFilter(level=DesensitizeLevel.STRICT)
    text = "Authorization: sk-abcdef12345678901234567890"
    result = f.desensitize(text)
    assert "sk-" not in result.lower() or "API_KEY" in result


def test_filter_bearer_token():
    f = SensitiveDataFilter(level=DesensitizeLevel.STRICT)
    text = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.test"
    result = f.desensitize(text)
    assert "JWT" in result or "****" in result
    assert "eyJ" not in result


def test_filter_password():
    f = SensitiveDataFilter(level=DesensitizeLevel.STRICT)
    text = 'password=mySecretPass123'
    result = f.desensitize(text)
    assert "mySecretPass123" not in result


def test_filter_phone_strict():
    f = SensitiveDataFilter(level=DesensitizeLevel.STRICT)
    text = "请联系 13812345678 获取帮助"
    result = f.desensitize(text)
    assert "13812345678" not in result


def test_filter_phone_moderate():
    f = SensitiveDataFilter(level=DesensitizeLevel.MODERATE)
    text = "请联系 13812345678"
    result = f.desensitize(text)
    assert "13812345678" not in result


def test_filter_email_moderate():
    f = SensitiveDataFilter(level=DesensitizeLevel.MODERATE)
    text = "邮箱: test@example.com"
    result = f.desensitize(text)
    assert "test@example.com" not in result
    assert "example.com" in result  # moderate 保留域名


def test_filter_email_strict():
    f = SensitiveDataFilter(level=DesensitizeLevel.STRICT)
    text = "邮箱: test@example.com"
    result = f.desensitize(text)
    assert "test@example.com" not in result
    assert "****" in result


def test_filter_id_card():
    f = SensitiveDataFilter(level=DesensitizeLevel.STRICT)
    text = "身份证: 110101199001011234"
    result = f.desensitize(text)
    assert "110101199001011234" not in result


def test_filter_db_url():
    f = SensitiveDataFilter(level=DesensitizeLevel.STRICT)
    text = "postgresql://user:password123@localhost:5432/db"
    result = f.desensitize(text)
    assert "password123" not in result


def test_filter_no_sensitive_data():
    f = SensitiveDataFilter(level=DesensitizeLevel.STRICT)
    text = "USB timeout at port 1"
    result = f.desensitize(text)
    assert result == text


def test_filter_empty_text():
    f = SensitiveDataFilter(level=DesensitizeLevel.STRICT)
    assert f.desensitize("") == ""
    assert f.desensitize("ab") == "ab"


def test_filter_patterns_compiled():
    # 确保所有模式都是编译后的正则
    for rule in SENSITIVE_PATTERNS:
        assert "pattern" in rule
        assert isinstance(rule["pattern"], re.Pattern)


# ═══════════════════════════════════════════════════════════
# AuditLogger
# ═══════════════════════════════════════════════════════════

def test_audit_logger_creation():
    audit = AuditLogger()
    assert audit is not None


def test_audit_logger_log():
    audit = AuditLogger()
    # 不应该抛出异常
    audit.log("test_action", user_id=1, ip="1.2.3.4", success=True)


def test_get_audit_logger():
    from app.security.log_desensitizer import get_audit_logger
    audit = get_audit_logger()
    assert audit is not None


# ═══════════════════════════════════════════════════════════
# Security Headers
# ═══════════════════════════════════════════════════════════

def test_security_headers():
    from fastapi import Response
    resp = Response(content="test")
    resp = SecurityMiddleware._add_security_headers(resp)
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("Strict-Transport-Security") is not None
    assert resp.headers.get("Content-Security-Policy") is not None
