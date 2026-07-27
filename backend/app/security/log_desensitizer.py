"""日志脱敏中间件 — 自动检测并过滤敏感数据。

支持脱敏类型：
- API Key / Token  (sk-... / Bearer ... / eyJ...)
- 密码 / 凭证
- 手机号
- 邮箱
- 身份证号
- IP 地址（可选）
- 银行卡号
- 自定义正则模式

策略：
- 脱敏发生在日志输出前（logging.Filter）
- 支持部分保留（如邮箱保留 @ 前2位 + 域名）
- 可配置脱敏强度（strict / moderate / minimal）
"""

from __future__ import annotations

import re
import logging
from enum import Enum
from typing import Dict, Any, List, Optional, Set


class DesensitizeLevel(str, Enum):
    STRICT = "strict"       # 全部替换为 ***
    MODERATE = "moderate"   # 部分保留（如邮箱@前2位）
    MINIMAL = "minimal"     # 仅脱敏最敏感的（token/password）


# ── 脱敏规则配置 ────────────────────────────────────────

SENSITIVE_PATTERNS: List[Dict[str, Any]] = [
    # API Key (通用 sk- / api-key 格式)
    {
        "name": "api_key",
        "pattern": re.compile(r'(?:sk|api)[-_](?:key|token)[=:]\s*["\']?([A-Za-z0-9_-]{12,})["\']?', re.IGNORECASE),
        "replacement": r'****API_KEY****',
        "level": "all",
    },
    # API Key (裸 sk-xxx 格式)
    {
        "name": "api_key_raw",
        "pattern": re.compile(r'\b(sk-[A-Za-z0-9_-]{20,})\b'),
        "replacement": r'****API_KEY****',
        "level": "all",
    },
    # Bearer Token / JWT (更宽泛的匹配)
    {
        "name": "bearer_token",
        "pattern": re.compile(r'(?:Bearer|Authorization)[=:\s]+["\']?(eyJ[A-Za-z0-9_\-=+/]+\.[A-Za-z0-9_\-=+/]+\.[A-Za-z0-9_\-=+/]+)', re.IGNORECASE),
        "replacement": r'Bearer ****JWT****',
        "level": "all",
    },
    # 密码字段
    {
        "name": "password",
        "pattern": re.compile(r'(?:password|passwd|pwd|secret)[=:]\s*["\']?([^"\'&\s]{3,})["\']?', re.IGNORECASE),
        "replacement": r'****PASSWORD****',
        "level": "all",
    },
    # 手机号（中国大陆）
    {
        "name": "phone_cn",
        "pattern": re.compile(r'1[3-9]\d{9}'),
        "replacement": r'**********',
        "level": "strict",
    },
    # 手机号（moderate — 保留前3后4）
    {
        "name": "phone_cn_moderate",
        "pattern": re.compile(r'(1[3-9])\d{7}(\d{2})'),
        "replacement_moderate": r'\1*******\2',
        "replacement": r'**********',
        "level": "moderate",
    },
    # 邮箱
    {
        "name": "email",
        "pattern": re.compile(r'([\w.-]+)@([\w.-]+)'),
        "replacement_moderate": lambda m: f'{m.group(1)[:2]}***@{m.group(2)}',
        "replacement_strict": r'****@****.***',
        "level": "moderate",
    },
    # 身份证号（中国大陆）
    {
        "name": "id_card_cn",
        "pattern": re.compile(r'[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]'),
        "replacement": r'******************',
        "level": "strict",
    },
    # IP 地址（IPv4）
    {
        "name": "ipv4",
        "pattern": re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
        "replacement": r'***.***.***.***',
        "level": "minimal",
    },
    # 私钥 (PEM 格式)
    {
        "name": "private_key",
        "pattern": re.compile(r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA )?PRIVATE KEY-----'),
        "replacement": r'-----BEGIN PRIVATE KEY----- [REDACTED] -----END PRIVATE KEY-----',
        "level": "all",
    },
    # Connection String (db URL with password)
    {
        "name": "db_url",
        "pattern": re.compile(r'(?:postgresql|mysql|mongodb)://([^:]+):([^@]+)@'),
        "replacement": r'postgresql://\1:****@',
        "level": "all",
    },
]


class SensitiveDataFilter(logging.Filter):
    """日志敏感数据过滤器 — 在日志写入前自动脱敏。

    Usage:
        import logging
        logger = logging.getLogger()
        logger.addFilter(SensitiveDataFilter(level=DesensitizeLevel.MODERATE))
    """

    def __init__(
        self,
        level: DesensitizeLevel = DesensitizeLevel.MODERATE,
        patterns: Optional[List[Dict[str, Any]]] = None,
        exclude_fields: Optional[Set[str]] = None,
    ):
        super().__init__()
        self.level = level
        self.patterns = patterns or SENSITIVE_PATTERNS
        self.exclude_fields = exclude_fields or set()
        self._compiled: bool = False

    def filter(self, record: logging.LogRecord) -> bool:
        """自动脱敏日志消息。"""
        if record.msg and isinstance(record.msg, str):
            record.msg = self.desensitize(record.msg)
        if record.args and isinstance(record.args, dict):
            record.args = {
                k: self.desensitize(str(v)) if k not in self.exclude_fields else v
                for k, v in record.args.items()
            }
        return True

    def desensitize(self, text: str) -> str:
        """对文本执行脱敏变换。"""
        if not text or len(text) < 3:
            return text

        result = text
        for rule in self.patterns:
            rule_level = rule.get("level", "all")
            if not self._should_apply(rule_level):
                continue

            pattern = rule.get("pattern")
            if not pattern:
                continue

            # 使用回调函数或简单替换
            if self.level == DesensitizeLevel.MODERATE and "replacement_moderate" in rule:
                repl = rule["replacement_moderate"]
                if callable(repl):
                    result = pattern.sub(repl, result)
                else:
                    result = pattern.sub(repl, result)
            else:
                repl = rule.get("replacement", "****")
                result = pattern.sub(repl, result)

        return result

    def _should_apply(self, rule_level: str) -> bool:
        """判断该规则是否应在当前脱敏级别下生效。"""
        if rule_level == "all":
            return True
        if self.level == DesensitizeLevel.STRICT:
            return rule_level in ("strict", "moderate", "minimal")
        if self.level == DesensitizeLevel.MODERATE:
            return rule_level in ("moderate", "minimal")
        if self.level == DesensitizeLevel.MINIMAL:
            return rule_level == "minimal"
        return False


# ── 审计日志记录 ────────────────────────────────────────

class AuditLogger:
    """审计日志记录器 — 记录关键操作的安全审计事件。

    Usage:
        audit = AuditLogger()
        audit.log("user_login", user_id=123, ip="1.2.3.4")
    """

    def __init__(self, logger_name: str = "audit"):
        self._logger = logging.getLogger(logger_name)
        self._logger.setLevel(logging.INFO)

    def log(
        self,
        action: str,
        user_id: Optional[int] = None,
        resource: Optional[str] = None,
        ip: Optional[str] = None,
        success: bool = True,
        extra: Optional[Dict[str, Any]] = None,
    ):
        """记录一条审计日志。"""
        parts = [f"action={action}"]
        if user_id is not None:
            parts.append(f"user_id={user_id}")
        if resource:
            parts.append(f"resource={resource}")
        if ip:
            parts.append(f"ip={ip}")
        parts.append(f"success={success}")
        if extra:
            parts.append(f"extra={extra}")

        self._logger.info(" | ".join(parts))


# ── 公开 API ─────────────────────────────────────────────

_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def apply_log_desensitization(
    level: DesensitizeLevel = DesensitizeLevel.MODERATE,
    exclude_fields: Optional[Set[str]] = None,
):
    """在全局 root logger 上注册敏感数据过滤器。

    Usage (in main.py):
        from app.security.log_desensitizer import apply_log_desensitization, DesensitizeLevel
        apply_log_desensitization(level=DesensitizeLevel.MODERATE)
    """
    root_logger = logging.getLogger()
    filter_instance = SensitiveDataFilter(
        level=level,
        exclude_fields=exclude_fields or set(),
    )
    root_logger.addFilter(filter_instance)
    logging.getLogger(__name__).info(
        "[Desensitizer] Log desensitization enabled (level=%s)", level.value
    )
